"""The engine's type-coercion table, the converts, and the switch that gates it.

`coercions.json` is generated from the live TypeScript by `npm run gen:registry`
(scripts/gen-registry-json.ts probes `canCoerce` / `canCoerceValue` over every
node-type pair), so the pairs are never hardcoded here — when type-coercion.ts
changes, re-running the generator updates this data. It holds two distinct
tables mirroring the two coercion paths in CommandExecutor.ts:

- ``node``  — cross-type NODE coercions (`canCoerce` / `coerceNode`): a whole
  node fed where another type is expected (`\\text s` with a Scalar `s`). A
  coercion may expand into SEVERAL arguments — a Point in a Scalar slot becomes
  its two coordinate scalars, consuming two parameters (CommandExecutor.ts
  advances `paramIndex` by the number of coerced ids).
- ``value`` — element-wise Array VALUE coercions (`canCoerceValue`): an
  `Array<X>` fed to an `X'`-typed parameter, coerced element by element into a
  fresh array (always one argument).

`coerce_gnode` mirrors each convert function in type-coercion.ts: it returns
the (tape token, value node) pairs that replace the original argument. Where
the TS convert binds to an existing child node (circle→radius, line→p1/p2) or
a per-coordinate accessor (point→x/y) we emit the equivalent `base.prop`
reference; where it synthesizes a computed node (line length, complex→point,
arrow→array, →Text formatting) we emit the bare id and let the engine perform
the identical coercion at parse time.

Coercions are the engine's convenience for feeding a `Line` where a `Scalar` is
wanted, etc. They are **on by default**; disable them with `allow_coercions(False)`
to force strict exact-type matching.

WHEN type-coercion.ts GAINS (or drops) A COERCION:
  1. `npm run gen:registry`  — regenerates coercions.json from the live TS.
  2. `cd python && uv run pytest` — the parity test
     (test_parity.py::test_node_coercion_converts_cover_generated_table) fails,
     naming the pair that has no convert here (or the stale one to delete).
  3. Mirror the new convert function in `_NODE_CONVERTS` below, following the
     token rule in this docstring (prop ref for existing child nodes, bare id
     for synthesized ones).
Until step 3, using the new coercion raises a TypeError pointing here rather
than emitting a wrong-arity tape.
"""

from __future__ import annotations

import json
import math
from contextlib import contextmanager
from contextvars import ContextVar
from importlib.resources import files
from typing import Callable, Optional

from .nodes import Array, GNode, Point, Ref, Scalar, Text


def _load() -> tuple[frozenset[tuple[str, str]], frozenset[tuple[str, str]]]:
    data = json.loads((files("pygeomatic") / "coercions.json").read_text())
    node = frozenset((a, b) for a, b in data.get("node", []))
    value = frozenset((a, b) for a, b in data.get("value", []))
    return node, value


# Cross-type node coercions (canCoerce) and element-wise Array value coercions
# (canCoerceValue), keyed (fromType, toType).
NODE_COERCIONS, VALUE_COERCIONS = _load()


# ---------------------------------------------------------------------------
# Convert functions (python mirror of type-coercion.ts `convert`s)
# ---------------------------------------------------------------------------

# One coerced argument: the token that goes on the tape + the typed value node
# handed to the python numeric body.
CoercedArg = tuple[Ref, GNode]


def _format_number(v: float) -> str:
    """Mirror of type-coercion.ts formatNumber (integers plain, else 2 dp)."""
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}"


def _point_to_scalar(node: Point) -> list[CoercedArg]:
    # pointToScalar: a Point in a Scalar slot becomes its (x, y) scalars,
    # consuming TWO parameters.
    x, y = node.x, node.y
    return [(x.ref, x), (y.ref, y)]


def _line_to_point(node) -> list[CoercedArg]:
    # lineToPointsArray: binds to the line's existing endpoint nodes.
    p1, p2 = node.p1, node.p2
    return [(p1.ref, p1), (p2.ref, p2)]


