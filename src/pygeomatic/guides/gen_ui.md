# gm.ui element tree examples

Laying gm.ui controls out in containers to form an element tree: five worked examples, and the rule that a control renders only inside the container it is created in.


### Something to be aware of
**A control only appears where you put it.** Create it inside a container and it
becomes an element of that tree. Create it outside one and it takes the old
inline path, which means it shows up only where an f-string puts it:

```python
# WRONG — k is created outside the container, so nothing renders it.
# The node exists, ${chosen} updates, but there is no box to type in.
k = gm.ui.number(0, 3, value=0)
with gm.ui.col():
    gm.ui.label("value ${chosen}")

# RIGHT
with gm.ui.col():
    k = gm.ui.number(0, 3, value=0)
    gm.ui.label("value ${chosen}")
```

Nothing errors either way — an inline control with no `gm.md(f"{k}")` has always
rendered nothing, and that is unchanged. 

| # | exercises | look for |
|---|---|---|
| 1 | `col`, `label`, `slider`, `${node}` | the sentence updates as you drag |
| 2 | `box`, `row`, `button`, `when` | pressing a button repeatedly works |
| 3 | the three repetition patterns | rows appear and vanish |
| 4 | all six controls, both `when` forms | `radio` gives a number, `dropdown` text |
| 5 | `math`, a bound formula, canvas `onclick` + buttons | all four manifests at once |

---

## 1. The basic panel

One container, one control, one live value. 

````markdown
# A circle you can resize

```pygeomatic
with gm.onpageload():
    with gm.ui.col(gap=2, pad=2):
        gm.ui.label("Radius", width="12ch")
        r = gm.ui.slider(1, 5, step=0.5, value=3, grow=1)
        gm.ui.label("the circle is ${r} units across the middle")

    gm.circle(gm.p0, r)
```

Drag the slider. The circle follows, and so does the sentence above it.
````

---

## 2. Buttons and reactive text

A button runs its commands every time it is pressed. A command link in the prose
runs once, in reading order.

````markdown
# Buttons and text that reacts

```pygeomatic
with gm.onpageload():
    n = gm.scalar(3, out="n")
    poly = gm.regular_polygon(gm.p0, gm.scalar(2), n, gm.scalar(0))

    with gm.ui.box(border=True, background=True, pad=3):
        gm.ui.label("Sides: ${n}")

        with gm.ui.row(gap=2):
            with gm.ui.button("triangle"):
                n = gm.scalar(3, out="n")
            with gm.ui.button("square"):
                n = gm.scalar(4, out="n")
            with gm.ui.button("hexagon"):
                n = gm.scalar(6, out="n")

        with when(gm.cond.ge(n, 6)):
            gm.ui.label("At six sides it is already starting to look round.")
```

Press a button as often as you like. A link in the prose runs once, in reading
order; a button runs whenever it is pressed.
````

---

## 3. Making several of something

There is no repeat element. These are the three patterns that replace it.

````markdown
# Making several of something

```pygeomatic
with gm.onpageload():
    xs = gm.array(gm.scalar(10), gm.scalar(20), gm.scalar(30), gm.scalar(40))

    with gm.ui.col(gap=3, pad=2):
        with gm.ui.box(border=True, pad=2):
            gm.ui.label("Pick one: the value below is xs[k]")
            with gm.ui.row(gap=2):
                k = gm.ui.number(0, 3, value=0, step=1, label="k", width="16ch")
                chosen = xs[k]
                gm.ui.label("value ${chosen}", grow=1)

        with gm.ui.box(border=True, pad=2):
            gm.ui.label("Show a few: every row is written out, spare ones are hidden")
            shown = gm.ui.number(1, 4, value=2, step=1, label="rows shown")
            for i in range(4):
                with when(gm.cond.lt(i, shown)):
                    gm.ui.label(f"row {i} holds ${{{xs[i].id}}}")
```

Three patterns, no repeat block. The rows come from a plain python loop; the
picked value comes from indexing the array with a control's node; the row count
comes from hiding the spares.
````

The three:

1. **Unroll at authoring time** — `for i in range(4)` writes four labels.
2. **Reader-chosen element** — `xs[k]` with `k` a control's node records
   `\get-array-element`, so the value follows the index box.
3. **Bounded count** — `when(gm.cond.lt(i, shown))` hides the spare rows.

Note `chosen = xs[k]` sits *between* the two elements of the row. It records a
command and adds no element, so it can go anywhere after `k` exists; putting it
there keeps the reference next to what reads it.

The `f"row {i} holds ${{{xs[i].id}}}"` is fiddly on purpose: the outer f-string
substitutes the node's id, and the doubled braces leave a literal `${…}` for the
browser to resolve at read time. `xs[i]` has no python name, so its id is an
auto-name (`num-4`, …) — harmless, but it is why the source reads awkwardly.

