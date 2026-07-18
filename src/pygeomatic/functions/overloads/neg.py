"""Mirror of overloads/neg.ts: Scalar | Complex negation."""

from ..implementations.complex_functions import complex_negate
from ..implementations.scalar_functions import scalar_negate
from .create_overload import unary_overload

neg = unary_overload("neg", "Negate", scalar_negate, complex_negate)
