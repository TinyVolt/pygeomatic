# `gm.ui` and conditional markdown

Added in `a795104` ("feat: add marimo style .ui and .md"). Three pieces that only
make sense together:

- **`gm.ui`** — reader-facing controls (slider, checkbox, dropdown, radio,
  number, text box) that drive a store node.
- **`gm.md`** — a `pygeomatic` article block writing *visible prose*, not just
  hidden setup commands. This is the only place a control can be dropped into a
  sentence, because the drop is an f-string.
- **`gm.when` + `gm.cond`** — prose that appears and disappears in the reader's
  browser as node values change.

The model is borrowed from marimo's `mo.ui`, with one important difference:
**there is no python at read time.** marimo re-runs a kernel cell when a widget
moves; here the widget writes a number into a store node and the engine
recomputes the canvas, bound formulas and gated prose on its own.

```python
r = gm.ui.slider(1, 5, step=0.5, value=3, label="radius")
c = gm.circle(gm.p0, r)
gm.md(f"Drag to resize the circle: {r}")
```

---

## 1. Controls (`gm.ui`)

A control **records one ordinary command and returns the node that command
produced**. `gm.ui.slider(1, 5, value=3)` emits exactly `r = \scalar 3` — nothing
more. So the returned node is a plain `Scalar` and everything that accepts a
Scalar keeps working untouched: `gm.circle(gm.p0, r)`, `r * 2`,
`gm.tex(...).bind(r)`.

| constructor | node type | signature |
| --- | --- | --- |
| `gm.ui.slider` | `Scalar` | `(start, stop, step=None, value=None, label=None, show_value=True)` |
| `gm.ui.number` | `Scalar` | `(start=None, stop=None, value=None, step=None, label=None)` |
| `gm.ui.checkbox` | `Bool` | `(value=False, label=None)` |
| `gm.ui.dropdown` | `Text` | `(options, value=None, label=None)` |
| `gm.ui.radio` | `Text` | `(options, value=None, label=None)` |
| `gm.ui.text` | `Text` | `(value="", label=None, placeholder=None)` |

`slider` needs `stop > start` and a positive `step` no wider than the range;
`number`'s bounds are both optional (omit them for an open field). `dropdown` and
`radio` take a non-empty list of **distinct strings** — the chosen one *is* the
Text node's value, so duplicates would be indistinguishable. Every violation
raises `gm.UIError` at compile time with the offending value in the message.

Choose `radio` over `dropdown` for two or three options the reader should see
without clicking; choose `number` over `slider` when they need an exact figure
rather than a sweep.

### The node gets its name from the assignment

`inference.py` normally reads the author's assignment target to name a node. A
`gm.ui` constructor calls `gm.scalar()` / `gm.text()` on the author's behalf, so
the recording call happens one frame *down* inside `pygeomatic.ui`. The commit
extends the existing dunder-frame hop to cover that:

```python
my_radius = gm.ui.slider(1, 5)
assert my_radius.id == "my-radius"     # not `num0`
```

The hoppable set is an explicit list of constructor names (plus the shared
`_choice` helper behind `dropdown`/`radio`, which adds one more frame), rather
than "any frame in `pygeomatic.ui`" — so an unrelated helper in that module can
never silently steal a name. The name matters beyond readability: the widget
addresses its own node by id in the emitted HTML.

### Widgets live off the tape

Widgets are recorded on `Store.ui_widgets` (node id → spec dict), a channel
**separate from the command tape**, exactly like `Store.tex_bindings`.
`gm.emit()` never sees them:

```python
with gm.Store() as s:
    r = gm.ui.slider(1, 5)
assert s.ui_widgets["r"]["kind"] == "slider"
assert "nova-ui" not in gm.emit(s)
```

Keying by node id is what forces the **one control per node** rule: `f"{r}"`
looks the control up by id and could not tell two apart. A second control on the
same node raises `UIError`.

---

## 2. `__format__` is the only entry point

`GNode.__format__` was added in this commit. Interpolating a node into a string
yields its **id**, unless the node carries a control — then it yields the
control's HTML:

