"""gm.ui.onclick — commands a canvas node runs when the reader clicks it.

    label = gm.annotate_text_box("what happens here?", 2, 3)

    with gm.ui.onclick(label):
        p = gm.point(2, 3)
        far = gm.gt(gm.distance(p, gm.p0), 1)

Clicking that text box on the canvas runs the block's commands, in order.
Opening `onclick` again for the same node replaces the previous body.

Three properties define the shape:

1. **The body's commands are MOVED off the tape, not copied.** A handler is
   the one place where recorded commands must not run in document order — they
   run when, and only when, the reader clicks. So the block captures the tape
   slice it recorded, deletes it, and keeps the emitted lines. `gm.emit()` for
   a scene with handlers is byte-identical to the same scene without them.

2. **The nodes stay registered.** Only the commands leave; `p` and `far` above
   are still in `store.nodes`, so python can keep using them. The pairing this
   exists for is `gm.when`, which records no DSL and reads the node in the
   browser — prose that appears once the reader has clicked:

       with gm.ui.onclick(label):
           far = gm.gt(gm.distance(p, gm.p0), 1)
       with gm.when(far):
           gm.md("The point landed outside the unit circle.")

3. **Handlers travel beside the article, not inside it.** They are recorded on
   a channel separate from the command tape (`Store.click_handlers`, keyed by
   node id) exactly like `gm.tex` bindings, and `compile_article` snapshots
   them into a trailing `<!-- onclick:v1 ... -->` comment. No DSL syntax, no
   registered function, so nothing about the grammar or the registry changes.

The consequence of (1) is the one rule an author has to keep: the MAIN tape may
not consume a node ONLY a handler defines, since at read time nothing has
created it yet. Reassigning a node the main tape already defined is fine, and is
the usual reason to write a handler at all. Nothing here checks this — the
article's round-trip gate replays the compiled DSL with auto-create disabled, so
a genuinely undefined id fails there with a line number.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

from .emit import render_command
from .nodes import GNode
from .store import IDENTIFIER_RE, Store, current_store

# Node types with no canvas presence: a handler on one could never fire, so say
# so at authoring time rather than leaving the author wondering why their click
# does nothing.
_UNCLICKABLE = frozenset({"Scalar", "Bool", "Text", "Complex", "Dummy"})

# The node id of the onclick block currently open, if any. Read by ui._register,
# article.group() and article.md() to reject what cannot work inside a handler.
_open: ContextVar[Optional[str]] = ContextVar("pygeomatic_onclick_open", default=None)


class OnClickError(ValueError):
    """A gm.ui.onclick block could not be recorded."""


def open_handler() -> Optional[str]:
    """The node id of the onclick block currently open, or None."""
    return _open.get()


def _barrier(store: Store) -> None:
    """Stop variadic fusion reaching across the block's edge.

    `Store.fuse_variadic` folds an anonymous just-recorded `\\add`/`\\mul` sitting
    at the end of the tape into the command that consumes it. Across a handler
    boundary that is wrong in both directions: the handler's first `\\add` could
    absorb (and delete) a main-tape command, and an outer `\\add` could absorb a
    command whose only consumer is now inside the handler. Clearing the flag at
    each edge makes both impossible; the cost is one unfused pair of lines.
    """
    if store.commands:
        store.commands[-1].fusable = False


def _validate_target(target) -> str:
    if not isinstance(target, GNode):
        raise OnClickError(
            f"gm.ui.onclick takes a node, got {target!r}. Pass the value a command "
            "returned, e.g. the text box you want the reader to click."
        )
    node_id = target.id
    if not node_id:
        raise OnClickError("gm.ui.onclick target has no id yet, so it cannot be clicked")
    if not IDENTIFIER_RE.match(node_id):
        raise OnClickError(
            f"node id {node_id!r} cannot carry a click handler: it is written straight "
            "into the article's handler manifest and must be a plain identifier"
        )
    if target.type in _UNCLICKABLE:
        raise OnClickError(
            f"a {target.type} node is not drawn on the canvas, so it can never be "
            f"clicked. Attach the handler to something visible (a text box, a shape, "
            f"a point) instead of {node_id!r}."
        )
    return node_id


@contextmanager
def onclick(target: GNode):
    """Record the block's commands as `target`'s click handler.

    The commands leave the tape and run only when the reader clicks the node.
    Opening `onclick` again for the same node replaces the handler.

    Legal inside a `gm.onpageload` block, and the natural way to write "a
    clickable thing is on screen from the start": the handler's commands leave
    the tape first, so the page-load block captures what remains around it. The
    node it targets is created at load, which is exactly when the canvas needs
    it to make the node clickable.
    """
    store = current_store()
    node_id = _validate_target(target)
    already_open = _open.get()
    if already_open is not None:
        raise OnClickError(
            f"gm.ui.onclick({node_id!r}) opened inside the handler for "
            f"{already_open!r}: handlers do not nest, because the inner block's "
            "commands would have to belong to both."
        )

    start = len(store.commands)
    _barrier(store)
    token = _open.set(node_id)
    try:
        yield target
    finally:
        _open.reset(token)

    captured = store.commands[start:]
    if not captured:
        raise OnClickError(
            f"gm.ui.onclick({node_id!r}) recorded no commands, so clicking the node "
            "would do nothing"
        )
    del store.commands[start:]
    _barrier(store)

    store.click_handlers[node_id] = {
        "commands": [render_command(cmd) for cmd in captured]
    }


# ---------------------------------------------------------------------------
# Harvest
# ---------------------------------------------------------------------------


def harvest_click_handlers(store: Optional[Store] = None) -> dict:
    """The session's click handlers, as the `onclick:v1` manifest.

    `{node id: {"commands": [dsl line, ...]}}`, in the order the handlers were
    recorded. Empty when nothing registered one, so an article with no handlers
    is byte-for-byte unchanged.
    """
    store = store or current_store()
    return {
        node_id: dict(handler) for node_id, handler in store.click_handlers.items()
    }
