"""Tests for uitree.py — gm.ui element trees, their manifest, and the rules.

The counterpart to test_ui.py, which covers a single control on its own
element. A tree is the same controls arranged into a panel, carried in the
`ui:v1` manifest instead.
"""

import json
import re

import pytest

import pygeomatic as gm
from pygeomatic import ArticleError, compile_article
from pygeomatic.article import _scan_spans, _segment, _Prose
from pygeomatic.uitree import UITreeError


def fence(code: str) -> str:
    return f"```pygeomatic\n{code}\n```\n"


def ui_manifest(compiled: str) -> dict:
    """The decoded `ui:v1` payload of a compiled article."""
    match = re.search(r"<!-- ui:v1\n(.*?)\n-->", compiled, re.S)
    assert match, f"no ui:v1 manifest in {compiled!r}"
    return json.loads(match.group(1))


def one_tree(code: str) -> dict:
    """Compile a fence and return the single tree it built."""
    trees = ui_manifest(compile_article(fence(code)))
    assert list(trees) == ["t0"], f"expected one tree, got {list(trees)}"
    return trees["t0"]


PANEL = (
    "with gm.ui.col(gap=2):\n"
    '    gm.ui.label("Radius")\n'
    "    r = gm.ui.slider(1, 5, value=3)\n"
)


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_a_container_becomes_a_tree_in_the_manifest():
    tree = one_tree(PANEL)
    assert tree["tag"] == "col"
    assert tree["gap"] == 2
    assert [child["tag"] for child in tree["children"]] == ["label", "slider"]


def test_the_prose_gets_only_a_placeholder():
    compiled = compile_article(fence(PANEL))
    assert '<div class="nova-ui-tree" data-tree="t0"></div>' in compiled
    # The tree itself must NOT be inline: a panel does not fit on the one line
    # markdown allows, and the compiled .md is read on GitHub.
    body = compiled.split("<!-- ui:v1")[0]
    assert '"tag"' not in body


def test_a_control_in_a_tree_does_not_become_an_inline_span():
    compiled = compile_article(fence(PANEL))
    assert 'class="nova-ui"' not in compiled


def test_containers_nest():
    tree = one_tree(
        "with gm.ui.col():\n"
        "    with gm.ui.row(gap=1):\n"
        '        gm.ui.label("a")\n'
        '        gm.ui.label("b")\n'
    )
    row = tree["children"][0]
    assert row["tag"] == "row"
    assert [c["text"] for c in row["children"]] == ["a", "b"]


def test_only_the_outermost_container_emits_a_placeholder():
    compiled = compile_article(
        fence("with gm.ui.col():\n    with gm.ui.row():\n        gm.ui.label(\"a\")\n")
    )
    assert compiled.count('class="nova-ui-tree"') == 1


def test_two_trees_get_their_own_ids():
    trees = ui_manifest(
        compile_article(
            fence(
                'with gm.ui.col():\n    gm.ui.label("a")\n'
                'with gm.ui.col():\n    gm.ui.label("b")\n'
            )
        )
    )
    assert list(trees) == ["t0", "t1"]


def test_an_article_without_a_tree_has_no_manifest():
    compiled = compile_article(fence("r = gm.scalar(3)\n"))
    assert "ui:v1" not in compiled


# ---------------------------------------------------------------------------
# The article-compiler safety property
# ---------------------------------------------------------------------------


def test_commands_are_identical_with_and_without_a_tree():
    """A tree is presentation only: the DSL must not shift by one token.

    The same assertion test_ui.py makes for a single control, and for the same
    reason — a tree that changed the tape would change the scene, which no
    amount of layout is allowed to do.
    """
    with_tree = fence(
        "with gm.ui.col(gap=2):\n"
        '    gm.ui.label("Radius")\n'
        "    r = gm.ui.slider(1, 5, value=3)\n"
        "c = gm.circle(gm.p0, r)\n"
    )
    without_tree = fence("r = gm.scalar(3)\nc = gm.circle(gm.p0, r)\n")

    def commands(compiled: str) -> list[str]:
        return [
            s.content.strip()
            for part in _segment(compiled)
            if isinstance(part, _Prose) and part.scan
            for s in _scan_spans(part.text)
        ]

    assert commands(compile_article(with_tree)) == commands(compile_article(without_tree))


