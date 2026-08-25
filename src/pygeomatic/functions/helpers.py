"""Coercion helpers shared by the function implementations.

Bodies receive the caller's raw arguments (nodes, numbers, or DSL defaults such
as the string 'p0'). These helpers pull numeric payloads out, returning None
when a value is unknown — implementations then produce record-only nodes.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from ..nodes import Array, Bool, Complex, GNode, Point, Scalar, Text


def fnum(x) -> Optional[float]:
    """Numeric value of a Scalar node / number; None when unknown."""
    if x is None or isinstance(x, str):
        return None
    if isinstance(x, bool):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, Scalar):
        return x.numeric
    if isinstance(x, Bool):
        return None if x.numeric is None else float(x.numeric)
    return None


def fint(x) -> Optional[int]:
    v = fnum(x)
    return None if v is None else int(np.floor(v))


def fxy(p) -> Optional[tuple[float, float]]:
    """(x, y) of a Point node; None when unknown or not a point."""
    if isinstance(p, Point):
        return p.numeric
    return None


def fcomplex(z) -> Optional[complex]:
    """Complex value of a Complex/Scalar node or a number; None when unknown."""
    if isinstance(z, Complex):
        return z.numeric
    v = fnum(z)
    return None if v is None else complex(v, 0.0)


def ftext(t) -> Optional[str]:
    if isinstance(t, Text):
        return t.numeric
    if isinstance(t, str):
        return t
    return None


def scalar_array(values: Optional[Sequence[float]], shape=None) -> Array:
    """Array node of Scalar elements from numeric values.

    `values=None` means the VALUES are unknown, which says nothing about the
    shape: pass `shape` whenever the caller knows it (most operations preserve
    their input's shape) so it survives the unknown-value path.
    """
    if values is None:
        return Array._new(
            element_type="Scalar",
            elements=[],
            shape=shape,
            shape_unknown=shape is None,
        )
    els: list[GNode] = [Scalar._new(v) for v in values]
    return Array._new(element_type="Scalar", elements=els, shape=shape or (len(els),))


def point_array(points: Sequence[Point]) -> Array:
    return Array._new(element_type="Point", elements=list(points), shape=(len(points),))


def flat_to_nd(flat_idx: int, shape: Sequence[int]) -> list[int]:
    """Mirror of `flatToNd` (functions/broadcasting.ts:31). Row-major."""
    nd = [0] * len(shape)
    remaining = flat_idx
    for i in range(len(shape) - 1, -1, -1):
        nd[i] = remaining % shape[i]
        remaining //= shape[i]
    return nd


def nd_to_flat_clamped(nd_idx: Sequence[int], input_shape: Sequence[int], rank: int) -> int:
    """Mirror of `ndToFlatClamped` (functions/broadcasting.ts:46).

    Converts an output index into a flat index into `input_shape`, which is
    left-padded with 1s to `rank`. An axis whose input dim is 1 contributes 0 —
    that is the stretching a broadcast does.
    """
    pad = rank - len(input_shape)
    strides = [0] * rank
    stride = 1
    for i in range(rank - 1, -1, -1):
        strides[i] = stride
        stride *= 1 if i < pad else input_shape[i - pad]
    flat = 0
    for i in range(rank):
        dim = 1 if i < pad else input_shape[i - pad]
        flat += (0 if dim == 1 else nd_idx[i]) * strides[i]
    return flat


def broadcast_shapes(shapes: Sequence[Optional[tuple[int, ...]]]) -> Optional[tuple[int, ...]]:
    """Mirror of `broadcastShapes` (functions/broadcasting.ts:11).

    NumPy rules: align right-to-left; each pair of dims must be equal or one of
    them must be 1. Returns None when any input shape is unknown — the result
    shape is then unknowable, which is not the same as a mismatch.
    """
    if any(s is None for s in shapes):
        return None
    known = [tuple(s) for s in shapes if s is not None]
    if not known:
        return None
    rank = max(len(s) for s in known)
    result: list[int] = []
    for i in range(rank):
        out = 1
        for s in known:
            pad = rank - len(s)
            dim = 1 if i < pad else s[i - pad]
            if dim != 1 and out != 1 and dim != out:
                raise ValueError(
                    f"Array broadcast shape mismatch: cannot broadcast "
                    f"dimension {out} with {dim}"
                )
            if dim != 1:
                out = dim
        result.append(out)
    return tuple(result)


def array_values(arr) -> Optional[np.ndarray]:
    """Flat numeric values of an Array of Scalars; None when unknown.

    An array with no elements returns values only when it is GENUINELY empty
    (a known shape holding zero elements). A record-only array has no elements
    because Python has no values for them, not because it has none — returning
    `np.array([])` for it is what let callers compute on a fabricated empty
    array (`sum([]) == 0.0`) instead of taking their unknown-value branch.
    """
    if not isinstance(arr, Array):
        return None
    vals = []
    for el in arr._elements:
        v = fnum(el)
        if v is None:
            return None
        vals.append(v)
    if not vals and arr._length() != 0:
        return None
    return np.array(vals)


def fbool(x) -> Optional[bool]:
    if isinstance(x, Bool):
        return x.numeric
    if isinstance(x, bool):
        return x
    if isinstance(x, str):  # DSL default like 'T'
        return x.upper().startswith("T")
    v = fnum(x)
    return None if v is None else v != 0
