"""Infer a command's output id from the python assignment target.

`p = gm.point(3, 4)` emits `p = \\point 3 4` — no `out="p"` needed. The
caller's bytecode tells us whether this call's result is stored to a simple
name: the frame's currently-executing CALL instruction is immediately followed
by STORE_NAME/STORE_FAST/... exactly for `name = call(...)` (and, with an
intervening `COPY 1`, for a walrus `(name := call(...))`). Working from
bytecode instead of source text makes the behavior identical everywhere —
files, the REPL, `python -c`, notebooks, `exec`'d strings.

Inference is best-effort and must never change what previously worked: any
doubt — no store (nested call arguments, expression statements), an ambiguous
target (tuple unpacking, chained `a = b = ...`, attribute/subscript targets),
or an id that is invalid, engine-auto-shaped (`p1`, `num3`, ...), or already
taken in the store (loops, system defaults) — falls back to the auto-generated
id. Python underscores translate to DSL dashes (`fwd_traj` → `fwd-traj`). An
explicit `out=` always wins; calls originating inside pygeomatic itself
(parse replay, macro bodies) are never inferred.
"""

from __future__ import annotations

import dis
from bisect import bisect_right
from types import CodeType
from typing import Optional
from weakref import WeakKeyDictionary

from .store import ENGINE_AUTO_ID_RE, IDENTIFIER_RE, Store

_CALL_OPS = frozenset({"CALL", "CALL_KW", "CALL_FUNCTION_EX"})
_STORE_OPS = frozenset({"STORE_NAME", "STORE_FAST", "STORE_GLOBAL", "STORE_DEREF"})

# code object -> (sorted instruction offsets, {CALL offset -> stored name})
_targets_cache: WeakKeyDictionary[
    CodeType, tuple[list[int], dict[int, str]]
] = WeakKeyDictionary()


def _assignment_targets(code: CodeType) -> tuple[list[int], dict[int, str]]:
    """Instruction offsets + map of each CALL stored to a simple name."""
    targets: dict[int, str] = {}
    instructions = [
        ins for ins in dis.get_instructions(code) if ins.opname != "EXTENDED_ARG"
    ]

    def op(i: int) -> str:
        return instructions[i].opname if i < len(instructions) else ""

    for i, ins in enumerate(instructions):
        if ins.opname not in _CALL_OPS:
            continue
        if op(i + 1) in _STORE_OPS and op(i + 2) not in _STORE_OPS:
            # `name = call(...)` / `name: T = call(...)`. A second store
            # right after is a function-scope unpack `a, b = ..., call(...)`
            # (module scope emits SWAP instead) — ambiguous, skipped.
            targets[ins.offset] = instructions[i + 1].argval
        elif (
            op(i + 1) == "COPY"
            and instructions[i + 1].arg == 1
            and op(i + 2) in _STORE_OPS
            and op(i + 3) not in _STORE_OPS
        ):
            # walrus `(name := call(...))`; a second store would make it a
            # chained `a = b = call(...)` — ambiguous, skipped
            targets[ins.offset] = instructions[i + 2].argval
    return [ins.offset for ins in instructions], targets


def _call_target(frame) -> Optional[str]:
    """The variable the caller frame is assigning this call to, if any."""
    module = frame.f_globals.get("__name__") or ""
    if module == "pygeomatic" or module.startswith("pygeomatic."):
        return None
    code = frame.f_code
    cached = _targets_cache.get(code)
    if cached is None:
        cached = _assignment_targets(code)
        _targets_cache[code] = cached
    offsets, targets = cached
    # f_lasti may point into the CALL's inline cache entries; resolve to the
    # owning instruction (greatest offset <= f_lasti).
    idx = bisect_right(offsets, frame.f_lasti) - 1
    if idx < 0:
        return None
    return targets.get(offsets[idx])


def infer_out_name(frame, store: Store) -> Optional[str]:
    """Output id for the command call executing in `frame`, or None."""
    try:
        name = _call_target(frame)
        if name is None:
            return None
        candidate = name.replace("_", "-")
        if not IDENTIFIER_RE.match(candidate):
            return None
        if ENGINE_AUTO_ID_RE.match(candidate):
            # p1/num3/... are the engine's internal auto-name space; claiming
            # one silently clobbers auxiliary nodes on replay.
            return None
        if candidate in store.nodes:
            # Taken (loop reuse, or a system default like T/F) — an inferred
            # name never reassigns; only an explicit out= may.
            return None
        return candidate
    except Exception:
        # Inference is a convenience; a scene must never fail because of it.
        return None
