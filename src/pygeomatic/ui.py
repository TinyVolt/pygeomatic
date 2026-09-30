"""gm.ui — reader-facing controls (slider, checkbox, ...) embedded in prose.

    r = gm.ui.slider(1, 5, step=0.5, value=3, label="radius")
    gm.md(f"Drag to resize the circle: {r}")
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from html import escape
from typing import Optional, Sequence, Union

from .nodes import Array, Bool, GNode, Scalar, Text
from .onclick import OnClickError, capture_commands, onclick, open_handler  # noqa: F401
from .store import IDENTIFIER_RE, current_store
from .uitree import (  # noqa: F401 — UITreeError is part of the gm.ui surface
    UITreeError,
    add_element,
    build_element,
    container,
    in_tree,
)


class UIError(ValueError):
    """A gm.ui control could not be created."""


_FIRST_OPTION = object()


# Types that interpolate as their value in article strings; others print their id.
READOUT_TYPES = frozenset({"Scalar", "Text", "Bool"})

# `.Nf`, `.N%`, `d`. Keep in sync with the browser's formatValue (format.ts).
FMT_RE = re.compile(r"\.\d+[f%]\Z|d\Z")


def _attr(name: str, value) -> str:
    """`data-<name>='<json>'`, escaped so the HTML sanitiser, markdown and the
    article compiler's `$...$` scan all leave it intact."""
    encoded = json.dumps(value, separators=(",", ":"))
    encoded = encoded.replace(">", "\\u003e").replace("<", "\\u003c")
    encoded = escape(encoded)
    encoded = encoded.replace("\\", "&#92;").replace("$", "&#36;")
    return f"data-{name}='{encoded}'"


def render_widget_html(spec: dict) -> str:
    """The control's HTML on one line (multi-line HTML in indented markdown
    renders as a code block). `kind` and `node` are plain; the rest are JSON."""
    options = spec.get("options", {})
    attrs = " ".join(
        _attr(name, value)
        for name, value in options.items()
        if value is not None or name == "initial-value"
    )
    return (
        f'<span class="nova-ui" data-kind="{spec["kind"]}" '
        f'data-node="{spec["node"]}"'
        f'{" " + attrs if attrs else ""}></span>'
    )


def _camel(name: str) -> str:
    """`initial-value` → `initialValue`."""
    head, *rest = name.split("-")
    return head + "".join(part.capitalize() for part in rest)


def _sizing(width, height, grow, pad, font_size=None, align_self=None) -> dict:
    """The layout attributes every element accepts, in the schema's spelling."""
    return {
        "width": width,
        "height": height,
        "grow": grow,
        "pad": pad,
        "fontSize": font_size,
        "alignSelf": align_self,
    }


def _register(node: GNode, kind: str, options: dict, sizing: Optional[dict] = None) -> None:
    """Add the control to the open tree, or record it as an inline widget."""
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
    if not IDENTIFIER_RE.match(node_id):
        raise UIError(
            f"node id {node_id!r} cannot carry a control: it is written straight "
            "into an HTML attribute and must be a plain identifier"
        )

    if in_tree():
        attrs = {_camel(name): value for name, value in options.items()}
        attrs["node"] = node_id
        add_element(build_element(kind, attrs, sizing or {}))
        return

    if sizing and any(value is not None for value in sizing.values()):
        raise UIError(
            f"gm.ui.{kind} was given layout (width/height/grow/pad/font_size/"
            f"align_self) but is not "
            "inside a `with gm.ui.col():` block. An inline control sits in a "
            "sentence and takes its size from the text around it."
        )

    existing = store.ui_widgets.get(node_id)
    if existing is not None:
        raise UIError(
            f"node {node_id!r} already has a {existing['kind']!r} control; a node "
            f"may carry at most one, because f\"{{{node_id}}}\" looks the control "
            f"up by node id and could not tell two apart. Give the "
            f"{kind!r} its own node."
        )
    store.ui_widgets[node_id] = {"kind": kind, "node": node_id, "options": options}


def _plain(
    value, kind: str, param: str, want: tuple[type[Union[Scalar, Text, Bool]], ...]
):
    """A `want`-typed node becomes its python value; a plain value passes through."""
    if not isinstance(value, GNode):
        return value
    if not isinstance(value, want):
        names = " or ".join(t.type for t in want)
        raise UIError(
            f"gm.ui.{kind} {param} takes a {names} node, got a {value.type} node"
        )
    if value.numeric is None:
        raise UIError(
            f"gm.ui.{kind} {param}: {value.type} node {value.id!r} has no value"
        )
    return value.numeric


def _check_label(label: Optional[str], kind: str) -> None:
    if label is not None and not isinstance(label, str):
        raise UIError(f"gm.ui.{kind} label must be a string, got {label!r}")


