"""Geomatic macros — named bundles of DSL commands, runnable as one command.

A macro is what `downloadMacro.ts` exports and `MacroLoader.ts` registers: a
JSON array of `{"macro": "<name> [param ...]", "commands": [...]}` objects.
Invoking `\\<name> args...` runs the body commands on the shared store with
each parameter name substituted by the corresponding argument's id; an
`id = \\<name> ...` invocation assigns `id` to the LAST body command (if that
command has no id of its own). The builtin macros the interactive editor
auto-loads (`public/geomatic/macros/geometry.json`) ship with pygeomatic as
`macros.json` — a checked-in copy, kept in sync by the parity test, because
pygeomatic is being spun out standalone.

pygeomatic mirrors the engine exactly, with one tape rule: a macro invocation
records ONE command (`\\load-colors`, `\\zero-back-step loss`), never its body —
so `emit()` after `parse_dsl()` still round-trips. The body IS replayed
locally (store._macro_replay mode: no recording, engine-style undashed auto
ids, last-write-wins), so every node the macro creates (`COLOR-BLUE`,
`points`, ...) is a real store node later lines can reference.

`load_macros(source)` registers additional macros on the fly — `source` is a
path, a URL, a JSON string, or an already-parsed list of dicts — mirroring
`load_extensions`. `unload_macros(source)` removes them again.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Optional, Union

from .coercions import _coercions_enabled
from .emit import _render_number
from .inference import infer_out_name
from .nodes import GNode
from .prompting import python_name
from .registry import FunctionDef, P, REGISTRY
from .store import (
    IDENTIFIER_RE,
    _allow_engine_ids,
    _macro_replay,
    current_store,
)

MACRO_CATEGORY = "Macros"
BUILTIN_SOURCE = "builtin:macros.json"

# macro source → keywords it registered (provenance for unload/replace)
_LOADED: dict[str, list[str]] = {}
# keyword → source that owns it
_KEYWORD_SOURCE: dict[str, str] = {}
# package attributes we created (never overwrite a pre-existing gm attribute,
# e.g. gm.load_colors is palette.py's ColorPalette wrapper around this macro)
_SET_ATTRS: set[str] = set()


class MacroError(ValueError):
    """A macro definition is malformed or conflicts with loaded functions."""


@dataclass(frozen=True)
class MacroDef:
    """Mirror of MacroSchema.ts MacroDefinition."""

    keyword: str
    params: tuple[str, ...]
    body: tuple[str, ...]
    assigned_ids: frozenset[str]


# ---------------------------------------------------------------------------
# Definition parsing & validation
# ---------------------------------------------------------------------------


def _fetch(source: str) -> Any:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    text = source.lstrip()
    if text.startswith("["):  # a JSON string, not a path
        return json.loads(text)
    return json.loads(Path(source).read_text())


def _parse_signature(source: str, signature: str) -> tuple[str, tuple[str, ...]]:
    parts = signature.split()
    if not parts:
        raise MacroError(f"{source}: empty macro name")
    keyword, *params = parts
    for name in parts:
        if not IDENTIFIER_RE.match(name):
            raise MacroError(
                f"{source}: macro {signature!r}: {name!r} is not a valid geomatic "
                "identifier (letters, digits, dashes; must start with a letter)"
            )
    if len(set(params)) != len(params):
        raise MacroError(f"{source}: macro {signature!r} has duplicate parameter names")
    return keyword, tuple(params)


def _body_assigned_ids(body: tuple[str, ...]) -> frozenset[str]:
    from .parse import _LINE_RE  # deferred: parse imports registry like we do

    ids = set()
    for line in body:
        m = _LINE_RE.match(line.strip())
        if m and m.group("out"):
            ids.add(m.group("out"))
    return ids


def _validate(source: str, data: Any) -> list[MacroDef]:
    if not isinstance(data, list) or not data:
        raise MacroError(f"{source}: expected a non-empty JSON array of macros")
    macros: list[MacroDef] = []
    seen: set[str] = set()
    for entry in data:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("macro"), str)
            or not isinstance(entry.get("commands"), list)
            or not all(isinstance(c, str) for c in entry["commands"])
        ):
            raise MacroError(
                f"{source}: each macro must be {{'macro': str, 'commands': [str, ...]}}"
            )
        keyword, params = _parse_signature(source, entry["macro"])
        if keyword in seen:
            raise MacroError(f"{source}: duplicate macro keyword {keyword!r}")
        seen.add(keyword)
        body = tuple(entry["commands"])
        if not body:
            raise MacroError(f"{source}: macro {keyword!r} has an empty body")
        macros.append(
            MacroDef(
                keyword=keyword,
                params=params,
                body=body,
                assigned_ids=_body_assigned_ids(body),
            )
        )
    return macros


# ---------------------------------------------------------------------------
# Invocation (replay the body with engine semantics, record one command)
# ---------------------------------------------------------------------------


def _substitute(line: str, subs: dict[str, str]) -> str:
    """Whole-token substitution of parameter names in a body line's arguments
    (mirrors MacroLoader.ts: only parsed args are mapped, never the keyword or
    the assigned id; quoted strings never match an identifier)."""
    from .parse import _LINE_RE, _TOKEN_RE

    m = _LINE_RE.match(line.strip())
    if m is None or not m.group("rest"):
        return line
    rest = _TOKEN_RE.sub(lambda t: subs.get(t.group(0), t.group(0)), m.group("rest"))
    head = f"{m.group('out')} = " if m.group("out") else ""
    return f"{head}\\{m.group('kw')} {rest}"


def _make_wrapper(macro: MacroDef, source: str):
    def wrapper(*args, out: Optional[str] = None):
        from .parse import _LINE_RE, _replay_line

        store = current_store()
        if len(args) != len(macro.params):
            raise TypeError(
                f"\\{macro.keyword} takes {len(macro.params)} argument(s) "
                f"({' '.join(macro.params) or 'none'}), got {len(args)}"
            )
        subs: dict[str, str] = {}
        tokens = []
        for name, arg in zip(macro.params, args):
            if isinstance(arg, GNode):
                if arg.id is None:
                    raise TypeError(
                        f"\\{macro.keyword}: parameter {name!r} got an unregistered node"
                    )
                if arg.id in macro.assigned_ids:
                    raise ValueError(
                        f"\\{macro.keyword}: input id {arg.id!r} conflicts with an "
                        "internal macro variable"
                    )
                tokens.append(arg.ref)
                subs[name] = arg.id
            elif isinstance(arg, bool):
                raise TypeError(f"\\{macro.keyword}: parameter {name!r} cannot take a bool")
            elif isinstance(arg, (int, float)):
                tokens.append(arg)
                subs[name] = _render_number(arg)
            else:
                raise TypeError(
                    f"\\{macro.keyword}: parameter {name!r} expects a node or a "
                    f"number, got {type(arg).__name__!r}"
                )

        if out is None:
            out = infer_out_name(sys._getframe(1), store)

        replay_token = _macro_replay.set(True)
        engine_token = _allow_engine_ids.set(True)
        coercion_token = _coercions_enabled.set(True)
        try:
            for i, raw in enumerate(macro.body):
                line = _substitute(raw, subs)
                if i == len(macro.body) - 1 and out is not None:
                    m = _LINE_RE.match(line.strip())
                    # engine: assignedId only applies if the last command has
                    # no id of its own
                    if m is not None and not m.group("out"):
                        line = f"{out} = {line.strip()}"
                _replay_line(i + 1, line, store)
        finally:
            _macro_replay.reset(replay_token)
            _allow_engine_ids.reset(engine_token)
            _coercions_enabled.reset(coercion_token)

        # ONE line on the tape for the whole macro (recorded after the replay
        # context exits, so nested macro invocations stay off the tape).
        store.record(macro.keyword, tokens, out)
        return store.nodes.get(out) if out is not None else None

    wrapper.macro = macro  # type: ignore[attr-defined]  # introspection (palette.py)
    wrapper.__name__ = python_name(macro.keyword)
    wrapper.__doc__ = (
        f"Macro \\{macro.keyword} (from {source}); expands to:\n  "
        + "\n  ".join(macro.body)
    )
    return wrapper


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def _pkg():
    import pygeomatic

    return pygeomatic


def _register_one(macro: MacroDef, source: str) -> str:
    fdef = FunctionDef(
        keyword=macro.keyword,
        name=macro.keyword,
        params=[P(name=n, type="Any") for n in macro.params],
        output_type="Any",
        category=MACRO_CATEGORY,
        is_macro=True,
    )
    wrapper = _make_wrapper(macro, source)
    wrapper.geomatic = fdef  # type: ignore[attr-defined]
    fdef.py_func = wrapper
    REGISTRY[macro.keyword] = fdef
    _KEYWORD_SOURCE[macro.keyword] = source

    # Expose gm.<python_name>() — but never clobber a pre-existing package
    # attribute (gm.load_colors is palette.py's ColorPalette wrapper, which
    # delegates to this macro's py_func).
    py = python_name(macro.keyword)
    pkg = _pkg()
    if py in _SET_ATTRS or not hasattr(pkg, py):
        setattr(pkg, py, wrapper)
        _SET_ATTRS.add(py)
    else:
        # The keeper (palette's load_colors) is still the python export for
        # this keyword; point its .geomatic at the macro's FunctionDef.
        existing = getattr(pkg, py)
        if getattr(existing, "geomatic", None) is None:
            existing.geomatic = fdef
    return macro.keyword


def _unregister_keywords(keywords: list[str]) -> None:
    pkg = _pkg()
    for kw in keywords:
        fdef = REGISTRY.pop(kw, None)
        _KEYWORD_SOURCE.pop(kw, None)
        py = python_name(kw)
        if py in _SET_ATTRS:
            _SET_ATTRS.discard(py)
            if getattr(pkg, py, None) is not None:
                delattr(pkg, py)
        else:
            existing = getattr(pkg, py, None)
            if existing is not None and getattr(existing, "geomatic", None) is fdef:
                del existing.geomatic


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_macros(source: Union[str, list], name: Optional[str] = None) -> list[str]:
    """Register macros from a JSON file path, URL, JSON string, or an
    already-parsed `[{"macro": ..., "commands": [...]}, ...]` list.

    Returns the registered keywords. Re-loading the same source replaces its
    previous macros; collisions with builtins, extensions, or another source's
    macros raise. For a list input, pass `name=` to give it a stable source
    key (defaults to "inline").
    """
    if isinstance(source, list):
        key = name or "inline"
        data = source
    else:
        key = name or source
        data = _fetch(source)
    macros = _validate(key, data)

    # Validate all collisions before touching the registry (atomic load).
    for macro in macros:
        kw = macro.keyword
        owner = _KEYWORD_SOURCE.get(kw)
        if kw in REGISTRY and owner is None:
            raise MacroError(
                f"{key}: macro keyword {kw!r} collides with an existing geomatic command"
            )
        if owner is not None and owner != key:
            raise MacroError(
                f"{key}: macro keyword {kw!r} is already provided by {owner!r} — "
                "unload that source first"
            )

    previous = _LOADED.pop(key, None)
    if previous:
        _unregister_keywords(previous)

    keywords = [_register_one(macro, key) for macro in macros]
    _LOADED[key] = keywords
    return keywords


def unload_macros(source: str) -> list[str]:
    """Remove every macro registered from `source`. Returns their keywords."""
    keywords = _LOADED.pop(source, None)
    if keywords is None:
        known = ", ".join(sorted(_LOADED)) or "none"
        raise KeyError(f"no macros loaded from {source!r} (loaded sources: {known})")
    _unregister_keywords(keywords)
    return keywords


def loaded_macros() -> dict[str, list[str]]:
    """Currently loaded macro sources and the keywords each provides."""
    return {src: list(kws) for src, kws in _LOADED.items()}


def load_builtin_macros() -> list[str]:
    """(Re-)register the builtin macros shipped as pygeomatic/macros.json —
    the same set the interactive editor auto-loads. Called once at import."""
    data = json.loads((files("pygeomatic") / "macros.json").read_text())
    return load_macros(data, name=BUILTIN_SOURCE)
