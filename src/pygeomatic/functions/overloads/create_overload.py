"""Mirror of src/lib/geomatic/functions/overloads/createOverload.ts.

The ten public operators (`add`, `sub`, `mul`, ...) dispatch on input types:
any Complex operand routes to the complex kernel (scalars are promoted to
re + 0i), otherwise the scalar kernel runs. Array operands dispatch on their
element type and broadcast elementwise against scalar operands, mirroring the
engine's broadcasting. The tape always records the public keyword.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from ...nodes import Array, Complex, GNode, Scalar
from ...registry import P, geomatic_fn
from ..helpers import fcomplex, fnum

CATEGORY = "Overloaded Functions"
OPERAND_TYPES = ["Scalar", "Complex"]


def _is_complex(value) -> bool:
    if isinstance(value, Complex):
        return True
    if isinstance(value, Array):
        return value._element_type == "Complex"
    return False


def _apply_flat(
    scalar_fn: Callable,
    complex_fn: Callable,
    complex_out: str,
    values: Sequence,
) -> GNode:
    """Apply to non-Array operands (nodes or numbers)."""
    if any(_is_complex(v) for v in values):
        result = complex_fn([fcomplex(v) for v in values])
        if complex_out == "Scalar":
            return Scalar._new(None if result is None else float(result.real if isinstance(result, complex) else result))
        if result is None:
            return Complex._new()
        c = complex(result)
        return Complex._new(c.real, c.imag)
    result = scalar_fn([fnum(v) for v in values])
    return Scalar._new(result)


def _elements_or_self(v, n: int) -> list:
    if isinstance(v, Array):
        if len(v._elements) != n:
            raise ValueError(
                f"operand arrays must have matching lengths ({len(v._elements)} vs {n})"
            )
        return list(v._elements)
    return [v] * n


def apply_overload(
    scalar_fn: Callable,
    complex_fn: Callable,
    complex_out: str,
    values: Sequence,
) -> GNode:
    arrays = [v for v in values if isinstance(v, Array)]
    if not arrays:
        return _apply_flat(scalar_fn, complex_fn, complex_out, values)
    n = len(arrays[0]._elements)
    columns = [_elements_or_self(v, n) for v in values]
    elements = [
        _apply_flat(scalar_fn, complex_fn, complex_out, [col[i] for col in columns])
        for i in range(n)
    ]
    element_type = elements[0].type if elements else "Scalar"
    return Array._new(element_type=element_type, elements=elements, shape=arrays[0]._shape)


def unary_overload(
    keyword: str,
    name: str,
    scalar_fn: Callable,
    complex_fn: Callable,
    complex_out: str = "Complex",
):
    @geomatic_fn(
        keyword=keyword,
        name=name,
        output="Any",
        params=[P("a", "Any")],
        category=CATEGORY,
        operand_types=OPERAND_TYPES,
    )
    def impl(a):
        return apply_overload(lambda v: scalar_fn(v[0]), lambda v: complex_fn(v[0]), complex_out, [a])

    impl.__name__ = keyword
    return impl


def binary_overload(keyword: str, name: str, scalar_fn: Callable, complex_fn: Callable):
    @geomatic_fn(
        keyword=keyword,
        name=name,
        output="Any",
        params=[P("a", "Any"), P("b", "Any")],
        category=CATEGORY,
        operand_types=OPERAND_TYPES,
    )
    def impl(a, b):
        return apply_overload(
            lambda v: scalar_fn(v[0], v[1]),
            lambda v: complex_fn(v[0], v[1]),
            "Complex",
            [a, b],
        )

    impl.__name__ = keyword
    return impl


def variadic_overload(keyword: str, name: str, scalar_fn: Callable, complex_fn: Callable):
    @geomatic_fn(
        keyword=keyword,
        name=name,
        output="Any",
        params=[P("a", "Any"), P("b", "Any", variadic=True)],
        category=CATEGORY,
        operand_types=OPERAND_TYPES,
    )
    def impl(a, rest):
        return apply_overload(scalar_fn, complex_fn, "Complex", [a, *rest])

    impl.__name__ = keyword
    return impl
