"""Tests for onclick.py — gm.ui.onclick click handlers.

The harvested JSON is a wire contract with the TypeScript runtime
(src/lib/geomatic/ui/clickHandlers.ts); the shape assertions below pin it.
"""

import pytest

import pygeomatic as gm
from pygeomatic import ArticleError, OnClickError, UIError, compile_article


def fence(code: str) -> str:
    return f"```pygeomatic\n{code}\n```\n"


# ---------------------------------------------------------------------------
# The wire shape
# ---------------------------------------------------------------------------


def test_handler_is_harvested_and_leaves_no_dsl():
    with gm.Store() as s:
        t = gm.annotate_text_box("click me", 2, 3, out="t")
        with gm.ui.onclick(t):
            p = gm.point(2, 3, out="p")
            gm.gt(gm.distance(p, gm.p0), 1, out="far")

    # The scene emits exactly what it would with no handler at all.
    assert gm.emit(s).splitlines() == [
        'text-0 = \\text "click me"',
        "t = \\annotate-text-box text-0 2 3",
    ]
    assert gm.harvest_click_handlers(s) == {
        "t": {
            "commands": [
                "p = \\point 2 3",
                "num-0 = \\distance p p0",
                "far = \\gt num-0 1",
            ]
        }
    }


def test_handlers_scoped_to_store():
    with gm.Store():
        t = gm.annotate_text_box("a", 0, 0, out="t")
        with gm.ui.onclick(t):
            gm.point(1, 1)
    with gm.Store() as s2:
        assert gm.harvest_click_handlers(s2) == {}


def test_reopening_replaces_the_handler():
    with gm.Store() as s:
        t = gm.annotate_text_box("a", 0, 0, out="t")
        with gm.ui.onclick(t):
            gm.point(1, 1, out="first")
        with gm.ui.onclick(t):
            gm.point(2, 2, out="second")
    assert gm.harvest_click_handlers(s) == {
        "t": {"commands": ["second = \\point 2 2"]}
    }


def test_two_nodes_keep_separate_handlers():
    with gm.Store() as s:
        a = gm.circle(gm.p0, 1, out="a")
        b = gm.circle(gm.p0, 2, out="b")
        with gm.ui.onclick(a):
            gm.point(1, 1, out="pa")
        with gm.ui.onclick(b):
            gm.point(2, 2, out="pb")
    assert list(gm.harvest_click_handlers(s)) == ["a", "b"]


# ---------------------------------------------------------------------------
# Body nodes stay usable (the gm.when pairing)
# ---------------------------------------------------------------------------


def test_body_nodes_remain_registered():
    with gm.Store() as s:
        t = gm.annotate_text_box("a", 0, 0, out="t")
        with gm.ui.onclick(t):
            far = gm.gt(gm.scalar(3), 1, out="far")
        # Readable afterwards, and usable as a gm.when gate — which records no
        # DSL, so it does not violate the main-tape rule.
        assert s.nodes["far"] is far
        assert gm.cond.to_payload(far) == {"node": "far"}
    assert gm.emit(s).splitlines() == [
        'text-0 = \\text "a"',
        "t = \\annotate-text-box text-0 0 0",
    ]


def test_main_tape_may_not_consume_a_handler_node():
    with gm.Store() as s:
        t = gm.annotate_text_box("a", 0, 0, out="t")
        with gm.ui.onclick(t):
            p = gm.point(1, 1, out="p")
        gm.circle(p, 2)  # runs at load time, when `p` does not exist yet
        with pytest.raises(OnClickError, match="only run when the reader clicks"):
            gm.harvest_click_handlers(s)


def test_property_access_to_a_handler_node_is_caught_too():
    with gm.Store() as s:
        t = gm.annotate_text_box("a", 0, 0, out="t")
        with gm.ui.onclick(t):
            p = gm.point(1, 1, out="p")
        gm.scalar(0) + p.x
        with pytest.raises(OnClickError, match=r"\bp\b"):
            gm.harvest_click_handlers(s)


# ---------------------------------------------------------------------------
# Variadic fusion must not reach across the block's edge
# ---------------------------------------------------------------------------


