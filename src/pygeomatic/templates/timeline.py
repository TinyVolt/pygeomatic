"""The timeline template."""

import math

from ..functions.helpers import text_box_size
from ._common import TemplateError, _frontmatter, _q

_FONT_SIZE = 14
_BACKGROUND = "#1c2130"
_UNIT = 50
_MAX_WIDTH = 3.0
_BOX_GAP = 0.3
_MIN_STEP = 1.0
_STEM = 0.5
_OVERHANG = 0.5
_CANVAS = {"right": 16.0, "down": 11.0}


def _round_up(v: float) -> float:
    return round(math.ceil(v * 1000) / 1000 + 0.001, 3)


def _parse(data: str) -> tuple[dict[str, str], str, list[str]]:
    fields, body, _ = _frontmatter(data)
    direction = fields.get("direction", "right")
    if direction not in ("right", "down"):
        raise TemplateError(f"direction must be right or down, got {direction!r}")
    events = [line.strip() for line in body.splitlines() if line.strip()]
    if not events:
        raise TemplateError("template data has no lines")
    return fields, direction, events


def _size(text: str) -> tuple[float, float]:
    w, h = text_box_size(text, _FONT_SIZE, -1, -1, _UNIT)
    if w > _MAX_WIDTH:
        w, h = text_box_size(text, _FONT_SIZE, _MAX_WIDTH, -1, _UNIT)
    return _round_up(w), _round_up(h)


def timeline(data: str) -> str:
    """Events in order along a line, drawn all at once on the canvas.

    Each line of `data` is one event: the whole line is the text of its box,
    commas included. Events keep the order of the lines.

    An optional frontmatter block at the top sets the heading and the
    direction the line runs in, `right` (the default) or `down`:

        ---
        title: Space race
        direction: right
        ---

    Ticks are evenly spaced, far enough apart for the widest box (the
    tallest for `down`). A box wraps its text past 3 units wide and joins the
    main line with a short line from its tick. All boxes sit on one side,
    above the line for `right` and right of it for `down`, unless that row
    would be longer than the visible canvas; then they alternate sides,
    which halves the spacing.
    """
    fields, direction, events = _parse(data)
    right = direction == "right"
    sizes = [_size(text) for text in events]
    along = [w if right else h for w, h in sizes]
    widest = max(along)
    n = len(events)

    step = max(_MIN_STEP, widest + _BOX_GAP)
    alternate = n > 1 and (n - 1) * step + widest > _CANVAS[direction]
    if alternate:
        step = max(_MIN_STEP / 2, (widest + _BOX_GAP) / 2)

    # Coordinates are (main, cross): main runs with the line, cross away from
    # it on the first side (up for `right`, rightward for `down`).
    ticks = [k * step for k in range(n)]
    boxes = []
    for k, (w, h) in enumerate(sizes):
        side = -1 if alternate and k % 2 else 1
        depth = h if right else w
        boxes.append((ticks[k], side * (_STEM + depth / 2), side))

    line_lo, line_hi = ticks[0] - _OVERHANG, ticks[-1] + _OVERHANG
    main_lo = min([line_lo] + [m - a / 2 for (m, _, _), a in zip(boxes, along)])
    main_hi = max([line_hi] + [m + a / 2 for (m, _, _), a in zip(boxes, along)])
    cross_lo = min(c - (h if right else w) / 2 for (_, c, _), (w, h) in zip(boxes, sizes))
    cross_hi = max(c + (h if right else w) / 2 for (_, c, _), (w, h) in zip(boxes, sizes))
    main_shift, cross_shift = (main_lo + main_hi) / 2, (min(cross_lo, 0) + max(cross_hi, 0)) / 2

    def to_canvas(main: float, cross: float) -> tuple[float, float]:
        m, c = round(main - main_shift, 3) + 0, round(cross - cross_shift, 3) + 0
        return (m, c) if right else (c, -m + 0)

    lines = []
    x, y = to_canvas(line_lo, 0)
    lines.append(f"    line_start = gm.point({x}, {y})")
    x, y = to_canvas(line_hi, 0)
    lines.append(f"    line_end = gm.point({x}, {y})")
    points = ["line_start", "line_end"]
    shapes = ["    gm.line(line_start, line_end)"]
    for k, ((m, c, side), text, (w, h)) in enumerate(zip(boxes, events, sizes), start=1):
        x, y = to_canvas(m, c)
        lines.append(f"    box_{k} = gm.annotate_text_box({_q(text)}, {x}, {y}, {_FONT_SIZE}, {w}, {h})")
        x, y = to_canvas(m, 0)
        lines.append(f"    tick_{k} = gm.point({x}, {y})")
        x, y = to_canvas(m, side * _STEM)
        lines.append(f"    stem_{k} = gm.point({x}, {y})")
        points += [f"tick_{k}", f"stem_{k}"]
        shapes.append(f"    gm.line(tick_{k}, stem_{k})")
    lines.append(f"    gm.hide({', '.join(points)})")
    lines += shapes

    code = "\n".join([
        "with gm.onpageload():",
        '    gm.scalar(0, out="grid-opacity")',
        f'    gm.text({_q(_BACKGROUND)}, out="grid-bg-color")',
        *lines,
    ])
    title = fields.get("title", "")
    heading = f"# {title}\n\n" if title else ""
    return f"---\nlayout: canvas-only\n---\n{heading}```pygeomatic\n{code}\n```\n"