def slider(
    start: Union[float, Scalar],
    stop: Union[float, Scalar],
    step: Optional[Union[float, Scalar]] = None,
    value: Optional[Union[float, Scalar]] = None,
    label: Optional[str] = None,
    show_value: bool = True,
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
) -> "GNode":
    """A slider over [start, stop] driving a new Scalar node."""
    from .functions.implementations.basic_figures import scalar

    start = float(_plain(start, "slider", "start", (Scalar,)))
    stop = float(_plain(stop, "slider", "stop", (Scalar,)))
    step = _plain(step, "slider", "step", (Scalar,))
    value = _plain(value, "slider", "value", (Scalar,))
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
        _sizing(width, height, grow, pad, font_size, align_self),
    )
    return node


def checkbox(
    value: Union[bool, Bool] = False,
    label: Optional[str] = None,
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
) -> "GNode":
    """A tick box driving a new Bool node."""
    from .functions.implementations.boolean_functions import bool_

    value = _plain(value, "checkbox", "value", (Bool,))
    if not isinstance(value, bool):
        raise UIError(f"gm.ui.checkbox value must be True or False, got {value!r}")
    _check_label(label, "checkbox")

    node = bool_(value)
    _register(
        node,
        "checkbox",
        {"initial-value": value, "label": label},
        _sizing(width, height, grow, pad, font_size, align_self),
    )
    return node


def number(
    start: Optional[Union[float, Scalar]] = None,
    stop: Optional[Union[float, Scalar]] = None,
    value: Optional[Union[float, Scalar]] = None,
    step: Optional[Union[float, Scalar]] = None,
    label: Optional[str] = None,
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
) -> "GNode":
    """A number box driving a new Scalar node. `start`/`stop` are optional bounds."""
    from .functions.implementations.basic_figures import scalar

    start = _plain(start, "number", "start", (Scalar,))
    stop = _plain(stop, "number", "stop", (Scalar,))
    step = _plain(step, "number", "step", (Scalar,))
    value = _plain(value, "number", "value", (Scalar,))
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
        _sizing(width, height, grow, pad, font_size, align_self),
    )
    return node


def _choice_options(options, kind: str) -> tuple[list, str, object]:
    """Validate options; return `(choices, mode, attr)`, mode "text" or "scalar"."""
    if isinstance(options, Array):
        if not options.id or not IDENTIFIER_RE.match(options.id):
            raise UIError(f"gm.ui.{kind} options array needs a plain identifier id, got {options.id!r}")
        mode = {"Text": "text", "Scalar": "scalar"}.get(options._element_type)
        if mode is None:
            raise UIError(f"gm.ui.{kind} options array must hold Text or Scalar nodes")
        values = [e.numeric for e in options._elements]
        if any(v is None for v in values):
            values = []
        choices = [float(v) for v in values] if mode == "scalar" else list(values)
        return choices, mode, {"node": options.id}

    if not isinstance(options, (list, tuple)) or not options:
        raise UIError(f"gm.ui.{kind} needs a non-empty list of options")
    options = [_plain(o, kind, "options", (Scalar, Text)) for o in options]

    if all(isinstance(o, str) for o in options):
        choices, mode = list(options), "text"
    elif all(isinstance(o, (int, float)) and not isinstance(o, bool) for o in options):
        choices, mode = [float(o) for o in options], "scalar"
    else:
        raise UIError(
            f"gm.ui.{kind} options must be all strings or all numbers, got "
            f"{list(options)!r}. Strings make a Text node, numbers a Scalar node."
        )

    return choices, mode, choices


def _check_display(display, options, kind: str):
    if display is None:
        return None
    count = len(options._elements) if isinstance(options, Array) else len(options)
    if isinstance(display, Array):
        if not display.id or not IDENTIFIER_RE.match(display.id):
            raise UIError(f"gm.ui.{kind} display array needs a plain identifier id, got {display.id!r}")
        if display._element_type != "Text":
            raise UIError(f"gm.ui.{kind} display array must hold Text nodes")
        entries, attr = len(display._elements), {"node": display.id}
    elif isinstance(display, (list, tuple)) and all(isinstance(d, str) for d in display):
        entries, attr = len(display), list(display)
    else:
        raise UIError(
            f"gm.ui.{kind} display must be a list of strings or an array of Text, got {display!r}"
        )
    if entries != count:
        raise UIError(
            f"gm.ui.{kind} display has {entries} entries but there are "
            f"{count} options; they must be the same length"
        )
    return attr


