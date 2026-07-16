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
    """Array node of Scalar elements from numeric values (None → unknown array)."""
    if values is None:
        return Array._new(element_type="Scalar", elements=[], shape=shape or (0,))
    els: list[GNode] = [Scalar._new(v) for v in values]
    return Array._new(element_type="Scalar", elements=els, shape=shape or (len(els),))


def point_array(points: Sequence[Point]) -> Array:
    return Array._new(element_type="Point", elements=list(points), shape=(len(points),))


def array_values(arr) -> Optional[np.ndarray]:
    """Flat numeric values of an Array of Scalars; None when unknown."""
    if not isinstance(arr, Array):
        return None
    vals = []
    for el in arr._elements:
        v = fnum(el)
        if v is None:
            return None
        vals.append(v)
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
