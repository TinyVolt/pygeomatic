"""Mirror of src/lib/geomatic/functions/implementations/rotation-functions.ts.

`rotate` mutates coordinates in place by an angle in DEGREES about a center
point (final state of the engine's animation). The per-type keyword:'' sub
implementations of the TS file collapse into the type dispatch below.
"""

from __future__ import annotations

import numpy as np

from ...nodes import Arrow, Circle, GNode, Line, Point, Polygon, Triangle
from ...registry import P, geomatic_fn
from ..helpers import fnum, fxy

CATEGORY = "Transformations"


def _rotate_point(p: Point, center: tuple[float, float], angle_rad: float) -> None:
    if not isinstance(p, Point) or p._x is None or p._y is None:
        return
    dx = np.subtract(p._x, center[0])
    dy = np.subtract(p._y, center[1])
    cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)
    p._x = float(np.add(center[0], np.subtract(np.multiply(dx, cos_a), np.multiply(dy, sin_a))))
    p._y = float(np.add(center[1], np.add(np.multiply(dx, sin_a), np.multiply(dy, cos_a))))


@geomatic_fn(
    keyword="rotate",
    name="Rotate",
    output="Any",
    params=[P("obj", "Any"), P("center", "Point"), P("angle", "Scalar")],
    category=CATEGORY,
    imperative=True,
)
def rotate(obj, center, angle):
    c = fxy(center)
    deg = fnum(angle)
    if c is None or deg is None:
        return obj
    rad = np.radians(deg)
    if isinstance(obj, Point):
        _rotate_point(obj, c, rad)
    elif isinstance(obj, (Line, Arrow)):
        for p in (obj._p1, obj._p2):
            if p is not None:
                _rotate_point(p, c, rad)
    elif isinstance(obj, Circle):
        if obj._center is not None:
            _rotate_point(obj._center, c, rad)
    elif isinstance(obj, (Triangle, Polygon)):
        for p in obj._vertices:
            _rotate_point(p, c, rad)
    else:
        raise TypeError(f"rotate: unsupported node type {obj.type if isinstance(obj, GNode) else type(obj)}")
    return obj
