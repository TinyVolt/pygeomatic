"""Compile a pygeomatic-in-markdown article into a geomatic CommandLink article.

Authors write prose in markdown and pygeomatic Python in two places:

- fenced ```pygeomatic blocks — real Python (loops, helpers, comments) run in
  document order against ONE shared store. Top-level code becomes hidden
  `{}(cmd)` setup spans where the fence sat; `with group("name"):` collects a
  named run of commands for prose to reveal.
- spans in prose — `{label}(ref:name)` expands a group (every command but the
  last as a hidden span, the last as the visible labeled span, so the reveal
  always lands on a fully set-up scene), and `{label}(python statement)` is an
  inline escape hatch for one-off commands (`{reset to 1}(s1 = gm.scalar(1))`).

`compile_article` replaces every fence and span with emitted DSL spans; the
result is exactly the `{label}(command)` article format used in markdowns. The span scanner extracts commands: brace/paren depth counters (labels may contain LaTeX
braces) and `$...$` / `$$...$$` math regions are skipped entirely, so a `}(`
adjacency inside math (e.g. `$\\tan^{-1}(y/x)$`) never becomes a span.

The compiled document is re-read span-by-span at read time, so its command
sequence must be executable in DOCUMENT order. A round-trip gate replays the
compiled spans through `parse_dsl` and compares the re-emitted lines, catching
define-before-use violations a ref reordering would introduce.

v1 strictness (each an ArticleError): unknown / unreferenced / doubly
referenced groups; refs out of document order relative to group execution
order (engine-internal auto-names like `arrow0` would diverge at read time);
a ref before its defining fence; empty or nested groups; duplicate group
names; `group()` inside an inline span; an inline span recording no command.
"""

from __future__ import annotations

import re
import subprocess
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional, Sequence, Union

from .coercions import allow_coercions
from .emit import emit, render_command
from .parse import DslParseError, parse_dsl
from .store import Store, _article_replay, current_store


class ArticleError(ValueError):
    """The article could not be compiled; `lineno` locates the cause (1-based)."""

    def __init__(self, lineno: Optional[int], message: str) -> None:
        self.lineno = lineno
        super().__init__(f"line {lineno}: {message}" if lineno else message)


# ---------------------------------------------------------------------------
# Article mode + group recording
# ---------------------------------------------------------------------------


@contextmanager
def article_mode():
    """Run pygeomatic calls with the engine's article semantics: an explicit or
    inferred output id may reassign an existing node (last-write-wins)."""
    token = _article_replay.set(True)
    try:
        yield
    finally:
        _article_replay.reset(token)


@dataclass
class _Group:
    name: str
    start: int  # tape slice [start:end)
    end: int


@dataclass
class _Recorder:
    groups: list[_Group] = field(default_factory=list)
    open: Optional[str] = None


_recorder: ContextVar[Optional[_Recorder]] = ContextVar(
    "pygeomatic_article_recorder", default=None
)

_GROUP_NAME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9-]*\Z")


@contextmanager
def group(name: str):
    """Collect the commands recorded in the block under `name`, for a prose
    `{label}(ref:name)` to reveal. Available inside article code only."""
    rec = _recorder.get()
    if rec is None:
        raise ArticleError(
            None, "group() is only usable inside a pygeomatic article block"
        )
    if not isinstance(name, str) or not _GROUP_NAME_RE.match(name):
        raise ArticleError(
            None,
            f"invalid group name {name!r}: must start with a letter and contain "
            "only letters, digits and dashes",
        )
    if rec.open is not None:
        raise ArticleError(None, f"group {name!r} opened inside group {rec.open!r}")
    if any(g.name == name for g in rec.groups):
        raise ArticleError(None, f"duplicate group name {name!r}")
    store = current_store()
    rec.open = name
    start = len(store.commands)
    try:
        yield
    finally:
        rec.open = None
    end = len(store.commands)
    if end == start:
        raise ArticleError(None, f"group {name!r} recorded no commands")
    rec.groups.append(_Group(name, start, end))


