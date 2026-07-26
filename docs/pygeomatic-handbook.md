# pygeomatic handbook

The user-facing feature and API reference for **pygeomatic**, written to be the
single briefing document when defining new agents or skills that author
geomatic content. It covers *what a user can do* and *how the API behaves* — not
internal implementation, except where a behavior only makes sense with a little
of the why.

> **Maintenance contract.** This file must be updated whenever a feature of this
> repo is added, changed, or removed. When the function library changes, print
> the authoritative signatures with
> `uv run python -c "import pygeomatic as gm; print(gm.system_prompt())"` and
> reconcile the [Function library](#function-library) section against it. When
> article-authoring, texatlas, extensions, macros, coercions, naming, or the CLI
> change, update the corresponding section here. The live registry
> (`gm.system_prompt()`) and the source under `src/pygeomatic/` are always the
> ground truth; this handbook is the curated view.
>
> **`gm.system_prompt()` is auto-generated and cannot drift from code.** Its
> function reference, system-node list, and property whitelist are rendered at
> call time from the live `REGISTRY` / `SYSTEM_NODES` / `NODE_PROPERTIES` (see
> [prompting.py](../src/pygeomatic/prompting.py)), so loaded extensions and
> macros appear automatically. The only hand-maintained parts are the fixed
> `_RULES` prose and the `_BUILTIN_SHADOWS` set. The one thing that needs a
> deliberate step is **parity with the TypeScript engine**: `registry.json` and
> `src/pygeomatic/coercions.json` are generated from TS via `npm run
> gen:registry` (run in the TS repo) and pinned by `tests/test_parity.py` — run
> that test after any registry change.

---

## 1. Mental model

pygeomatic is a **Python mirror of the geomatic DSL**. Every public function maps
1:1 to a geomatic command. Calling it does two things at once:

1. **Computes** numeric values with numpy where possible (a `Point` really holds
   `x, y`).
2. **Records** the call onto an append-only *tape* on the active store.

From that tape, two things can be produced:

- `gm.emit()` renders the tape as **DSL text**, one line per call
  (`p-0 = \point 3 2`).
- **`compile_article(...)`** renders a markdown article that mixes prose with
  pygeomatic Python into the geomatic `{label}(command)` CommandLink format.

The modern, primary way to author content is **writing markdown with pygeomatic
Python directly** (§8). Emitting raw DSL (§11) still exists but is the lower-level
path.

Two hard rules that shape everything:

- **One `gm.` call = exactly one command** (one DSL line). Repetition is done with
  ordinary Python loops.
- **Ids obey the DSL grammar**: start with a letter, then letters/digits/dashes,
  **no underscores**, and never an engine-auto-name shape (`num0`, `p3`,
  `text1`) — those collide with engine-internal nodes.

---

## 2. Naming nodes

Every node has an id. There are three ways to set it, in order of precedence:

1. **`out="my-id"`** — explicit, always wins. Required for programmatic ids in a
   loop: `gm.point(i, 0, out=f"point-{i}")`.
2. **Assignment target** — the variable name becomes the id, with underscores
   turned into dashes. `fwd_traj = gm.point(3, 4)` → id `fwd-traj`. Multi-target
   works: `a, b, c = gm.scalar(1), gm.scalar(2), gm.scalar(3)` names all three.
   Name inference reads the caller's bytecode, so it behaves identically in
   files, the REPL, `python -c`, notebooks, and `exec`.
3. **Auto** — no target, or anything ambiguous/unsafe (attribute targets,
   reusing a name in a loop, an already-taken id, an engine-auto-name shape) →
   a dashed auto-id (`p-0`, `num-1`). Dashed ids can never collide with engine
   ids.

Explicit ids that violate the grammar raise. Prefer **descriptive names** — they
become descriptive DSL ids for free.

---

## 3. Built-in (system default) nodes

Every store starts with the engine's default nodes already registered. Reference
them without defining them, as `gm.<name>` (dashes → underscores) or
`gm.node("id")`. They record no commands and resolve against the active store.
You may reassign any of them (last-write-wins).

| `gm.` accessor | id | type | value | what it is |
| --- | --- | --- | --- | --- |
| `gm.p0` | `p0` | Point | `(0,0)` | world origin; default `center`/`point2` for many commands; hidden by default |
| `gm.learning_rate` | `learning-rate` | Scalar | `0.01` | step size for `\gradient-descent-step` / `\minimize` |
| `gm.animation_speed` | `animation-speed` | Scalar | `0.001` | per-frame step for `\animate` |
| `gm.grid_points` | `grid-points` | Array<Point> | integer lattice | every integer point on the visible canvas; reactive to `unit`/canvas |
| `gm.unit` | `unit` | Scalar | `50` | zoom: pixels per world unit (larger = more zoomed in) |
| `gm.grid_opacity` | `grid-opacity` | Scalar | `1` | grid/axis opacity; `0` hides the grid |
| `gm.grid_bg_color` | `grid-bg-color` | Text | `""` | solid fill behind the grid (empty = transparent) |
| `gm.grid_origin` | `grid-origin` | Point | `(0,0)` | where the world origin sits on canvas ((0,0) = centered); reassign to pan |
| `gm.T` | `T` | Bool | `true` | boolean literal |
| `gm.F` | `F` | Bool | `false` | boolean literal |

**Canvas geometry.** (0,0) is the *center* of the frame. The visible region in
world units is `x ∈ [-W/(2·unit), +W/(2·unit)]`, `y ∈ [-H/(2·unit), +H/(2·unit)]`
for a `W×H` pixel canvas. At the default `unit=50` on a ~640×640 canvas that is
roughly `x,y ∈ [-6.4, +6.4]`. Center constructions on the origin; size `unit` to
fit.

---

## 4. Node types and accessible properties

Property access returns a new node (e.g. `p.x` is a Scalar node). **Only the
whitelisted properties are accessible** — nothing else. This is the full list:

| Node type | Properties |
| --- | --- |
| Scalar | `.value` |
| Complex | `.re`, `.im` |
| Point | `.x`, `.y` |
| ScalarGradient | `.value` |
| PointGradient | `.x`, `.y` |
| Line | `.p1`, `.p2` |
| Arrow | `.p1`, `.p2` |
| Circle | `.center`, `.radius` |
| Ellipse | `.center`, `.radiusX`, `.radiusY`, `.rotation` |
| Arc | `.center`, `.radius`, `.startAngle`, `.endAngle` |
| RegularPolygon | `.center`, `.radius`, `.numVertices`, `.startAngle` |
| BezierQuadratic | `.p1`, `.control`, `.p2` |
| BezierCubic | `.p1`, `.control1`, `.control2`, `.p2` |
| Triangle | `.vertices` |
| Polygon | `.vertices` |
| Array | `.length` |

Chaining is allowed within the whitelist (`circ.center.x`). `len(arr)` returns a
plain Python int (records nothing), so `for k in range(len(arr)):` unrolls.

---

## 5. Arithmetic on nodes

Infix arithmetic works **on Scalar / Complex / Array nodes** and records the
overload command:

- `c = a + b` → `\add`; `- * /` → `\sub \mul \div`; unary `-` → `\neg`.
- Number literals may sit on either side (`2 * a`). Arrays broadcast elementwise.
- Same-op chains fuse into one variadic command: `a + b + c` → one `\add a b c`.
- `arr[i]` → `\get-array-element` (int or Scalar index; literal negative indices
  normalized). `arr[i] = v` is **not** supported.
- Chained assignment `a = b = gm.scalar(1)` records one command per target.

**Not** supported via infix (use the explicit function): `**` (`gm.pow_`), `@`,
in-place ops (`acc += 2` raises — assign a new name), infix on non-arithmetic
node types (Point, Circle, …), slices.

Plain Python numbers use normal arithmetic freely (loop-computed coordinates are
fine) — a command is recorded only when a node is involved.

---

## 6. Function library

The authoritative, always-current signatures come from
`gm.system_prompt()`. Signatures below are grouped for orientation; keep them in
sync when the registry changes.

**Conventions.** Function name = DSL keyword with dashes → underscores. Python
builtins that would clash get a trailing underscore: `abs_`, `pow_`, `min_`,
`max_`, `round_`, `bool_`, `and_`, `or_`, `not_`, `xor` (no clash but grouped),
`complex_`, `help_`, `filter_`. Arguments are **positional**; the only keyword
arg is `out=`. `# imperative` functions mutate/annotate existing nodes and return
no new value node. A `str` passed where a Text param is expected auto-records an
implicit `\text`; a Python `bool` for a Bool param auto-records `\bool`.

### Basic figures
`scalar(value)` · `text(value)` · `point(x=0, y=0)` ·
`triangle(v1, v2, v3)` · `line(p1, p2)` · `circle(center='p0', radius=2)` ·
`ellipse(center='p0', radiusX=3, radiusY=2, rotation=0)` ·
`bezier_quadratic(p1, control, p2)` · `bezier_cubic(p1, c1, c2, p2)` ·
`arc(center='p0', radius=2, startAngle=0, endAngle=90)` ·
`ellipse_from_foci(f1, f2, stringLength)`

### Planar geometry
`slope_of_line(line)` · `mid_point(p1, p2)` · `bisect_angle(l1, l2)` ·
`project_point(point, line)` · `reflect_point(point, line)` ·
`distance(p1, p2='p0')` · `angle(p1, vertex, p3)` · `area_triangle(tri)` ·
`area_circle(circle)` · `centroid(tri)` · `circumcenter(tri)` · `incenter(tri)`

### Intersections
`intersection_line_line` · `intersection_line_circle` ·
`intersection_line_ellipse` · `intersection_circle_circle` ·
`intersection_line_bezier_quadratic` (→ Array where more than one solution)

### Curves & plotting
`polynomial(*a0)` · `evaluate_polynomial(poly, x)` · `trail(*pointId)` ⟳ ·
`clear_trail(trailId)` ⟳ · `plot(x, y)` · `plot_inverse(x, y)` ·
`tangent(curve, x, length=2)`

### Polygons
`polygon_from_side(a, b, n=6)` · `polygon(v1, v2, *v3)` · `polyline(p1, *p2)` ·
`regular_polygon(center='p0', radius=2, numVertices=6, startAngle=0)` ·
`square(bottomLeft='p0', side=2, angle=0)` ·
`rectangle(bottomLeft='p0', width=3, height=2, angle=0)` ·
`convex_hull(p1, *p2)`

### Scalar functions
`sin cos tan asin acos atan log10 relu sigmoid tanh floor ceil round_ sign
reciprocal rad2deg deg2rad` (unary) · `atan2(a, b)` · `mod(a, b)` ·
`min_(a, *b)` · `max_(a, *b)` · `x_coord(point)` · `y_coord(point)`

### Complex functions
`complex_(re, im)` · `real(z)` · `imag(z)` · `conj(z)` · `arg(z)` ·
`fft(array)` · `ifft(array)`

### Tensor functions
`reduce_sum/min/max/mean/std/var(array, dim=-1)` · `softmax(array)` ·
`reshape(array, *dim)` · `linspace(start=0, end=1, n=10)` · `cumsum(array)` ·
`arange(start=0, end=5, step=1)` · `circular_arange(n=10, r=1)` ·
`ones/zeros(n=1)` · `ones_like/zeros_like(array)`

### Arrays
`array(*element1)` · `get_array_element(array, index)`

### Transformations (all imperative ⟳)
`translate_array(array, dx, dy)` · `translate(obj, dx, dy)` ·
`animate(s, animateTo)` · `rotate(obj, center, angle)`

### Autograd & optimization
`param(*id)` ⟳ · `backprop(id)` ⟳ · `partial(target, param)` ·
`gradient_descent_step(*id)` ⟳ · `reevaluate(id)` ⟳ ·
`minimize(value, num_iterations)` ⟳ · `vector_field(xId, yId)` ⟳ ·
`zero_grad()` ⟳

### Boolean & bitwise
`bool_(value)` · `gt ge lt le eq(a, b)` · `and_(*v)` · `or_(*v)` · `not_(v)` ·
`xor(a, b)` · `filter_(array, mask)` · `int_to_bin(value, nBits=8,
useTwosComplement='T')` · `uint_to_bin(value, nBits=8)` ·
`fp_to_bin(value, nBits=32)` · `bin_to_dec_unsigned/twos_complement/ones_complement(value)`

### ODEs / SDEs
`solve_ode(t, y, dydt, y0, t1, steps=200)` · `eval_ode(trajectory, t)` ·
`flow(point, out, p0, t1, steps=200)` ·
`simulate_sde(t, x, drift, diffusion, x0, t1, steps=200, seed=-1)`

### Special (imperative ⟳)
`clear()` (full store reset — removes ALL nodes) · `highlight(*id)` ·
`hide(*id)` · `show(*id)` · `copy(node)` · `remove(*id)` · `help_(id)` ·
`set_stroke(node, stroke)` · `set_fill(node, fill)`

### Annotations
`annotate_text_box(text, x=0, y=0, fontSize=14, width=0, height=0)` ·
`annotate_pin(position, label='')` · `annotate_arrow(p1, p2, padding=0,
label='')` · `annotate_curved_arrow(p1, p2, control, padding=0, label='')` ·
`annotate_dim_line(p1, p2, label='')` · `annotate_curly_bracket(p1, p2,
label='')` · `annotate_angle_mark(line1, line2, label='')` ·
`annotate_leader_line(p1, p2, label)` (label required)

Annotation furniture (arrowheads, offsets, label boxes) is sized in **fixed
screen pixels** (`/unit`), so it keeps a constant on-screen size at any `unit`.
`padding` on the arrow forms is a **fraction of length in `[0, 0.5]`**, not a
distance. `annotate_text_box` `(x, y)` is the **center**; `fontSize` is pixels,
`width`/`height` are canvas units (`≤0` = auto). `annotate_angle_mark` needs the
two lines to literally **share the same vertex point id** or it renders nothing.

### Overloaded (dispatch on Scalar | Complex)
`abs_ add div exp log mul neg pow_ sqrt sub` — `add`/`mul` are variadic.

### Macros (bundle → one tape line, body nodes referenceable)
`load_colors()` (see §7) · `fermat_point_of_a_triangle()` ·
`fermat_train_step()` · `gradient_of_an_angle()` · `mean_squared_loss(y,
target)` · `square_root_of_3()` · `plot_sqrt()` ·
`get_uniform_radian_angles(n)` · `get_uniform_points_on_circle(numPoints)` ·
`zero_back_step(loss)` · `peaucellier_lipkin_linkage()` · `cardioid()`

`⟳` = imperative (no new output node).

---

## 7. Colors

**Load the palette once up front, then reuse its names** — call
`gm.load_colors()` before you color anything and reference the loaded nodes
instead of defining colors ad hoc. It emits one `\load-colors` line (the macro is
auto-loaded on every interactive page) and returns the canonical palette as
referenceable Text nodes:

```python
c = gm.load_colors()
gm.set_stroke(v, c.BLUE)      # \set-stroke v COLOR-BLUE
gm.set_fill(label, c.AMBER)   # \set-fill label COLOR-AMBER
```

**Never redefine `COLOR-*` hex yourself** — the macro already defines every name
below. Reach for a raw hex only when the request supplies a specific shade the
palette lacks.

**Access:** single-word names as an attribute (`c.BLUE`, `c.BLACK`), any name by
id (`c["COLOR-BLUE"]`). Hyphenated ramp names are **only** reachable by id —
`c["COLOR-TEAL-LIGHT"]` works, `c.TEAL_LIGHT` raises `AttributeError`.

Full palette (29 names — this is the complete loaded set; `gm.PALETTE` is the
live id→hex map):

| name | hex | name | hex | name | hex |
| --- | --- | --- | --- | --- | --- |
| RED | `#F87171` | CYAN | `#22D3EE` | WHITE | `#F5F5F5` |
| ORANGE | `#F97316` | BLUE | `#6aa8ff` | GRAY | `#dddddd` |
| AMBER | `#F59E0B` | INDIGO | `#818CF8` | DARKGRAY | `#333333` |
| YELLOW | `#f0e080` | VIOLET | `#A78BFA` | BLACK | `#000000` |
| LIME | `#84CC16` | PURPLE | `#a988f5` | GRAY-LIGHT | `#d1d5db` |
| GREEN | `#10B981` | PINK | `#EC4899` | GRAY-MID | `#6b7280` |
| EMERALD | `#34D399` | FUCHSIA | `#E879F9` | GRAY-DARK | `#374151` |
| TEAL | `#14B8A6` | TEAL-LIGHT | `#5eead4` | RED-LIGHT | `#fca5a5` |
| VOLT | `#41dbc9` | TEAL-MID | `#14b8a6` | RED-MID | `#ef4444` |
|  |  | TEAL-DARK | `#0f766e` | RED-DARK | `#b91c1c` |

The canvas is dark; reserve WHITE/GRAY (and the GRAY ramp) for neutral
scaffolding, and `BLACK`/`DARKGRAY` are handy for `grid_bg_color` backgrounds.
The `-LIGHT/-MID/-DARK` ramps give a single hue three tints for shading related
elements.

**No LaTeX inside `gm.text`** — it renders plain text. Use Unicode glyphs
directly (`λ₁`, `v₂`, `Mᵀ`, `V⁻¹`, `θ`), never `$...$` / `^{-1}` / `\lambda`.
Reactive interpolation is allowed: `gm.text("scale = ${scale}")` updates live from
the referenced node. (KaTeX *is* fine in article prose and in `{label}(...)` link
labels — just not in `\text`.)

---

## 8. Authoring articles (the primary workflow)

Write a geomatic article as **markdown with pygeomatic Python**, and
`compile_article` turns it into the `{label}(command)` span format. The Python
runs **once at compile time**; readers only ever receive deterministic command
text. Everything shares **one store per article**, run in document order, so ids
and auto-names stay consistent across every fence and span.

Python appears in two places:

**` ```pygeomatic ` fences** — real Python (loops, comments, helpers). Top-level
code becomes hidden `{}(cmd)` setup spans where the fence sat. A
`with group("name"):` block collects a named run of commands for prose to reveal.

**Spans in prose:**
- `{label}(ref:name)` — expands a group: every command but the last becomes a
  hidden `{}()` span, the last becomes the visible labeled span, so a click
  always lands on a fully set-up scene.
- `{label}(python statement)` — inline one-off escape hatch. Article mode is
  **last-write-wins**, so `s = gm.scalar(1)` reassigns like the DSL line it
  becomes.

````markdown
```pygeomatic
origin = gm.p0                    # top-level → hidden {}(...) setup spans
a = gm.point(3, 0)
walk = gm.line(origin, a)
gm.hide(walk)

with group("walk-x"):             # a named run for prose to reveal
    gm.highlight(walk)
    gm.show(walk)                 # last command gets the visible label
```

Reach the point by {moving a distance}(ref:walk-x) of $3$ units.
Or reset inline: {set scale to 1}(scale = gm.scalar(1)).
````

**Rules and guarantees:**

- **Fence namespace is exactly `{gm, group}`.** Nothing else is in scope — no
  imports, no other names. Reach axis handles as `gm.rows` / `gm.cols` /
  `gm.dim(i)` (§9), never bare.
- **Regular code fences and `$...$` / `$$...$$` math are never scanned for
  spans** — a `}(` inside `$\tan^{-1}(y/x)$` is safe, and a ```` ```python ````
  block is copied through verbatim.
- **Round-trip gate.** The compiled doc is replayed with `parse_dsl` in document
  order; broken ordering or invalid DSL fails the **compile** (exit 1), not the
  reader.
- **Ref discipline (each an error):** unknown / unreferenced / doubly-referenced
  groups; a ref before its defining fence; refs out of the order their groups
  ran; empty or nested groups; duplicate group names; `group()` inside an inline
  span; an inline span that records no command.

**Entry points:**

| Purpose | Call / command |
| --- | --- |
| In-process compile | `gm.compile_article(md, allow_coercions=False)` |
| Sandboxed subprocess compile | `gm.run_article(md, extensions=(), macros=(), allow_coercions=False)` |
| One file (CLI) | `uv run python scripts/compile_article.py article.md [-o out.md] [--ext M.json ...] [--macros M.json ...] [--allow-coercions]` (stdin if no file) |
| A tree (CLI) | `uv run python scripts/compile_articles.py articles/ dist/ [same flags]` |

---

## 9. Live formulas — texatlas (`gm.tex`)

Make a KaTeX `$$…$$` formula **addressable and reactive**: a slot showing a store
node's live value, matrix cells highlighted or revealed by store nodes. This is
**not DSL** — no `\tex-*` keyword exists and `emit()` never sees it. Bindings are
harvested straight from the session into a trailing `<!-- texatlas:v1 {…} -->`
HTML comment on the compiled article (invisible to any markdown renderer). Python
never parses LaTeX or touches the DOM — only symbolic addresses and selector
trees cross the wire; occurrence/empty-slot/ambiguity errors surface in the
browser, not here.

**Addressing.** Give a formula an id with a `%id:name` line as the **first line**
inside the `$$…$$` block. `gm.tex("name")` returns a handle to that whole formula.
Reactivity always flows through the *store node* a binding references — driving
that node (`\scalar`, `\animate`, or reassigning it in a CommandLink) reflows the
formula with no re-render.

Two rules that bite otherwise:

- **Bind replaces content; it never creates structure.** Write placeholder
  symbols in every slot you bind (`\int_{a}^{b}`, not a bare `\int`). An empty
  slot fails validation browser-side.
- **The bound node must already exist** when you call `.bind()` / build a
  selector — define it (`gm.scalar(…, out="b")`) above the binding.

### 9a. Value bind

`t.<family>.<slot>.bind(node, show="value", fmt=None)`:

```python
b = gm.scalar(3)
energy = gm.tex("energy")         # matches %id:energy
energy.int.upper.bind(b)          # show b's value in the upper limit
energy.int.lower.bind(a, show="symbol")   # link without substituting the glyph
energy.int.upper.bind(b, fmt=".2f")       # or "d"; omit → trim to ≤4 dp
```

Registered families → slots (extend with `gm.register_tex_schema(family,
slots)`):

| Family | Slots |
| --- | --- |
| `int`, `sum`, `prod` | `lower`, `upper`, `body` |
| `frac` | `num`, `denom` |
| `sqrt` | `body` |
| `underbrace`, `overbrace` | `body`, `label` |

Repeated command (same family twice in one formula): `t.ints[1].upper` picks the
2nd occurrence — **discouraged** (an edit silently retargets it); prefer splitting
into two formulas with distinct ids.

### 9b. Highlight (matrix cells → color)

`t.highlight(selector, color="COLOR-YELLOW", matrix=0)`. A highlight is a
predicate over a cell's **grid position** (row/col index), never its content.
Build selectors from axis handles:

- **Axes:** `gm.rows`, `gm.cols`, `gm.dim(i)` (module-level; `dim(0)`=rows,
  `dim(1)`=cols; only dims 0–1 today). `t.rows()` / `t.cols()` are aliases.
- **Compare:** `== >= <= > <` (or `.eq/.ge/.le/.gt/.lt`) against a **node or
  int** — all reactive. `==` returns a `Selector`, not a bool (non-hashable).
- **Axis arithmetic:** `gm.cols - gm.rows`, `1 + gm.rows`, etc.
- **numpy-style boxes:** `M[3:, 4:]` (rows≥3 ∧ cols≥4), `M[:3, :]`
  (row<3), `M[r, ...]` (exact row r; trailing `...` = rest unconstrained). Slice
  `start` inclusive → `>=`, `stop` exclusive → `<`; a bare int/node → `==`; nodes
  stay reactive. Whole-matrix slice `M[:, :]` and a step `M[::2]` raise.
- **Named regions:** `M.diag(k=0)` (`col-row==k`), `M.triu(k=0)`
  (`col-row>=k`), `M.tril(k=0)` (`col-row<=k`).
- **Combine:** `&` / `|` (or `.and_` / `.or_`); regions stay paintable
  (`(M[3:, :] | M[:, 4:]).highlight()`).
- **Gate/fade:** `.scale(node)` multiplies the weight — `scale` by a node that
  starts at 0, then set it to 1 in a CommandLink, to reveal a highlight only
  after a click.

Colors: palette names (`"pink"`, `"BLUE"`) resolve to hex; raw `#f472b6` / CSS
names pass through. `matrix=N` picks the N-th matrix in a multi-matrix formula
(0-based source order, **skipping** equation-layout blocks like `aligned` /
`align` / `split` / `gather` / `CD`; counting `matrix` / `pmatrix` / `bmatrix` /
`array` / `cases` / …). You count — Python never parses the LaTeX. `matrix=0` is
omitted from the wire. Full reference: [tex-highlight-ergonomics.md](tex-highlight-ergonomics.md).

```python
r = gm.scalar(0)
M = gm.tex("M")
M.highlight(gm.rows == r, color="pink")   # row r
M.triu().highlight(color="blue")          # upper triangle
```

### 9c. Reveal (fade a part in — paints opacity)

Same selector machine as highlight, painting **opacity** instead of color. A
**gate** is any store node: a **bool** for all-or-nothing (`gm.bool_(False)` →
flip on by reassigning `b = gm.bool_(True)`), a **scalar** for an animatable
sweep (`gm.scalar(0)` → `gm.animate(k, 3)`). A bare gate node passed to
`.reveal(...)` lowers to the `{node}` leaf — no dummy comparison. Three targets:

```python
# over/underbrace — brace glyph + label; body stays visible
t.underbrace.reveal(b)               # or .label / .body for just that part

# derivation, line by line (the equation-layout / align block)
d.rows().reveal(gm.rows < k)         # k = #lines shown; align=N for multiple blocks

# matrix rows/columns (fade only — collapse breaks the grid)
M.reveal(M.cols() < k)               # matrix=N for a multi-matrix formula
```

**Count, not index:** for "reveal the first N" use strict `<` (`gm.rows < k`) so
the gate = *how many* show and `k=0` shows nothing. `mode="fade"` (default,
keeps layout) or `"collapse"` (also removes space; not allowed for matrices).
Full reference: [tex-reveal.md](tex-reveal.md).

### 9d. Harvest

`gm.harvest_tex_bindings(store=None)` returns the raw wire manifest
`{ texId: { "values": [...], "highlights": [...], "reveals": [...] } }` directly
(empty arrays and binding-free formulas dropped). `compile_article` calls this
automatically and snapshots it into the `<!-- texatlas:v1 … -->` comment after
the round-trip gate; articles with no bindings are byte-for-byte unchanged.

---

## 10. Extensions, macros, coercions

**Extensions** (`manifest.json`) add extra commands. They are pure graph-record
in Python — compute never runs here, so their outputs are record-only nodes with
`.numeric = None`.

```python
gm.load_extensions("manifest.json")     # path or URL; commands appear in system_prompt()
gm.unload_extensions("manifest.json")
```

Load an extension before authoring so its signatures show in `gm.system_prompt()`;
pass `--ext manifest.json` (repeatable) to the article/DSL CLIs.

**Macros** are bundles of commands recorded as one tape line while the body
replays locally (last-write-wins). The builtin set (`macros.json`) is registered
on import; add more with `gm.load_macros("macros.json")` / `gm.unload_macros(...)`,
or `--macros` on the CLIs. See the Macros list in §6.

**Coercions** (a `Line` accepted for a `Scalar`, an `Arrow` for an `Array`, …)
are **off by default** — pass exact node types. Enable per-scope with
`gm.allow_coercions(True)` (a context manager), the `allow_coercions=` kwarg on
`compile_article` / `run_article`, or `--allow-coercions` on the CLIs. The
coercion table (`coercions.json`) is generated from TypeScript.

---

## 11. Emitting DSL directly (the lower-level path)

When you want raw DSL rather than an article, write a `build(gm)` function and run
it through the emitter. This is how a designed static scene becomes pasteable DSL.

```python
def build(gm):
    unit = gm.scalar(30)
    v = gm.line(gm.p0, gm.point(3, 2))
    ...
```

```sh
uv run python scripts/build_to_dsl.py build.py [--ext manifest.json ...] [--allow-coercions]
```

Exit 0 → stdout is the DSL (numbers in positional notation, no scientific form).
Exit 1 → stderr is a type/emit error; fix `build.py` and re-run. In-process, an
active `Store` context plus `gm.emit()` does the same. `gm.parse_dsl(text)` is the
inverse — replay existing DSL onto the store, then modify via the returned
`nodes["id"]` map (the way to edit an existing scene without re-deriving it).

---

## 12. Gotchas cheat-sheet

- **One `gm.` call = one command.** Use Python loops for repetition.
- **No underscores in ids; never `<prefix><digits>` shapes** (`num0`, `p3`).
- **Article fence namespace is only `{gm, group}`** — axis handles via `gm.rows`
  etc., no imports.
- **`gm.clear()` wipes the whole store** — never reference a node across a clear.
- **`gm.text` is plain text, single-line** (newlines collapse to a space); use
  Unicode, not LaTeX.
- **Don't branch on `.numeric`** — many nodes are record-only (`None`). Structure
  comes from the request, not from reading values back.
- **texatlas: bind needs placeholder symbols in every slot; the bound node must
  exist first; reveal uses strict `<` for "first N".**
- **Coercions are off by default.**
