"""Mirror of src/lib/geomatic/functions/implementations/tensor-functions.ts."""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from ...nodes import Array, Point, Scalar
from ...registry import P, geomatic_fn
from ..helpers import array_values, fint, fnum, scalar_array

CATEGORY = "Tensor Functions"


def _nd_values(array: Array) -> Optional[np.ndarray]:
    flat = array_values(array)
    if flat is None:
        return None
    return flat.reshape(array._shape)


def _reduce(keyword: str, name: str, fn: Callable[[np.ndarray, Optional[int]], np.ndarray]):
    """reduce-*: dim=-1 (default) reduces all elements → Scalar; otherwise
    reduces along `dim` → Array (or Scalar for a 1-D input)."""

    @geomatic_fn(
        keyword=keyword,
        name=name,
        output="Any",
        params=[P("array", "Array"), P("dim", "Scalar", default=-1)],
        category=CATEGORY,
    )
    def impl(array, dim):
        vals = _nd_values(array)
        d = fint(dim)
        if vals is None:
            return Scalar._new(None)
        if d is None or d == -1 or vals.ndim <= 1:
            return Scalar._new(fn(vals.ravel(), None))
        if d < 0 or d >= vals.ndim:
            raise ValueError(f"{keyword}: dim {d} out of range for rank-{vals.ndim} array")
        out = fn(vals, d)
        return scalar_array(np.ravel(out), shape=out.shape)

    impl.__name__ = keyword.replace("-", "_")
    return impl


reduce_sum = _reduce("reduce-sum", "ReduceSum", lambda v, d: np.sum(v, axis=d))
reduce_min = _reduce("reduce-min", "ReduceMin", lambda v, d: np.min(v, axis=d))
reduce_max = _reduce("reduce-max", "ReduceMax", lambda v, d: np.max(v, axis=d))
reduce_mean = _reduce("reduce-mean", "ReduceMean", lambda v, d: np.mean(v, axis=d))
# std/var mirror jax defaults (population, ddof=0)
reduce_std = _reduce("reduce-std", "ReduceStd", lambda v, d: np.std(v, axis=d))
reduce_var = _reduce("reduce-var", "ReduceVar", lambda v, d: np.var(v, axis=d))


@geomatic_fn(
    keyword="softmax",
    name="Softmax",
    output="Array",
    params=[P("array", "Array")],
    category=CATEGORY,
)
def softmax(array):
    vals = array_values(array)
    if vals is None:
        return scalar_array(None)
    exps = np.exp(vals)
    return scalar_array(np.divide(exps, np.sum(exps)))


@geomatic_fn(
    keyword="reshape",
    name="Reshape",
    output="Array",
    params=[P("array", "Array"), P("dim", "Scalar", variadic=True)],
    category=CATEGORY,
)
def reshape(array, dims):
    raw = [fint(d) for d in dims]
    if any(d is None for d in raw):
        raise ValueError("reshape: dimensions must be numeric")
    count = len(array._elements)
    shape = np.empty(count).reshape(raw).shape  # numpy validates, incl. one -1
    return Array._new(element_type=array._element_type, elements=list(array._elements), shape=shape)


@geomatic_fn(
    keyword="linspace",
    name="Linspace",
    output="Array",
    params=[
        P("start", "Scalar", default=0),
        P("end", "Scalar", default=1),
        P("n", "Scalar", default=10),
    ],
    category=CATEGORY,
)
def linspace(start, end, n):
    s, e, count = fnum(start), fnum(end), fint(n)
    count = max(1, count if count is not None else 10)
    if s is None or e is None:
        return scalar_array(None)
    return scalar_array(np.linspace(s, e, count))


@geomatic_fn(
    keyword="cumsum",
    name="Cumsum",
    output="Array",
    params=[P("array", "Array")],
    category=CATEGORY,
)
def cumsum(array):
    vals = array_values(array)
    if vals is None:
        return scalar_array(None)
    return scalar_array(np.cumsum(vals), shape=array._shape)


@geomatic_fn(
    keyword="arange",
    name="ARange",
    output="Array",
    params=[
        P("start", "Scalar", default=0),
        P("end", "Scalar", default=5),
        P("step", "Scalar", default=1),
    ],
    category=CATEGORY,
)
def arange(start, end, step):
    s, e, st = fnum(start), fnum(end), fnum(step)
    if s is None or e is None or st is None:
        return scalar_array(None)
    if abs(st) < 1e-10:
        raise ValueError("arange: step must be non-zero")
    return scalar_array(np.arange(s, e, st))


@geomatic_fn(
    keyword="circular-arange",
    name="CircularARange",
    output="Array",
    params=[P("n", "Scalar", default=10), P("r", "Scalar", default=1)],
    category=CATEGORY,
)
def circular_arange(n, r):
    count = max(1, fint(n) or 10)
    radius = fnum(r)
    angles = np.divide(np.multiply(2 * np.pi, np.arange(count)), count)
    pts = [
        Point._new(
            None if radius is None else np.multiply(radius, np.cos(a)),
            None if radius is None else np.multiply(radius, np.sin(a)),
        )
        for a in angles
    ]
    return Array._new(element_type="Point", elements=pts, shape=(count,))


def _filled(keyword: str, name: str, fill: float, like: bool):
    if like:
        params = [P("array", "Array")]
    else:
        params = [P("n", "Scalar", default=1)]

    @geomatic_fn(
        keyword=keyword,
        name=name,
        output="Array",
        params=params,
        category=CATEGORY,
    )
    def impl(arg):
        if like:
            shape = arg._shape if isinstance(arg, Array) else (1,)
        else:
            count = fint(arg)
            if count is None or count < 1:
                raise ValueError(f"{keyword}: n must be a positive integer")
            shape = (count,)
        return scalar_array(np.full(shape, fill).ravel(), shape=shape)

    impl.__name__ = keyword.replace("-", "_")
    return impl


ones = _filled("ones", "Ones", 1.0, like=False)
zeros = _filled("zeros", "Zeros", 0.0, like=False)
ones_like = _filled("ones-like", "OnesLike", 1.0, like=True)
zeros_like = _filled("zeros-like", "ZerosLike", 0.0, like=True)
