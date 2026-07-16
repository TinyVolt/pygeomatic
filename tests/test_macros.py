"""Macros: builtin auto-load, invocation semantics, parse/emit round-trip,
on-the-fly registration, and single-line text guarantees."""

import pytest

import pygeomatic as gm


# --- builtin macros ----------------------------------------------------------


def test_builtin_macros_registered():
    assert "builtin:macros.json" in gm.loaded_macros()
    for kw in ("load-colors", "zero-back-step", "get-uniform-points-on-circle"):
        assert kw in gm.REGISTRY, kw
        assert gm.REGISTRY[kw].is_macro


def test_load_colors_export_stays_palette_helper():
    # gm.load_colors wraps the macro in a ColorPalette return; it carries the
    # macro's FunctionDef for introspection.
    assert gm.load_colors is not gm.REGISTRY["load-colors"].py_func
    assert gm.load_colors.geomatic is gm.REGISTRY["load-colors"]


def test_palette_is_derived_from_the_macro():
    # No hardcoded colors: PALETTE and load_colors read the macro body.
    ids = gm.color_ids()
    assert list(gm.PALETTE) == ids
    with gm.Store() as st:
        pal = gm.load_colors()
        assert set(pal) == set(ids)
        assert pal.BLUE is st.nodes["COLOR-BLUE"]
        assert {cid: n.numeric for cid, n in pal.items()} == gm.PALETTE
        gm.load_colors()  # idempotent: no second \load-colors line
    assert gm.emit(st) == "\\load-colors"


# --- invocation --------------------------------------------------------------


def test_macro_records_one_line_and_registers_body_nodes():
    with gm.Store() as st:
        gm.get_uniform_points_on_circle(6)
        assert "points" in st.nodes and "radians" in st.nodes
    assert gm.emit(st) == "\\get-uniform-points-on-circle 6"


def test_macro_body_uses_engine_auto_ids():
    with gm.Store() as st:
        gm.fermat_point_of_a_triangle()
        # `\point 0 3` / `\point 5 0` inside the body get the ENGINE's undashed
        # ids (p0 is the reserved system origin), and `\triangle p0 p1 p2`
        # resolves against them.
        assert "p1" in st.nodes and "p2" in st.nodes and "p" in st.nodes
    assert gm.emit(st) == "\\fermat-point-of-a-triangle"


def test_macro_with_node_argument():
    with gm.Store() as st:
        loss = gm.scalar(4, out="loss")
        gm.zero_back_step(loss)
    assert gm.emit(st) == "loss = \\scalar 4\n\\zero-back-step loss"


def test_nested_macros_stay_off_the_tape():
    # cardioid's body references p1 (an earlier canvas point) and internally
    # invokes the get-uniform-points-on-circle macro.
    with gm.Store() as st:
        gm.parse_dsl("p1 = \\point 1 0")
        gm.cardioid()
        assert "points" in st.nodes and "radians" in st.nodes
    assert gm.emit(st) == "p1 = \\point 1 0\n\\cardioid"


def test_macro_out_binds_last_body_command():
    gm.load_macros([{"macro": "double x", "commands": ["\\mul x 2"]}], name="t-out")
    try:
        with gm.Store() as st:
            a = gm.scalar(3, out="a")
            d = gm.double(a, out="dbl")
            assert d is st.nodes["dbl"]
            gm.add(d, 1, out="more")
        assert gm.emit(st) == "a = \\scalar 3\ndbl = \\double a\nmore = \\add dbl 1"
    finally:
        gm.unload_macros("t-out")


def test_macro_arg_count_and_conflicts():
    with gm.Store() as st:
        loss = gm.scalar(4, out="loss")
        with pytest.raises(TypeError, match="takes 1 argument"):
            gm.zero_back_step(loss, loss)
        n = gm.scalar(1, out="n")
        with pytest.raises(ValueError, match="conflicts with an internal macro variable"):
            gm.get_uniform_radian_angles(n)  # body assigns `n` itself


# --- parse round-trip --------------------------------------------------------


def test_parse_dsl_with_macros_round_trips():
    dsl = (
        "\\load-colors\n"
        "loss = \\scalar 4\n"
        "\\zero-back-step loss\n"
        "v = \\point 1 2\n"
        "\\set-stroke v COLOR-BLUE\n"
        "\\get-uniform-points-on-circle 6\n"
        "arrs = \\array points"
    )
    with gm.Store() as st:
        nodes = gm.parse_dsl(dsl)
        assert "COLOR-BLUE" in nodes and "points" in nodes
    assert gm.emit(st) == dsl


def test_parse_load_colors_after_palette_helper():
    # palette helper first, then a pasted \load-colors: last-write-wins, no dup error
    with gm.Store() as st:
        gm.load_colors()
        gm.parse_dsl("\\load-colors")
        assert st.nodes["COLOR-BLUE"].numeric == "#6aa8ff"


# --- load/unload -------------------------------------------------------------


def test_load_macros_collisions_and_replace():
    src = [{"macro": "trip x", "commands": ["\\mul x 3"]}]
    gm.load_macros(src, name="t-a")
    try:
        with pytest.raises(gm.MacroError, match="already provided"):
            gm.load_macros(src, name="t-b")
        with pytest.raises(gm.MacroError, match="collides"):
            gm.load_macros([{"macro": "add a b", "commands": ["\\add a b"]}], name="t-c")
        # re-loading the same source replaces
        gm.load_macros([{"macro": "trip x", "commands": ["\\mul x 3.5"]}], name="t-a")
        assert "trip" in gm.REGISTRY
    finally:
        gm.unload_macros("t-a")
    assert "trip" not in gm.REGISTRY and not hasattr(gm, "trip")


def test_load_macros_from_file(tmp_path):
    f = tmp_path / "my-macros.json"
    f.write_text('[{"macro": "half x", "commands": ["\\\\div x 2"]}]')
    assert gm.load_macros(str(f)) == ["half"]
    try:
        with gm.Store() as st:
            gm.half(gm.scalar(8, out="v"), out="h")
        assert gm.emit(st) == "v = \\scalar 8\nh = \\half v"
    finally:
        gm.unload_macros(str(f))


def test_macro_invalid_definitions_rejected():
    with pytest.raises(gm.MacroError, match="empty body"):
        gm.load_macros([{"macro": "nothing", "commands": []}], name="t-bad")
    with pytest.raises(gm.MacroError, match="not a valid geomatic identifier"):
        gm.load_macros([{"macro": "bad_name x", "commands": ["\\mul x 2"]}], name="t-bad")


# --- single-line text --------------------------------------------------------


def test_multiline_text_collapses_to_one_line():
    with gm.Store() as st:
        t = gm.text("breakpoints = creases\n(max switches line)")
        assert t.numeric == "breakpoints = creases (max switches line)"
    assert gm.emit(st) == 't = \\text "breakpoints = creases (max switches line)"'


def test_multiline_implicit_text_collapses():
    with gm.Store() as st:
        p = gm.point(0, 0, out="anchor")
        gm.annotate_text_box("multi\r\n  line\nlabel", p)
    emitted = gm.emit(st)
    assert '"multi line label"' in emitted
    assert all("\n" not in gm.render_command(c) for c in st.commands)
    # and the emitted DSL parses back
    with gm.Store() as st2:
        gm.parse_dsl(emitted)
