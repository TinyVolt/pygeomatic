"""Mirror of src/lib/geomatic/functions/implementations/scalar-functions.ts.

The public unary/binary/variadic scalar keywords are registered here. The
`keyword: ''` sub-implementations (ScalarAdd, ScalarMultiply, ...) that the
overload routers dispatch to live here too, as plain numeric helpers — they are
never registered or recorded directly (the router records the public keyword).
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from ...nodes import Scalar
from ...registry import P, geomatic_fn
from ..helpers import fnum, fxy

CATEGORY = "Scalar Functions"


def _unary(keyword: str, name: str, fn: Callable[[float], float]):
    @geomatic_fn(
        keyword=keyword,
        name=name,
        output="Scalar",
        params=[P("a", "Scalar")],
        category=CATEGORY,
    )
    def impl(a):
        v = fnum(a)
        return Scalar._new(None if v is None else fn(v))

    impl.__name__ = keyword.replace("-", "_")
    return impl


def _binary(keyword: str, name: str, fn: Callable[[float, float], float]):
    @geomatic_fn(
        keyword=keyword,
        name=name,
        output="Scalar",
        params=[P("a", "Scalar"), P("b", "Scalar")],
        category=CATEGORY,
    )
    def impl(a, b):
        va, vb = fnum(a), fnum(b)
        return Scalar._new(None if va is None or vb is None else fn(va, vb))

    impl.__name__ = keyword.replace("-", "_")
    return impl


def _variadic(keyword: str, name: str, fn: Callable[[list[float]], float]):
    @geomatic_fn(
        keyword=keyword,
        name=name,
        output="Scalar",
        params=[P("a", "Scalar"), P("b", "Scalar", variadic=True)],
        category=CATEGORY,
    )
    def impl(a, rest):
        vals = [fnum(a), *(fnum(r) for r in rest)]
        if any(v is None for v in vals):
            return Scalar._new(None)
        return Scalar._new(fn(vals))

    impl.__name__ = keyword.replace("-", "_")
    return impl


sin = _unary("sin", "Sin", np.sin)
cos = _unary("cos", "Cos", np.cos)
tan = _unary("tan", "Tan", np.tan)
asin = _unary("asin", "Asin", np.arcsin)
acos = _unary("acos", "Acos", np.arccos)
atan = _unary("atan", "Atan", np.arctan)
log10 = _unary("log10", "Log10", np.log10)
relu = _unary("relu", "ReLU", lambda a: np.maximum(a, 0.0))
sigmoid = _unary("sigmoid", "Sigmoid", lambda a: np.divide(1.0, np.add(1.0, np.exp(np.negative(a)))))
tanh = _unary("tanh", "Tanh", np.tanh)
floor = _unary("floor", "Floor", np.floor)
ceil = _unary("ceil", "Ceil", np.ceil)
round_ = _unary("round", "Round", np.round)
sign = _unary("sign", "Sign", np.sign)
reciprocal = _unary("reciprocal", "Reciprocal", np.reciprocal)
rad2deg = _unary("rad2deg", "Rad2Deg", np.degrees)
deg2rad = _unary("deg2rad", "Deg2Rad", np.radians)

atan2 = _binary("atan2", "Atan2", np.arctan2)
mod = _binary("mod", "Mod", np.mod)

min_ = _variadic("min", "Min", lambda vals: np.minimum.reduce(vals))
max_ = _variadic("max", "Max", lambda vals: np.maximum.reduce(vals))


@geomatic_fn(
    keyword="x-coord",
    name="XCoord",
    output="Scalar",
    params=[P("point", "Point")],
    category=CATEGORY,
)
def x_coord(pt):
    xy = fxy(pt)
    return Scalar._new(None if xy is None else xy[0])


@geomatic_fn(
    keyword="y-coord",
    name="YCoord",
    output="Scalar",
    params=[P("point", "Point")],
    category=CATEGORY,
)
def y_coord(pt):
    xy = fxy(pt)
    return Scalar._new(None if xy is None else xy[1])


# ---------------------------------------------------------------------------
# keyword:'' sub-implementations, dispatched to by the overload routers
# (functions/overloads/). Pure numeric helpers on already-coerced floats.
# ---------------------------------------------------------------------------


def _lift(fn: Callable, *vals: Optional[float]) -> Optional[float]:
    if any(v is None for v in vals):
        return None
    return fn(*vals)


def scalar_add(vals: list[Optional[float]]) -> Optional[float]:
    return _lift(lambda *v: np.add.reduce(v), *vals)


def scalar_multiply(vals: list[Optional[float]]) -> Optional[float]:
    return _lift(lambda *v: np.multiply.reduce(v), *vals)


def scalar_subtract(a, b):
    return _lift(np.subtract, a, b)


def scalar_divide(a, b):
    return _lift(np.divide, a, b)


def scalar_power(a, b):
    return _lift(np.power, a, b)


def scalar_exp(a):
    return _lift(np.exp, a)


def scalar_log(a):
    return _lift(np.log, a)


def scalar_sqrt(a):
    return _lift(np.sqrt, a)


def scalar_abs(a):
    return _lift(np.abs, a)


def scalar_negate(a):
    return _lift(np.negative, a)
