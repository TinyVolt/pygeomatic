"""Infer a command's output id from the python assignment target.

`p = gm.point(3, 4)` emits `p = \\point 3 4` — no `out="p"` needed. A small
symbolic simulation of the caller's bytecode tracks which stack slot holds
which CALL / BINARY_OP / BINARY_SUBSCR result and which simple name (if any)
each result is stored to. Working from bytecode instead of source text makes
the behavior identical everywhere — files, the REPL, `python -c`, notebooks,
`exec`'d strings.

Covered shapes:
- `name = call(...)`, `name: T = call(...)`, walrus `(name := call(...))`
- multi-target `a, b, c = f(...), g(...), h(...)` at any arity, both scopes
- chained `a = b = call(...)`: every target becomes its own DSL node (the
  python object carries the first id; a clone is registered per extra name)
- infix operators / indexing: `c = a + b`, `x = arr[i]` name the result even
  though the recording call happens one frame down inside a GNode dunder

The simulation is conservative by construction: the virtual stack is cleared
at jump targets, jumps, and any unmodeled opcode, so a name is only inferred
when the full data flow from the producing instruction to its STORE was
understood. Anything unclear — attribute/subscript
targets, expression statements — falls back to the auto-generated id, as does
an id that is invalid, engine-auto-shaped (`p1`, `num3`, ...), or already
taken in the store (loops, system defaults; article mode instead reassigns —
last-write-wins, see article.py). Python underscores translate to
DSL dashes (`fwd_traj` → `fwd-traj`). An explicit `out=` always wins; calls
originating inside pygeomatic itself (parse replay, macro bodies) are never
inferred.
"""

from __future__ import annotations

import dis
from bisect import bisect_right
from types import CodeType, FrameType
from typing import Optional, Union
from weakref import WeakKeyDictionary

from .store import ENGINE_AUTO_ID_RE, IDENTIFIER_RE, Store, _article_replay

_STORE_OPS = frozenset({"STORE_NAME", "STORE_FAST", "STORE_GLOBAL", "STORE_DEREF"})

# Ops whose pushed value we track as a nameable marker.
_VALUE_OPS = frozenset(
    {
        "CALL",
        "CALL_KW",
        "CALL_FUNCTION_EX",
        "BINARY_OP",
        "BINARY_SUBSCR",
        "UNARY_NEGATIVE",
    }
)

# Plain loads and no-ops with fixed stack behavior.
_PUSH_ONE = frozenset(
    {
        "LOAD_CONST",
        "LOAD_NAME",
        "LOAD_FAST",
        "LOAD_FAST_CHECK",
        "LOAD_FAST_AND_CLEAR",
        "LOAD_DEREF",
        "LOAD_CLOSURE",
        "PUSH_NULL",
    }
)
_NO_EFFECT = frozenset({"NOP", "RESUME", "PRECALL", "KW_NAMES", "EXTENDED_ARG"})

# GNode frames that sit between the user's operator expression and the
# recording wrapper; inference hops over them to the user frame.
_DUNDER_FRAME_NAMES = frozenset(
    {
        "_infix",
        "_arith",
        "__add__",
        "__radd__",
        "__sub__",
        "__rsub__",
        "__mul__",
        "__rmul__",
        "__truediv__",
        "__rtruediv__",
        "__neg__",
        "__getitem__",
    }
)

# A marker is the offset of the instruction that produced the value; opaque
# stack entries are None; BUILD_TUPLE groups become lists of entries.
_Entry = Union[int, None, list]

# code object -> (sorted instruction offsets, {value-op offset -> stored names})
_targets_cache: WeakKeyDictionary[
    CodeType, tuple[list[int], dict[int, list[str]]]
] = WeakKeyDictionary()

_JUMPY = frozenset(dis.hasjrel) | frozenset(dis.hasjabs)