```python
gm.md(f"Drag to resize the circle: {r}")
```

It lives on the base `GNode` rather than on a widget subclass, precisely so a
widget stays an ordinary `Scalar`/`Bool`/`Text`. With no active store (a bare
node built outside `with Store()`), it falls back to the plain id rather than
breaking the f-string.

The rendered element is always **one line** — markdown treats an indented line as
a code block, and an f-string inside an indented triple-quoted `gm.md(...)` would
otherwise hand markdown multi-line HTML and get it rendered as source:

```html
<span class="nova-ui" data-kind="slider" data-node="r" data-initial-value='3.0'
      data-start='1.0' data-stop='5.0' data-step='0.5'
      data-label='&quot;radius&quot;' data-show-value='true'></span>
```

**Settings travel on the element.** Every option becomes a `data-*` attribute
holding JSON, inline where the f-string put it — no separate manifest (unlike
`gm.tex`), so a control needs no reader-side lookup step. `kind` and `node` are
written plainly rather than as JSON, since both are validated identifiers; the
browser's rule is simply *those two are strings, the rest are `JSON.parse`*.
`None`-valued options are omitted entirely.

### The escaping is load-bearing

`ui._attr` applies four passes in a fixed order, each fixing a real breakage:

1. `<` and `>` → `<` / `>` **inside the JSON**, so an HTML sanitiser
   cannot see tag-like text in an attribute and strip it;
2. `html.escape` for `&` and both quote characters (attributes are quoted with
   `'`, so `'` must be escaped);
3. `\` → `&#92;`, because markdown eats backslashes;
4. `$` → `&#36;`, because the article compiler skips `$...$` regions when
   scanning for command links — an unescaped `$` in a label would desynchronise
   that scan and silently swallow the rest of the paragraph.

The browser reverses all of it: the HTML parser decodes the entities and
`JSON.parse` decodes the unicode escapes.

---

## 3. `gm.md` — prose from inside a block

A ```` ```pygeomatic ```` block normally contributes only hidden setup commands.
`gm.md(text)` is how it contributes visible prose as well. Calls accumulate in
order on the recorder and land **after** the block's setup commands, blank-line
separated so markdown sees each as its own block.

`inspect.cleandoc` strips the uniform indentation of a triple-quoted string, so
prose written at any indent level reaches markdown flush-left rather than as a
code block.

Two deliberate limits:

- **Not rescanned for `{label}(command)` links.** A link has to be *executed* to
  produce its DSL, and by the time this text exists all execution has finished.
  Maths, controls and conditional blocks are all fine.
- **Not allowed in an inline span.** An inline span is replaced by its commands
  mid-sentence; there is nowhere sensible to put a block of prose, so it raises
  `ArticleError` — the same reasoning as the existing ban on `group()` there.

Outside an article block, `gm.md()` raises `ArticleError`. Both `md` and `when`
are also injected bare into the fence namespace alongside `gm` and `group`.

---

## 4. `gm.when` and `gm.cond` — reader-side conditions

A condition is **pure configuration**: a small JSON tree naming nodes and
constants, recorded into the article and evaluated in the browser whenever one of
those nodes changes. It records no DSL and has no engine command behind it.

```python
show = gm.ui.checkbox(False, label="Show the proof")
with gm.when(show):
    gm.md("Because $ab=ba$, the map commutes.")

with gm.when(gm.cond.ge(k, 2)):
    gm.md("Now the second eigenvector matters.")