# ---------------------------------------------------------------------------
# Span scanner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Span:
    start: int  # offsets into the chunk text; end is just past the `)`
    end: int
    label: str
    content: str


def _parse_span_at(text: str, start: int) -> Optional[_Span]:
    """The balanced `{label}(content)` span anchored at `start`, or None."""
    n = len(text)
    if start >= n or text[start] != "{":
        return None
    depth = 0
    j = start
    while j < n:
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    if depth != 0:
        return None  # unterminated label
    open_ = j + 1
    if open_ >= n or text[open_] != "(":
        return None
    pdepth = 0
    m = open_
    while m < n:
        c = text[m]
        if c == "(":
            pdepth += 1
        elif c == ")":
            pdepth -= 1
            if pdepth == 0:
                break
        m += 1
    if pdepth != 0:
        return None  # unterminated content
    return _Span(start, m + 1, text[start + 1 : j], text[open_ + 1 : m])


_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n")


def _skip_math_at(text: str, start: int) -> Optional[int]:
    """Index past the `$...$` / `$$...$$` region at `start`, or None."""
    if start >= len(text) or text[start] != "$":
        return None
    is_block = text[start + 1 : start + 2] == "$"
    open_ = start + (2 if is_block else 1)
    close = text.find("$", open_)
    if close == -1 or close == open_:
        return None  # unterminated or empty
    if _BLANK_LINE_RE.search(text[open_:close]):
        return None  # inline content never crosses a block boundary
    if is_block:
        return close + 2 if text[close + 1 : close + 2] == "$" else None
    return close + 1


def _scan_spans(text: str) -> list[_Span]:
    """Every `{label}(content)` span in `text` in order, math regions skipped."""
    spans: list[_Span] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "$":
            i = _skip_math_at(text, i) or i + 1
            continue
        if c != "{":
            i += 1
            continue
        span = _parse_span_at(text, i)
        if span is None or not span.content.strip():
            i += 1
            continue
        spans.append(span)
        i = span.end
    return spans


# ---------------------------------------------------------------------------
# Markdown segmentation
# ---------------------------------------------------------------------------

_FENCE_OPEN_RE = re.compile(r"^```pygeomatic\s*$")
_FENCE_CLOSE_RE = re.compile(r"^```\s*$")
_OTHER_FENCE_RE = re.compile(r"^(```|~~~)")


@dataclass
class _Prose:
    lineno: int  # 1-based line of the chunk's first line
    text: str  # verbatim, newlines included
    # False for a non-pygeomatic code fence: copied through verbatim, its body
    # never scanned for spans (it may contain `{...}(...)`-shaped text).
    scan: bool = True


@dataclass
class _Fence:
    lineno: int  # 1-based line of the first CODE line
    text: str  # the whole fence, ``` lines included
    code: str


def _segment(markdown: str) -> list[Union[_Prose, _Fence]]:
    parts: list[Union[_Prose, _Fence]] = []
    lines = markdown.splitlines(keepends=True)
    prose: list[str] = []
    prose_lineno = 1
    i = 0
    while i < len(lines):
        stripped = lines[i].rstrip("\n")
        if _FENCE_OPEN_RE.match(stripped):
            if prose:
                parts.append(_Prose(prose_lineno, "".join(prose)))
                prose = []
            open_i = i
            i += 1
            code_start = i
            while i < len(lines) and not _FENCE_CLOSE_RE.match(lines[i].rstrip("\n")):
                i += 1
            if i == len(lines):
                raise ArticleError(open_i + 1, "unclosed ```pygeomatic fence")
            parts.append(
                _Fence(
                    lineno=code_start + 1,
                    text="".join(lines[open_i : i + 1]),
                    code="".join(lines[code_start:i]),
                )
            )
            i += 1
            prose_lineno = i + 1
        elif _OTHER_FENCE_RE.match(stripped):
            # A non-pygeomatic code fence: its own unscanned verbatim chunk.
            if prose:
                parts.append(_Prose(prose_lineno, "".join(prose)))
                prose = []
            closer = stripped[:3]
            block_start = i
            i += 1
            while i < len(lines) and not lines[i].rstrip("\n").startswith(closer):
                i += 1
            if i < len(lines):
                i += 1
            parts.append(
                _Prose(block_start + 1, "".join(lines[block_start:i]), scan=False)
            )
            prose_lineno = i + 1
        else:
            if not prose:
                prose_lineno = i + 1
            prose.append(lines[i])
            i += 1
    if prose:
        parts.append(_Prose(prose_lineno, "".join(prose)))
    return parts


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

