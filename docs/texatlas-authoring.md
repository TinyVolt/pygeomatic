# Live formulas: what you can do with texatlas

An author's guide. This is about **what you can make a formula do**, not how the
machinery works. For the internals see [`texatlas.md`](texatlas.md); for the
exact JSON on the wire see
[`src/lib/texatlas/CONTRACT.md`](../src/lib/texatlas/CONTRACT.md).

Everything below was run and checked against the current code (KaTeX 0.16.x,
pygeomatic `gm.tex`). Where something does not work, it says so and gives the
form that does.

---

## The idea in one minute

A normal `$$…$$` formula is a picture. With texatlas, parts of it become live:

- a number in the formula tracks a store node and updates as the node changes,
- cells of a matrix light up in a color you choose,
- any part can start hidden and fade in when the reader clicks.

You never write JavaScript, CSS, or a special LaTeX command. You write two
things: an **id** on the formula, and a few lines of **Python** saying which
part is tied to which node. Then you drive the nodes from prose links, exactly
like every other interactive thing in an article.

Three effects exist, and that is the whole menu:

| Effect | What it does | You call |
| --- | --- | --- |
| **value** | a slot in the formula prints a node's number | `t.int.upper.bind(b)` |
| **highlight** | matrix cells get a color | `t.highlight(gm.rows == r, color="pink")` |
| **reveal** | a part fades in or out | `t.underbrace.reveal(shown)` |

---

## The two pieces you write

### 1. Give the formula an id

Put a `%id:` comment on its own line, as the first line inside the `$$`:

```markdown
$$
%id:energy
\int_a^b x^2 \, dx
$$
```

- The id may contain letters, digits, `_` and `-`.
- `%` is a LaTeX comment, so the raw markdown still renders correctly on GitHub
  and anywhere else. Nothing about the formula changes for a reader who never
  clicks.
- **Display math only.** An inline `$…$` formula cannot carry an id.
- The `%id:` line must be on its own line. Writing `$$ %id:x \int … $$` on one
  line comments out the whole formula.

A formula with an id but no bindings renders exactly like a plain formula.

### 2. Bind parts of it in Python

```python
a = gm.scalar(0)
b = gm.scalar(2)
t = gm.tex("energy")          # a handle to the formula with that id
t.int.lower.bind(a)
t.int.upper.bind(b, fmt=".2f")
```

`gm.tex("energy")` is a handle to the **whole formula**, not to one piece of it.
You then address a piece of it (a slot, a matrix, an alignment block).

Bindings are configuration, not commands. They do not appear as clickable steps
in the article and they never run twice. They just sit there and listen to the
nodes they name.

---

## Effect 1: value

**What it does.** A named part of the formula stops showing the symbol you wrote
and shows a node's current number instead.

```markdown
$$
%id:energy
\int_a^b x^2 \, dx
$$
```
```python
b = gm.scalar(2)
gm.tex("energy").int.upper.bind(b, fmt=".2f")
```

The `b` in the formula now reads `2.00`, and reads `3.00` after the reader
clicks a link that sets `b = gm.scalar(3)`.

### Which parts can hold a value

Only these. The name on the left is what you type after the handle.

| Address | Covers these LaTeX commands | Slots |
| --- | --- | --- |
| `int` | `\int` `\iint` `\iiint` `\oint` `\oiint` `\oiiint` | `lower`, `upper`, `body` |
| `sum` | `\sum` `\bigcup` `\bigcap` `\bigoplus` `\bigotimes` | `lower`, `upper`, `body` |
| `prod` | `\prod` `\coprod` | `lower`, `upper`, `body` |
| `frac` | `\frac` `\dfrac` `\tfrac` `\binom` | `num`, `denom` |
| `sqrt` | `\sqrt` | `body` |
| `underbrace`, `overbrace` | `\underbrace` `\overbrace` | `body`, `label` (**reveal only**, see below) |