def _choice(kind: str, options, value, label, display=None, sizing=None):
    from .functions.implementations.basic_figures import scalar
    from .functions.implementations.basic_figures import text as _text_node

    choices, mode, attr = _choice_options(options, kind)
    display = _check_display(display, options, kind)
    if display is None and len(set(choices)) != len(choices):
        raise UIError(
            f"gm.ui.{kind} options must be distinct — the node holds the chosen "
            "one, so duplicates would be indistinguishable. Pass `display` to "
            "show distinct labels for repeated values."
        )
    if display is not None and len(set(display)) != len(display):
        raise UIError(f"gm.ui.{kind} display labels must be distinct")
    if value is _FIRST_OPTION:
        if not choices:
            raise UIError(f"gm.ui.{kind} options array has no known value; pass value= explicitly")
        initial = choices[0]
    elif value is None:
        initial = None
    else:
        value = _plain(value, kind, "value", (Scalar, Text))
        initial = float(value) if mode == "scalar" else value
    unselected = initial is None or (kind == "radio" and mode == "text" and initial == "")
    if choices and initial not in choices and not unselected:
        raise UIError(
            f"gm.ui.{kind} value {initial!r} is not one of the options {choices!r}"
        )
    _check_label(label, kind)

    if mode == "scalar":
        node = scalar(current_store().nodes["NaN"] if initial is None else initial)
    else:
        initial = "" if initial is None else initial
        node = _text_node(initial)
    _register(
        node,
        kind,
        {"initial-value": initial, "options": attr, "label": label, "display": display},
        sizing,
    )
    return node


def dropdown(
    options: Union[Sequence[Union[str, float, Scalar, Text]], Array],
    value: Optional[Union[str, float, Scalar, Text]] = _FIRST_OPTION,
    label: Optional[str] = None,
    display: Optional[Union[Sequence[str], Array]] = None,
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
) -> "GNode":
    """A drop-down driving a new node: Text for string options, Scalar for numbers.
    `display` is the text shown for each option; the node still holds the option.
    Leaving out `value` selects the first option. `value=None` starts with nothing
    selected: the node holds "" for string options, NaN for numbers."""
    return _choice("dropdown", options, value, label, display, _sizing(width, height, grow, pad, font_size, align_self))


def radio(
    options: Union[Sequence[Union[str, float, Scalar, Text]], Array],
    value: Optional[Union[str, float, Scalar, Text]] = _FIRST_OPTION,
    label: Optional[str] = None,
    display: Optional[Union[Sequence[str], Array]] = None,
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
) -> "GNode":
    """Radio buttons, otherwise like `dropdown`. `value=None` starts with nothing
    selected; with string options, so does `value=""`."""
    return _choice("radio", options, value, label, display, _sizing(width, height, grow, pad, font_size, align_self))


def text(
    value: Union[str, Text] = "",
    label: Optional[str] = None,
    placeholder: Optional[str] = None,
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
) -> "GNode":
    """A free-text box driving a new Text node."""
    from .functions.implementations.basic_figures import text as _text_node

    value = _plain(value, "text", "value", (Text,))
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
        _sizing(width, height, grow, pad, font_size, align_self),
    )
    return node


def col(
    gap: int = 0,
    align: str = "stretch",
    justify: str = "start",
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
):
    """Stack the block's elements vertically. `gap`/`pad` are spacing-scale steps, not pixels."""
    return container(
        "col",
        {"gap": gap, "align": align, "justify": justify},
        _sizing(width, height, grow, pad, font_size, align_self),
    )


def row(
    gap: int = 0,
    align: str = "center",
    justify: str = "start",
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
):
    """Stack the block's elements horizontally, wrapping when out of width."""
    return container(
        "row",
        {"gap": gap, "align": align, "justify": justify},
        _sizing(width, height, grow, pad, font_size, align_self),
    )


def box(
    border: bool = False,
    background: bool = False,
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
):
    """A padded container, optionally with a border and a surface behind it."""
    return container(
        "box",
        {"border": border, "background": background},
        _sizing(width, height, grow, pad, font_size, align_self),
    )


def label(
    text: str,
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
) -> None:
    """Plain text (not markdown) inside a tree. `${node}` interpolates a live value."""
    add_element(
        build_element(
            "label",
            {"text": text},
            _sizing(width, height, grow, pad, font_size, align_self),
        )
    )


def math(
    latex: str,
    id: Optional[str] = None,
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
) -> None:
    """A KaTeX formula inside a tree. `id` makes it addressable from `gm.tex(id)`."""
    add_element(
        build_element(
            "math",
            {"latex": latex, "id": id},
            _sizing(width, height, grow, pad, font_size, align_self),
        )
    )


def button(
    label: str,
    *,
    width=None,
    height=None,
    grow=None,
    pad=None,
    font_size=None,
    align_self=None,
):
    """Run the block's commands when the reader presses this button."""
    if not in_tree():
        raise UITreeError(
            "gm.ui.button needs an open container — put it inside a "
            "`with gm.ui.col():` or `with gm.ui.row():` block"
        )
    store = current_store()
    # Skip ids taken by gm.ui.onclick handlers on nodes named `btn-N`.
    index = len(store.click_handlers)
    while f"btn-{index}" in store.click_handlers:
        index += 1
    action = f"btn-{index}"
    element = build_element(
        "button", {"label": label, "action": action}, _sizing(width, height, grow, pad, font_size, align_self)
    )

    @contextmanager
    def _run():
        with capture_commands(store, f"gm.ui.button({label!r})") as commands:
            yield
        store.click_handlers[action] = {"commands": commands}
        add_element(element)

    return _run()
