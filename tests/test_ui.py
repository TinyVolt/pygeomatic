"""Tests for ui.py — gm.ui controls, their HTML, and gm.md article output."""

import html
import json
import re

import pytest

import pygeomatic as gm
from pygeomatic import ArticleError, UIError, compile_article
from pygeomatic.article import _scan_spans, _segment, _Prose


def fence(code: str) -> str:
    return f"```pygeomatic\n{code}\n```\n"


def attr(markup: str, name: str):
    """The decoded, JSON-parsed value of `data-<name>` — i.e. exactly what the
    browser gets after the HTML parser and JSON.parse have both run."""
    match = re.search(rf"data-{name}='([^']*)'", markup)
    assert match, f"no data-{name} in {markup!r}"
    # The HTML parser expands entities; `&#92;`/`&#36;` are ours, the rest are
    # standard and html.unescape covers them.
    decoded = html.unescape(match.group(1))
    decoded = decoded.replace("&#92;", "\\").replace("&#36;", "$")
    return json.loads(decoded)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def test_slider_records_a_plain_scalar_command():
    """The control adds no DSL of its own — the node is an ordinary scalar."""
    with gm.Store() as s:
        r = gm.ui.slider(1, 5, value=3)
        gm.circle(gm.p0, r)
    assert gm.emit(s).splitlines() == ["r = \\scalar 3", "circ-0 = \\circle p0 r"]


def test_slider_node_is_named_from_the_assignment():
    """The frame hop in inference.py: without it this node would be `num0`."""
    with gm.Store():
        my_radius = gm.ui.slider(1, 5)
        assert my_radius.id == "my-radius"


def test_slider_returns_a_usable_scalar():
    with gm.Store() as s:
        r = gm.ui.slider(1, 5, value=2)
        doubled = r * 2
    assert doubled.id == "doubled"
    assert "\\mul r 2" in gm.emit(s)


def test_widget_is_off_the_tape_but_on_the_store():
    with gm.Store() as s:
        r = gm.ui.slider(1, 5)
        assert s.ui_widgets[r.id]["kind"] == "slider"
    assert "nova-ui" not in gm.emit(s)


def test_two_controls_on_one_node_is_an_error():
    with gm.Store():
        r = gm.ui.slider(1, 5)
        with pytest.raises(UIError, match="already has a 'slider' control"):
            gm.ui._register(r, "slider", {})


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(start=5, stop=1), "stop > start"),
        (dict(start=1, stop=5, step=0), "step must be positive"),
        (dict(start=1, stop=5, step=99), "wider than the range"),
        (dict(start=1, stop=5, value=9), "outside the range"),
        (dict(start=1, stop=5, label=3), "label must be a string"),
    ],
)
def test_slider_rejects_bad_options(kwargs, message):
    with gm.Store():
        with pytest.raises(UIError, match=message):
            gm.ui.slider(**kwargs)


# ---------------------------------------------------------------------------
# The other controls
# ---------------------------------------------------------------------------


def test_each_control_records_its_own_node_type():
    with gm.Store() as s:
        r = gm.ui.slider(1, 5)
        show = gm.ui.checkbox(True)
        n = gm.ui.number(0, 10, value=4)
        mode = gm.ui.dropdown(["sum", "product"])
        pick = gm.ui.radio(["a", "b"])
        name = gm.ui.text("world")
    assert gm.emit(s).splitlines() == [
        "r = \\scalar 1",
        "show = \\bool 1",
        "n = \\scalar 4",
        'mode = \\text "sum"',
        'pick = \\text "a"',
        'name = \\text "world"',
    ]


def test_every_control_names_its_node_from_the_assignment():
    """dropdown/radio reach the recording call through a shared helper, one
    frame deeper than the rest — inference has to hop that too."""
    with gm.Store():
        a_slider = gm.ui.slider(1, 5)
        a_box = gm.ui.checkbox(True)
        a_number = gm.ui.number(0, 5)
        a_dropdown = gm.ui.dropdown(["x", "y"])
        a_radio = gm.ui.radio(["x", "y"])
        a_text = gm.ui.text("hi")
    assert [n.id for n in (a_slider, a_box, a_number, a_dropdown, a_radio, a_text)] == [
        "a-slider",
        "a-box",
        "a-number",
        "a-dropdown",
        "a-radio",
        "a-text",
    ]


def test_choice_defaults_to_the_first_option():
    with gm.Store():
        mode = gm.ui.dropdown(["sum", "product"])
        assert f"{mode}".count("sum") >= 1


@pytest.mark.parametrize(
    "call, message",
    [
        (lambda: gm.ui.checkbox(1), "must be True or False"),
        (lambda: gm.ui.dropdown([]), "non-empty list"),
        (lambda: gm.ui.dropdown([1, 2]), "must be strings"),
        (lambda: gm.ui.dropdown(["a", "a"]), "must be distinct"),
        (lambda: gm.ui.dropdown(["a"], value="z"), "not one of the options"),
        (lambda: gm.ui.radio(["a"], value="z"), "not one of the options"),
        (lambda: gm.ui.number(5, 1), "stop > start"),
        (lambda: gm.ui.number(0, 10, value=99), "above stop"),
        (lambda: gm.ui.number(0, 10, value=-1), "below start"),
        (lambda: gm.ui.text(42), "must be a string"),
    ],
)
def test_controls_reject_bad_options(call, message):
    with gm.Store():
        with pytest.raises(UIError, match=message):
            call()


