"""System (default) nodes every geomatic Store starts with.

Mirrors `GeomaticStore.initSystemNodes()` in
`src/lib/geomatic/state/GeomaticStore.ts`: a fresh interactive canvas always
registers these nodes *before* any user command runs, so a scene may reference
them by id without defining them first — `p0` (the origin), `T`/`F` (the
booleans), `learning-rate`, `unit`, `grid-origin`, ... They are how default
parameter values like `\\circle`'s `center` (`default="p0"`) resolve.

They are NOT part of the emitted DSL — they exist implicitly on every canvas —
so `register_system_nodes` seeds them into `store.nodes` WITHOUT recording any
command. A user command may reassign a system id (the engine's `saveNode` is
last-write-wins, and the `fermat-point-of-a-triangle` macro does exactly this
with `learning-rate = \\scalar 0.5`); `Store.allocate_id` therefore permits an
`out=` id that names a system node, while still rejecting other duplicates.

Keep this list in exact sync with `initSystemNodes()`. Because pygeomatic is
being spun out standalone, it carries its own copy rather than reading the web
repo's source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .nodes import Array, Bool, GNode, Point, Scalar, Text


@dataclass(frozen=True)
class SystemNode:
    """One default node: its id, a factory for a fresh instance, a `doc` line
    (what it is + when a scene should reference or reassign it), and the two
    canvas facts pygeomatic tracks for fidelity — whether the engine reserves
    the id in its NameGenerator, and whether the node is hidden by default."""

    id: str
    factory: Callable[[], GNode]
    doc: str
    reserve: bool = False  # engine calls nameGenerator.reserveName(id)
    hidden: bool = False  # in the store's default hiddenNodes set


# Ordered exactly as initSystemNodes() registers them. `doc` is the single
# source of truth surfaced to agents (skills/pygeomatic.md mirrors it).
SYSTEM_NODES: list[SystemNode] = [
    SystemNode(
        "p0",
        lambda: Point._new(0, 0),
        doc="The world origin (0, 0). It is the default `center`/`point2` for "
        "many commands (`\\circle`, `\\ellipse`, `\\square`, `\\rectangle`, "
        "`\\reflect-point`, ...), so reference it for a fixed origin instead of "
        "re-declaring `\\point 0 0`.",
        reserve=True,
        hidden=True,
    ),
    SystemNode(
        "learning-rate",
        lambda: Scalar._new(1e-2),
        doc="Gradient-descent step size (0.01), read by `\\gradient-descent-step` "
        "and `\\minimize`. Reassign it (`learning-rate = \\scalar 0.5`) before a "
        "descent step to tune training speed.",
    ),
    SystemNode(
        "animation-speed",
        lambda: Scalar._new(0.001),
        doc="Per-frame step size for `\\animate` (0.001). Reassign to make "
        "animations run faster (larger) or slower (smaller).",
    ),
    # `grid-points` is rebuilt from the live canvas bounds/unit, which pygeomatic
    # has no notion of; register an empty (numerically-unknown) Point array as a
    # referenceable stub so the id resolves.
    SystemNode(
        "grid-points",
        lambda: Array._new(element_type="Point", elements=[]),
        doc="Array of every integer-lattice Point currently on the canvas "
        "(built from the live canvas bounds, so numerically unknown here). "
        "Reference it to act on the whole background grid at once, e.g. apply a "
        "linear map / `\\translate-array` to every grid point.",
    ),
    SystemNode(
        "unit",
        lambda: Scalar._new(50),
        doc="Zoom: pixels per world unit (50); unitX == unitY == unit. Reassign "
        "to zoom (larger = more zoomed in).",
    ),
    SystemNode(
        "grid-opacity",
        lambda: Scalar._new(1),
        doc="Opacity of the grid lines and axes (1). Set to 0 to hide the grid.",
    ),
    SystemNode(
        "grid-bg-color",
        lambda: Text._new(""),
        doc="Solid fill painted behind the grid (empty = transparent). Reassign "
        "to a color (`grid-bg-color = COLOR-BLACK`) to give the canvas a "
        "background.",
        hidden=True,
    ),
    SystemNode(
        "grid-origin",
        lambda: Point._new(0, 0),
        doc="Where the world origin sits on the canvas, in world units "
        "((0, 0) = centered). Reassign to pan the view.",
        hidden=True,
    ),
    SystemNode(
        "T",
        lambda: Bool._new(True),
        doc="The boolean literal `true`, referenceable by id wherever a Bool "
        "argument is expected.",
        reserve=True,
    ),
    SystemNode(
        "F",
        lambda: Bool._new(False),
        doc="The boolean literal `false`, referenceable by id wherever a Bool "
        "argument is expected.",
        reserve=True,
    ),
]

SYSTEM_NODE_IDS: frozenset[str] = frozenset(spec.id for spec in SYSTEM_NODES)

# Python attribute name → node id (`learning_rate` → `learning-rate`), backing
# `gm.p0` / `gm.learning_rate` module attribute access (see __init__.__getattr__).
SYSTEM_NODE_ATTRS: dict[str, str] = {
    spec.id.replace("-", "_"): spec.id for spec in SYSTEM_NODES
}


def register_system_nodes(store) -> None:
    """Seed a fresh Store with the default nodes (no commands recorded)."""
    for spec in SYSTEM_NODES:
        if spec.reserve:
            store.names.reserve(spec.id)
        store.register(spec.factory(), spec.id)
