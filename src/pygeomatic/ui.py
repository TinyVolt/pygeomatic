"""gm.ui — reader-facing controls (slider, checkbox, ...) embedded in prose.

An author makes a control, then drops it into a sentence with an f-string:

    r = gm.ui.slider(1, 5, step=0.5, value=3, label="radius")
    c = gm.circle(gm.p0, r)
    gm.md(f"Drag to resize the circle: {r}")

Three properties define the shape (borrowed from marimo, whose `mo.ui` this
mirrors — see the plan notes for the source references):

1. **The control drives a node; the node drives everything else.** A widget
   records one ordinary command (`r = \\scalar 3`) and returns the very node
   that command produced, so `gm.circle(gm.p0, r)`, arithmetic on `r` and
   `gm.tex(...).bind(r)` all work unchanged. At read time the browser writes
   the reader's value into that node and the store recomputes the canvas and
   any bound formulas on its own. There is no python at read time and no
   round-trip: marimo re-runs a kernel cell, we just move a node.

2. **The settings travel on the element.** Every option becomes a `data-*`
   attribute holding JSON, inline in the markdown where the f-string put it.
   Nothing is stored in a separate manifest (unlike gm.tex), so a control needs
   no reader-side lookup step and appears exactly where it was written.

3. **`__format__` is the only entry point.** Widgets are recorded on a channel
   separate from the command tape (`Store.ui_widgets`, keyed by node id) and
   `gm.emit()` never sees them. `GNode.__format__` reads that channel — which
   is why one node may carry at most one widget: the lookup is by node id, so
   two widgets on `r` would make `f"{r}"` ambiguous.

The escaping in `_attr` is load-bearing and copied deliberately; see its
docstring.

`gm.ui.onclick` (onclick.py) also lives in this namespace but is a different
mechanism: a control drives a node's VALUE, a handler runs COMMANDS when the
reader clicks the node on the canvas.
"""

from __future__ import annotations

import json
import re
from html import escape
from typing import Optional, Sequence, Union

from .nodes import GNode
from .onclick import OnClickError, onclick, open_handler  # noqa: F401 — gm.ui.onclick
from .store import IDENTIFIER_RE, current_store


class UIError(ValueError):
    """A gm.ui control could not be created (bad options, or a node that
    already has a control)."""


# Node types that print their value when interpolated into an article string
# (`gm.md(f"the side is {side}")`); everything else prints its id. See
# `GNode.__format__`.
READOUT_TYPES = frozenset({"Scalar", "Text", "Bool"})

# Number formats the browser's `formatValue` implements: `.Nf` (fixed), `.N%`
# (percent, value * 100 with a trailing sign), `d` (round to int). Keep in sync
# with format.ts / CONTRACT.md — a format accepted here but unknown there falls
# through to a raw `String(value)`. Shared by readouts and `gm.tex(...).bind`,
# so an author learns one grammar.
FMT_RE = re.compile(r"\.\d+[f%]\Z|d\Z")


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------


def _attr(name: str, value) -> str:
    """One `data-<name>='<json>'` attribute, escaped to survive the whole
    pipeline. Each replacement below fixes a real breakage:

    - `<` / `>` become unicode escapes *inside* the JSON so an HTML sanitiser
      cannot see tag-like text in an attribute and strip it;
    - `html.escape` then handles `&` and both quote characters (we quote with
      `'`, so `'` must be escaped);
    - `\\` and `$` become entities last, because markdown eats backslashes and
      because our own article compiler skips `$...$` regions when it scans for
      command links — an unescaped `$` in a label would desynchronise that scan
      and silently swallow the rest of the paragraph.

    The browser reverses all of it: the HTML parser decodes the entities and
    `JSON.parse` decodes the unicode escapes.
    """
    encoded = json.dumps(value, separators=(",", ":"))
    encoded = encoded.replace(">", "\\u003e").replace("<", "\\u003c")
    encoded = escape(encoded)
    encoded = encoded.replace("\\", "&#92;").replace("$", "&#36;")
    return f"data-{name}='{encoded}'"


