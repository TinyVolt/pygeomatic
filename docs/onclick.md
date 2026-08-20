# `gm.ui.onclick` — commands the reader runs by clicking the canvas

Until now a scene only advanced when the reader clicked a `{label}(command)`
link in the prose. `gm.ui.onclick` attaches a block of commands to a node on the
**canvas**, so clicking the node itself runs them.

```python
label = gm.annotate_text_box("where does it land?", 2, 3)

with gm.ui.onclick(label):
    p = gm.point(2, 3)
    far = gm.gt(gm.distance(p, gm.p0), 1)
```

It sits in the `gm.ui` namespace beside the controls, but it is a different
mechanism: a control drives a node's **value**, a handler runs **commands**.

---

## 1. The body's commands leave the tape

Inside the block you write ordinary pygeomatic. The block records it the usual
way, then **moves** the recorded slice off the tape and keeps the emitted lines
as the handler. A handler is the one thing in an article that must *not* run in
document order — it runs when, and only when, the reader clicks.

So the scene above emits exactly what it would with no handler at all:

```
text-0 = \text "where does it land?"
label = \annotate-text-box text-0 2 3
```

and the handler travels separately (§3). `gm.emit()` for a scene with handlers is
byte-identical to the same scene without them.

Opening `onclick` again for the same node **replaces** its handler; the last
block wins. Different nodes keep independent handlers.

## 2. The nodes stay registered

Only the commands leave. `p` and `far` above are still in the store, so python
can keep using them — which is the point, because of `gm.when`:

```python
with gm.ui.onclick(label):
    far = gm.gt(gm.distance(p, gm.p0), 1)

with gm.when(far):
    gm.md("The point landed outside the unit circle.")
```

`gm.when` records no DSL: it writes a condition into the compiled article and the
browser watches the node. So the prose is written at compile time and appears
when the reader's click makes `far` true.

**The one rule this creates:** the *main tape* may not consume a node a handler
defines. At read time the article's commands all run before any click, so the
consumer would find nothing there and the engine would auto-create a
random-valued node in its place — a silently wrong scene rather than an error.
`harvest_click_handlers` refuses:

```python
with gm.ui.onclick(label):
    p = gm.point(1, 1)
gm.circle(p, 2)        # OnClickError: `p` is defined inside a handler
```

Move the definition out of the handler, or move the consumer into it. (Inside an
article the round-trip gate usually reaches the same problem first, reporting it
as an unknown node id.)

## 3. Handlers travel beside the article

Handlers are recorded on a channel separate from the command tape
(`Store.click_handlers`, keyed by node id), exactly like `gm.tex` bindings, and
`compile_article` snapshots them into a trailing HTML comment after the
`texatlas:v1` one:

```
<!-- onclick:v1
{"label":{"commands":["p-0 = \\point 2 3","num-0 = \\distance p-0 p0","far = \\gt num-0 1"]}}
-->
```

The reader (`src/lib/geomatic/ui/clickHandlers.ts` in the web repo) strips both
trailing manifests, loads this one into the store, and the canvas makes every
node with a handler clickable. There is **no DSL syntax and no registered
function** behind any of this, so the grammar, the registry and the TS/Python
parity test are all untouched.

`harvest_click_handlers(store)` returns the same dict for any other consumer;
articles with no handlers are byte-for-byte unchanged.

## 4. What is rejected, and why

| | |
| --- | --- |
| an empty block | clicking would do nothing |
| nesting two blocks | the inner commands would have to belong to both |
| a `Scalar`/`Bool`/`Text`/`Complex`/`Dummy` target | not drawn on the canvas, so it can never be clicked |
| a target with no id, or a non-node | there is nothing to key the handler by |
| `gm.ui.slider(...)` (any control) inside a block | the command behind a control must exist before the reader touches anything |
| `group(...)` inside a block | a group is a run of commands prose reveals; a handler's commands leave the tape |
| `gm.md(...)` inside a block | prose is written once, at compile time; gate it with `gm.when` instead |

All of them raise at compile time (`OnClickError`, or `UIError`/`ArticleError`
where the call belongs to that namespace).

## 5. Two things it does not do

- **Handler bodies are not covered by the article round-trip gate.** They are
  deliberately outside document order, so the gate cannot replay them. A handler
  that references a node defined *later* in the article will fail if the reader
  clicks before reaching that point — pygeomatic cannot detect this.
- **Handlers do not travel with bare emitted DSL.** They live in the article
  manifest, so `build_to_dsl.py` output and a command list pasted into the
  editor carry the scene but not its handlers.
