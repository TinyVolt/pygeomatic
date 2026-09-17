# Complex numbers

Complex nodes, arithmetic that works on both Scalars and Complex values, and the Fourier transform.

## Making and reading

```python
z = gm.complex_(1, 2)          # 1 + 2i
re = z.re                      # live Scalar parts
im = z.im
same_re = gm.real(z)           # the same as z.re
same_im = gm.imag(z)
zbar = gm.conj(z)              # 1 − 2i
size = gm.abs_(z)              # |z|, a Scalar
phase = gm.arg(z)              # angle in radians, from atan2(im, re)
```

A Complex node is drawn as a dot at (re, im).

## Arithmetic

These work on Scalars and on Complex values: `add`, `sub`, `mul`, `div`, `neg`, `pow_`,
`exp`, `log`, `sqrt`, `abs_`. The infix operators `+ - * /` and unary `-` use them, so
ordinary Python arithmetic works:

```python
z = gm.complex_(1, 2)
w = gm.complex_(0, 1)
total = z + w
product = z * w                # (1 + 2i)·i = −2 + i
shifted = z + 1                # a plain number or Scalar becomes re + 0i
squared = gm.pow_(z, 2)
rotation = gm.exp(w)           # e^i
root = gm.sqrt(gm.complex_(-4, 0))   # 2i
```

- If any argument is Complex, the result is Complex.
- `abs_` always returns a Scalar.
- `log`, `sqrt` and `pow_` use the principal branch.
- `%` does not accept Complex values.
- Coercions are off by default, so a Complex cannot be passed where a Point is
  expected. Build the point from its parts:

```python
z = gm.complex_(1, 2)
tip = gm.point(z.re, z.im)
arm = gm.line(gm.p0, tip)
```

## Arrays of complex values

Complex values broadcast like Scalars:

```python
angles = gm.linspace(0, 6, 7)
unit_circle = gm.exp(gm.complex_(0, angles))   # 7 points on the unit circle
```

## Fourier transform

`gm.fft(array)` turns an Array of Scalars (or Complex values) of any length into an
Array of Complex frequency values: X_k = Σ x_n·e^(−2πikn/N). `gm.ifft(spectrum)` turns
it back, so `ifft(fft(x))` gives `x`. Both take the whole array at once.

```python
signal = gm.array(0, 1, 0, -1)
spectrum = gm.fft(signal)
strength = gm.abs_(spectrum)   # the magnitude of each frequency
back = gm.ifft(spectrum)
```

Gradients flow through the real and imaginary parts, so Complex math works with
`partial_derivative`, `backprop` and optimization.
