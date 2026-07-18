"""Mirror of src/lib/geomatic/functions/implementations/intersections.ts.

Solution ordering matches the TS implementations: for quadratic cases the
first point uses t1 = (-b + sqrt(disc)) / 2a, the second t2 = (-b - sqrt(disc)) / 2a.
Degenerate cases (no intersection) return an empty/unknown node, where the
engine returns a Dummy.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ...nodes import Array, BezierQuadratic, Circle, Dummy, Ellipse, Line, Point
from ...registry import P, geomatic_fn
from ..helpers import fnum, fxy, point_array

CATEGORY = "Intersections"


def _line_pts(line) -> Optional[tuple[np.ndarray, np.ndarray]]:
    if not isinstance(line, Line):
        return None
    a, b = fxy(line._p1), fxy(line._p2)
    if a is None or b is None:
        return None
    return np.array(a), np.array(b)


def _points_from_ts(a: np.ndarray, d: np.ndarray, ts: list[float]) -> Array:
    pts = [Point._new(*np.add(a, np.multiply(t, d))) for t in ts]
    return point_array(pts)


@geomatic_fn(
    keyword="intersection-line-line",
    name="LineLineIntersection",
    output="Point",
    params=[P("line1", "Line"), P("line2", "Line")],
    category=CATEGORY,
)
def intersection_line_line(line1, line2):
    pts1, pts2 = _line_pts(line1), _line_pts(line2)
    if pts1 is None or pts2 is None:
        return Point._new()
    (x1, y1), (x2, y2) = pts1
    (x3, y3), (x4, y4) = pts2
    denom = np.subtract(
        np.multiply(np.subtract(x1, x2), np.subtract(y3, y4)),
        np.multiply(np.subtract(y1, y2), np.subtract(x3, x4)),
    )
    if abs(denom) < 1e-10:
        return Dummy._new()
    c1 = np.subtract(np.multiply(x1, y2), np.multiply(y1, x2))
    c2 = np.subtract(np.multiply(x3, y4), np.multiply(y3, x4))
    px = np.divide(
        np.subtract(np.multiply(c1, np.subtract(x3, x4)), np.multiply(np.subtract(x1, x2), c2)),
        denom,
    )
    py = np.divide(
        np.subtract(np.multiply(c1, np.subtract(y3, y4)), np.multiply(np.subtract(y1, y2), c2)),
        denom,
    )
    return Point._new(px, py)


@geomatic_fn(
    keyword="intersection-line-circle",
    name="LineCircleIntersection",
    output="Array",
    params=[P("line", "Line"), P("circle", "Circle")],
    category=CATEGORY,
)
def intersection_line_circle(line, circle):
    pts = _line_pts(line)
    center = fxy(circle._center) if isinstance(circle, Circle) else None
    r = fnum(circle._radius) if isinstance(circle, Circle) else None
    if pts is None or center is None or r is None:
        return point_array([])
    p1, p2 = pts
    d = np.subtract(p2, p1)
    f = np.subtract(p1, center)
    a = np.dot(d, d)
    if abs(a) < 1e-10:
        return Dummy._new()
    b = np.multiply(2, np.dot(f, d))
    c = np.subtract(np.dot(f, f), np.square(r))
    disc = np.subtract(np.square(b), np.multiply(4, np.multiply(a, c)))
    if disc < -1e-10:
        return Dummy._new()
    if disc < 1e-10:
        ts = [np.divide(np.negative(b), np.multiply(2, a))]
    else:
        sq = np.sqrt(disc)
        ts = [
            np.divide(np.add(np.negative(b), sq), np.multiply(2, a)),
            np.divide(np.subtract(np.negative(b), sq), np.multiply(2, a)),
        ]
    return _points_from_ts(p1, d, ts)


@geomatic_fn(
    keyword="intersection-line-ellipse",
    name="LineEllipseIntersection",
    output="Array",
    params=[P("line", "Line"), P("ellipse", "Ellipse")],
    category=CATEGORY,
)
def intersection_line_ellipse(line, ellipse):
    pts = _line_pts(line)
    if not isinstance(ellipse, Ellipse) or pts is None:
        return point_array([])
    center = fxy(ellipse._center)
    rx, ry = fnum(ellipse._radiusX), fnum(ellipse._radiusY)
    rot = fnum(ellipse._rotation)
    if center is None or rx is None or ry is None or rot is None:
        return point_array([])
    p1, p2 = pts
    theta = np.radians(rot)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    rot_mat = np.array([[cos_t, sin_t], [np.negative(sin_t), cos_t]])
    q1 = rot_mat @ np.subtract(p1, center)
    q2 = rot_mat @ np.subtract(p2, center)
    d = np.subtract(q2, q1)
    ry2, rx2 = np.square(ry), np.square(rx)
    a = np.add(np.multiply(ry2, np.square(d[0])), np.multiply(rx2, np.square(d[1])))
    if abs(a) < 1e-10:
        return Dummy._new()
    b = np.multiply(
        2,
        np.add(np.multiply(ry2, np.multiply(q1[0], d[0])), np.multiply(rx2, np.multiply(q1[1], d[1]))),
    )
    c = np.subtract(
        np.add(np.multiply(ry2, np.square(q1[0])), np.multiply(rx2, np.square(q1[1]))),
        np.multiply(rx2, ry2),
    )
    disc = np.subtract(np.square(b), np.multiply(4, np.multiply(a, c)))
    if disc < -1e-10:
        return Dummy._new()
    if disc < 1e-10:
        ts = [np.divide(np.negative(b), np.multiply(2, a))]
    else:
        sq = np.sqrt(disc)
        ts = [
            np.divide(np.add(np.negative(b), sq), np.multiply(2, a)),
            np.divide(np.subtract(np.negative(b), sq), np.multiply(2, a)),
        ]
    # ts are parameters of the ORIGINAL line (rotation is affine in t)
    return _points_from_ts(p1, np.subtract(p2, p1), ts)


@geomatic_fn(
    keyword="intersection-circle-circle",
    name="CircleCircleIntersection",
    output="Array",
    params=[P("circle1", "Circle"), P("circle2", "Circle")],
    category=CATEGORY,
)
def intersection_circle_circle(circle1, circle2):
    if not (isinstance(circle1, Circle) and isinstance(circle2, Circle)):
        return point_array([])
    c1, c2 = fxy(circle1._center), fxy(circle2._center)
    r1, r2 = fnum(circle1._radius), fnum(circle2._radius)
    if c1 is None or c2 is None or r1 is None or r2 is None:
        return point_array([])
    c1, c2 = np.array(c1), np.array(c2)
    delta = np.subtract(c2, c1)
    dist = np.hypot(*delta)
    if dist > np.add(np.add(r1, r2), 1e-10) or dist < np.subtract(abs(np.subtract(r1, r2)), 1e-10) or dist < 1e-10:
        return Dummy._new()
    a = np.divide(
        np.add(np.subtract(np.square(r1), np.square(r2)), np.square(dist)),
        np.multiply(2, dist),
    )
    m = np.add(c1, np.divide(np.multiply(a, delta), dist))
    if abs(np.subtract(dist, np.add(r1, r2))) < 1e-10 or abs(np.subtract(dist, abs(np.subtract(r1, r2)))) < 1e-10:
        return point_array([Point._new(m[0], m[1])])
    h = np.sqrt(np.subtract(np.square(r1), np.square(a)))
    # perpendicular offset (dy, -dx), matching the TS point ordering
    off = np.divide(np.multiply(h, np.array([delta[1], np.negative(delta[0])])), dist)
    i1 = np.add(m, off)
    i2 = np.subtract(m, off)
    return point_array([Point._new(i1[0], i1[1]), Point._new(i2[0], i2[1])])


@geomatic_fn(
    keyword="intersection-line-bezier-quadratic",
    name="LineBezierQuadraticIntersection",
    output="Array",
    params=[P("line", "Line"), P("bezier", "BezierQuadratic")],
    category=CATEGORY,
)
def intersection_line_bezier_quadratic(line, bezier):
    pts = _line_pts(line)
    if not isinstance(bezier, BezierQuadratic) or pts is None:
        return point_array([])
    b0, b1, b2 = fxy(bezier._p1), fxy(bezier._control), fxy(bezier._p2)
    if b0 is None or b1 is None or b2 is None:
        return point_array([])
    (lx1, ly1), (lx2, ly2) = pts
    b0, b1, b2 = np.array(b0), np.array(b1), np.array(b2)

    # Line as A x + B y + C = 0
    la = np.subtract(ly1, ly2)
    lb = np.subtract(lx2, lx1)
    lc = np.subtract(np.multiply(lx1, ly2), np.multiply(lx2, ly1))

    # Bezier coefficients: P(t) = c2 t^2 + c1 t + c0
    c2 = np.add(np.subtract(b0, np.multiply(2, b1)), b2)
    c1 = np.multiply(2, np.subtract(b1, b0))
    c0 = b0

    qa = np.add(np.multiply(la, c2[0]), np.multiply(lb, c2[1]))
    qb = np.add(np.multiply(la, c1[0]), np.multiply(lb, c1[1]))
    qc = np.add(np.add(np.multiply(la, c0[0]), np.multiply(lb, c0[1])), lc)

    eps = 1e-6
    ts: list[float] = []
    if abs(qa) < eps:
        if abs(qb) > eps:
            t = np.divide(np.negative(qc), qb)
            if -eps <= t <= 1 + eps:
                ts.append(float(np.clip(t, 0, 1)))
    else:
        disc = np.subtract(np.square(qb), np.multiply(4, np.multiply(qa, qc)))
        if disc >= -eps:
            sq = np.sqrt(max(0.0, float(disc)))
            for t in (
                np.divide(np.add(np.negative(qb), sq), np.multiply(2, qa)),
                np.divide(np.subtract(np.negative(qb), sq), np.multiply(2, qa)),
            ):
                if -eps <= t <= 1 + eps:
                    ts.append(float(np.clip(t, 0, 1)))

    if not ts:
        return Dummy._new()

    points = []
    for t in ts:
        mt = np.subtract(1, t)
        pos = np.add(
            np.add(
                np.multiply(np.square(mt), b0),
                np.multiply(np.multiply(2, np.multiply(mt, t)), b1),
            ),
            np.multiply(np.square(t), b2),
        )
        points.append(Point._new(pos[0], pos[1]))
    return point_array(points)