def test_fusion_barrier_at_both_edges():
    with gm.Store() as s:
        t = gm.annotate_text_box("a", 0, 0, out="t")
        a = gm.scalar(1, out="a")
        b = gm.scalar(2, out="b")
        a + b  # anonymous, fusable — must NOT be absorbed by the handler
        with gm.ui.onclick(t):
            a + b  # nor absorb the main-tape command before it
        a + b
    assert gm.emit(s).splitlines() == [
        'text-0 = \\text "a"',
        "t = \\annotate-text-box text-0 0 0",
        "a = \\scalar 1",
        "b = \\scalar 2",
        "num-0 = \\add a b",
        "num-2 = \\add a b",
    ]
    assert gm.harvest_click_handlers(s) == {"t": {"commands": ["num-1 = \\add a b"]}}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_empty_body_raises():
    with gm.Store():
        t = gm.annotate_text_box("a", 0, 0, out="t")
        with pytest.raises(OnClickError, match="recorded no commands"):
            with gm.ui.onclick(t):
                pass


def test_nesting_raises():
    with gm.Store():
        a = gm.circle(gm.p0, 1, out="a")
        b = gm.circle(gm.p0, 2, out="b")
        with pytest.raises(OnClickError, match="do not nest"):
            with gm.ui.onclick(a):
                gm.point(1, 1)
                with gm.ui.onclick(b):
                    gm.point(2, 2)


@pytest.mark.parametrize(
    "make, match",
    [
        (lambda: gm.scalar(1), "never be clicked"),
        (lambda: gm.text("hello"), "never be clicked"),
        (lambda: gm.bool_(True), "never be clicked"),
    ],
)
def test_unclickable_target_raises(make, match):
    with gm.Store():
        with pytest.raises(OnClickError, match=match):
            with gm.ui.onclick(make()):
                gm.point(1, 1)


def test_non_node_target_raises():
    with gm.Store():
        with pytest.raises(OnClickError, match="takes a node"):
            with gm.ui.onclick("t"):
                gm.point(1, 1)


def test_ui_control_inside_a_handler_raises():
    with gm.Store():
        t = gm.annotate_text_box("a", 0, 0, out="t")
        with pytest.raises(UIError, match="cannot be created inside"):
            with gm.ui.onclick(t):
                gm.ui.slider(1, 5)


# ---------------------------------------------------------------------------
# Article integration
# ---------------------------------------------------------------------------


HANDLER_FENCE = """\
t = gm.annotate_text_box("click me", 2, 3, out="t")
with gm.ui.onclick(t):
    gm.point(2, 3, out="p")
"""


def test_compile_article_appends_the_manifest():
    out = compile_article(fence(HANDLER_FENCE))
    assert '{}(t = \\annotate-text-box text-0 2 3)' in out
    assert "p = \\point 2 3" not in out.split("<!-- onclick:v1")[0]
    assert out.rstrip().endswith(
        '<!-- onclick:v1\n{"t":{"commands":["p = \\\\point 2 3"]}}\n-->'
    )


def test_article_without_handlers_is_unchanged():
    out = compile_article(fence("a = gm.point(3, 0)"))
    assert "onclick:v1" not in out


def test_both_manifests_are_appended():
    code = HANDLER_FENCE + 'gm.tex("f").frac.num.bind(gm.scalar(2, out="b"))\n'
    out = compile_article(fence(code))
    assert "<!-- texatlas:v1" in out
    # onclick last: the reader strips trailing manifests in a loop.
    assert out.index("<!-- texatlas:v1") < out.index("<!-- onclick:v1")


def test_dangling_reference_fails_compilation():
    # In an article the round-trip gate reaches it first (the handler's
    # definition is not among the spans it replays), so the message comes from
    # there; harvest's own check covers the non-article paths.
    code = HANDLER_FENCE + "gm.circle(gm.node('p'), 2)\n"
    with pytest.raises(ArticleError, match="unknown node id 'p'"):
        compile_article(fence(code))


def test_group_inside_a_handler_raises():
    code = HANDLER_FENCE.replace(
        "    gm.point(2, 3, out=\"p\")",
        "    with group('g'):\n        gm.point(2, 3, out='p')",
    )
    with pytest.raises(ArticleError, match="opened inside the gm.ui.onclick block"):
        compile_article(fence(code))


def test_md_inside_a_handler_raises():
    code = HANDLER_FENCE + "with gm.ui.onclick(t):\n    gm.md('hi')\n"
    with pytest.raises(ArticleError, match="cannot be produced by a click"):
        compile_article(fence(code))
