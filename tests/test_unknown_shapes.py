"""pygeomatic must not decide what it does not know.

When a value or a shape is missing, the right move is to record the command and
hand back a node marked unknown — not to guess a type, invent a number, or
reject a scene the engine would run fine. The one exception is where staying
quiet would silently change the emitted DSL.

Missing values are not extension-specific: `\\partial` returns valueless
gradients and `\\solve-ode` returns a valueless Trajectory, with no manifest in
sight.
"""

import json

import pytest

import pygeomatic as gm
from pygeomatic.nodes import Array, Scalar, Unknown


def load(tmp_path, extensions, name="unknown-ext"):
    manifest = {"name": name, "version": "1.0.0", "extensions": extensions}
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(manifest))
    return str(path)


MAKE_ARRAY = {
    "name": "MakeArray",
    "keyword": "make-array",
    "parameters": [{"name": "n", "type": "Scalar"}],
    "outputType": "Array",
}

# Declares a Scalar output but is called with Arrays — the engine broadcasts and
# returns an Array (ExtensionAdapter.ts:375 → tryBroadcastAsync).
SCALAR_FN = {
    "name": "ScalarFn",
    "keyword": "sc-fn",
    "parameters": [
        {"name": "x", "type": "Scalar"},
        {"name": "mu", "type": "Scalar"},
    ],
    "outputType": "Scalar",
}


@pytest.fixture
def ext(tmp_path):
    src = load(tmp_path, [MAKE_ARRAY, SCALAR_FN])
    gm.load_extensions(src)
    yield
    gm.unload_extensions(src)


# --- an unknown shape is not an empty one ----------------------------------


def test_record_only_array_shape_is_unknown_not_empty(ext):
    with gm.Store():
        arr = gm.make_array(3)
    assert arr._shape is None, "shape (0,) reads as a genuinely empty array"
    assert arr._length() is None
    assert arr.numeric is None


def test_reduce_along_dim_does_not_collapse_to_scalar(ext):
    with gm.Store():
        arr = gm.make_array(3)
        out = gm.reduce_sum(arr, 1)
    # Scalar-vs-Array turns on the rank, which is unknown here.
    assert isinstance(out, Unknown)


def test_reduce_does_not_fabricate_zero(ext):
    with gm.Store():
        arr = gm.make_array(3)
        # dim=-1 is a Scalar whatever the shape, but `sum([])` is not 0.0.
        out = gm.reduce_sum(arr)
    assert isinstance(out, Scalar)
    assert out.numeric is None


def test_unknown_node_satisfies_any_parameter_slot(ext):
    with gm.Store() as s:
        arr = gm.make_array(3)
        out = gm.reduce_sum(arr, 1)
        gm.reduce_sum(out, 0, out="again")  # must not raise on the Unknown
    assert "again = \\reduce-sum out 0" in gm.emit(s)


def test_downstream_of_unknown_records_instead_of_raising(ext):
    with gm.Store() as s:
        arr = gm.make_array(3)
        arr[0]
        arr.length
        arr * 2
        arr + gm.array(1, 2, 3)
        gm.reshape(arr, 3, 1)
    dsl = gm.emit(s)
    for keyword in ("\\get-array-element", "\\mul", "\\add", "\\reshape"):
        assert keyword in dsl


# --- the exception: silence would drop the author's code --------------------


def test_iterating_an_unknown_length_array_raises(ext):
    with gm.Store() as s:
        arr = gm.make_array(3)
        with pytest.raises(TypeError, match="length of array .* is unknown"):
            for el in arr:
                gm.circle(el, 1)
        with pytest.raises(TypeError, match="length of array .* is unknown"):
            len(arr)
    # The loop body emitted nothing; only the extension call is on the tape.
    assert gm.emit(s).splitlines() == ["arr = \\make-array 3"]


def test_negative_index_on_unknown_length_raises(ext):
    with gm.Store():
        arr = gm.make_array(3)
        with pytest.raises(IndexError, match="cannot normalize negative index"):
            arr[-1]


# --- extension outputs broadcast, whatever the manifest declares -------------