# ---------------------------------------------------------------------------
# __format__
# ---------------------------------------------------------------------------


def test_plain_node_formats_to_its_id():
    with gm.Store():
        c = gm.circle(gm.p0, 2)
        assert f"{c}" == c.id


def test_widget_node_formats_to_its_html():
    with gm.Store():
        r = gm.ui.slider(1, 5, step=0.5, value=3, label="radius")
        markup = f"{r}"
    assert markup.startswith('<span class="nova-ui"')
    assert 'data-kind="slider"' in markup
    assert 'data-node="r"' in markup
    assert attr(markup, "start") == 1.0
    assert attr(markup, "stop") == 5.0
    assert attr(markup, "step") == 0.5
    assert attr(markup, "initial-value") == 3.0
    assert attr(markup, "label") == "radius"


def test_widget_html_is_one_line():
    """Multi-line HTML inside an indented gm.md() would render as a code block."""
    with gm.Store():
        r = gm.ui.slider(1, 5, label="radius")
        assert "\n" not in f"{r}"


def test_omitted_options_are_left_out_entirely():
    with gm.Store():
        r = gm.ui.slider(1, 5)
        markup = f"{r}"
    assert "data-step=" not in markup
    assert "data-label=" not in markup


def test_hostile_label_survives_the_round_trip():
    """Every character the escaping exists for, in one label."""
    nasty = 'radius $x$ <b>bold</b> & "quoted" \\ back'
    with gm.Store():
        r = gm.ui.slider(1, 5, label=nasty)
        markup = f"{r}"
    # Raw specials must not appear unescaped in the attribute value.
    value = re.search(r"data-label='([^']*)'", markup).group(1)
    for ch in ("<", ">", "$", "\\"):
        assert ch not in value, f"{ch!r} left unescaped in {value!r}"
    assert attr(markup, "label") == nasty


# ---------------------------------------------------------------------------
# The article-compiler safety property
# ---------------------------------------------------------------------------


def test_widget_html_does_not_disturb_the_command_scan():
    """A `$` in a label must not desynchronise the compiler's math skip.

    _scan_spans jumps over `$...$` regions; an unescaped `$` inside an
    attribute would open a phantom math region and swallow the command links
    after it. This is the whole reason `_attr` escapes `$`.
    """
    with gm.Store():
        r = gm.ui.slider(1, 5, label="cost $ per $ unit")
        markup = f"{r}"
    text = f"Before {{a}}(x = \\scalar 1) {markup} after {{b}}(y = \\scalar 2)\n"
    spans = _scan_spans(text)
    assert [s.content for s in spans] == ["x = \\scalar 1", "y = \\scalar 2"]


def test_commands_are_identical_with_and_without_controls():
    """Controls are presentation only: the DSL must not shift by one token."""
    with_ui = fence(
        'r = gm.ui.slider(1, 5, value=3, label="radius")\n'
        "c = gm.circle(gm.p0, r)\n"
        'gm.md(f"Drag: {r}")\n'
    )
    without_ui = fence("r = gm.scalar(3)\nc = gm.circle(gm.p0, r)\n")

    def commands(compiled: str) -> list[str]:
        return [
            s.content.strip()
            for part in _segment(compiled)
            if isinstance(part, _Prose) and part.scan
            for s in _scan_spans(part.text)
        ]

    assert commands(compile_article(with_ui)) == commands(compile_article(without_ui))


# ---------------------------------------------------------------------------
# gm.md
# ---------------------------------------------------------------------------


def test_md_text_lands_in_the_article():
    compiled = compile_article(fence('gm.md("Hello **world**.")'))
    assert "Hello **world**." in compiled


def test_md_follows_the_blocks_setup_commands():
    compiled = compile_article(
        fence('a = gm.scalar(1)\ngm.md("After the setup.")')
    )
    assert compiled.index("a = \\scalar 1") < compiled.index("After the setup.")


def test_md_calls_accumulate_in_order():
    compiled = compile_article(fence('gm.md("first")\ngm.md("second")'))
    assert compiled.index("first") < compiled.index("second")


def test_md_dedents_a_triple_quoted_string():
    """Indented prose must reach markdown flush-left, not as a code block."""
    compiled = compile_article(
        fence('def go():\n    gm.md("""\n        A paragraph.\n    """)\ngo()')
    )
    assert "\nA paragraph." in compiled


def test_md_outside_an_article_is_an_error():
    with gm.Store():
        with pytest.raises(ArticleError, match="only usable inside"):
            gm.md("nope")


def test_md_in_an_inline_span_is_an_error():
    with pytest.raises(ArticleError, match="not allowed in an inline span"):
        compile_article('{go}(gm.md("nope") or gm.scalar(1))\n')


def test_md_rejects_a_non_string():
    with pytest.raises(ArticleError, match="takes a string"):
        compile_article(fence("gm.md(42)"))


def test_article_without_md_is_unchanged():
    """The feature must be invisible to every existing article."""
    plain = fence("a = gm.scalar(1)")
    assert compile_article(plain) == "{}(a = \\scalar 1)\n"


def test_slider_reaches_the_compiled_article():
    compiled = compile_article(
        fence(
            'r = gm.ui.slider(1, 5, step=0.5, value=3, label="radius")\n'
            "c = gm.circle(gm.p0, r)\n"
            'gm.md(f"Drag to resize: {r}")\n'
        )
    )
    assert "{}(r = \\scalar 3)" in compiled
    assert 'data-kind="slider"' in compiled
    assert 'data-node="r"' in compiled
