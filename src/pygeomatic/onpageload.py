"""gm.onpageload — commands that run before the reader clicks anything.

    with gm.onpageload():
        r = gm.ui.slider(1, 5, step=0.5, value=3, label="radius")
        gm.circle(gm.p0, r)

An article otherwise opens on a blank canvas: every command sits behind a
CommandLink and nothing exists until the reader clicks. That is right for a
step-by-step exposition and wrong for two things — a control, whose backing node
must exist the moment the slider is on screen, and a starting scene the article
is meant to open with. This block is both.

It is `gm.ui.onclick`'s shape (read onclick.py first): the body's commands are
MOVED off the tape and snapshotted into a trailing `<!-- onpageload:v1 ... -->`
manifest, so `gm.emit()` for a scene with a block is byte-identical to the same
scene without one. Two things differ, both consequences of WHEN it runs:

1. **One block per article, not one per node.** The manifest payload is a bare
   `{"commands": [...]}`.

2. **The main tape MAY consume what the block defines.** That is the point:
   `gm.circle(gm.p0, r)` on a slider node. `onclick` forbids it, because at read
   time nothing has run the handler yet; here the block has already run before
   the first span. `compile_article` therefore pre-seeds its round-trip gate
   with these lines instead of rejecting them.

The three author rules — inside a fence, at most one, in the very first fence
before any other command — exist to keep recording order equal to read-time
order. At read time these commands run first, ahead of every document-order
span; if anything had been recorded before the block, the compiled article would
replay in an order the author never built.

`gm.ui.onclick` nests INSIDE this block, and is the way to put something
clickable on screen from the start:

    with gm.onpageload():
        box = gm.annotate_text_box("what happens here?", 2, 3)
        with gm.ui.onclick(box):
            p = gm.point(2, 3)

The handler's commands leave the tape first, so this block captures what remains
around it, and the two manifests each get their own slice. The reverse does not
nest: a handler runs on a click, so a "page load" block inside one could never
mean anything.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

from .emit import render_command
from .onclick import _barrier, open_handler
from .store import Store, current_store

# True only while the article's FIRST ```pygeomatic fence is executing; set by
# article._execute. The default is False so a block outside article compilation
# (a bare script, Nova's Python tab) reports the rule rather than silently
# recording a manifest nothing will ever read.
_allowed: ContextVar[bool] = ContextVar("pygeomatic_onpageload_allowed", default=False)

# True while a block is open. Read by onclick to reject nesting in either
# direction, and by this module to reject nesting in itself.
_open: ContextVar[bool] = ContextVar("pygeomatic_onpageload_open", default=False)


class PageLoadError(ValueError):
    """A gm.onpageload block could not be recorded."""


def open_page_load() -> bool:
    """True while a gm.onpageload block is open."""
    return _open.get()


@contextmanager
def onpageload():
    """Record the block's commands to run when the article loads.

    The commands leave the tape and run once the page has loaded, before any
    CommandLink — and again after any `\\clear`, so the load-time scene is what
    "Start over" returns the reader to.
    """
    if not _allowed.get():
        raise PageLoadError(
            "gm.onpageload() is only usable inside the FIRST ```pygeomatic block "
            "of an article: its commands run before every link in the document, "
            "so nothing may be recorded ahead of them."
        )
    if _open.get():
        raise PageLoadError("gm.onpageload() blocks do not nest")
    handler = open_handler()
    if handler is not None:
        raise PageLoadError(
            f"gm.onpageload() opened inside the gm.ui.onclick block for {handler!r}: "
            "the two run at different times, so the inner block's commands would "
            "have to belong to both."
        )
    store = current_store()
    if store.page_load is not None:
        raise PageLoadError(
            "an article may contain at most one gm.onpageload() block; put "
            "everything the page starts with in the first one"
        )
    if store.commands:
        raise PageLoadError(
            f"gm.onpageload() must come before any other command, but "
            f"{len(store.commands)} have already been recorded. Move the block to "
            "the top of the first ```pygeomatic fence."
        )

    start = len(store.commands)
    _barrier(store)
    token = _open.set(True)
    try:
        yield
    finally:
        _open.reset(token)

    captured = store.commands[start:]
    if not captured:
        raise PageLoadError(
            "gm.onpageload() recorded no commands, so the page would load exactly "
            "as it does without the block"
        )
    del store.commands[start:]
    _barrier(store)

    store.page_load = [render_command(cmd) for cmd in captured]


# ---------------------------------------------------------------------------
# Harvest
# ---------------------------------------------------------------------------


def harvest_page_load(store: Optional[Store] = None) -> dict:
    """The session's page-load commands, as the `onpageload:v1` manifest.

    `{"commands": [dsl line, ...]}`, empty when the article has no block — so an
    article without one is byte-for-byte unchanged.
    """
    store = store or current_store()
    if not store.page_load:
        return {}
    return {"commands": list(store.page_load)}
