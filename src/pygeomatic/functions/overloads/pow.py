"""Mirror of overloads/pow.ts: Scalar | Complex power.

Exported as `pow_` (trailing underscore) to avoid shadowing the builtin; the
DSL keyword is still `pow`.
"""

from ..implementations.complex_functions import complex_power
from ..implementations.scalar_functions import scalar_power
from .create_overload import binary_overload

pow_ = binary_overload("pow", "Power", scalar_power, complex_power)
