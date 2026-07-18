"""Mirror of src/lib/geomatic/functions/implementations/complex-functions.ts."""

from __future__ import annotations

from typing import Optional

import numpy as np

from ...nodes import Array, Complex, Scalar
from ...registry import P, geomatic_fn
from ..helpers import fcomplex, fnum

CATEGORY = "Complex Functions"


@geomatic_fn(
    keyword="complex",
    name="Complex",
    output="Complex",
    params=[P("re", "Scalar"), P("im", "Scalar")],
    category=CATEGORY,
)
def complex_(re, im):
    return Complex._new(fnum(re), fnum(im))


@geomatic_fn(
    keyword="real",
    name="Real",
    output="Scalar",
    params=[P("z", "Complex")],
    category=CATEGORY,
)
def real(z):
    v = fcomplex(z)
    return Scalar._new(None if v is None else np.real(v))


@geomatic_fn(
    keyword="imag",
    name="Imag",
    output="Scalar",
    params=[P("z", "Complex")],
    category=CATEGORY,
)
def imag(z):
    v = fcomplex(z)
    return Scalar._new(None if v is None else np.imag(v))


@geomatic_fn(
    keyword="conj",
    name="Conjugate",
    output="Complex",
    params=[P("z", "Complex")],
    category=CATEGORY,
)
def conj(z):
    v = fcomplex(z)
    if v is None:
        return Complex._new()
    c = np.conj(v)
    return Complex._new(np.real(c), np.imag(c))


@geomatic_fn(
    keyword="arg",
    name="Arg",
    output="Scalar",
    params=[P("z", "Complex")],
    category=CATEGORY,
)
def arg(z):
    v = fcomplex(z)
    return Scalar._new(None if v is None else np.angle(v))


def _complex_values(array: Array) -> Optional[np.ndarray]:
    """Element values of an Array of Complex (or Scalar) nodes; None if unknown."""
    if not isinstance(array, Array):
        return None
    vals = []
    for el in array._elements:
        v = fcomplex(el)
        if v is None:
            return None
        vals.append(v)
    return np.array(vals, dtype=np.complex128)


def _complex_array(values: np.ndarray) -> Array:
    els = [Complex._new(np.real(v), np.imag(v)) for v in values]
    return Array._new(element_type="Complex", elements=els, shape=(len(els),))


@geomatic_fn(
    keyword="fft",
    name="Fft",
    output="Array",
    params=[P("array", "Array")],
    category=CATEGORY,
)
def fft(array):
    vals = _complex_values(array)
    if vals is None:
        return Array._new(element_type="Complex", elements=[])
    return _complex_array(np.fft.fft(vals))


@geomatic_fn(
    keyword="ifft",
    name="InverseFFT",
    output="Array",
    params=[P("array", "Array")],
    category=CATEGORY,
)
def ifft(array):
    vals = _complex_values(array)
    if vals is None:
        return Array._new(element_type="Complex", elements=[])
    return _complex_array(np.fft.ifft(vals))


# ---------------------------------------------------------------------------
# keyword:'' sub-implementations for the overload routers. Numeric helpers on
# python complex values.
# ---------------------------------------------------------------------------


def _lift(fn, *vals):
    if any(v is None for v in vals):
        return None
    return fn(*vals)


def complex_add(vals):
    return _lift(lambda *v: np.add.reduce(v), *vals)


def complex_multiply(vals):
    return _lift(lambda *v: np.multiply.reduce(v), *vals)


def complex_subtract(a, b):
    return _lift(np.subtract, a, b)


def complex_divide(a, b):
    return _lift(np.divide, a, b)


def complex_power(a, b):
    return _lift(np.power, a, b)


def complex_negate(a):
    return _lift(np.negative, a)


def complex_exp(a):
    return _lift(np.exp, a)


def complex_log(a):
    return _lift(np.log, a)


def complex_sqrt(a):
    return _lift(np.sqrt, a)


def complex_abs(a):
    """|z| — the one Complex overload whose output is a Scalar."""
    return _lift(np.abs, a)
