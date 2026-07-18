"""Mirror of src/lib/geomatic/functions/implementations/special-functions.ts.

All of these are visual/store-level side effects in the engine; here they are
recorded on the tape (so emitted DSL includes them) and otherwise do nothing.
`copy` is the exception: it assigns a new node id to a copy of its input.
"""

from __future__ import annotations

from ...nodes import Dummy, GNode
from ...registry import P, geomatic_fn

CATEGORY = "Special Functions"


@geomatic_fn(
    keyword="clear",
    name="Clear",
    output="Dummy",
    params=[],
    category=CATEGORY,
    imperative=True,
)
def clear():
    return Dummy._new()


@geomatic_fn(
    keyword="highlight",
    name="Highlight",
    output="Dummy",
    params=[P("id", "Any", variadic=True)],
    category=CATEGORY,
    imperative=True,
)
def highlight(ids):
    return Dummy._new()


@geomatic_fn(
    keyword="hide",
    name="Hide",
    output="Dummy",
    params=[P("id", "Any", variadic=True)],
    category=CATEGORY,
    imperative=True,
)
def hide(ids):
    return Dummy._new()


@geomatic_fn(
    keyword="show",
    name="Show",
    output="Dummy",
    params=[P("id", "Any", variadic=True)],
    category=CATEGORY,
    imperative=True,
)
def show(ids):
    return Dummy._new()


@geomatic_fn(
    keyword="copy",
    name="Copy",
    output="Any",
    params=[P("node", "Any")],
    category=CATEGORY,
    imperative=True,
    assigns_output=True,
)
def copy(node):
    if not isinstance(node, GNode):
        raise TypeError("copy: argument must be a node")
    return node.model_copy()


@geomatic_fn(
    keyword="remove",
    name="Remove",
    output="Dummy",
    params=[P("id", "Any", variadic=True)],
    category=CATEGORY,
    imperative=True,
)
def remove(ids):
    return Dummy._new()


@geomatic_fn(
    keyword="help",
    name="Help",
    output="Dummy",
    params=[P("id", "Any")],
    category=CATEGORY,
    imperative=True,
)
def help_(node_id):
    return Dummy._new()


@geomatic_fn(
    keyword="set-stroke",
    name="SetStroke",
    output="Dummy",
    params=[P("node", "Any"), P("stroke", "Text")],
    category=CATEGORY,
    imperative=True,
)
def set_stroke(node, stroke):
    return Dummy._new()


@geomatic_fn(
    keyword="set-fill",
    name="SetFill",
    output="Dummy",
    params=[P("node", "Any"), P("fill", "Text")],
    category=CATEGORY,
    imperative=True,
)
def set_fill(node, fill):
    return Dummy._new()