def test_the_manifest_sits_after_the_other_three():
    compiled = compile_article(
        "$$\n%id:f\n\\int_{a}^{b} x \\, dx\n$$\n\n"
        + fence(
            "with gm.onpageload():\n"
            "    box = gm.annotate_text_box(\"hi\", 2, 3)\n"
            "    with gm.ui.onclick(box):\n"
            "        p = gm.point(2, 3)\n"
            "    with gm.ui.col():\n"
            "        r = gm.ui.slider(1, 5)\n"
            "b = gm.tex(\"f\")\n"
            "b.int.upper.bind(r)\n"
        )
    )
    order = [compiled.index(f"<!-- {tag}:v1") for tag in ("texatlas", "onclick", "onpageload", "ui")]
    assert order == sorted(order)


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


def test_a_button_records_its_commands_in_the_onclick_manifest():
    compiled = compile_article(
        fence(
            "r = gm.scalar(3, out=\"r\")\n"
            "with gm.ui.col():\n"
            '    with gm.ui.button("reset"):\n'
            '        r2 = gm.scalar(9, out="r")\n'
        )
    )
    match = re.search(r"<!-- onclick:v1\n(.*?)\n-->", compiled, re.S)
    assert match
    assert json.loads(match.group(1)) == {"btn-0": {"commands": ["r = \\scalar 9"]}}


def test_a_button_element_carries_only_its_action_id():
    tree = one_tree(
        "with gm.ui.col():\n"
        '    with gm.ui.button("reset"):\n'
        '        r = gm.scalar(3, out="r")\n'
    )
    button = tree["children"][0]
    assert button == {"tag": "button", "label": "reset", "action": "btn-0"}


def test_a_buttons_commands_leave_the_tape():
    """Like a click handler's: they run on a press, not in document order.

    If they stayed, they would also renumber every command link after them,
    because links are numbered by document position.
    """
    compiled = compile_article(
        fence(
            "with gm.ui.col():\n"
            '    with gm.ui.button("go"):\n'
            "        p = gm.point(1, 1)\n"
        )
    )
    assert "\\point 1 1" not in compiled.split("<!-- onclick:v1")[0]


def test_an_empty_button_is_refused():
    with pytest.raises(ArticleError, match="recorded no commands"):
        compile_article(
            fence('with gm.ui.col():\n    with gm.ui.button("go"):\n        pass\n')
        )


def test_a_button_outside_a_container_is_refused():
    with pytest.raises(ArticleError, match="needs an open container"):
        compile_article(fence('with gm.ui.button("go"):\n    p = gm.point(1, 1)\n'))


# ---------------------------------------------------------------------------
# when
# ---------------------------------------------------------------------------


def test_when_inside_a_tree_becomes_an_element():
    tree = one_tree(
        "r = gm.ui.slider(1, 5)\n"
        "with gm.ui.col():\n"
        "    with when(gm.cond.ge(r, 4)):\n"
        '        gm.ui.label("large")\n'
    )
    gate = tree["children"][0]
    assert gate["tag"] == "when"
    assert gate["cond"] == {"op": "ge", "a": {"node": "r"}, "b": {"const": 4.0}}
    assert gate["children"][0]["text"] == "large"


def test_when_outside_a_tree_still_gates_prose():
    """The tree branch must not have changed the prose path."""
    compiled = compile_article(
        fence(
            "show = gm.ui.checkbox(False)\n"
            "with when(show):\n"
            '    gm.md("hidden for now")\n'
        )
    )
    assert 'class="nova-when"' in compiled
    assert "ui:v1" not in compiled


# ---------------------------------------------------------------------------
# Validation — the whole point of the schema
# ---------------------------------------------------------------------------


def test_an_unknown_attribute_is_refused_with_a_line_number():
    """A typo must not be silent. The constructor's own signature catches it,
    and the compiler attaches the article line — which is what a model writing
    this python needs to see."""
    with pytest.raises(ArticleError, match="line 3: TypeError.*unexpected keyword"):
        compile_article(fence('with gm.ui.col():\n    gm.ui.label("a", wdth=3)\n'))


def test_a_bad_enum_value_names_the_choices():
    with pytest.raises(ArticleError, match="must be one of start, center, end, stretch"):
        compile_article(fence('with gm.ui.col(align="middle"):\n    gm.ui.label("a")\n'))


def test_free_form_css_is_refused():
    with pytest.raises(ArticleError, match="must use one of"):
        compile_article(
            fence('with gm.ui.col():\n    gm.ui.label("a", width="calc(100% - 3px)")\n')
        )


def test_a_spacing_step_off_the_scale_is_refused():
    with pytest.raises(ArticleError, match="between 0 and 9"):
        compile_article(fence('with gm.ui.col(gap=42):\n    gm.ui.label("a")\n'))


