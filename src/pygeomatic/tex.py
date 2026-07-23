"""gm.tex — texatlas bindings recorder (addressable, reactively styled KaTeX).

A `$$…$$` formula in a markdown article (given an id by a `%id:` line as its
first line) is made addressable and reactive
NOT by any DSL command but by declarative *bindings* recorded here. Three
effects, all driven by *changing a store node* (reassigning it — `b = gm.bool_(True)`,
`k = gm.scalar(1)` — or `gm.animate(k, 3)` — in a CommandLink):

- **value** — a schema slot shows a store node's live value
  (`energy.int.upper.bind(a)`);
- **highlight** — matrix cells painted a color by a selector over store nodes
  (`M.highlight(M.rows().eq(r), color="pink")`);
- **reveal** — a part of the formula fades in when a node says so: an
  over/underbrace (`t.underbrace.reveal(b)`), a derivation line-by-line
  (`d.rows().reveal(rows < k)`), or a matrix's rows/columns
  (`M.reveal(M.cols() < k)`). Same selector machine as highlight, painting
  opacity instead of color.

Three properties define the shape (see the texatlas design memo):

1. **Bindings are not DSL.** They are recorded on a channel separate from the
   command tape (`Store.tex_bindings`); `gm.emit()` never sees them and there is
   no `\\tex-*` keyword. Dynamic behavior flows exclusively through the *store
   nodes* a binding references — `\\scalar r` / `\\animate r` drive the node and
   the bound slot is just another subscriber. To gate a highlight behind a
   click, `.scale()` it by a node and CommandLink that node — never a tex op.

2. **Python never parses LaTeX and never touches the DOM.** Only symbolic
   addresses cross the wire (`"int.upper"`, a selector expression tree). Slot
   resolution against the KaTeX parse tree happens in the browser at mount time,
   so occurrence/empty-slot/ambiguity errors are raised *there* (or by a build
   validation step), not here. This module only validates what is knowable
   without the formula: that a family and its slots exist in the schema mirror.

3. **The schema registry is a finite set of typed slots**, mirrored from the
   browser's `schema.ts` — not an open query language. Register more with
   `register_tex_schema(...)`, exactly like `gm.load_extensions` grows the
   command registry.

The JSON these produce (`harvest_tex_bindings`) is the frozen wire contract with
the TypeScript runtime — keep it in sync with that repo's CONTRACT.md.
"""

from __future__ import annotations

import re
from typing import Optional, Union

from .nodes import GNode
from .store import current_store

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TexError(ValueError):
    """A texatlas binding could not be recorded (bad family, slot, or option)."""


# ---------------------------------------------------------------------------
# Schema registry — family → its bindable slot names
# ---------------------------------------------------------------------------
#
# Python only needs the slot NAMES (what the author writes: `int.upper`); the
# mapping of a slot to a KaTeX AST position (`upper` → the `sup` node) lives in
# the browser's schema.ts and never crosses the wire. `\int`/`\iint`/`\oint`
# are one family ("int") matched browser-side; here they are a single entry.

SCHEMA: dict[str, tuple[str, ...]] = {}


def register_tex_schema(family: str, slots: Union[tuple[str, ...], list[str]]) -> None:
    """Declare a bindable LaTeX command family and its slot names (mirroring the
    browser schema). Re-registering a family replaces its slots."""
    if not isinstance(family, str) or not re.match(r"[a-zA-Z][a-zA-Z0-9-]*\Z", family):
        raise TexError(
            f"invalid schema family {family!r}: must start with a letter and "
            "contain only letters, digits and dashes"
        )
    SCHEMA[family] = tuple(slots)


