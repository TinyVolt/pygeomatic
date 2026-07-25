"""Lint the KaTeX math in an article, catching the two failure modes that only
surface when the browser renders the formula (never at compile time otherwise):

1. **Undefined control sequence** — e.g. `\\emerald{x}` when the palette has no
   `\\emerald`. KaTeX renders the command name as literal red text and spills its
   argument unstyled. We flag any `\\name` that is neither a KaTeX built-in
   (`katex_commands.json`, a self-contained copy of the pinned KaTeX's command
   set) nor one of the custom color macros the renderer registers (`COLOR_MACROS`
   below), nor a command the formula defines itself (`\\def` / `\\newcommand`).

2. **The `#`-hex color footgun** — `\\textcolor{#10B981}` / `\\amber{#...}`. Inside
   these macros KaTeX reads `#`+digit as a parameter reference and corrupts the
   color. The palette hexes carry no leading `#`; a bare `#` in article math is
   almost always this mistake (macro-defining formulas, the only legitimate use
   of `#`, are exempted).

Pure string scanning — no LaTeX parse tree — so it stays lightweight and honours
the project rule that Python never parses LaTeX semantically.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# The custom color-macro palette the article's KaTeX renderer registers: each
# name expands to `\textcolor{<hex>}` (hex has NO leading `#` — see the footgun
# note below). This dict is the canonical, self-contained copy of that palette;
# the linter treats these names as defined so authors may use them in prose math.
COLOR_MACROS: dict[str, str] = {
    "\\grey": "71717a",
    "\\amber": "fbbf24",
    "\\rose": "fb7185",
    "\\zinc": "e4e4e7",
    "\\white": "dddddd",
    "\\fuchsia": "E879F9",
    "\\blue": "6aa8ff",
    "\\lightblue": "93c5fd",
    "\\violet": "B9A4FC",
    "\\pink": "F472B6",
    "\\lavender": "a988f5",
    "\\orange": "F97316",
    "\\green": "10B981",
    "\\lime": "84CC16",
    "\\red": "F87171",
    "\\cyan": "22D3EE",
    "\\yellow": "f0e080",
    "\\teal": "41dbc9",
}


def _load_katex_commands() -> frozenset[str]:
    path = Path(__file__).with_name("katex_commands.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return frozenset("\\" + name for name in data["commands"])


KATEX_COMMANDS: frozenset[str] = _load_katex_commands()
_KNOWN: frozenset[str] = KATEX_COMMANDS | frozenset(COLOR_MACROS)

# A used control word: backslash + letters (KaTeX control words are letters
# only; `\,` `\!` `\\` and other control symbols are spacing/escapes, not
# candidates for an "undefined macro").
_CMD_RE = re.compile(r"\\([a-zA-Z]+)")

# Commands that DEFINE a new macro; their first `\name` argument becomes valid.
_DEF_RE = re.compile(
    r"\\(?:re)?newcommand\s*\{?\s*(\\[a-zA-Z]+)"
    r"|\\(?:g|e|x)?def\s*(\\[a-zA-Z]+)"
    r"|\\let\s*(\\[a-zA-Z]+)"
)
_DEFINES_MACRO_RE = re.compile(r"\\(?:(?:re)?newcommand|(?:g|e|x)?def|let)\b")


def _locally_defined(latex: str) -> set[str]:
    out: set[str] = set()
    for m in _DEF_RE.finditer(latex):
        out.add(next(g for g in m.groups() if g))
    return out


def lint_latex(latex: str) -> list[str]:
    """Return a list of human-readable problems in one `$…$`/`$$…$$` body
    (empty if clean). The caller attaches location/line context."""
    problems: list[str] = []
    allowed = _KNOWN | _locally_defined(latex)

    seen: set[str] = set()
    for m in _CMD_RE.finditer(latex):
        cmd = "\\" + m.group(1)
        if cmd in allowed or cmd in seen:
            continue
        seen.add(cmd)
        problems.append(
            f"unknown LaTeX command {cmd!r}: not a KaTeX built-in, a color macro "
            f"({', '.join(sorted(COLOR_MACROS))}), or defined in the formula"
        )

    # The `#`-hex color footgun. `\#` is a literal hash (fine); a real macro
    # definition is the only place `#`-params belong, so exempt those formulas.
    if not _DEFINES_MACRO_RE.search(latex):
        for m in re.finditer(r"#", latex):
            if m.start() == 0 or latex[m.start() - 1] != "\\":
                problems.append(
                    "raw '#' in math: color macros take a bare 6-digit hex with "
                    "NO leading '#' (e.g. \\textcolor{10B981}); a '#' is read as a "
                    "KaTeX parameter and corrupts the color"
                )
                break

    return problems
