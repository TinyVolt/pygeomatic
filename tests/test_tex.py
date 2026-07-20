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
