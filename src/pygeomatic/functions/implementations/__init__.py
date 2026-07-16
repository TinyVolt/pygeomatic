"""Implementation barrel (mirror of implementations/index.ts).

Importing the modules registers every function; the order matches the TS
barrel's docs order.
"""

from . import (  # noqa: F401
    basic_figures,
    planar_geometry,
    intersections,
    curve_functions,
    polygons,
    tangent_functions,
    scalar_functions,
    complex_functions,
    tensor_functions,
    array,
    translation_functions,
    rotation_functions,
    autograd_functions,
    boolean_functions,
    special_functions,
    ode_functions,
    annotation_functions,
    property_functions,
)

implementation_modules = [
    basic_figures,
    planar_geometry,
    intersections,
    curve_functions,
    polygons,
    tangent_functions,
    scalar_functions,
    complex_functions,
    tensor_functions,
    array,
    translation_functions,
    rotation_functions,
    autograd_functions,
    boolean_functions,
    special_functions,
    ode_functions,
    annotation_functions,
    property_functions,
]
