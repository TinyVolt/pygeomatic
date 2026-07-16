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


def python_name(keyword: str) -> str:
    """The pygeomatic attribute name for a DSL keyword (`reduce-sum` → `reduce_sum`,
    `abs` → `abs_`)."""
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
1. Arguments are POSITIONAL, in the documented order. A simple assignment
   target names the output node: `fwd_traj = gm.point(3, 4)` emits
   `fwd-traj = \\point 3 4` (python underscores become DSL dashes), so
   descriptive variable names give descriptive ids for free. The only
   keyword argument is `out="my-id"` for an id different from the variable.
   Explicit ids must start with a letter and contain only letters, digits
   and dashes — NEVER underscores (`fwd-traj`, not `fwd_traj`). Never use
   ids shaped like `<prefix><digits>` (`num0`, `p3`, `text1`): the engine
   auto-generates those for internal nodes and they collide (inferred names
   of that shape are skipped automatically). Prefer descriptive names.
2. NO infix arithmetic on nodes: never `a + b`, `a * 2`, `-a` — use
   `gm.add(a, b)`, `gm.mul(a, 2)`, `gm.neg(a)`. Plain Python numbers may use
   normal arithmetic freely (e.g. in a `for` loop computing coordinates);
   only node objects must go through gm functions. Each gm call becomes
   exactly one DSL command, so prefer fewer, well-chosen calls.
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


def system_prompt() -> str:
    """Complete system prompt for prompt→python→DSL generation."""
    return (
        f"{_RULES}\n"
        f"## Accessible node properties\n{_property_reference()}\n\n"
        f"## Function reference (python signature -> output node type)\n\n"
        f"{_function_reference()}\n"
    )
