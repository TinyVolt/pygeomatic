"""Mirror of overloads/sqrt.ts: Scalar | Complex square root."""

from ..implementations.complex_functions import complex_sqrt
from ..implementations.scalar_functions import scalar_sqrt
from .create_overload import unary_overload

sqrt = unary_overload("sqrt", "Sqrt", scalar_sqrt, complex_sqrt)