```python
t.frac.num.bind(p)          # numerator
t.frac.denom.bind(q)        # denominator
t.sqrt.body.bind(x)         # the thing under the root
t.sum.lower.bind(i)         # the i=1 under the sigma
t.sum.upper.bind(n)         # the n above it
```

Anything not in that table (`\lim`, `\max`, an ordinary letter in the middle of
an expression) has no address and cannot hold a value. New commands can be
added to the schema, which is a code change on both sides; see
[`texatlas.md`](texatlas.md).

### Three rules that will bite you

**The slot must already contain something.** Binding replaces content, it never
creates it. `\int f(x) dx` has no upper limit written, so `int.upper` fails with
"write placeholder symbols". Write `\int_a^b f(x) dx` and bind over the `b`.

**Two of the same command means you must say which.** `\int_a^b x\,dx +
\int_c^d y\,dy` gives an "ambiguous" error for `int.upper`. Use the index form,
counting occurrences from 0 in reading order:

```python
t.ints[1].upper.bind(d)      # the second integral
```

Note the plural (`ints`, `fracs`, `sums`, `underbraces`) when you index.
Also note that `\binom` counts as a `frac`, so a formula with one `\frac` and
one `\binom` needs indices.

**`body` is the next thing after the operator, not the whole integrand.** In
`\int_a^b x^2 \, dx`, `int.body` is `x^2`. In `\int_a^b (x^2+1)\,dx` it
resolves to just the opening parenthesis, which is not useful. Use `body` only
when the integrand is a single symbol or a single braced group.

### Number formatting

| `fmt` | `0.5` becomes | Notes |
| --- | --- | --- |
| omitted | `0.5` | trims trailing zeros, at most 4 decimals |
| `".2f"` | `0.50` | fixed decimals |
| `".1%"` | `50.0%` | percent: multiplied by 100, `%` appended |
| `"d"` | `1` | rounded to a whole number |

Anything else is rejected when you compile the article.

### Binding without changing the picture

```python
t.frac.num.bind(p, show="symbol")
```

registers the link but leaves the glyph you wrote alone. Useful when you want
the connection recorded without the formula visibly changing.

### Before the node exists

A value slot shows **the symbol you originally wrote** until the node it names
has a value. So a formula that has not been "run" yet reads as ordinary math
rather than showing a made-up `0`.

---

## Effect 2: highlight

**What it does.** Cells of a matrix take on a color: the text turns that color,
the cell gets a faint tint of it and a hairline ring. It crossfades over about
140ms, so a click looks like a transition rather than a jump.

Highlights work on **matrix cells only**. There is no way to highlight the `x`
in `x + y`.

```markdown
$$
%id:mat
M = \begin{pmatrix} a & b & c \\ d & e & f \\ g & h & i \end{pmatrix}
$$
```
```python
r = gm.scalar(0)
M = gm.tex("mat")
M.highlight(gm.rows == r, color="pink")
```

Row 0 is pink. Click a link that sets `r = gm.scalar(1)` and the pink moves to
row 1.

### Ways to say which cells

All of these produce the same kind of thing, so pick whichever reads best.

```python
M.highlight(gm.rows == r)             # one row, tracked by a node
M.highlight(gm.cols == 2)             # one column, fixed
M.highlight(gm.cols - gm.rows > 0)    # strictly above the diagonal
M.diag().highlight()                  # main diagonal
M.triu().highlight(color="blue")      # upper triangle
M.tril(-1).highlight()                # below the diagonal
M[1:, 2:].highlight()                 # a box: rows >= 1 and cols >= 2
M[:, c].highlight()                   # column c exactly
M[r, ...].highlight()                 # row r exactly
(M[0, ...] | M[:, 0]).highlight()     # first row or first column
```

Slice rules match numpy: start is included, stop is excluded, and a bare
integer or node is an exact index. A node used anywhere in a slice stays live,
so `M[r:, :]` follows `r`.

