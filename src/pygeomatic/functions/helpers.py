"""Coercion helpers shared by the function implementations.

Bodies receive the caller's raw arguments (nodes, numbers, or DSL defaults such
as the string 'p0'). These helpers pull numeric payloads out, returning None
when a value is unknown — implementations then produce record-only nodes.
"""

from __future__ import annotations

import math
import re
from typing import Callable, Optional, Sequence

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


def mulberry32(seed: float) -> Callable[[], float]:
    """Mirror of utils.ts `mulberry32(seed >>> 0)`: same uniform [0, 1) stream."""
    a = int(seed) & 0xFFFFFFFF if math.isfinite(seed) else 0

    def imul(x: int, y: int) -> int:
        return (x * y) & 0xFFFFFFFF

    def uniform() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = imul(a ^ (a >> 15), 1 | a)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return (t ^ (t >> 14)) / 4294967296

    return uniform


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


def text_box_size(
    text: str, font_size: float = 14, width: float = 0, height: float = 0, unit: float = 50
) -> tuple[float, float]:
    """Mirror of `textBoxLayout` (functions/renderUtils.ts): the outer
    (width, height) of a drawn `\\annotate-text-box`, in canvas units."""
    fs = font_size / unit
    line_height = fs * 1.4

    if width != 0 or height != 0:
        char_w = 0.55 * fs
        max_auto = 5
        bg_pad = 10 / unit

        raw_w = width if width != 0 else -1
        raw_h = height if height != 0 else -1
        w_auto = raw_w <= 0
        h_auto = raw_h <= 0

        def wrap(chars_per_line: int) -> list[str]:
            cpl = max(1, chars_per_line)
            tokens: list[str] = []
            for word in text.split():
                for part in re.split(r"(?<=-)", word):
                    if not part:
                        continue
                    if len(part) <= cpl:
                        tokens.append(part)
                    else:
                        tokens.extend(part[i:i + cpl] for i in range(0, len(part), cpl))
            lines: list[str] = []
            current = ""
            for token in tokens:
                sep = " " if current and not current.endswith("-") else ""
                candidate = current + sep + token
                if len(candidate) <= cpl:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                    current = token
            if current:
                lines.append(current)
            return lines

        def inner_from_outer(outer: float) -> float:
            return max(0.0, outer - 2 * bg_pad)

        inner_w_cap = max_auto - 2 * bg_pad
        inner_h_cap = max_auto - 2 * bg_pad

        if not w_auto:
            inner_w = inner_from_outer(raw_w)
            lines = wrap(math.floor(inner_w / char_w))
        elif not h_auto:
            max_lines = max(1, math.floor(inner_from_outer(raw_h) / line_height))
            cpl = max(1, math.ceil(len(text) / max_lines))
            lines = wrap(cpl)
            while len(lines) > max_lines and cpl < len(text):
                cpl += 1
                lines = wrap(cpl)
            inner_w = max([1, *(len(l) for l in lines)]) * char_w
        else:
            lines = wrap(math.floor(inner_w_cap / char_w))
            inner_w = min(inner_w_cap, max([1, *(len(l) for l in lines)]) * char_w)

        if not h_auto:
            inner_h = inner_from_outer(raw_h)
        elif not w_auto:
            inner_h = len(lines) * line_height
        else:
            max_lines = max(1, math.floor(inner_h_cap / line_height))
            inner_h = min(len(lines), max_lines) * line_height

        outer_w = inner_w + 2 * bg_pad if w_auto else raw_w
        outer_h = inner_h + 2 * bg_pad if h_auto else raw_h
        return outer_w, outer_h

    bg_pad = 4 / unit
    return len(text) * 0.55 * fs + 2 * bg_pad, fs * 1.4 + 2 * bg_pad


def fbool(x) -> Optional[bool]:
    if isinstance(x, Bool):
        return x.numeric
    if isinstance(x, bool):
        return x
    if isinstance(x, str):  # DSL default like 'T'
        return x.upper().startswith("T")
    v = fnum(x)
    return None if v is None else v != 0
