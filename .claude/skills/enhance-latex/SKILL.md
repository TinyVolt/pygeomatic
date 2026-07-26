---
name: enhance-latex
description: Use KaTeX math as a tool for exposition in markdown, not just typesetting. Invoke to write NEW display/inline math, or to audit and rewrite EXISTING math for pedagogical clarity — color + underbrace annotation of structure, consistent notation across a document, and breaking dense one-line equalities into multi-line `aligned` blocks. Also fixes the KaTeX-in-markdown footguns (Setext-heading collisions on lone `=`/`-` lines, `$...$` nested in `\text{}`, the `\textcolor` `#`-parameter corruption), and preserves texatlas live-binding structure when editing reactive (`%id:`) formulas. Triggers: "annotate this equation", "make this math readable", "break this derivation into steps", "color the terms", "audit the notation", "underbrace", "aligned block".
---

You use LaTeX/KaTeX as a **tool for exposition**, not just typesetting. Math in a
document is meant to be *read and understood*, not merely to be correct. Your job
is to make each equation carry its own explanation. You edit only the inline
`$…$` and display `$$…$$` math (and the prose immediately around it).

This is a **KaTeX** pipeline, not full LaTeX. The color macros are custom
`\textcolor` shorthands with a parameter-expansion footgun; know them cold before
writing.

## Working principle: this document is self-contained

Everything you need to write correct, consistent, well-annotated math is here.
**Do not go hunting through other files for "exemplar" style or hex values** —
the complete macro table, color rules, and notation conventions below are the
single source of truth; apply them directly.

Notation is still a document-wide contract: the file you are editing must be
internally consistent. So you *may* Read the target file itself (and grep *within
it*) to see which convention it already uses, and match that. What you must not
do is copy a style from unrelated files.

## The three core skills

### 1. Color + underbrace to annotate structure

Use color and `\underbrace{…}_{…}` to make the *meaning* of each piece visible.

Rules for color:

- **A weight inherits the color of the thing it scales.** If column `x` is
  `\blue`, the scalar `s₁` that multiplies it is `\blue{s_1}` too. Color tracks
  *role*, not token.
- **Row / column coloring**: give each row or column its own distinct color so
  the reader can trace it through a product.
- A generic, un-role-specific weight uses `\teal`.
- Progression when you need N distinct colors: blue → pink → green → amber → …
  (`\blue \pink \green \amber`). Reuse the same assignment every time that object
  reappears in the document.

Available macros — each expands to `\textcolor{<hex>}` and consumes the following
`{…}` as its argument (`\amber{x}` → `\textcolor{fbbf24}{x}`). This is the
complete list; use only these, and use the named macro, never a raw
`\textcolor{...}`. **This set is enforced**: `compile_article` runs a KaTeX
linter (`pygeomatic/latex_lint.py`, mirrored from the browser's `Katex.tsx`
`MACROS`) that rejects any undefined `\command` in article math — e.g. a
plausible-looking `\emerald` or `\teal2` fails the compile with a line number,
rather than rendering as literal red text in the browser. Pick a color from this
table, not from the geomatic stroke palette (which has extra names like
`EMERALD` that are **not** KaTeX macros):

| macro | hex | typical role |
|---|---|---|
| `\grey` | 71717a | zinc-500 |
| `\amber` | fbbf24 | amber-400 |
| `\rose` | fb7185 | rose-400 |
| `\zinc` | e4e4e7 | zinc-200 |
| `\white` | dddddd | point |
| `\fuchsia` | E879F9 | complex |
| `\blue` | 6aa8ff | line / plot |
| `\lightblue` | 93c5fd | blue-300, legible on dark bg |
| `\violet` | B9A4FC | triangle |
| `\pink` | F472B6 | circle |
| `\lavender` | a988f5 | ellipse |
| `\orange` | F97316 | trail |
| `\green` | 10B981 | bezier |
| `\lime` | 84CC16 | polynomial |
| `\red` | F87171 | vectorField |
| `\cyan` | 22D3EE | trajectory |
| `\yellow` | f0e080 | annotation |
| `\teal` | 41dbc9 | generic weight |

**Never write raw `\textcolor{#hex}`** in prose math — and never a leading `#`:
inside these macros KaTeX reads `#`+digit as a parameter ref and corrupts the
color (e.g. `\green{p_3}` expanded against `#10B981` becomes
`\textcolor{p_30B981}` → "Invalid color"). The hexes above are stored *without*
the `#` for exactly this reason. Always use the named macro.

