"""Broadcasting parity with the engine.

Every declarative TS implementation ends with
`tryBroadcast(inner, inputs) ?? inner(inputs)`, which fires when ANY input is an
Array — whatever the declared parameter type — and returns an Array of the
NumPy-broadcast shape whose element type comes from the first element's result
(functions/broadcasting.ts:83). Five imperative commands use the mutating
variant, `applyImperativeBroadcast` (broadcasting.ts:197).

The exceptions are the operations defined over a whole array: `\\array`,
`\\get-array-element`, `\\fft`, `\\ifft`, `\\filter`, and everything in
tensor-functions.ts.
"""

import json
import re
from pathlib import Path

import pytest

import pygeomatic as gm
from pygeomatic.nodes import Array, Scalar
from pygeomatic.registry import REGISTRY


@pytest.fixture
def store():
    with gm.Store() as s:
        yield s


# --- the reported case ------------------------------------------------------


def test_point_over_an_array_is_an_array_of_points(store):
    x = gm.array(1, 2, 3, out="x")
    p = gm.point(x, x, out="p")
    assert isinstance(p, Array)
    assert p._element_type == "Point"
    assert p._shape == (3,)
    assert p.numeric.tolist() == [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]
    # One command either way — only the Python-side type was ever wrong.
    assert gm.emit(store).splitlines()[-1] == "p = \\point x x"


# --- the broadcast itself ---------------------------------------------------


def test_rank_mixing_stretches_like_numpy(store):
    """(2,1) against (3,) → (2,3), exercising nd_to_flat_clamped."""
    col = gm.reshape(gm.array(10, 20), 2, 1)
    row = gm.array(1, 2, 3)
    out = gm.point(col, row)
    assert out._shape == (2, 3)
    assert out.numeric.tolist() == [
        [[10.0, 1.0], [10.0, 2.0], [10.0, 3.0]],
        [[20.0, 1.0], [20.0, 2.0], [20.0, 3.0]],
    ]


def test_non_array_arguments_are_shared_across_elements(store):
    pts = gm.point(gm.array(1, 2, 3), gm.array(0, 0, 0))
    circles = gm.circle(pts, 2)
    assert circles._element_type == "Circle"
    assert circles._shape == (3,)
    assert [c._radius.numeric for c in circles._elements] == [2.0, 2.0, 2.0]


def test_element_type_comes_from_the_result_not_the_declared_output(store):
    # \gt declares Bool; \sin declares Scalar; \line declares Line.
    assert gm.gt(gm.array(1, 2, 3), 2)._element_type == "Bool"
    assert list(gm.sin(gm.array(0, 0))._element_type) == list("Scalar")
    pts = gm.point(gm.array(1, 2), gm.array(3, 4))
    assert gm.line(pts, pts)._element_type == "Line"


def test_scalar_and_text_broadcast_too(store):
    """basic-figures.ts wraps every function, `\\scalar` and `\\text` included."""
    out = gm.scalar(gm.array(1, 2, 3))
    assert isinstance(out, Array) and out._shape == (3,)
    assert list(out.numeric) == [1.0, 2.0, 3.0]


def test_broadcast_mismatch_raises(store):
    with pytest.raises(ValueError, match="broadcast shape mismatch"):
        gm.point(gm.array(1, 2, 3), gm.array(1, 2))


# --- the exceptions ---------------------------------------------------------


def test_array_takes_an_array_as_an_element(store):
    """array.ts:38 keeps its tryBroadcast commented out."""
    a3 = gm.array(1, 2, 3)
    nested = gm.array(a3, a3)
    assert nested._element_type == "Array"
    assert nested._shape == (2,)


def test_tensor_functions_do_not_broadcast(store):
    a3 = gm.array(1, 2, 3)
    a23 = gm.reshape(gm.arange(0, 6, 1), 2, 3)
    assert gm.reduce_sum(a3).numeric == 6.0
    assert isinstance(gm.reduce_sum(a3, 0), Scalar)
    assert gm.reduce_sum(a23, 1)._shape == (2,)
    assert list(gm.cumsum(a3).numeric) == [1.0, 3.0, 6.0]
    assert gm.softmax(a3)._shape == (3,)


def test_get_array_element_still_indexes(store):
    a3 = gm.array(1, 2, 3)
    assert a3[1].numeric == 2.0


def test_filter_and_fft_do_not_broadcast(store):
    vals = gm.array(1, 2, 3, 4)
    mask = gm.array(gm.bool_(True), gm.bool_(False), gm.bool_(True), gm.bool_(False))
    assert gm.filter_(vals, mask)._shape == (2,)
    assert gm.fft(vals)._shape == (4,)


# --- imperative broadcast ---------------------------------------------------


