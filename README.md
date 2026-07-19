# pygeomatic

Python mirror of the geomatic DSL function library. Every public
function maps 1:1 to a geomatic command; calling it computes numeric values
(numpy) where possible **and** records the call onto a tape, from which
`emit()` produces geomatic DSL lines deterministically.

```python
import pygeomatic as gm

with gm.Store() as s:
    a = gm.point(1, 2)             # assignment target → output id `a`
    b = gm.point(4, 6)
    d = gm.distance(a, b)          # float(d) == 5.0
    c = gm.circle(a, 3)
    m = gm.mid_point(c.center, b)  # property access → `c.center`
    gm.highlight(a, b)
    print(gm.emit(s))
```

```
a = \point 1 2
b = \point 4 6
d = \distance a b
c = \circle a 3
m = \mid-point c.center b
\highlight a b
```

## Conventions

- **Function names** = DSL keyword with dashes → underscores (`reduce-sum` →
  `reduce_sum`). Names that would shadow Python builtins get a trailing
  underscore: `abs_`, `pow_`, `min_`, `max_`, `round_`, `bool_`, `filter_`,
  `and_`, `or_`, `not_`, `complex_`, `help_`.
- **Output ids**: an assignment target names the output —
  `fwd_traj = gm.point(3, 4)` emits `fwd-traj = \point 3 4` (underscores
  become dashes), and multi-target assignment works at any arity:
  `a, b, c = gm.scalar(1), gm.scalar(2), gm.scalar(3)` names all three. The
  optional `out="my-id"` keyword overrides it. Chained `a = b = gm.scalar(1)`
  records one command per target (`a = \scalar 1`, `b = \scalar 1`; the
  python object carries the first id, the store holds a clone per extra).
  Anything ambiguous or unsafe (no assignment, attribute targets, loop reuse
  of a name, a name shaped like an engine auto-name, a taken id) silently
  falls back to a dashed auto-id (`num-0`, `p-1`). Explicit ids must match the DSL grammar:
  start with a letter, letters/digits/dashes, **no underscores** — and must
  not look like engine auto-names (`num0`, `p3`, `text1`): the engine
  generates those for internal nodes (property accessors, literals, array
  elements) and a collision creates a reactive cycle that hangs the tab.
  pygeomatic's dashed ids can never collide. Inference reads the caller's
  bytecode, not its source, so it behaves identically everywhere: files,
  `run_generated`, the REPL, `python -c`, notebooks, `exec`'d strings.
- **Infix arithmetic** works on Scalar / Complex / Array nodes (with number
  literals on either side): `c = a + b` records `c = \add a b`; `- * /` and
  unary `-` map to `\sub`, `\mul`, `\div`, `\neg`, and Arrays broadcast
  elementwise. Chains of the same associative op fuse into ONE variadic
  command: `d = a + b + c` emits `d = \add a b c`. `**`/`@`, in-place ops
  (`acc += 2` would silently diverge from the reactive node — write
  `total = acc + 2`), and infix on any other node type (Point, Circle, ...)
  raise instructively — use the explicit functions (`gm.pow_`,
  `gm.translate`, ...).
- **Array indexing / iteration**: `x = arr[i]` records
  `x = \get-array-element arr i` (`i` an int or a Scalar node; literal
  negative indices are normalized against the record-time length — the engine
  has no negative indexing). `len(arr)` is a plain record-time int (records
  nothing), so `for k in range(len(arr)): arr[k]` and `for el in arr:` unroll
  into one command per element. Slices and `arr[i] = v` have no DSL
  equivalent and raise.
- **Node properties** are exactly the whitelist in
  [nodeProperties.ts](../src/lib/geomatic/state/nodeProperties.ts)
  (`p.x`, `circ.center`, `circ.center.x`, ...); each access returns a node that
  serializes to the `base.field` argument form. Read raw numbers via
  `node.numeric`, `float(node)`, `complex(node)`.
- **str / bool convenience**: passing a Python `str` for a Text parameter (or
  `bool` for a Bool parameter) records an implicit `\text "..."` / `\bool`
  command first, then references it.
- **Strings as node references (auto-create)**: a `str` filling any *other*
  parameter names a node by id — the existing node under that id, or, for
  Point/Scalar parameters, a fresh auto-created node exactly like the engine
  (`CommandExecutor.createAndSavePoint/Scalar`): `gm.line("a", "b")` creates
  Points `a`, `b` with random coordinates, `gm.point("x", "y")` creates
  Scalars `x`, `y` with random values. Auto-created nodes are store-only —
  no tape command — so the emitted DSL references the bare id and the engine
  auto-creates it again on replay. The same applies to unknown ids in
  `parse_dsl` lines (`\line a b`, `\triangle a b c`), where an unknown id in
  a Text slot also auto-creates (id becomes the value), mirroring
  `createAndSaveText`.
