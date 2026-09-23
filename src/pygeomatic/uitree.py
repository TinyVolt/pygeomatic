"""gm.ui element trees — the machinery behind `with gm.ui.col():`.

A single control rides on its own element: `gm.ui.slider(...)` returns a node,
`f"{r}"` turns it into a `<span class="nova-ui" data-…>` right where the
f-string put it. That works because a control fits on one line, which markdown
requires.

A whole panel does not. So a tree goes the way gm.tex bindings and onclick
handlers already go: a short placeholder in the prose,

    <div class="nova-ui-tree" data-tree="t0"></div>

and the tree itself in a trailing `<!-- ui:v1 … -->` comment. The compiled
markdown stays readable, which matters because these files are read on GitHub.

WHAT LIVES HERE vs IN ui.py
    Here: the open-container stack, schema validation, tree emission, harvest.
    There: every `gm.ui.*` an author calls.

That split is deliberate. Name inference (`inference.py`) only hops frames whose
module is `pygeomatic.ui`, so a constructor that records a NODE has to live in
ui.py or `r = gm.ui.slider(...)` silently loses its name. The constructors here
would be safe (a container records no node), but keeping every author-facing
call in one module means nobody has to remember which kind they are writing.

THE SCHEMA
`ui_schema.json` is generated into this package by the web repo's
`npm run gen:ui-schema`, from a hand-written source that also generates the
browser's parser table. Validating against it here is what makes a mistyped
attribute a compile-time error with a line number, instead of an element that
silently renders without that setting — which is the failure mode this whole
mechanism exists to remove, and the one that matters most once a model is
writing the python.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from importlib.resources import files
from typing import Optional

from .store import IDENTIFIER_RE, Store, current_store


class UITreeError(ValueError):
    """A gm.ui element tree could not be built."""


# `${r}` inside a label is a live value, the same readout `f"{r}"` produces in
# prose.
_INTERPOLATION = re.compile(r"\$\{([a-zA-Z][a-zA-Z0-9-]*)\}")


# The stack of open containers. Each entry is the element dict being filled;
# children are appended to the last one. Empty (or None) means no tree is open,
# so a control registers as an inline span exactly as it always did.
_stack: ContextVar[Optional[list[dict]]] = ContextVar(
    "pygeomatic_uitree_stack", default=None
)


def _schema() -> dict:
    """The element vocabulary, loaded once from the generated JSON."""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        text = (files("pygeomatic") / "ui_schema.json").read_text(encoding="utf-8")
        _SCHEMA_CACHE = json.loads(text)
    return _SCHEMA_CACHE


_SCHEMA_CACHE: Optional[dict] = None


def _real(mapping: dict) -> dict:
    """Drop the `_comment` keys the schema carries for its human readers."""
    return {k: v for k, v in mapping.items() if not k.startswith("_")}


def open_container() -> Optional[dict]:
    """The innermost open container element, or None when no tree is open."""
    stack = _stack.get()
    return stack[-1] if stack else None


def in_tree() -> bool:
    """Whether a `gm.ui` container is currently open."""
    return bool(_stack.get())


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

MAX_SPACE_STEP = 9


def _check_size(where: str, name: str, value):
    """A `size`: a spacing step, `"fill"`, or `<number><allowed unit>`.

    Free-form CSS is refused on purpose. Allowing it would reopen both the
    theming and the injection surface that a closed vocabulary closes, and would
    make every generated article look different.
    """
    units = _schema()["sizeUnits"]
    if isinstance(value, bool):
        raise UITreeError(f"{where}.{name} must be a length, got {value!r}")
    if isinstance(value, int):
        if not 0 <= value <= MAX_SPACE_STEP:
            raise UITreeError(
                f"{where}.{name} as a number must be a spacing step "
                f"between 0 and {MAX_SPACE_STEP}, got {value}"
            )
        return value
    if not isinstance(value, str):
        raise UITreeError(
            f"{where}.{name} must be a number, \"fill\", or a length like \"12ch\""
        )
    if value == "fill":
        return value
    for unit in units:
        if value.endswith(unit):
            head = value[: -len(unit)]
            try:
                float(head)
            except ValueError:
                break
            return value
    raise UITreeError(
        f"{where}.{name} must use one of {', '.join(units)} — got {value!r}"
    )


def _check_font_size(where: str, name: str, value):
    """A `fontsize`: a positive length in one of the font units.

    A spacing step is not one of them — the spacing scale measures gaps, and a
    number here would silently mean something it does not mean.
    """
    units = _schema()["fontUnits"]
    if not isinstance(value, str):
        raise UITreeError(
            f'{where}.{name} must be a length like "0.9rem" or "14px", got {value!r}'
        )
    for unit in units:
        if value.endswith(unit):
            head = value[: -len(unit)]
            try:
                size = float(head)
            except ValueError:
                break
            if size <= 0:
                raise UITreeError(f"{where}.{name} must be positive, got {value!r}")
            return value
    raise UITreeError(
        f"{where}.{name} must use one of {', '.join(units)} — got {value!r}"
    )


def _check_attr(where: str, name: str, spec: dict, value):
    kind = spec["type"]

    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise UITreeError(f"{where}.{name} must be a number, got {value!r}")
        return float(value) if isinstance(value, float) else value

    if kind == "space":
        if isinstance(value, bool) or not isinstance(value, int):
            raise UITreeError(
                f"{where}.{name} must be a whole number of spacing steps, got {value!r}"
            )
        if not 0 <= value <= MAX_SPACE_STEP:
            raise UITreeError(
                f"{where}.{name} must be between 0 and {MAX_SPACE_STEP}, got {value}"
            )
        return value

    if kind == "size":
        return _check_size(where, name, value)

    if kind == "fontsize":
        return _check_font_size(where, name, value)

    if kind == "string":
        if not isinstance(value, str):
            raise UITreeError(f"{where}.{name} must be a string, got {value!r}")
        return value

    if kind == "identifier":
        if not isinstance(value, str) or not IDENTIFIER_RE.match(value):
            raise UITreeError(
                f"{where}.{name} must be an identifier (a letter, then letters, "
                f"digits or dashes), got {value!r}"
            )
        return value

    if kind == "bool":
        if not isinstance(value, bool):
            raise UITreeError(f"{where}.{name} must be True or False, got {value!r}")
        return value

    if kind == "enum":
        if value not in spec["values"]:
            raise UITreeError(
                f"{where}.{name} must be one of {', '.join(spec['values'])}, "
                f"got {value!r}"
            )
        return value

    if kind == "options":
        if not isinstance(value, (list, tuple)) or not value:
            raise UITreeError(f"{where}.{name} must be a non-empty list")
        return list(value)

    if kind == "cond":
        if not isinstance(value, dict):
            raise UITreeError(f"{where}.{name} must be a condition")
        return value

    return value  # "any"


def build_element(tag: str, attrs: dict, sizing: dict) -> dict:
    """Validate one element's attributes and return it, ready for the manifest.

    `attrs` uses the schema's names (camelCase, matching the browser); `sizing`
    holds the layout attributes every tag accepts. `None` values are dropped so
    an omitted keyword is indistinguishable from one never written.
    """
    schema = _schema()
    tags = _real(schema["tags"])
    if tag not in tags:
        raise UITreeError(f"{tag!r} is not a gm.ui element")
    spec = tags[tag]
    allowed = _real(spec["attrs"])

    element: dict = {"tag": tag}

    for name, value in sizing.items():
        if value is None:
            continue
        shared = _real(schema["sizing"])
        if name not in shared:
            raise UITreeError(f"{tag}.{name} is not a layout attribute")
        element[name] = _check_attr(tag, name, shared[name], value)

    for name, attr_spec in allowed.items():
        if name in attrs and attrs[name] is not None:
            element[name] = _check_attr(tag, name, attr_spec, attrs[name])
        elif attr_spec.get("required"):
            raise UITreeError(f"gm.ui.{tag} needs {name}")

    unknown = sorted(
        name for name, value in attrs.items() if value is not None and name not in allowed
    )
    if unknown:
        raise UITreeError(
            f"gm.ui.{tag} has no attribute{'s' if len(unknown) > 1 else ''}: "
            f"{', '.join(unknown)}"
        )
    return element


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def add_element(element: dict) -> None:
    """Attach a finished element to the open container.

    Raises if none is open: every element except a container root needs a
    parent, and a control outside a tree takes the inline path instead.
    """
    parent = open_container()
    if parent is None:
        raise UITreeError(
            f"gm.ui.{element['tag']} needs an open container — put it inside a "
            "`with gm.ui.col():` or `with gm.ui.row():` block"
        )
    parent.setdefault("children", []).append(element)


@contextmanager
def container(tag: str, attrs: dict, sizing: dict):
    """Open a container element; on exit attach it, or emit it as a tree.

    Only the OUTERMOST container emits: it registers the finished tree and
    writes one placeholder line into the article. Nested containers just attach
    to their parent, so `rec.md` receives exactly one line per tree and never
    needs the swap-and-restore dance `gm.when` does for prose.
    """
    element = build_element(tag, attrs, sizing)
    element["children"] = []

    stack = _stack.get()
    outermost = not stack
    if outermost:
        stack = []
        token = _stack.set(stack)
    else:
        token = None
    stack.append(element)
    try:
        yield element
    finally:
        stack.pop()
        if token is not None:
            _stack.reset(token)

    if not element["children"]:
        raise UITreeError(f"gm.ui.{tag} block is empty, so it would render nothing")

    if outermost:
        _emit(element)
    else:
        add_element(element)


def _emit(root: dict) -> None:
    """Register a finished tree and write its placeholder into the article."""
    from .article import md_raw

    store = current_store()
    tree_id = f"t{len(store.ui_trees)}"
    store.ui_trees[tree_id] = root
    md_raw(f'<div class="nova-ui-tree" data-tree="{tree_id}"></div>')


# ---------------------------------------------------------------------------
# Harvest
# ---------------------------------------------------------------------------


def harvest_ui_trees(store: Optional[Store] = None) -> dict:
    """The session's element trees, as the `ui:v1` manifest.

    `{tree id: root element}`, in the order they were built. Empty when the
    article has none, so an article without a tree is byte-for-byte unchanged.
    """
    store = store or current_store()
    return {tree_id: root for tree_id, root in store.ui_trees.items()}


def node_refs(element: dict, into: set) -> set:
    """Every store node id a tree reads, so the compiler can check they exist.

    A tree's commands are the article's own; only the references are new. A
    reference to a node the article never defines would fail silently at read
    time — the control would render with nothing behind it — so it is caught at
    compile time instead.
    """
    if "node" in element:
        into.add(element["node"])
    cond = element.get("cond")
    if isinstance(cond, dict):
        _cond_refs(cond, into)
    for name in ("text",):
        value = element.get(name)
        if isinstance(value, str):
            for ref in _INTERPOLATION.findall(value):
                into.add(ref)
    for child in element.get("children", ()):
        node_refs(child, into)
    return into


def _cond_refs(payload: dict, into: set) -> None:
    from .cond import node_refs as cond_node_refs

    cond_node_refs(payload, into)