def _register_builtin_schema() -> None:
    # The families from the texatlas design memo. `body` is the integrand /
    # summand (`\arg`); browser schema.ts maps names to AST positions.
    register_tex_schema("int", ("lower", "upper", "body"))
    register_tex_schema("sum", ("lower", "upper", "body"))
    register_tex_schema("prod", ("lower", "upper", "body"))
    register_tex_schema("frac", ("num", "denom"))
    register_tex_schema("sqrt", ("body",))
    # Over/underbrace are one browser family (`horizBrace`, keyed off `isOver`);
    # here they are two named families with the same slots. The BARE family
    # address (`t.underbrace`) is the annotation — brace glyph + label; the body
    # stays visible. `.body` / `.label` address just those parts. Used for the
    # reveal effect (`t.underbrace.reveal(gate)`), not for value binding.
    register_tex_schema("underbrace", ("body", "label"))
    register_tex_schema("overbrace", ("body", "label"))


_register_builtin_schema()


# ---------------------------------------------------------------------------
# Wire helpers
# ---------------------------------------------------------------------------

_FMT_RE = re.compile(r"\.\d+f\Z|d\Z")


def _node_id(value: Union[GNode, str], *, what: str) -> str:
    """The store id of a node argument, validated to exist in the active store."""
    if isinstance(value, GNode):
        node_id = value.id
        if node_id is None:
            raise TexError(
                f"{what} node has no id yet — it was not produced by a pygeomatic call"
            )
    elif isinstance(value, str):
        node_id = value
    else:
        raise TexError(
            f"{what} must be a geomatic node or a node id string, got {type(value).__name__}"
        )
    if node_id not in current_store().nodes:
        raise TexError(
            f"no node {node_id!r} in the active store to use as {what} — define it "
            "before binding it (a bound node must exist so the runtime env carries its value)"
        )
    return node_id


def _env_ref(value: Union[GNode, str, int, float], *, what: str) -> dict:
    """An `EnvRef`: a store node (`{node}`) or a numeric literal (`{const}`)."""
    if isinstance(value, bool):  # bool is an int subclass — reject before the number branch
        raise TexError(f"{what} must be a node or a number, not a bool")
    if isinstance(value, (int, float)):
        return {"const": value}
    return {"node": _node_id(value, what=what)}


def _matrix_index(matrix: int) -> int:
    """Validate an author-supplied matrix occurrence index (a non-negative int).

    This is which matrix in a multi-matrix formula a highlight paints — see
    `Tex.highlight` for the source-order counting rule. Python never counts the
    matrices itself (it does not parse LaTeX); the author supplies the integer."""
    if isinstance(matrix, bool) or not isinstance(matrix, int) or matrix < 0:
        raise TexError(f"matrix index must be a non-negative int, got {matrix!r}")
    return matrix


def _highlight_entry(selector_json: dict, color: str, matrix: int) -> dict:
    """A `HighlightBinding` wire entry. `matrix` (occurrence index) is omitted
    when 0 so single-matrix formulas stay byte-identical to the v1 output."""
    entry: dict = {"selector": selector_json, "color": _resolve_color(color)}
    if _matrix_index(matrix):
        entry["matrix"] = matrix
    return entry


def _align_index(align: int) -> int:
    """Validate an author-supplied align occurrence index (a non-negative int).

    This is which equation-layout array (`aligned`/`align`/`split`/`alignat`/
    `gather`/`CD`) in the formula a reveal fades line-by-line, counted in source
    order — the arrays that `matrix`/highlight deliberately SKIP. Python does not
    parse the LaTeX; the author supplies the integer (default 0)."""
    if isinstance(align, bool) or not isinstance(align, int) or align < 0:
        raise TexError(f"align index must be a non-negative int, got {align!r}")
    return align


def _reveal_mode(mode: str) -> str:
    """Validate a reveal paint mode. `"fade"` (default) paints opacity and keeps
    the layout; `"collapse"` also removes the slot's space (avoid it for matrix
    cells — it breaks the grid/brackets)."""
    if mode not in ("fade", "collapse"):
        raise TexError(f"reveal mode must be 'fade' or 'collapse', got {mode!r}")
    return mode


