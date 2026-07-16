"""Dynamic extension loading from manifest.json files.

Extensions are pure graph-record: only signature metadata is used, no compute.
Every test unloads what it loaded so the global REGISTRY stays builtins-only
for the parity tests.
"""

import json

import pytest

import pygeomatic as gm
from pygeomatic.extensions import ManifestError


def make_manifest(tmp_path, extensions, name="test-ext", filename="manifest.json"):
    manifest = {"name": name, "version": "1.0.0", "extensions": extensions}
    path = tmp_path / filename
    path.write_text(json.dumps(manifest))
    return str(path)


VEC2D = {
    "id": "vector2d",
    "name": "Vector2D",
    "keyword": "la-vec2d",
    "entry": "linear-algebra.mjs",
    "parameters": [
        {"name": "x", "type": "Scalar"},
        {"name": "y", "type": "Scalar"},
        {"name": "offsetX", "type": "Scalar", "default": 0},
        {"name": "offsetY", "type": "Scalar", "default": 0},
    ],
    "outputType": "Arrow",
}

VEC = {
    "id": "vector",
    "name": "Vector",
    "keyword": "la-vec",
    "entry": "linear-algebra.mjs",
    "parameters": [{"name": "values", "type": "Scalar", "default": 0, "variadic": True}],
    "outputType": "Array",
}


@pytest.fixture(autouse=True)
def unload_all():
    yield
    for source in list(gm.loaded_extensions()):
        gm.unload_extensions(source)


@pytest.fixture()
def manifest(tmp_path):
    return make_manifest(tmp_path, [VEC2D, VEC])


def test_load_registers_functions(manifest):
    keywords = gm.load_extensions(manifest)
    assert keywords == ["la-vec2d", "la-vec"]
    assert "la-vec2d" in gm.REGISTRY
    assert gm.REGISTRY["la-vec2d"].is_async
    assert gm.REGISTRY["la-vec2d"].category == "Extensions"
    assert callable(gm.la_vec2d)
    assert gm.loaded_extensions() == {manifest: ["la-vec2d", "la-vec"]}


def test_emission_and_defaults(manifest):
    gm.load_extensions(manifest)
    with gm.Store() as s:
        gm.la_vec2d(3, 4, out="v")
        gm.la_vec2d(1, 2, 5, 6)
    lines = gm.emit(s).splitlines()
    assert lines[0] == "v = \\la-vec2d 3 4"
    assert lines[1] == "arrow-0 = \\la-vec2d 1 2 5 6"


def test_variadic_emission(manifest):
    gm.load_extensions(manifest)
    with gm.Store() as s:
        gm.la_vec(1, 2, 3, out="w")
    assert gm.emit(s).strip() == "w = \\la-vec 1 2 3"


def test_output_properties_work(manifest):
    gm.load_extensions(manifest)
    with gm.Store() as s:
        v = gm.la_vec2d(3, 4, out="v")
        gm.mid_point(v.p1, v.p2)
    lines = gm.emit(s).splitlines()
    assert lines[-1] == "p-0 = \\mid-point v.p1 v.p2"


def test_required_param_enforced(manifest):
    gm.load_extensions(manifest)
    with gm.Store():
        with pytest.raises(TypeError, match="missing required parameter 'y'"):
            gm.la_vec2d(3)


def test_extensions_appear_in_system_prompt(manifest):
    assert "la-vec2d" not in gm.system_prompt()
    gm.load_extensions(manifest)
    prompt = gm.system_prompt()
    assert "gm.la_vec2d(x, y, offsetX=0, offsetY=0)" in prompt
    assert "### Extensions" in prompt
    gm.unload_extensions(manifest)
    assert "la-vec2d" not in gm.system_prompt()


def test_unload_removes_everything(manifest):
    gm.load_extensions(manifest)
    removed = gm.unload_extensions(manifest)
    assert removed == ["la-vec2d", "la-vec"]
    assert "la-vec2d" not in gm.REGISTRY
    assert not hasattr(gm, "la_vec2d")
    assert gm.loaded_extensions() == {}
    with pytest.raises(KeyError):
        gm.unload_extensions(manifest)


