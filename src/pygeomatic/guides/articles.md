# Markdown articles

Writing Nova articles: pygeomatic blocks in markdown, click-through links, gm.md prose, gm.ui controls and panels, conditional text, click and page-load blocks, and live formulas.

An article is ordinary markdown with pygeomatic Python in two places: fenced
```` ```pygeomatic ```` blocks, and `{label}(...)` links in the prose. The article
compiler runs all of that Python once, in document order, against one shared scene,
and turns it into the published page.

Everything in this guide only works inside an article. In plain pygeomatic code,
`gm.md`, `gm.when`, `group` and `gm.onpageload` raise errors.

## What records a DSL command

Most `gm.*` calls record one DSL command, but not all:

- A plain call such as `gm.point(1, 2)` records one command.
- Reading a property (`p.x`, `circ.center`) records nothing.
- Chained infix with one operator records one command: `a * b * c` is one `\mul`.
- A `gm.ui` control records the one command that makes its node
  (`r = gm.ui.slider(1, 5)` records `r = \scalar 1`). The control itself is not a command.
- Commands inside `with gm.ui.onclick(...)`, `with gm.ui.button(...)` and
  `with gm.onpageload()` are taken out of the document's command list. They run on a
  click, on a button press, or when the page loads.
- `gm.md`, `gm.when`, `gm.cond.*`, `group`, the layout calls (`gm.ui.col`, `row`, `box`,
  `label`, `math`) and `gm.tex` bindings record no command at all.

## Blocks and links

````markdown
```pygeomatic
origin = gm.p0
a = gm.point(3, 0)
walk = gm.line(origin, a)
gm.hide(walk)

with group("walk-x"):
    gm.highlight(walk)
    gm.show(walk)
```

Reach the point by {moving 3 units}(ref:walk-x), then {hide the line}(gm.hide(walk)).
````

- **A block** runs as real Python: loops, helpers and comments all work. The reader
  never sees the code. Each command it records becomes a hidden step at the spot where
  the block sat.
- **`with group("name"):`** gathers the commands inside it into a named step. Write it
  as a bare `group`, not `gm.group`. Names use letters, digits and dashes, and start with
  a letter.
- **`{label}(ref:name)`** in the prose is the link that runs that group. The group's
  last command sits on the visible link and the rest run just before it. So put the
  command the reader should see last, for example `gm.show(...)` after the setup.
- **`{label}(python)`** runs one short piece of Python as a link, for example
  `{reset}(b = gm.scalar(3))`. It must record at least one command.
- A label can hold math: `{$x = 3$}(x = gm.scalar(3))`.

When the reader clicks a link, every step before it runs first, in document order,
starting from the nearest `gm.clear()`. Call `gm.clear()` at the top of a block to
start a new section on a blank canvas.

Rules. Each one is a compile error:

- Every group is referenced exactly once, after the block that defines it.
- Links to groups appear in the same order the groups ran.
- Groups do not nest, are never empty, and never go inside a `{label}(python)` link.
- Group names are unique in the article.

## gm.md: prose from a block

A block adds only hidden steps unless it calls `gm.md(text)`. The text is placed after
the block's steps. Triple-quoted strings may be indented; the indent is removed.

```python
side = gm.scalar(4)
gm.md(f"The side is {side:.2f} units.")
```

In an f-string, a node becomes:

- its **control**, if it has one (see below);
- a **live number or text** for a Scalar, Text or Bool node, which updates as the node
  changes. A format forces this: `.2f` (fixed decimals), `.1%` (percent), `d` (whole
  number);
- its **id** for any other node.

Limits:

- `gm.md` text is not searched for `{label}(...)` links. Write links in the markdown
  itself, outside the block.
- No `gm.md` inside a `{label}(python)` link or inside a `gm.ui.onclick` block.

## Controls

A control makes one node and returns it, so it works anywhere a node of that type does.
Show it by putting it in a `gm.md` f-string.

| call | node | arguments |
| --- | --- | --- |
| `gm.ui.slider` | Scalar | `(start, stop, step=None, value=None, label=None, show_value=True)` |
| `gm.ui.number` | Scalar | `(start=None, stop=None, value=None, step=None, label=None)` |
| `gm.ui.checkbox` | Bool | `(value=False, label=None)` |
| `gm.ui.dropdown` | Text or Scalar | `(options, value=None, label=None)` |
| `gm.ui.radio` | Text or Scalar | `(options, value=None, label=None)` |
| `gm.ui.text` | Text | `(value="", label=None, placeholder=None)` |

````markdown
```pygeomatic
gm.clear()
r = gm.ui.slider(1, 5, step=0.5, value=3, label="radius")