def _reveal_entry(target: dict, selector: "Selector", mode: str) -> dict:
    """A `RevealBinding` wire entry: exactly one target descriptor
    (`slot` | `align` | `matrix`) plus a selector giving each cell an opacity
    weight in [0, 1]. `mode` is omitted when `"fade"` (the default) so the wire
    JSON stays minimal. A bare gate node/bool is accepted as the selector (the
    `{node}` leaf — the degenerate all-or-nothing case)."""
    entry: dict = dict(target)
    entry["selector"] = _as_selector(selector)
    if _reveal_mode(mode) != "fade":
        entry["mode"] = mode
    return entry


def _resolve_color(color: str) -> str:
    """Resolve a palette name to its hex before it crosses the wire; pass any
    other CSS color string (`#f472b6`, `pink`, `rgb(...)`) through unchanged."""
    if not isinstance(color, str) or not color:
        raise TexError(f"color must be a non-empty string, got {color!r}")
    if color.startswith("#"):
        return color
    import pygeomatic as gm  # PALETTE is built at import end; present at call time

    palette: dict[str, str] = getattr(gm, "PALETTE", {})
    key = color if color.startswith("COLOR-") else f"COLOR-{color.upper()}"
    return palette.get(key, color)


# ---------------------------------------------------------------------------
# Selector expression trees  (pure (address, env) -> weight in [0, 1])
# ---------------------------------------------------------------------------


class AxisExpr:
    """A per-cell axis value: `row`, `col`, or arithmetic over them. Serializes
    to the `AxisExpr` wire shape."""

    def add(self, other: Union["AxisExpr", int, float]) -> "AxisExpr":
        return _AxisBinOp("add", self, _as_axis(other))

    def sub(self, other: Union["AxisExpr", int, float]) -> "AxisExpr":
        return _AxisBinOp("sub", self, _as_axis(other))

    __add__ = add
    __sub__ = sub

    def eq(self, value: Union[GNode, str, int, float]) -> "Selector":
        return Selector({"op": "eq", "axis": self._json(), "value": _env_ref(value, what="selector value")})

    def ge(self, value: Union[GNode, str, int, float]) -> "Selector":
        return Selector({"op": "ge", "axis": self._json(), "value": _env_ref(value, what="selector value")})

    def le(self, value: Union[GNode, str, int, float]) -> "Selector":
        return Selector({"op": "le", "axis": self._json(), "value": _env_ref(value, what="selector value")})

    def gt(self, value: Union[GNode, str, int, float]) -> "Selector":
        return Selector({"op": "gt", "axis": self._json(), "value": _env_ref(value, what="selector value")})

    def lt(self, value: Union[GNode, str, int, float]) -> "Selector":
        return Selector({"op": "lt", "axis": self._json(), "value": _env_ref(value, what="selector value")})

    # Rich comparison sugar: `axis == v` / `>= v` / `<= v` / `> v` / `< v` are the
    # `.eq/.ge/.le/.gt/.lt` wire ops. Strict `>`/`<` are first-class in the runtime
    # (CONTRACT.md), so a node bound is fine — no integer shift here.
    def __eq__(self, value: object) -> "Selector":  # type: ignore[override]
        return self.eq(value)  # type: ignore[arg-type]

    def __ge__(self, value: Union[GNode, str, int, float]) -> "Selector":
        return self.ge(value)

    def __le__(self, value: Union[GNode, str, int, float]) -> "Selector":
        return self.le(value)

    def __gt__(self, value: Union[GNode, str, int, float]) -> "Selector":
        return self.gt(value)

    def __lt__(self, value: Union[GNode, str, int, float]) -> "Selector":
        return self.lt(value)

    def __radd__(self, other: Union[int, float]) -> "AxisExpr":  # 1 + rows
        return _as_axis(other).add(self)

    def __rsub__(self, other: Union[int, float]) -> "AxisExpr":  # 1 - rows
        return _as_axis(other).sub(self)

    # `__eq__` makes instances non-hashable by Python's rules; that is correct
    # here (an axis is an expression builder, never a dict key or set member).
    __hash__ = None  # type: ignore[assignment]

    def _json(self) -> dict:  # pragma: no cover - overridden
        raise NotImplementedError


