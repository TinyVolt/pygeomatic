"""The flowchart template."""

import math

from ..functions.helpers import text_box_size
from ._common import TemplateError, _frontmatter, _q, _rows

_FONT_SIZE = 14
_LABEL_FONT_SIZE = 11
_LABEL_GAP = 0.05
_LABEL_NEAR_PX = {"right": -3, "down": -1}
_BACKGROUND = "#1c2130"
_UNIT = 50
_MAIN_GAP = 1.0
_BOX_GAP = 0.5
_CHANNEL_GAP = 0.3
_PORT_MARGIN = 0.2
_PORT_GAP = 0.3
_TRACK_GAP = 0.3
_MIN_VERTICAL_PX = 25
_MIN_STUB_PX = 18
_SWEEPS = 40
_SNAP_SLACK = 0.03


def _endpoint(field: str, lineno: int) -> tuple[str, "str | None"]:
    ident, sep, text = field.partition("=")
    ident, text = ident.strip(), text.strip()
    if not ident:
        raise TemplateError(f"line {lineno}: a box needs an id")
    if sep and not text:
        raise TemplateError(f"line {lineno}: box {ident!r} has '=' but no text after it")
    return ident, (text if sep else None)


def _parse(data: str):
    fields, body, skipped = _frontmatter(data)
    direction = fields.get("direction", "right")
    if direction not in ("right", "down"):
        raise TemplateError(f"direction must be right or down, got {direction!r}")

    texts: dict[str, tuple[str, int]] = {}
    boxes: set[str] = set()
    edges: list[tuple[str, str, str]] = []
    for lineno, row in _rows(body, first_line=skipped + 1):
        if len(row) not in (2, 3):
            raise TemplateError(f"line {lineno}: needs from, to and an optional arrow label")
        ends = []
        for field in row[:2]:
            ident, text = _endpoint(field, lineno)
            boxes.add(ident)
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
        edges.append((src, dst, row[2] if len(row) == 3 else ""))
    edges.sort()
    return fields, direction, sorted(boxes), {n: t for n, (t, _) in texts.items()}, edges