`\underbrace{expr}_{\text{label}}`: label what a sub-expression *is* ("weighted
sums", "then transform", "scale"). You can nest underbraces (e.g.
`\underbrace{M(\underbrace{cx}_{\text{scale}})}_{\text{then transform}}`) and
color the label text (`_{\text{\pink{scale}}}`) to tie it to the colored
expression above it. Use `\overbrace` sparingly, only when a brace below would
collide.

**Color the relationship, not just the object.** Beyond role-coloring (weight ↔
value it scales), use color to narrate what is *happening* to a term across a
derivation:

- **Cancellation**: give the two terms that cancel a shared color and underbrace
  them together with a label like `_{=\, I}` (e.g.
  `\underbrace{\teal{(A^TA)(A^TA)^{-1}}}_{=\, I}`), so the eye catches the
  cancelling pair before reading the algebra.
- **Grouping into a new object**: when several factors are regrouped into a named
  block (e.g. `VD^{1/2}` becomes `A`), color each side of the eventual grouping
  distinctly and carry that color through every line up to the
  `\underbrace{...}_{A}` that names it. Color the underbrace label to match
  (`_{\blue{A}}`), and keep using that color for the named object afterward.
- **Swapping one term for another** (e.g. `D^{1/2}` for `(D^{1/2})^T` because the
  matrix is symmetric): keep the same color on the term across the swap so it
  reads as "this same thing, now written differently," not a new quantity.

**Named/well-known equations deserve one clear visual unit.** When a multi-factor
expression *is* a well-known named result (the projection matrix
`A(A^TA)^{-1}A^T`, a rotation matrix, …) and the point is "see this whole product
as one matrix," color the **entire expression** with one color, every time it
appears — do not just recolor the shorthand symbol it gets assigned to. Add
`\underbrace{...}_{\text{name}}` at the *first* occurrence only to name it in
words; every later occurrence just carries the color, without repeating the
underbrace. Use this when the derivation's whole point is "stop looking at the
parts, see the one object," not as a default for every long expression.

### 2. Consistent notation (audit + enforce)

Treat inconsistent notation as a bug.

- **Catch stray decorators.** Prefer a bare letter (`x`, `v_1`) or a bracketed
  column over `\vec{v}`. A string like `$R(\vec{v}) = R\vec{v}$` is inconsistent
  when `\vec` appears nowhere else — rewrite it to the document's convention
  (`$R(v) = Rv$` or the bracketed-column form). Same for stray `\mathbf`,
  `\overrightarrow`, `\boldsymbol`, `\cdot` where the document uses `.` or
  juxtaposition, `*` vs `\cdot` vs juxtaposition for scaling, `^T` vs `^\top`,
  `\text{tan}` vs `\tan`.
- When a decorator/operator is used in exactly one place, grep **within the
  target file** to see which form dominates, then converge the outlier onto it.
  Decide by the target file alone. Report every normalization you make.
- Keep subscripts, index bases (0- vs 1-based), and object names identical to the
  surrounding prose and code.

### 3. Break `A = B = C = …` into a multi-line aligned block

**Never** ship a single-line chain of equalities `$$A = B = C = D$$` — it hides
the derivation. Break it into an `aligned` environment aligned at `=`:

```
$$\begin{aligned}
A &= B \\
  &= C \\
  &= D
\end{aligned}$$
```

Each `&=` line is one deliberate step. This applies to derivations,
simplifications, and definitions-then-expansion. (KaTeX needs `displayMode` for
`aligned`, which `$$…$$` provides.) Use `&` the same way for systems, piecewise
defs (`cases`), and multi-term factorings.

**Write the block as an actual multi-line string in the source**, one step per
physical line — never collapse an `aligned` block onto a single crammed line just
because KaTeX ignores the newlines. The next editor needs to find and change one
line, not re-parse a wall of `\\`.

**Space out dense steps.** When one step is visibly denser than its neighbors (it
expands into a matrix, carries an `\underbrace`, or is just long), give it room:
use a blank alignment row (`\\ \\` instead of `\\`) before and/or after that
line, rather than spacing every line uniformly.

**Blank line after every `\underbrace` in a multi-line equation.** Whenever a
line inside an `aligned` block contains an `\underbrace{...}_{...}`, follow it
with a blank alignment row (`\\ \\`) before the next step — the label needs a
visual beat to land.

## Reactive formulas (texatlas): don't break the live bindings

