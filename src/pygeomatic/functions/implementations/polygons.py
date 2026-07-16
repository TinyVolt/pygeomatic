"""Mirror of src/lib/geomatic/functions/implementations/polygons.ts."""

from __future__ import annotations

import numpy as np

from ...nodes import Array, Line, Point, Polygon, RegularPolygon, Scalar
from ...registry import P, geomatic_fn
from ..helpers import fint, fnum, fxy

CATEGORY = "Polygons"


@geomatic_fn(
    keyword="polygon-from-side",
    name="RegularPolygonFromSide",
    output="Polygon",
    params=[P("a", "Point"), P("b", "Point"), P("n", "Scalar", default=6)],
    category=CATEGORY,
)
def polygon_from_side(a, b, n):
    """Regular polygon built by successively rotating the previous side by
    π - 2π/n about the current vertex (as in the TS impl; swapping a/b flips it)."""
    num_sides = max(3, fint(n) or 6)
    pa, pb = fxy(a), fxy(b)
    vertices = [a, b]
    if pa is not None and pb is not None:
        coords = [np.array(pa), np.array(pb)]
        rot = np.subtract(np.pi, np.divide(np.multiply(2, np.pi), num_sides))
        cos_t, sin_t = np.cos(rot), np.sin(rot)
        for i in range(2, num_sides):
            prev, cur = coords[i - 2], coords[i - 1]
            d = np.subtract(prev, cur)
            nd = np.array([
                np.subtract(np.multiply(d[0], cos_t), np.multiply(d[1], sin_t)),
                np.add(np.multiply(d[0], sin_t), np.multiply(d[1], cos_t)),
            ])
            nxt = np.add(cur, nd)
            coords.append(nxt)
            vertices.append(Point._new(nxt[0], nxt[1]))
    else:
        vertices.extend(Point._new() for _ in range(num_sides - 2))
    return Polygon._new(vertices)


@geomatic_fn(
    keyword="polygon",
    name="Polygon",
    output="Polygon",
    params=[P("vertex1", "Point"), P("vertex2", "Point"), P("vertex3", "Point", variadic=True)],
    category=CATEGORY,
)
def polygon(vertex1, vertex2, rest):
    return Polygon._new([vertex1, vertex2, *rest])


@geomatic_fn(
    keyword="polyline",
    name="Polyline",
    output="Array",
    params=[P("point1", "Point"), P("point2", "Point", variadic=True)],
    category=CATEGORY,
)
def polyline(point1, rest):
    pts = [point1, *rest]
    lines = [Line._new(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    return Array._new(element_type="Line", elements=lines, shape=(len(lines),))


@geomatic_fn(
    keyword="regular-polygon",
    name="RegularPolygon",
    output="RegularPolygon",
    params=[
        P("center", "Point", default="p0"),
        P("radius", "Scalar", default=2),
        P("numVertices", "Scalar", default=6),
        P("startAngle", "Scalar", default=0),
    ],
    category=CATEGORY,
)
def regular_polygon(center, radius, numVertices, startAngle):
    return RegularPolygon._new(
        center if isinstance(center, Point) else None,
        Scalar._new(fnum(radius)),
        Scalar._new(fnum(numVertices)),
        Scalar._new(fnum(startAngle)),
    )


def _rotated_rect(bottomLeft, w, h, angle_deg):
    bl = fxy(bottomLeft)
    if bl is None or w is None or h is None or angle_deg is None:
        return [
            bottomLeft if isinstance(bottomLeft, Point) else Point._new(),
            Point._new(),
            Point._new(),
            Point._new(),
        ]
    bl = np.array(bl)
    theta = np.radians(angle_deg)
    u = np.array([np.cos(theta), np.sin(theta)])  # along width
    v = np.array([np.negative(np.sin(theta)), np.cos(theta)])  # along height
    br = np.add(bl, np.multiply(w, u))
    tr = np.add(br, np.multiply(h, v))
    tl = np.add(bl, np.multiply(h, v))
    return [
        bottomLeft if isinstance(bottomLeft, Point) else Point._new(bl[0], bl[1]),
        Point._new(br[0], br[1]),
        Point._new(tr[0], tr[1]),
        Point._new(tl[0], tl[1]),
    ]


@geomatic_fn(
    keyword="square",
    name="Square",
    output="Polygon",
    params=[
        P("bottomLeft", "Point", default="p0"),
        P("side", "Scalar", default=2),
        P("angle", "Scalar", default=0),
    ],
    category=CATEGORY,
)
def square(bottomLeft, side, angle):
    s = fnum(side)
    return Polygon._new(_rotated_rect(bottomLeft, s, s, fnum(angle)))


@geomatic_fn(
    keyword="rectangle",
    name="Rectangle",
    output="Polygon",
    params=[
        P("bottomLeft", "Point", default="p0"),
        P("width", "Scalar", default=3),
        P("height", "Scalar", default=2),
        P("angle", "Scalar", default=0),
    ],
    category=CATEGORY,
)
def rectangle(bottomLeft, width, height, angle):
    return Polygon._new(_rotated_rect(bottomLeft, fnum(width), fnum(height), fnum(angle)))


@geomatic_fn(
    keyword="convex-hull",
    name="ConvexHull",
    output="Polygon",
    params=[P("point1", "Point"), P("point2", "Point", variadic=True)],
    category=CATEGORY,
)
def convex_hull(point1, rest):
    """Graham scan, matching the TS implementation (pivot = lowest y, then x;
    collinear points dropped via ccw <= 0)."""
    points = [point1, *rest]
    if len(points) < 3:
        return Polygon._new(points)
    coords = [fxy(p) for p in points]
    if any(c is None for c in coords):
        return Polygon._new(points)

    entries = sorted(zip(coords, points), key=lambda e: (e[0][1], e[0][0]))
    pivot = entries[0]
    px, py = pivot[0]

    def polar_key(entry):
        dx = np.subtract(entry[0][0], px)
        dy = np.subtract(entry[0][1], py)
        return (np.arctan2(dy, dx), np.add(np.square(dx), np.square(dy)))

    rest_sorted = sorted(entries[1:], key=polar_key)

    def ccw(a, b, c):
        return np.subtract(
            np.multiply(np.subtract(b[0][0], a[0][0]), np.subtract(c[0][1], a[0][1])),
            np.multiply(np.subtract(b[0][1], a[0][1]), np.subtract(c[0][0], a[0][0])),
        )

    hull = [pivot]
    for entry in rest_sorted:
        while len(hull) > 1 and ccw(hull[-2], hull[-1], entry) <= 0:
            hull.pop()
        hull.append(entry)
    return Polygon._new([e[1] for e in hull])
