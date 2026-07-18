"""Tests for article.py — pygeomatic-in-markdown → CommandLink article."""

import subprocess
import sys
from pathlib import Path

import pytest

import pygeomatic as gm
from pygeomatic import ArticleError, article_mode, compile_article, run_article

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fence(code: str) -> str:
    return f"```pygeomatic\n{code}\n```\n"


# ---------------------------------------------------------------------------
# article_mode / gm.node
# ---------------------------------------------------------------------------


def test_article_mode_allows_explicit_reassignment():
    with gm.Store() as s, article_mode():
        gm.scalar(1, out="s1")
        gm.scalar(0.5, out="s1")
    assert gm.emit(s).splitlines() == ["s1 = \\scalar 1", "s1 = \\scalar 0.5"]


def test_explicit_reassignment_still_rejected_outside_article_mode():
    with gm.Store():
        gm.scalar(1, out="s1")
        with pytest.raises(ValueError, match="already exists"):
            gm.scalar(0.5, out="s1")


def test_article_mode_allows_inferred_reassignment():
    with gm.Store() as s, article_mode():
        exec("s1 = gm.scalar(1)\ns1 = gm.scalar(2)", {"gm": gm})
    assert gm.emit(s).splitlines() == ["s1 = \\scalar 1", "s1 = \\scalar 2"]


def test_node_returns_system_default():
    with gm.Store():
        origin = gm.node("p0")
        assert origin.type == "Point"
        line = gm.line(origin, gm.point(2, 2))
        assert line.type == "Line"


def test_node_unknown_id_raises():
    with gm.Store():
        with pytest.raises(KeyError, match="no node 'nope'"):
            gm.node("nope")


# ---------------------------------------------------------------------------
# Compilation: fences, groups, inline spans
# ---------------------------------------------------------------------------


def test_fence_becomes_hidden_spans():
    md = fence("a = gm.point(3, 0)\ngm.hide(a)")
    out = compile_article(md)
    assert out == "{}(a = \\point 3 0)\n{}(\\hide a)\n"


def test_group_ref_expands_hidden_then_visible():
    md = fence(
        "a = gm.point(3, 0)\n"
        "with group('walk'):\n"
        "    gm.highlight(a)\n"
        "    gm.show(a)\n"
    ) + "Click {here}(ref:walk) to walk.\n"
    out = compile_article(md)
    assert "{}(a = \\point 3 0)\n" in out
    assert "Click {}(\\highlight a) {here}(\\show a) to walk." in out


def test_ref_with_empty_label_is_all_hidden():
    md = fence("with group('g'):\n    a = gm.point(1, 1)\n    gm.hide(a)") + "{}(ref:g) done\n"
    out = compile_article(md)
    assert "{}(a = \\point 1 1) {}(\\hide a) done" in out


def test_state_and_autonames_flow_across_fences():
    md = (
        fence("a = gm.point(1, 0)\ngm.point(2, 0)")
        + "middle prose\n"
        + fence("b = gm.point(0, 1)\nc = gm.mid_point(a, b)\ngm.point(3, 3)")
    )
    out = compile_article(md)
    # The second fence keeps using `a` and the auto-name counter continues.
    assert "{}(c = \\mid-point a b)" in out
    assert "{}(p-0 = \\point 2 0)" in out
    assert "{}(p-1 = \\point 3 3)" in out


def test_inline_span_compiles_to_one_dsl_span():
    md = fence("s1 = gm.scalar(1)") + "{reset to 1}(s1 = gm.scalar(1))\n"
    out = compile_article(md)
    assert "{reset to 1}(s1 = \\scalar 1)" in out


def test_inline_span_implicit_text_becomes_hidden_prefix():
    md = "{label it}(tb = gm.annotate_text_box('hi', -2, 2, 12))\n"
    out = compile_article(md)
    assert (
        '{}(text-0 = \\text "hi") {label it}(tb = \\annotate-text-box text-0 -2 2 12)'
        in out
    )


def test_hidden_inline_span():
    md = "{}(a = gm.point(1, 2))\n"
    out = compile_article(md)
    assert out == "{}(a = \\point 1 2)\n"


