"""pygeomatic — Python mirror of the geomatic DSL function library.

Every public function maps 1:1 to a geomatic command (dashes become
underscores: `reduce-sum` → `reduce_sum`). Calls compute numeric values where
possible AND record onto the active Store's tape; `emit()` turns the tape into
geomatic DSL lines. `abs`/`pow`/`min`/`max`/`round`/... that would shadow
Python builtins get a trailing underscore.

Example:
    import pygeomatic as gm

    with gm.Store() as s:
        a = gm.point(1, 2, out="a")
        b = gm.point(4, 6)
        d = gm.distance(a, b)
        gm.highlight(a, b)
        print(gm.emit(s))
"""

from .article import (  # noqa: F401
    ArticleError,
    ArticleResult,
    article_mode,
    compile_article,
    run_article,
)
from .coercions import allow_coercions, coercions_enabled  # noqa: F401
from .emit import emit, render_command, render_token  # noqa: F401
from .extensions import (  # noqa: F401
    ManifestError,
    load_extensions,
    loaded_extensions,
    unload_extensions,
)
from .generate import (  # noqa: F401
    GenerateResult,
    GenerationError,
    extract_code,
    generate_dsl,
)
from .macros import (  # noqa: F401
    BUILTIN_SOURCE,
    MacroDef,
    MacroError,
    load_builtin_macros,
    load_macros,
    loaded_macros,
    unload_macros,
)
from .palette import ColorPalette, build_palette, color_ids, load_colors  # noqa: F401
from .parse import DslParseError, parse_dsl  # noqa: F401
from .prompting import python_name, system_prompt  # noqa: F401
from .runner import RunResult, run_generated  # noqa: F401
from .nodes import (  # noqa: F401
    AngleMark,
    Arc,
    Array,
    Arrow,
    BezierCubic,
    BezierQuadratic,
    Bool,
    Circle,
    Complex,
    CurlyBracket,
    CurvedArrow,
    DimensionLine,
    Dummy,
    Ellipse,
    GNode,
    IdRef,
    LeaderLine,
    Line,
    NODE_CLASSES,
    NODE_PROPERTIES,
    Pin,
    Plot,
    Point,
    PointGradient,
    Polygon,
    Polynomial,
    PropRef,
    RegularPolygon,
    Scalar,
    ScalarGradient,
    Text,
    TextBox,
    Trail,
    Trajectory,
    Triangle,
    VectorField,
)
from .registry import REGISTRY, FunctionDef, P  # noqa: F401
from .store import (  # noqa: F401
    Command,
    Store,
    TextLit,
    current_store,
    node,
    reset_default_store,
)
from .system_nodes import (  # noqa: F401
    SYSTEM_NODE_ATTRS,
    SYSTEM_NODE_IDS,
    SYSTEM_NODES,
    SystemNode,
    register_system_nodes,
)
from .tex import (  # noqa: F401
    SCHEMA,
    AxisExpr,
    Selector,
    Tex,
    TexError,
    cols,
    dim,
    harvest_tex_bindings,
    register_tex_schema,
    rows,
    tex,
)


def __getattr__(name: str) -> GNode:
    # System defaults are per-Store instances (and reassignable, last-write-
    # wins), so `gm.p0` / `gm.learning_rate` must resolve against the ACTIVE
    # store at access time rather than bind one instance at import.
    node_id = SYSTEM_NODE_ATTRS.get(name)
    if node_id is not None:
        return current_store().nodes[node_id]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list:
    return sorted(set(globals()) | set(SYSTEM_NODE_ATTRS))

# Import the barrels for their registration side effects, then re-export the
# public callables.
from .functions import implementations as _implementations  # noqa: F401
from .functions import overloads as _overloads  # noqa: F401

