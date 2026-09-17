# Formula commands

Plots, vector fields, flows, ODEs and SDEs: commands that take an input node plus an output built from it, and treat the chain between them as a function.

## The idea

These commands take a placeholder input node and an output node built from it with `gm`
calls. The engine reads the chain of nodes between them as a function, and evaluates it
at many input values itself.

- The placeholder's own value is ignored, except that the time node `t` in `solve_ode`
  and `simulate_sde` sets the start time.
- The output must be built from the placeholder. If it is not, nothing fails, but the
  result is wrong: a flat plot, identical arrows, a straight path.
- Every other node the formula uses stays live. Change it, and the result redraws.
- Use a fresh placeholder for each role. Never read a placeholder as an ordinary value
  somewhere else, and never reuse its name for another node.
- Use built-in functions in the formula. Extension functions inside a formula are
  treated as constants.

## plot_reactive and plot_inverse

`gm.plot_reactive(x, y)`: `x` is a Scalar placeholder, `y` a Scalar built from `x`. The
engine sweeps `x` across the visible width and draws `y`.

`gm.plot_inverse(x, y)`: the same, but the placeholder is swept up the vertical axis and
the output is drawn horizontally, for curves like x = f(y).

```python
x = gm.scalar(0)
a = gm.scalar(1)
wave = a * gm.sin(x)
gm.plot_reactive(x, wave)                    # change a to rescale the wave

amps = gm.array(0.5, 1, 1.5)
waves = amps * gm.sin(x)                     # an array output gives one curve each
gm.plot_reactive(x, waves)

s = gm.scalar(0)
sideways = s * s
gm.plot_inverse(s, sideways)                 # x = y²

cubic = x * x * x
touch = gm.scalar(1)
curve = gm.plot_reactive(x, cubic)
gm.tangent(curve, touch, 3)                  # tangent line at x = 1, length 3
```

## vector_field

`gm.vector_field(p, out)`: `p` is a Point placeholder.

- `out` a Point: the arrow drawn at each grid point p is `out` evaluated there.
- `out` a Scalar: the arrow at p is the gradient of `out` there.

It is imperative: call it without assigning.

```python
p = gm.point(0, 0)
k = gm.scalar(0.5)
spin_x = -k * p.y
spin_y = k * p.x
spin = gm.point(spin_x, spin_y)
gm.vector_field(p, spin)                     # rotation, scaled by k

bowl = p.x * p.x + 2 * p.y * p.y
gm.vector_field(p, bowl)                     # gradient arrows (2x, 4y)
```

## flow

`gm.flow(p, out, start, duration, steps=200)` follows the same kind of field from
`start` for `duration` time units and draws the path. `p` and `out` mean the same as in
`vector_field`; a Scalar `out` follows the gradient (slower than a Point field). A
negative `duration` runs backward. An Array of start Points draws one path each.

```python
p = gm.point(0, 0)
spin = gm.point(-p.y, p.x)
start = gm.point(2, 0)
duration = gm.scalar(3)
orbit = gm.flow(p, spin, start, duration)

starts = gm.point(gm.linspace(1, 3, 3), 0)
orbits = gm.flow(p, spin, starts, duration)
```

## solve_ode and eval_ode

`gm.solve_ode(t, y, dydt, y0, t1, steps=200)` solves dy/dt = f(t, y) and draws the
curve (t, y(t)).

- `t`: Scalar time placeholder. Its value is the start time.
- `y`: Scalar state placeholder; its value is ignored.
- `dydt`: a Scalar built from `t` and/or `y`.
- `y0`: the value of y at the start time. An Array gives one curve each.
- `t1`: the end time. If it is before the start time, the solve runs backward.
- `y` is a single Scalar: systems of several coupled equations are not supported.

`gm.eval_ode(curve, when)` returns the Point (t, y(t)) on a solved curve.

```python
t = gm.scalar(0)
y = gm.scalar(0)
rate = gm.scalar(0.8)
dydt = -rate * y
y_start = gm.scalar(3)
t_end = gm.scalar(5)
decay = gm.solve_ode(t, y, dydt, y_start, t_end)
when = gm.scalar(2)
marker = gm.eval_ode(decay, when)            # follows when, rate and y_start
```

## simulate_sde

`gm.simulate_sde(t, x, drift, diffusion, x0, t1, steps=200, seed=-1)` simulates
dX = drift·dt + diffusion·dW and draws one random path. `drift` and `diffusion` are
Scalars built from `t` and/or `x`.

- `seed` below 0 (the default) draws a new random path on every recompute.
- `seed` 0 or above gives a repeatable path; changing other inputs reshapes the same
  path.
- An Array `x0` draws one path per start value.

```python
t = gm.scalar(0)
x = gm.scalar(0)
pull = gm.scalar(1)
drift = -pull * x
noise = gm.scalar(0.5)
x_start = gm.scalar(2)
t_end = gm.scalar(6)
seed = gm.scalar(7)
path = gm.simulate_sde(t, x, drift, noise, x_start, t_end, 200, seed)
```

## partial_derivative

`gm.partial_derivative(target, param)` follows the same pattern: `target` must be built
from `param`. See the `autodiff` guide.