def _layout(data: str) -> dict:
    """Place boxes, arrows and labels. Coordinates are (main, cross): main runs
    with the chart's direction, cross across it and grows downward on screen
    for `right` (rightward for `down`)."""
    fields, direction, real, texts, edges = _parse(data)
    right = direction == "right"
    min_vertical = _MIN_VERTICAL_PX / _UNIT
    min_stub = _MIN_STUB_PX / _UNIT
    label_near = _LABEL_NEAR_PX[direction] / _UNIT

    inputs: dict[str, list[str]] = {n: sorted({s for s, t, _ in edges if t == n}) for n in real}
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

    for n in real:
        visit(n)

    # Every arrow becomes a chain of one-column hops; a pass-through slot holds
    # its place in each column it crosses.
    chains: list[list[str]] = []
    for e, (src, dst, _) in enumerate(edges):
        slots = [f"\x7f{src}\x1f{dst}\x1f{e:04d}\x1f{r:04d}" for r in range(rank[src] + 1, rank[dst])]
        for slot, r in zip(slots, range(rank[src] + 1, rank[dst])):
            rank[slot] = r
        chains.append([src, *slots, dst])
    is_box = {n: n in texts or n in inputs for n in rank}
    nodes = sorted(rank)

    hops: list[tuple[int, str, str]] = []
    for e, chain in enumerate(chains):
        for a, b in zip(chain, chain[1:]):
            hops.append((e, a, b))
    hops_in: dict[str, list[int]] = {n: [] for n in nodes}
    hops_out: dict[str, list[int]] = {n: [] for n in nodes}
    for h, (_, a, b) in enumerate(hops):
        hops_out[a].append(h)
        hops_in[b].append(h)
    first_hop = {e: next(h for h, hop in enumerate(hops) if hop[0] == e) for e in range(len(edges))}

    # Column order: sweep toward the side with fewer crossings, ties by id.
    columns = [sorted(n for n in nodes if rank[n] == r) for r in range(max(rank.values()) + 1)]

    def crossings() -> int:
        index = {n: i for column in columns for i, n in enumerate(column)}
        by_gap: dict[int, list[tuple[int, int]]] = {}
        for _, a, b in hops:
            by_gap.setdefault(rank[a], []).append((index[a], index[b]))
        return sum(
            1
            for pairs in by_gap.values()
            for i in range(len(pairs))
            for j in range(i + 1, len(pairs))
            if (pairs[i][0] - pairs[j][0]) * (pairs[i][1] - pairs[j][1]) < 0
        )

    def reorder(r: int, toward: int) -> None:
        ref = {m: i for i, m in enumerate(columns[r + toward])}
        own = {n: i for i, n in enumerate(columns[r])}
        scale = max(1, len(columns[r + toward]) - 1) / max(1, len(columns[r]) - 1)

        def key(n: str) -> tuple[float, str]:
            near = [hops[h][2] for h in hops_out[n]] if toward > 0 else [hops[h][1] for h in hops_in[n]]
            return (sum(ref[m] for m in near) / len(near) if near else own[n] * scale, n)

        columns[r].sort(key=key)

    best = ([list(c) for c in columns], crossings())
    for _ in range(8):
        for r in range(1, len(columns)):
            reorder(r, -1)
        for r in range(len(columns) - 2, -1, -1):
            reorder(r, 1)
        count = crossings()
        if count < best[1]:
            best = ([list(c) for c in columns], count)
    columns = best[0]
    count = best[1]
    improved = True
    while improved and count:
        improved = False
        for column in columns:
            for n in sorted(column):
                column.remove(n)
                tries = []
                for k in range(len(column) + 1):
                    column.insert(k, n)
                    tries.append((crossings(), k))
                    column.pop(k)
                fewest, k = min(tries)
                column.insert(k, n)
                if fewest < count:
                    count, improved = fewest, True
    position_in_column = {n: i for column in columns for i, n in enumerate(column)}

    # Sizes.
    def label_size(label: str) -> tuple[float, float]:
        w, h = text_box_size(label, _LABEL_FONT_SIZE, 0, 0, _UNIT)
        return (w, h) if right else (h, w)

    labelled_hop = {first_hop[e]: edges[e][2] for e in range(len(edges)) if edges[e][2]}

    def label_room(h: int) -> float:
        if h not in labelled_hop:
            return _PORT_GAP
        return max(_PORT_GAP, label_size(labelled_hop[h])[1] + _LABEL_GAP)

    def pair_gap(smaller: int, larger: int) -> float:
        return label_room(larger) if right else label_room(smaller)

    def ports_need(side: list[int]) -> float:
        if len(side) < 2:
            return 0.0
        rooms = sorted((label_room(h) for h in side), reverse=True)
        return 2 * _PORT_MARGIN + sum(rooms[: len(side) - 1])

    natural = {n: text_box_size(texts.get(n, n), _FONT_SIZE, -1, -1, _UNIT) for n in nodes if is_box[n]}
    cross_size: dict[str, float] = {}
    for n in nodes:
        if is_box[n]:
            w, h = natural[n]
            cross_size[n] = max(h if right else w, ports_need(hops_in[n]), ports_need(hops_out[n]))
        else:
            cross_size[n] = 0.0

    def margin(n: str) -> float:
        return _PORT_MARGIN if is_box[n] else 0.0

    def sep(a: str, b: str) -> float:
        base = _BOX_GAP if is_box[a] and is_box[b] else _CHANNEL_GAP
        hanging = b if right else a
        rooms = [label_room(h) for h in hops_in[hanging] + hops_out[hanging] if h in labelled_hop]
        return max([base] + [room - margin(a) - margin(b) for room in rooms])

    # Cross placement: line up each hop's two ends while keeping every column
    # in order and apart.
    cross_mid: dict[str, float] = {}
    for column in columns:
        pos = 0.0
        for k, n in enumerate(column):
            if k:
                pos += cross_size[column[k - 1]] / 2 + sep(column[k - 1], n) + cross_size[n] / 2
            cross_mid[n] = pos

    def span(n: str) -> tuple[float, float]:
        return cross_mid[n] - cross_size[n] / 2, cross_mid[n] + cross_size[n] / 2

    port: dict[tuple[int, int], float] = {}

    def place_side(n: str, side: list[int], end: int, wanted: dict[int, float]) -> None:
        if not side:
            return
        if not is_box[n]:
            for h in side:
                port[(h, end)] = cross_mid[n]
            return
        lo, hi = span(n)
        a, b = lo + _PORT_MARGIN, hi - _PORT_MARGIN
        if a > b:
            a = b = (lo + hi) / 2
        order = sorted(side, key=lambda h: (wanted[h], h))
        steps = [pair_gap(order[j], order[j + 1]) for j in range(len(order) - 1)]
        if sum(steps) > b - a:
            v = (a + b) / 2 - sum(steps) / 2
            for j, h in enumerate(order):
                port[(h, end)] = v
                v += steps[j] if j < len(steps) else 0
            return
        prev = None
        for j, h in enumerate(order):
            v = min(max(wanted[h], a), b)
            port[(h, end)] = v if prev is None else max(v, prev + steps[j - 1])
            prev = port[(h, end)]
        limit = b
        for j in range(len(order) - 1, -1, -1):
            h = order[j]
            port[(h, end)] = min(port[(h, end)], limit)
            if j:
                limit = port[(h, end)] - steps[j - 1]

    def place_ports() -> None:
        other_out = {h: port.get((h, 1), cross_mid[hops[h][2]]) for h in range(len(hops))}
        other_in = {h: port.get((h, 0), cross_mid[hops[h][1]]) for h in range(len(hops))}
        for n in nodes:
            place_side(n, hops_out[n], 0, other_out)
            place_side(n, hops_in[n], 1, other_in)

    # One variable per box and one per skip arrow, so a skip arrow's slots
    # share a level. Two skip arrows that swap order between columns cannot
    # both stay straight; one of them falls back to a slot per column.
    var_of: dict[str, str] = {n: n for n in nodes if is_box[n]}
    for e, chain in enumerate(chains):
        for d in chain[1:-1]:
            var_of[d] = f"\x7f{e:04d}"

    rel: dict[str, float] = {n: 0.0 for n in var_of}

    def least_distance(u: str, v: str) -> float:
        column = columns[rank[u]]
        i, j = position_in_column[u], position_in_column[v]
        return sum(
            cross_size[column[k]] / 2 + sep(column[k], column[k + 1]) + cross_size[column[k + 1]] / 2
            for k in range(i, j)
        )

    def constraints() -> list[tuple[str, str, float]]:
        found: dict[tuple[str, str], float] = {}
        for column in columns:
            for u, v in zip(column, column[1:]):
                if var_of[u] == var_of[v]:
                    continue
                pair = (var_of[u], var_of[v])
                gap = cross_size[u] / 2 + sep(u, v) + cross_size[v] / 2 + rel[u] - rel[v]
                found[pair] = max(found.get(pair, -math.inf), gap)
        return [(a, b, g) for (a, b), g in sorted(found.items())]

    def topological(cons: list[tuple[str, str, float]]) -> "list[str] | None":
        names = sorted(set(var_of.values()))
        after: dict[str, list[str]] = {v: [] for v in names}
        before = {v: 0 for v in names}
        for a, b, _ in cons:
            after[a].append(b)
            before[b] += 1
        ready = sorted(v for v in names if not before[v])
        out = []
        while ready:
            v = ready.pop(0)
            out.append(v)
            for w in after[v]:
                before[w] -= 1
                if not before[w]:
                    ready.append(w)
            ready.sort()
        return out if len(out) == len(names) else None

    cons = constraints()
    order_of_vars = topological(cons)
    while order_of_vars is None:
        stuck = sorted({a for a, b, _ in cons} & {b for a, b, _ in cons})
        chain_vars = [v for v in stuck if v.startswith("\x7f") and not v.startswith("\x7f\x7f")]
        split = chain_vars[0]
        for d, v in list(var_of.items()):
            if v == split:
                var_of[d] = f"\x7f\x7f{d}"
        cons = constraints()
        order_of_vars = topological(cons)
    members: dict[str, list[str]] = {}
    for n, v in var_of.items():
        members.setdefault(v, []).append(n)

    def hop_weight(h: int) -> float:
        _, a, b = hops[h]
        return 1.0 if is_box[a] and is_box[b] else 4.0

    def solve(desired: dict[str, float], weight: dict[str, float]) -> dict[str, float]:
        block = {v: v for v in order_of_vars}
        inside = {v: [v] for v in order_of_vars}
        offset = {v: 0.0 for v in order_of_vars}
        wsum = {v: weight[v] for v in order_of_vars}
        wpos = {v: weight[v] * desired[v] for v in order_of_vars}
        incoming: dict[str, list[tuple[str, str, float]]] = {v: [] for v in order_of_vars}
        for c in cons:
            incoming[c[1]].append(c)

        def x(v: str) -> float:
            b = block[v]
            return wpos[b] / wsum[b] + offset[v]

        for v in order_of_vars:
            b = block[v]
            while True:
                worst, most = None, 1e-12
                for u in inside[b]:
                    for left, right_var, gap in incoming[u]:
                        if block[left] != b:
                            violation = x(left) + gap - x(right_var)
                            if violation > most:
                                worst, most = (left, right_var, gap), violation
                if worst is None:
                    break
                left, right_var, gap = worst
                other = block[left]
                shift = offset[right_var] - gap - offset[left]
                for u in inside[other]:
                    offset[u] += shift
                    block[u] = b
                    wpos[b] += weight[u] * (desired[u] - offset[u])
                wsum[b] += wsum[other]
                inside[b] += inside.pop(other)
        return {v: x(v) for v in order_of_vars}

    def place_all() -> None:
        place_ports()
        for _ in range(_SWEEPS):
            desired, weight = {}, {}
            for v in order_of_vars:
                pulls = []
                for n in members[v]:
                    for h in hops_in[n]:
                        if var_of.get(hops[h][1]) != v:
                            centre = port[(h, 0)] - (port[(h, 1)] - cross_mid[n])
                            pulls.append((centre - rel[n], hop_weight(h)))
                    for h in hops_out[n]:
                        if var_of.get(hops[h][2]) != v:
                            centre = port[(h, 1)] - (port[(h, 0)] - cross_mid[n])
                            pulls.append((centre - rel[n], hop_weight(h)))
                total = sum(w for _, w in pulls)
                first = members[v][0]
                desired[v] = sum(p * w for p, w in pulls) / total if total else cross_mid[first] - rel[first]
                weight[v] = total or 0.01
            placed = solve(desired, weight)
            for n, v in var_of.items():
                cross_mid[n] = placed[v] + rel[n]
            place_ports()

    # Short vertical runs: pull a pass-through slot level, or stretch a box
    # into free room, so the hop runs straight.
    def free_room(n: str) -> tuple[float, float]:
        column = columns[rank[n]]
        k = position_in_column[n]
        lo = span(column[k - 1])[1] + sep(column[k - 1], n) if k else -math.inf
        hi = span(column[k + 1])[0] - sep(n, column[k + 1]) if k + 1 < len(column) else math.inf
        return lo, hi

    def side_of(n: str, end: int) -> list[int]:
        return hops_out[n] if end == 0 else hops_in[n]

    def try_move_port(n: str, h: int, end: int, level: float) -> bool:
        side = sorted(side_of(n, end), key=lambda g: (port[(g, end)], g))
        k = side.index(h)
        if k and level - port[(side[k - 1], end)] < pair_gap(side[k - 1], h) - 1e-9:
            return False
        if k + 1 < len(side) and port[(side[k + 1], end)] - level < pair_gap(h, side[k + 1]) - 1e-9:
            return False
        if not is_box[n]:
            lo_room, hi_room = free_room(n)
            if not lo_room <= level <= hi_room:
                return False
            cross_mid[n] = level
            for g in hops_in[n]:
                port[(g, 1)] = level
            for g in hops_out[n]:
                port[(g, 0)] = level
            return True
        lo, hi = span(n)
        new_lo, new_hi = min(lo, level - _PORT_MARGIN), max(hi, level + _PORT_MARGIN)
        lo_room, hi_room = free_room(n)
        if new_lo < lo_room - 1e-9 or new_hi > hi_room + 1e-9:
            return False
        cross_size[n], cross_mid[n] = new_hi - new_lo, (new_lo + new_hi) / 2
        port[(h, end)] = level
        return True

    def other_end(h: int, end: int) -> float:
        return port[(h, 1 - end)]

    def short_jogs(side: list[int], end: int) -> int:
        return sum(1 for h in side if 1e-9 < abs(port[(h, end)] - other_end(h, end)) < min_vertical)

    def stretch_side(n: str, end: int) -> None:
        side = side_of(n, end)
        before = short_jogs(side, end)
        if not before:
            return
        saved = (cross_size[n], cross_mid[n], {h: port[(h, end)] for h in side})
        other = 1 - end
        lo, hi = span(n)
        room_lo, room_hi = free_room(n)
        wanted = [other_end(h, end) for h in side]
        new_lo = max(min(lo, min(wanted) - _PORT_MARGIN), room_lo)
        new_hi = min(max(hi, max(wanted) + _PORT_MARGIN), room_hi)
        cross_size[n], cross_mid[n] = new_hi - new_lo, (new_lo + new_hi) / 2
        place_side(n, side, end, {h: other_end(h, end) for h in side})
        rest = side_of(n, other)
        if short_jogs(side, end) >= before or any(not new_lo <= port[(h, other)] <= new_hi for h in rest):
            cross_size[n], cross_mid[n] = saved[0], saved[1]
            for h, v in saved[2].items():
                port[(h, end)] = v

    def jog(h: int) -> float:
        return abs(port[(h, 0)] - port[(h, 1)])

    def set_slot(d: str, level: float) -> None:
        cross_mid[d] = level
        for g in hops_in[d]:
            port[(g, 1)] = level
        for g in hops_out[d]:
            port[(g, 0)] = level

    def snap_chain(e: int) -> None:
        slots = chains[e][1:-1]
        if not slots:
            return
        mine = [h for h, hop in enumerate(hops) if hop[0] == e]
        src, dst = chains[e][0], chains[e][-1]
        candidates = sorted({port[(mine[0], 0)], port[(mine[-1], 1)], *(cross_mid[d] for d in slots)})
        saved = {d: cross_mid[d] for d in slots}

        def box_state():
            return {n: (cross_size[n], cross_mid[n]) for n in (src, dst)}, dict(port)

        def restore(state):
            sizes, ports = state
            for n, (size, mid) in sizes.items():
                cross_size[n], cross_mid[n] = size, mid
            port.clear()
            port.update(ports)

        def attempt(level: float) -> bool:
            if not all(free_room(d)[0] - 1e-9 <= level <= free_room(d)[1] + 1e-9 for d in slots):
                return False
            for d in slots:
                set_slot(d, level)
            if 1e-9 < jog(mine[0]) < min_vertical:
                try_move_port(src, mine[0], 0, level)
            if 1e-9 < jog(mine[-1]) < min_vertical:
                try_move_port(dst, mine[-1], 1, level)
            return True

        start = box_state()
        best = None
        for level in candidates:
            if attempt(level):
                score = (sum(1 for h in mine if 1e-9 < jog(h) < min_vertical),
                         sum(1 for h in mine if jog(h) > 1e-9),
                         sum(abs(level - saved[d]) for d in slots))
                if best is None or score < best[0]:
                    best = (score, level)
            restore(start)
            for d in slots:
                set_slot(d, saved[d])
        if best is None and max(saved.values()) - min(saved.values()) < _SNAP_SLACK:
            best = ((), sum(saved.values()) / len(saved))
            for d in slots:
                set_slot(d, best[1])
        elif best is not None:
            attempt(best[1])

    def snap_all() -> None:
        for _ in range(4):
            for e in range(len(edges)):
                snap_chain(e)
            for column in columns:
                for n in column:
                    if is_box[n]:
                        stretch_side(n, 1)
                        stretch_side(n, 0)
            for h, (_, a, b) in enumerate(hops):
                if 1e-9 < jog(h) < min_vertical:
                    if not (is_box[b] and try_move_port(b, h, 1, port[(h, 0)])):
                        if not (is_box[a] and try_move_port(a, h, 0, port[(h, 1)])) and jog(h) < _SNAP_SLACK:
                            if is_box[b]:
                                port[(h, 1)] = port[(h, 0)]
                            elif is_box[a]:
                                port[(h, 0)] = port[(h, 1)]

    # A jog that no free room could fix: grow the box anyway and place again,
    # so its neighbours make way.
    place_all()
    for _ in range(3):
        snap_all()
        grown = False
        for h, (_, a, b) in enumerate(hops):
            if not 1e-9 < jog(h) < min_vertical:
                continue
            growths = []
            for n, end in ((b, 1), (a, 0)):
                if is_box[n]:
                    level = port[(h, 1 - end)]
                    lo, hi = span(n)
                    new_lo, new_hi = min(lo, level - _PORT_MARGIN), max(hi, level + _PORT_MARGIN)
                    growths.append(((new_hi - new_lo) - (hi - lo), n, new_hi - new_lo))
            if growths:
                need, n, size = min(growths)
                if need > 1e-9:
                    cross_size[n] = size
                    grown = True
        if not grown:
            break
        cons = constraints()
        place_all()
    snap_all()

    # Lock every hop that is level, or nearly so: its two ends join one rigid
    # group, as long as that keeps each column in order and the groups acyclic.
    # Placing again then keeps those hops exactly level.
    for _, h in sorted((jog(h), h) for h, (_, a, b) in enumerate(hops) if jog(h) < min_vertical):
        _, a, b = hops[h]
        ga, gb = var_of[a], var_of[b]
        if ga == gb:
            continue
        delta = rel[a] + (port[(h, 0)] - cross_mid[a]) - rel[b] - (port[(h, 1)] - cross_mid[b])
        moved = sorted(n for n, g in var_of.items() if g == gb)
        saved = {n: (var_of[n], rel[n]) for n in moved}
        for n in moved:
            var_of[n], rel[n] = ga, rel[n] + delta
        group = [n for n, g in var_of.items() if g == ga]
        ok = all(
            rel[v] - rel[u] >= least_distance(u, v) - 1e-9
            for u in group for v in group
            if rank[u] == rank[v] and position_in_column[u] < position_in_column[v]
        )
        trial = constraints() if ok else []
        order = topological(trial) if ok else None
        if order is None:
            for n, (g, offset) in saved.items():
                var_of[n], rel[n] = g, offset
        else:
            cons, order_of_vars = trial, order
    members = {}
    for n, v in var_of.items():
        members.setdefault(v, []).append(n)
    place_all()
    snap_all()

    for h, (_, a, b) in enumerate(hops):
        if not 1e-9 < jog(h) < min_vertical:
            continue
        options = []
        for n, end in ((b, 1), (a, 0)):
            if not is_box[n]:
                continue
            here, there = port[(h, end)], port[(h, 1 - end)]
            for level in (there - min_vertical, there + min_vertical):
                options.append((abs(level - here), n, end, level))
        for _, n, end, level in sorted(options):
            saved = (cross_size[n], cross_mid[n], port[(h, end)])
            if try_move_port(n, h, end, level):
                break
            cross_size[n], cross_mid[n], port[(h, end)] = saved

    # Main placement: gaps wide enough for their labels and turns.
    def text_of(n: str) -> str:
        return texts.get(n, n)

    def round_up(v: float) -> float:
        return round(math.ceil(v * 1000) / 1000 + 0.001, 3)

    box_size: dict[str, tuple[float, float]] = {}
    for n in nodes:
        if not is_box[n]:
            continue
        if right:
            box_size[n] = (round_up(natural[n][0]), round_up(cross_size[n]))
        else:
            width = round_up(cross_size[n])
            box_size[n] = (width, round_up(text_box_size(text_of(n), _FONT_SIZE, width, -1, _UNIT)[1]))
    main_size = {n: (box_size[n][0] if right else box_size[n][1]) if is_box[n] else 0.0 for n in nodes}

    turns_in_gap: dict[int, list[int]] = {}
    labels_in_gap: dict[int, list[int]] = {}
    for h, (e, a, _) in enumerate(hops):
        if abs(port[(h, 0)] - port[(h, 1)]) > 1e-9:
            turns_in_gap.setdefault(rank[a], []).append(h)
        if h in labelled_hop:
            labels_in_gap.setdefault(rank[a], []).append(h)

    gaps = []
    for r in range(len(columns)):
        widest = max((label_size(labelled_hop[h])[0] for h in labels_in_gap.get(r, [])), default=0.0)
        turns = len(turns_in_gap.get(r, []))
        need = _MAIN_GAP
        if widest:
            need = max(need, widest + 4 * _LABEL_GAP + 2 * _PORT_GAP)
        if turns:
            clear_of_labels = widest + 4 * _LABEL_GAP if widest else 0.0
            need = max(need, 2 * min_stub + (turns - 1) * _TRACK_GAP + clear_of_labels)
        gaps.append(need)

    extent = [max(main_size[n] for n in column) for column in columns]
    main_mid: dict[int, float] = {}
    pos = 0.0
    for r in range(len(columns)):
        main_mid[r] = pos + extent[r] / 2
        pos += extent[r] + gaps[r]

    def main_span(n: str) -> tuple[float, float]:
        return main_mid[rank[n]] - main_size[n] / 2, main_mid[rank[n]] + main_size[n] / 2

    def gap_bounds(r: int) -> tuple[float, float]:
        return main_mid[r] + extent[r] / 2, main_mid[r + 1] - extent[r + 1] / 2

    # Labels sit in the gap after the arrow's source, on the label side of its
    # first run.
    label_rects: dict[int, tuple[float, float, float, float]] = {}
    for h, label in labelled_hop.items():
        lw, lh = label_size(label)
        r = rank[hops[h][1]]
        left, right_edge = gap_bounds(r)
        m = left + 2 * _LABEL_GAP + lw / 2 if turns_in_gap.get(r) else (left + right_edge) / 2
        level = port[(h, 0)]
        if right:
            label_rects[h] = (m - lw / 2, m + lw / 2, level - label_near - lh, level - label_near)
        else:
            label_rects[h] = (m - lw / 2, m + lw / 2, level + label_near, level + label_near + lh)

    def touches(rect, m0, m1, c0, c1, pad=_LABEL_GAP) -> bool:
        ma, mb, ca, cb = rect
        m0, m1 = sorted((m0, m1))
        c0, c1 = sorted((c0, c1))
        return m0 < mb + pad and ma - pad < m1 and c0 < cb + pad and ca - pad < c1

    # Turns: each turning hop gets its own vertical track in the gap, ordered so
    # parallel hops nest, clear of labels.
    track: dict[int, float] = {}
    for r, turning in turns_in_gap.items():
        left, right_edge = gap_bounds(r)
        lo, hi = left + min_stub, right_edge - min_stub
        if labels_in_gap.get(r):
            lo = max(lo, max(label_rects[h][1] for h in labels_in_gap[r]) + 2 * _LABEL_GAP)

        def key(h: int) -> tuple[int, float, int]:
            s, t = port[(h, 0)], port[(h, 1)]
            return (0, -s, h) if t > s else (1, s, h)

        turning.sort(key=key)
        rects = [label_rects[h] for h in labels_in_gap.get(r, [])]

        def blocked(h: int, x: float) -> bool:
            s, t = port[(h, 0)], port[(h, 1)]
            for g in labels_in_gap.get(r, []):
                rect = label_rects[g]
                if touches(rect, x, x, s, t):
                    return True
                if g != h and touches(rect, left, x, s, s):
                    return True
                if touches(rect, x, right_edge, t, t):
                    return True
            return False

        n = len(turning)
        prev = -math.inf
        for k, h in enumerate(turning):
            ideal = (lo + hi) / 2 if n == 1 else lo + (hi - lo) * k / (n - 1)
            start = max(ideal, prev + _TRACK_GAP) if prev > -math.inf else ideal
            candidates = sorted(
                {round(start + i * 0.05, 4) for i in range(-40, 81)}
                | {round(rect[1] + 2 * _LABEL_GAP, 4) for rect in rects}
                | {round(rect[0] - 2 * _LABEL_GAP, 4) for rect in rects},
                key=lambda x: abs(x - start),
            )
            fits = [x for x in candidates if lo <= x <= hi and x >= prev + _TRACK_GAP - 1e-9 and not blocked(h, x)]
            track[h] = fits[0] if fits else min(max(start, lo), hi)
            prev = track[h]

    # Arrow paths.
    paths: list[list[tuple[float, float]]] = []
    for e, chain in enumerate(chains):
        pts = [(main_span(chain[0])[1], port[(first_hop[e], 0)])]
        for h in (g for g, hop in enumerate(hops) if hop[0] == e):
            _, a, b = hops[h]
            s, t = port[(h, 0)], port[(h, 1)]
            if abs(s - t) > 1e-9:
                pts += [(track[h], s), (track[h], t)]
        pts.append((main_span(chain[-1])[0], port[(max(g for g, hop in enumerate(hops) if hop[0] == e), 1)]))
        paths.append(pts)

    cross_lo = min(span(n)[0] for n in nodes if is_box[n])
    cross_hi = max(span(n)[1] for n in nodes if is_box[n])
    return {
        "fields": fields,
        "direction": direction,
        "boxes": {n: (*main_span(n), *span(n)) for n in nodes if is_box[n]},
        "box_size": box_size,
        "centers": {n: ((main_span(n)[0] + main_span(n)[1]) / 2, cross_mid[n]) for n in nodes if is_box[n]},
        "texts": {n: text_of(n) for n in nodes if is_box[n]},
        "edges": edges,
        "paths": paths,
        "labels": {first: (edges[e][2], label_rects[first]) for e, first in first_hop.items() if first in label_rects},
        "shift": ((pos - gaps[-1]) / 2, (cross_lo + cross_hi) / 2),
    }


