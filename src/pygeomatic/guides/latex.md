# Manipulating LaTeX

Binding scalar nodes into a LaTeX formula with gm.tex, highlighting entries of a matrix, and revealing parts of a formula on a condition.

It has three components:
- `bind`: binds a scalar node to a part of a latex string.
- `highlight`: conditionally highlights entries of an array-like latex (useful for matrices)
- `reveal`: conditionally reveals parts of a latex

## 1. `bind`

$$
%id:energy
\int_a^b x^2 \, dx
$$

```pygeomatic
a = gm.scalar(0.5)
b = gm.scalar(1)
body = gm.text('this part get integrated')
energy = gm.tex('energy')
energy.int.lower.bind(a)
energy.int.upper.bind(b, fmt='.2f')

text_animate = gm.annotate_text_box('Animate b to 5', 0, 5, 14, -1)

with gm.ui.onclick(text_animate):
  gm.animate(b, 5)
```
- Bind {$a$ and $b$}(b = gm.scalar(1))

---

## 2. `highlight`

$$
%id:mat
M = \begin{pmatrix} a & b & c & d \\ e & f & g & h \\ h & i & j & k \end{pmatrix}
$$

```pygeomatic
gm.clear()
highlight_row_index = gm.scalar(-1)
mat = gm.tex('mat')
mat[highlight_row_index, :].highlight()

text_hl_row0 = gm.annotate_text_box('Highlight row 0', -3, 2, 14, -1)
text_hl_row1 = gm.annotate_text_box('Highlight row 1', -0, 2, 14, -1)
text_hl_row2 = gm.annotate_text_box('Highlight row 2', 3, 2, 14, -1)

for i, txt in enumerate([text_hl_row0, text_hl_row1, text_hl_row2]):
  with gm.ui.onclick(txt):
    highlight_row_index = gm.scalar(i)

# mat.highlight(gm.cols - gm.rows > 0, color='blue')
```

- Show {the text boxes}(b = gm.scalar(5)): click the boxes to highlight rows. 
- {Remove}(highlight_row_index = gm.scalar(-1)) row highlights. 

### 2.1 When a latex contains multiple matrices

Use `matrix = <index>` in the `highlights` method. 


```pygeomatic
gm.clear()
matmul = gm.tex('matmul')
matmul.diag().highlight(color='blue')
matmul.triu().highlight(color='lime', matrix=1)

show = gm.ui.checkbox(True, label='Show the matrices')
gm.md(f'{show}')

with gm.when(show):
  gm.md(r'''  
$$
%id:matmul
A = \begin{pmatrix} a & b \\ c & d \end{pmatrix}
\quad
B = \begin{pmatrix} e & f \\ g & h \end{pmatrix}
$$
  ''')
```

---

## 3. `reveal`

### 3.1 Reveal underbrace with text

$$
%id:pyth-both
a^2 + b^2 = \underbrace{c^2}_{\text{hypotenuse}}
$$

```pygeomatic
gm.clear()
# shown = gm.bool_(False)
shown = gm.ui.checkbox(False, label='Show hint')
gm.md(f'{shown}')

p = gm.tex("pyth-both")
p.underbrace.reveal(shown)
```

### 3.2 Reveal only the underbrace text

$$
%id:pyth-label
a^2 + b^2 = \underbrace{c^2}_{\text{hypotenuse}}
$$

```pygeomatic
gm.clear()
shown2 = gm.ui.checkbox(False, 'Show hint')
gm.md(f'{shown2}')

p = gm.tex("pyth-label")
p.underbrace.label.reveal(shown2)
```

### 3.3 Reveal only the body 

$$
%id:eipi
e^{i \pi} = \underbrace{-1}_{\text{guess}}
$$

```pygeomatic
gm.clear()
shown3 = gm.ui.checkbox(False, label='Show the answer')
gm.md(f'{shown3}')

eipi = gm.tex('eipi')
eipi.underbrace.body.reveal(shown3)
```

### 3.4 Matrix columns

$$
%id:matcols
M = \begin{pmatrix} a & b & c \\ d & e & f \\ g & h & i \end{pmatrix}
$$

```pygeomatic
gm.clear()

k = gm.ui.slider(0, 3, step=1, value=0, label='Column')
gm.md(f'{k}')

matcols = gm.tex('matcols')
# matcols.reveal(M.cols() < k)
matcols.reveal(gm.cols < k)
```

### 3.5 Multi-step latex

$$
%id:deriv
\begin{aligned}
f(x) &= (x+1)^2 \\
     &= x^2 + 2x + 1 \\
     &= x(x+2) + 1
\end{aligned}
$$

```pygeomatic
step = gm.ui.slider(0,3,1,0,label='Steps to show')
gm.md(f'{step}')
deriv = gm.tex('deriv')
deriv.rows().reveal(gm.rows < step)
```
