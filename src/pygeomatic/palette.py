"""Named color palette — a thin convenience layer over the `load-colors` macro.

Nothing is hardcoded here. `gm.load_colors()` invokes the builtin
`\\load-colors` macro exactly like the DSL line does (one command on the tape,
body replayed → one Text node per `COLOR-*` id in the store) and returns those
nodes in a `ColorPalette` for attribute access (`pal.BLUE`). The color names
and hexes have a single source of truth: the macro definition in
`pygeomatic/macros.json` (the parity-tested copy of
`public/geomatic/macros/geometry.json`).
"""

from __future__ import annotations

from typing import Optional

from .nodes import Text
from .registry import REGISTRY
from .store import Store, _current_store, current_store


def _load_colors_macro():
    fdef = REGISTRY.get("load-colors")
    if fdef is None or not fdef.is_macro or fdef.py_func is None:
        raise RuntimeError(
            "the builtin 'load-colors' macro is not registered "
            "(was it unloaded via unload_macros?)"
        )
    return fdef


def color_ids() -> list[str]:
    """The `COLOR-*` ids the `load-colors` macro defines, in body order."""
    from .parse import _LINE_RE

    ids = []
    for line in _load_colors_macro().py_func.macro.body:
        m = _LINE_RE.match(line.strip())
        if m and m.group("out"):
            ids.append(m.group("out"))
    return ids


def build_palette() -> dict[str, str]:
    """id → hex, read off the macro body (a `COLOR-X = \\text "#hex"` per line).
    Exported as `gm.PALETTE` once the builtin macros are loaded."""
    with Store() as scratch:
        _load_colors_macro().py_func()
        return {cid: scratch.nodes[cid].numeric for cid in color_ids()}


class ColorPalette(dict):
    """`dict[str, Text]` keyed by the full id (`"COLOR-BLUE"`), with attribute
    access by the short name too: `pal.BLUE` == `pal["COLOR-BLUE"]`."""

    def __getattr__(self, name: str) -> Text:
        key = name if name.startswith("COLOR-") else f"COLOR-{name}"
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(name) from exc


def load_colors(store: Optional[Store] = None) -> ColorPalette:
    """Run the `\\load-colors` macro (same behavior as the DSL line: one
    command recorded, the `COLOR-*` Text nodes added to the store) and return
    the palette nodes. Call once, at the top of a scene (after any `\\clear`).
    Idempotent: a second call reuses the already-loaded nodes."""
    fdef = _load_colors_macro()
    ids = color_ids()
    store = store or current_store()

    if not all(cid in store.nodes for cid in ids):
        token = _current_store.set(store)
        try:
            fdef.py_func()
        finally:
            _current_store.reset(token)

    return ColorPalette({cid: store.nodes[cid] for cid in ids})
