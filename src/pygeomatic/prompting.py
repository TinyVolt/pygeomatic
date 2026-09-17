"""LLM-facing system prompt, rendered from the live Python registry.

`system_prompt()` produces the full instructions for a model that must write a
`def build(gm): ...` function using pygeomatic. It is generated from REGISTRY
(which the parity test pins to the TS registry), so the documented signatures
can never drift from the code.

Everything here is model-agnostic text; no provider SDK is involved.
"""

from __future__ import annotations

from .nodes import NODE_PROPERTIES
from .registry import REGISTRY, FunctionDef, P
from .system_nodes import SYSTEM_NODES

# Keywords whose python name would shadow a builtin get a trailing underscore.
_BUILTIN_SHADOWS = {
    "abs",
    "pow",
    "min",
    "max",
    "round",
    "bool",
    "filter",
    "and",
    "or",
    "not",
    "complex",
    "help",
}


# Keywords deliberately exposed under a more descriptive python name than the
# wire keyword (the DSL keyword — and the emitted `\<keyword>` — is unchanged).
_DESCRIPTIVE_ALIASES = {
    "plot": "plot_reactive",
    "partial": "partial_derivative",
}


def python_name(keyword: str) -> str:
    """The pygeomatic attribute name for a DSL keyword (`reduce-sum` → `reduce_sum`,
    `abs` → `abs_`, `plot` → `plot_reactive`)."""
    if keyword in _DESCRIPTIVE_ALIASES:
        return _DESCRIPTIVE_ALIASES[keyword]
    name = keyword.replace("-", "_")
    if keyword in _BUILTIN_SHADOWS:
        name = f"{name}_"
    return name


def _param_sig(p: P) -> str:
    if p.variadic:
        return f"*{p.name}"
    if p.has_default:
        return f"{p.name}={p.default!r}"
    return p.name


def _fn_line(f: FunctionDef) -> str:
    params = ", ".join(_param_sig(p) for p in f.params)
    sig = f"gm.{python_name(f.keyword)}({params})"
    out = f.output_type
    notes = []
    if f.is_imperative:
        notes.append("imperative: acts on existing nodes, no output id")
    if f.is_macro:
        notes.append("macro: expands to a bundle of commands; the nodes its body defines become referenceable")
    if f.operand_types:
        notes.append(f"dispatches on {' | '.join(f.operand_types)}")
    suffix = f"  # {'; '.join(notes)}" if notes else ""
    return f"- `{sig} -> {out}`{suffix}"


def _function_reference() -> str:
    by_category: dict[str, list[FunctionDef]] = {}
    for f in REGISTRY.values():
        by_category.setdefault(f.category, []).append(f)
    sections = []
    for category, fns in by_category.items():
        lines = "\n".join(_fn_line(f) for f in fns)
        sections.append(f"### {category}\n{lines}")
    return "\n\n".join(sections)


def _system_node_reference() -> str:
    lines = []
    for spec in SYSTEM_NODES:
        node_type = type(spec.factory()).__name__
        attr = spec.id.replace("-", "_")
        lines.append(f"- `gm.{attr}` ({node_type}, id `{spec.id}`): {spec.doc}")
    return "\n".join(lines)


def _property_reference() -> str:
    lines = []
    for node_type, props in NODE_PROPERTIES.items():
        rendered = ", ".join(f"`.{name}` → {t}" for name, t in props.items())
        lines.append(f"- {node_type}: {rendered}")
    return "\n".join(lines)


_RULES = """\
You write Python code that builds a geomatic scene. Reply with ONE fenced
python code block defining exactly this function:

```python
def build(gm):
    ...
```

The harness imports pygeomatic as `gm`, opens a fresh store, calls
`build(gm)`, and converts the recorded calls into geomatic DSL commands.
Do not import anything, do not create a Store, do not call `gm.emit` — only
define `build`.

Rules (violations raise errors):
1. Arguments are POSITIONAL, in the documented order. An assignment target
   names the output node: `fwd_traj = gm.point(3, 4)` emits
   `fwd-traj = \\point 3 4` (python underscores become DSL dashes), and
   multi-target assignment names every output
   (`a, b = gm.scalar(1), gm.scalar(2)`), so descriptive variable names give
   descriptive ids for free. The only keyword argument is `out="my-id"` for
   an id different from the variable. Explicit ids must start with a letter
   and contain only letters, digits and dashes — NEVER underscores
   (`fwd-traj`, not `fwd_traj`). Never use ids shaped like
   `<prefix><digits>` (`num0`, `p3`, `text1`): the engine auto-generates
   those for internal nodes and they collide (inferred names of that shape
   are skipped automatically). Prefer descriptive names.
2. Infix arithmetic works on Scalar/Complex/Array nodes and records the
   overload commands: `c = a + b` emits `c = \\add a b`; `- * /` and unary
   `-` map to \\sub, \\mul, \\div, \\neg; number literals may sit on either
   side (`2 * a`); Arrays broadcast elementwise. Same-op chains fuse into
   one variadic command (`d = a + b + c` emits `d = \\add a b c`).
   `%` maps to \\mod (`r = a % b` emits `r = \\mod a b`), but only for
   Scalars and Arrays — \\mod takes no Complex operand, and `%` chains do
   not fuse.
   `x = arr[i]` emits `x = \\get-array-element arr i` (int or Scalar index;
   literal negative indices are normalized), and `len(arr)` is a plain
   python int recorded as nothing, so `for k in range(len(arr)):` unrolls.
   Chained `a = b = gm.scalar(1)` records one command per target name.
   NOT supported (use the explicit functions): `**` (`gm.pow_`), `@`,
   in-place ops (`acc += 2`, `acc %= 2` raise — assign a NEW name:
   `total = acc + 2`),
   infix on other node types (Point, Circle, ...), slices, `arr[i] = v`.
   Plain Python numbers still use normal arithmetic freely (e.g.
   loop-computed coordinates); a command is recorded only when a node is
   involved.
3. Node properties are limited to the full whitelist under "Accessible node
   properties" below; a few examples: `p.x`, `circ.center`, `circ.center.x`,
   `tri.vertices`, `arr.length`. Nothing outside that list is accessible.
4. Functions marked "imperative" mutate/annotate existing nodes and return no
   new value node.
5. Do NOT branch on computed node values: many functions are record-only and
   their `.numeric` is None. Scene structure must come from the request, not
   from reading values back. You may use plain-Python loops/variables to
   organize repeated calls.
6. A `str` passed for a Text parameter and a Python `bool` for a Bool
   parameter are auto-converted (an implicit `\\text` / `\\bool` command is
   recorded). `gm.text("...")` is the explicit form.
7. Optional trailing arguments may be omitted; the engine applies the
   documented default. Pass them explicitly only when you need non-default
   values.
"""