class _NamedAxis(AxisExpr):
    def __init__(self, axis: str) -> None:
        self._axis = axis

    def _json(self) -> dict:
        return {"axis": self._axis}


class _AxisConst(AxisExpr):
    def __init__(self, value: Union[int, float]) -> None:
        self._value = value

    def _json(self) -> dict:
        return {"const": self._value}


class _AxisBinOp(AxisExpr):
    def __init__(self, op: str, a: AxisExpr, b: AxisExpr) -> None:
        self._op, self._a, self._b = op, a, b

    def _json(self) -> dict:
        return {"op": self._op, "a": self._a._json(), "b": self._b._json()}


def _as_axis(value: Union[AxisExpr, int, float]) -> AxisExpr:
    if isinstance(value, AxisExpr):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TexError(f"axis operand must be an axis expression or a number, got {value!r}")
    return _AxisConst(value)


# Free axis handles — an axis carries no reference to any formula, so these are
# shared module singletons (immutable: every operator returns a NEW node). Write
# `rows`/`cols`/`dim(i)` directly instead of `M.rows()`/`M.cols()`.
_AXIS_NAMES: tuple[str, ...] = ("row", "col")


def dim(i: int) -> AxisExpr:
    """The `i`-th grid axis as an expression (`dim(0)` == `rows`, `dim(1)` == `cols`).

    Matrices are 2-D browser-side, so only dims 0 and 1 resolve today; higher
    ranks await browser-schema support (keeping the wire's `row`/`col` names)."""
    if isinstance(i, bool) or not isinstance(i, int) or i < 0:
        raise TexError(f"axis index must be a non-negative int, got {i!r}")
    if i >= len(_AXIS_NAMES):
        raise TexError(
            f"axis {i} is unsupported: matrices are 2-D browser-side (dims 0 and 1); "
            "rank > 2 awaits browser-schema support"
        )
    return _NamedAxis(_AXIS_NAMES[i])


rows: AxisExpr = _NamedAxis("row")
cols: AxisExpr = _NamedAxis("col")


class _TexAxis(_NamedAxis):
    """A row/col axis that remembers its formula, returned by `t.rows()` /
    `t.cols()`. It behaves exactly like the free `rows`/`cols` axes for building
    selectors (`t.rows().eq(r)`), and additionally carries `.reveal(...)` to fade
    in an equation-layout / derivation block line-by-line (the `align` target).
    The axis identity does not enter the align target — the whole aligned block
    is the target and the selector (e.g. `rows < k`) picks which lines show."""

    def __init__(self, tex_id: str, axis: str) -> None:
        super().__init__(axis)
        self._tex_id = tex_id

    def reveal(
        self, selector: "Selector", *, align: int = 0, mode: str = "fade"
    ) -> None:
        """Progressively reveal the lines of an equation-layout / derivation
        block: `d.rows().reveal(rows < k)` shows `k` lines (`k = 0` shows none).

        `align` is the 0-based occurrence index of which equation-layout array to
        reveal (source order, counting only `aligned`/`align`/`split`/`alignat`/
        `gather`/`CD` — the arrays highlight/`matrix` skip); default 0. `mode` is
        `"fade"` (opacity, keeps layout) or `"collapse"` (also removes space)."""
        _bindings(self._tex_id)["reveals"].append(
            _reveal_entry({"align": _align_index(align)}, selector, mode)
        )


