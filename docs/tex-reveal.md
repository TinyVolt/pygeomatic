# `gm.tex` reveal effect

A third texatlas effect alongside **value** (`slot.bind(node)`) and **highlight**
(`M.highlight(selector, color=...)`): **reveal** — a part of a `$$…$$` formula
**fades in** when a store node says so. It is the same selector machine as
highlight, but the paint is **opacity**, not color.

Like the other two effects, reveal records on the store's texatlas channel and is
harvested by `harvest_tex_bindings` (never emitted as DSL). Reactivity comes from
the store node a selector references — drive it with `\scalar` / `\set-bool` /
`\animate` on an ordinary CommandLink and the revealed region follows. There is
**no new DSL keyword**.

```python
import pygeomatic as gm
from pygeomatic import rows, cols
```

A **gate** is just a store node. A boolean reads best for an on/off reveal
(`gm.bool_(False)` makes a false gate, toggled by `\set-bool b true`); a scalar
(`gm.scalar(0)`) gives an animatable sweep (`\animate k 3`). A bare gate node
passed to `.reveal(...)` lowers to the `{node}` selector leaf
(`weight = clamp(0, v, 1)`) — no dummy comparison needed.

> **Count, not index.** For "reveal the first N", use **strict** `<`
> (`rows < k`), so the gate node = *how many* lines/rows/cols show and `k = 0`
> shows nothing. `<=` (index) leaves the first one always visible — an
> off-by-one. Same for matrix rows/cols and derivation lines.

---

## 1. Over/underbrace — brace + label on a click (body stays)

Over- and underbrace are one browser family (keyed off `isOver`); here they are
the `underbrace` / `overbrace` slot families, each with slots `body` and `label`.
The **bare** address is the *annotation* — the brace glyph **and** the label. The
math under/over the brace (`body`) was already there, so a bare reveal never hides
it.

````markdown
$$
%id:pyth
a^2 + b^2 = \underbrace{c^2}_{\text{hypotenuse}}
$$
```python
b = gm.bool_(False)             # false gate
t = gm.tex("pyth")
t.underbrace.reveal(b)          # brace + "hypotenuse" hidden until b; c^2 stays
```
Click to reveal: {the hypotenuse}(\set-bool b true)
````

Reveal only the label (brace stays), or only the body:

```python
t.underbrace.label.reveal(b)    # brace visible immediately, label fades in
t.underbrace.body.reveal(b)     # only the under-brace math
```

Overbrace is identical with `t.overbrace…` — same family; `isOver` flips which
sub/sup holds the label (resolved browser-side). Two braces in sequence:

```python
b1, b2 = gm.bool_(False), gm.bool_(False)
t = gm.tex("expand")
t.underbraces[0].reveal(b1)
t.underbraces[1].reveal(b2)
```

---

## 2. Derivation — one line per click (the `align` target)

`t.rows().reveal(...)` targets the formula's **equation-layout block** (an
`aligned` / `align` / `split` / `alignat` / `gather` / `CD` array — the arrays
that highlight/`matrix` deliberately skip) and paints per-cell opacity. The
selector references the **row** axis, so it reveals line-by-line.

````markdown
$$
%id:deriv
\begin{aligned}
f(x) &= (x+1)^2 \\
     &= x^2 + 2x + 1 \\
     &= x(x+2) + 1
\end{aligned}
$$
```python
k = gm.scalar(0)
d = gm.tex("deriv")
d.rows().reveal(rows < k)        # k = number of lines shown; k = 0 shows nothing
```
Step: {line 1}(k = \scalar 1) · {line 2}(k = \scalar 2) · {line 3}(k = \scalar 3)
````

`{Play}(\animate k 3)` crossfades each appearing line and exports to video for
free. A single specific line, gated by a bool:

```python
d.rows().reveal((rows == 2) & b)   # last line only, on when b is true
```

For a formula with more than one equation-layout block, pick which with
`align=N` (0-based source order, counting only the equation-layout arrays):
`d.rows().reveal(rows < k, align=1)`.

---

## 3. Matrix — reveal rows or columns

`M.reveal(selector)` reuses the highlight cell machinery (`M.rows()` / `M.cols()`
axes, `[...]` regions, `.triu()` …) and paints **opacity** instead of color.

````markdown
$$
%id:mat
M = \begin{pmatrix} a & b & c \\ d & e & f \\ g & h & i \end{pmatrix}
$$
```python
k = gm.scalar(0)
M = gm.tex("mat")
M.reveal(M.cols() < k)           # k = number of columns shown; col j shows when k > j
```
Build it up: {1 col}(k = \scalar 1) · {2 cols}(k = \scalar 2) · {3 cols}(k = \scalar 3)
````

```python
M.reveal(M.rows() < k)                   # row by row; {Fill}(\animate k 3)
M.reveal((M.rows() == 1) & b)            # a single row, gated by a bool
M.reveal((cols - rows) <= k)             # diagonal wavefront (grow the upper triangle)
M.reveal(M.cols() < k, matrix=1)         # the 2nd matrix in a multi-matrix formula
```

`matrix=N` counts matrices the **same way** as `highlight`'s `matrix=` (genuine
matrices in source order, skipping equation-layout blocks — see
[tex-highlight-ergonomics.md §5](tex-highlight-ergonomics.md)). Only `mode="fade"`
is allowed for matrices — `collapse` would break the grid and brackets, so
opacity keeps the shape stable while cells fade in.

---

## Modes and the wire shape

Each reveal lowers to a `RevealBinding` in the `reveals[]` array — exactly one
target descriptor (`slot` | `align` | `matrix`) plus a selector:

```jsonc
"reveals": [
  { "slot": "underbrace.label", "selector": <SelectorExpr> },
  { "align": 0,                 "selector": <SelectorExpr> },
  { "matrix": 0,                "selector": <SelectorExpr> }
]
```

- `mode` — `"fade"` (opacity, keeps layout; the default, **omitted** from the
  wire) or `"collapse"` (also removes the slot's space). Slots and `align` accept
  both; matrices accept only `fade`.
- Unlike `HighlightBinding.matrix`, the `matrix` / `align` index is the **target
  discriminator**, so it is always written — even when 0.
- **SelectorExpr addition:** a bare `{ "node": "b" }` leaf lets a bool gate be a
  selector without a dummy comparison. Everything else reuses the CONTRACT.md
  selector ops (`eq` / `ge` / `le` / `gt` / `lt`, `and` / `or` / `scale`).
```
