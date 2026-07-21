"""gm.tex — texatlas bindings recorder (addressable, reactively styled KaTeX).

A `$$[#id]$$` formula in a markdown article is made addressable and reactive
NOT by any DSL command but by declarative *bindings* recorded here: a schema
slot can show a store node's live value (`energy.int.upper.bind(a)`), and matrix
cells can be highlighted by selectors built from store nodes
(`M.highlight(M.rows().eq(r), color="pink")`).

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


def _as_selector(value: "Selector") -> dict:
    if not isinstance(value, Selector):
        raise TexError(f"expected a selector, got {type(value).__name__}")
    return value._json_


class _Region(Selector):
    """A selector that remembers which formula it targets, so it can paint
    itself directly: `M[3:, 4:].highlight()`, `M.triu().highlight(color=...)`.
    It IS a `Selector`, so it still composes (`M[3:, :] | M[:, 4:]`) and can be
    passed to `M.highlight(...)`; the combinators keep the target so the result
    stays paintable."""

    def __init__(self, tex_id: str, json: dict) -> None:
        super().__init__(json)
        self._tex_id = tex_id

    def highlight(self, *, color: str = "COLOR-YELLOW") -> None:
        """Paint this region on its formula, in `color` (see `Tex.highlight`)."""
        _bindings(self._tex_id)["highlights"].append(
            {"selector": self._json_, "color": _resolve_color(color)}
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
# Tex — the callable matching a $$[#id]$$ formula
# ---------------------------------------------------------------------------


class Tex:
    """Handle to a `$$[#id]$$` formula. Descend into a slot family to bind a
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

    def rows(self) -> AxisExpr:
        """The cell's row index, as an axis expression."""
        return _NamedAxis("row")

    def cols(self) -> AxisExpr:
        """The cell's column index, as an axis expression."""
        return _NamedAxis("col")

    def highlight(self, selector: Selector, *, color: str = "COLOR-YELLOW") -> None:
        """Paint the cells the selector weights, in `color` (a palette name is
        resolved to hex here; any other CSS color passes through)."""
        _bindings(self.id)["highlights"].append(
            {"selector": _as_selector(selector), "color": _resolve_color(color)}
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
    """A handle to the `$$[#id]$$` formula in the current article, for binding
    values and highlights to it. Its bindings record on the active store's
    texatlas channel, harvested (not emitted) into the compiled article."""
    if not isinstance(tex_id, str) or not tex_id:
        raise TexError(f"tex id must be a non-empty string, got {tex_id!r}")
    return Tex(tex_id)


# ---------------------------------------------------------------------------
# Recording + harvest
# ---------------------------------------------------------------------------


def _bindings(tex_id: str) -> dict:
    return current_store().tex_bindings.setdefault(tex_id, {"values": [], "highlights": []})


def harvest_tex_bindings(store=None) -> dict:
    """The session's recorded texatlas bindings as the wire manifest
    `{ texId: { "values": [...], "highlights": [...] } }` — the exact JSON the
    TypeScript runtime consumes (empty arrays and formulas with no bindings are
    dropped). This is how the publish compiler snapshots bindings into an
    article without the author calling any emit; it is the tex analogue of
    `gm.emit()` for the command tape."""
    store = store or current_store()
    manifest: dict = {}
    for tex_id, b in store.tex_bindings.items():
        entry = {}
        if b["values"]:
            entry["values"] = b["values"]
        if b["highlights"]:
            entry["highlights"] = b["highlights"]
        if entry:
            manifest[tex_id] = entry
    return manifest
