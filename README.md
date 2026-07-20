# pygeomatic

Python mirror of the [geomatic](https://www.tinyvolt.com/geomatic) DSL. Intended to be used in [Nova editor](https://www.tinyvolt.com/geomatic). 

Every public function maps 1:1 to a geomatic command; calling it computes numeric values (numpy) where
possible **and** records the call onto a tape, from which `emit()` produces
geomatic DSL lines deterministically.

## Naming

Every node has an id. You control it in three ways.

**Programmatically** — pass `out=` with an f-string (or any computed string),
so ids can be generated in a loop:

```python
>>> for i in range(5):
...   gm.point(i-3, 0, out=f'point{i}')
...
Point(id='point0', x=-3.0, y=0.0)
Point(id='point1', x=-2.0, y=0.0)
Point(id='point2', x=-1.0, y=0.0)
Point(id='point3', x=0.0, y=0.0)
Point(id='point4', x=1.0, y=0.0)
```

**By assignment** — the assignment target names the output (underscores become
dashes). Without a target, the id is auto-assigned a dashed form (`p-0`,
`num-1`):

```python
>>> my_p
Point(id='my-p', x=2.0, y=3.0)
>>> gm.point(3,2)
Point(id='p-0', x=3.0, y=2.0)
```

Assignment naming works at any arity — `a, b, c = gm.scalar(1), gm.scalar(2), gm.scalar(3)` names all three. 
An explicit `out="my-id"` always overrides the
inferred name.

Anything ambiguous or unsafe (no assignment target, attribute targets, reusing
a name in a loop, a name shaped like an engine auto-name, an already-taken id)
silently falls back to a dashed auto-id. Explicit ids must match the DSL
grammar: start with a letter, then letters/digits/dashes, **no underscores** —
and must not look like an engine auto-name (`num0`, `p3`, `text1`). The engine
generates those for its own internal nodes, and a collision creates a reactive
cycle that hangs the tab; pygeomatic's dashed ids can never collide. Name
inference reads the caller's bytecode, not its source, so it behaves
identically everywhere: files, the REPL, `python -c`, notebooks, `exec`'d
strings.

Whichever way a node was named, `gm.emit()` renders the tape as DSL, one line
per call, using each node's resolved id. The examples above emit as:

```
>>> print(gm.emit())
point0 = \point -3 0
point1 = \point -2 0
point2 = \point -1 0
point3 = \point 0 0
point4 = \point 1 0
my-p = \point 2 3
p-0 = \point 3 2
```


## Built-in variables

Every canvas — and every `Store` — starts with the engine's default nodes
already registered, so a scene may reference them by id without defining them
first. They record no commands (they exist implicitly on every canvas) and
resolve against the active store at access time. Access them as module
attributes with dashes turned into underscores (`gm.p0`, `gm.learning_rate`),
or by id with `gm.node("learning-rate")`.

You may reassign any of them (`gm.scalar(0.5, out="learning-rate")`), matching
the engine's last-write-wins `saveNode`.

| Variable | Value | What it is / when to use it |
| --- | --- | --- |
| `p0` | `(0, 0)` | The world origin. It is the default `center`/`point2` for many commands (`\circle`, `\ellipse`, `\square`, `\rectangle`, `\reflect-point`, …), so reference it for a fixed origin instead of re-declaring `\point 0 0`. |
| `learning-rate` | `0.01` | Gradient-descent step size, read by `\gradient-descent-step` and `\minimize`. Reassign before a descent step to tune training speed. |
| `animation-speed` | `0.001` | Per-frame step size for `\animate`. Reassign larger to make animations run faster, smaller to slow them. |
| `grid-points` | Point array | Every integer-lattice Point currently on the canvas (built from the live canvas bounds, so numerically unknown here). Reference it to act on the whole background grid at once, e.g. apply a linear map / `\translate-array` to every grid point. |
| `unit` | `50` | Zoom: pixels per world unit (`unitX == unitY == unit`). Reassign to zoom (larger = more zoomed in). |
| `grid-opacity` | `1` | Opacity of the grid lines and axes. Set to `0` to hide the grid. |
| `grid-bg-color` | `""` | Solid fill painted behind the grid (empty = transparent). Reassign to a color (`grid-bg-color = COLOR-BLACK`) to give the canvas a background. |
| `grid-origin` | `(0, 0)` | Where the world origin sits on the canvas, in world units (`(0, 0)` = centered). Reassign to pan the view. |
| `T` | `true` | The boolean literal `true`, referenceable wherever a Bool argument is expected. |
| `F` | `false` | The boolean literal `false`, referenceable wherever a Bool argument is expected. |

```python
gm.line(gm.p0, gm.point(1, 1))          # p0 by attribute
gm.scalar(0.5, out="learning-rate")     # reassign a default (last-write-wins)
gm.node("unit")                          # the string-keyed equivalent
```

## Authoring articles with Nova

Write geomatic articles as markdown with pygeomatic Python instead of raw DSL;
`compile_article` turns them into the `{label}(command)` span format. The Python
runs once at compile time — readers only ever receive deterministic DSL text.

````markdown
```pygeomatic
origin = gm.p0                    # top-level code → hidden {}(...) setup spans
a = gm.point(3, 0)
walk = gm.line(origin, a)
gm.hide(walk)

with group("walk-x"):             # a named run of commands for prose to reveal
    gm.highlight(walk)
    gm.show(walk)                 # last command gets the visible label
```

Reach the point by {moving a distance}(ref:walk-x) of $3$ units.
Or reset it inline: {set scale to 1}(scale = gm.scalar(1)).
````

- **One store per article**: all fences and inline spans run in document order
  sharing state, so ids and auto-names stay consistent.
- **Ref expansion**: every command of a group but the last becomes a hidden
  `{}()` span before the visible one — a click always lands on a fully set-up
  scene.
- **Inline spans** (`{label}(python statement)`) are the escape hatch for
  one-offs; article mode is last-write-wins, so `s1 = gm.scalar(1)` reassigns
  like the DSL line it becomes.
- **Round-trip gate**: the compiled document is replayed with `parse_dsl` in
  document order; broken ordering or invalid DSL fails the compile, not the
  reader.
- Regular code fences and `$...$` math are never scanned for spans.

```sh
uv run python scripts/compile_article.py article.md -o compiled.md   # one file
uv run python scripts/compile_articles.py articles/ dist/            # a tree
```

(equivalently `gm.compile_article(md)` in-process or `gm.run_article(md)` in a
subprocess; both take `extensions=` / `macros=` / `allow_coercions=`.)

### Publishing from a content repo (GitHub Action)

A content repo publishes compiled articles with one workflow file; a compile
error in any article fails the push and nothing is published:

```yaml
name: Publish articles
on:
  push: {branches: [main]}
jobs:
  publish:
    permissions: {contents: write}
    uses: TinyVolt/pygeomatic/.github/workflows/publish-articles.yml@main
```

This compiles `articles/` and force-pushes the result (plus any non-markdown
assets) to a `dist` branch, which raw.githubusercontent.com serves with CORS.
Inputs: `source`, `publish-branch`, `extensions`, `macros`, `allow-coercions`,
and `pygeomatic-ref` — pin the latter to a tag or SHA for reproducible output.
For custom pipelines, the composite action `TinyVolt/pygeomatic@<ref>` runs just
the compile step (the `<ref>` you pin is also the exact pygeomatic version
used).

### Reading published articles

Once the `dist` branch exists, the article is live — readers open it at

```
https://www.tinyvolt.com/nova/<username>/<repo>/<article>
```

where `<article>` is the markdown file's path within `dist` (the `.md` suffix
is optional). E.g. `articles/intro.md` compiled from the repo `alice/vectors`
is read at `/nova/alice/vectors/intro`.

If the article uses extension commands or macros, bake their URLs into the link
you share so readers never load anything manually:

- `?ext=<manifest-url>` — extension manifest, loaded (sandboxed, from
  whitelisted domains only) before the article renders.
- `?esm=<url>` — macro definitions, fetched and registered on page load.