class Selector:
    """A highlight selector: `(cell, env) -> weight`. Combine with `and_`/`or_`
    (min/max) or fade the whole selection with `scale`."""

    def __init__(self, json: dict) -> None:
        self._json_ = json

    def and_(self, other: "Selector") -> "Selector":
        return Selector({"op": "and", "a": self._json_, "b": _as_selector(other)})

    def or_(self, other: "Selector") -> "Selector":
        return Selector({"op": "or", "a": self._json_, "b": _as_selector(other)})

    def scale(self, by: Union[GNode, str, int, float]) -> "Selector":
        return Selector({"op": "scale", "sel": self._json_, "by": _env_ref(by, what="scale factor")})

    __and__ = and_
    __or__ = or_

    def _json(self) -> dict:
        return self._json_


def _as_selector(value: Union["Selector", GNode, str]) -> dict:
    """The selector JSON for a value that is either a built `Selector` or a bare
    gate node/id. A bare node lowers to the `{node}` `SelectorExpr` leaf
    (`weight = clamp(0, v, 1)`), so a bool gate is expressible without a dummy
    comparison — e.g. `t.underbrace.reveal(b)` or `(rows == 2) & b`."""
    if isinstance(value, Selector):
        return value._json_
    if isinstance(value, (GNode, str)):
        return {"node": _node_id(value, what="selector gate")}
    raise TexError(
        f"expected a selector or a gate node, got {type(value).__name__}"
    )


class _Region(Selector):
    """A selector that remembers which formula it targets, so it can paint
    itself directly: `M[3:, 4:].highlight()`, `M.triu().highlight(color=...)`.
    It IS a `Selector`, so it still composes (`M[3:, :] | M[:, 4:]`) and can be
    passed to `M.highlight(...)`; the combinators keep the target so the result
    stays paintable."""

    def __init__(self, tex_id: str, json: dict) -> None:
        super().__init__(json)
        self._tex_id = tex_id

    def highlight(self, *, color: str = "COLOR-YELLOW", matrix: int = 0) -> None:
        """Paint this region on its formula, in `color`, on the `matrix`-th
        matrix of the formula (see `Tex.highlight` for both)."""
        _bindings(self._tex_id)["highlights"].append(
            _highlight_entry(self._json_, color, matrix)
        )

    def and_(self, other: "Selector") -> "_Region":
        return _Region(self._tex_id, {"op": "and", "a": self._json_, "b": _as_selector(other)})

    def or_(self, other: "Selector") -> "_Region":
        return _Region(self._tex_id, {"op": "or", "a": self._json_, "b": _as_selector(other)})

    def scale(self, by: Union[GNode, str, int, float]) -> "_Region":
        return _Region(self._tex_id, {"op": "scale", "sel": self._json_, "by": _env_ref(by, what="scale factor")})

    __and__ = and_
    __or__ = or_


# ---------------------------------------------------------------------------
# Slot addressing — energy.int.upper.bind(a)
# ---------------------------------------------------------------------------


class _Slot:
    """A concrete slot address (`int.upper`, `int[1].lower`), bindable to a node."""

    def __init__(self, tex_id: str, address: str) -> None:
        self._tex_id = tex_id
        self._address = address

    def bind(
        self,
        node: Union[GNode, str],
        *,
        show: str = "value",
        fmt: Optional[str] = None,
    ) -> None:
        """Link this slot to a store node. `show="value"` (default) substitutes
        the node's value into the slot; `show="symbol"` registers the link
        without changing the rendered glyph. `fmt` is a number format
        (`".2f"`, `"d"`, or omit to trim to <=4 dp)."""
        if show not in ("value", "symbol"):
            raise TexError(f"show must be 'value' or 'symbol', got {show!r}")
        if fmt is not None and not _FMT_RE.fullmatch(fmt):
            raise TexError(
                f"invalid fmt {fmt!r}: use '.Nf' (fixed), 'd' (round to int), or omit"
            )
        node_id = _node_id(node, what="bound")
        entry: dict = {"slot": self._address, "node": node_id}
        if show != "value":
            entry["show"] = show
        if fmt is not None:
            entry["fmt"] = fmt
        _bindings(self._tex_id)["values"].append(entry)

    def reveal(self, selector: "Selector", *, mode: str = "fade") -> None:
        """Fade this slot in when the `selector` says so (opacity from its weight
        in [0, 1]). A bare gate node/bool is the all-or-nothing case
        (`t.underbrace.label.reveal(b)`); pass a real selector for a progressive
        sweep. `mode` is `"fade"` (default, keeps layout) or `"collapse"` (also
        removes the slot's space). For a bare over/underbrace address
        (`t.underbrace.reveal(b)`) the browser reveals the brace glyph + label
        while the body stays visible; `.label` / `.body` address just that part."""
        _bindings(self._tex_id)["reveals"].append(
            _reveal_entry({"slot": self._address}, selector, mode)
        )


