"""Mirror of overloads/abs.ts: Scalar | Complex absolute value.

|z| of a Complex is a Scalar. Exported as `abs_` (trailing underscore) to
avoid shadowing the builtin; the DSL keyword is still `abs`.
"""

from ..implementations.complex_functions import complex_abs
from ..implementations.scalar_functions import scalar_abs
from .create_overload import unary_overload

abs_ = unary_overload("abs", "Abs", scalar_abs, complex_abs, complex_out="Scalar")
