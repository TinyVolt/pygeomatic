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


def _q(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


class TemplateError(ValueError):
    pass


def _rows(data: str) -> list[tuple[int, list[str]]]:
    if not isinstance(data, str):
        raise TemplateError(f"template data must be a string, got {type(data).__name__}")
    rows = []
    for lineno, line in enumerate(data.splitlines(), start=1):
        if not line.strip():
            continue
        fields = next(csv.reader([line], skipinitialspace=True))
        rows.append((lineno, [field.strip() for field in fields]))
    if not rows:
        raise TemplateError("template data has no lines")
    return rows


def flash_card(data: str) -> str:
    """Multiple-choice flash cards, one question on screen at a time.

    Each line of `data` is one card, comma separated:

        question, correct answer, hint, wrong answer, wrong answer, ...

    The hint may be left empty; the card then has no hint checkbox. Options
    are shown in the order written, correct answer first. Quote a field that
    contains a comma: `"Pick one, please", yes, , no`.

    Picking the correct answer shows a Continue button that moves on to the
    next card; the last card's Finish button shows a restart panel.
    """
    cards = []
    for lineno, fields in _rows(data):
        if len(fields) < 2 or not fields[0] or not fields[1]:
            raise TemplateError(f"line {lineno}: needs at least a question and a correct answer")
        question, answer = fields[0], fields[1]
        hint = fields[2] if len(fields) > 2 else ""
        wrong = [field for field in fields[3:] if field]
        options = [answer, *wrong]
        if len(set(options)) != len(options):
            raise TemplateError(f"line {lineno}: the answers must all be different")
        cards.append((question, answer, hint, options))

    total = len(cards)
    done = [f"card_{i}_done" for i in range(1, total + 1)]
    done_ids = [f"card-{i}-done" for i in range(1, total + 1)]

    lines = ["with gm.onpageload():"]
    for var, node_id in zip(done, done_ids):
        lines.append(f"    {var} = gm.bool_(False, out={_q(node_id)})")
    lines.append("")
    lines.append("    with gm.ui.col(gap=3, pad=2):")

    for i, (question, answer, hint, options) in enumerate(cards):
        n = i + 1
        if i == 0:
            gate = f"gm.cond.eq({done[0]}, False)"
        else:
            gate = f"gm.cond.eq({done[i - 1]}, True) & gm.cond.eq({done[i]}, False)"
        lines += [
            f"        with gm.when({gate}):",
            "            with gm.ui.box(border=True, pad=2):",
            f"                gm.ui.label({_q(f'Question {n} of {total}')})",
            f"                gm.ui.label({_q(question)})",
            f"                answer_{n} = gm.ui.radio([{', '.join(_q(o) for o in options)}], value=\"\", label=\"Choose an answer\")",
        ]
        if hint:
            lines += [
                f"                hint_{n} = gm.ui.checkbox(False, label=\"Show hint\")",
                f"                with gm.when(hint_{n}):",
                f"                    gm.ui.label({_q(f'Hint: {hint}')})",
            ]
        lines += [
            f"                with gm.when(gm.cond.eq(answer_{n}, {_q(answer)})):",
            f"                    with gm.ui.button({_q('Finish' if n == total else 'Continue')}):",
            f"                        {done[i]} = gm.bool_(True, out={_q(done_ids[i])})",
            "",
        ]

    lines += [
        f"        with gm.when({done[-1]}):",
        "            with gm.ui.box(border=True, pad=2):",
        f"                gm.ui.label({_q(f'All {total} questions are correct!')})",
        "                with gm.ui.button(\"Restart quiz\"):",
    ]
    for var, node_id in zip(done, done_ids):
        lines.append(f"                    {var} = gm.bool_(False, out={_q(node_id)})")

    code = "\n".join(lines)
    return (
        "# Flash cards\n\n"
        "Answer each question correctly to unlock the next one.\n\n"
        f"```pygeomatic\n{code}\n```\n"
    )
