"""Tests for onpageload.py — gm.onpageload, the article's load-time scene.

The harvested JSON is a wire contract with the TypeScript runtime
(src/lib/geomatic/ui/pageLoad.ts); the shape assertions below pin it.

Almost everything here goes through `compile_article`: the block is only legal
inside an article's first fence, so there is no bare-Store happy path to test.
"""

import pytest

import pygeomatic as gm
from pygeomatic import ArticleError, PageLoadError, compile_article


def fence(code: str) -> str:
    return f"```pygeomatic\n{code}\n```\n"


BLOCK = """\
with gm.onpageload():
    r = gm.ui.slider(1, 5, step=0.5, value=3, label="radius")
    gm.circle(gm.p0, r, out="c")
"""


def manifest_of(compiled: str) -> str:
    """The `onpageload:v1` comment, or '' when the article has none."""
    _, sep, rest = compiled.partition("<!-- onpageload:v1")
    return rest.split("-->")[0].strip() if sep else ""


# ---------------------------------------------------------------------------
# The wire shape
# ---------------------------------------------------------------------------


def test_commands_are_harvested_and_leave_no_spans():
    out = compile_article(fence(BLOCK))
    assert manifest_of(out) == (
        '{"commands":["r = \\\\scalar 3","c = \\\\circle p0 r"]}'
    )
    # The scene itself contributes nothing to the document.
    body = out.split("<!-- onpageload:v1")[0]
    assert "\\circle" not in body
    assert "\\scalar" not in body


def test_article_without_a_block_is_unchanged():
    out = compile_article(fence("a = gm.point(3, 0)"))
    assert "onpageload:v1" not in out


def test_block_may_sit_beside_ordinary_commands():
    code = BLOCK + "gm.point(1, 1, out='p')\n"
    out = compile_article(fence(code))
    assert "{}(p = \\point 1 1)" in out
    assert '"c = \\\\circle p0 r"' in manifest_of(out)


def test_all_three_manifests_coexist():
    code = BLOCK + """\
t = gm.annotate_text_box("click me", 2, 3, out="t")
with gm.ui.onclick(t):
    gm.point(2, 3, out="q")
gm.tex("f").frac.num.bind(gm.scalar(2, out="b"))
"""
    out = compile_article(fence(code))
    # The reader strips trailing manifests in a loop, so order is not
    # load-bearing — but all three must survive together.
    assert "<!-- texatlas:v1" in out
    assert "<!-- onclick:v1" in out
    assert "<!-- onpageload:v1" in out


# ---------------------------------------------------------------------------
# What the block makes possible
# ---------------------------------------------------------------------------


def test_document_may_consume_a_node_the_block_defined():
    """The point of the feature: the block has already run at read time, so a
    span may build on it. The round-trip gate is seeded with its lines."""
    code = BLOCK + "gm.translate(gm.node('c'), 2, 0)\n"
    out = compile_article(fence(code))
    assert "{}(\\translate c 2 0)" in out


def test_a_control_created_in_the_block_still_renders():
    code = BLOCK + "gm.md(f'Drag to resize: {r}')\n"
    out = compile_article(fence(code))
    assert 'class="nova-ui" data-kind="slider" data-node="r"' in out


def test_block_nodes_remain_registered_for_when():
    code = """\
with gm.onpageload():
    show = gm.ui.checkbox(False, label="Show the proof")
with when(show):
    gm.md("Because $ab=ba$, the map commutes.")
"""
    out = compile_article(fence(code))
    assert 'class="nova-when"' in out
    assert '"commands":["show = \\\\bool 0"]' in manifest_of(out)


def test_onclick_nests_inside_the_block():
    """Something clickable, on screen from the start. The handler's commands
    leave the tape first; the block captures what remains around it."""
    code = """\
with gm.onpageload():
    t = gm.annotate_text_box("what happens here?", 2, 3, out="t")
    with gm.ui.onclick(t):
        gm.point(2, 3, out="p")
    gm.circle(gm.p0, 1, out="c")
"""
    out = compile_article(fence(code))
    # The block keeps the box and the circle; the handler keeps only its own.
    assert manifest_of(out) == (
        '{"commands":["text-0 = \\\\text \\"what happens here?\\"",'
        '"t = \\\\annotate-text-box text-0 2 3","c = \\\\circle p0 1"]}'
    )
    assert '<!-- onclick:v1\n{"t":{"commands":["p = \\\\point 2 3"]}}' in out
    # Neither slice reaches the document.
    body = out.split("<!-- onclick:v1")[0]
    assert "\\point 2 3" not in body
    assert "\\annotate-text-box" not in body