_ARTICLE_FILENAME = "<article>"


@dataclass
class _Executable:
    """One unit of author Python in document order: a fence or an inline span."""

    kind: str  # "fence" | "inline"
    lineno: int
    code: str
    span: Optional[_Span] = None  # inline only
    start: int = -1  # tape slice [start:end) once executed
    end: int = -1


def _author_lineno(exc: BaseException, fallback: int) -> int:
    """The article line of the deepest frame in author code, for error reports."""
    tb = exc.__traceback__
    lineno = fallback
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == _ARTICLE_FILENAME:
            lineno = tb.tb_lineno
        tb = tb.tb_next
    return lineno


def _execute(executables: list[_Executable], allow: bool) -> tuple[Store, list[_Group]]:
    """Run the article's Python in one shared store; returns it and the groups."""
    import pygeomatic as gm  # the fully-initialized package, for the namespace

    namespace = {"gm": gm, "group": group}
    rec = _Recorder()
    rec_token = _recorder.set(rec)
    try:
        with Store() as store, article_mode(), allow_coercions(allow):
            for ex in executables:
                ex.start = len(store.commands)
                groups_before = len(rec.groups)
                # Pad so tracebacks and SyntaxErrors carry article line numbers.
                padded = "\n" * (ex.lineno - 1) + ex.code
                try:
                    exec(compile(padded, _ARTICLE_FILENAME, "exec"), namespace)
                except ArticleError as err:
                    if err.lineno is None:
                        raise ArticleError(_author_lineno(err, ex.lineno), str(err))
                    raise
                except SyntaxError as err:
                    raise ArticleError(
                        err.lineno or ex.lineno, f"syntax error: {err.msg}"
                    ) from err
                except Exception as err:
                    raise ArticleError(
                        _author_lineno(err, ex.lineno),
                        f"{type(err).__name__}: {err}",
                    ) from err
                ex.end = len(store.commands)
                if ex.kind == "inline":
                    if len(rec.groups) != groups_before:
                        raise ArticleError(
                            ex.lineno, "group() is not allowed in an inline span"
                        )
                    if ex.end == ex.start:
                        raise ArticleError(
                            ex.lineno,
                            f"inline span recorded no commands: {ex.code.strip()!r}",
                        )
        return store, rec.groups
    finally:
        _recorder.reset(rec_token)


def _render_spans(dsl_lines: Sequence[str], label: str) -> str:
    """Hidden `{}()` spans for all lines but the last; the label on the last."""
    label = label.strip()
    spans = [f"{{}}({line})" for line in dsl_lines[:-1]]
    spans.append(f"{{{label}}}({dsl_lines[-1]})" if label else f"{{}}({dsl_lines[-1]})")
    return " ".join(spans)


