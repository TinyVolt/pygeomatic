"""Mirror of src/lib/geomatic/functions/implementations/boolean-functions.ts."""

from __future__ import annotations

import struct
from typing import Callable

import numpy as np

from ...nodes import Array, Bool, Scalar, Text
from ...registry import P, geomatic_fn
from ..helpers import array_values, fbool, fint, fnum, ftext

CATEGORY = "Boolean & Bitwise"


@geomatic_fn(
    keyword="bool",
    name="Bool",
    output="Bool",
    params=[P("value", "Any")],
    category=CATEGORY,
)
def bool_(value):
    """Truthiness: Scalar non-zero, Text non-empty, Bool pass-through."""
    if isinstance(value, Bool):
        return Bool._new(value.numeric)
    if isinstance(value, Text):
        t = value.numeric
        return Bool._new(None if t is None else len(t) > 0)
    v = fnum(value)
    return Bool._new(None if v is None else v != 0)


def _comparison(keyword: str, name: str, fn: Callable[[float, float], bool]):
    @geomatic_fn(
        keyword=keyword,
        name=name,
        output="Bool",
        params=[P("a", "Scalar"), P("b", "Scalar")],
        category=CATEGORY,
    )
    def impl(a, b):
        va, vb = fnum(a), fnum(b)
        return Bool._new(None if va is None or vb is None else bool(fn(va, vb)))

    impl.__name__ = keyword
    return impl


gt = _comparison("gt", "GreaterThan", np.greater)
ge = _comparison("ge", "GreaterEqual", np.greater_equal)
lt = _comparison("lt", "LessThan", np.less)
le = _comparison("le", "LessEqual", np.less_equal)
eq = _comparison("eq", "Equal", np.equal)


@geomatic_fn(
    keyword="and",
    name="And",
    output="Bool",
    params=[P("values", "Bool", variadic=True)],
    category=CATEGORY,
)
def and_(values):
    vals = [fbool(v) for v in values]
    if any(v is None for v in vals):
        return Bool._new(None)
    return Bool._new(all(vals))


@geomatic_fn(
    keyword="or",
    name="Or",
    output="Bool",
    params=[P("values", "Bool", variadic=True)],
    category=CATEGORY,
)
def or_(values):
    vals = [fbool(v) for v in values]
    if any(v is None for v in vals):
        return Bool._new(None)
    return Bool._new(any(vals))


@geomatic_fn(
    keyword="not",
    name="Not",
    output="Bool",
    params=[P("value", "Bool")],
    category=CATEGORY,
)
def not_(value):
    v = fbool(value)
    return Bool._new(None if v is None else not v)


@geomatic_fn(
    keyword="xor",
    name="Xor",
    output="Bool",
    params=[P("a", "Bool"), P("b", "Bool")],
    category=CATEGORY,
)
def xor(a, b):
    va, vb = fbool(a), fbool(b)
    return Bool._new(None if va is None or vb is None else va != vb)


@geomatic_fn(
    keyword="filter",
    name="Filter",
    output="Array",
    params=[P("array", "Array"), P("mask", "Array")],
    category=CATEGORY,
)
def filter_(array, mask):
    """Filter along the single non-trivial mask axis (NumPy-style broadcast
    alignment, exactly one filtered axis — see the TS docstring)."""
    if not (isinstance(array, Array) and isinstance(mask, Array)):
        raise TypeError("filter: both arguments must be Arrays")
    arr_shape = array._shape
    rank = len(arr_shape)
    mask_shape = mask._shape
    if len(mask_shape) > rank:
        raise ValueError(f"filter: mask rank {len(mask_shape)} exceeds array rank {rank}")
    padded = (1,) * (rank - len(mask_shape)) + tuple(mask_shape)

    filter_axis = -1
    for i in range(rank):
        ad, md = arr_shape[i], padded[i]
        if md == ad and ad > 1:
            if filter_axis != -1:
                raise ValueError("filter: mask has more than one non-trivial axis")
            filter_axis = i
        elif md != 1 and md != ad:
            raise ValueError("filter: mask is not broadcast-compatible with array")

    mask_vals = [fbool(el) for el in mask._elements]
    if any(v is None for v in mask_vals):
        raise ValueError("filter: mask contains unknown Bool values")

    if filter_axis == -1:
        if mask_vals and mask_vals[0]:
            return Array._new(
                element_type=array._element_type,
                elements=list(array._elements),
                shape=arr_shape,
            )
        raise ValueError("filter: scalar false mask would produce an empty array")

    keep = [i for i, v in enumerate(mask_vals[: arr_shape[filter_axis]]) if v]
    if not keep:
        raise ValueError("filter: mask has no true values — empty arrays are not supported")

    idx_grid = np.arange(int(np.prod(arr_shape))).reshape(arr_shape)
    taken = np.take(idx_grid, keep, axis=filter_axis)
    elements = [array._elements[i] for i in taken.ravel()]
    return Array._new(element_type=array._element_type, elements=elements, shape=taken.shape)


