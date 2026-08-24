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


def test_numeric_choice_records_a_scalar():
    """An all-number list makes a Scalar node, like a plain gm.scalar — the
    control adds no DSL of its own."""
    with gm.Store() as s:
        pick = gm.ui.radio([1, 2, 3], 2)
    assert gm.emit(s).splitlines() == ["pick = \\scalar 2"]
    assert s.ui_widgets["pick"]["kind"] == "radio"


def test_numeric_choice_dsl_matches_a_plain_scalar():
    """Presentation only: a numeric choice must emit exactly the plain scalar."""
    with gm.Store() as with_ui:
        pick = gm.ui.dropdown([1, 2, 3], 2)  # noqa: F841 — named for the DSL
    with gm.Store() as without_ui:
        pick = gm.scalar(2)  # noqa: F841 — same name so the DSL matches
    assert gm.emit(with_ui) == gm.emit(without_ui)


def test_string_choice_still_records_text():
    """Regression: an all-string list keeps the Text behaviour."""
    with gm.Store() as s:
        mode = gm.ui.radio(["a", "b"])  # noqa: F841
    assert gm.emit(s).splitlines() == ['mode = \\text "a"']


def test_numeric_choice_html_carries_number_options():
    with gm.Store():
        pick = gm.ui.radio([1, 2, 3], 2, label="sides")
        markup = f"{pick}"
    assert 'data-kind="radio"' in markup
    assert attr(markup, "options") == [1.0, 2.0, 3.0]
    assert attr(markup, "initial-value") == 2.0
    assert attr(markup, "label") == "sides"


@pytest.mark.parametrize(
    "call, message",
    [
        (lambda: gm.ui.checkbox(1), "must be True or False"),
        (lambda: gm.ui.dropdown([]), "non-empty list"),
        (lambda: gm.ui.dropdown([1, "a"]), "all strings or all numbers"),
        (lambda: gm.ui.dropdown([True, False]), "all strings or all numbers"),
        (lambda: gm.ui.dropdown(["a", "a"]), "must be distinct"),
        (lambda: gm.ui.radio([1, 1]), "must be distinct"),
        (lambda: gm.ui.dropdown(["a"], value="z"), "not one of the options"),
        (lambda: gm.ui.radio(["a"], value="z"), "not one of the options"),
        (lambda: gm.ui.radio([1, 2], value=9), "not one of the options"),
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


def test_non_value_node_formats_to_its_id():
    """A Circle has no value to print, so it stays an id."""
    with gm.Store():
        c = gm.circle(gm.p0, 2)
        assert f"{c}" == c.id


@pytest.mark.parametrize(
    "build",
    [
        lambda: gm.scalar(2),
        lambda: gm.text("hello"),
        lambda: gm.gt(gm.scalar(2), gm.scalar(1)),
    ],
    ids=["Scalar", "Text", "Bool"],
)
def test_value_node_formats_to_a_readout(build):
    with gm.Store():
        node = build()
        markup = f"{node}"
    assert markup.startswith('<span class="nova-ui"')
    assert 'data-kind="readout"' in markup
    assert f'data-node="{node.id}"' in markup
    assert "data-fmt=" not in markup


def test_readout_carries_the_format_spec():
    with gm.Store():
        x = gm.scalar(2)
        assert attr(f"{x:.2f}", "fmt") == ".2f"
        assert attr(f"{x:d}", "fmt") == "d"
        assert attr(f"{x:.1%}", "fmt") == ".1%"


def test_readout_rejects_a_format_outside_the_gm_tex_grammar():
    with gm.Store():
        x = gm.scalar(2)
        with pytest.raises(UIError, match="invalid format"):
            f"{x:%.2f}"


def test_a_format_on_a_non_value_node_is_an_error():
    """Silently printing the id would look like the format was applied."""
    with gm.Store():
        c = gm.circle(gm.p0, 2)
        with pytest.raises(UIError, match="number format"):
            f"{c:.2f}"


def test_a_format_asks_for_the_value_of_a_control_node():
    """`{r}` is the slider; `{r:d}` is its number, so both can share a page."""
    with gm.Store():
        r = gm.ui.slider(1, 5, value=3, label="radius")
        assert 'data-kind="slider"' in f"{r}"
        assert 'data-kind="readout"' in f"{r:d}"


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
# Readouts in canvas text
# ---------------------------------------------------------------------------


def test_an_f_string_in_canvas_text_becomes_the_canvas_interpolation():
    """The canvas draws plain text, so a span there would be painted as markup.
    `${x}` is the canvas's own live interpolation and means the same thing."""
    with gm.Store() as a:
        x = gm.scalar(2)
        gm.text(f"scale = {x}", out="t")
    with gm.Store() as b:
        x = gm.scalar(2)
        gm.text("scale = ${x}", out="t")
    assert gm.emit(a) == gm.emit(b)
    assert 't = \\text "scale = ${x}"' in gm.emit(a)


def test_a_control_in_canvas_text_is_rewritten_too():
    with gm.Store() as s:
        r = gm.ui.slider(1, 5, value=3, label="radius")
        gm.text(f"r = {r}", out="t")
    assert 't = \\text "r = ${r}"' in gm.emit(s)


def test_an_implicit_text_argument_is_rewritten():
    """Not just gm.text: every string reaching a Text parameter goes through
    the same resolution step."""
    with gm.Store() as s:
        x = gm.scalar(2)
        gm.annotate_text_box(f"x = {x}", 0, 0, 14, out="box")
    assert 'text-0 = \\text "x = ${x}"' in gm.emit(s)


def test_the_canvas_drops_a_number_format():
    """`${}` has no format spec; the canvas prints integers plain, else 2 dp."""
    with gm.Store() as s:
        x = gm.scalar(2)
        gm.text(f"x = {x:.1%}", out="t")
    assert 't = \\text "x = ${x}"' in gm.emit(s)


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
