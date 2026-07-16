"""Mirror of src/lib/geomatic/functions/implementations/basic-figures.ts."""

from __future__ import annotations

import numpy as np

from ...nodes import (
    Arc,
    BezierCubic,
    BezierQuadratic,
    Circle,
    Ellipse,
    Line,
    Point,
    Scalar,
    Text,
    Triangle,
)
from ...registry import P, geomatic_fn
from ..helpers import fnum, ftext, fxy

CATEGORY = "Basic Figures"


@geomatic_fn(
    keyword="scalar",
    name="Scalar",
    output="Scalar",
    params=[P("value", "Scalar")],
    category=CATEGORY,
)
def scalar(value):
    return Scalar._new(fnum(value))


@geomatic_fn(
    keyword="text",
    name="Text",
    output="Text",
    params=[P("value", "Text")],
    category=CATEGORY,
)
def text(value):
    return Text._new(ftext(value))


@geomatic_fn(
    keyword="point",
    name="Point",
    output="Point",
    params=[P("x", "Scalar", default=0), P("y", "Scalar", default=0)],
    category=CATEGORY,
)
def point(x, y):
    return Point._new(fnum(x), fnum(y))


@geomatic_fn(
    keyword="triangle",
    name="Triangle",
    output="Triangle",
    params=[P("vertex1", "Point"), P("vertex2", "Point"), P("vertex3", "Point")],
    category=CATEGORY,
)
def triangle(vertex1, vertex2, vertex3):
    return Triangle._new([vertex1, vertex2, vertex3])


@geomatic_fn(
    keyword="line",
    name="Line",
    output="Line",
    params=[P("point1", "Point"), P("point2", "Point")],
    category=CATEGORY,
)
def line(point1, point2):
    return Line._new(point1, point2)


@geomatic_fn(
    keyword="circle",
    name="Circle",
    output="Circle",
    params=[P("center", "Point", default="p0"), P("radius", "Scalar", default=2)],
    category=CATEGORY,
)
def circle(center, radius):
    r = fnum(radius)
    return Circle._new(
        center if isinstance(center, Point) else None,
        Scalar._new(r),
    )


@geomatic_fn(
    keyword="ellipse",
    name="Ellipse",
    output="Ellipse",
    params=[
        P("center", "Point", default="p0"),
        P("radiusX", "Scalar", default=3),
        P("radiusY", "Scalar", default=2),
        P("rotation", "Scalar", default=0),
    ],
    category=CATEGORY,
)
def ellipse(center, radiusX, radiusY, rotation):
    return Ellipse._new(
        center if isinstance(center, Point) else None,
        Scalar._new(fnum(radiusX)),
        Scalar._new(fnum(radiusY)),
        Scalar._new(fnum(rotation)),
    )


@geomatic_fn(
    keyword="bezier-quadratic",
    name="BezierQuadratic",
    output="BezierQuadratic",
    params=[P("p1", "Point"), P("control", "Point"), P("p2", "Point")],
    category=CATEGORY,
)
def bezier_quadratic(p1, control, p2):
    return BezierQuadratic._new(p1, control, p2)


@geomatic_fn(
    keyword="bezier-cubic",
    name="BezierCubic",
    output="BezierCubic",
    params=[P("p1", "Point"), P("control1", "Point"), P("control2", "Point"), P("p2", "Point")],
    category=CATEGORY,
)
def bezier_cubic(p1, control1, control2, p2):
    return BezierCubic._new(p1, control1, control2, p2)


@geomatic_fn(
    keyword="arc",
    name="Arc",
    output="Arc",
    params=[
        P("center", "Point", default="p0"),
        P("radius", "Scalar", default=2),
        P("startAngle", "Scalar", default=0),
        P("endAngle", "Scalar", default=90),
    ],
    category=CATEGORY,
)
def arc(center, radius, startAngle, endAngle):
    return Arc._new(
        center if isinstance(center, Point) else None,
        Scalar._new(fnum(radius)),
        Scalar._new(fnum(startAngle)),
        Scalar._new(fnum(endAngle)),
    )


@geomatic_fn(
    keyword="ellipse-from-foci",
    name="EllipseFromFociAndStringLength",
    output="Ellipse",
    params=[P("focus1", "Point"), P("focus2", "Point"), P("stringLength", "Scalar")],
    category=CATEGORY,
)
def ellipse_from_foci(focus1, focus2, stringLength):
    f1, f2, length = fxy(focus1), fxy(focus2), fnum(stringLength)
    if f1 is None or f2 is None or length is None:
        return Ellipse._new()
    dx = np.subtract(f2[0], f1[0])
    dy = np.subtract(f2[1], f1[1])
    focal = np.hypot(dx, dy)
    if length <= focal:
        return Ellipse._new()
    cx = np.divide(np.add(f1[0], f2[0]), 2)
    cy = np.divide(np.add(f1[1], f2[1]), 2)
    c = np.divide(focal, 2)
    a = np.divide(length, 2)
    b = np.sqrt(np.subtract(np.multiply(a, a), np.multiply(c, c)))
    rotation_deg = np.degrees(np.arctan2(dy, dx))
    return Ellipse._new(
        Point._new(cx, cy),
        Scalar._new(a),
        Scalar._new(b),
        Scalar._new(rotation_deg),
    )