def render_widget_html(spec: dict) -> str:
    """The control's HTML, on ONE line.

    Single-line matters: markdown treats an indented line as a code block, and
    an f-string inside an indented triple-quoted `gm.md(...)` would otherwise
    hand markdown multi-line HTML and get it rendered as source.

    `kind` and `node` are written plainly rather than as JSON. Both are
    validated identifiers, so they need no escaping, and keeping them readable
    makes the compiled markdown far easier to eyeball. Every OTHER attribute is
    JSON, so the browser parser's rule is simply: those two are strings, the
    rest are JSON.
    """
    options = spec.get("options", {})
    attrs = " ".join(
        _attr(name, value)
        for name, value in options.items()
        if value is not None
    )
    return (
        f'<span class="nova-ui" data-kind="{spec["kind"]}" '
        f'data-node="{spec["node"]}"'
        f'{" " + attrs if attrs else ""}></span>'
    )


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def _register(node: GNode, kind: str, options: dict) -> None:
    """Attach a widget to the node a constructor just recorded."""
    store = current_store()
    node_id = node.id
    if not node_id:
        raise UIError(f"gm.ui.{kind} produced a node with no id")
    handler = open_handler()
    if handler is not None:
        raise UIError(
            f"gm.ui.{kind} cannot be created inside the gm.ui.onclick block for "
            f"{handler!r}: the command behind a control must exist before the reader "
            "touches anything, and a handler's commands only run once they click."
        )
    existing = store.ui_widgets.get(node_id)
    if existing is not None:
        raise UIError(
            f"node {node_id!r} already has a {existing['kind']!r} control; a node "
            f"may carry at most one, because f\"{{{node_id}}}\" looks the control "
            f"up by node id and could not tell two apart. Give the "
            f"{kind!r} its own node."
        )
    if not IDENTIFIER_RE.match(node_id):
        raise UIError(
            f"node id {node_id!r} cannot carry a control: it is written straight "
            "into an HTML attribute and must be a plain identifier"
        )
    store.ui_widgets[node_id] = {"kind": kind, "node": node_id, "options": options}


def _check_label(label: Optional[str], kind: str) -> None:
    if label is not None and not isinstance(label, str):
        raise UIError(f"gm.ui.{kind} label must be a string, got {label!r}")


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


def slider(
    start: float,
    stop: float,
    step: Optional[float] = None,
    value: Optional[float] = None,
    label: Optional[str] = None,
    show_value: bool = True,
) -> "GNode":
    """A slider over [start, stop] driving a new Scalar node.

    `value` is where it starts (default: `start`). `step` snaps it; omit for a
    continuous slide. Returns the Scalar, so it can be used like any other.
    """
    from .functions.implementations.basic_figures import scalar

    start = float(start)
    stop = float(stop)
    if stop <= start:
        raise UIError(f"gm.ui.slider needs stop > start, got start={start}, stop={stop}")
    if step is not None:
        step = float(step)
        if step <= 0:
            raise UIError(f"gm.ui.slider step must be positive, got {step}")
        if step > stop - start:
            raise UIError(
                f"gm.ui.slider step {step} is wider than the range "
                f"{start}..{stop}, so the slider would have one position"
            )
    initial = start if value is None else float(value)
    if not (start <= initial <= stop):
        raise UIError(
            f"gm.ui.slider value {initial} is outside the range {start}..{stop}"
        )
    _check_label(label, "slider")

    node = scalar(initial)
    _register(
        node,
        "slider",
        {
            "initial-value": initial,
            "start": start,
            "stop": stop,
            "step": step,
            "label": label,
            "show-value": show_value,
        },
    )
    return node


def checkbox(value: bool = False, label: Optional[str] = None) -> "GNode":
    """A tick box driving a new Bool node.

    The usual partner for `gm.when`, which shows or hides prose while a Bool
    node is true:

        show = gm.ui.checkbox(False, label="Show the proof")
        with gm.when(show):
            gm.md("Because $ab=ba$, the map commutes.")
    """
    from .functions.implementations.boolean_functions import bool_

    if not isinstance(value, bool):
        raise UIError(f"gm.ui.checkbox value must be True or False, got {value!r}")
    _check_label(label, "checkbox")

    node = bool_(value)
    _register(node, "checkbox", {"initial-value": value, "label": label})
    return node