def _line_to_scalar(node) -> list[CoercedArg]:
    # lineToScalar: a synthesized length node — no property to reference, so
    # the bare id goes on the tape and the engine coerces identically.
    length: Optional[float] = None
    p1, p2 = node._p1, node._p2
    if p1 is not None and p2 is not None and p1.numeric and p2.numeric:
        length = math.hypot(p2._x - p1._x, p2._y - p1._y)
    return [(node.ref, Scalar._new(length))]


def _circle_to_scalar(node) -> list[CoercedArg]:
    # circleToScalar: binds to the circle's existing radius node.
    r = node.radius
    return [(r.ref, r)]


def _circle_to_point(node) -> list[CoercedArg]:
    # circleToPoint: binds to the circle's existing center node.
    c = node.center
    return [(c.ref, c)]


def _complex_to_point(node) -> list[CoercedArg]:
    # complexToPoint: a synthesized (re, im) point node.
    return [(node.ref, Point._new(node._re, node._im))]


def _arrow_to_array(node) -> list[CoercedArg]:
    # arrowToArray: a synthesized [p2.x, p2.y] scalar array.
    p2 = node._p2
    elements = [
        Scalar._new(None if p2 is None else p2._x),
        Scalar._new(None if p2 is None else p2._y),
    ]
    return [(node.ref, Array._new("Scalar", elements))]


def _scalar_to_text(node: Scalar) -> list[CoercedArg]:
    # scalarToText: a synthesized formatted-value text node.
    v = node._value
    return [(node.ref, Text._new(None if v is None else _format_number(v)))]


def _point_to_text(node: Point) -> list[CoercedArg]:
    # pointToText: a synthesized "(x, y)" text node.
    known = node._x is not None and node._y is not None
    value = f"({_format_number(node._x)}, {_format_number(node._y)})" if known else None
    return [(node.ref, Text._new(value))]


# Keyed by (dispatched fromType, toType), exactly like type-coercion.ts's
# coercionMap. ScalarGradient/PointGradient reach these through their dispatch
# type, matching the engine.
_NODE_CONVERTS: dict[tuple[str, str], Callable[[GNode], list[CoercedArg]]] = {
    ("Point", "Scalar"): _point_to_scalar,
    ("Point", "Text"): _point_to_text,
    ("Line", "Point"): _line_to_point,
    ("Line", "Scalar"): _line_to_scalar,
    ("Circle", "Scalar"): _circle_to_scalar,
    ("Circle", "Point"): _circle_to_point,
    ("Complex", "Point"): _complex_to_point,
    ("Arrow", "Array"): _arrow_to_array,
    ("Scalar", "Text"): _scalar_to_text,
}


def coerce_gnode(node: GNode, node_type: str, target_type: str) -> list[CoercedArg]:
    """Apply the `node_type` → `target_type` node coercion to `node`.

    `node_type` is the DISPATCHED type (gradients already mapped to their
    payload type). Returns the (token, value) pairs that replace the argument —
    possibly more than one, consuming that many parameter slots, exactly as
    CommandExecutor.ts consumes `coercedIds.length` parameters.
    """
    convert = _NODE_CONVERTS.get((node_type, target_type))
    if convert is None:
        raise TypeError(
            f"coercion {node_type} -> {target_type} is declared in coercions.json "
            "but has no python convert — mirror the new type-coercion.ts entry "
            "in pygeomatic/coercions.py"
        )
    return convert(node)

# On by default; flip inside allow_coercions(False) to force strict matching.
_coercions_enabled: ContextVar[bool] = ContextVar("pygeomatic_coercions", default=True)


def coercions_enabled() -> bool:
    return _coercions_enabled.get()


@contextmanager
def allow_coercions(enabled: bool = True):
    """Toggle engine type-coercions for the duration of the block (on by default).

        with gm.allow_coercions(False):
            gm.some_fn(...)   # strict exact-type matching
    """
    token = _coercions_enabled.set(enabled)
    try:
        yield
    finally:
        _coercions_enabled.reset(token)
