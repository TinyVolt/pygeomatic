"""Auto-creation of missing Point/Scalar/Text arguments (engine parity with
CommandExecutor.ts createAndSavePoint/Scalar/Text + createAndSaveNode).

A string argument in a non-Text slot names a node: the existing node under
that id, or a fresh auto-created one (random Point coordinates / random Scalar
value / the id itself as a Text's value). Auto-created nodes are registered in
the store but record NO tape command — the emitted DSL references the bare id
and the engine auto-creates it again on replay, exactly as the TS executor
does. The same applies to unknown bare identifiers in parsed DSL lines.
"""

import pytest

import pygeomatic as gm
from pygeomatic.parse import DslParseError


# --- direct python calls -----------------------------------------------------


def test_line_auto_creates_points():
    with gm.Store() as st:
        ln = gm.line("a", "b")
        assert st.nodes["a"].type == "Point"
        assert st.nodes["b"].type == "Point"
        assert ln.p1.numeric == st.nodes["a"].numeric
    # One tape line: the auto-created points are store-only (the engine
    # re-creates them on replay).
    assert gm.emit(st) == "ln = \\line a b"


def test_point_auto_creates_scalars():
    with gm.Store() as st:
        gm.point("x", "y", out="pt")
        assert st.nodes["x"].type == "Scalar"
        assert st.nodes["y"].type == "Scalar"
    assert gm.emit(st) == "pt = \\point x y"


def test_triangle_auto_creates_three_points():
    with gm.Store() as st:
        gm.triangle("a", "b", "c", out="tr")
        assert all(st.nodes[i].type == "Point" for i in ("a", "b", "c"))
    assert gm.emit(st) == "tr = \\triangle a b c"


def test_random_payload_ranges():
    # Engine caps: scalar in [0, 2), point coordinates in [-3, 3).
    with gm.Store() as st:
        for i in range(50):
            gm.point(f"sx-{i}", f"sy-{i}")
            gm.line(f"pa-{i}", f"pb-{i}")
        for i in range(50):
            for sid in (f"sx-{i}", f"sy-{i}"):
                assert 0 <= st.nodes[sid].numeric < 2
            for pid in (f"pa-{i}", f"pb-{i}"):
                x, y = st.nodes[pid].numeric
                assert -3 <= x < 3 and -3 <= y < 3


def test_auto_created_values_are_random():
    with gm.Store() as st:
        gm.line("a", "b")
        assert st.nodes["a"].numeric != st.nodes["b"].numeric


def test_same_name_reused_within_one_call():
    with gm.Store() as st:
        ln = gm.line("a", "a")
        # one node auto-created, both slots bound to it
        assert ln.p1.numeric == ln.p2.numeric == st.nodes["a"].numeric
    assert gm.emit(st) == "ln = \\line a a"


def test_existing_node_is_referenced_not_recreated():
    with gm.Store() as st:
        p = gm.point(1, 2, out="pt")
        ln = gm.line("pt", "b")
        assert ln.p1.numeric == (1.0, 2.0)
        gm.distance("pt", "b", out="d")
        assert st.nodes["pt"] is p  # still the original
    assert gm.emit(st).splitlines() == [
        "pt = \\point 1 2",
        "ln = \\line pt b",
        "d = \\distance pt b",
    ]


def test_system_node_by_name():
    with gm.Store() as st:
        ln = gm.line("p0", "b")
        assert ln.p1.numeric == (0.0, 0.0)  # bound to the system origin
    assert gm.emit(st) == "ln = \\line p0 b"


def test_existing_node_still_type_checked():
    with gm.Store():
        gm.scalar(5, out="s-1")
        with pytest.raises(TypeError, match="expects Point, got a Scalar"):
            gm.line("s-1", "b")


def test_existing_node_by_name_for_any_param():
    with gm.Store() as st:
        gm.scalar(2, out="len")
        gm.highlight("len")
    assert gm.emit(st).splitlines() == ["len = \\scalar 2", "\\highlight len"]


def test_only_point_scalar_text_auto_create():
    # `Any` (and every other type) mirrors the executor's createAndSaveNode
    # error: unknown id + no concrete type hint → no auto-creation.
    with gm.Store():
        with pytest.raises(TypeError, match="'ghost' does not exist and Any cannot be auto-created"):
            gm.highlight("ghost")
    with gm.Store():
        with pytest.raises(TypeError, match="Line cannot be auto-created"):
            gm.slope_of_line("l1")


def test_auto_create_id_grammar_enforced():
    with gm.Store():
        with pytest.raises(ValueError, match="invalid geomatic identifier"):
            gm.line("bad name", "b")
    with gm.Store():
        # Engine auto-name shape (`p1`) stays rejected for authored ids.
        with pytest.raises(ValueError, match="unsafe geomatic identifier"):
            gm.line("p1", "b")


def test_text_param_string_keeps_value_semantics():
    # A plain str filling a Text slot is still a text VALUE (implicit \text),
    # never a node reference — only parse-replay auto-creates Text by id.
    with gm.Store() as st:
        gm.annotate_leader_line("a", "b", "hello", out="lead")
        assert st.nodes["a"].type == "Point"
    assert gm.emit(st).splitlines() == [
        'text-0 = \\text "hello"',
        "lead = \\annotate-leader-line a b text-0",
    ]