from .functions.implementations.basic_figures import (  # noqa: F401
    arc,
    bezier_cubic,
    bezier_quadratic,
    circle,
    ellipse,
    ellipse_from_foci,
    line,
    point,
    scalar,
    text,
    triangle,
)
from .functions.implementations.planar_geometry import (  # noqa: F401
    angle,
    area_circle,
    area_triangle,
    bisect_angle,
    centroid,
    circumcenter,
    distance,
    incenter,
    mid_point,
    project_point,
    reflect_point,
    slope_of_line,
)
from .functions.implementations.intersections import (  # noqa: F401
    intersection_circle_circle,
    intersection_line_bezier_quadratic,
    intersection_line_circle,
    intersection_line_ellipse,
    intersection_line_line,
)
from .functions.implementations.curve_functions import (  # noqa: F401
    clear_trail,
    evaluate_polynomial,
    plot,
    plot_inverse,
    polynomial,
    trail,
)
from .functions.implementations.polygons import (  # noqa: F401
    convex_hull,
    polygon,
    polygon_from_side,
    polyline,
    rectangle,
    regular_polygon,
    square,
)
from .functions.implementations.tangent_functions import tangent  # noqa: F401
from .functions.implementations.scalar_functions import (  # noqa: F401
    acos,
    asin,
    atan,
    atan2,
    ceil,
    cos,
    deg2rad,
    floor,
    log10,
    max_,
    min_,
    mod,
    rad2deg,
    reciprocal,
    relu,
    round_,
    sigmoid,
    sign,
    sin,
    tan,
    tanh,
    x_coord,
    y_coord,
)
from .functions.implementations.complex_functions import (  # noqa: F401
    arg,
    complex_,
    conj,
    fft,
    ifft,
    imag,
    real,
)
from .functions.implementations.tensor_functions import (  # noqa: F401
    arange,
    circular_arange,
    cumsum,
    linspace,
    ones,
    ones_like,
    reduce_max,
    reduce_mean,
    reduce_min,
    reduce_std,
    reduce_sum,
    reduce_var,
    reshape,
    softmax,
    zeros,
    zeros_like,
)
from .functions.implementations.array import array, get_array_element  # noqa: F401
from .functions.implementations.translation_functions import (  # noqa: F401
    animate,
    translate,
    translate_array,
)
from .functions.implementations.rotation_functions import rotate  # noqa: F401
from .functions.implementations.autograd_functions import (  # noqa: F401
    backprop,
    gradient_descent_step,
    minimize,
    param,
    partial,
    reevaluate,
    vector_field,
    zero_grad,
)
from .functions.implementations.boolean_functions import (  # noqa: F401
    and_,
    bin_to_dec_ones_complement,
    bin_to_dec_twos_complement,
    bin_to_dec_unsigned,
    bool_,
    eq,
    filter_,
    fp_to_bin,
    ge,
    gt,
    int_to_bin,
    le,
    lt,
    not_,
    or_,
    uint_to_bin,
    xor,
)
from .functions.implementations.special_functions import (  # noqa: F401
    clear,
    copy,
    help_,
    hide,
    highlight,
    remove,
    set_fill,
    set_stroke,
    show,
)
from .functions.implementations.ode_functions import (  # noqa: F401
    eval_ode,
    flow,
    simulate_sde,
    solve_ode,
)
from .functions.implementations.annotation_functions import (  # noqa: F401
    annotate_angle_mark,
    annotate_arrow,
    annotate_curly_bracket,
    annotate_curved_arrow,
    annotate_dim_line,
    annotate_leader_line,
    annotate_pin,
    annotate_text_box,
)
from .functions.overloads import (  # noqa: F401
    abs_,
    add,
    div,
    exp,
    log,
    mul,
    neg,
    pow_,
    sqrt,
    sub,
)

# The builtin macros (public/geomatic/macros/geometry.json, shipped as
# pygeomatic/macros.json) are auto-loaded like the interactive editor does —
# after everything above, so builtin-keyword collisions are detectable and
# existing gm attributes (gm.load_colors) are never clobbered.
load_builtin_macros()

# id → hex of the load-colors macro, derived (not hardcoded) from the macro
# body — hence built only after the builtin macros are registered.
PALETTE: dict[str, str] = build_palette()