`M[:, :]` is rejected: it selects everything, so there is nothing to
distinguish. Steps (`M[::2, :]`) are not supported.

### Colors

`color=` takes a palette name or any CSS color:

```python
M.highlight(gm.rows == r, color="pink")      # #F472B6
M.highlight(gm.rows == r, color="#6aa8ff")   # any CSS color works
```

Palette names include `red`, `orange`, `amber`, `yellow`, `lime`, `green`,
`emerald`, `teal`, `volt`, `cyan`, `blue`, `indigo`, `violet`, `purple`, `pink`,
`fuchsia`, `white`, `gray`. Omitting `color` gives yellow (`#f0e080`).

### More than one matrix in one formula

`gm.tex(id)` is the whole formula, so when it holds several matrices you say
which one with `matrix=N`, counting from 0 in reading order:

```markdown
$$
%id:matmul
A = \begin{pmatrix} a & b \\ c & d \end{pmatrix}
\quad
B = \begin{pmatrix} e & f \\ g & h \end{pmatrix}
$$
```
```python
f = gm.tex("matmul")
f.highlight(gm.rows == r, color="pink")               # row of A
f.highlight(gm.cols == c, color="blue", matrix=1)     # column of B
```

Cells never bleed between matrices: a rule aimed at matrix 1 leaves matrix 0
alone.

**What counts as a matrix when you number them.** Count these:
`matrix`, `pmatrix`, `bmatrix`, `Bmatrix`, `vmatrix`, `Vmatrix` (and their `*`
variants), plain `array`, `cases`, `dcases`, `rcases`, `smallmatrix`,
`subarray`. Do **not** count these: `aligned`, `align`, `split`, `alignat`,
`gathered`, `gather`, `CD`. So a `pmatrix` sitting inside an `aligned` block is
matrix **0**, because the `aligned` wrapper is not a matrix.

If you name a matrix that is not there, that one highlight quietly paints
nothing and everything else still renders.

### Fading a highlight in

Multiply any selection by a node to control its strength:

```python
g = gm.scalar(0)
M.highlight((gm.rows == r).scale(g))     # invisible until g rises to 1
```

`gm.animate(g, 1)` then fades the highlight in smoothly.

---

## Effect 3: reveal

**What it does.** A part of the formula gets an opacity between 0 and 1 taken
from a node. At 0 it is invisible, at 1 fully visible, in between it is
half-faded. That is the whole mechanism: reveal is "set the opacity from a
number", and every clever effect below is just a different way of computing that
number per part.

Two things make reveals different from the other effects:

- **A part with a reveal on it starts hidden.** If the node it reads does not
  exist yet, the weight is 0. (Values and highlights do the opposite: they leave
  things untouched until their node exists.)
- Reveals fade over about 200ms, so a click reads as an appearance, and an
  `gm.animate` sweep fades things in one after another.

You choose **what** to reveal from exactly three kinds of target.

### Target A: a slot (a brace annotation)

Used for "explain this piece of the equation on click".

There are two forms, and the difference is **whether the brace itself fades**.
Both leave the math under the brace visible throughout.

#### Form 1: the bare address fades the brace and its label together

````markdown
$$
%id:pyth-both
a^2 + b^2 = \underbrace{c^2}_{\text{hypotenuse}}
$$

```pygeomatic
shown = gm.bool_(False)
p = gm.tex("pyth-both")
p.underbrace.reveal(shown)
```

Click: {name it}(shown = gm.bool_(True))
````

On load you see `a^2 + b^2 = c^2` and nothing else. The click brings in the
brace **and** the word "hypotenuse" at once. This is the usual choice: the
annotation appears as one thing.

#### Form 2: the `.label` address leaves the brace showing

````markdown
$$
%id:pyth-label
a^2 + b^2 = \underbrace{c^2}_{\text{hypotenuse}}
$$

