# Animation

Moving values and shapes over time, and tracing the path a moving point leaves behind.

Animation works through the live graph: animate one input, and everything built from it
moves with it on every frame.

## animate

`gm.animate(s, target)` moves the Scalar `s` from its current value to `target`. Every
node built from `s` updates each frame. Afterwards `s` holds `target`.

- It is imperative: call it without assigning.
- An animation lasts between 0.5 and 1 second. `gm.animation_speed` (default 0.001 units
  per millisecond) sets the pace inside that window.
- An Array `s` with an Array or Scalar `target` animates all elements together. Give
  arrays of the same length: elements are paired by position, with no error when the
  lengths differ (see the `arrays` guide).
- Commands run in order, so a second `animate` starts after the first ends.
- Animate free inputs made from numbers. The animated node is overwritten with plain
  numbers, so a computed node would lose its link to its inputs.

```python
angle = gm.scalar(0)
radius = gm.scalar(2)
tip = gm.point(radius * gm.cos(angle), radius * gm.sin(angle))
arm = gm.line(gm.p0, tip)
gm.animate(angle, 6.28)          # the arm sweeps a full turn
gm.animate(radius, 1)            # then shrinks
```

## translate and rotate

- `gm.translate(obj, dx, dy)` slides a shape by (dx, dy), animated.
- `gm.translate_array(array, dx, dy)` does the same for every element of an array.
- `gm.rotate(obj, center, angle)` turns a shape around `center`; `angle` is in degrees.

They move the points a shape is built from: a Point itself, a Circle, Arc or
RegularPolygon's center, a Triangle or Polygon's vertices, a Line's endpoints, a text
box's position. Those points are overwritten with plain numbers, so they should be free
inputs made from numbers.

```python
a = gm.point(-1, 0)
b = gm.point(1, 0)
c = gm.point(0, 2)
tri = gm.triangle(a, b, c)
gm.translate(tri, 2, 1)
pivot = gm.point(1, 1)
gm.rotate(tri, pivot, 90)
```

## trail

`gm.trail(*points)` records where each point has been every time it moves, and draws the
path. It starts recording from the next change.

```python
t = gm.scalar(0)
x_t = gm.cos(3 * t)
y_t = gm.sin(2 * t)
dancer = gm.point(x_t, y_t)
gm.trail(dancer)
gm.animate(t, 6.28)              # draws a Lissajous curve
```

This is the usual way to draw a parametric curve: a time Scalar, coordinates built from
it, a point from those, a trail on the point, then `animate` the time.

`gm.clear_trail` erases a trail, but a trail cannot be referred to from pygeomatic yet,
so it cannot be used here.
