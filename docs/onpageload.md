# `gm.onpageload` — the scene the article opens with

An article opens on a blank canvas. Every command sits behind a
`{label}(command)` link, so nothing exists until the reader clicks. That is
right for a step-by-step exposition and wrong for two things:

- **a control**, whose backing node has to exist the moment the slider is on
  screen — otherwise the reader drags it and nothing moves;
- **a starting scene**: axes, a figure, a title box the article is meant to
  begin with.

`gm.onpageload` is the block for both.

```python
with gm.onpageload():
    r = gm.ui.slider(1, 5, step=0.5, value=3, label="radius")
    gm.circle(gm.p0, r)

gm.md(f"Drag to resize the circle: {r}")
```

The circle is on the canvas before the reader touches anything, and the slider
works on the first drag.

---

## 1. The body's commands leave the tape

This is `gm.ui.onclick`'s mechanism exactly (read [onclick.md](onclick.md)
first). The block records ordinary pygeomatic, then **moves** the recorded slice
off the tape and keeps the emitted lines. `gm.emit()` for a scene with a block is
byte-identical to the same scene without one, and the fence contributes no spans
for those commands.

They travel in a trailing manifest instead:

```
<!-- onpageload:v1
{"commands":["r = \\scalar 3","circ-0 = \\circle p0 r"]}
-->
```

The nodes stay registered, so python can keep using them — `f"{r}"` still
renders the slider, and `gm.when(show)` still reads a checkbox created here.

## 2. Unlike a handler, the document may build on it

`onclick` forbids the main tape consuming a node only a handler defines: at read
time nothing has clicked yet, so the node does not exist. `onpageload` is the
opposite — its commands have **already run** by the time the reader meets the
first span. So this is fine, and is the usual reason to write the block:

```python
with gm.onpageload():
    r = gm.ui.slider(1, 5, value=3, label="radius")

# an ordinary span, later in the article, reading the slider's node
gm.circle(gm.p0, r)
```

`compile_article` seeds its round-trip gate with the block's lines before
replaying the document's, so references like this pass rather than failing as
unknown ids.

## 3. Three rules

- The block goes inside a ` ```pygeomatic ` fence.
- **At most one per document.** Put everything the page starts with in it.
- **It must be in the very first fence, before any other command is recorded.**

The third is not style. At read time the block runs first, ahead of every
document-order span. If anything had been recorded before it, the compiled
article would replay in an order the author never built. Each rule is an
`ArticleError` with a line number:

| what you wrote | message |
|---|---|
| a command before the block | `must come before any other command` |
| the block in a later fence | `only usable inside the FIRST ```pygeomatic block` |
| a second block | `at most one gm.onpageload() block` |
| an empty body | `recorded no commands` |
| `group()` inside | `opened inside the gm.onpageload block` |
| the block inside a `gm.ui.onclick` handler | `the two run at different times` |

`gm.md()` inside the block **is** allowed: prose is written once when the
article compiles, whenever its commands happen to run.

So is `gm.ui.onclick`, and nesting it here is how you put something clickable on
screen from the start:

```python
with gm.onpageload():
    box = gm.annotate_text_box("what happens here?", 2, 3)
    with gm.ui.onclick(box):
        p = gm.point(2, 3)
```

The handler's commands leave the tape first, so the page-load block captures
what remains around it and each manifest gets its own slice: the box is built at
load, the point waits for the click. The target being created at load is exactly
what the canvas needs in order to make it clickable — and it survives `\clear`,
because the replay rebuilds it and the handler map is document config. (If the
handler takes *every* command, the block itself recorded nothing and raises.)

The reverse does not nest: a handler runs on a click, so a "page load" block
inside one could never mean anything.

Outside article compilation — a bare script, Nova's Python tab — the block
raises rather than recording a manifest nothing would read.

## 4. At read time

The browser runs the manifest's commands once the article's extensions and
macros have registered, before any link, and **again after every `\clear`** —
a `\clear` written as a span, the rebuild on a backward jump, and the "Start
over" button. That makes the load-time scene an invariant, which is what makes
§2 safe: a mid-article `\clear` would otherwise destroy the slider's node and
every command downstream of it would fail.

Reader side: `src/lib/geomatic/ui/pageLoad.ts` (parse),
`src/lib/geomatic/utils/sequentialRunner.ts` (the after-`\clear` replay) and
`src/lib/geomatic/components/InteractiveTextWithComponents.tsx` (the load run)
in the tinyvolt-web repo.