```pygeomatic
shown = gm.bool_(False)
p = gm.tex("pyth-label")
p.underbrace.label.reveal(shown)
```

Click: {name it}(shown = gm.bool_(True))
````

Same formula, one word changed in the Python. Now the brace under `c^2` is
drawn from the start, and only "hypotenuse" fades in. Use this when the brace
is part of the picture you want up front and the naming is the reveal.

`p.underbrace.body.reveal(shown)` is the third address: it fades the math under
the brace instead of the annotation.

`overbrace` behaves identically, with the label above.

#### More than one brace: index them

With two braces in a formula, an unindexed address is ambiguous and reveals
nothing, so number them from 0 in reading order. The indexed bare address fades
the glyph, exactly like form 1:

````markdown
$$
%id:two-braces
\underbrace{a + b}_{\text{sum}} \cdot \underbrace{c}_{\text{scale}}
$$

```pygeomatic
b1 = gm.bool_(False)
b2 = gm.bool_(False)
t = gm.tex("two-braces")
t.underbraces[0].reveal(b1)
t.underbraces[1].reveal(b2)
```

Click: {the sum}(b1 = gm.bool_(True)) then {the scale}(b2 = gm.bool_(True))
````

Each click fades in only its own brace and label.

Braces are the reveal families. You cannot `.bind()` a value into a brace label:
pygeomatic raises an error telling you so, because the value and the reveal
would fight over the same span. Put the live number in a `frac`/`int`/`sum`/
`sqrt` slot or in plain prose instead.

Slot reveals also accept `mode="collapse"`, which removes the space instead of
just making it transparent:

```python
p.underbrace.label.reveal(shown, mode="collapse")
```

Use `"fade"` (the default) when you want the layout to stay put, `"collapse"`
when the empty gap looks wrong.

### Target B: a matrix

Used for "build this matrix up column by column".

```markdown
$$
%id:mat
M = \begin{pmatrix} a & b & c \\ d & e & f \\ g & h & i \end{pmatrix}
$$
```
```python
k = gm.scalar(0)
M = gm.tex("mat")
M.reveal(M.cols() < k)
```

`k` is now literally **how many columns are showing**. `k = 0` shows none,
`k = 2` shows the first two, and `gm.animate(k, 3)` fills the matrix in from the
left. The brackets and the grid never move, because hidden cells keep their
space.

```python
M.reveal(M.rows() < k)                    # row by row instead
M.reveal((gm.cols - gm.rows) <= k)        # grow outward from the diagonal
M.reveal((M.rows() == 1) & shown)         # one row, gated by a bool
M.reveal(M[:, :2])                        # a fixed region, always shown
M.reveal(M.cols() < k, matrix=1)          # the second matrix in the formula
```

`matrix=N` counts exactly as it does for highlights.

Highlight and reveal can both apply to the same matrix; they do not interfere.

Only `mode="fade"` is allowed here. Collapsing cells would break the grid and
the brackets, so pygeomatic rejects it.

### Target C: an alignment block (a derivation)

Used for "show this derivation one line at a time". This is the target people
miss, because the thing it acts on is not a matrix: it is a multi-line equation
block written with `aligned`, `align`, `split`, `alignat`, `gather` or `CD`.

```markdown
$$
%id:deriv
\begin{aligned}
f(x) &= (x+1)^2 \\
     &= x^2 + 2x + 1 \\
     &= x(x+2) + 1
\end{aligned}
$$
```
```python
step = gm.scalar(0)
d = gm.tex("deriv")
d.rows().reveal(gm.rows < step)
```

`step` is how many lines are showing. Note `d.rows()`, which is what marks this
as the alignment-block target; `d.reveal(...)` would mean the matrix target
instead.

```python
d.rows().reveal((gm.rows == 2) & shown)      # just the last line, on a bool
d.rows().reveal(gm.rows < step, align=1)     # the second aligned block
```