def compile_article(markdown: str, *, allow_coercions: bool = False) -> str:
    """Compile pygeomatic-in-markdown to a `{label}(command)` article.

    Runs the article's Python IN-PROCESS on a fresh store (extensions/macros
    must already be loaded); use `run_article` for a sandboxed subprocess run.
    """
    parts = _segment(markdown)

    # Document-order events: executables (fences, inline spans) and ref spans.
    executables: list[_Executable] = []
    # (prose part, span, lineno, executable-or-None) per span, document order.
    ref_events: list[tuple[_Prose, _Span, int, str]] = []
    span_render: dict[int, tuple[_Prose, _Span]] = {}  # executable idx → location
    doc_pos: dict[int, int] = {}  # executable idx → document event ordinal
    ref_pos: list[int] = []  # ref event ordinals, aligned with ref_events
    ordinal = 0
    for part in parts:
        if isinstance(part, _Fence):
            executables.append(_Executable("fence", part.lineno, part.code))
            doc_pos[len(executables) - 1] = ordinal
            ordinal += 1
            continue
        if not part.scan:
            continue
        for span in _scan_spans(part.text):
            lineno = part.lineno + part.text[: span.start].count("\n")
            content = span.content.strip()
            if content.startswith("ref:"):
                name = content[len("ref:") :].strip()
                if not _GROUP_NAME_RE.match(name):
                    raise ArticleError(lineno, f"invalid group reference {content!r}")
                ref_events.append((part, span, lineno, name))
                ref_pos.append(ordinal)
            else:
                executables.append(_Executable("inline", lineno, content, span=span))
                span_render[len(executables) - 1] = (part, span)
                doc_pos[len(executables) - 1] = ordinal
            ordinal += 1

    store, groups = _execute(executables, allow_coercions)
    dsl_lines = [render_command(cmd) for cmd in store.commands]
    groups_by_name = {g.name: g for g in groups}

    # -- ref validation ------------------------------------------------------
    seen: dict[str, int] = {}
    for (_, _, lineno, name), _pos in zip(ref_events, ref_pos):
        if name not in groups_by_name:
            known = ", ".join(sorted(groups_by_name)) or "none defined"
            raise ArticleError(lineno, f"unknown group {name!r} (groups: {known})")
        if name in seen:
            raise ArticleError(
                lineno, f"group {name!r} already referenced at line {seen[name]}"
            )
        seen[name] = lineno
    unreferenced = [g.name for g in groups if g.name not in seen]
    if unreferenced:
        raise ArticleError(
            None, f"group(s) never referenced: {', '.join(unreferenced)}"
        )
    # Refs must appear in the order their groups executed, and after the fence
    # that defined them — the compiled document replays in DOCUMENT order, so
    # any other arrangement diverges from the recorded tape at read time.
    fence_pos_for_group: dict[str, int] = {}
    for idx, ex in enumerate(executables):
        if ex.kind != "fence":
            continue
        for g in groups:
            if ex.start <= g.start < ex.end:
                fence_pos_for_group[g.name] = doc_pos[idx]
    prev_start = -1
    for (_, _, lineno, name), pos in zip(ref_events, ref_pos):
        g = groups_by_name[name]
        if pos < fence_pos_for_group[name]:
            raise ArticleError(
                lineno, f"group {name!r} is referenced before the block defining it"
            )
        if g.start < prev_start:
            raise ArticleError(
                lineno,
                f"group {name!r} is referenced out of order: refs must appear in "
                "the order their groups run, or the article diverges from the "
                "recorded scene at read time",
            )
        prev_start = g.start

    # -- substitution --------------------------------------------------------
    # Ungrouped ranges per fence = the fence's tape slice minus its groups.
    fence_lines: dict[int, list[str]] = {}
    for idx, ex in enumerate(executables):
        if ex.kind != "fence":
            continue
        inside = sorted(
            (g for g in groups if ex.start <= g.start < ex.end), key=lambda g: g.start
        )
        kept: list[str] = []
        cursor = ex.start
        for g in inside:
            kept.extend(dsl_lines[cursor : g.start])
            cursor = g.end
        kept.extend(dsl_lines[cursor : ex.end])
        fence_lines[idx] = kept

    replacements: dict[int, list[tuple[_Span, str]]] = {}  # keyed by id(part)
    for ex_idx, (part, span) in span_render.items():
        ex = executables[ex_idx]
        text = _render_spans(dsl_lines[ex.start : ex.end], span.label)
        replacements.setdefault(id(part), []).append((span, text))
    for (part, span, _lineno, name) in ref_events:
        g = groups_by_name[name]
        text = _render_spans(dsl_lines[g.start : g.end], span.label)
        replacements.setdefault(id(part), []).append((span, text))

    fence_order = [i for i, ex in enumerate(executables) if ex.kind == "fence"]
    out: list[str] = []
    nth_fence = 0
    for part in parts:
        if isinstance(part, _Fence):
            lines = fence_lines[fence_order[nth_fence]]
            nth_fence += 1
            out.append("".join(f"{{}}({line})\n" for line in lines))
            continue
        text = part.text
        for span, new in sorted(
            replacements.get(id(part), []), key=lambda r: r[0].start, reverse=True
        ):
            text = text[: span.start] + new + text[span.end :]
        out.append(text)
    compiled = "".join(out)

    # -- round-trip gate -----------------------------------------------------
    # The compiled article executes span-by-span in document order at read
    # time; prove that order is replayable and re-emits verbatim. Segmenting
    # again applies the same skip rules (code fences, math) the reader does.
    commands = [
        s.content.strip()
        for part in _segment(compiled)
        if isinstance(part, _Prose) and part.scan
        for s in _scan_spans(part.text)
    ]
    with Store() as check, article_mode():
        try:
            parse_dsl(commands)
        except DslParseError as exc:
            raise ArticleError(
                None,
                f"compiled article failed the parse round-trip (command "
                f"{exc.lineno} in document order): {exc}",
            ) from exc
        replayed = emit(check).splitlines()
    if replayed != commands:
        for i, (got, want) in enumerate(zip(replayed, commands)):
            if got != want:
                raise ArticleError(
                    None,
                    f"round-trip drift at command {i + 1}: emitted {want!r}, "
                    f"re-emitted {got!r}",
                )
        raise ArticleError(
            None,
            f"round-trip drift: {len(commands)} command(s) in the document, "
            f"{len(replayed)} after replay",
        )
    return compiled


