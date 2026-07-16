"""Mirror of overloads/exp.ts: Scalar | Complex exponential."""

from ..implementations.complex_functions import complex_exp
from ..implementations.scalar_functions import scalar_exp
from .create_overload import unary_overload

exp = unary_overload("exp", "Exp", scalar_exp, complex_exp)