def test_reload_replaces(tmp_path):
    source = make_manifest(tmp_path, [VEC2D])
    gm.load_extensions(source)
    updated = {**VEC2D, "parameters": VEC2D["parameters"][:2], "outputType": "Line"}
    gm.load_extensions(source)  # same content reload is fine
    (tmp_path / "manifest.json").write_text(
        json.dumps({"name": "test-ext", "version": "1.0.1", "extensions": [updated]})
    )
    gm.load_extensions(source)
    assert gm.REGISTRY["la-vec2d"].output_type == "Line"
    assert len(gm.REGISTRY["la-vec2d"].params) == 2


def test_builtin_collision_errors(tmp_path):
    source = make_manifest(tmp_path, [{**VEC2D, "keyword": "point"}])
    with pytest.raises(ManifestError, match="collides with a builtin"):
        gm.load_extensions(source)
    assert gm.loaded_extensions() == {}


def test_cross_source_collision_errors(tmp_path):
    first = make_manifest(tmp_path, [VEC2D], filename="a.json")
    second = make_manifest(tmp_path, [VEC2D], name="other", filename="b.json")
    gm.load_extensions(first)
    with pytest.raises(ManifestError, match="already provided by"):
        gm.load_extensions(second)


def test_bad_manifests_rejected(tmp_path):
    cases = [
        {"name": "x", "version": "1", "extensions": []},
        {"name": "x", "extensions": [VEC2D]},
        {
            "name": "x",
            "version": "1",
            "extensions": [{**VEC2D, "keyword": "has_underscore"}],
        },
        {
            "name": "x",
            "version": "1",
            "extensions": [
                {
                    **VEC2D,
                    "parameters": [
                        {"name": "a", "type": "Scalar", "default": 0},
                        {"name": "b", "type": "Scalar"},
                    ],
                }
            ],
        },
        {
            "name": "x",
            "version": "1",
            "extensions": [
                {
                    **VEC2D,
                    "parameters": [
                        {"name": "a", "type": "Scalar", "variadic": True},
                        {"name": "b", "type": "Scalar"},
                    ],
                }
            ],
        },
    ]
    for i, manifest in enumerate(cases):
        path = tmp_path / f"bad{i}.json"
        path.write_text(json.dumps(manifest))
        with pytest.raises(ManifestError):
            gm.load_extensions(str(path))
    assert gm.loaded_extensions() == {}


def test_null_default_means_required(tmp_path):
    ext = {
        **VEC2D,
        "parameters": [
            {"name": "x", "type": "Scalar", "default": None},
            {"name": "y", "type": "Scalar"},
        ],
    }
    source = make_manifest(tmp_path, [ext])
    gm.load_extensions(source)
    assert not gm.REGISTRY["la-vec2d"].params[0].has_default


def test_custom_output_type_gets_dashed_auto_id(tmp_path):
    ext = {
        "id": "widget",
        "name": "Widget",
        "keyword": "make-widget",
        "entry": "w.mjs",
        "parameters": [{"name": "size", "type": "Scalar"}],
        "outputType": "Widget",
    }
    source = make_manifest(tmp_path, [ext])
    gm.load_extensions(source)
    with gm.Store() as s:
        node = gm.make_widget(5)
        assert node.type == "Widget"
        assert node.numeric is None if hasattr(node, "numeric") else True
    assert gm.emit(s).strip() == "widget-0 = \\make-widget 5"


def test_run_generated_with_extensions(manifest):
    code = "def build(gm):\n    gm.la_vec2d(3, 4, out='v')\n"
    result = gm.run_generated(code, extensions=[manifest])
    assert result.ok, result.error
    assert result.dsl == ["v = \\la-vec2d 3 4"]
    # Without the manifest the function must not exist in the subprocess.
    result = gm.run_generated(code)
    assert not result.ok
    assert "la_vec2d" in (result.error or "")