def test_math_regions_are_not_scanned():
    md = "The angle $\\theta = \\tan^{-1}(y / x)$ is fixed.\n"
    assert compile_article(md) == md


def test_non_pygeomatic_fences_pass_through_unscanned():
    md = "```python\ndef f(x):\n    return {x}(x)\n```\n"
    assert compile_article(md) == md


def test_document_without_pygeomatic_is_unchanged():
    md = "# Title\n\nJust prose with a [link](https://example.com).\n"
    assert compile_article(md) == md


# ---------------------------------------------------------------------------
# Strictness errors
# ---------------------------------------------------------------------------


def test_unknown_group_ref():
    md = fence("with group('g'):\n    gm.point(1, 1)") + "{x}(ref:nope)\n"
    with pytest.raises(ArticleError, match="unknown group 'nope'"):
        compile_article(md)


def test_unreferenced_group():
    md = fence("with group('lonely'):\n    gm.point(1, 1)")
    with pytest.raises(ArticleError, match="never referenced: lonely"):
        compile_article(md)


def test_double_ref():
    md = fence("with group('g'):\n    gm.point(1, 1)") + "{a}(ref:g) {b}(ref:g)\n"
    with pytest.raises(ArticleError, match="already referenced"):
        compile_article(md)


def test_refs_out_of_execution_order():
    md = (
        fence(
            "with group('first'):\n    gm.point(1, 1)\n"
            "with group('second'):\n    gm.point(2, 2)\n"
        )
        + "{b}(ref:second) then {a}(ref:first)\n"
    )
    with pytest.raises(ArticleError, match="out of order"):
        compile_article(md)


def test_ref_before_defining_fence():
    md = "{x}(ref:g)\n" + fence("with group('g'):\n    gm.point(1, 1)")
    with pytest.raises(ArticleError, match="before the block defining it"):
        compile_article(md)


def test_empty_group():
    md = fence("with group('g'):\n    pass") + "{x}(ref:g)\n"
    with pytest.raises(ArticleError, match="recorded no commands"):
        compile_article(md)


def test_nested_group():
    md = fence(
        "with group('outer'):\n"
        "    gm.point(1, 1)\n"
        "    with group('inner'):\n"
        "        gm.point(2, 2)\n"
    )
    with pytest.raises(ArticleError, match="opened inside"):
        compile_article(md)


def test_duplicate_group_name():
    md = fence(
        "with group('g'):\n    gm.point(1, 1)\nwith group('g'):\n    gm.point(2, 2)\n"
    )
    with pytest.raises(ArticleError, match="duplicate group name"):
        compile_article(md)


def test_group_in_inline_span_rejected():
    md = "{x}(with group('g'): gm.point(1, 1))\n"
    with pytest.raises(ArticleError, match="not allowed in an inline span"):
        compile_article(md)


def test_inline_span_syntax_error():
    md = "{x}(= 3)\n"
    with pytest.raises(ArticleError, match="line 1: syntax error"):
        compile_article(md)


def test_inline_span_recording_nothing():
    md = "{x}(x = 1 + 1)\n"
    with pytest.raises(ArticleError, match="recorded no commands"):
        compile_article(md)


def test_unclosed_fence():
    with pytest.raises(ArticleError, match="unclosed"):
        compile_article("```pygeomatic\ngm.point(1, 1)\n")


def test_author_error_reports_article_line():
    md = "line one\n\n" + fence("a = gm.point(1, 1)\nb = gm.undefined_fn(a)")
    with pytest.raises(ArticleError, match="line 5: AttributeError"):
        compile_article(md)


def test_round_trip_catches_document_order_violation():
    # The group's output is consumed by UNGROUPED code after it in the fence:
    # the tape is fine, but in the compiled document the consumer's hidden
    # span comes before the ref that defines `p` — define-before-use breaks.
    md = (
        fence("with group('mk'):\n    p = gm.point(1, 1)\nc = gm.circle(p, 2)")
        + "reveal {the point}(ref:mk)\n"
    )
    with pytest.raises(ArticleError, match="round-trip"):
        compile_article(md)


