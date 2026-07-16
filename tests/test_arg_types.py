"""Argument type checking at the pygeomatic binding boundary.

pygeomatic mirrors the engine's acceptance rule (CommandExecutor.ts +
type-coercion.ts) so a type error surfaces at emission instead of producing DSL
that fails in the browser. These pin the accept/reject decision.
"""

import json

import pytest

import pygeomatic as gm


# --- rejections: what the engine would reject at runtime -------------------


def test_array_of_scalars_rejected_for_point_param():
    with gm.Store():
        with pytest.raises(TypeError, match="expects Point, got a Array<Scalar>"):
            gm.circle(gm.array(1, 2, 3), 2)


def test_numeric_literal_rejected_for_point_param():
    with gm.Store():
        with pytest.raises(TypeError, match="expects Point, cannot use a numeric literal"):
            gm.circle(3, 2)


def test_numeric_literal_rejected_for_bool_param():
    with gm.Store():
        with pytest.raises(TypeError, match="expects Bool, cannot use a numeric literal"):
            gm.int_to_bin(5, 8, 7)  # useTwosComplement is Bool


def test_array_rejected_for_point_variadic():
    with gm.Store():
        with pytest.raises(TypeError, match="expects Point"):
            gm.polygon(gm.array(1, 2), gm.point(0, 0), gm.point(1, 1))


def test_scalar_node_rejected_for_point_param():
    with gm.Store():
        s = gm.scalar(5, out="s")
        with pytest.raises(TypeError, match="expects Point, got a Scalar node"):
            gm.circle(s, 2)


# --- keyword arguments ------------------------------------------------------


def test_keyword_skips_optional_middle_default():
    # The bug this fixes: leaving fontSize at its default while supplying width
    # /height. fontSize must be materialised on the tape (14), not shifted.
    # The Point coerces to its (x, y) scalars, consuming the x AND y slots.
    with gm.Store() as st:
        p = gm.point(0, 0, out="p")
        gm.annotate_text_box("hi", p, width=2, height=2, out="box")
    # tape is positional: text, x, y, fontSize(=14 default), width, height
    assert "box = \\annotate-text-box text-0 p.x p.y 14 2 2" in gm.emit(st)


def test_keyword_by_name_matches_position():
    with gm.Store() as st:
        p = gm.point(0, 0, out="p")
        gm.annotate_text_box("hi", x=p, fontSize=20, out="box")
    # width/height omitted (trailing) stay off the tape
    assert "box = \\annotate-text-box text-0 p.x p.y 20" in gm.emit(st)


def test_keyword_unknown_name_rejected():
    with gm.Store():
        with pytest.raises(TypeError, match="unknown parameter 'nope'"):
            gm.annotate_text_box("hi", nope=1)


def test_keyword_duplicate_position_and_keyword_rejected():
    with gm.Store() as st:
        p = gm.point(0, 0, out="p")
        with pytest.raises(TypeError, match="given by both position and keyword"):
            gm.annotate_text_box("hi", p, 14, fontSize=14)


def test_keyword_coercion_spill_collides_with_keyword():
    # x=p expands into the x AND y slots; also supplying y collides.
    with gm.Store() as st:
        p = gm.point(0, 0, out="p")
        with pytest.raises(TypeError, match="given by both position and keyword"):
            gm.annotate_text_box("hi", x=p, y=3)


def test_keyword_node_default_hole_rejected():
    # circle's center defaults to node id 'p0'; can't materialise it to skip past.
    with gm.Store():
        with pytest.raises(TypeError, match="pass it positionally"):
            gm.circle(radius=3)


# --- acceptances: broadcasting, coercions, Any ------------------------------


def test_broadcast_array_of_scalars_for_scalar_param():
    with gm.Store() as st:
        xs = gm.linspace(0, 1, 3, out="xs")
        gm.point(xs, xs, out="grid")
    assert "grid = \\point xs xs" in gm.emit(st)


def test_property_ref_scalar_accepted():
    with gm.Store() as st:
        p = gm.point(1, 2, out="p")
        gm.mul(p.x, 2, out="d")
    assert "d = \\mul p.x 2" in gm.emit(st)


def test_any_param_takes_any_node():
    with gm.Store():
        gm.reduce_sum(gm.array(1, 2, 3))  # array param is Any-ish; must not raise
        gm.add(gm.complex_(1, 2), gm.complex_(3, 4))  # overload operand Any


def test_numeric_literal_accepted_for_scalar_and_any():
    with gm.Store():
        gm.point(1, 2)  # Scalar params
        gm.reduce_sum(gm.array(1, 2), 0)  # dim is Scalar/Any