class _Family:
    """A LaTeX command family occurrence (`tex.int`, `tex.ints[1]`). Bind the
    whole group directly (`.bind`) or descend into a named slot (`.upper`)."""

    def __init__(self, tex_id: str, family: str, index: Optional[int]) -> None:
        self._tex_id = tex_id
        self._family = family
        self._index = index

    @property
    def _base(self) -> str:
        return self._family if self._index is None else f"{self._family}[{self._index}]"

    def bind(self, node: Union[GNode, str], *, show: str = "value", fmt: Optional[str] = None) -> None:
        _Slot(self._tex_id, self._base).bind(node, show=show, fmt=fmt)

    def reveal(self, selector: "Selector", *, mode: str = "fade") -> None:
        """Reveal this whole family occurrence (the bare address, e.g. a brace's
        glyph + label — see `_Slot.reveal`)."""
        _Slot(self._tex_id, self._base).reveal(selector, mode=mode)

    def __getattr__(self, name: str) -> _Slot:
        # Only slot names reach here (real methods/attrs resolve first). Let
        # Python's own dunder probing (copy, pickling, ...) miss cleanly.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        slots = SCHEMA[self._family]
        if name not in slots:
            raise TexError(
                f"{self._family!r} has no slot {name!r}; valid slots: {', '.join(slots)}"
            )
        return _Slot(self._tex_id, f"{self._base}.{name}")


class _FamilyList:
    """The all-occurrences accessor (`tex.ints`): index to pick one (`tex.ints[1]`).

    Positional indexing is DISCOURAGED — editing the formula silently retargets
    it — but supported; prefer a single unambiguous match (`tex.int`) or a
    `\\cap{...}` capture."""

    def __init__(self, tex_id: str, family: str) -> None:
        self._tex_id = tex_id
        self._family = family

    def __getitem__(self, index: int) -> _Family:
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise TexError(f"occurrence index must be a non-negative int, got {index!r}")
        return _Family(self._tex_id, self._family, index)


# ---------------------------------------------------------------------------
# Tex — the callable matching a $$…$$ formula (by its `%id:` id)
# ---------------------------------------------------------------------------


