"""Mirror of overloads/add.ts: Scalar | Complex addition (variadic)."""

from ..implementations.complex_functions import complex_add
from ..implementations.scalar_functions import scalar_add
from .create_overload import variadic_overload

add = variadic_overload("add", "Add", scalar_add, complex_add)