- **System default nodes**: every canvas (and every `Store`) starts with the
  engine's defaults — `p0` (the origin), `T`/`F`, `learning-rate`,
  `animation-speed`, `unit`, `grid-points`, `grid-opacity`, `grid-bg-color`,
  `grid-origin` — so reference them directly without defining them:
  `gm.line(gm.p0, gm.point(1, 1))` (dashed ids become underscores:
  `gm.learning_rate`). They record no commands and resolve against the active
  store at access time; reassigning one (`gm.scalar(0.5, out="learning-rate")`)
  is allowed, matching the engine's last-write-wins `saveNode`. `gm.node(id)`
  is the string-keyed equivalent.
- **Record-only commands**: functions whose computation lives in the engine
  (plot, tangent, solve-ode/flow/simulate-sde, autograd ops, highlight/hide/...)
  record onto the tape with correct signatures but produce nodes with unknown
  (`None`) numerics. `translate`/`rotate`/`animate` do update numerics (final
  state).

## Prompt → DSL generation (model-agnostic)

Three functions turn a natural-language prompt into DSL commands with any LLM;
pygeomatic never imports a provider SDK — you inject the model call:

```python
import pygeomatic as gm

# 1. the system prompt (rendered from the live registry, never drifts)
system = gm.system_prompt()

# 2. your adapter: any callable (system, messages) -> reply text
def complete(system: str, messages: list[dict]) -> str:
    # messages: [{"role": "user"|"assistant", "content": str}, ...]
    # call OpenAI / Anthropic / a local model / anything, return the text
    ...

# 3. the loop: generate build(gm), run it, feed errors back (max_attempts tries)
result = gm.generate_dsl("a unit circle with 8 highlighted points on it", complete)
print("\n".join(result.dsl))   # geomatic DSL commands, ready to paste
print(result.code)             # the python the model wrote
print(result.attempts)         # how many tries it took
```

Example adapter for an OpenAI-compatible chat endpoint (no SDK needed):

```python
import json, urllib.request

def complete(system, messages):
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, *messages],
    }
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)["choices"][0]["message"]["content"]
```

The pieces are usable separately:

- `gm.system_prompt() -> str` — the full instructions + function reference.
- `gm.run_generated(code, timeout=20) -> RunResult` — executes code that
  defines `build(gm)` in a subprocess (same interpreter, so run it from an
  environment where pygeomatic is installed) and returns `.dsl` or `.error`.
- `gm.generate_dsl(prompt, complete, max_attempts=3) -> GenerateResult` —
  the retry loop; raises `gm.GenerationError` (with the transcript) when all
  attempts fail.

The model is asked to reply with one fenced code block defining `build(gm)`;
the harness (runner.py) owns the Store/emit plumbing. Errors — bad ids,
infix arithmetic, wrong arity, timeouts — come back as Python tracebacks and
are fed to the model verbatim for the next attempt.

## Type checking & coercions

Each argument is checked against the parameter type at emission (the same
acceptance rule as the engine's `CommandExecutor`), so a wrong-typed argument
raises in Python instead of producing DSL that fails in the browser. `Any`
takes anything, exact types pass, and an `Array` broadcasts into a scalar param
when its element type matches (`\point xs ys`).

The engine's **type-coercions** (feeding a `Line` where a `Scalar` is wanted,
an `Arrow` where an `Array` is wanted, ...) are **on by default**. Force strict
exact-type matching for a block with `allow_coercions(False)`:

```python
with gm.allow_coercions(False):
    gm.text(a_scalar)          # raises: Scalar is not a Text
```

The coercion table is **not hardcoded**: it is generated from the live
TypeScript into `src/pygeomatic/coercions.json` by `npm run gen:registry`
(which probes `canCoerce`/`canCoerceValue` over every node-type pair), so adding
a coercion in `type-coercion.ts` and regenerating is all it takes.

## Parsing DSL back (modification round-trips)

`gm.parse_dsl(text) -> dict[str, GNode]` is the inverse of `emit`: it replays
each line through the registered python functions onto the active store and
returns the store's id → node map, so you can modify a pasted scene
deterministically:

```python
with gm.Store() as s:
    nodes = gm.parse_dsl(existing_dsl)
    gm.rotate(nodes["v"], nodes["center"], 30)
print(gm.emit(s))   # original lines round-tripped + the new commands
```

Grammar = exactly what emit produces (numbers, id refs, whitelist-checked
property chains, quoted strings for `\text` only). An unknown bare id filling
a Point/Scalar/Text parameter is auto-created engine-style (random payload,
Text gets its id as value); any other parameter type enforces
define-before-use. Engine-generated ids (`p0`, `num1`, ...) are accepted while
parsing — pasted scenes contain them — but stay rejected for authored
`out=` ids. Failures raise `gm.DslParseError` with the line number and line.
Extension commands parse once their manifest is loaded. A bare `\point 1 2`
re-emits with an auto id (`p-0 = \point 1 2`): same scene, different text.

## Articles: pygeomatic-in-markdown → CommandLink articles

