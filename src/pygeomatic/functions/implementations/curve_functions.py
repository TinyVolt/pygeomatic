"""Mirror of src/lib/geomatic/functions/implementations/curve-functions.ts.

`polynomial` / `evaluate-polynomial` compute numerically; `trail`,
`clear-trail`, `plot` and `plot-inverse` are canvas-bound and record-only.
"""

from __future__ import annotations

import numpy as np

from ...nodes import Dummy, Plot, Polynomial, Scalar
from ...registry import P, geomatic_fn
from ..helpers import fnum

CATEGORY = "Curves & Plotting"


@geomatic_fn(
    keyword="polynomial",
    name="Polynomial",
    output="Polynomial",
    params=[P("a0", "Scalar", variadic=True)],
    category=CATEGORY,
)
def polynomial(coefficients):
    """y = a0 + a1*x + ... + an*x^n; coefficients in ascending-degree order."""
    return Polynomial._new([Scalar._new(fnum(c)) for c in coefficients])


@geomatic_fn(
    keyword="evaluate-polynomial",
    name="EvaluatePolynomial",
    output="Scalar",
    params=[P("polynomial", "Polynomial"), P("x", "Scalar")],
    category=CATEGORY,
)
def evaluate_polynomial(poly, x):
    coeffs = poly.numeric if isinstance(poly, Polynomial) else None
    xv = fnum(x)
    if coeffs is None or xv is None:
        return Scalar._new(None)
    # np.polyval expects descending order; coefficients are ascending
    return Scalar._new(np.polyval(coeffs[::-1], xv))


@geomatic_fn(
    keyword="trail",
    name="Trail",
    output="Trail",
    params=[P("pointId", "Any", variadic=True)],
    category=CATEGORY,
    imperative=True,
)
def trail(point_ids):
    return Dummy._new()


@geomatic_fn(
    keyword="clear-trail",
    name="ClearTrail",
    output="Dummy",
    params=[P("trailId", "Any")],
    category=CATEGORY,
    imperative=True,
)
def clear_trail(trail_id):
    return Dummy._new()


@geomatic_fn(
    keyword="plot",
    name="Plot",
    output="Plot",
    params=[P("x", "Scalar"), P("y", "Scalar")],
    category=CATEGORY,
    is_async=True,
)
def plot_reactive(x, y):
    """Record-only: traces the reactive graph in the engine. `x` and `y` are
    single Scalar nodes in a reactive relationship (`y = f(x)`); the engine
    sweeps `x` and traces the curve. NOT matplotlib: do not pass arrays of
    precomputed samples. Emits `\\plot`."""
    return Plot._new()


@geomatic_fn(
    keyword="plot-inverse",
    name="PlotInverse",
    output="Plot",
    params=[P("x", "Scalar"), P("y", "Scalar")],
    category=CATEGORY,
    is_async=True,
)
def plot_inverse(x, y):
    return Plot._new()
