"""Tests for tex.py — gm.tex texatlas bindings recorder.

The harvested JSON is a frozen wire contract with the TypeScript runtime; the
three "worked example" tests below pin it to that repo's CONTRACT.md byte-shape.
"""

import pytest

import pygeomatic as gm
from pygeomatic import TexError


# ---------------------------------------------------------------------------
# The three worked examples from CONTRACT.md
# ---------------------------------------------------------------------------


def test_worked_example_value_bind():
    with gm.Store() as s:
        b = gm.scalar(2, out="b")
        gm.tex("integral").int.upper.bind(b)
    assert gm.harvest_tex_bindings(s) == {
        "integral": {"values": [{"slot": "int.upper", "node": "b"}]}
    }


def test_worked_example_row_highlight():
    with gm.Store() as s:
        r = gm.scalar(0, out="r")
        M = gm.tex("M")
        M.highlight(M.rows().eq(r), color="#f472b6")
    assert gm.harvest_tex_bindings(s) == {
        "M": {
            "highlights": [
                {
                    "selector": {
                        "op": "eq",
                        "axis": {"axis": "row"},
                        "value": {"node": "r"},
                    },
                    "color": "#f472b6",
                }
            ]
        }
    }


def test_worked_example_upper_triangle():
    with gm.Store() as s:
        M = gm.tex("M")
        M.highlight(M.cols().sub(M.rows()).ge(0), color="#6aa8ff")
    assert gm.harvest_tex_bindings(s) == {
        "M": {
            "highlights": [
                {
                    "selector": {
                        "op": "ge",
                        "axis": {
                            "op": "sub",
                            "a": {"axis": "col"},
                            "b": {"axis": "row"},
                        },
                        "value": {"const": 0},
                    },
                    "color": "#6aa8ff",
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Bindings are recorded off the command tape
# ---------------------------------------------------------------------------


def test_tex_records_no_dsl_command():
    with gm.Store() as s:
        a = gm.scalar(4, out="a")
        gm.tex("f").frac.num.bind(a)
    assert gm.emit(s) == "a = \\scalar 4"  # the tex op left no line


def test_bindings_scoped_to_store():
    with gm.Store():
        a = gm.scalar(1, out="a")
        gm.tex("f").int.upper.bind(a)
    with gm.Store() as s2:
        assert gm.harvest_tex_bindings(s2) == {}


# ---------------------------------------------------------------------------
# show / fmt on a value binding
# ---------------------------------------------------------------------------


def test_show_symbol_and_fmt_recorded():
    with gm.Store() as s:
        a = gm.scalar(1, out="a")
        gm.tex("f").int.upper.bind(a, show="symbol", fmt=".2f")
    (entry,) = gm.harvest_tex_bindings(s)["f"]["values"]
    assert entry == {"slot": "int.upper", "node": "a", "show": "symbol", "fmt": ".2f"}


def test_show_value_is_omitted_as_default():
    with gm.Store() as s:
        a = gm.scalar(1, out="a")
        gm.tex("f").int.upper.bind(a, show="value")
    (entry,) = gm.harvest_tex_bindings(s)["f"]["values"]
    assert "show" not in entry and "fmt" not in entry


def test_fmt_d_allowed():
    with gm.Store() as s:
        a = gm.scalar(1, out="a")
        gm.tex("f").int.upper.bind(a, fmt="d")
    assert gm.harvest_tex_bindings(s)["f"]["values"][0]["fmt"] == "d"


def test_invalid_show_rejected():
    with gm.Store():
        a = gm.scalar(1, out="a")
        with pytest.raises(TexError, match="show must be"):
            gm.tex("f").int.upper.bind(a, show="glow")


def test_invalid_fmt_rejected():
    with gm.Store():
        a = gm.scalar(1, out="a")
        with pytest.raises(TexError, match="invalid fmt"):
            gm.tex("f").int.upper.bind(a, fmt="%.2f")


# ---------------------------------------------------------------------------
# Slot / family addressing
# ---------------------------------------------------------------------------


def test_bind_node_by_id_string():
    with gm.Store() as s:
        gm.scalar(1, out="a")
        gm.tex("f").frac.denom.bind("a")
    assert gm.harvest_tex_bindings(s)["f"]["values"][0] == {"slot": "frac.denom", "node": "a"}


def test_occurrence_index_addressing():
    with gm.Store() as s:
        a = gm.scalar(1, out="a")
        gm.tex("f").ints[1].lower.bind(a)
    assert gm.harvest_tex_bindings(s)["f"]["values"][0]["slot"] == "int[1].lower"


def test_bind_whole_family_without_slot():
    with gm.Store() as s:
        a = gm.scalar(1, out="a")
        gm.tex("f").frac.bind(a)
    assert gm.harvest_tex_bindings(s)["f"]["values"][0]["slot"] == "frac"


def test_unknown_family_rejected():
    with gm.Store():
        with pytest.raises(TexError, match="unknown LaTeX slot family 'wat'"):
            gm.tex("f").wat


def test_unknown_slot_rejected():
    with gm.Store():
        a = gm.scalar(1, out="a")
        with pytest.raises(TexError, match="has no slot 'sideways'"):
            gm.tex("f").int.sideways.bind(a)


def test_bind_unknown_node_rejected():
    with gm.Store():
        with pytest.raises(TexError, match="no node 'ghost'"):
            gm.tex("f").int.upper.bind("ghost")


def test_negative_occurrence_index_rejected():
    with gm.Store():
        with pytest.raises(TexError, match="non-negative int"):
            gm.tex("f").ints[-1]


# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------


def test_and_or_scale_selectors():
    with gm.Store() as s:
        r = gm.scalar(0, out="r")
        u = gm.scalar(1, out="u")
        M = gm.tex("M")
        sel = M.rows().eq(r).and_(M.cols().ge(1)).scale(u)
        M.highlight(sel)
    (h,) = gm.harvest_tex_bindings(s)["M"]["highlights"]
    assert h["selector"] == {
        "op": "scale",
        "sel": {
            "op": "and",
            "a": {"op": "eq", "axis": {"axis": "row"}, "value": {"node": "r"}},
            "b": {"op": "ge", "axis": {"axis": "col"}, "value": {"const": 1}},
        },
        "by": {"node": "u"},
    }


def test_axis_arithmetic_operators():
    with gm.Store() as s:
        M = gm.tex("M")
        # `&` / `|` operator sugar and axis `+` / `-`.
        sel = (M.cols() + 1).eq(2).or_(M.rows().le(0)) | M.rows().ge(3)
        M.highlight(sel)
    top = gm.harvest_tex_bindings(s)["M"]["highlights"][0]["selector"]
    assert top["op"] == "or"


def test_selector_value_must_not_be_bool():
    with gm.Store():
        M = gm.tex("M")
        with pytest.raises(TexError, match="not a bool"):
            M.rows().eq(True)


# ---------------------------------------------------------------------------
# Free axis handles  —  rows / cols / dim(i)   (ergonomics #1)
# ---------------------------------------------------------------------------


def test_free_axes_match_method_axes():
    from pygeomatic import cols, rows

    with gm.Store() as s1:
        r = gm.scalar(0, out="r")
        gm.tex("M").highlight(rows == r)
    with gm.Store() as s2:
        r = gm.scalar(0, out="r")
        M = gm.tex("M")
        M.highlight(M.rows().eq(r))
    assert gm.harvest_tex_bindings(s1) == gm.harvest_tex_bindings(s2)


def test_dim_maps_to_row_col():
    from pygeomatic import dim

    with gm.Store() as s:
        M = gm.tex("M")
        M.highlight(dim(0).eq(1))
        M.highlight(dim(1).eq(2))
    axes = [h["selector"]["axis"] for h in gm.harvest_tex_bindings(s)["M"]["highlights"]]
    assert axes == [{"axis": "row"}, {"axis": "col"}]


def test_dim_rank_over_two_rejected():
    from pygeomatic import dim

    with pytest.raises(TexError, match="rank > 2"):
        dim(2)
    with pytest.raises(TexError, match="non-negative int"):
        dim(-1)


# ---------------------------------------------------------------------------
# Comparison / arithmetic operators  (ergonomics #2)
# ---------------------------------------------------------------------------


def test_operator_forms_lower_to_named_methods():
    from pygeomatic import cols, rows

    with gm.Store() as s1:
        M = gm.tex("M")
        M.highlight(cols - rows > 0, color="#6aa8ff")
    with gm.Store() as s2:
        M = gm.tex("M")
        M.highlight(M.cols().sub(M.rows()).ge(0), color="#6aa8ff")
    # `> 0` is `>= 1` on integer indices — NOT equal to `.ge(0)`.
    assert gm.harvest_tex_bindings(s1) != gm.harvest_tex_bindings(s2)
    sel = gm.harvest_tex_bindings(s1)["M"]["highlights"][0]["selector"]
    assert sel["op"] == "ge" and sel["value"] == {"const": 1}


def test_eq_ge_le_operators():
    from pygeomatic import rows

    with gm.Store() as s:
        r = gm.scalar(0, out="r")
        M = gm.tex("M")
        M.highlight(rows == r)
        M.highlight(rows >= 2)
        M.highlight(rows <= 5)
    ops = [(h["selector"]["op"], h["selector"]["value"]) for h in gm.harvest_tex_bindings(s)["M"]["highlights"]]
    assert ops == [("eq", {"node": "r"}), ("ge", {"const": 2}), ("le", {"const": 5})]


def test_reflected_arithmetic():
    from pygeomatic import rows

    with gm.Store() as s:
        M = gm.tex("M")
        M.highlight((1 + rows).eq(3))  # __radd__
    sel = gm.harvest_tex_bindings(s)["M"]["highlights"][0]["selector"]
    assert sel["axis"] == {"op": "add", "a": {"const": 1}, "b": {"axis": "row"}}


def test_strict_operator_needs_integer_bound():
    from pygeomatic import rows

    with gm.Store():
        r = gm.scalar(0, out="r")
        with pytest.raises(TexError, match="strict '>' needs an integer bound"):
            rows > r


# ---------------------------------------------------------------------------
# Slice / cell-region syntax  (ergonomics #3)
# ---------------------------------------------------------------------------


def test_slice_box_is_and_of_bounds():
    with gm.Store() as s:
        M = gm.tex("M")
        M[3:, 4:].highlight(color="#10B981")
    sel = gm.harvest_tex_bindings(s)["M"]["highlights"][0]["selector"]
    assert sel == {
        "op": "and",
        "a": {"op": "ge", "axis": {"axis": "row"}, "value": {"const": 3}},
        "b": {"op": "ge", "axis": {"axis": "col"}, "value": {"const": 4}},
    }


def test_slice_exclusive_stop():
    with gm.Store() as s:
        M = gm.tex("M")
        M[:3, :].highlight()  # rows 0..2  ->  row <= 2
    sel = gm.harvest_tex_bindings(s)["M"]["highlights"][0]["selector"]
    assert sel == {"op": "le", "axis": {"axis": "row"}, "value": {"const": 2}}


def test_single_index_is_equality_and_node_is_reactive():
    with gm.Store() as s:
        c = gm.scalar(0, out="c")
        M = gm.tex("M")
        M[:, c].highlight()  # exact column, node -> reactive
    sel = gm.harvest_tex_bindings(s)["M"]["highlights"][0]["selector"]
    assert sel == {"op": "eq", "axis": {"axis": "col"}, "value": {"node": "c"}}


def test_slice_node_start_is_reactive():
    with gm.Store() as s:
        r = gm.scalar(0, out="r")
        M = gm.tex("M")
        M[r:, :].highlight()
    sel = gm.harvest_tex_bindings(s)["M"]["highlights"][0]["selector"]
    assert sel == {"op": "ge", "axis": {"axis": "row"}, "value": {"node": "r"}}


def test_trailing_ellipsis_is_noop():
    with gm.Store() as s1:
        M = gm.tex("M")
        M[2, ...].highlight()
    with gm.Store() as s2:
        M = gm.tex("M")
        M[2].highlight()
    assert gm.harvest_tex_bindings(s1) == gm.harvest_tex_bindings(s2)


def test_region_union_stays_paintable():
    with gm.Store() as s:
        M = gm.tex("M")
        (M[3:, :] | M[:, 4:]).highlight(color="pink")  # combined region keeps .highlight
    top = gm.harvest_tex_bindings(s)["M"]["highlights"][0]["selector"]
    assert top["op"] == "or"


def test_whole_matrix_slice_rejected():
    with gm.Store():
        M = gm.tex("M")
        with pytest.raises(TexError, match="constrain at least one axis"):
            M[:, :]


def test_slice_step_rejected():
    with gm.Store():
        M = gm.tex("M")
        with pytest.raises(TexError, match="step is not supported"):
            M[::2, :]


def test_slice_node_stop_rejected():
    with gm.Store():
        r = gm.scalar(0, out="r")
        M = gm.tex("M")
        with pytest.raises(TexError, match="exclusive slice stop must be an integer"):
            M[:r, :]


# ---------------------------------------------------------------------------
# Named region helpers  (ergonomics #6)
# ---------------------------------------------------------------------------


def test_diag_triu_tril():
    with gm.Store() as s:
        M = gm.tex("M")
        M.diag().highlight()
        M.triu(1).highlight()
        M.tril().highlight()
    hs = gm.harvest_tex_bindings(s)["M"]["highlights"]
    base = {"op": "sub", "a": {"axis": "col"}, "b": {"axis": "row"}}
    assert hs[0]["selector"] == {"op": "eq", "axis": base, "value": {"const": 0}}
    assert hs[1]["selector"] == {"op": "ge", "axis": base, "value": {"const": 1}}
    assert hs[2]["selector"] == {"op": "le", "axis": base, "value": {"const": 0}}


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------


def test_palette_name_resolved_to_hex():
    with gm.Store() as s:
        r = gm.scalar(0, out="r")
        M = gm.tex("M")
        M.highlight(M.rows().eq(r), color="BLUE")
    assert gm.harvest_tex_bindings(s)["M"]["highlights"][0]["color"] == gm.PALETTE["COLOR-BLUE"]


def test_raw_hex_passes_through():
    with gm.Store() as s:
        r = gm.scalar(0, out="r")
        M = gm.tex("M")
        M.highlight(M.rows().eq(r), color="#abcdef")
    assert gm.harvest_tex_bindings(s)["M"]["highlights"][0]["color"] == "#abcdef"


def test_unknown_color_name_passes_through():
    with gm.Store() as s:
        r = gm.scalar(0, out="r")
        M = gm.tex("M")
        M.highlight(M.rows().eq(r), color="rebeccapurple")
    assert gm.harvest_tex_bindings(s)["M"]["highlights"][0]["color"] == "rebeccapurple"


# ---------------------------------------------------------------------------
# harvest shape
# ---------------------------------------------------------------------------


def test_empty_formula_dropped_from_harvest():
    with gm.Store() as s:
        gm.tex("touched-but-unbound")
    assert gm.harvest_tex_bindings(s) == {}


def test_register_tex_schema_extends_families():
    with gm.Store() as s:
        gm.register_tex_schema("binom", ("top", "bottom"))
        try:
            a = gm.scalar(1, out="a")
            gm.tex("f").binom.top.bind(a)
            assert gm.harvest_tex_bindings(s)["f"]["values"][0]["slot"] == "binom.top"
        finally:
            gm.SCHEMA.pop("binom", None)


# ---------------------------------------------------------------------------
# Article compiler integration
# ---------------------------------------------------------------------------


def test_compile_article_snapshots_bindings():
    md = (
        "# Doc\n\n"
        "```pygeomatic\n"
        "a = gm.scalar(4, out='a')\n"
        "with group('g'):\n"
        "    gm.point(1, 2, out='pt')\n"
        "gm.tex('energy').int.upper.bind(a)\n"
        "```\n\n"
        "Scene: {show}(ref:g)\n"
    )
    out = gm.compile_article(md)
    assert "<!-- texatlas:v1" in out
    assert '"energy":{"values":[{"slot":"int.upper","node":"a"}]}' in out
    # DSL spans are unaffected; the tex op recorded no span.
    assert "{show}(pt = \\point 1 2)" in out
    assert "tex" not in out.split("<!-- texatlas")[0]  # no tex text leaked into the article body


def test_compile_article_without_bindings_has_no_manifest():
    md = (
        "```pygeomatic\n"
        "with group('g'):\n"
        "    gm.point(1, 2, out='pt')\n"
        "```\n\n"
        "{show}(ref:g)\n"
    )
    out = gm.compile_article(md)
    assert "texatlas" not in out
