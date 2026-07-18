"""Mirror of overloads/mul.ts: Scalar | Complex multiplication (variadic)."""

from ..implementations.complex_functions import complex_multiply
from ..implementations.scalar_functions import scalar_multiply
from .create_overload import variadic_overload

mul = variadic_overload("mul", "Multiply", scalar_multiply, complex_multiply)
