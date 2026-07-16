"""Mirror of src/lib/geomatic/functions/implementations/array.ts."""

from __future__ import annotations

from ...nodes import Array, GNode, Scalar
from ...registry import P, geomatic_fn
from ..helpers import fint, fnum

CATEGORY = "Arrays"


@geomatic_fn(
    keyword="array",
    name="Array",
    output="Array",
    params=[P("element1", "Any", variadic=True)],
    category=CATEGORY,
)
def array(elements):
    els: list[GNode] = []
    for e in elements:
        els.append(e if isinstance(e, GNode) else Scalar._new(fnum(e)))
    element_type = els[0].type if els else "Scalar"
    return Array._new(element_type=element_type, elements=els, shape=(len(els),))


@geomatic_fn(
    keyword="get-array-element",
    name="GetArrayElement",
    output="Any",
    params=[P("array", "Array"), P("index", "Scalar")],
    category=CATEGORY,
)
def get_array_element(arr, index):
    i = fint(index)
    if not isinstance(arr, Array) or i is None:
        return Scalar._new(None)
    if i < 0 or i >= len(arr._elements):
        raise IndexError(f"get-array-element: index {i} out of range for length {len(arr._elements)}")
    # The DSL assigns the element to a NEW node id — clone so the output node
    # gets its own identity without re-referencing the source element.
    return arr._elements[i].model_copy()
