# `gm.tex` highlight ergonomics

Four sugar layers over the matrix-highlight selector, so you can paint cells of a
`$$[#id]$$` matrix without the `M.rows().sub(M.cols()).ge(0)` ceremony. **Every
form below lowers to the exact same selector JSON** the browser already consumes
(`eq` / `ge` / `le`, `AxisBinOp`, `and` / `or` / `scale`) — nothing here changes
the wire contract or the runtime. It is all recorded on the store's texatlas
channel and harvested by `harvest_tex_bindings`, never emitted as DSL.

Reminder on the model: a highlight is a predicate over a cell's **grid position**
(row/col index), never its rendered content. Reactivity comes from the store
nodes a selector references — drive them with `\scalar` / `\animate` and the
painted region follows. See [`tex.py`](../src/pygeomatic/tex.py) for the
recorder.

```python
import pygeomatic as gm
from pygeomatic import rows, cols, dim
```

---

## 1. Free axis handles: `rows`, `cols`, `dim(i)`

An axis carries no reference to any formula, so it's a shared module singleton —
write it directly instead of `M.rows()` / `M.cols()`. Immutable: every operator
returns a **new** node, so sharing one `rows` object across calls is safe.

```python
M = gm.tex("M")
M.highlight(rows == r)          # instead of M.highlight(M.rows().eq(r))
M.highlight(cols >= 2)
```

`dim(i)` is the generic, tensor-friendly form — `dim(0)` is `rows`, `dim(1)` is
`cols`:

```python
M.highlight(dim(0) == 1)
```

Matrices are 2-D browser-side, so only dims 0 and 1 resolve today; `dim(2)`
raises. Higher ranks await browser-schema support (the wire keeps its
`row` / `col` axis names regardless).

`M.rows()` / `M.cols()` remain as aliases — existing code is untouched.

---

## 2. Comparison & arithmetic operators

`AxisExpr` now supports infix operators that lower to the named methods:

| You write | Lowers to | Wire |
| --- | --- | --- |
| `rows == r` | `rows.eq(r)` | `{"op":"eq", …}` |
| `rows >= 2` | `rows.ge(2)` | `{"op":"ge", …}` |
| `rows <= 5` | `rows.le(5)` | `{"op":"le", …}` |
| `rows > 2` | `rows.ge(3)` | `{"op":"ge", value:3}` |
| `rows < 5` | `rows.le(4)` | `{"op":"le", value:4}` |
| `cols - rows` | `cols.sub(rows)` | `AxisBinOp("sub", …)` |
| `1 + rows` | `rows.__radd__` | `AxisBinOp("add", …)` |

So the upper-triangle selector reads naturally:

```python
M.highlight(cols - rows > 0, color="blue")   # col - row >= 1
```

### The two things to know

- **Strict `>` / `<` need an *integer* bound.** There is no `gt`/`lt` wire op;
  on integer grid indices `> v` is exactly `>= v+1`, so `__gt__`/`__lt__` shift
  the bound by one. That shift isn't representable for a **node** bound, so
  `rows > some_node` raises — use `rows >= some_node` (its inclusive edge is
  explicit). `==`, `>=`, `<=` accept a node or an int.
- **`==` returns a `Selector`, not a bool.** An `AxisExpr` is an expression
  builder, so it's intentionally non-hashable and never a dict key or set
  member. Don't compare two axes for value equality.

> These are single-expression operators, **not** a traced boolean predicate.
> `and` / `or` / `not` and chained comparisons (`2 < rows < 5`) do **not** work —
> Python can't overload them. Combine selectors with `&` / `|` (min/max) or with
> `.and_()` / `.or_()`.

---

## 3. numpy-style cell regions: `M[...]`

Index the formula like a tensor to select an **axis-aligned box**. Each index
constrains one axis (0 = row, 1 = col, …); the result is a paintable region:

```python
M[3:, 4:].highlight(color="pink")   # rows >= 3 AND cols >= 4
M[:3, :].highlight()                # rows 0..2  (exclusive stop -> row <= 2)
M[:, c].highlight()                 # exact column c
M[r, ...].highlight()               # exact row r; trailing ... = rest unconstrained
```

Semantics:

- **Slice** — `start` inclusive → `>=`, `stop` exclusive → `<= stop-1`.
- **Bare int / node / node-id** — exact index → `==`.
- **Node as `start` or as an index stays reactive** — `M[r:, :]` moves as `r`
  changes. (A node can only be a slice *start* or an exact index, never a slice
  *stop* — an exclusive upper bound has no representable node edge; use an
  explicit `dim(i) <= node` selector.)
- **Omitted / `:` axes are unconstrained.** A trailing `...` documents that and
  is otherwise a no-op.
- Regions compose and **stay paintable**: `(M[3:, :] | M[:, 4:]).highlight()`.

Rejected (each raises `TexError`): a whole-matrix slice `M[:, :]` (nothing to
distinguish), a step `M[::2, :]`, and a node slice-stop `M[:r, :]`.

Boxes are the common case. What a box **cannot** express is a relation *between*
axes (diagonals, triangles) — reach for the operators (#2) or the helpers (#6).

---

## 4. Named region helpers: `.diag()`, `.triu()`, `.tril()`

Sugar for the cross-axis relations a box can't express (`col - row` bands). Each
returns a paintable region:

```python
M.diag().highlight()                 # main diagonal:  col - row == 0
M.triu().highlight(color="blue")     # upper triangle: col - row >= 0
M.tril().highlight()                 # lower triangle: col - row <= 0
M.triu(1).highlight()                # strictly above the diagonal: col - row >= 1
```

The `k` offset picks the `k`-th diagonal (`diag(k)`) or the triangle from the
`k`-th diagonal (`triu(k)` / `tril(k)`).

---

## Choosing a form

| Region shape | Use |
| --- | --- |
| A single row/column | `rows == r`, or `M[r, ...]` |
| An axis-aligned box | `M[a:b, c:d]` |
| A diagonal / triangle | `M.diag()` / `M.triu()` / `M.tril()` |
| Any cross-axis relation / band | operators: `cols - rows > k` |
| Combine regions | `&` / `\|`, or `.and_()` / `.or_()` |
| Fade / gate behind a click | `.scale(node)` on any region |

All of it is Python-side only and lowers to today's selector JSON — the browser
runtime and the frozen wire contract are unchanged.
