# Automatic differentiation

Getting derivatives of any Scalar built from other nodes, either as a live node or as gradients stored on chosen inputs.

The engine can differentiate any Scalar with respect to the nodes it was built from, by
following the chain of `gm` calls between them. There are two ways to ask for a
derivative.

## 1. `partial_derivative`: a live derivative node

`gm.partial_derivative(target, param)` returns a node holding d target / d param at
the current value of `param`. It is an ordinary live node: change `param` or anything
else in `target`'s formula, and it recomputes.

- `target` must be a Scalar built from `param`.
- `param` a Scalar gives a Scalar result.
- `param` a Point gives a Point result holding (∂target/∂x, ∂target/∂y). It is drawn as
  an arrow starting at `param`.
- `param` an Array of Scalars or Points gives an Array of results, one per element.

```python
w = gm.scalar(2)
loss = w * w - 3 * w
slope = gm.partial_derivative(loss, w)       # 2w − 3 = 1 now; follows w

p = gm.point(1, 2)
height = p.x * p.x + p.y * p.y
grad_arrow = gm.partial_derivative(height, p)   # (2x, 2y), drawn as an arrow at p

scaled = gm.mul(slope, 0.5)                  # usable wherever a Scalar is
```

- Infix operators (`0.5 * slope`) do not work on these results yet. Use the explicit
  functions (`gm.mul`, `gm.add`, ...).
- Second and higher derivatives do not work yet. `gm.partial_derivative(slope, w)` runs
  without an error but always gives 0, so never chain `partial_derivative`.

## 2. `param` and `backprop`: gradients stored on inputs

This is the machinery gradient descent uses (see the `optimization` guide).

- `gm.param(*nodes)` marks free input Scalars or Points as parameters. An array marks
  every element.
- `gm.backprop(loss)` computes the gradient of the Scalar `loss` with respect to every
  parameter and stores it on the parameter. A Point parameter with a gradient is drawn
  with an arrow.
- Gradients add up: each `backprop` adds to what is stored. Call `gm.zero_grad()` first
  to reset them.

```python
a = gm.point(0, 0)
b = gm.point(4, 0)
c = gm.point(1, 3)
tri = gm.triangle(a, b, c)
gm.param(c)
spread = gm.angle(a, c, b)
gm.zero_grad()
gm.backprop(spread)            # c now shows the direction that widens the angle
```

Stored gradients cannot be read into a node. Use `partial_derivative` when the
derivative itself should be shown or used in further math.

## What gradients flow through

- All built-in functions, including shapes, measurements, arrays and complex numbers.
- Broadcast arrays: each element is its own node with its own gradient.
- Extension functions only if the extension was written to support it.

Gradients do not flow when `gm.with_numeric_mode` is true: that setting makes the math
faster by giving up gradients.

## Rules

- `target` and `loss` must be Scalars.
- Parameters should be free inputs made from numbers (`gm.scalar(2)`, `gm.point(1, 2)`),
  not computed nodes.
- The chain from the parameter to the target must be made of `gm` calls. A value typed
  in by hand has no link, so its derivative is 0.
- Do not reuse a node in two roles. If a formula command (see the `formulas` guide) uses
  a node as its input placeholder, do not also read that node as a constant inside a
  formula you differentiate.