Some `$$…$$` blocks are **reactive**: their first line is a `%id:name` comment,
and a `pygeomatic` code fence *elsewhere in the same article* wires parts of them
to live store nodes — a substituted value (`gm.tex("name").frac.num.bind(node)`),
a revealed brace/matrix column (`.reveal(...)`), or highlighted cells
(`.highlight(...)`). The LaTeX you see is a *template*: the browser resolves those
addresses against the KaTeX parse tree at mount and patches the DOM. **Editing the
template can silently kill the reactivity** — the formula still renders, but a
broken address is swallowed as a console warning and the live behavior just dies
(you'd never see it in a compile). So before touching a `%id:` block, read the
fence that binds it (it's in the same file) and preserve the structures it
addresses. The following are **verified** against the resolver.

**Safe — do these freely:**

- **Color a bound slot by wrapping its whole family**, not its inner argument:
  `\teal{\frac{a}{b}}` (not `\frac{\teal{a}}{b}`). The injected live value renders
  *inside* the color wrapper, so it inherits the color — a live readout you can
  role-color like any other term.
- **`\underbrace`/`\overbrace` around a bound `\frac`/`\sqrt`, or around a matrix
  that `reveal`/`highlight` animates.** The resolver recurses through brace
  wrappers, so naming a live sub-expression with a brace does not detach its
  binding.
- **Break a reactive `A = B = C` into `\begin{aligned}`.** The `aligned` wrapper
  is *not counted* when numbering matrices, and family occurrences are counted
  across the whole tree — so wrapping never shifts a `matrix=N` target or a bare
  `.frac`/`.sqrt` address.

**Breaks it — invariants you must hold:**

- **Keep exactly one occurrence of each bound family the fence addresses by bare
  name** (`.frac`, `.sqrt`, `.underbrace`, `.int`, `.sum`, `.prod`). Adding a
  second `\frac` to a formula whose fence says `t.frac.num.bind(...)` makes the
  address ambiguous and the binding fails. If a second one is unavoidable, that's
  an authoring change (the fence must switch to indexed `t.fracs[i]`), so flag it
  rather than silently introducing the ambiguity.
- **Preserve matrix count and source order.** Matrices are numbered in source
  order *skipping* equation-layout arrays (`aligned`/`align`/`split`/`alignat`/
  `gather`/`CD`); inserting or reordering a `pmatrix` renumbers every `matrix=N`
  highlight/reveal.
- **Never empty a bound slot.** Bind *replaces* a slot's content, it never creates
  structure, so a slot you keep must still hold a placeholder symbol.
- **Only these families are bindable browser-side:** `int`, `sum`, `prod`, `frac`,
  `sqrt` (plus `underbrace`/`overbrace` for *reveal* only). `\sqrt`'s optional
  index `[n]` (`sqrt.index`) is **not** bindable. Don't relocate a live readout
  into an unsupported construct.

**One gotcha to recognize (authoring-side, but flag it):** a value-bound slot
shows its node's *current* value from the very first beat. If the node is
initialized to a not-yet-meaningful number (e.g. `0` before it's computed), the
reader sees a wrong number early. The clean fix is to not create the node until
it's meaningful — then the slot shows its authored *symbol* until the binding node
exists. If your annotation implies "the number appears later," make sure the
formula actually behaves that way, or tell the author.

## House rules (hard)

- **Never leave `=` (or `-`) alone on its own line inside a `$$…$$` block.** This
  is a *markdown* footgun: the block lexer runs before the inline display-math
  tokenizer, and a lone `=` line directly under text is Setext-heading syntax
  (`===` H1; a lone `-` line is `---` H2). The renderer grabs the lines above the
  `=` as a heading, splits the rest, and the `$$…$$` is never recognized as one
  math unit — the whole block renders as literal text. Keep the `=` attached to
  the end of the preceding line (`…}_{R_z(\alpha)} =`) or the start of the next
  line, never on a line by itself. (Inside an `aligned` block this never bites,
  because `&=` is mid-line.) When auditing, scan every `$$…$$` block for a line
  matching `^\s*[=-]+\s*$`.
- **Never nest `$...$` inside `\text{}`.** Plain LaTeX lets `\text{...}` switch
  back into math with `$...$`; KaTeX does **not**, and it renders broken. This
  shows up in reason-annotations like `\text{(column $i$ is $Rv_i$)}`. Fix by
  breaking out of `\text{}` for the math parts:
  `\text{(column } i \text{ is } Rv_i\text{)}`. When auditing, grep the target
  file for `\text{[^}]*\$`.
- **No em dashes (—) anywhere** in prose you write. A hyphen, comma, or colon is
  fine. (Leave existing `\text{—}` matrix row-markers alone.)
- `\text{…}` for words inside math; multi-word function names use
  `\text{weighted\_sum}` with the escaped underscore, matching existing usage.
- One idea per display block. If an equation needs a sentence of setup, put the
  sentence before it, not a second equation.
- Don't renumber sections or restructure prose beyond what the math change
  requires.

## When done

Report: which equations you added or rewrote, every notation inconsistency you
normalized (old → new, and why that form won), and any place where the document's
convention itself looked ambiguous so the author can rule.
