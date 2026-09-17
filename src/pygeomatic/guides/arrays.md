# Arrays and broadcasting

Arrays of nodes, how to make and index them, and how passing an array to an ordinary function runs it once per element.

## What an array is

An Array node is an ordered list of nodes that all have the same type (all Scalars, all
Points, all Circles, ...). The elements are live nodes: when an input of an element
changes, that element recomputes, and so does everything built from the array.

An array also has a shape, like NumPy. `gm.array(1, 2, 3)` has shape `[3]`;
`gm.reshape(xs, 3, 1)` gives shape `[3, 1]`.

## Making arrays

```python
radii = gm.array(1, 1.5, 2)          # from values or nodes of one type
xs = gm.linspace(-3, 3, 7)           # 7 evenly spaced Scalars from -3 to 3
ks = gm.arange(0, 5, 1)              # 0, 1, 2, 3, 4 (end excluded)
ring = gm.circular_arange(6, 2)      # 6 Points evenly spaced on a circle of radius 2
ones = gm.ones(4)                    # 1, 1, 1, 1
zeros = gm.zeros_like(xs)            # same length as xs, all 0
col = gm.reshape(xs, 7, 1)           # same elements, shape [7, 1]
```

- `gm.array` needs at least one element, all of one type. Arrays passed to it are not
  unpacked: `gm.array(a, b)` with two arrays makes an array holding two arrays.
- `gm.reshape` needs the new dimensions to multiply to the element count exactly. There
  is no `-1`.
- Some commands return arrays: the `intersection_*` commands (except
  `intersection_line_line`), `polyline`, `fft`, `ifft`, `circular_arange`.

## Reading arrays

```python
xs = gm.linspace(-3, 3, 7)
first = xs[0]                        # records \get-array-element xs 0
last = xs[-1]                        # negative literal indices are allowed
i = gm.scalar(2)
picked = xs[i]                       # a Scalar node as the index stays live
count = xs.length                    # a Scalar node
n = len(xs)                          # a plain Python int, for loops
for k in range(n):
    gm.highlight(xs[k])
```

Not supported: slices (`xs[1:3]`) and assignment (`xs[0] = v`).

## Broadcasting

Most functions accept arrays wherever they take a single value. They then run once per
element and return an array of results. This follows NumPy's rules: shapes are lined up
from the right, and each pair of sizes must be equal or one of them must be 1. A plain
value (not an array) is used for every element.

```python
xs = gm.linspace(-3, 3, 7)
dots = gm.point(xs, 0)               # 7 Points along the x axis
ys = gm.sin(xs)                      # 7 Scalars
curve_pts = gm.point(xs, ys)         # 7 Points on the sine curve
doubled = 2 * xs + 1                 # infix arithmetic is element-wise too
```

A column against a row gives every combination:

```python
cx = gm.linspace(-3, 3, 3)
cx_col = gm.reshape(cx, 3, 1)        # shape [3, 1]
centers = gm.point(cx_col, 0)        # shape [3, 1]
rs = gm.array(0.5, 1)                # shape [2]
rings = gm.circle(centers, rs)       # shape [3, 2]: 6 circles
```

Because `gm.array` is always one-dimensional, the `reshape` to a column is required for
this.

Broadcasting also works in the commands that take a formula:

- `plot_reactive(x, ys)` with an array `ys` draws one curve per element.
- `solve_ode(..., y0s, ...)` and `simulate_sde(..., x0s, ...)` with an array start value
  draw a family of curves; `flow(..., starts, ...)` with an array of Points draws a
  family of paths.
- `partial_derivative(target, params)` with an array of Scalars or Points gives an array
  of derivatives.

`animate(values, targets)` also runs per element, and all elements move together. It
pairs elements by position and ignores shape, so give it arrays of the same length, or a
single target number:

- A shorter `targets` array: the extra values animate to 0.
- A longer `targets` array: the extra targets are ignored.
- A column against a row does not expand to every combination.
- A single Scalar with an array of targets animates to each in turn and ends at the last.

None of these raise an error.

## Commands that take any number of arguments