Write geomatic articles as markdown with pygeomatic Python instead of raw DSL;
`compile_article` turns them into the `{label}(command)` span format. The Python runs once at compile time —
readers only ever receive deterministic DSL text.

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
  `{}()` span before the visible one — a click always lands on a fully
  set-up scene.
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
For custom pipelines, the composite action `TinyVolt/pygeomatic@<ref>` runs
just the compile step (the `<ref>` you pin is also the exact pygeomatic
version used).

### Reading published articles

Once the `dist` branch exists, the article is live — readers open it at

```
https://www.tinyvolt.com/nova/<username>/<repo>/<article>
```

where `<article>` is the markdown file's path within `dist` (the `.md`
suffix is optional). E.g. `articles/intro.md` compiled from the repo
`alice/vectors` is read at `/nova/alice/vectors/intro`.

If the article uses extension commands or macros, bake their URLs into the
link you share so readers never load anything manually:

- `?ext=<manifest-url>` — extension manifest, loaded (sandboxed, from
  whitelisted domains only) before the article renders.
- `?esm=<url>` — macro definitions, fetched and registered on page load.

## Extensions

Geomatic extension functions (loaded in the app from a `manifest.json`, see
`src/lib/geomatic/functions/extensionLoader.ts`) can be registered
dynamically. pygeomatic never runs their `compute` — emission only needs the
signature metadata the manifest carries, so extension calls are pure graph
record: outputs are record-only nodes of the declared `outputType` with
`.numeric` `None`.

```python
gm.load_extensions("dist/manifest.json")   # path or URL; returns keywords
gm.la_vec2d(3, 4, out="v")                 # callable like any builtin
gm.loaded_extensions()                     # {source: [keywords]}
gm.unload_extensions("dist/manifest.json")
```

The registry is live: `system_prompt()` includes loaded extensions (category
`Extensions`) and drops them on unload. Re-loading a source replaces its
functions; colliding with a builtin keyword or another loaded source raises
`gm.ManifestError`. In the manifest, a required parameter must omit `default`
(or set it to `null`) — a present non-null `default` makes it optional. Only
the extension's `main` output is addressable; aux composite outputs exist
host-side only. `outputType`s outside the builtin node set get a generic
node (no properties) and dashed auto-ids (`widget-0`).

Subprocess runs start fresh, so pass manifests through:

```sh
uv run python scripts/build_to_dsl.py build.py --ext dist/manifest.json
```

(equivalently `gm.run_generated(code, extensions=[...])`).

## Macros

A macro is a named bundle of DSL commands — the format `downloadMacro.ts`
exports and `MacroLoader.ts` registers: `{"macro": "<name> [param ...]",
"commands": [...]}`. The builtin set the interactive editor auto-loads
(`public/geomatic/macros/geometry.json`) ships with pygeomatic as
`src/pygeomatic/macros.json` (a parity test keeps the copies identical) and is
registered on import, so `\load-colors`, `\zero-back-step loss`, ... parse and
are callable.

Invoking a macro records ONE line on the tape (never its body — parse → emit
still round-trips) while the body is replayed locally with engine semantics:
parameter names substituted by argument ids, unnamed body lines given the
engine's undashed auto ids (`p1`, `num0`), last-write-wins on reassignments.
Every node the body defines becomes a real store node later calls can
reference. An `id = \macro ...` invocation assigns the id to the last body
command if that command has no id of its own.

```python
gm.load_macros("my-macros.json")           # path, URL, JSON string, or a
gm.load_macros([{...}], name="inline")     #   parsed list (name it for unload)
gm.zero_back_step(loss)                    # callable like any builtin
gm.loaded_macros()                         # {source: [keywords]}
gm.unload_macros("my-macros.json")
```

Collisions with builtins, extensions, or another source raise
`gm.MacroError`; re-loading a source replaces its macros. `gm.load_colors`
invokes the `load-colors` macro (identical store effect to the DSL line) and
wraps the created nodes in a `ColorPalette` (`pal.BLUE`); `gm.PALETTE`
(id → hex) is derived from the macro body, nothing is hardcoded.
Subprocess runs: `build_to_dsl.py build.py --macros my-macros.json`
(equivalently `gm.run_generated(code, macros=[...])`).

## Text is single-line

The DSL is line-based and the canvas renders text as single-line SVG `<text>`,
so newlines can neither be emitted nor displayed. Any newline in a text value
(with surrounding indentation) is collapsed to a single space at record time,
for `gm.text` and implicit Text coercions alike — use separate text nodes, not
`\n`, for multi-line layouts.

## Parity with the TypeScript registry

`registry.json` (function signatures) and `src/pygeomatic/coercions.json` (the
type-coercion table) are both generated from the live TS:

```sh
npm run gen:registry   # → python/registry.json + python/src/pygeomatic/coercions.json
```

`tests/test_parity.py` asserts the Python registry matches it exactly
(keywords, parameter names/types/variadic/defaults, output types,
imperative/async flags, categories, overload operand types). Re-run it after
changing TS functions.

## Development

```sh
cd python
uv sync
uv run pytest
```
