"""Mirror of src/lib/geomatic/functions/implementations/tangent-functions.ts.

`\\tangent` samples the engine's rendered curve — record-only here.
"""

from __future__ import annotations

from ...nodes import Line
from ...registry import P, geomatic_fn

CATEGORY = "Tangents"


@geomatic_fn(
    keyword="tangent",
    name="Tangent",
    output="Line",
    params=[P("curve", "Any"), P("x", "Scalar"), P("length", "Scalar", default=2)],
    category=CATEGORY,
    is_async=True,
)
def tangent(curve, x, length):
    return Line._new()