```

### The `gm.cond` API

Comparisons: `ge`, `gt`, `le`, `lt`, `eq`, `ne` — each taking nodes or plain
constants on either side. The ordered four reject string constants (compare text
with `eq`/`ne`). Combinators: `all_(*conds)`, `any_(*conds)`, `not_(c)`, also
spelled `&`, `|`, `~` on a `Cond`.

**Why a namespace instead of `k >= 2`.** Overloading comparison operators on
nodes would collide with geomatic's own comparison commands (`\gt`, `\lt`, …),
which record DSL and return `Bool` nodes — the opposite of what a condition is.
Keeping them apart leaves `k >= 2` available for its real meaning. `&`, `|`, `~`
*are* overloaded, but only on `Cond` itself, which is our own type with no other
reading.

`Cond.__bool__` raises deliberately: a condition cannot be used in a python `if`,
because it describes something the **reader's** browser decides, not something
known while compiling. For a compile-time branch, test the plain python value.

`gm.when` also accepts a bare `Bool` or `Scalar` node as a truth gate. Any other
node type raises `CondError` pointing you at `gm.cond.eq(...)`.

### What the block does

```html
<div class="nova-when" data-when='{&quot;node&quot;:&quot;show&quot;}' style="display:none">

The area is $\pi r^2$.

</div>
```

- The blank lines inside the `<div>` are load-bearing: markdown stops treating a
  block as raw HTML at the first blank line, so the prose inside is still
  formatted normally and the raw file still reads correctly on GitHub.
- `cond.evaluate` runs at compile time against the nodes' current values to
  decide whether to emit `style="display:none"`, so a block that starts false
  never flashes on screen before the browser's watcher runs. A node with no known
  value counts as false — the safe direction: a block that should have been
  visible appears a frame later, rather than one that should have been hidden
  appearing at all. `cond.node_refs` collects the ids to look up.
- An empty block (no `gm.md` output inside) is an error.
- Blocks **nest**; an inner block shows only when both conditions hold.

Two rules worth internalising:

- **Only `gm.md` output is gated.** Commands recorded inside a `when` block go
  onto the tape as usual — hiding prose must not silently change the scene.
- **No command links inside a gated block.** Commands are numbered by document
  position, so hiding one does not remove it from the sequence: the reader would
  be left waiting on a link they cannot see. Prose, maths and controls are fine.

`evaluate` mirrors `evalPredicate` and the JSON shape is shared with the
browser's `predicate.ts` — keep the two in step.

---

## 5. Worked example

````markdown
# Circles

```pygeomatic
r = gm.ui.slider(1, 5, step=0.5, value=3, label="radius")
c = gm.circle(gm.p0, r)
show = gm.ui.checkbox(False, label="Show the note")
gm.md(f"Drag to resize the circle: {r}")
gm.md(f"{show}")
with gm.when(show):
    gm.md("The area is $\\pi r^2$.")
```
````

compiles to:

```markdown
# Circles

{}(r = \scalar 3)
{}(c = \circle p0 r)
{}(show = \bool 0)

Drag to resize the circle: <span class="nova-ui" data-kind="slider" data-node="r" data-initial-value='3.0' data-start='1.0' data-stop='5.0' data-step='0.5' data-label='&quot;radius&quot;' data-show-value='true'></span>

<span class="nova-ui" data-kind="checkbox" data-node="show" data-initial-value='false' data-label='&quot;Show the note&quot;'></span>

<div class="nova-when" data-when='{&quot;node&quot;:&quot;show&quot;}' style="display:none">

The area is $\pi r^2$.

</div>
```

Three ordinary DSL lines, then prose carrying two controls and one gated block.
Nothing about the tape changed.

---

## Exports and files

`gm.ui`, `gm.cond`, `gm.md`, `gm.when`, `gm.Cond`, `gm.CondError`, `gm.UIError`,
`gm.render_widget_html`.

| file | change |
| --- | --- |
| `src/pygeomatic/ui.py` | new — controls, `_register`, HTML rendering, escaping |
| `src/pygeomatic/cond.py` | new — `Cond`, comparisons, combinators, `evaluate`, `node_refs` |
| `src/pygeomatic/article.py` | `md()`, `when()`, recorder `md` channel, fence emission |
| `src/pygeomatic/nodes.py` | `GNode.__format__` |
| `src/pygeomatic/store.py` | `Store.ui_widgets` |
| `src/pygeomatic/inference.py` | `_is_hoppable` / `_UI_FRAME_NAMES` frame hop |
| `tests/test_ui.py`, `tests/test_cond.py` | new — 520 lines of coverage |
