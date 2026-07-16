"""Parse geomatic DSL lines back onto a Store — the inverse of emit.

`parse_dsl(text)` replays each line through the registered python function
(builtin or loaded extension), so the result is a normal tape: parsed nodes
are real pygeomatic nodes you can keep calling functions on, and
`emit()` after `parse_dsl()` round-trips the input deterministically.

Supported grammar (exactly what emit produces / the engine accepts):

    [id = ] \\keyword arg arg ...

where an arg is a number (positional notation), a node id, a property chain
(`v.p1.x`, whitelist-checked per node type), or — for `\\text` only — a quoted
string. Blank lines are skipped. Define-before-use is enforced (an id must
name an earlier output).

Engine-generated ids (`p0`, `num1`, ...) are accepted here — pasted scenes
legitimately contain them — even though pygeomatic rejects them for ids YOU
author (see store.validate_identifier).

Notes:
- A line without `id =` still allocates an auto id, so it re-emits as
  `p-0 = \\point 1 2`: different text, same scene.
- Extension commands parse only if their manifest is loaded
  (`load_extensions`) first. Macro invocations parse via the registered macro
  (builtins are auto-loaded; others need `load_macros`) and round-trip as the
  single macro line — the body is replayed but never re-emitted.
"""

from __future__ import annotations

import re
from typing import Iterable, Union

from .coercions import _coercions_enabled
from .nodes import GNode, NODE_PROPERTIES
from .prompting import python_name
from .registry import REGISTRY
from .store import _allow_engine_ids, current_store

_LINE_RE = re.compile(
    r"^(?:(?P<out>[A-Za-z][A-Za-z0-9-]*)\s*=\s*)?"
    r"\\(?P<kw>[A-Za-z][A-Za-z0-9-]*)"
    r"(?:\s+(?P<rest>.*))?$"
)
_TOKEN_RE = re.compile(r'"[^"]*"|\S+')
_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)\Z")
_REF_RE = re.compile(r"(?P<base>[A-Za-z][A-Za-z0-9-]*)(?P<path>(?:\.[A-Za-z][A-Za-z0-9]*)*)\Z")


class DslParseError(ValueError):
    """A DSL line could not be parsed or replayed."""

    def __init__(self, lineno: int, line: str, message: str) -> None:
        self.lineno = lineno
        self.line = line
        super().__init__(f"line {lineno}: {message}\n  {line}")


def _parse_number(tok: str) -> Union[int, float]:
    if "." in tok:
        return float(tok)
    return int(tok)


def _resolve_ref(tok: str, store, lineno: int, line: str):
    m = _REF_RE.match(tok)
    if m is None:
        raise DslParseError(lineno, line, f"cannot parse argument {tok!r}")
    base = m.group("base")
    node = store.nodes.get(base)
    if node is None:
        raise DslParseError(
            lineno, line, f"unknown node id {base!r} — geomatic requires define-before-use"
        )
    for field in m.group("path").lstrip(".").split(".") if m.group("path") else []:
        allowed = NODE_PROPERTIES.get(node.type, {})
        if field not in allowed:
            options = ", ".join(f".{p}" for p in allowed) or "none"
            raise DslParseError(
                lineno,
                line,
                f"{node.type} node {base!r} has no property {field!r} (accessible: {options})",
            )
        node = getattr(node, field)
    return node


def _resolve_token(tok: str, keyword: str, store, lineno: int, line: str):
    if tok.startswith('"'):
        if not (tok.endswith('"') and len(tok) >= 2):
            raise DslParseError(lineno, line, f"unterminated quoted string {tok!r}")
        if keyword != "text":
            raise DslParseError(
                lineno, line, 'quoted strings are only valid as the argument of \\text'
            )
        return tok[1:-1]
    if _NUMBER_RE.match(tok):
        return _parse_number(tok)
    return _resolve_ref(tok, store, lineno, line)


def _replay_line(lineno: int, raw: str, store) -> None:
    """Parse and execute one DSL line against `store` (blank lines are no-ops).

    Shared by `parse_dsl` and macro-body replay (macros.py)."""
    line = raw.strip()
    if not line:
        return
    m = _LINE_RE.match(line)
    if m is None:
        raise DslParseError(lineno, line, "expected `[id = ] \\keyword arg ...`")
    keyword = m.group("kw")
    fdef = REGISTRY.get(keyword)
    if fdef is None or fdef.py_func is None:
        hint = (
            " (an extension command or a macro? load it with gm.load_extensions /"
            " gm.load_macros first)"
            if keyword not in REGISTRY
            else ""
        )
        raise DslParseError(lineno, line, f"unknown command \\{keyword}{hint}")

    out = m.group("out")
    # `\copy` is the imperative command that still assigns an output id
    # (assigns_output=True); other imperatives reject an `id =` prefix —
    # their wrapper would silently ignore `out` otherwise. Macros accept an
    # optional id (the engine assigns it to the last body command).
    if out is not None and fdef.is_imperative and keyword != "copy":
        raise DslParseError(
            lineno, line, f"\\{keyword} is imperative and cannot be assigned to {out!r}"
        )

    rest = m.group("rest") or ""
    args = [
        _resolve_token(tok, keyword, store, lineno, line)
        for tok in _TOKEN_RE.findall(rest)
    ]
    try:
        if out is not None:
            fdef.py_func(*args, out=out)
        else:
            fdef.py_func(*args)
    except DslParseError:
        raise
    except (TypeError, ValueError) as exc:
        raise DslParseError(
            lineno, line, f"\\{keyword} (gm.{python_name(keyword)}): {exc}"
        ) from exc


def parse_dsl(text: Union[str, Iterable[str]]) -> dict[str, GNode]:
    """Replay DSL lines onto the active store; returns its id → node map.

    Use inside a Store context, then keep modifying with normal calls:

        with gm.Store() as s:
            nodes = gm.parse_dsl(dsl_text)
            gm.rotate(nodes["v"], nodes["center"], 30)
        print(gm.emit(s))
    """
    store = current_store()
    lines = text.splitlines() if isinstance(text, str) else list(text)

    # Replaying, not authoring: the input is engine-valid DSL, which may use
    # type-coercions (`\text someScalar`), so permit them here even though
    # authoring a scene from scratch keeps coercions off by default.
    token = _allow_engine_ids.set(True)
    coercion_token = _coercions_enabled.set(True)
    try:
        for lineno, raw in enumerate(lines, start=1):
            _replay_line(lineno, raw, store)
    finally:
        _allow_engine_ids.reset(token)
        _coercions_enabled.reset(coercion_token)

    return store.nodes