`align=N` counts alignment blocks in reading order, and it counts exactly the
blocks that the matrix numbering skips. The two numbering systems are disjoint:
in a formula with one `aligned` wrapping one `pmatrix`, the `pmatrix` is
`matrix=0` and the `aligned` is `align=0`.

### Matrix or align: how to tell

| You wrote | Target | Call |
| --- | --- | --- |
| `\begin{pmatrix}`, `bmatrix`, `cases`, `array`, `smallmatrix` … | matrix | `t.reveal(...)`, `t.highlight(...)` |
| `\begin{aligned}`, `align`, `split`, `alignat`, `gather`, `CD` | align | `t.rows().reveal(...)` |
| `\underbrace{…}_{…}`, `\overbrace` | slot | `t.underbrace.reveal(...)` |

---

## Selectors: the one rule language

Highlights and reveals both take a **selector**, which is a rule that gives each
cell a weight from 0 to 1. Highlight turns the weight into color strength;
reveal turns it into opacity. Same rule, two paints.

A selector talks about a cell's **position** (`gm.rows`, `gm.cols`), never its
contents. There is no way to say "highlight every cell containing a 3".

| You write | Weight is 1 when | Notes |
| --- | --- | --- |
| `gm.rows == r` | row equals `r` | |
| `gm.rows >= r` | row is `r` or more | |
| `gm.rows <= r` | row is `r` or less | |
| `gm.rows > r` | row is strictly more than `r` | |
| `gm.rows < k` | row is strictly less than `k` | the "first k" form |
| `gm.cols - gm.rows >= 0` | on or above the diagonal | any arithmetic works |
| `a & b` | both, the smaller of the two weights | |
| `a \| b` | either, the larger | |
| `sel.scale(g)` | weight multiplied by `g` | fades a whole selection |
| a bare node | the node's own value, clamped to 0..1 | a bool is an on/off switch |

### Count, not index

For "show the first N", use strict `<`:

```python
M.reveal(M.cols() < k)      # k = 0 shows nothing, k = 2 shows two columns
```

With `<=` the first column is visible even at `k = 0`, which is almost never
what you want. This is the single most common mistake with reveals.

### Fractional values crossfade

Weights are not just on and off. During `gm.animate(r, 3)` the node passes
through `1.5`, and `gm.rows == r` then gives row 1 and row 2 a weight of 0.5
each, so the highlight glides between rows instead of snapping. The same applies
to reveals, which is why an animated build-up looks smooth.

---

## Making it happen: driving the nodes

Nothing in a binding is clickable by itself. The reader changes a **node**, and
everything bound to that node follows. In an article that means an ordinary
CommandLink holding Python:

```markdown
Move the limit: {b = 3}(b = gm.scalar(3)) or {sweep it}(gm.animate(b, 5))

Show the name: {what c is}(shown = gm.bool_(True))

Build the matrix: {1}(k = gm.scalar(1)) {2}(k = gm.scalar(2)) {3}(k = gm.scalar(3))
```

- **`gm.scalar(v)`** reassigns a number. Assignment is last write wins, so
  reusing the same variable name is how you change it.
- **`gm.bool_(True)` / `gm.bool_(False)`** is the natural on/off gate, and reads
  as 1/0 to a selector.
- **`gm.animate(node, target)`** sweeps a scalar and repaints every frame, which
  is what makes a reveal or a moving highlight look animated. It also exports to
  video like any other animation.
- A `gm.ui` slider on a bound node works too: drag it and the formula follows.

---

## Gotchas

Each of these was reproduced against the current code.

**Chained comparisons are not allowed.** Python cannot overload them, so
`1 < gm.rows < 3` would mean "`(1 < gm.rows)` and `(gm.rows < 3)`", and Python
would keep only the second half. Rather than record a rule you did not write,
this raises "a selector has no truth value". Write it out:

```python
(gm.rows >= 1) & (gm.rows < 3)
```

