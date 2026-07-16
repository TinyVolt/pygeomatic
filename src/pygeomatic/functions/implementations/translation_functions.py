"""Mirror of src/lib/geomatic/functions/implementations/translation-functions.ts.

`translate` / `translate-array` mutate coordinates in place (final state; the
engine's animation frames are irrelevant to the mirror). `animate` sets the
scalar to its target value (its final state).
"""

from __future__ import annotations

import numpy as np

from ...nodes import (
    Arc,
    Array,
    Arrow,
    Circle,
    Ellipse,
    GNode,
    Line,
    Point,
    Polygon,
    RegularPolygon,
    Scalar,
    Triangle,
)
from ...registry import P, geomatic_fn
from ..helpers import fnum

CATEGORY = "Transformations"


def _translate_point(p: Point, dx: float, dy: float) -> None:
    if isinstance(p, Point) and p._x is not None and p._y is not None:
        p._x = float(np.add(p._x, dx))
        p._y = float(np.add(p._y, dy))


def _translate_node(obj: GNode, dx, dy) -> None:
    if dx is None or dy is None:
        return
    if isinstance(obj, Point):
        _translate_point(obj, dx, dy)
    elif isinstance(obj, (Line, Arrow)):
        for p in (obj._p1, obj._p2):
            if p is not None:
                _translate_point(p, dx, dy)
    elif isinstance(obj, (Circle, Ellipse, Arc, RegularPolygon)):
        if obj._center is not None:
            _translate_point(obj._center, dx, dy)
    elif isinstance(obj, (Triangle, Polygon)):
        for p in obj._vertices:
            _translate_point(p, dx, dy)
    elif isinstance(obj, Array):
        for el in obj._elements:
            _translate_node(el, dx, dy)


@geomatic_fn(
    keyword="translate-array",
    name="TranslateArray",
    output="Array",
    params=[P("array", "Array"), P("dx", "Scalar"), P("dy", "Scalar")],
    category=CATEGORY,
    imperative=True,
)
def translate_array(array, dx, dy):
    _translate_node(array, fnum(dx), fnum(dy))
    return array


@geomatic_fn(
    keyword="translate",
    name="Translate",
    output="Any",
    params=[P("obj", "Any"), P("dx", "Scalar"), P("dy", "Scalar")],
    category=CATEGORY,
    imperative=True,
)
def translate(obj, dx, dy):
    _translate_node(obj, fnum(dx), fnum(dy))
    return obj


@geomatic_fn(
    keyword="animate",
    name="Animate",
    output="Scalar",
    params=[P("s", "Scalar"), P("animateTo", "Scalar")],
    category=CATEGORY,
    imperative=True,
)
def animate(s, animateTo):
    target = fnum(animateTo)
    if isinstance(s, Scalar) and target is not None:
        s._value = target
    return s