`add`, `mul`, `min_`, `max_`, `and_`, `or_`, `polygon`, `polyline`, `convex_hull`,
`polynomial` and `trail` take any number of arguments. They broadcast like every other
command: an array in any argument runs the command once per element.

An array is never unpacked into the argument list. To pass many points, unpack a Python
list instead:

```python
corners = [gm.point(0, 0), gm.point(4, 0), gm.point(0, 3)]
tri = gm.polygon(*corners)            # one polygon through the three points
hull = gm.convex_hull(*corners)

a = gm.array(1, 2, 3)
b = gm.array(10, 20, 30)
sums = gm.add(a, b, 100)              # 111, 122, 133
smallest = gm.min_(a, b)              # 1, 2, 3
low = gm.reduce_min(a)                # 1: one array alone needs reduce_*

xs = gm.array(1, 2, 3)
bottoms = gm.point(xs, 0)
tops = gm.point(xs, 1)
apex = gm.point(0, 4)
tents = gm.polygon(bottoms, tops, apex)   # 3 triangles, one per element
consts = gm.polynomial(a)             # 3 flat polynomials y = 1, y = 2, y = 3
lines = gm.polynomial(1, a)           # y = 1 + x, y = 1 + 2x, y = 1 + 3x
gm.trail(tops)                        # one trail per point
```

- `gm.polygon(ring)` with one array of points fails: it needs at least three arguments.
  `polyline` and `convex_hull` need at least two. `add`, `mul`, `min_` and `max_` need at
  least two; for one array use `reduce_sum`, `reduce_min`, ... A call with too few
  arguments raises an error that says how many are needed and, when you passed an array,
  suggests unpacking it with `*`.
- `gm.polynomial(a)` does not read the coefficients from `a`. It makes one polynomial per
  element.
- `gm.polyline(p, points)` with an array `points` gives an array of arrays of Lines.

## Commands with their own array rules

- `highlight(*nodes)`: an array is expanded, and each element flashes.
- `hide(*nodes)`, `show(*nodes)` and `set_stroke` / `set_fill` with one color: act on
  the array, and every element follows, including elements added later and the nodes a
  `gm.array(p, q)` was made from. A node in several colored arrays takes the color of the
  array colored last; a color set on the node itself always wins. `show` undoes a `hide`
  only on the same node: showing one element of a hidden array does nothing.
- `set_stroke` / `set_fill` with an array of colors: one color per element.
- `remove(*nodes)`: removes the array and its elements. For `gm.array(p, q)` that
  deletes `p` and `q` themselves.
- `param(*nodes)`: an array registers every element as a parameter; `backprop` gives
  each element its own gradient. Move them with `gradient_descent_step()` (no arguments)
  or `minimize`. `gradient_descent_step(arr)` with the array named fails: it only
  accepts Scalars and Points.
- `array(*elements)` and `reshape(array, *dims)`: see above.

## Commands that take the whole array

These use the array as one value and do not run per element:

- `array`, `get_array_element`, `reshape`, `linspace`
- `reduce_sum`, `reduce_min`, `reduce_max`, `reduce_mean`, `reduce_std`, `reduce_var`
- `softmax`, `cumsum`, `fft`, `ifft`, `filter_`

```python
xs = gm.linspace(-3, 3, 7)
total = gm.reduce_sum(xs)            # one Scalar
grid = gm.reshape(gm.arange(0, 6, 1), 2, 3)
col_sums = gm.reduce_sum(grid, 0)    # dim 0 removed: shape [3]
probs = gm.softmax(xs)
running = gm.cumsum(xs)
positive = gm.filter_(xs, gm.gt(xs, 0))   # keeps elements where the mask is true
```

`dim=-1` (the default) reduces over every element to one Scalar. `dim=k` removes axis
`k`.

## Pitfalls

- Shapes that do not match (`[3]` with `[2]`) raise an error.
- Each broadcast element is its own node, with its own gradient.
- Name arrays, not elements: `dots = gm.point(xs, 0)` names the array `dots`; its
  elements get engine names. Use `dots[k]` to reach one.