with group("draw"):
    circ = gm.circle(gm.p0, r)
```

Click to {draw the circle}(ref:draw).

```pygeomatic
gm.md(f"Drag to resize it: {r}")
```
````

- A slider needs `stop > start`, a positive `step` no wider than the range, and a
  `value` inside the range.
- `dropdown` and `radio` options must be distinct and either all strings (a Text node)
  or all numbers (a Scalar node).
- One control per node. Each control needs its own node.
- The control's node is made by a hidden step, which only runs once the reader clicks
  a link after it. For a control that must work before any click, make it in
  `gm.onpageload()` (see below).
- A control cannot be made inside a `gm.ui.onclick` block.

## Conditional prose

`with gm.when(condition):` shows the `gm.md` text inside it only while the condition
holds. The reader's browser checks it whenever the nodes change.

```python
show = gm.ui.checkbox(False, label="Show the note")
radius = gm.ui.slider(1, 6, 0.5, 3, label="radius")
gm.md(f"{show} {radius}")

with gm.when(show):
    gm.md("You ticked the box.")

with gm.when(gm.cond.ge(radius, 4)):
    gm.md("**Large:** the radius is 4 or more.")
```

- A condition is a Bool or Scalar node, or a `gm.cond` rule: `eq`, `ne`, `lt`, `le`,
  `gt`, `ge`, each taking nodes or plain values on either side. Combine rules with
  `gm.cond.all_`, `any_` and `not_`, or with `&`, `|` and `~`.
- Compare text only with `eq` or `ne`: `gm.cond.eq(mode, "sum")`.
- Never write `k >= 2` or use a condition in a Python `if`. Python does not know what
  the reader will choose.
- Only the `gm.md` text is hidden. Commands inside the block still run.
- Blocks nest. The block must produce some `gm.md` text.
- Never put a `{label}(...)` link inside hidden text.

## Panels

A panel arranges several elements. The outermost container is where the panel appears.

```python
with gm.ui.box(border=True, pad=2):
    with gm.ui.col(gap=2):
        gm.ui.label("radius = ${size}")
        size = gm.ui.slider(1, 5, value=2, label="radius")
        gm.ui.math("A = \\pi r^2")
        with gm.ui.row(gap=1):
            with gm.ui.button("reset"):
                size = gm.scalar(2)
        with gm.when(gm.cond.gt(size, 4)):
            gm.ui.label("That is a big circle.")
```

- Containers: `gm.ui.col(gap=0, align="stretch")`, `gm.ui.row(gap=0, align="center")`
  (it wraps when it runs out of width), and `gm.ui.box(border=False, background=False)`.
  `align` is `start`, `center`, `end` or `stretch`.
- Inside a container:
  - any control;
  - `gm.ui.label(text)`: plain text, not markdown, where `${node}` shows a live value;
  - `gm.ui.math(latex, id=None)`: a formula, which `gm.tex(id)` can address;
  - `gm.ui.button(label)`: a `with` block whose commands run when pressed;
  - `gm.when(...)`: shows the elements inside it only while the condition holds.
- Every element also takes `width`, `height`, `grow` and `pad` as keywords.
  - `gap` and `pad` are spacing steps from 0 to 9, not pixels.
  - `width` and `height` are a step, `"fill"`, or a length in `px`, `ch`, `%` or `rem`,
    such as `"12ch"`.
  - Those four keywords only work on a control inside a container.
- A button's commands behave like a `gm.ui.onclick` block: they leave the document's
  steps.
- A container cannot be empty. A button must be inside a container.
- Every node a panel reads must be defined somewhere in the article.

## Clicking a shape: gm.ui.onclick

`with gm.ui.onclick(node):` runs its commands when the reader clicks that shape on the
canvas.

```python
box = gm.annotate_text_box("click me", 2, 3)
c = gm.circle(gm.p0, 1)
with gm.ui.onclick(box):
    c = gm.circle(gm.p0, 3)
