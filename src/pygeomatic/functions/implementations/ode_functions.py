"""Mirror of src/lib/geomatic/functions/implementations/ode-functions.ts.

The engine solves ODEs by re-evaluating the reactive expression graph rooted
at the `dydt` / drift / diffusion nodes. The Python mirror records only values,
not re-evaluable graphs, so `solve-ode`, `flow` and `simulate-sde` are
record-only (Trajectory with unknown samples). `eval-ode` samples a trajectory
when its points are known.
"""

from __future__ import annotations

import numpy as np

from ...nodes import Point, Trajectory
from ...registry import P, geomatic_fn
from ..helpers import fnum

CATEGORY = "ODEs"


@geomatic_fn(
    keyword="solve-ode",
    name="SolveODE",
    output="Trajectory",
    params=[
        P("t", "Scalar"),
        P("y", "Scalar"),
        P("dydt", "Any"),
        P("y0", "Scalar"),
        P("t1", "Scalar"),
        P("steps", "Scalar", default=200),
    ],
    category=CATEGORY,
)
def solve_ode(t, y, dydt, y0, t1, steps):
    return Trajectory._new(None)


@geomatic_fn(
    keyword="eval-ode",
    name="EvalODE",
    output="Point",
    params=[P("trajectory", "Trajectory"), P("t", "Scalar")],
    category=CATEGORY,
)
def eval_ode(trajectory, t):
    tv = fnum(t)
    pts = trajectory._points if isinstance(trajectory, Trajectory) else None
    if pts is None or tv is None or not pts:
        return Point._new()
    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    return Point._new(tv, np.interp(tv, xs, ys))


@geomatic_fn(
    keyword="flow",
    name="Flow",
    output="Trajectory",
    params=[
        P("point", "Point"),
        P("out", "Any"),
        P("p0", "Point"),
        P("t1", "Scalar"),
        P("steps", "Scalar", default=200),
    ],
    category=CATEGORY,
)
def flow(point, out_node, p0, t1, steps):
    return Trajectory._new(None)


@geomatic_fn(
    keyword="simulate-sde",
    name="SimulateSDE",
    output="Trajectory",
    params=[
        P("t", "Scalar"),
        P("x", "Scalar"),
        P("drift", "Any"),
        P("diffusion", "Any"),
        P("x0", "Scalar"),
        P("t1", "Scalar"),
        P("steps", "Scalar", default=200),
        P("seed", "Scalar", default=-1),
    ],
    category=CATEGORY,
)
def simulate_sde(t, x, drift, diffusion, x0, t1, steps, seed):
    return Trajectory._new(None)
