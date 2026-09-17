# Optimization

Moving parameters downhill on a Scalar loss with gradient descent, one visible step at a time or many steps at once.

Read the `autodiff` guide first: optimization uses `param`, `backprop` and the gradients
they store.

## The pieces

- `gm.param(*nodes)`: the free Scalars or Points to optimize.
- `gm.learning_rate`: the step size, 0.01 by default. Change it with
  `learning_rate = gm.scalar(0.5)` (the variable name becomes the id `learning-rate`).
- `gm.gradient_descent_step(*nodes)`: moves each node by `−learning_rate × gradient`.
  With no arguments it moves every parameter. It needs a stored gradient, so run
  `backprop` first.
- `gm.zero_grad()`: resets stored gradients. Gradients add up otherwise.
- `gm.zero_back_step(loss)`: one full step: `zero_grad`, `backprop(loss)`,
  `gradient_descent_step()`.
- `gm.minimize(loss, iterations)`: runs many steps at once. `iterations` must be a
  Scalar node holding a positive whole number.
- `gm.reevaluate(node)`: recomputes a node from the current values and stores the
  result.

Everything built from the parameters follows each step, so the scene moves as the
optimizer runs.

## Step by step

Each step is its own command, so the scene updates visibly after every one.

```python
a = gm.point(0, 3)
b = gm.point(5, 0)
c = gm.point(-2, -1)
corners = gm.array(a, b, c)
tri = gm.triangle(a, b, c)
p = gm.point(2, -1)
gm.param(p)
spokes = gm.line(p, corners)         # one line from p to each corner
dists = gm.distance(p, corners)      # broadcasts: 3 distances
loss = gm.reduce_sum(dists)
learning_rate = gm.scalar(0.5)
for _ in range(10):
    gm.zero_back_step(loss)          # p walks toward the Fermat point
```

## Many steps at once

```python
w = gm.scalar(4)
gm.param(w)
bowl = (w - 1) * (w - 1)
learning_rate = gm.scalar(0.1)
steps = gm.scalar(200)
gm.minimize(bowl, steps)             # w ends near 1
```

`minimize` only shows the final result. It stops with an error if the values become
NaN, which usually means the learning rate is too high.

## Rules

- Register parameters with `param` before `backprop`, `gradient_descent_step()` or
  `minimize`.
- Parameters must be free inputs made from numbers. A step overwrites the parameter
  with a plain number, so a computed parameter would lose its link to its inputs.
- `gradient_descent_step` takes single Scalars and Points, or no arguments. To move an
  array parameter, call it with no arguments (or use `minimize`); passing the array
  raises an error.
- The loss must be a Scalar built from the parameters through `gm` calls.