def _ieee754_bits(val: float, n_bits: int) -> str:
    if n_bits == 16:
        (raw,) = struct.unpack(">H", struct.pack(">e", np.float16(val)))
        return format(raw, "016b")
    if n_bits == 32:
        (raw,) = struct.unpack(">I", struct.pack(">f", val))
        return format(raw, "032b")
    (raw,) = struct.unpack(">Q", struct.pack(">d", val))
    return format(raw, "064b")


@geomatic_fn(
    keyword="int-to-bin",
    name="IntToBool",
    output="Text",
    params=[
        P("value", "Scalar"),
        P("nBits", "Scalar", default=8),
        P("useTwosComplement", "Bool", default="T"),
    ],
    category=CATEGORY,
)
def int_to_bin(value, nBits, useTwosComplement):
    v = fnum(value)
    n = None if v is None else int(np.trunc(v))  # trunc (not floor), as in TS
    n_bits = fint(nBits) or 8
    twos = fbool(useTwosComplement)
    if n is None or twos is None:
        return Text._new(None)
    if n_bits <= 0:
        raise ValueError(f"int-to-bin: nBits must be a positive integer, got {n_bits}")
    half = 2 ** (n_bits - 1)
    lo = -half if twos else -(half - 1)
    hi = half - 1
    if n < lo or n > hi:
        raise ValueError(
            f"int-to-bin: value {n} does not fit in a signed {n_bits}-bit integer (range {lo}..{hi})"
        )
    if n >= 0:
        unsigned = n
    else:
        unsigned = 2**n_bits + n if twos else 2**n_bits - 1 + n
    return Text._new(format(unsigned, f"0{n_bits}b"))


@geomatic_fn(
    keyword="uint-to-bin",
    name="UIntToBin",
    output="Text",
    params=[P("value", "Scalar"), P("nBits", "Scalar", default=8)],
    category=CATEGORY,
)
def uint_to_bin(value, nBits):
    n = fint(value)
    n_bits = fint(nBits) or 8
    if n is None:
        return Text._new(None)
    if n_bits <= 0:
        raise ValueError(f"uint-to-bin: nBits must be a positive integer, got {n_bits}")
    if n < 0:
        raise ValueError(f"uint-to-bin: value must be a non-negative integer, got {n}")
    if n > 2**n_bits - 1:
        raise ValueError(f"uint-to-bin: value {n} does not fit in {n_bits} bits")
    return Text._new(format(n, f"0{n_bits}b"))


@geomatic_fn(
    keyword="fp-to-bin",
    name="FpToBool",
    output="Text",
    params=[P("value", "Scalar"), P("nBits", "Scalar", default=32)],
    category=CATEGORY,
)
def fp_to_bin(value, nBits):
    v = fnum(value)
    n_bits = fint(nBits) or 32
    if v is None:
        return Text._new(None)
    if n_bits not in (16, 32, 64):
        raise ValueError(f"fp-to-bin: nBits must be 16, 32 or 64 for IEEE 754, got {n_bits}")
    return Text._new(_ieee754_bits(v, n_bits))


def _parse_binary(keyword: str, raw: str) -> tuple[str, int, int]:
    bits = raw.strip()
    if not bits or any(c not in "01" for c in bits):
        raise ValueError(f"{keyword}: binary string must be non-empty 0/1, got {raw!r}")
    return bits, int(bits, 2), len(bits)


@geomatic_fn(
    keyword="bin-to-dec-unsigned",
    name="BinToDecUnsigned",
    output="Scalar",
    params=[P("value", "Text")],
    category=CATEGORY,
)
def bin_to_dec_unsigned(value):
    raw = ftext(value)
    if raw is None:
        return Scalar._new(None)
    _, unsigned, _ = _parse_binary("bin-to-dec-unsigned", raw)
    return Scalar._new(unsigned)


@geomatic_fn(
    keyword="bin-to-dec-twos-complement",
    name="BinToDecTwoComplement",
    output="Scalar",
    params=[P("value", "Text")],
    category=CATEGORY,
)
def bin_to_dec_twos_complement(value):
    raw = ftext(value)
    if raw is None:
        return Scalar._new(None)
    bits, unsigned, n = _parse_binary("bin-to-dec-twos-complement", raw)
    return Scalar._new(unsigned - 2**n if bits[0] == "1" else unsigned)


@geomatic_fn(
    keyword="bin-to-dec-ones-complement",
    name="BinToDecOneComplement",
    output="Scalar",
    params=[P("value", "Text")],
    category=CATEGORY,
)
def bin_to_dec_ones_complement(value):
    raw = ftext(value)
    if raw is None:
        return Scalar._new(None)
    bits, unsigned, n = _parse_binary("bin-to-dec-ones-complement", raw)
    return Scalar._new(unsigned - (2**n - 1) if bits[0] == "1" else unsigned)
