# Scaling a vector

```pygeomatic
gm.clear()
scale = gm.scalar(1)
x = gm.mul(scale, 3)
y = gm.mul(scale, 2)
v0 = gm.line(gm.node("p0"), gm.point(3, 2))
gm.hide(v0)
v1 = gm.line(gm.node("p0"), gm.point(x, y))
p_text = gm.point(-2, 2)
gm.hide(p_text)
text_scale = gm.text("Scale: ${scale}")
tbox = gm.annotate_text_box(text_scale, p_text.x, p_text.y, 12)

with group("show-vector"):
    gm.highlight(v0)
```

Scaling a vector only changes its norm, not its direction. E.g. given a
{vector}(ref:show-vector) $\begin{bmatrix} 3 \\ 2 \end{bmatrix}$ one can modify
the scale and watch the magnitude change:

- {Increase scale}(gm.animate(scale, 2))
- {Decrease scale}(gm.animate(scale, -2))
- {Set `scale = 0.5`}(scale = gm.scalar(0.5))

A function to compute the norm looks like this (regular code fences are left
untouched):

```python
def norm(array):
    return sum(i**2 for i in array)**0.5
```

Math regions are never scanned for spans: $\theta = \tan^{-1}(y / x)$ and
$\text{add}(\blue{v_1}, \pink{v_2})$ come through verbatim.