class Tex:
    """Handle to a `$$…$$` formula (addressed by its `%id:` id). Descend into a slot family to bind a
    value (`t.int.upper.bind(a)`), or highlight matrix cells. Highlights have
    several ergonomic surfaces, all lowering to the same selector JSON (see
    docs/tex-highlight-ergonomics.md):

        t.highlight(rows == r, color="pink")     # free axes + operators (#1, #2)
        t.highlight(cols - rows > 0)             # cross-axis relation
        t[3:, 4:].highlight(color="green")       # numpy-style box (#3)
        t.triu().highlight()                     # named region (#6)

    `rows`/`cols`/`dim(i)` are module-level axis handles; `t.rows()`/`t.cols()`
    remain as aliases."""

    def __init__(self, tex_id: str) -> None:
        self.id = tex_id
        _bindings(tex_id)  # register the formula id eagerly (even with no bindings yet)

    # -- matrix highlights --------------------------------------------------

    def rows(self) -> _TexAxis:
        """The cell's row index, as an axis expression. Also carries `.reveal()`
        to fade in a derivation / equation-layout block line-by-line
        (`d.rows().reveal(rows < k)`)."""
        return _TexAxis(self.id, "row")

    def cols(self) -> _TexAxis:
        """The cell's column index, as an axis expression."""
        return _TexAxis(self.id, "col")

    def highlight(
        self, selector: Selector, *, color: str = "COLOR-YELLOW", matrix: int = 0
    ) -> None:
        """Paint the cells the selector weights, in `color` (a palette name is
        resolved to hex here; any other CSS color passes through).

        `matrix` is the 0-based occurrence index of which matrix in the formula
        to paint, in document (source) order — for a formula with more than one
        matrix. It defaults to 0 (the first / only matrix) and is omitted from
        the wire JSON when 0, so single-matrix formulas are unchanged. Each
        highlight carries its own index, so different highlights on one formula
        may target different matrices.

        Python does NOT parse the LaTeX to count matrices — you supply the
        integer — so you must count the SAME way the browser does: count only
        genuine matrices, in source order, SKIPPING equation-layout blocks.
        Skip: `aligned`, `align`, `split`, `alignat`, `gathered`, `gather`, `CD`.
        Count: `matrix` / `pmatrix` / `bmatrix` / `Bmatrix` / `vmatrix` /
        `Vmatrix` (and `*`-variants), plain `array`, `cases` / `dcases` /
        `rcases`, `smallmatrix`, `subarray`. So in
        `\\begin{aligned} ... \\begin{pmatrix}...\\end{pmatrix} ... \\end{aligned}`
        the pmatrix is matrix index 0 (the aligned wrapper is not counted). An
        out-of-range index is non-fatal browser-side (that highlight paints
        nothing; the rest still render), so no error is raised here."""
        _bindings(self.id)["highlights"].append(
            _highlight_entry(_as_selector(selector), color, matrix)
        )

    def reveal(
        self, selector: Selector, *, matrix: int = 0, mode: str = "fade"
    ) -> None:
        """Progressively reveal the rows/columns of a matrix — the same selector
        machine as `highlight`, painting opacity instead of color:
        `M.reveal(M.cols() < k)` shows `k` columns (`k = 0` shows none). A bare
        gate node/bool reveals the whole matrix all-or-nothing.

        `matrix` is the 0-based occurrence index of which matrix to reveal (same
        source-order counting rule as `highlight`'s `matrix=`; unlike highlight
        it is always written to the wire — it is the target discriminator). Only
        `mode="fade"` is supported: `collapse` would break the grid and brackets,
        so opacity keeps the shape stable while cells fade in."""
        if _reveal_mode(mode) == "collapse":
            raise TexError(
                "matrix reveal supports only mode='fade' — collapse would remove "
                "cell space and break the grid/brackets; opacity keeps the shape"
            )
        _bindings(self.id)["reveals"].append(
            _reveal_entry({"matrix": _matrix_index(matrix)}, selector, mode)
        )

    def __getitem__(self, key) -> _Region:
        """numpy-style cell region: `M[3:, 4:]`, `M[:, c]`, `M[r, ...]`.

        Each index constrains one axis (0 = row, 1 = col, ...): a slice is an
        axis-aligned box (`start` inclusive, `stop` exclusive), a bare int or
        node is an exact index (`==`). A node as a `start` or an index stays
        reactive — retarget it with `\\scalar` and the region follows. Omitted
        or `:` axes are unconstrained; a trailing `...` documents that. Returns a
        paintable region: `M[3:, 4:].highlight(color="pink")`. Cross-axis
        relations (diagonals, triangles) are NOT boxes — use the axis operators
        or `.diag()`/`.triu()`/`.tril()`."""
        keys = key if isinstance(key, tuple) else (key,)
        # Ellipsis is a no-op (unmentioned axes are already unconstrained), but
        # accepted at the end for readability. Use identity — `==` is overloaded.
        if any(k is Ellipsis for k in keys):
            if sum(1 for k in keys if k is Ellipsis) > 1 or keys[-1] is not Ellipsis:
                raise TexError(
                    "'...' is only supported as the final index "
                    "(trailing axes are unconstrained by default)"
                )
            keys = keys[:-1]
        parts: list[Selector] = []
        for axis_i, k in enumerate(keys):
            ax = dim(axis_i)
            if isinstance(k, slice):
                if k.step not in (None, 1):
                    raise TexError("slice step is not supported in a cell region")
                if k.start is not None:
                    parts.append(ax.ge(k.start))  # inclusive start (node or int)
                if k.stop is not None:
                    parts.append(ax.lt(k.stop))  # exclusive stop -> < stop (node or int)
            elif isinstance(k, GNode) or (isinstance(k, int) and not isinstance(k, bool)) or isinstance(k, str):
                parts.append(ax.eq(k))  # exact index
            else:
                raise TexError(f"unsupported cell index {k!r}: use an int, a node, a node id, or a slice")
        if not parts:
            raise TexError(
                "cell region selects the whole matrix — constrain at least one axis"
            )
        sel: Selector = parts[0]
        for p in parts[1:]:
            sel = sel.and_(p)
        return _Region(self.id, sel._json())

    def diag(self, k: int = 0) -> _Region:
        """The `k`-th diagonal (`col - row == k`; `k=0` is the main diagonal)."""
        return _Region(self.id, cols.sub(rows).eq(k)._json())

    def triu(self, k: int = 0) -> _Region:
        """Upper triangle from the `k`-th diagonal up (`col - row >= k`)."""
        return _Region(self.id, cols.sub(rows).ge(k)._json())

    def tril(self, k: int = 0) -> _Region:
        """Lower triangle from the `k`-th diagonal down (`col - row <= k`)."""
        return _Region(self.id, cols.sub(rows).le(k)._json())

    # -- slot families ------------------------------------------------------

    def __getattr__(self, name: str) -> Union[_Family, _FamilyList]:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        if name in SCHEMA:
            return _Family(self.id, name, index=None)
        if name.endswith("s") and name[:-1] in SCHEMA:
            return _FamilyList(self.id, name[:-1])
        known = ", ".join(sorted(SCHEMA)) or "none registered"
        raise TexError(
            f"unknown LaTeX slot family {name!r}; registered families: {known}. "
            "Register more with gm.register_tex_schema(...)."
        )


