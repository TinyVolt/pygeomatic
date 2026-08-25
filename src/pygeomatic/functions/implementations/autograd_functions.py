"""Mirror of src/lib/geomatic/functions/implementations/autograd-functions.ts.

The autograd/optimization ops mutate node gradients in the engine's store via
JAX; the Python mirror has no reactive graph to differentiate, so all of these
are record-only.
"""

from __future__ import annotations

from ...nodes import Array, Dummy, Point, PointGradient, ScalarGradient, VectorField
from ...registry import P, geomatic_fn

CATEGORY = "Autograd & Optimization"


@geomatic_fn(
    keyword="param",
    name="Param",
    output="Dummy",
    params=[P("id", "Any", variadic=True)],
    category=CATEGORY,
    imperative=True,
)
def param(ids):
    return Dummy._new()


@geomatic_fn(
    keyword="backprop",
    name="Backprop",
    output="Dummy",
    params=[P("id", "Any")],
    category=CATEGORY,
    imperative=True,
)
def backprop(node):
    return Dummy._new()


def _reject_array_target(target, param_node):
    """The target is validated OUTSIDE the broadcast, as the engine arranges it
    (autograd-functions.ts:126-133): jax grad needs a scalar output, so an Array
    target is rejected rather than sliced — which guarantees the broadcast can
    only ever slice the param."""
    if isinstance(target, Array):
        raise TypeError("\\partial: target (first argument) must be a Scalar, got an Array")


@geomatic_fn(
    keyword="partial",
    name="Partial",
    output="Any",
    params=[P("target", "Scalar"), P("param", "Any")],
    category=CATEGORY,
    pre_broadcast=_reject_array_target,
)
def partial_derivative(target, param_node):
    # Computes the partial derivative of `target` w.r.t. `param` (NOT
    # functools.partial). Emits `\partial`.
    #
    # An Array param broadcasts element-wise into an Array of gradient nodes
    # (PointGradient for Point-like elements, ScalarGradient otherwise). That
    # is handled centrally, so this body only ever sees a single param.
    if isinstance(param_node, Point):
        return PointGradient._new(None, None)
    return ScalarGradient._new(None)


@geomatic_fn(
    keyword="gradient-descent-step",
    name="GradientDescent",
    output="Dummy",
    params=[P("id", "Any", variadic=True)],
    category=CATEGORY,
    imperative=True,
)
def gradient_descent_step(ids):
    return Dummy._new()


@geomatic_fn(
    keyword="reevaluate",
    name="Reevaluate",
    output="Dummy",
    params=[P("id", "Any")],
    category=CATEGORY,
    imperative=True,
)
def reevaluate(node):
    return Dummy._new()


@geomatic_fn(
    keyword="minimize",
    name="Minimize",
    output="Dummy",
    params=[P("value", "Any"), P("num-iterations", "Any")],
    category=CATEGORY,
    imperative=True,
)
def minimize(value, num_iterations):
    return Dummy._new()


@geomatic_fn(
    keyword="vector-field",
    name="VectorField",
    output="VectorField",
    params=[P("xId", "Any"), P("yId", "Any")],
    category=CATEGORY,
    imperative=True,
)
def vector_field(x_node, y_node):
    return VectorField._new()


@geomatic_fn(
    keyword="zero-grad",
    name="ZeroGrad",
    output="Dummy",
    params=[],
    category=CATEGORY,
    imperative=True,
)
def zero_grad():
    return Dummy._new()
