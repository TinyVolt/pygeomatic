"""Mirror of overloads/div.ts: Scalar | Complex division."""

from ..implementations.complex_functions import complex_divide
from ..implementations.scalar_functions import scalar_divide
from .create_overload import binary_overload

div = binary_overload("div", "Divide", scalar_divide, complex_divide)