def test_node_coercion_on_by_default():
    # Scalar -> Text is an engine coercion: allowed by default, strict only
    # inside allow_coercions(False).
    with gm.Store() as st:
        s = gm.scalar(5, out="s")
        gm.text(s, out="t")
    assert "t = \\text s" in gm.emit(st)
    with gm.Store():
        s = gm.scalar(5, out="s")
        with gm.allow_coercions(False):
            with pytest.raises(TypeError, match="expects Text, got a Scalar node"):
                gm.text(s)


def test_point_coerces_to_two_scalar_args():
    # A Point in a Scalar slot is REPLACED by its (x, y) scalars on the tape,
    # consuming two parameter slots — mirroring CommandExecutor.ts advancing
    # paramIndex by coercedIds.length.
    with gm.Store() as st:
        p = gm.point(1, 2, out="p")
        box = gm.annotate_text_box("hi", p, width=2, height=2, out="box")
    assert "box = \\annotate-text-box text-0 p.x p.y 14 2 2" in gm.emit(st)
    # The numeric body received the coordinates, not the raw Point.
    assert box._position.numeric == (1.0, 2.0)


def test_point_coerces_positionally_with_trailing_args():
    # `\annotate-text-box t p 20` style: args after the Point shift past BOTH
    # coordinate slots.
    with gm.Store() as st:
        p = gm.point(1, 2, out="p")
        gm.annotate_text_box("hi", p, 20, out="box")
    assert "box = \\annotate-text-box text-0 p.x p.y 20" in gm.emit(st)


def test_circle_coerces_to_its_child_nodes():
    # circleToScalar binds to the circle's existing radius node
    # (type-coercion.ts returns node.radius.id).
    with gm.Store() as st:
        c = gm.circle(gm.point(0, 0, out="p"), 2, out="c")
        gm.circle(gm.point(1, 1, out="q"), c, out="c2")  # Circle in the Scalar radius slot
    assert "c2 = \\circle q c.radius" in gm.emit(st)


def test_line_coerces_to_two_point_args():
    # lineToPointsArray: a Line in a Point slot becomes its two endpoints,
    # consuming both Point parameters.
    with gm.Store() as st:
        l = gm.line(gm.point(0, 0, out="a"), gm.point(1, 1, out="b"), out="l")
        gm.line(l, out="l2")
    assert "l2 = \\line l.p1 l.p2" in gm.emit(st)


def test_allow_coercions_default_and_scope():
    assert gm.coercions_enabled() is True
    with gm.allow_coercions(False):
        assert gm.coercions_enabled() is False
    assert gm.coercions_enabled() is True


def test_run_generated_coercions_on_by_default():
    code = "def build(gm):\n    s = gm.scalar(5, out='s')\n    gm.text(s, out='t')\n"
    result = gm.run_generated(code)
    assert result.ok, result.error
    assert result.dsl == ["s = \\scalar 5", "t = \\text s"]


def test_array_of_points_accepted_for_point_param(tmp_path):
    # la-mat-from-point-array declares an Array param; an Array<Point> passes.
    manifest = {
        "name": "t",
        "version": "1",
        "extensions": [
            {
                "id": "m",
                "name": "MatrixFromPointArray",
                "keyword": "la-mat-from-point-array",
                "entry": "x.mjs",
                "parameters": [{"name": "points", "type": "Array"}],
                "outputType": "Array",
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    gm.load_extensions(str(path))
    try:
        with gm.Store() as st:
            pts = gm.polyline(gm.point(0, 0), gm.point(1, 1), out="pts")  # Array<Point>
            gm.la_mat_from_point_array(pts, out="M")
        assert "M = \\la-mat-from-point-array pts" in gm.emit(st)
    finally:
        gm.unload_extensions(str(path))


def test_arrow_to_array_param_gated_by_switch(tmp_path):
    # Arrow -> Array is an engine coercion: allowed by default, strict only
    # inside allow_coercions(False).
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
                ],
                "outputType": "Arrow",
            },
            {
                "id": "s",
                "name": "Sink",
                "keyword": "la-sink",
                "entry": "x.mjs",
                "parameters": [{"name": "a", "type": "Array"}],
                "outputType": "Scalar",
            },
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    gm.load_extensions(str(path))
    try:
        # Default: the coercion is permitted.
        with gm.Store() as st:
            v = gm.la_vec2d(3, 4, out="v")
            gm.la_sink(v, out="out")
        assert "out = \\la-sink v" in gm.emit(st)
        # Strict: Arrow into an Array param rejects.
        with gm.Store():
            v = gm.la_vec2d(3, 4, out="v")
            with gm.allow_coercions(False):
                with pytest.raises(TypeError, match="expects Array, got a Arrow node"):
                    gm.la_sink(v)
    finally:
        gm.unload_extensions(str(path))