def number(
    start: Optional[float] = None,
    stop: Optional[float] = None,
    value: Optional[float] = None,
    step: Optional[float] = None,
    label: Optional[str] = None,
) -> "GNode":
    """A typed number box driving a new Scalar node.

    Use this over `slider` when the reader needs an exact figure rather than a
    sweep. `start`/`stop` are optional bounds; omit both for an open field.
    """
    from .functions.implementations.basic_figures import scalar

    start = None if start is None else float(start)
    stop = None if stop is None else float(stop)
    if start is not None and stop is not None and stop <= start:
        raise UIError(f"gm.ui.number needs stop > start, got start={start}, stop={stop}")
    if step is not None:
        step = float(step)
        if step <= 0:
            raise UIError(f"gm.ui.number step must be positive, got {step}")
    initial = float(value) if value is not None else (start if start is not None else 0.0)
    if start is not None and initial < start:
        raise UIError(f"gm.ui.number value {initial} is below start {start}")
    if stop is not None and initial > stop:
        raise UIError(f"gm.ui.number value {initial} is above stop {stop}")
    _check_label(label, "number")

    node = scalar(initial)
    _register(
        node,
        "number",
        {
            "initial-value": initial,
            "start": start,
            "stop": stop,
            "step": step,
            "label": label,
        },
    )
    return node


def _choice_options(options: Sequence, kind: str) -> tuple[list, str]:
    """Validate a choice's options and infer the node type they imply.

    Returns `(choices, mode)` where `mode` is `"text"` for an all-string list
    (the chosen option becomes a Text node's value) or `"scalar"` for an
    all-number list (a Scalar node holding the chosen number). A `bool` is an
    `int` subclass but belongs to `gm.ui.checkbox`, so it is rejected here.
    """
    if not isinstance(options, (list, tuple)) or not options:
        raise UIError(f"gm.ui.{kind} needs a non-empty list of options")

    if all(isinstance(o, str) for o in options):
        choices, mode = list(options), "text"
    elif all(isinstance(o, (int, float)) and not isinstance(o, bool) for o in options):
        choices, mode = [float(o) for o in options], "scalar"
    else:
        raise UIError(
            f"gm.ui.{kind} options must be all strings or all numbers, got "
            f"{list(options)!r}. Strings make a Text node, numbers a Scalar node."
        )

    if len(set(choices)) != len(choices):
        raise UIError(
            f"gm.ui.{kind} options must be distinct — the node holds the chosen "
            "one, so duplicates would be indistinguishable"
        )
    return choices, mode


def _choice(kind: str, options, value, label):
    from .functions.implementations.basic_figures import scalar
    from .functions.implementations.basic_figures import text as _text_node

    choices, mode = _choice_options(options, kind)
    if value is None:
        initial = choices[0]
    else:
        initial = float(value) if mode == "scalar" else value
    if initial not in choices:
        raise UIError(
            f"gm.ui.{kind} value {initial!r} is not one of the options {choices!r}"
        )
    _check_label(label, kind)

    node = scalar(initial) if mode == "scalar" else _text_node(initial)
    _register(
        node,
        kind,
        {"initial-value": initial, "options": choices, "label": label},
    )
    return node


def dropdown(
    options: Sequence[Union[str, float]],
    value: Optional[Union[str, float]] = None,
    label: Optional[str] = None,
) -> "GNode":
    """A drop-down of `options` driving a new node holding the chosen one.

    An all-string list makes a Text node; an all-number list makes a Scalar
    node, so `gm.ui.dropdown([1, 2], 1)` gives a number the canvas can use.
    Compare it with `gm.cond.eq(mode, "sum")` or `gm.cond.eq(n, 1)` to gate
    prose on the choice.
    """
    return _choice("dropdown", options, value, label)


def radio(
    options: Sequence[Union[str, float]],
    value: Optional[Union[str, float]] = None,
    label: Optional[str] = None,
) -> "GNode":
    """Radio buttons over `options`, driving a new node. Same as `dropdown` but
    with every choice visible at once — better for two or three options the
    reader should be able to see without clicking. An all-number list makes a
    Scalar node, an all-string list a Text node."""
    return _choice("radio", options, value, label)


def text(
    value: str = "",
    label: Optional[str] = None,
    placeholder: Optional[str] = None,
) -> "GNode":
    """A free-text box driving a new Text node."""
    from .functions.implementations.basic_figures import text as _text_node

    if not isinstance(value, str):
        raise UIError(f"gm.ui.text value must be a string, got {value!r}")
    if placeholder is not None and not isinstance(placeholder, str):
        raise UIError(f"gm.ui.text placeholder must be a string, got {placeholder!r}")
    _check_label(label, "text")

    node = _text_node(value)
    _register(
        node,
        "text",
        {"initial-value": value, "label": label, "placeholder": placeholder},
    )
    return node
