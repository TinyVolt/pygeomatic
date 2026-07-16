"""Mirror of src/lib/geomatic/functions/implementations/planar-geometry.ts."""

from __future__ import annotations

from typing import Optional

import numpy as np

from ...nodes import Circle, Line, Point, Scalar, Triangle
from ...registry import P, geomatic_fn
from ..helpers import fnum, fxy

CATEGORY = "Planar Geometry"


def _line_pts(line: Line) -> Optional[tuple[np.ndarray, np.ndarray]]:
    if not isinstance(line, Line):
        return None
    a, b = fxy(line._p1), fxy(line._p2)
    if a is None or b is None:
        return None
    return np.array(a), np.array(b)


def _tri_pts(tri: Triangle) -> Optional[list[np.ndarray]]:
    if not isinstance(tri, Triangle) or len(tri._vertices) != 3:
        return None
    pts = [fxy(v) for v in tri._vertices]
    if any(p is None for p in pts):
        return None
    return [np.array(p) for p in pts]


@geomatic_fn(
    keyword="slope-of-line",
    name="SlopeOfLine",
    output="Scalar",
    params=[P("line", "Line")],
    category=CATEGORY,
)
def slope_of_line(line):
    pts = _line_pts(line)
    if pts is None:
        return Scalar._new(None)
    p1, p2 = pts
    d = np.subtract(p2, p1)
    angle = np.arctan2(d[1], d[0])
    # normalize [-π, π] → [0, 2π)
    return Scalar._new(np.mod(np.add(angle, 2 * np.pi), 2 * np.pi))


@geomatic_fn(
    keyword="mid-point",
    name="Midpoint",
    output="Point",
    params=[P("point1", "Point"), P("point2", "Point")],
    category=CATEGORY,
)
def mid_point(point1, point2):
    a, b = fxy(point1), fxy(point2)
    if a is None or b is None:
        return Point._new()
    return Point._new(
        np.divide(np.add(a[0], b[0]), 2),
        np.divide(np.add(a[1], b[1]), 2),
    )


@geomatic_fn(
    keyword="bisect-angle",
    name="AngleBisector",
    output="Line",
    params=[P("line1", "Line"), P("line2", "Line")],
    category=CATEGORY,
)
def bisect_angle(line1, line2):
    """Bisector of the angle at the shared endpoint of two lines. Mirrors the
    TS construction: cut both rays to the shorter length, take the midpoint of
    the two cut points, extend to the far chord when possible."""
    pts1, pts2 = _line_pts(line1), _line_pts(line2)
    if pts1 is None or pts2 is None:
        return Line._new()

    shared = None
    for i, a in enumerate(pts1):
        for j, b in enumerate(pts2):
            if np.allclose(a, b):
                shared, o1, o2 = a, pts1[1 - i], pts2[1 - j]
                break
        if shared is not None:
            break
    if shared is None:
        raise ValueError("bisect-angle: lines share no endpoint")

    v1 = np.subtract(o1, shared)
    v2 = np.subtract(o2, shared)
    len1, len2 = np.hypot(*v1), np.hypot(*v2)
    short = min(len1, len2)
    a_cut = np.add(shared, np.multiply(np.divide(v1, len1), short))
    b_cut = np.add(shared, np.multiply(np.divide(v2, len2), short))
    mid = np.divide(np.add(a_cut, b_cut), 2)

    # Extend the bisector from `shared` through `mid` to the chord o1-o2.
    inter = _line_intersection(shared, mid, o1, o2)
    end = inter if inter is not None else mid
    return Line._new(
        Point._new(shared[0], shared[1]),
        Point._new(end[0], end[1]),
    )


def _line_intersection(p1, p2, p3, p4) -> Optional[np.ndarray]:
    d1 = np.subtract(p1, p2)
    d2 = np.subtract(p3, p4)
    denom = np.subtract(np.multiply(d1[0], d2[1]), np.multiply(d1[1], d2[0]))
    if abs(denom) < 1e-10:
        return None
    c1 = np.subtract(np.multiply(p1[0], p2[1]), np.multiply(p1[1], p2[0]))
    c2 = np.subtract(np.multiply(p3[0], p4[1]), np.multiply(p3[1], p4[0]))
    x = np.divide(np.subtract(np.multiply(c1, d2[0]), np.multiply(d1[0], c2)), denom)
    y = np.divide(np.subtract(np.multiply(c1, d2[1]), np.multiply(d1[1], c2)), denom)
    return np.array([x, y])


def _project(point, line) -> Optional[np.ndarray]:
    p = fxy(point)
    pts = _line_pts(line)
    if p is None or pts is None:
        return None
    p = np.array(p)
    a, b = pts
    d = np.subtract(b, a)
    # epsilon mirrors the TS guard against zero-length lines
    len_sq = np.add(np.dot(d, d), 1e-10)
    t = np.divide(np.dot(np.subtract(p, a), d), len_sq)
    return np.add(a, np.multiply(t, d))


@geomatic_fn(
    keyword="project-point",
    name="ProjectPointOnLine",
    output="Point",
    params=[P("point", "Point"), P("line", "Line")],
    category=CATEGORY,
)
def project_point(point, line):
    proj = _project(point, line)
    if proj is None:
        return Point._new()
    return Point._new(proj[0], proj[1])