# ---------------------------------------------------------------------------
# Subprocess wrapper (the CLI / CI entry — untrusted article code)
# ---------------------------------------------------------------------------

_DRIVER = """\
import sys

argv = sys.argv[1:]
allow_coercions = "--allow-coercions" in argv
macros = [a[len("--macros="):] for a in argv if a.startswith("--macros=")]
extensions = [
    a for a in argv if a != "--allow-coercions" and not a.startswith("--macros=")
]

import pygeomatic as gm
from pygeomatic.article import ArticleError, compile_article

for _src in extensions:
    gm.load_extensions(_src)
for _src in macros:
    gm.load_macros(_src)

try:
    sys.stdout.write(compile_article(sys.stdin.read(), allow_coercions=allow_coercions))
except ArticleError as exc:
    print(exc, file=sys.stderr)
    raise SystemExit(1)
"""


@dataclass
class ArticleResult:
    ok: bool
    markdown: str = ""
    error: Optional[str] = None


def run_article(
    markdown: str,
    timeout: float = 30.0,
    extensions: Sequence[str] = (),
    macros: Sequence[str] = (),
    allow_coercions: bool = False,
) -> ArticleResult:
    """`compile_article` in a subprocess: the author's Python runs isolated,
    with a timeout, and errors come back as text (mirrors runner.run_generated).
    `extensions`/`macros` are manifest sources loaded before compilation."""
    driver_args = [*extensions, *(f"--macros={src}" for src in macros)]
    if allow_coercions:
        driver_args.append("--allow-coercions")
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _DRIVER, *driver_args],
            input=markdown,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ArticleResult(
            ok=False, error=f"compilation timed out after {timeout}s (infinite loop?)"
        )
    if proc.returncode != 0:
        err = (proc.stderr or "").strip() or f"exited with code {proc.returncode}"
        lines = err.splitlines()
        if len(lines) > 30:
            err = "\n".join(lines[-30:])
        return ArticleResult(ok=False, error=err)
    return ArticleResult(ok=True, markdown=proc.stdout)