What you cannot do here: let the reader add a fifth row. `\array` fixes its shape
when it computes.

---

## 4. Every control at once

````markdown
# Every control, in one panel

```pygeomatic
with gm.onpageload():
    with gm.ui.col(gap=2, pad=3):
        gm.ui.label("Shape")

        with gm.ui.row(gap=2):
            sides = gm.ui.radio([3, 4, 6], 4, label="sides", width="14ch")
            radius = gm.ui.slider(0.5, 3, step=0.5, value=2, label="radius", grow=1)

        with gm.ui.row(gap=2):
            spin = gm.ui.number(0, 90, value=0, step=15, label="turn", width="14ch")
            palette = gm.ui.dropdown(["amber", "teal", "pink"], "amber", label="colour", grow=1)

        with gm.ui.row(gap=2):
            labelled = gm.ui.checkbox(True, label="show a caption")
            caption = gm.ui.text("my shape", placeholder="caption", grow=1)

        with when(labelled):
            gm.ui.label("caption: ${caption}")

        with when(gm.cond.eq(palette, "teal")):
            gm.ui.label("teal is the colour the command links already use.")

    shape = gm.regular_polygon(gm.p0, radius, sides, spin)
```

Six controls, one panel. `radio` and `dropdown` both give back the chosen
option: a list of numbers makes a number the canvas can use, a list of strings
makes text you compare with `gm.cond.eq`.
````

Typing in the text box should update the caption line live.

---

## 5. A panel, a live formula, and a clickable canvas

All four manifests in one article.

````markdown
# A panel, a live formula and a clickable canvas

$$
%id:area
A = \int_{0}^{b} 2\pi t \, dt
$$

```pygeomatic
with gm.onpageload():
    with gm.ui.col(gap=2, pad=2):
        r = gm.ui.slider(1, 4, step=0.5, value=2, label="r", width="fill")

        with gm.ui.row(gap=2):
            gm.ui.math("A = \\pi r^2", width="14ch")
            gm.ui.label("with r = ${r}", grow=1)

        with gm.ui.row(gap=2):
            with gm.ui.button("small"):
                r = gm.scalar(1, out="r")
            with gm.ui.button("large"):
                r = gm.scalar(4, out="r")

    c = gm.circle(gm.p0, r)

    marker = gm.annotate_text_box("click me", 3, 3)
    with gm.ui.onclick(marker):
        r = gm.scalar(1, out="r")

area = gm.tex("area")
area.int.upper.bind(r)
```

The upper limit of the integral above tracks the same node the slider drives, so
the formula, the circle and the panel all move together.

Two ways to run commands sit side by side: the text box on the canvas is a
`gm.ui.onclick` target, and the two buttons are in the panel. Both go through the
same guard, so neither can interleave with a link sequence or with narration.
````

---

## Layout, on any element

Every element takes `width`, `height`, `grow`, `pad`, `font_size` and
`align_self`. `col` and `row` also take `gap`, `align` (across the stack) and
`justify` (along it).

```python
with gm.ui.col(gap=2, pad=2, font_size="1.1rem"):   # sizes the whole panel
    gm.ui.label("Radius", align_self="center")      # just this one, centred
    r = gm.ui.slider(1, 5, value=3, grow=1)
    gm.ui.math("A = \\pi r^2", font_size="1.4em")   # bigger than its neighbours

    with gm.ui.row(gap=1, justify="end"):           # buttons on the right edge
        with gm.ui.button("reset", font_size="0.8rem"):
            r = gm.scalar(3, out="r")
```

`font_size` is a length in `px`, `rem`, `em` or `%` — never a spacing step,
because that scale measures gaps. It **inherits**: set on a container it sizes
every `label`, `math` and `button` inside, and an element that sets its own
wins. The six controls keep their fixed sizes either way.

`justify` is `"start"`, `"center"`, `"end"` or `"between"` (gaps pushed to the
outside). It is the axis `align` does not cover: in a row, `align` moves the
children up and down, `justify` moves them left and right.

---

## Common errors

Each of these should fail the compile with a line number, not render something
broken. Worth confirming, since silent failure is what this whole mechanism was
built to remove.

```python
# unknown attribute — caught by the constructor signature
gm.ui.label("a", wdth=3)

# free-form CSS — refused; the vocabulary is closed
gm.ui.label("a", width="calc(100% - 3px)")

# a spacing step off the scale (0-9)
gm.ui.col(gap=42)

# a spacing step as a font size — refused; that scale measures gaps
gm.ui.label("a", font_size=2)

# layout on an INLINE control: a sentence decides its size
r = gm.ui.slider(1, 5, width="12ch")

# an empty container would render nothing
with gm.ui.col():
    pass
```

In the Nova editor a malformed element also shows the reason in place of itself
(a red `.nova-ui-error` box). A published article drops it silently instead — one
bad element must never cost a reader the page.
