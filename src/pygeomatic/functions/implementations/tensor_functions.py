"""Mirror of src/lib/geomatic/functions/implementations/tensor-functions.ts."""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from ...nodes import Array, Point, Scalar, Unknown
from ...registry import P, geomatic_fn
from ..helpers import array_values, fint, fnum, scalar_array

CATEGORY = "Tensor Functions"


def _nd_values(array: Array) -> Optional[np.ndarray]:
    flat = array_values(array)
    if flat is None or array._shape is None:
        return None
    return flat.reshape(array._shape)


def _reduce(keyword: str, name: str, fn: Callable[[np.ndarray, Optional[int]], np.ndarray]):
    """reduce-*: dim=-1 (default) reduces all elements → Scalar; otherwise
    reduces along `dim` → Array (or Scalar for a 1-D input).

    The output TYPE is decided from the input's shape and `dim` alone, never
    from its values — mirroring tensor-functions.ts:118-127, which builds an
    Array only when `outShape.length > 0` and otherwise falls through to a
    Scalar. Values are computed separately, and only when they are available.
    """

    @geomatic_fn(
        keyword=keyword,
        name=name,
        output="Any",
        params=[P("array", "Array"), P("dim", "Scalar", default=-1)],
        category=CATEGORY,
    )
    def impl(array, dim):
        d = fint(dim)
        shape = array._shape if isinstance(array, Array) else None
        vals = _nd_values(array)

        # `dim` came from a node with no value: it could be -1 (Scalar out) or a
        # real axis (Array out). Both the shape and the type are undecidable.
        if d is None:
            return Unknown._new()

        if d != -1:
            if shape is None:
                # Scalar-vs-Array turns on the rank, which we do not have.
                return Unknown._new()
            rank = len(shape)
            if d < 0 or d >= rank:
                raise ValueError(f"{keyword}: dim {d} out of range for rank-{rank} array")
            out_shape = shape[:d] + shape[d + 1 :]
            if out_shape:
                if vals is None:
                    return scalar_array(None, shape=out_shape)
                out = fn(vals, d)
                return scalar_array(np.ravel(out), shape=out.shape)
            # 1-D array reduced along its only dim → Scalar (as in the engine).

        return Scalar._new(None if vals is None else fn(vals.ravel(), None))

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
    shape = array._shape if isinstance(array, Array) else None
    if vals is None:
        return scalar_array(None, shape=shape)  # softmax preserves shape
    exps = np.exp(vals)
    return scalar_array(np.divide(exps, np.sum(exps)), shape=shape)


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
        # A dim from a valueless node: the target shape is genuinely unknown.
        return Array._new(element_type=array._element_type, elements=[], shape_unknown=True)
    count = array._length()
    if count is None:
        # Element count unknown, so numpy cannot validate the dims (and a `-1`
        # cannot be resolved). Take the author's dims when they are concrete.
        shape = tuple(raw) if -1 not in raw else None
        return Array._new(
            element_type=array._element_type,
            elements=[],
            shape=shape,
            shape_unknown=shape is None,
        )
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
    if count is None:
        # `n` is a node with no value. Substituting the default 10 here emitted
        # ten real numbers with nothing marking them as invented; the length is
        # simply unknown, which makes the shape unknown too.
        return scalar_array(None)
    count = max(1, count)
    if s is None or e is None:
        return scalar_array(None, shape=(count,))  # length known, values not
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
    shape = array._shape if isinstance(array, Array) else None
    if vals is None:
        return scalar_array(None, shape=shape)  # cumsum preserves shape
    return scalar_array(np.cumsum(vals), shape=shape)


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
    count = fint(n)
    if count is None:
        # Unknown `n`: `or 10` invented ten points (and turned a real n=0 into
        # ten). Without the count there is no shape and no element list.
        return Array._new(element_type="Point", elements=[], shape_unknown=True)
    count = max(1, count)
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
            if count is None:
                # `n` is a valueless node — not a bad `n`. The engine will read
                # its real value; refusing here would reject a valid scene.
                return scalar_array(None)
            if count < 1:
                raise ValueError(f"{keyword}: n must be a positive integer")
            shape = (count,)
        if shape is None:
            return scalar_array(None)
        # Every element is `fill`, so a known shape is enough to know the values.
        return scalar_array(np.full(shape, fill).ravel(), shape=shape)

    impl.__name__ = keyword.replace("-", "_")
    return impl


ones = _filled("ones", "Ones", 1.0, like=False)
zeros = _filled("zeros", "Zeros", 0.0, like=False)
ones_like = _filled("ones-like", "OnesLike", 1.0, like=True)
zeros_like = _filled("zeros-like", "ZerosLike", 0.0, like=True)