def _assignment_targets(code: CodeType) -> tuple[list[int], dict[int, list[str]]]:
    """Instruction offsets + map of each nameable value-op to its target(s).

    A marker stored to several names (chained `a = b = call(...)`, or a walrus
    whose value is then assigned) yields all of them in store order; the
    recorder gives the first one to the node and records a clone per extra.
    """
    targets: dict[int, list[str]] = {}
    stack: list[_Entry] = []

    def pop(n: int = 1) -> list[_Entry]:
        taken: list[_Entry] = []
        for _ in range(n):
            taken.append(stack.pop() if stack else None)
        return taken

    def store(entry: _Entry, name: str) -> None:
        if isinstance(entry, int):
            targets.setdefault(entry, []).append(name)

    instructions = list(dis.get_instructions(code))
    for ins in instructions:
        if ins.is_jump_target:
            stack.clear()
        op = ins.opname
        if op in _PUSH_ONE:
            stack.append(None)
        elif op == "LOAD_GLOBAL":  # arg&1 → also pushes NULL
            stack.append(None)
            if ins.arg is not None and ins.arg & 1:
                stack.append(None)
        elif op == "LOAD_ATTR":  # arg&1 → method form pushes two entries
            pop(1)
            stack.append(None)
            if ins.arg is not None and ins.arg & 1:
                stack.append(None)
        elif op == "LOAD_METHOD":  # 3.11
            pop(1)
            stack.extend((None, None))
        elif op == "COPY":
            n = ins.arg or 1
            stack.append(stack[-n] if len(stack) >= n else None)
        elif op == "SWAP":
            n = ins.arg or 1
            if len(stack) >= n:
                stack[-1], stack[-n] = stack[-n], stack[-1]
            else:
                stack.clear()
        elif op in _VALUE_OPS:
            if op == "CALL":
                pop((ins.arg or 0) + 2)
            elif op == "CALL_KW":
                pop((ins.arg or 0) + 3)
            elif op == "CALL_FUNCTION_EX":
                pop(3 + (1 if ins.arg is not None and ins.arg & 1 else 0))
            elif op == "BINARY_OP" or op == "BINARY_SUBSCR":
                pop(2)
            else:  # UNARY_NEGATIVE
                pop(1)
            stack.append(ins.offset)
        elif op in {"UNARY_NOT", "UNARY_INVERT", "UNARY_POSITIVE", "TO_BOOL"}:
            pop(1)
            stack.append(None)
        elif op in {"COMPARE_OP", "IS_OP", "CONTAINS_OP"}:
            pop(2)
            stack.append(None)
        elif op in _STORE_OPS:
            store(pop(1)[0], ins.argval)
        elif op == "STORE_ATTR":
            pop(2)
        elif op == "STORE_SUBSCR":
            pop(3)
        elif op == "POP_TOP":
            pop(1)
        elif op in {"BUILD_TUPLE", "BUILD_LIST", "BUILD_SET"}:
            n = ins.arg or 0
            elems = pop(n)
            elems.reverse()
            stack.append(elems)
        elif op == "BUILD_MAP":
            pop(2 * (ins.arg or 0))
            stack.append(None)
        elif op == "UNPACK_SEQUENCE":
            n = ins.arg or 0
            top = pop(1)[0]
            if isinstance(top, list) and len(top) == n:
                stack.extend(top[::-1])  # first target's value ends on top
            else:
                stack.extend([None] * n)
        elif op in {"LIST_APPEND", "SET_ADD", "LIST_EXTEND", "SET_UPDATE"}:
            pop(1)
        elif op in {"MAP_ADD", "DICT_UPDATE", "DICT_MERGE"}:
            pop(2 if op == "MAP_ADD" else 1)
        elif op in _NO_EFFECT:
            pass
        elif op in {"RETURN_VALUE", "RETURN_CONST"} or ins.opcode in _JUMPY:
            stack.clear()
        else:
            # Unmodeled opcode: naming only from fully-understood flow.
            stack.clear()

    return [ins.offset for ins in instructions], targets


def _hop_dunder_frames(frame: FrameType) -> Optional[FrameType]:
    """Skip GNode operator-dunder frames so `c = a + b` reads the user frame."""
    hops = 0
    while (
        frame is not None
        and hops < 4
        and (frame.f_globals.get("__name__") or "") == "pygeomatic.nodes"
        and frame.f_code.co_name in _DUNDER_FRAME_NAMES
    ):
        frame = frame.f_back
        hops += 1
    return frame


def _call_targets(frame: FrameType) -> list[str]:
    """The variables the caller frame is assigning this operation to."""
    frame = _hop_dunder_frames(frame)
    if frame is None:
        return []
    module = frame.f_globals.get("__name__") or ""
    if module == "pygeomatic" or module.startswith("pygeomatic."):
        return []
    code = frame.f_code
    cached = _targets_cache.get(code)
    if cached is None:
        cached = _assignment_targets(code)
        _targets_cache[code] = cached
    offsets, targets = cached
    # f_lasti may point into the instruction's inline cache entries; resolve
    # to the owning instruction (greatest offset <= f_lasti).
    idx = bisect_right(offsets, frame.f_lasti) - 1
    if idx < 0:
        return []
    return targets.get(offsets[idx], [])


def infer_out_names(frame, store: Store) -> list[str]:
    """Usable output ids for the command executing in `frame`, in assignment
    order, deduplicated. First entry names the node itself; the recorder
    registers a clone per extra entry (chained `a = b = call(...)`)."""
    try:
        candidates: list[str] = []
        for name in _call_targets(frame):
            candidate = name.replace("_", "-")
            if candidate in candidates:
                continue
            if not IDENTIFIER_RE.match(candidate):
                continue
            if ENGINE_AUTO_ID_RE.match(candidate):
                # p1/num3/... are the engine's internal auto-name space;
                # claiming one silently clobbers auxiliary nodes on replay.
                continue
            if candidate in store.nodes and not _article_replay.get():
                # Taken (loop reuse, or a system default like T/F) — an
                # inferred name never reassigns; only an explicit out= may.
                # Articles are the exception: `s1 = gm.scalar(1)` there means
                # what the DSL line `s1 = \scalar 1` means — last-write-wins.
                continue
            candidates.append(candidate)
        return candidates
    except Exception:
        # Inference is a convenience; a scene must never fail because of it.
        return []


def infer_out_name(frame, store: Store) -> Optional[str]:
    """First usable output id for the command executing in `frame`, or None."""
    names = infer_out_names(frame, store)
    return names[0] if names else None