`and` / `or` / `not` on a selector raise for the same reason. Use `&` and `|`.

**A region cannot paint itself with a reveal.** `M[1:, :].highlight()` works,
but `M[1:, :].reveal(...)` does not exist. Pass the region in instead:

```python
M.reveal(M[1:, :])
```

**A bound node must already exist.** `t.int.upper.bind(b)` requires `b` to have
been created earlier in the article, otherwise pygeomatic raises immediately.

**Values and highlights wait; reveals hide.** If a selector reads a node that
does not exist yet, a highlight paints nothing and a value slot keeps the symbol
you wrote, but a reveal treats it as 0 and hides the part. That is deliberate,
and it is why an unrevealed brace is invisible on first paint.

---

## A complete article

This compiles as written and uses all three effects.

````markdown
# Demo

$$
%id:energy
\int_a^b x^2 \, dx
$$

```pygeomatic
a = gm.scalar(0)
b = gm.scalar(2)
t = gm.tex("energy")
t.int.lower.bind(a)
t.int.upper.bind(b, fmt=".2f")
```

Move the upper limit: {b = 3}(b = gm.scalar(3)) or {sweep}(gm.animate(b, 5))

$$
%id:mat
M = \begin{pmatrix} a & b & c \\ d & e & f \\ g & h & i \end{pmatrix}
$$

```pygeomatic
r = gm.scalar(0)
k = gm.scalar(0)
M = gm.tex("mat")
M.highlight(gm.rows == r, color="pink")
M.reveal(M.cols() < k)
```

Row: {row 1}(r = gm.scalar(1)) Columns: {2}(k = gm.scalar(2))

$$
%id:pyth
a^2 + b^2 = \underbrace{c^2}_{\text{hypotenuse}}
$$

```pygeomatic
shown = gm.bool_(False)
p = gm.tex("pyth")
p.underbrace.reveal(shown)
```

Click: {name it}(shown = gm.bool_(True))

$$
%id:deriv
\begin{aligned}
f(x) &= (x+1)^2 \\
     &= x^2 + 2x + 1 \\
     &= x(x+2) + 1
\end{aligned}
$$

```pygeomatic
step = gm.scalar(0)
d = gm.tex("deriv")
d.rows().reveal(gm.rows < step)
```

Steps: {1}(step = gm.scalar(1)) {2}(step = gm.scalar(2)) {3}(step = gm.scalar(3))
````

---

## Quick reference

```python
t = gm.tex("id")                        # handle to the formula with %id:id

# value
t.int.upper.bind(node)                  # also int.lower, int.body
t.frac.num.bind(node, fmt=".2f")        # also frac.denom
t.sqrt.body.bind(node)
t.sum.upper.bind(node)                  # also sum.lower/body, prod.*
t.ints[1].upper.bind(node)              # pick one of several
t.frac.num.bind(node, show="symbol")    # link without changing the glyph

# highlight (matrices only)
t.highlight(gm.rows == r, color="pink")
t.highlight(gm.cols - gm.rows > 0, color="blue")
t.highlight(sel, matrix=1)              # the second matrix
t[1:, 2:].highlight()                   # box region
t.diag().highlight()                    # also .triu(k), .tril(k)
t.highlight(sel.scale(g))               # fade the whole selection

# reveal
t.underbrace.reveal(gate)               # brace + label; body stays
t.underbrace.label.reveal(gate)         # also .body, and overbrace
t.underbrace.label.reveal(gate, mode="collapse")
t.reveal(t.cols() < k)                  # matrix, column by column
t.reveal(t.rows() < k, matrix=1)
t.rows().reveal(gm.rows < k)            # aligned block, line by line
t.rows().reveal(gm.rows < k, align=1)

# driving them from prose
{label}(k = gm.scalar(2))
{label}(gate = gm.bool_(True))
{label}(gm.animate(k, 3))
```