```

- The target must be something drawn: not a Scalar, Bool, Text or Complex.
- Reassigning a node the document already made is the usual use: `c` above grows on
  click.
- The document must not use a node that only the click block makes. The click may
  never happen.
- A second block for the same target replaces the first.
- Not allowed inside the block: `gm.md`, `group`, a control, `gm.onpageload`, or
  another `gm.ui.onclick`.

## The opening scene: gm.onpageload

`with gm.onpageload():` runs its commands when the page loads, before any link. It runs
again after every `gm.clear()` and after "Start over". Use it for a starting figure,
and for controls that must work before any click.

```python
with gm.onpageload():
    r = gm.ui.slider(1, 5, step=0.5, value=3, label="radius")
    gm.circle(gm.p0, r)

gm.md(f"Drag to resize the circle: {r}")
```

- At most one per article.
- It must be in the article's **first** pygeomatic block, before any other command.
- Later steps may use what it made.
- `gm.md` and `gm.ui.onclick` are allowed inside it. `group` is not.

## Live formulas: gm.tex

Give a display formula an id with a `%id:name` line as the first line inside `$$`.
Then address it from a block with `gm.tex("name")`. Inline `$...$` math cannot have an
id.

````markdown
$$
%id:area
A = \int_{0}^{b} 2\pi x \, dx
$$

```pygeomatic
b = gm.ui.slider(1, 5, step=0.5, value=3, label="b")
area = gm.tex("area")
area.int.upper.bind(b)
gm.md(f"Drag the upper limit: {b}")
```

{make it 5}(b = gm.scalar(5))
````

There are three effects.

**Value.** A slot shows a node's number: `t.int.upper.bind(node, fmt=".2f")`.

- Slots:
  - `int`, `sum`, `prod`: `lower`, `upper`, `body`;
  - `frac`: `num`, `denom` (`\binom` also counts as a `frac`);
  - `sqrt`: `body`.
- The slot must already hold a symbol. `\int_a^b` can bind `upper`; `\int` cannot.
- With two of the same command, index them with the plural: `t.ints[1].upper`.
- `show="symbol"` records the link but keeps the written symbol.
- The node must exist before the binding.

**Highlight** (matrix cells only):

```python
M.highlight(M.rows() == row, color="pink")
M.triu().highlight(color="blue")
M.diag().highlight()
M[1:, 2:].highlight()
M.highlight((M.cols() - M.rows() <= band) & (M.rows() - M.cols() <= band))
M.highlight(sel, matrix=1)
```

- `color` is a palette name (`red`, `orange`, `amber`, `yellow`, `lime`, `green`,
  `emerald`, `teal`, `volt`, `cyan`, `blue`, `indigo`, `violet`, `purple`, `pink`,
  `fuchsia`, `white`, `gray`) or any CSS color.
- `matrix=N` picks the Nth matrix in the formula, counting from 0.
- `sel.scale(g)` fades a selection by the node `g`.

**Reveal.** A part fades in as a node goes from 0 to 1. It starts hidden.

```python
t.underbrace.reveal(shown)             # the brace and its label
t.underbrace.label.reveal(shown)       # only the label; also .body, overbrace
M.reveal(M.cols() < k)                 # the first k columns of a matrix
d.rows().reveal(gm.rows < step)        # the first `step` lines of an aligned block
```

Selector rules:

- Use `&` and `|`, never `and`, `or`, or chained comparisons like `1 < x < 3`.
- For "the first k", use strict `<`.
- A region is passed in, not revealed directly: `M.reveal(M[1:, :])`.

Drive every effect by changing its node: `{2}(k = gm.scalar(2))`,
`{show}(shown = gm.bool_(True))`, `{sweep}(gm.animate(k, 3))`, or a control.