def tex(tex_id: str) -> Tex:
    """A handle to the `$$…$$` formula (by its `%id:` id) in the current article, for binding
    values and highlights to it. Its bindings record on the active store's
    texatlas channel, harvested (not emitted) into the compiled article."""
    if not isinstance(tex_id, str) or not tex_id:
        raise TexError(f"tex id must be a non-empty string, got {tex_id!r}")
    return Tex(tex_id)


# ---------------------------------------------------------------------------
# Recording + harvest
# ---------------------------------------------------------------------------


def _bindings(tex_id: str) -> dict:
    return current_store().tex_bindings.setdefault(
        tex_id, {"values": [], "highlights": [], "reveals": []}
    )


def harvest_tex_bindings(store=None) -> dict:
    """The session's recorded texatlas bindings as the wire manifest
    `{ texId: { "values": [...], "highlights": [...], "reveals": [...] } }` — the
    exact JSON the TypeScript runtime consumes (empty arrays and formulas with no
    bindings are dropped). This is how the publish compiler snapshots bindings
    into an article without the author calling any emit; it is the tex analogue
    of `gm.emit()` for the command tape."""
    store = store or current_store()
    manifest: dict = {}
    for tex_id, b in store.tex_bindings.items():
        entry = {}
        if b["values"]:
            entry["values"] = b["values"]
        if b["highlights"]:
            entry["highlights"] = b["highlights"]
        if b.get("reveals"):
            entry["reveals"] = b["reveals"]
        if entry:
            manifest[tex_id] = entry
    return manifest