def test_a_handler_inside_the_block_may_target_a_node_the_block_defines():
    """The target is created at load, which is when the canvas needs it to make
    the node clickable — so this is the ordinary case, not a violation."""
    code = """\
with gm.onpageload():
    t = gm.annotate_text_box("a", 0, 0, out="t")
    with gm.ui.onclick(t):
        gm.circle(gm.p0, 4, out="big")
"""
    out = compile_article(fence(code))
    assert '"t":{"commands":["big = \\\\circle p0 4"]}' in out


def test_a_block_emptied_by_its_handler_raises():
    """If the handler takes every command, the block itself recorded nothing."""
    code = """\
with gm.onpageload():
    with gm.ui.onclick(gm.p0):
        gm.point(1, 1, out="p")
"""
    with pytest.raises(ArticleError, match="recorded no commands"):
        compile_article(fence(code))


def test_fusion_barrier_at_the_closing_edge():
    """An anonymous `\\add` left at the end of the block must not be absorbed by
    the first main-tape command after it."""
    code = """\
with gm.onpageload():
    a = gm.scalar(1)
    b = gm.scalar(2)
    a + b
c = gm.scalar(3)
gm.add(gm.node('num-0'), c, out='total')
"""
    out = compile_article(fence(code))
    assert '"num-0 = \\\\add a b"' in manifest_of(out)
    assert "{}(total = \\add num-0 c)" in out


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_outside_an_article_raises():
    with gm.Store():
        with pytest.raises(PageLoadError, match="only usable inside the FIRST"):
            with gm.onpageload():
                gm.point(1, 1)


def test_after_another_command_raises():
    code = "gm.point(1, 1)\n" + BLOCK
    with pytest.raises(ArticleError, match="must come before any other command"):
        compile_article(fence(code))


def test_in_a_later_fence_raises():
    doc = fence("a = gm.point(3, 0)") + "\nprose\n\n" + fence(BLOCK)
    with pytest.raises(ArticleError, match="only usable inside the FIRST"):
        compile_article(doc)


def test_in_a_later_fence_raises_even_when_the_first_recorded_nothing():
    """The rule is positional, not "nothing has been recorded yet": an author
    who splits their setup across fences must still open the block in the
    first one."""
    doc = fence("RADIUS = 3") + "\nprose\n\n" + fence(BLOCK)
    with pytest.raises(ArticleError, match="only usable inside the FIRST"):
        compile_article(doc)


def test_second_block_raises():
    code = BLOCK + "with gm.onpageload():\n    gm.point(1, 1)\n"
    with pytest.raises(ArticleError, match="at most one gm.onpageload"):
        compile_article(fence(code))


def test_empty_body_raises():
    code = "with gm.onpageload():\n    pass\n"
    with pytest.raises(ArticleError, match="recorded no commands"):
        compile_article(fence(code))


def test_nesting_raises():
    code = """\
with gm.onpageload():
    gm.point(1, 1)
    with gm.onpageload():
        gm.point(2, 2)
"""
    with pytest.raises(ArticleError, match="do not nest"):
        compile_article(fence(code))


def test_block_inside_onclick_raises():
    code = """\
t = gm.annotate_text_box("a", 0, 0, out="t")
with gm.ui.onclick(t):
    with gm.onpageload():
        gm.point(1, 1)
"""
    with pytest.raises(ArticleError, match="opened inside the gm.ui.onclick block"):
        compile_article(fence(code))


def test_group_inside_the_block_raises():
    code = """\
with gm.onpageload():
    with group('g'):
        gm.point(1, 1, out='p')
"""
    with pytest.raises(ArticleError, match="opened inside the gm.onpageload block"):
        compile_article(fence(code))


def test_inline_span_cannot_open_a_block():
    doc = "Text {label}(with gm.onpageload(): gm.point(1, 1))\n"
    with pytest.raises(ArticleError):
        compile_article(doc)