def test_scalar_output_over_arrays_is_an_array(ext):
    with gm.Store():
        xs = gm.reshape(gm.linspace(0, 1, 6), 6, 1)
        mus = gm.array(1, 2, 3)
        out = gm.sc_fn(xs, mus)
    assert isinstance(out, Array)
    assert out._shape == (6, 3)


def test_scalar_output_over_scalars_stays_scalar(ext):
    with gm.Store():
        out = gm.sc_fn(gm.scalar(1.0), gm.scalar(2.0))
    assert isinstance(out, Scalar)


def test_reported_chain_types_end_to_end(ext):
    """`sc_fn` over arrays → `*` → `reduce-sum ... 1` used to yield a Scalar."""
    with gm.Store() as s:
        xs = gm.reshape(gm.linspace(0, 1, 6), 6, 1, out="xs")
        mus = gm.array(1, 2, 3, out="mus")
        weights = gm.softmax(gm.array(1, 1, 1, out="logits"), out="weights")
        likes = gm.sc_fn(xs, mus, out="likes")
        w = weights * likes
        ys = gm.reduce_sum(w, 1, out="ys")
    assert w._shape == (6, 3)
    assert isinstance(ys, Array) and ys._shape == (6,)
    assert gm.emit(s).splitlines()[-2:] == [
        "w = \\mul weights likes",
        "ys = \\reduce-sum w 1",
    ]


# --- no extensions involved -------------------------------------------------


def test_gradient_array_keeps_its_known_shape():
    with gm.Store():
        params = gm.array(gm.scalar(1.0), gm.scalar(2.0), gm.scalar(3.0))
        grad = gm.partial_derivative(gm.scalar(0.5), params)
        assert grad.numeric is None  # gradients never carry values in Python
        # Both operations preserve shape; the unknown-value path used to drop it.
        assert gm.cumsum(grad)._shape == (3,)
        assert gm.softmax(grad)._shape == (3,)


def test_constructors_do_not_invent_values_for_an_unknown_count():
    with gm.Store():
        n = gm.partial_derivative(gm.scalar(0.5), gm.scalar(2.0))  # no value
        assert n.numeric is None
        for node in (gm.linspace(0, 1, n), gm.circular_arange(n, 1), gm.ones(n)):
            assert node._shape is None
            assert node.numeric is None


def test_circular_arange_zero_is_not_ten():
    with gm.Store():
        # `fint(n) or 10` turned a real 0 into 10.
        assert gm.circular_arange(0, 1)._shape == (1,)


# --- known values must behave exactly as before -----------------------------


def test_known_reduce_rules_are_unchanged():
    with gm.Store():
        a3 = gm.array(1, 2, 3)
        a23 = gm.reshape(gm.arange(0, 6, 1), 2, 3)
        assert gm.reduce_sum(a3).numeric == 6.0
        # tensor-functions.ts:122-124 — 1-D reduced along its only dim → Scalar.
        assert isinstance(gm.reduce_sum(a3, 0), Scalar)
        assert gm.reduce_sum(a23, 1)._shape == (2,)
        assert gm.reduce_sum(a23, 0)._shape == (3,)
        assert gm.reduce_sum(a23).numeric == 15.0
        with pytest.raises(ValueError, match="dim 5 out of range"):
            gm.reduce_sum(a23, 5)


def test_known_index_checks_are_kept():
    with gm.Store():
        a3 = gm.array(1, 2, 3)
        assert a3[0].numeric == 1.0
        assert a3[-1].numeric == 3.0
        assert len(a3) == 3
        with pytest.raises(IndexError, match="out of range for length 3"):
            a3[9]


def test_infix_broadcasts_like_the_engine():
    """broadcasting.ts:11 — NumPy rules, not "first operand's length"."""
    with gm.Store():
        a3 = gm.array(1, 2, 3)
        a23 = gm.reshape(gm.arange(0, 6, 1), 2, 3)
        col = gm.reshape(gm.array(1, 2), 2, 1)
        assert (a3 * a23)._shape == (2, 3)
        assert (col * a3)._shape == (2, 3)
        # Same-shape operands still compute values.
        assert list((a3 * a3).numeric) == [1.0, 4.0, 9.0]
        assert list((a3 * 2).numeric) == [2.0, 4.0, 6.0]
        with pytest.raises(ValueError, match="broadcast shape mismatch"):
            a3 * gm.array(1, 2)