@geomatic_fn(
    keyword="reflect-point",
    name="ReflectPointAcrossLine",
    output="Point",
    params=[P("point", "Point"), P("line", "Line")],
    category=CATEGORY,
)
def reflect_point(point, line):
    proj = _project(point, line)
    p = fxy(point)
    if proj is None or p is None:
        return Point._new()
    refl = np.add(p, np.multiply(2, np.subtract(proj, p)))
    return Point._new(refl[0], refl[1])


@geomatic_fn(
    keyword="distance",
    name="Distance",
    output="Scalar",
    params=[P("point1", "Point"), P("point2", "Point", default="p0")],
    category=CATEGORY,
)
def distance(point1, point2):
    a, b = fxy(point1), fxy(point2)
    if a is None or b is None:
        return Scalar._new(None)
    return Scalar._new(np.hypot(np.subtract(a[0], b[0]), np.subtract(a[1], b[1])))


@geomatic_fn(
    keyword="angle",
    name="Angle",
    output="Scalar",
    params=[P("point1", "Point"), P("vertex", "Point"), P("point3", "Point")],
    category=CATEGORY,
)
def angle(point1, vertex, point3):
    """Angle at `vertex` in degrees (law of cosines, as in the TS impl)."""
    p1, v, p3 = fxy(point1), fxy(vertex), fxy(point3)
    if p1 is None or v is None or p3 is None:
        return Scalar._new(None)
    a2 = np.sum(np.square(np.subtract(p1, p3)))
    b2 = np.sum(np.square(np.subtract(v, p1)))
    c2 = np.sum(np.square(np.subtract(v, p3)))
    cos_val = np.divide(
        np.subtract(np.add(b2, c2), a2),
        np.multiply(2, np.multiply(np.sqrt(b2), np.sqrt(c2))),
    )
    return Scalar._new(np.degrees(np.arccos(cos_val)))


@geomatic_fn(
    keyword="area-triangle",
    name="AreaTriangle",
    output="Scalar",
    params=[P("triangle", "Triangle")],
    category=CATEGORY,
)
def area_triangle(tri):
    pts = _tri_pts(tri)
    if pts is None:
        return Scalar._new(None)
    p1, p2, p3 = pts
    cross = np.subtract(
        np.multiply(np.subtract(p2[0], p1[0]), np.subtract(p3[1], p1[1])),
        np.multiply(np.subtract(p2[1], p1[1]), np.subtract(p3[0], p1[0])),
    )
    return Scalar._new(np.divide(np.abs(cross), 2))


@geomatic_fn(
    keyword="area-circle",
    name="AreaCircle",
    output="Scalar",
    params=[P("circle", "Circle")],
    category=CATEGORY,
)
def area_circle(circle):
    r = fnum(circle._radius) if isinstance(circle, Circle) else None
    return Scalar._new(None if r is None else np.multiply(np.pi, np.square(r)))


@geomatic_fn(
    keyword="centroid",
    name="Centroid",
    output="Point",
    params=[P("triangle", "Triangle")],
    category=CATEGORY,
)
def centroid(tri):
    pts = _tri_pts(tri)
    if pts is None:
        return Point._new()
    c = np.divide(np.add(np.add(pts[0], pts[1]), pts[2]), 3)
    return Point._new(c[0], c[1])


@geomatic_fn(
    keyword="circumcenter",
    name="Circumcenter",
    output="Point",
    params=[P("triangle", "Triangle")],
    category=CATEGORY,
)
def circumcenter(tri):
    pts = _tri_pts(tri)
    if pts is None:
        return Point._new()
    (x1, y1), (x2, y2), (x3, y3) = pts
    s1 = np.add(np.square(x1), np.square(y1))
    s2 = np.add(np.square(x2), np.square(y2))
    s3 = np.add(np.square(x3), np.square(y3))
    d = np.multiply(
        2,
        np.add(
            np.add(
                np.multiply(x1, np.subtract(y2, y3)),
                np.multiply(x2, np.subtract(y3, y1)),
            ),
            np.multiply(x3, np.subtract(y1, y2)),
        ),
    )
    cx = np.divide(
        np.add(
            np.add(
                np.multiply(s1, np.subtract(y2, y3)),
                np.multiply(s2, np.subtract(y3, y1)),
            ),
            np.multiply(s3, np.subtract(y1, y2)),
        ),
        d,
    )
    cy = np.divide(
        np.add(
            np.add(
                np.multiply(s1, np.subtract(x3, x2)),
                np.multiply(s2, np.subtract(x1, x3)),
            ),
            np.multiply(s3, np.subtract(x2, x1)),
        ),
        d,
    )
    return Point._new(cx, cy)


@geomatic_fn(
    keyword="incenter",
    name="Incenter",
    output="Point",
    params=[P("triangle", "Triangle")],
    category=CATEGORY,
)
def incenter(tri):
    pts = _tri_pts(tri)
    if pts is None:
        return Point._new()
    p1, p2, p3 = pts
    a = np.hypot(*np.subtract(p2, p3))
    b = np.hypot(*np.subtract(p1, p3))
    c = np.hypot(*np.subtract(p1, p2))
    total = np.add(np.add(a, b), c)
    weighted = np.add(
        np.add(np.multiply(a, p1), np.multiply(b, p2)),
        np.multiply(c, p3),
    )
    center = np.divide(weighted, total)
    return Point._new(center[0], center[1])