def test_every_whitelisted_unit_is_accepted():
    for width in ("10px", "12ch", "50%", "2rem", "fill", 4):
        code = f'with gm.ui.col():\n    gm.ui.label("a", width={width!r})\n'
        assert one_tree(code)["children"][0]["width"] == width


def test_an_empty_container_is_refused():
    with pytest.raises(ArticleError, match="is empty"):
        compile_article(fence("with gm.ui.col():\n    pass\n"))


def test_a_label_outside_a_container_is_refused():
    with pytest.raises(ArticleError, match="needs an open container"):
        compile_article(fence('gm.ui.label("stray")\n'))


def test_layout_on_an_inline_control_is_refused():
    """Sizing only means something inside a tree; inline, the sentence decides."""
    with pytest.raises(ArticleError, match="not inside a"):
        compile_article(fence('r = gm.ui.slider(1, 5, width="12ch")\ngm.md(f"{r}")\n'))


def test_a_tree_reading_an_undefined_node_is_refused():
    """The reference check: a control with no node behind it is dead on arrival,
    and nothing would report that at read time."""
    with pytest.raises(ArticleError, match="which the article never defines"):
        compile_article(
            fence(
                "with gm.ui.col():\n"
                '    gm.ui.label("value is ${ghost}")\n'
            )
        )


def test_a_tree_may_not_consume_a_node_only_a_button_defines():
    """A button's commands run on a press, so the node does not exist until then."""
    with pytest.raises(ArticleError, match="which the article never defines"):
        compile_article(
            fence(
                "with gm.ui.col():\n"
                '    with gm.ui.button("make"):\n'
                '        made = gm.scalar(1, out="made")\n'
                '    gm.ui.label("made is ${made}")\n'
            )
        )


def test_a_tree_may_consume_a_node_gm_onpageload_defines():
    tree = one_tree(
        "with gm.onpageload():\n"
        "    r = gm.ui.slider(1, 5)\n"
        "    with gm.ui.col():\n"
        '        gm.ui.label("r is ${r}")\n'
    )
    assert tree["children"][0]["text"] == "r is ${r}"


# ---------------------------------------------------------------------------
# Name inference still works inside a container
# ---------------------------------------------------------------------------


def test_a_control_in_a_tree_keeps_its_python_name():
    """`r = gm.ui.slider(...)` must still name its node `r`.

    Inference hops frames whose module is `pygeomatic.ui`, and a container adds
    none, but this is the assertion that says so.
    """
    tree = one_tree("with gm.ui.col():\n    radius = gm.ui.slider(1, 5)\n")
    assert tree["children"][0]["node"] == "radius"


def test_every_control_works_as_a_tree_leaf():
    tree = one_tree(
        "with gm.ui.col():\n"
        "    a = gm.ui.slider(1, 5)\n"
        "    b = gm.ui.number(0, 10)\n"
        "    c = gm.ui.checkbox(False)\n"
        '    d = gm.ui.dropdown(["x", "y"])\n'
        "    e = gm.ui.radio([1, 2])\n"
        '    f = gm.ui.text("hi")\n'
    )
    assert [child["tag"] for child in tree["children"]] == [
        "slider",
        "number",
        "checkbox",
        "dropdown",
        "radio",
        "text",
    ]
    assert [child["node"] for child in tree["children"]] == ["a", "b", "c", "d", "e", "f"]


def test_options_and_initial_value_reach_the_manifest_camel_cased():
    """The browser reads `initialValue`; the inline path writes
    `data-initial-value`. One conversion, in `_camel`."""
    tree = one_tree('with gm.ui.col():\n    m = gm.ui.dropdown(["sum", "max"], "max")\n')
    leaf = tree["children"][0]
    assert leaf["options"] == ["sum", "max"]
    assert leaf["initialValue"] == "max"
    assert "initial-value" not in leaf


def test_a_button_id_cannot_collide_with_a_clickable_node():
    """Buttons share the click-handler channel with gm.ui.onclick, which keys by
    node id. A node the author named `btn-0` would otherwise be replaced."""
    compiled = compile_article(
        fence(
            'btn0 = gm.annotate_text_box("me", 1, 1, out="btn-0")\n'
            "with gm.ui.onclick(btn0):\n"
            "    p = gm.point(9, 9)\n"
            "with gm.ui.col():\n"
            '    with gm.ui.button("go"):\n'
            "        q = gm.point(1, 1)\n"
        )
    )
    match = re.search(r"<!-- onclick:v1\n(.*?)\n-->", compiled, re.S)
    handlers = json.loads(match.group(1))
    assert handlers["btn-0"]["commands"] == ["p = \\point 9 9"]
    assert "btn-1" in handlers