_LIVE_GRAPH = """\
## The scene is a live graph

This is the most important thing to understand. Everything else follows from it.

Every `gm.*` call makes a node, and a node's value is computed from its input
nodes. The engine keeps that link alive: when an input changes, every node built
from it recomputes at once, and so does everything built from those, all the way
down. Inputs change, for example, when `gm.animate` runs or a gradient step
updates a parameter.

So build a scene as a chain of dependencies:

- Make the free inputs once, from plain numbers (`r = gm.scalar(2)`,
  `c = gm.point(0, 0)`).
- Build everything else from those nodes: `circ = gm.circle(c, r)`,
  `d = 2 * r`, `tip = gm.point(c.x, d)`. Change `c` or `r`, and all of it
  follows.
- Never type a value that should come from a node. `d = gm.scalar(4)` looks the
  same as `d = 2 * r` today, but has no link to `r` and will not follow it.
- Python never knows the live values. Do the math with nodes, not with Python
  numbers read from nodes.
- Assigning a name that already exists replaces that node, and everything built
  from the old one breaks. Use a new name for every node.

### Commands that take a formula

Some commands take an input node and an output node built from it. The engine
reads the chain of nodes between them as a function, and evaluates it at many
input values itself.

- The input node is only a placeholder. Its own value is ignored (except that
  `t` in `solve_ode` and `simulate_sde` sets the start time).
- The output must be built from the input through `gm` calls. If it does not
  depend on the input, nothing fails, but the result is wrong: a flat plot,
  identical arrows.
- Every other node the formula uses stays live. Change it, and the result
  redraws.
- Give each role its own node. Never reuse a formula's placeholder as an
  ordinary value somewhere else, even when the numbers match.

```python
def build(gm):
    # plot_reactive(x, y): y as a function of x, swept across the canvas.
    x = gm.scalar(0)
    a = gm.scalar(0.5)
    parabola = a * x * x
    gm.plot_reactive(x, parabola)     # changing a redraws it

    # vector_field(p, out): p is a Point. If out is a Point, the arrow at p is
    # out. If out is a Scalar, the arrow at p is the gradient of out.
    p = gm.point(0, 0)
    neg_y = -p.y
    v = gm.point(neg_y, p.x)
    gm.vector_field(p, v)             # rotation field; imperative, do not assign
    f = p.x * p.x + p.y * p.y
    gm.vector_field(p, f)             # gradient field (2x, 2y)

    # flow(p, out, start, duration, steps=200): follows the same kind of field.
    start = gm.point(2, 0)
    duration = gm.scalar(3)
    orbit = gm.flow(p, v, start, duration)

    # solve_ode(t, y, dydt, y_start, t_end, steps=200): dy/dt from t and y.
    t = gm.scalar(0)                  # its value is the start time
    y = gm.scalar(0)                  # placeholder
    dydt = t - y
    y_start = gm.scalar(1)
    t_end = gm.scalar(4)
    curve = gm.solve_ode(t, y, dydt, y_start, t_end)

    # partial_derivative(target, param): target built from param; stays live.
    w = gm.scalar(2)
    loss = w * w
    slope = gm.partial_derivative(loss, w)   # 4 now, and follows w
```

The same pattern holds for `plot_inverse(x, y)` (sweeps along the vertical
axis) and `simulate_sde(t, x, drift, diffusion, x0, t1, steps=200, seed=-1)`
(drift and diffusion are formulas of `t` and `x`).
"""


def system_prompt() -> str:
    """Complete system prompt for prompt→python→DSL generation."""
    return (
        f"{_RULES}\n"
        f"{_LIVE_GRAPH}\n"
        f"## System default nodes\n"
        f"Every canvas starts with these nodes; reference them directly as "
        f"`gm.<name>` (or reassign their id with `out=`) without defining "
        f"them first:\n{_system_node_reference()}\n\n"
        f"## Accessible node properties\n{_property_reference()}\n\n"
        f"## Function reference (python signature -> output node type)\n\n"
        f"{_function_reference()}\n"
    )
