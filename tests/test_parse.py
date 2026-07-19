"""parse_dsl: DSL lines → replayed tape (inverse of emit)."""

import json

import pytest

import pygeomatic as gm
from pygeomatic.parse import DslParseError

ROUNDTRIP = """\
center = \\point 0 0
p0 = \\point 3 1
scale = \\scalar 2
angle = \\scalar 60
num0 = \\mul p0.x scale
num1 = \\mul p0.y scale
scaled = \\point num0 num1
\\rotate scaled center angle
scale-then-rotate = \\copy scaled
\\rotate p0 center angle
num2 = \\mul p0.x scale
num3 = \\mul p0.y scale
rotate-then-scale = \\point num2 num3"""


def test_roundtrip_is_identity():
    with gm.Store() as s:
        gm.parse_dsl(ROUNDTRIP)
    assert gm.emit(s) == ROUNDTRIP


def test_returns_live_node_map_for_modification():
    with gm.Store() as s:
        nodes = gm.parse_dsl("a = \\point 1 2\nb = \\point 4 6")
        gm.mid_point(nodes["a"], nodes["b"], out="mid")
    assert gm.emit(s).splitlines()[-1] == "mid = \\mid-point a b"


def test_text_quoted_and_defaults():
    src = 't = \\text "hello world = ${a}"\narr-x = \\linspace 0 1'
    with gm.Store() as s:
        gm.parse_dsl(src)
    assert gm.emit(s) == src


def test_numbers_parse_positionally():
    src = "a = \\point -3 2.5\nb = \\scalar 0.125"
    with gm.Store() as s:
        gm.parse_dsl(src)
    assert gm.emit(s) == src


def test_property_chain_whitelist():
    with gm.Store():
        gm.parse_dsl("c = \\circle\nx = \\x-coord c.center")
        with pytest.raises(DslParseError, match="has no property 'radius'"):
            gm.parse_dsl("bad = \\x-coord c.center.radius")


def test_define_before_use():
    # Point/Scalar/Text ids auto-create (see test_auto_create.py); any other
    # parameter type still enforces define-before-use.
    with gm.Store():
        with pytest.raises(DslParseError, match="'ghost' does not exist"):
            gm.parse_dsl("\\highlight ghost")


def test_unknown_command():
    with gm.Store():
        with pytest.raises(DslParseError, match="unknown command"):
            gm.parse_dsl("\\no-such-thing 1 2")


def test_imperative_cannot_assign():
    with gm.Store():
        with pytest.raises(DslParseError, match="imperative and cannot be assigned"):
            gm.parse_dsl("a = \\point 1 2\nh = \\highlight a")


def test_arity_errors_carry_line_info():
    with gm.Store():
        with pytest.raises(DslParseError, match="line 1.*missing required parameter"):
            gm.parse_dsl("l = \\line")


def test_engine_shaped_ids_accepted_but_authored_ids_stay_strict():
    with gm.Store() as s:
        gm.parse_dsl("num0 = \\scalar 5")
        assert "num0" in s.nodes
        with pytest.raises(ValueError, match="unsafe geomatic identifier"):
            gm.scalar(1, out="num7")


def test_bare_assignment_gets_auto_id():
    with gm.Store() as s:
        gm.parse_dsl("\\point 1 2")
    assert gm.emit(s) == "p-0 = \\point 1 2"


def test_quoted_string_outside_text_rejected():
    with gm.Store():
        with pytest.raises(DslParseError, match="only valid as the argument"):
            gm.parse_dsl('a = \\scalar "5"')


def test_parse_permits_coercions_even_under_strict_authoring():
    # `\text s` where s is a Scalar is a coercion the engine allows; parse_dsl
    # replays engine-valid DSL so it accepts it even inside allow_coercions(False).
    src = "s = \\scalar 5\nt = \\text s"
    with gm.Store() as store:
        with gm.allow_coercions(False):
            gm.parse_dsl(src)
    assert gm.emit(store) == src


def test_parse_extension_commands(tmp_path):
    manifest = {
        "name": "t",
        "version": "1",
        "extensions": [
            {
                "id": "v",
                "name": "Vector2D",
                "keyword": "la-vec2d",
                "entry": "x.mjs",
                "parameters": [
                    {"name": "x", "type": "Scalar"},
                    {"name": "y", "type": "Scalar"},
                    {"name": "offsetX", "type": "Scalar", "default": 0},
                    {"name": "offsetY", "type": "Scalar", "default": 0},
                ],
                "outputType": "Arrow",
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))

    src = "v = \\la-vec2d 3 4\nm = \\mid-point v.p1 v.p2"
    with gm.Store():
        with pytest.raises(DslParseError, match="load_extensions"):
            gm.parse_dsl(src)

    gm.load_extensions(str(path))
    try:
        with gm.Store() as s:
            gm.parse_dsl(src)
        assert gm.emit(s) == src
    finally:
        gm.unload_extensions(str(path))