# ---------------------------------------------------------------------------
# End-to-end: a §2.1-style article through compile_article and the CLI
# ---------------------------------------------------------------------------

SPACEWALK_STYLE = """\
## 2.1 A vector is a point in space

```pygeomatic
origin = gm.node("p0")
a = gm.point(3, 0)
b = gm.point(3, 2)
walk_x_line = gm.line(origin, a)
```

```pygeomatic
gm.hide(a, b, walk_x_line)
t1 = gm.text("move 3 units")

with group("the-point"):
    vec = gm.line(origin, b)

with group("walk-x"):
    gm.highlight(walk_x_line)
    gm.annotate_curly_bracket(origin, a, t1)
    gm.show(walk_x_line)
```

We represent $[3,2]$ (with angle $\\tan^{-1}(y / x)$) as {the point}(ref:the-point), reached by:
- {moving a distance}(ref:walk-x) of $3$ units.
- {reset scale}(s1 = gm.scalar(1)) then {halve it}(s1 = gm.scalar(0.5)).
"""


def test_spacewalk_style_article():
    out = compile_article(SPACEWALK_STYLE)
    assert "{}(a = \\point 3 0)" in out
    assert "{}(walk-x-line = \\line p0 a)" in out  # underscores → dashes
    assert "{the point}(vec = \\line p0 b)" in out
    assert (
        "{}(\\highlight walk-x-line) {}(brace-0 = \\annotate-curly-bracket p0 a t1) "
        "{moving a distance}(\\show walk-x-line)" in out
    )
    assert "{reset scale}(s1 = \\scalar 1)" in out
    assert "{halve it}(s1 = \\scalar 0.5)" in out
    assert "$\\tan^{-1}(y / x)$" in out  # math untouched
    assert "```" not in out  # no fences remain


def test_run_article_subprocess():
    result = run_article(SPACEWALK_STYLE)
    assert result.ok, result.error
    assert result.markdown == compile_article(SPACEWALK_STYLE)


def test_run_article_reports_errors():
    result = run_article("{x}(gm.no_such_thing())\n")
    assert not result.ok
    assert "AttributeError" in result.error


def test_cli_end_to_end(tmp_path: Path):
    src = tmp_path / "article.md"
    dst = tmp_path / "compiled.md"
    src.write_text(SPACEWALK_STYLE)
    script = Path(__file__).resolve().parents[1] / "scripts" / "compile_article.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(src), "-o", str(dst)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert dst.read_text() == compile_article(SPACEWALK_STYLE)


# ---------------------------------------------------------------------------
# Batch compiler (scripts/compile_articles.py — the CI gate)
# ---------------------------------------------------------------------------

BATCH_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compile_articles.py"


def run_batch(src: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BATCH_SCRIPT), str(src), str(out)],
        capture_output=True,
        text=True,
    )


def test_batch_compiles_tree_and_copies_assets(tmp_path: Path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    (src / "sub").mkdir(parents=True)
    (src / "good.md").write_text("{x}(a = gm.point(1, 2))\n")
    (src / "sub" / "plain.md").write_text("prose only\n")
    (src / "sub" / "figure.svg").write_text("<svg/>")
    proc = run_batch(src, out)
    assert proc.returncode == 0, proc.stderr
    assert (out / "good.md").read_text() == "{x}(a = \\point 1 2)\n"
    assert (out / "sub" / "plain.md").read_text() == "prose only\n"
    assert (out / "sub" / "figure.svg").read_text() == "<svg/>"


def test_batch_reports_every_failure_and_exits_nonzero(tmp_path: Path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    (src / "good.md").write_text("{x}(a = gm.point(1, 2))\n")
    (src / "bad.md").write_text("{x}(gm.no_such_fn())\n")
    (src / "worse.md").write_text("{x}(ref:missing)\n")
    proc = run_batch(src, out)
    assert proc.returncode == 1
    assert "FAILED bad.md" in proc.stderr
    assert "FAILED worse.md" in proc.stderr
    # Good articles are still compiled so authors see all errors in one run.
    assert (out / "good.md").exists()
    assert not (out / "bad.md").exists()
