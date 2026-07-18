"""Mirror of overloads/sub.ts: Scalar | Complex subtraction."""

from ..implementations.complex_functions import complex_subtract
from ..implementations.scalar_functions import scalar_subtract
from .create_overload import binary_overload

sub = binary_overload("sub", "Subtract", scalar_subtract, complex_subtract)