def test_keyword_argument_auto_creates():
    with gm.Store() as st:
        gm.point(y="b", out="pt")
        assert st.nodes["b"].type == "Scalar"
    # x's literal default is materialised, y references the auto-created scalar.
    assert gm.emit(st) == "pt = \\point 0 b"


def test_variadic_tail_auto_creates():
    with gm.Store() as st:
        gm.polygon("a", "b", "c", "d", out="poly")
        assert all(st.nodes[i].type == "Point" for i in ("a", "b", "c", "d"))
    assert gm.emit(st) == "poly = \\polygon a b c d"


def test_auto_created_ids_reserved_in_name_generator():
    # `num-3` taken by auto-create → the generator skips past it.
    with gm.Store() as st:
        gm.point("num-3", 1)
        gm.scalar(7)  # bare statement: gets the next auto id
        assert "num-4" in st.nodes
        assert st.nodes["num-3"].type == "Scalar"


# --- parse_dsl ---------------------------------------------------------------


def test_parse_line_auto_creates():
    with gm.Store() as st:
        gm.parse_dsl("\\line a b")
        assert st.nodes["a"].type == "Point"
        assert st.nodes["b"].type == "Point"
    assert gm.emit(st) == "line-0 = \\line a b"


def test_parse_point_and_triangle_auto_create():
    with gm.Store() as st:
        gm.parse_dsl("\\point x y\n\\triangle a b c")
        assert st.nodes["x"].type == "Scalar"
        assert all(st.nodes[i].type == "Point" for i in ("a", "b", "c"))


def test_parse_reuses_across_lines():
    with gm.Store() as st:
        gm.parse_dsl("\\line a b\nd = \\distance a b")
        assert st.nodes["d"].type == "Scalar"
        # distance is computed from the same auto-created points the line got
        ax, ay = st.nodes["a"].numeric
        bx, by = st.nodes["b"].numeric
        assert st.nodes["d"].numeric == pytest.approx(
            ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
        )


def test_parse_text_auto_creates_by_id():
    # Engine parity (createAndSaveText): the id itself becomes the value.
    with gm.Store() as st:
        gm.parse_dsl("\\annotate-leader-line a b mylabel")
        assert st.nodes["mylabel"].type == "Text"
        assert st.nodes["mylabel"].numeric == "mylabel"
    assert gm.emit(st) == "lead-0 = \\annotate-leader-line a b mylabel"


def test_parse_bare_text_command():
    with gm.Store() as st:
        gm.parse_dsl("\\text hello")
        assert st.nodes["hello"].numeric == "hello"
    assert gm.emit(st) == "text-0 = \\text hello"


def test_parse_engine_shaped_ids_auto_create():
    # Pasted scenes legitimately use engine-generated ids; they auto-create too.
    with gm.Store() as st:
        gm.parse_dsl("\\line p1 p2")
        assert st.nodes["p1"].type == "Point"


def test_parse_property_access_on_unknown_id_still_errors():
    with gm.Store():
        with pytest.raises(DslParseError, match="unknown node id 'ghost'"):
            gm.parse_dsl("\\scalar ghost.x")


def test_parse_unknown_id_for_other_types_still_errors():
    with gm.Store():
        with pytest.raises(DslParseError, match="'ghost' does not exist"):
            gm.parse_dsl("\\highlight ghost")


def test_parse_emit_round_trip():
    src = "line-0 = \\line a b\ntr = \\triangle a b c"
    with gm.Store() as first:
        gm.parse_dsl(src)
    assert gm.emit(first) == src
    with gm.Store() as second:
        gm.parse_dsl(gm.emit(first))
    assert gm.emit(second) == src


# --- macros ------------------------------------------------------------------

SEG_MACRO = [{"macro": "seg-between a b", "commands": ["seg-ln = \\line a b"]}]


def test_macro_argument_auto_creates_via_body():
    gm.load_macros(SEG_MACRO, name="test:auto-create")
    try:
        with gm.Store() as st:
            gm.seg_between("m", "n")
            assert st.nodes["m"].type == "Point"
            assert st.nodes["n"].type == "Point"
            assert st.nodes["seg-ln"].type == "Line"
        assert gm.emit(st) == "\\seg-between m n"
        # ...and through parse as well.
        with gm.Store() as st2:
            gm.parse_dsl("\\seg-between m n")
            assert st2.nodes["m"].type == "Point"
        assert gm.emit(st2) == "\\seg-between m n"
    finally:
        gm.unload_macros("test:auto-create")


def test_macro_argument_existing_node_still_binds():
    gm.load_macros(SEG_MACRO, name="test:auto-create-2")
    try:
        with gm.Store() as st:
            p = gm.point(1, 2, out="m")
            gm.seg_between("m", "n")
            assert st.nodes["m"] is p
        assert gm.emit(st).splitlines() == ["m = \\point 1 2", "\\seg-between m n"]
    finally:
        gm.unload_macros("test:auto-create-2")