def test_rotate_mutates_every_element(store):
    pts = gm.point(gm.array(1, 2, 3), gm.array(0, 0, 0))
    out = gm.rotate(pts, gm.point(0, 0), 90)
    assert out is pts  # the mutated object comes back, as for a single node
    assert [[round(v, 6) for v in p] for p in pts.numeric.tolist()] == [
        [0.0, 1.0], [0.0, 2.0], [0.0, 3.0]
    ]


def test_translate_mutates_every_element(store):
    pts = gm.point(gm.array(1, 2), gm.array(0, 0))
    gm.translate(pts, 1, 1)
    assert pts.numeric.tolist() == [[2.0, 1.0], [3.0, 1.0]]


# --- autograd ---------------------------------------------------------------


def test_partial_broadcasts_over_an_array_param(store):
    params = gm.array(gm.scalar(1.0), gm.scalar(2.0), gm.scalar(3.0))
    grad = gm.partial_derivative(gm.scalar(0.5), params)
    assert isinstance(grad, Array)
    assert grad._element_type == "ScalarGradient"
    assert grad._shape == (3,)


def test_partial_rejects_an_array_target(store):
    """Validated OUTSIDE the broadcast, as autograd-functions.ts:126-133 does."""
    params = gm.array(gm.scalar(1.0), gm.scalar(2.0))
    with pytest.raises(TypeError, match="target .* must be a Scalar"):
        gm.partial_derivative(params, gm.scalar(1.0))


# --- unknown shapes still record --------------------------------------------


def test_unknown_shape_records_instead_of_raising(tmp_path):
    manifest = {
        "name": "bc-ext",
        "version": "1.0.0",
        "extensions": [
            {
                "name": "MakeArray",
                "keyword": "bc-make-array",
                "parameters": [{"name": "n", "type": "Scalar"}],
                "outputType": "Array",
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    gm.load_extensions(str(path))
    try:
        with gm.Store() as s:
            arr = gm.bc_make_array(3)
            out = gm.point(arr, arr)
        assert isinstance(out, Array)
        assert out._shape is None  # shape unknown, nothing invented
        assert "\\point" in gm.emit(s)
    finally:
        gm.unload_extensions(str(path))


# --- drift guard ------------------------------------------------------------

TS_ROOT = Path("/Users/sisovina/github/tinyvolt-web/src/lib/geomatic/functions")


# Every builtin that does NOT broadcast. Kept explicit so that adding a command
# forces a deliberate decision rather than silently inheriting the default.
# Declarative exceptions are the operations defined over a whole array; the rest
# are imperative commands with no `applyImperativeBroadcast` in their TS body.
NON_BROADCASTING = {
    # whole-array operations (declarative)
    "array", "get-array-element", "fft", "ifft", "filter",
    "reduce-sum", "reduce-min", "reduce-max", "reduce-mean", "reduce-std",
    "reduce-var", "softmax", "reshape", "linspace", "cumsum", "arange",
    "circular-arange", "ones", "zeros", "ones-like", "zeros-like",
    # imperative, no broadcast in the engine either
    "clear", "highlight", "hide", "show", "copy", "remove", "help",
    "clear-trail", "gradient-descent-step", "param", "backprop",
    "translate-array", "animate",
    "minimize", "reevaluate", "vector-field", "zero-grad",
}


def test_non_broadcasting_keywords_are_exactly_the_documented_set():
    actual = {
        kw
        for kw, fdef in REGISTRY.items()
        if not fdef.broadcasts and not fdef.is_macro and fdef.category != "Extensions"
    }
    assert actual == NON_BROADCASTING


@pytest.mark.skipif(not TS_ROOT.is_dir(), reason="TypeScript source not available")
def test_files_without_the_broadcast_import_have_no_broadcasting_keywords():
    """A TS implementation file that never imports `tryBroadcast` cannot have a
    broadcasting function in it — so every keyword it defines must be flagged
    `broadcasts=False` here. This catches the biggest class of drift (a whole
    file changing policy) without trying to parse TS per function: `\\plot`'s
    broadcast lives in a shared helper, so per-function regexes give false
    answers in both directions.
    """
    checked = 0
    for path in (TS_ROOT / "implementations").glob("*.ts"):
        source = path.read_text()
        imports_broadcast = re.search(
            r"import\s*\{[^}]*(tryBroadcast|applyImperativeBroadcast)[^}]*\}\s*from\s*'\.\./broadcasting'",
            source,
        )
        if imports_broadcast:
            continue
        for keyword in re.findall(r"keyword:\s*'([a-z0-9-]+)'", source):
            fdef = REGISTRY.get(keyword)
            if fdef is None:
                continue
            checked += 1
            assert not fdef.broadcasts, (
                f"\\{keyword} is flagged as broadcasting, but {path.name} never "
                "imports tryBroadcast"
            )
    assert checked, "no non-broadcasting TS files found — parse likely broke"
