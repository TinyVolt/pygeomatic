"""Mirror of src/lib/geomatic/functions/implementations/array.ts."""

from __future__ import annotations

from ...nodes import NODE_CLASSES, Array, GNode, Scalar, Unknown
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
    if not isinstance(arr, Array):
        return Unknown._new()
    if i is None:
        # A valueless index (a slider, say). Which element is unknown, but the
        # element TYPE need not be.
        return _empty_element(arr._element_type)
    n = arr._length()
    if n is None:
        # Length unknown: the index cannot be range-checked, and the element
        # type may be unknown too. Record the command and let the engine index.
        return _empty_element(arr._element_type)
    if i < 0 or i >= n:
        raise IndexError(f"get-array-element: index {i} out of range for length {n}")
    if i >= len(arr._elements):
        # The shape says this element exists; Python just has no value for it.
        return _empty_element(arr._element_type)
    # The DSL assigns the element to a NEW node id — clone so the output node
    # gets its own identity without re-referencing the source element.
    return arr._elements[i].model_copy()


def _empty_element(element_type) -> GNode:
    """A valueless node of `element_type`, or Unknown when even that is unknown."""
    cls = NODE_CLASSES.get(element_type) if element_type else None
    return cls._new() if cls is not None else Unknown._new()  # type: ignore[attr-defined]
