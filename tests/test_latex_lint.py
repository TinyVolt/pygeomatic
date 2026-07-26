"""Tests for the article KaTeX linter (`latex_lint.py`) and its wiring into
`compile_article`. It catches the two mistakes that only surface at browser
render time: an undefined control sequence (`\\emerald`) and the `#`-hex color
footgun.
"""
import re
from pathlib import Path

import pytest

from pygeomatic.article import ArticleError, compile_article
from pygeomatic import latex_lint
from pygeomatic.latex_lint import COLOR_MACROS, KATEX_COMMANDS, lint_latex

# The committed, self-contained command table the linter loads (no external path).
_COMMANDS_JSON = Path(latex_lint.__file__).with_name("katex_commands.json")


# ---------------------------------------------------------------------------
# lint_latex — unknown commands
# ---------------------------------------------------------------------------


def test_flags_undefined_color_macro():
    (problem,) = lint_latex(r"\emerald{a_2 \cdot q_1}")
    assert "\\emerald" in problem and "unknown" in problem


def test_accepts_defined_color_macros_and_builtins():
    assert lint_latex(r"\amber{q_1} = \frac{1}{\lVert a_1 \rVert} + \sum_{i=1}^{n} x_i") == []


def test_accepts_matrix_and_common_structure():
    latex = r"A = \begin{pmatrix} 2 & 4 \\ 3 & 1 \end{pmatrix} \qquad \vec{v} \cdot \hat{n}"
    assert lint_latex(latex) == []


def test_control_symbols_not_flagged():
    # `\,` `\!` `\;` `\\` are spacing/escapes, never "undefined macros".
    assert lint_latex(r"a \, b \! c \; d \\ e") == []


def test_locally_defined_macro_is_allowed():
    assert lint_latex(r"\def\R{\mathbb{R}} x \in \R") == []
    assert lint_latex(r"\newcommand{\foo}{\alpha} \foo + \foo") == []


def test_only_reported_once_per_command():
    problems = lint_latex(r"\emerald{a} + \emerald{b}")
    assert len(problems) == 1


# ---------------------------------------------------------------------------
# lint_latex — the #-hex footgun
# ---------------------------------------------------------------------------


def test_flags_raw_hash_in_math():
    (problem,) = lint_latex(r"\textcolor{#10B981}{x}")
    assert "#" in problem


def test_escaped_hash_is_allowed():
    assert lint_latex(r"a \# b") == []


def test_hash_allowed_inside_macro_definition():
    # `#1` is a real parameter reference where a macro is defined.
    assert lint_latex(r"\newcommand{\sq}[1]{#1^2} \sq{x}") == []


# ---------------------------------------------------------------------------
# compile_article wiring — fails with a line number, before Python runs
# ---------------------------------------------------------------------------


def test_compile_article_rejects_unknown_macro_with_lineno():
    md = "Intro line.\n\nThe vector $\\emerald{v}$ appears here.\n"
    with pytest.raises(ArticleError) as exc:
        compile_article(md)
    assert exc.value.lineno == 3
    assert "\\emerald" in str(exc.value)


def test_compile_article_ignores_math_in_code_fences():
    # `$\emerald$` inside a non-pygeomatic fence is verbatim, not linted.
    md = "Text.\n\n```python\nx = r\"$\\emerald{v}$\"\n```\n\nDone.\n"
    compile_article(md)  # must not raise


def test_compile_article_allows_clean_math():
    md = "The norm $\\lVert a_1 \\rVert = \\sqrt{13}$ and $\\amber{q_1}$.\n"
    compile_article(md)  # must not raise


# ---------------------------------------------------------------------------
# katex_commands.json sanity + color palette parity
# ---------------------------------------------------------------------------


def test_katex_commands_table_is_self_contained_and_plausible():
    # The committed katex_commands.json is a self-contained copy — no external
    # path is read at import or test time. It should be a stable ~1000-command
    # table with the everyday structure commands present and \emerald absent.
    assert _COMMANDS_JSON.exists()
    assert len(KATEX_COMMANDS) > 800
    for cmd in ("\\frac", "\\sqrt", "\\underbrace", "\\textcolor", "\\begin", "\\cdot"):
        assert cmd in KATEX_COMMANDS
    assert "\\emerald" not in KATEX_COMMANDS


def test_color_macros_are_wellformed():
    """The palette is self-describing: every entry is a `\\name` with a bare
    6-digit hex (NO leading `#` — the footgun the linter guards against)."""
    assert len(COLOR_MACROS) == 18
    for name, hexv in COLOR_MACROS.items():
        assert name.startswith("\\") and name[1:].isalpha()
        assert re.fullmatch(r"[0-9a-fA-F]{6}", hexv), (name, hexv)
    # A couple of pinned entries so an accidental palette edit is caught.
    assert COLOR_MACROS["\\amber"] == "fbbf24"
    assert COLOR_MACROS["\\teal"] == "41dbc9"
    # \emerald was never part of the palette — that's the whole bug.
    assert "\\emerald" not in COLOR_MACROS
