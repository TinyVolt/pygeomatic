"""gm.templates — turn plain data into a complete pygeomatic article.

Each template takes the author's data as text and returns the full markdown
source of an article (prose plus a ```pygeomatic block), ready for
`compile_article`. Nothing is recorded on any store: the returned source is
compiled like any hand-written article.

    source = gm.templates.flash_card("What is 2+2?, 4, Count them, 3, 5")
    compiled = gm.compile_article(source)
"""

import csv
import json
import re
import textwrap


def _q(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


class TemplateError(ValueError):
    pass


_FRONTMATTER = re.compile(r"\A﻿?---[ \t]*\r?\n(?:([\s\S]*?)\r?\n)?---[ \t]*(?:\r?\n|\Z)")


def _frontmatter(data: str) -> tuple[dict[str, str], str, int]:
    """Split a `---` fenced `key: value` block off the top of `data`; return
    `(fields, rest, number of lines taken)`. Mirrors readFrontmatter in
    tinyvolt-web's frontmatter.ts."""
    if not isinstance(data, str):
        raise TemplateError(f"template data must be a string, got {type(data).__name__}")
    match = _FRONTMATTER.match(data)
    if not match:
        return {}, data, 0
    fields = {}
    for line in (match.group(1) or "").splitlines():
        pair = re.match(r"^\s*([\w-]+)\s*:\s*(.*?)\s*$", line)
        if pair:
            fields[pair.group(1)] = re.sub(r"^(['\"])(.*)\1$", r"\2", pair.group(2))
    return fields, data[match.end():], match.group(0).count("\n")


def _rows(data: str, first_line: int = 1) -> list[tuple[int, list[str]]]:
    if not isinstance(data, str):
        raise TemplateError(f"template data must be a string, got {type(data).__name__}")
    rows = []
    for lineno, line in enumerate(data.splitlines(), start=first_line):
        if not line.strip():
            continue
        fields = next(csv.reader([line], skipinitialspace=True))
        rows.append((lineno, [field.strip() for field in fields]))
    if not rows:
        raise TemplateError("template data has no lines")
    return rows


def _block(text: str, depth: int) -> str:
    return textwrap.indent(textwrap.dedent(text).strip("\n"), "    " * depth)


def _score_var(k: int) -> str:
    return "answer_1" if k == 1 else f"score_{k}"


def _score_id(k: int) -> str:
    return "answer-1" if k == 1 else f"score-{k}"


def _card_setup(n: int, options: list[str]) -> str:
    values = ", ".join("1" if k == 0 else "0" for k in range(len(options)))
    labels = ", ".join(f"gm.text({_q(o)})" for o in options)
    return _block(f"""
        answer_{n} = gm.scalar(gm.NaN, out={_q(f'answer-{n}')})
        indices_{n} = gm.arange(0, {len(options)})
        order_{n} = gm.shuffle(indices_{n}, out={_q(f'order-{n}')})
        values_{n} = gm.get_array_element(gm.array({values}), order_{n})
        labels_{n} = gm.get_array_element(gm.array({labels}), order_{n})
    """, 1)


def _card_block(n: int, total: int, question: str, hint: str, options: list[str]) -> str:
    unanswered = f"gm.cond.not_(gm.cond.ge(answer_{n}, 0))"
    if n == 1:
        gate = unanswered
        right, wrong_so_far = "✓ 0", "✗ 0"
    else:
        gate = f"gm.cond.ge(answer_{n - 1}, 0) & {unanswered}"
        right, wrong_so_far = f"✓ ${{{_score_id(n - 1)}}}", f"✗ ${{wrong-{n - 1}}}"
    parts = [_block(f"""
        with gm.when({gate}):
            with gm.ui.box(border=True, pad=2):
                with gm.ui.row(justify="between", font_size="0.75rem"):
                    with gm.ui.row(gap=2):
    """, 2)]
    if n > 1:
        parts.append(_block(f"""
            with gm.ui.button("←", font_size="0.8rem"):
                gm.scalar(gm.NaN, out={_q(f'answer-{n - 1}')})
        """, 6))
    parts.append(_block(f"gm.ui.label({_q(f'Question {n} of {total}')})", 6))
    parts.append(_block(f"""
        with gm.ui.row(gap=3):
            gm.ui.label({_q(right)})
            gm.ui.label({_q(wrong_so_far)})
    """, 5))
    parts.append(_block(f"""
        gm.ui.label({_q(question)}, pad=1)
        answer_{n} = gm.ui.radio(values_{n}, value=None, display=labels_{n})
    """, 4))
    if n > 1:
        parts.append(_block(f"{_score_var(n)} = {_score_var(n - 1)} + answer_{n}", 4))
    if n < total:
        parts.append(_block(f"wrong_{n} = {n} - {_score_var(n)}", 4))
    if hint:
        parts.append(_block(f"""
            hint_{n} = gm.ui.checkbox(False, label="Show hint")
            with gm.when(hint_{n}):
                gm.ui.label({_q(f'Hint: {hint}')}, pad=1)
        """, 4))
    return "\n".join(parts)


def _card_restart(n: int, hint: str) -> str:
    parts = [_block(f"""
        order_{n} = gm.shuffle(indices_{n}, out={_q(f'order-{n}')})
        answer_{n} = gm.scalar(gm.NaN, out={_q(f'answer-{n}')})
    """, 5)]
    if hint:
        parts.append(_block(f"hint_{n} = gm.bool_(False, out={_q(f'hint-{n}')})", 5))
    return "\n".join(parts)


def flash_card(data: str) -> str:
    """Multiple-choice flash cards, one question on screen at a time.

    Each line of `data` is one card, comma separated:

        question, correct answer, hint, wrong answer, wrong answer, ...

    The hint may be left empty; the card then has no hint checkbox. The
    options are shuffled each time the quiz starts. Quote a field that
    contains a comma: `"Pick one, please", yes, , no`.

    An optional frontmatter block at the top sets the article's heading:

        ---
        title: Capitals
        ---

    With no title there is no heading. The article is text only: the canvas
    is hidden.

    Picking any answer moves on to the next card. The top of each card
    shows the question number and the right and wrong answers so far; after
    the last card a panel
    shows the final score and a restart button.
    """
    fields, body, skipped = _frontmatter(data)
    cards = []
    for lineno, row in _rows(body, first_line=skipped + 1):
        if len(row) < 2 or not row[0] or not row[1]:
            raise TemplateError(f"line {lineno}: needs at least a question and a correct answer")
        question, answer = row[0], row[1]
        hint = row[2] if len(row) > 2 else ""
        wrong = [field for field in row[3:] if field]
        options = [answer, *wrong]
        if len(set(options)) != len(options):
            raise TemplateError(f"line {lineno}: the answers must all be different")
        cards.append((question, answer, hint, options))

    total = len(cards)
    numbered = list(enumerate(cards, start=1))
    setups = [_card_setup(n, options) for n, (_, _, _, options) in numbered]
    blocks = [_card_block(n, total, question, hint, options) for n, (question, _, hint, options) in numbered]
    restarts = [_card_restart(n, hint) for n, (_, _, hint, _) in numbered]
    final = _block(f"""
        with gm.when(gm.cond.ge(answer_{total}, 0)):
            with gm.ui.box(border=True, pad=2):
                gm.ui.label({_q(f'Final score: ${{{_score_id(total)}}} out of {total}')})
                with gm.ui.button("Restart quiz", font_size="0.8rem"):
    """, 2)

    code = "\n".join([
        "with gm.onpageload():",
        *setups,
        "",
        "    with gm.ui.col(gap=3, pad=2):",
        "\n\n".join(blocks),
        "",
        final,
        *restarts,
    ])
    title = fields.get("title", "")
    heading = f"# {title}\n\n" if title else ""
    return f"---\nlayout: text-only\n---\n{heading}```pygeomatic\n{code}\n```\n"
