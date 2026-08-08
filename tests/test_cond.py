"""Tests for cond.py and gm.when — conditional markdown."""

import html
import json
import re

import pytest

import pygeomatic as gm
from pygeomatic import ArticleError, CondError, compile_article
from pygeomatic.cond import evaluate, node_refs


def fence(code: str) -> str:
    return f"```pygeomatic\n{code}\n```\n"


def when_payload(compiled: str, nth: int = 0) -> dict:
    """The decoded condition of the nth gm.when block in a compiled article."""
    blocks = re.findall(r"data-when='([^']*)'", compiled)
    return json.loads(html.unescape(blocks[nth]))


# ---------------------------------------------------------------------------
# Building conditions
# ---------------------------------------------------------------------------


def test_comparison_payload_shape():
    with gm.Store():
        k = gm.scalar(0)
        assert gm.cond.ge(k, 2).payload == {
            "op": "ge",
            "a": {"node": "k"},
            "b": {"const": 2.0},
        }


def test_operators_combine_conditions():
    with gm.Store():
        k = gm.scalar(0)
        b = gm.bool_(True)
        combined = gm.cond.ge(k, 2) & ~gm.cond.eq(b, True)
        assert combined.payload["op"] == "and"
        assert combined.payload["b"]["op"] == "not"


def test_all_and_any_fold_left():
    with gm.Store():
        k = gm.scalar(0)
        folded = gm.cond.all_(gm.cond.ge(k, 1), gm.cond.ge(k, 2), gm.cond.ge(k, 3))
        assert folded.payload["op"] == "and"
        assert folded.payload["a"]["op"] == "and"


def test_text_can_be_compared_for_equality_only():
    with gm.Store():
        mode = gm.text("sum")
        assert gm.cond.eq(mode, "sum").payload["b"] == {"const": "sum"}
        with pytest.raises(CondError, match="orders numbers"):
            gm.cond.ge(mode, "sum")


def test_a_condition_cannot_be_used_in_a_python_if():
    """The failure mode this guards against is silent: a condition object is
    always truthy, so `if cond:` would take the same branch every time."""
    with gm.Store():
        k = gm.scalar(0)
        with pytest.raises(CondError, match="cannot be used in a python `if`"):
            bool(gm.cond.ge(k, 2))


def test_when_rejects_an_ungateable_node():
    with gm.Store():
        p = gm.point(1, 2)
        with pytest.raises(CondError, match="cannot be a gate on its own"):
            gm.cond.to_payload(p)


# ---------------------------------------------------------------------------
# Evaluation (this mirrors predicate.ts — the two must agree)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload, values, expected",
    [
        ({"node": "show"}, {"show": True}, True),
        ({"node": "show"}, {"show": False}, False),
        ({"node": "k"}, {"k": 2.0}, True),
        ({"node": "k"}, {"k": 0.0}, False),
        ({"node": "missing"}, {}, False),
        ({"op": "ge", "a": {"node": "k"}, "b": {"const": 2}}, {"k": 2}, True),
        ({"op": "ge", "a": {"node": "k"}, "b": {"const": 2}}, {"k": 1}, False),
        ({"op": "lt", "a": {"node": "k"}, "b": {"const": 2}}, {"k": 1}, True),
        ({"op": "eq", "a": {"node": "m"}, "b": {"const": "sum"}}, {"m": "sum"}, True),
        ({"op": "ne", "a": {"node": "m"}, "b": {"const": "sum"}}, {"m": "prod"}, True),
        # An unknown node makes an ordering false, never true.
        ({"op": "ge", "a": {"node": "k"}, "b": {"const": 2}}, {}, False),
    ],
)
def test_evaluate(payload, values, expected):
    assert evaluate(payload, values) is expected


def test_node_refs_ignores_constants():
    payload = {
        "op": "and",
        "a": {"op": "ge", "a": {"node": "k"}, "b": {"const": 2}},
        "b": {"node": "show"},
    }
    assert node_refs(payload, set()) == {"k", "show"}


# ---------------------------------------------------------------------------
# gm.when in an article
# ---------------------------------------------------------------------------


def test_when_wraps_its_markdown_in_a_gated_block():
    compiled = compile_article(
        fence('show = gm.ui.checkbox(True)\nwith when(show):\n    gm.md("Secret.")')
    )
    assert '<div class="nova-when"' in compiled
    assert "Secret." in compiled
    assert when_payload(compiled) == {"node": "show"}


def test_a_block_true_at_compile_time_starts_visible():
    compiled = compile_article(
        fence('show = gm.ui.checkbox(True)\nwith when(show):\n    gm.md("Shown.")')
    )
    assert "display:none" not in compiled


def test_a_block_false_at_compile_time_starts_hidden():
    """Otherwise it flashes on screen before the browser's watcher runs."""
    compiled = compile_article(
        fence('show = gm.ui.checkbox(False)\nwith when(show):\n    gm.md("Hidden.")')
    )
    assert 'style="display:none"' in compiled


def test_blank_lines_surround_the_body():
    """Markdown stops treating a block as raw HTML at a blank line; without
    these the prose inside would not be formatted."""
    compiled = compile_article(
        fence('show = gm.ui.checkbox(True)\nwith when(show):\n    gm.md("**bold**")')
    )
    assert ">\n\n**bold**\n\n</div>" in compiled


def test_commands_inside_a_when_block_still_reach_the_tape():
    """Hiding prose must never silently change the scene."""
    compiled = compile_article(
        fence(
            'show = gm.ui.checkbox(False)\n'
            "with when(show):\n"
            "    c = gm.circle(gm.p0, 2)\n"
            '    gm.md("Note.")'
        )
    )
    assert "c = \\circle p0 2" in compiled


def test_nested_when_blocks():
    compiled = compile_article(
        fence(
            "a = gm.ui.checkbox(True)\n"
            "b = gm.ui.checkbox(True)\n"
            "with when(a):\n"
            "    with when(b):\n"
            '        gm.md("Both.")'
        )
    )
    assert compiled.count('class="nova-when"') == 2
    assert "Both." in compiled


def test_when_with_no_markdown_is_an_error():
    with pytest.raises(ArticleError, match="produced no markdown"):
        compile_article(
            fence('show = gm.ui.checkbox(True)\nwith when(show):\n    gm.scalar(1)')
        )


def test_when_outside_an_article_is_an_error():
    with gm.Store():
        b = gm.bool_(True)
        with pytest.raises(ArticleError, match="only usable inside"):
            with gm.when(b):
                pass


def test_condition_json_survives_the_attribute_round_trip():
    compiled = compile_article(
        fence(
            'k = gm.ui.slider(0, 4, step=1, value=0)\n'
            "with when(gm.cond.ge(k, 2)):\n"
            '    gm.md("Later.")'
        )
    )
    assert when_payload(compiled) == {
        "op": "ge",
        "a": {"node": "k"},
        "b": {"const": 2.0},
    }