def flowchart(data: str) -> str:
    """Boxes laid out in columns, drawn all at once on the canvas.

    Each line of `data` is one arrow, comma separated:

        from, to, arrow label

    The arrow label is optional. `from` and `to` are box ids; either may give
    the box's text as `id = text drawn on box`. The text is given once, and
    the id alone refers to the box after that. A box that never gets text
    shows its id. Quote a field that contains a comma. The order of the lines
    never changes the chart.

    An optional frontmatter block at the top sets the heading and the
    direction the chart runs in, `right` (the default) or `down`:

        ---
        title: Two-layer MLP
        direction: right
        ---

    A box's column is the longest chain of arrows leading into it. An arrow
    that skips columns holds a slot in each column it crosses and runs between
    the boxes there. Boxes in a column are ordered to cut down crossings, then
    placed so arrows run straight where they can. A box is its text's size,
    grown to fit its arrow ends and labels, and stretched into free room when
    that turns a short jog into a straight run. Arrows only run horizontally
    and vertically; each turn happens in the gap between two columns, on its
    own track, clear of the labels. A label sits in the gap after its arrow's
    source, just beside the arrow's first run.
    """
    layout = _layout(data)
    right = layout["direction"] == "right"
    main_shift, cross_shift = layout["shift"]

    def to_canvas(main: float, cross: float) -> tuple[float, float]:
        m, c = round(main - main_shift, 3) + 0, round(cross - cross_shift, 3) + 0
        return (m, -c + 0) if right else (c, -m + 0)

    lines = []
    for k, (n, (m, c)) in enumerate(sorted(layout["centers"].items(), key=lambda item: item[1]), start=1):
        x, y = to_canvas(m, c)
        w, h = layout["box_size"][n]
        lines.append(f"    box_{k} = gm.annotate_text_box({_q(layout['texts'][n])}, {x}, {y}, {_FONT_SIZE}, {w}, {h})")

    points: list[str] = []
    arrows = []
    for k, path in enumerate(layout["paths"], start=1):
        names = []
        for j, (m, c) in enumerate(path, start=1):
            x, y = to_canvas(m, c)
            name = f"arrow_{k}_{j}"
            lines.append(f"    {name} = gm.point({x}, {y})")
            names.append(name)
        points += names
        arrows.append(f"    gm.annotate_polyline_arrow({', '.join(names)})")
    lines.append(f"    gm.hide({', '.join(points)})")
    lines += arrows
    for label, (m0, m1, c0, c1) in layout["labels"].values():
        x, y = to_canvas((m0 + m1) / 2, (c0 + c1) / 2)
        lines.append(f"    gm.annotate_text_box({_q(label)}, {x}, {y}, {_LABEL_FONT_SIZE})")

    code = "\n".join([
        "with gm.onpageload():",
        '    gm.scalar(0, out="grid-opacity")',
        f'    gm.text({_q(_BACKGROUND)}, out="grid-bg-color")',
        *lines,
    ])
    title = layout["fields"].get("title", "")
    heading = f"# {title}\n\n" if title else ""
    return f"{heading}```pygeomatic\n{code}\n```\n"
