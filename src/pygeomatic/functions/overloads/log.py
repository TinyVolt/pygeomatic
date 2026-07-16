"""Mirror of overloads/log.ts: Scalar | Complex natural logarithm."""

from ..implementations.complex_functions import complex_log
from ..implementations.scalar_functions import scalar_log
from .create_overload import unary_overload

log = unary_overload("log", "Log", scalar_log, complex_log)
