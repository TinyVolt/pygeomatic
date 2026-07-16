"""Mirror of src/lib/geomatic/functions/implementations/annotation-functions.ts.

Annotations are declarative (they produce typed nodes with ids); their labels
are Text parameters — pass a Python str and an implicit `\\text "..."` command
is recorded first.
"""

from __future__ import annotations

from ...nodes import (
    AngleMark,
    Arrow,
    CurlyBracket,
    CurvedArrow,
    DimensionLine,
    LeaderLine,
    Pin,
    Point,
    TextBox,
)
from ...registry import P, geomatic_fn
from ..helpers import fnum, ftext

CATEGORY = "Annotations"


@geomatic_fn(
    keyword="annotate-curly-bracket",
    name="CurlyBracket",
    output="CurlyBracket",
    params=[P("p1", "Point"), P("p2", "Point"), P("label", "Text", default="")],
    category=CATEGORY,
)
def annotate_curly_bracket(p1, p2, label):
    return CurlyBracket._new(p1, p2, ftext(label) or "")


@geomatic_fn(
    keyword="annotate-arrow",
    name="Arrow",
    output="Arrow",
    params=[
        P("p1", "Point"),
        P("p2", "Point"),
        P("padding", "Scalar", default=0),
        P("label", "Text", default=""),
    ],
    category=CATEGORY,
)
def annotate_arrow(p1, p2, padding, label):
    return Arrow._new(p1, p2, ftext(label) or "")


@geomatic_fn(
    keyword="annotate-curved-arrow",
    name="CurvedArrow",
    output="CurvedArrow",
    params=[
        P("p1", "Point"),
        P("p2", "Point"),
        P("control", "Point"),
        P("padding", "Scalar", default=0),
        P("label", "Text", default=""),
    ],
    category=CATEGORY,
)
def annotate_curved_arrow(p1, p2, control, padding, label):
    return CurvedArrow._new(p1, p2, control, ftext(label) or "")


@geomatic_fn(
    keyword="annotate-dim-line",
    name="DimensionLine",
    output="DimensionLine",
    params=[P("p1", "Point"), P("p2", "Point"), P("label", "Text", default="")],
    category=CATEGORY,
)
def annotate_dim_line(p1, p2, label):
    return DimensionLine._new(p1, p2, ftext(label) or "")


@geomatic_fn(
    keyword="annotate-angle-mark",
    name="AngleMark",
    output="AngleMark",
    params=[P("line1", "Line"), P("line2", "Line"), P("label", "Text", default="")],
    category=CATEGORY,
)
def annotate_angle_mark(line1, line2, label):
    return AngleMark._new(ftext(label) or "")


@geomatic_fn(
    keyword="annotate-leader-line",
    name="LeaderLine",
    output="LeaderLine",
    params=[P("p1", "Point"), P("p2", "Point"), P("label", "Text")],
    category=CATEGORY,
)
def annotate_leader_line(p1, p2, label):
    return LeaderLine._new(p1, p2, ftext(label) or "")


@geomatic_fn(
    keyword="annotate-pin",
    name="Pin",
    output="Pin",
    params=[P("position", "Point"), P("label", "Text", default="")],
    category=CATEGORY,
)
def annotate_pin(position, label):
    return Pin._new(position, ftext(label) or "")


@geomatic_fn(
    keyword="annotate-text-box",
    name="TextBox",
    output="TextBox",
    params=[
        P("text", "Text"),
        # A Point argument coerces to (x, y) scalars, so existing `... p0` commands still work.
        P("x", "Scalar", default=0),
        P("y", "Scalar", default=0),
        P("fontSize", "Scalar", default=14),
        P("width", "Scalar", default=0),
        P("height", "Scalar", default=0),
    ],
    category=CATEGORY,
)
def annotate_text_box(text, x, y, fontSize, width, height):
    return TextBox._new(
        ftext(text) or "",
        Point._new(fnum(x), fnum(y)),
    )
