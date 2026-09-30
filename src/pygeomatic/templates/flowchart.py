"""The flowchart template."""

import math

from ..functions.helpers import text_box_size
from ._common import TemplateError, _frontmatter, _q, _rows

_FONT_SIZE = 14
_LABEL_FONT_SIZE = 11
_LABEL_GAP = 0.05
_BACKGROUND = "#1c2130"
_UNIT = 50
_MAIN_GAP = 1.0
_CROSS_GAP = 0.5
_PORT_MARGIN = 0.2
_PORT_GAP = 0.3


def _endpoint(field: str, lineno: int) -> tuple[str, "str | None"]:
    ident, sep, text = field.partition("=")
    ident, text = ident.strip(), text.strip()
    if not ident:
        raise TemplateError(f"line {lineno}: a box needs an id")
    if sep and not text:
        raise TemplateError(f"line {lineno}: box {ident!r} has '=' but no text after it")
    return ident, (text if sep else None)


def flowchart(data: str) -> str:
    """Boxes laid out in columns, drawn all at once on the canvas.

    Each line of `data` is one arrow, comma separated:

        from, to, arrow label

    The arrow label is optional. `from` and `to` are box ids; either may give
    the box's text as `id = text drawn on box`. The text is given once, and
    the id alone refers to the box after that. A box that never gets text
    shows its id. Quote a field that contains a comma.

    An optional frontmatter block at the top sets the heading and the
    direction the chart runs in, `right` (the default) or `down`:

        ---
        title: Two-layer MLP
        direction: right
        ---

    A box's column is the longest chain of arrows leading into it. Boxes in a
    column keep the order they first appear in. A box with two or more inputs
    is stretched across the span of its inputs, and a box with two or more
    outputs across the span of its outputs.

    Each arrow runs straight from one box's outgoing side to the other box's
    incoming side: level with whichever end lies within the other box's span,
    else between the two sides' midpoints. An arrow whose straight path would
    cross a box in a column between its ends is routed around them instead,
    with right-angle turns, along a lane just outside those columns' boxes on
    the nearer side; each further such arrow on that side gets its own lane.
    """
    fields, body, skipped = _frontmatter(data)
    direction = fields.get("direction", "right")
    if direction not in ("right", "down"):
        raise TemplateError(f"direction must be right or down, got {direction!r}")

    order: list[str] = []
    texts: dict[str, tuple[str, int]] = {}
    inputs: dict[str, list[str]] = {}
    edges: list[tuple[str, str, str]] = []
    for lineno, row in _rows(body, first_line=skipped + 1):
        if len(row) not in (2, 3):
            raise TemplateError(f"line {lineno}: needs from, to and an optional arrow label")
        ends = []
        for field in row[:2]:
            ident, text = _endpoint(field, lineno)
            if ident not in inputs:
                order.append(ident)
                inputs[ident] = []
            if text is not None:
                if ident in texts and texts[ident][0] != text:
                    known, where = texts[ident]
                    raise TemplateError(
                        f"line {lineno}: box {ident!r} already has the text {known!r} (line {where})"
                    )
                texts[ident] = (text, lineno)
            ends.append(ident)
        src, dst = ends
        if src == dst:
            raise TemplateError(f"line {lineno}: box {src!r} points to itself")
        if src not in inputs[dst]:
            inputs[dst].append(src)
        edges.append((src, dst, row[2] if len(row) == 3 else ""))

    rank: dict[str, int] = {}
    visiting: set[str] = set()

    def visit(n: str) -> int:
        if n in rank:
            return rank[n]
        if n in visiting:
            raise TemplateError(f"the arrows form a loop through box {n!r}")
        visiting.add(n)
        rank[n] = 1 + max((visit(s) for s in inputs[n]), default=-1)
        visiting.discard(n)
        return rank[n]

    for n in order:
        visit(n)

    outputs: dict[str, list[str]] = {n: [] for n in order}
    for n in order:
        for s in inputs[n]:
            outputs[s].append(n)

    natural = {
        n: text_box_size(texts[n][0] if n in texts else n, _FONT_SIZE, -1, -1, _UNIT) for n in order
    }

    def natural_cross(n: str) -> float:
        return natural[n][1] if direction == "right" else natural[n][0]

    cross_size: dict[str, float] = {}
    cross_mid: dict[str, float] = {}
    columns = [[n for n in order if rank[n] == r] for r in range(max(rank.values()) + 1)]

    def span(nodes: list[str]) -> tuple[float, float]:
        return (
            min(cross_mid[s] - cross_size[s] / 2 for s in nodes),
            max(cross_mid[s] + cross_size[s] / 2 for s in nodes),
        )

    def settle(column: list[str]) -> None:
        prev_end = None
        for n in column:
            start = cross_mid[n] - cross_size[n] / 2
            if prev_end is not None:
                start = max(start, prev_end + _CROSS_GAP)
            cross_mid[n] = start + cross_size[n] / 2
            prev_end = start + cross_size[n]

    for column in columns:
        prev_end = None
        for n in column:
            ins = inputs[n]
            size = natural_cross(n)
            start = 0.0 if prev_end is None else prev_end + _CROSS_GAP
            if ins:
                lo, hi = span(ins)
                if len(ins) >= 2:
                    size = max(size, hi - lo)
                wanted = (lo + hi) / 2 - size / 2
                start = wanted if prev_end is None else max(wanted, prev_end + _CROSS_GAP)
            cross_size[n] = size
            cross_mid[n] = start + size / 2
            prev_end = start + size

    for column in reversed(columns[:-1]):
        for n in column:
            if len(outputs[n]) >= 2:
                out_lo, out_hi = span(outputs[n])
                own_lo, own_hi = span([n])
                lo, hi = min(out_lo, own_lo), max(out_hi, own_hi)
                cross_size[n] = hi - lo
                cross_mid[n] = (lo + hi) / 2
        settle(column)

    def round_up(v: float) -> float:
        return round(math.ceil(v * 1000) / 1000 + 0.001, 3)

    box_size: dict[str, tuple[float, float]] = {}
    for n in order:
        text = texts[n][0] if n in texts else n
        if direction == "right":
            box_size[n] = (round_up(natural[n][0]), round_up(cross_size[n]))
        else:
            width = round_up(cross_size[n])
            box_size[n] = (width, round_up(text_box_size(text, _FONT_SIZE, width, -1, _UNIT)[1]))
    main_size = {n: box_size[n][0] if direction == "right" else box_size[n][1] for n in order}

    gaps = [_MAIN_GAP] * len(columns)
    for src, dst, label in edges:
        if label and rank[dst] == rank[src] + 1:
            w, h = text_box_size(label, _LABEL_FONT_SIZE, 0, 0, _UNIT)
            need = (w if direction == "right" else h) + 2 * _LABEL_GAP + 2 * _PORT_GAP
            gaps[rank[src]] = max(gaps[rank[src]], need)

    main_mid: dict[int, float] = {}
    pos = 0.0
    for r, column in enumerate(columns):
        extent = max(main_size[n] for n in column)
        main_mid[r] = pos + extent / 2
        pos += extent + gaps[r]
    main_shift = (pos - gaps[-1]) / 2
    cross_lo = min(cross_mid[n] - cross_size[n] / 2 for n in order)
    cross_hi = max(cross_mid[n] + cross_size[n] / 2 for n in order)
    cross_shift = (cross_lo + cross_hi) / 2

    lines = []
    box_var = {n: f"box_{k}" for k, n in enumerate(order, start=1)}
    for k, n in enumerate(order, start=1):
        m = round(main_mid[rank[n]] - main_shift, 3)
        c = round(cross_mid[n] - cross_shift, 3)
        text = texts[n][0] if n in texts else n
        w, h = box_size[n]
        x, y = (m, -c) if direction == "right" else (c, -m)
        lines.append(f"    box_{k} = gm.annotate_text_box({_q(text)}, {x + 0}, {y + 0}, {_FONT_SIZE}, {w}, {h})")

    sides = {
        "right": {"out": (1, 2), "in": (0, 3), "lo": (0, 1), "hi": (3, 2)},
        "down": {"out": (2, 3), "in": (0, 1), "lo": (0, 3), "hi": (1, 2)},
    }[direction]
    anchors: dict[tuple[str, str], str] = {}

    def anchor(n: str, side: str) -> str:
        if (n, side) not in anchors:
            box = box_var[n]
            if not any(key[0] == n for key in anchors):
                lines.append(f"    {box}_corners = gm.text_box_corners({box})")
            i, j = sides[side]
            var = f"{box}_{side}"
            lines.append(
                f"    {var} = gm.mid_point(gm.get_array_element({box}_corners, {i}), "
                f"gm.get_array_element({box}_corners, {j}))"
            )
            anchors[(n, side)] = var
        return anchors[(n, side)]

    def main_span(n: str) -> tuple[float, float]:
        mid = main_mid[rank[n]]
        return mid - main_size[n] / 2, mid + main_size[n] / 2

    def crosses(a: tuple[float, float], b: tuple[float, float], n: str) -> bool:
        (m0, m1), (c0, c1) = main_span(n), span([n])
        t0, t1 = 0.0, 1.0
        for p, q in (
            (a[0] - b[0], a[0] - m0), (b[0] - a[0], m1 - a[0]),
            (a[1] - b[1], a[1] - c0), (b[1] - a[1], c1 - a[1]),
        ):
            if p == 0:
                if q < 0:
                    return False
                continue
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
        return True

    def to_canvas(cross: float) -> float:
        c = cross - cross_shift
        return round(-c if direction == "right" else c, 3)

    def place_ports(lo: float, hi: float, wanted: list[float]) -> list[float]:
        n = len(wanted)
        a, b = lo + _PORT_MARGIN, hi - _PORT_MARGIN
        if a > b:
            a = b = (lo + hi) / 2
        by_want = sorted(range(n), key=lambda i: wanted[i])
        placed = [0.0] * n
        if n > 1 and b - a < _PORT_GAP * (n - 1):
            for j, i in enumerate(by_want):
                placed[i] = lo + (hi - lo) * (j + 1) / (n + 1)
            return placed
        prev = None
        for i in by_want:
            v = min(max(wanted[i], a), b)
            placed[i] = v if prev is None else max(v, prev + _PORT_GAP)
            prev = placed[i]
        limit = b
        for i in reversed(by_want):
            placed[i] = min(placed[i], limit)
            limit = placed[i] - _PORT_GAP
        return placed

    def clear(a: tuple[float, float], b: tuple[float, float], ends: set[str]) -> bool:
        return not any(crosses(a, b, n) for n in order if n not in ends)

    def corner_side(level: float, dst: str) -> "str | None":
        lo, hi = span([dst])
        return "lo" if level <= lo else "hi" if level >= hi else None

    routes = []
    for src, dst, label in edges:
        src_mid, dst_mid = cross_mid[src], cross_mid[dst]
        src_lo, src_hi = span([src])
        dst_lo, dst_hi = span([dst])
        level = dst_mid if src_lo < dst_mid < src_hi else src_mid
        x0, x1, xc = main_span(src)[1], main_span(dst)[0], main_mid[rank[dst]]
        ends = {src, dst}
        side = corner_side(level, dst)
        if side is None and clear((x0, level), (x1, level), ends):
            routes.append({"kind": "straight", "want": (level, level)})
        elif side and clear((x0, level), (xc, level), ends) and clear(
            (xc, level), (xc, dst_lo if side == "lo" else dst_hi), ends
        ):
            nearer_first = 1e-6 * (xc - x0) * (1 if side == "hi" else -1)
            routes.append({"kind": "corner", "want": (level + nearer_first, None)})
        elif rank[dst] - rank[src] == 1:
            routes.append({"kind": "zig", "want": (src_mid, dst_mid), "stub": round((x1 - x0) / 2, 3)})
        else:
            between = [n for n in order if rank[src] < rank[n] < rank[dst]]
            top = min(span([n])[0] for n in between)
            bottom = max(span([n])[1] for n in between)
            lane_side = "top" if (src_mid + dst_mid) / 2 - top <= bottom - (src_mid + dst_mid) / 2 else "bottom"
            wants = (src_lo, dst_lo) if lane_side == "top" else (src_hi, dst_hi)
            routes.append({"kind": "elbow", "want": wants, "lane": (lane_side, top if lane_side == "top" else bottom)})
        routes[-1].update(src=src, dst=dst, label=label)

    start_at: dict[int, float] = {}
    outs: dict[str, list[int]] = {}
    for i, r in enumerate(routes):
        outs.setdefault(r["src"], []).append(i)
    for n, items in outs.items():
        lo, hi = span([n])
        for i, v in zip(items, place_ports(lo, hi, [routes[i]["want"][0] for i in items])):
            start_at[i] = v

    for i, r in enumerate(routes):
        if r["kind"] == "straight" and corner_side(start_at[i], r["dst"]) is not None:
            r["kind"] = "corner"
        if r["kind"] == "corner":
            r["side"] = corner_side(start_at[i], r["dst"]) or "lo"

    end_at: dict[int, float] = {}
    ins: dict[str, list[int]] = {}
    corners_in: dict[tuple[str, str], list[int]] = {}
    for i, r in enumerate(routes):
        if r["kind"] == "straight":
            end_at[i] = start_at[i]
        elif r["kind"] == "corner":
            corners_in.setdefault((r["dst"], r["side"]), []).append(i)
        else:
            ins.setdefault(r["dst"], []).append(i)
    for n, items in ins.items():
        lo, hi = span([n])
        for i, v in zip(items, place_ports(lo, hi, [routes[i]["want"][1] for i in items])):
            end_at[i] = v
    entry_at: dict[int, float] = {}
    for (n, side), items in corners_in.items():
        edge = span([n])[0 if side == "lo" else 1]
        lo, hi = main_span(n)
        by_near = sorted(items, key=lambda i: abs(start_at[i] - edge))
        for j, i in enumerate(by_near):
            entry_at[i] = lo + (hi - lo) * (j + 1) / (len(items) + 1)

    hidden: list[str] = []

    def port(n: str, side: str, cross: float, var: str) -> str:
        mid = anchor(n, side)
        if abs(cross - cross_mid[n]) < 1e-9:
            return mid
        if direction == "right":
            lines.append(f"    {var} = gm.point({mid}.x, {to_canvas(cross)})")
        else:
            lines.append(f"    {var} = gm.point({to_canvas(cross)}, {mid}.y)")
        hidden.append(var)
        return var

    def to_canvas_main(main: float) -> float:
        m = main - main_shift
        return round(m if direction == "right" else -m, 3)

    arrows = []
    stubs: dict[int, float] = {}
    lanes: dict[int, float] = {}
    elbows: list[tuple[int, int, str, float]] = []
    for k, r in enumerate(routes, start=1):
        i, src, dst, label, kind = k - 1, r["src"], r["dst"], r["label"], r["kind"]
        start = port(src, "out", start_at[i], f"arrow_{k}_start")
        if kind == "corner":
            edge = anchor(dst, r["side"])
            end = f"arrow_{k}_end"
            m = to_canvas_main(entry_at[i])
            if direction == "right":
                lines.append(f"    {end} = gm.point({m}, {edge}.y)")
            else:
                lines.append(f"    {end} = gm.point({edge}.x, {m})")
            hidden.append(end)
            stubs[i], lanes[i] = 0, to_canvas(start_at[i])
        else:
            end = port(dst, "in", end_at[i], f"arrow_{k}_end")
        if kind == "zig":
            stubs[i], lanes[i] = r["stub"], to_canvas(end_at[i])
        if kind == "elbow":
            lane_side, lane_edge = r["lane"]
            elbows.append((rank[dst] - rank[src], i, lane_side, lane_edge))
            stubs[i] = round(min(gaps[rank[src]], gaps[rank[dst] - 1]) / 2, 3)
        arrows.append((kind, start, end, label, None))

    edge_of = {"top": min, "bottom": max}
    for side in ("top", "bottom"):
        mine = sorted(e for e in elbows if e[2] == side)
        if not mine:
            continue
        edge = edge_of[side](e[3] for e in mine)
        offset = 0.0
        for _, i, _, _ in mine:
            offset += _CROSS_GAP
            lane = edge - offset if side == "top" else edge + offset
            kind, start, end, label, _ = arrows[i]
            arrows[i] = (kind, start, end, label, (to_canvas(lane), side))
            lanes[i] = to_canvas(lane)
            if label:
                w, h = text_box_size(label, _LABEL_FONT_SIZE, 0, 0, _UNIT)
                offset += (h if direction == "right" else w) + _LABEL_GAP

    labels = []
    for k, (kind, start, end, label, route) in enumerate(arrows, start=1):
        if not label:
            continue
        mid = f"arrow_{k}_mid"
        lines.append(f"    {mid} = gm.mid_point({start}, {end})")
        hidden.append(mid)
        w, h = text_box_size(label, _LABEL_FONT_SIZE, 0, 0, _UNIT)
        if kind == "elbow":
            lane, side = route
            if direction == "right":
                away = h / 2 + _LABEL_GAP
                x, y = f"{mid}.x", round(lane + (away if side == "top" else -away), 3)
            else:
                away = w / 2 + _LABEL_GAP
                x, y = round(lane + (-away if side == "top" else away), 3), f"{mid}.y"
        elif direction == "right":
            x, y = f"{mid}.x", f"gm.add({mid}.y, {round(h / 2 + _LABEL_GAP, 3)})"
        else:
            x, y = f"gm.add({mid}.x, {round(w / 2 + _LABEL_GAP, 3)})", f"{mid}.y"
        labels.append(f"    gm.annotate_text_box({_q(label)}, {x}, {y}, {_LABEL_FONT_SIZE})")
    lines.append(f"    gm.hide({', '.join([*anchors.values(), *hidden])})")
    for i, (kind, start, end, _, _) in enumerate(arrows):
        if kind == "straight":
            lines.append(f"    gm.annotate_arrow({start}, {end})")
        else:
            lines.append(
                f"    gm.annotate_elbow_arrow({start}, {end}, {lanes[i]}, {stubs[i]}, "
                f"{direction == 'down'})"
            )
    lines.extend(labels)

    code = "\n".join([
        "with gm.onpageload():",
        '    gm.scalar(0, out="grid-opacity")',
        f'    gm.text({_q(_BACKGROUND)}, out="grid-bg-color")',
        *lines,
    ])
    title = fields.get("title", "")
    heading = f"# {title}\n\n" if title else ""
    return f"{heading}```pygeomatic\n{code}\n```\n"
