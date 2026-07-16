"""Infer a command's output id from the python assignment target.

`p = gm.point(3, 4)` emits `p = \\point 3 4` — no `out="p"` needed. The caller
frame's currently-executing CALL instruction carries the exact source span of
the call expression (PEP 657, python 3.11+); when that span is the value of a
simple single-target assignment (`name = call(...)`, `name: T = call(...)`,
`(name := call(...))`), the target's name becomes the output id, with python
underscores translated to DSL dashes (`fwd_traj` → `fwd-traj`).

Inference is best-effort and must never change what previously worked: any
doubt — unavailable source, non-assignment statement, tuple/attribute target,
an id that is invalid, engine-auto-shaped (`p1`, `num3`, ...), or already
taken in the store (loops, system defaults) — falls back to the auto-generated
id. An explicit `out=` always wins; calls originating inside pygeomatic
itself (parse replay, macro bodies) are never inferred.

Code run through `exec` sees no source unless its filename is seeded into
`linecache.cache` — runner.py's driver does this for `"<generated>"`.
"""

from __future__ import annotations

import ast
import linecache
from itertools import islice
from typing import Optional

from .store import ENGINE_AUTO_ID_RE, IDENTIFIER_RE, Store

Span = tuple[int, int, int, int]

# filename -> (source fingerprint, {call-expression span -> assignment target})
_span_cache: dict[str, tuple[int, dict[Span, str]]] = {}


def _assignment_spans(tree: ast.AST) -> dict[Span, str]:
    """Map the span of every `name = <call>`-shaped Call node to its name."""
    spans: dict[Span, str] = {}
    for node in ast.walk(tree):
        value: Optional[ast.expr]
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            value, name = node.value, node.targets[0].id
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and isinstance(
            node.target, ast.Name
        ):
            value, name = node.value, node.target.id
        else:
            continue
        if isinstance(value, ast.Call) and value.end_lineno is not None:
            spans[
                (value.lineno, value.end_lineno, value.col_offset, value.end_col_offset)
            ] = name
    return spans


def _call_target(frame) -> Optional[str]:
    """The variable the caller frame is assigning this call to, if any."""
    module = frame.f_globals.get("__name__") or ""
    if module == "pygeomatic" or module.startswith("pygeomatic."):
        return None
    code = frame.f_code
    lines = linecache.getlines(code.co_filename, frame.f_globals)
    if not lines:
        return None
    source = "".join(lines)
    fingerprint = hash(source)
    cached = _span_cache.get(code.co_filename)
    if cached is None or cached[0] != fingerprint:
        try:
            spans = _assignment_spans(ast.parse(source))
        except SyntaxError:
            spans = {}
        cached = (fingerprint, spans)
        _span_cache[code.co_filename] = cached
    pos = next(islice(code.co_positions(), frame.f_lasti // 2, None), None)
    if pos is None:
        return None
    return cached[1].get(pos)


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
