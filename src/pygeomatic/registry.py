"""Function registration + the recording decorator.

`@geomatic_fn(...)` welds a Python implementation to its geomatic command:
the decorator resolves the call's arguments to DSL argument tokens, appends
one `Command` to the active store's tape, allocates the output id (mirroring
the DSL's auto-naming), and wraps the numeric result in a typed node.

Public functions take their DSL parameters *positionally* plus an optional
`out="my-id"` keyword for an explicit output id (the `out = \\fn ...` form).
Without `out=`, a simple assignment target names the output instead —
`p = gm.point(3, 4)` emits `p = \\point 3 4` (see inference.py); otherwise
the id is auto-generated.

Argument coercions (each keeps emission deterministic):
- a GNode        → its id / `base.prop` reference
- an int/float   → a numeric literal token
- a str  (Text param)  → an implicit `\\text "..."` command is recorded first
- a str  (any other param) → a node REFERENCE by id: the existing node under
  that id, or — for Point/Scalar params — a fresh auto-created node (engine
  parity: CommandExecutor.createAndSaveNode), so `gm.line("a", "b")` works on
  ids that were never defined
- a bool (Bool param)  → an implicit `\\bool 1|0` command is recorded first
(`\\text` itself takes the quoted string directly — the DSL's only quoted form.)
"""

from __future__ import annotations

import random
import re
import sys
from dataclasses import dataclass, field as dc_field
from functools import wraps
from typing import Any, Callable, Optional, Sequence

import numpy as np

from .coercions import NODE_COERCIONS, VALUE_COERCIONS, coerce_gnode, coercions_enabled
from .functions.helpers import broadcast_shapes, flat_to_nd, nd_to_flat_clamped
from .inference import infer_out_names
from .nodes import Array, Bool, Dummy, GNode, Point, Scalar, Text, _infix_call

# Variadic + associative commands whose anonymous infix intermediates may be
# folded into one line (`d = a + b + c` → `d = \add a b c`).
_FUSABLE_KEYWORDS = frozenset({"add", "mul"})
from .store import (
    ArgToken,
    Store,
    TextLit,
    UnresolvedId,
    _auto_create_enabled,
    current_store,
    sanitize_text,
)


class _Unset:
    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()


@dataclass(frozen=True)
class P:
    """One DSL parameter (mirror of ParameterDefinition in GeometricFunction.ts)."""

    name: str
    type: str
    variadic: bool = False
    default: Any = UNSET

    @property
    def has_default(self) -> bool:
        return not isinstance(self.default, _Unset)


@dataclass
class FunctionDef:
    keyword: str
    name: str
    params: list[P]
    output_type: str
    category: str
    is_imperative: bool = False
    is_async: bool = False
    is_macro: bool = False
    operand_types: Optional[list[str]] = None
    # Whether an Array argument makes this function run element-wise. Mirrors
    # each TS implementation's `tryBroadcast(inner, inputs) ?? inner(inputs)`
    # (declarative) or `applyImperativeBroadcast` (imperative) opt-in.
    broadcasts: bool = True
    py_func: Optional[Callable] = dc_field(default=None, repr=False)


REGISTRY: dict[str, FunctionDef] = {}


# ---------------------------------------------------------------------------
# Argument binding
# ---------------------------------------------------------------------------

# Parameter types a bare numeric literal may fill (CommandExecutor.ts lines
# 166-176): Scalar/Any create a scalar node, Text stringifies it.
_NUMERIC_PARAM_TYPES = frozenset({"Scalar", "Any", "Text"})

# Gradient nodes dispatch as their payload type (mirrors Node.ts dispatchType).
_DISPATCH_TYPE = {"ScalarGradient": "Scalar", "PointGradient": "Point"}


def _resolve_gnode(fdef: FunctionDef, p: P, arg: GNode) -> list[tuple[ArgToken, Any]]:
    """Resolve a node argument for a `p.type` slot into (token, value) pairs.

    Mirrors CommandExecutor.ts: `Any` takes anything and an exact type match
    passes. An `Array` arg passes a non-Array param when its element type
    matches (broadcasting) or is value-coercible (type-coercion.ts
    `canCoerceValue`) — one token either way. The cross-type NODE coercions
    (`coerceNode`) may instead REPLACE the argument with several: a Point in a
    Scalar slot becomes its (x, y) scalars, consuming two parameter slots
    exactly as the executor advances `paramIndex` by `coercedIds.length`.
    Coercions are on by default; `allow_coercions(False)` forces strict
    exact-type matching.
    """
    node_type = _DISPATCH_TYPE.get(arg.type, arg.type)
    element_type = getattr(arg, "_element_type", None)
    element_type = _DISPATCH_TYPE.get(element_type, element_type) if element_type else element_type
    if p.type == "Any" or node_type == p.type:
        return [(arg.ref, arg)]
    # A node whose type pygeomatic could not determine satisfies every slot.
    # Rejecting it would be a type error invented from missing values, and the
    # emitted DSL is identical either way — the engine does the real checking.
    if node_type == "Unknown":
        return [(arg.ref, arg)]
    if node_type == "Array":
        if element_type is None or element_type == p.type or (
            coercions_enabled() and (element_type, p.type) in VALUE_COERCIONS
        ):
            return [(arg.ref, arg)]
    elif coercions_enabled() and (node_type, p.type) in NODE_COERCIONS:
        return coerce_gnode(arg, node_type, p.type)
    got = f"{arg.type}<{element_type}>" if arg.type == "Array" else arg.type
    raise TypeError(
        f"\\{fdef.keyword}: parameter '{p.name}' expects {p.type}, got a {got} node"
    )


def _default_value(fdef: FunctionDef, p: P, store: Store) -> Any:
    """A parameter's default, as the BODY should see it.

    Numeric and Text defaults are values. A string default on any other
    parameter type is a NODE ID (`\\circle`'s `center="p0"`, `\\distance`'s
    `point2="p0"`) and must be resolved to that node — the engine resolves
    defaults through the same path as supplied arguments
    (CommandExecutor.getInputNodeIds), and every such default in the registry
    names `p0`, which every store seeds.
    """
    if isinstance(p.default, str) and p.type != "Text":
        return _deref_name(fdef, p, p.default, store)
    return p.default


# Node types a missing id may be auto-created as (CommandExecutor.ts
# createAndSaveNode: Point / Scalar / Text only).
_AUTO_CREATE_TYPES = frozenset({"Point", "Scalar", "Text"})

# The engine draws random payloads scaled by the live canvas bounds, capped at
# 4 world units for scalars and 6 for point coordinates (createAndSaveScalar /
# createAndSavePoint). pygeomatic has no canvas, so it uses the caps: a scalar
# in [0, 2), point coordinates in [-3, 3).
_AUTO_SCALAR_SPAN = 4.0
_AUTO_POINT_SPAN = 6.0


def _auto_create(name: str, node_type: str, store: Store) -> GNode:
    """Create + register the node a missing id refers to, mirroring the
    engine's createAndSavePoint/Scalar/Text: random payload for Point/Scalar,
    the id itself as a Text's value. Registered in the store but NOT recorded
    on the tape — emitted DSL references the bare id and the engine
    auto-creates it again on replay, exactly as the TS executor does."""
    if node_type == "Point":
        node: GNode = Point._new(
            (random.random() - 0.5) * _AUTO_POINT_SPAN,
            (random.random() - 0.5) * _AUTO_POINT_SPAN,
        )
    elif node_type == "Scalar":
        node = Scalar._new(random.random() * 0.5 * _AUTO_SCALAR_SPAN)
    else:
        node = Text._new(name)
    node_id = store.allocate_id(node_type, name)  # validates + reserves the id
    return store.register(node, node_id)


def _deref_name(fdef: FunctionDef, p: P, arg: Any, store: Store) -> Any:
    """Resolve a string node-reference — or parse.py's UnresolvedId — to a live
    node (CommandExecutor.getInputNodeIds): the existing node under that id,
    else an auto-created Point/Scalar/Text. A plain str filling a Text
    parameter keeps its value semantics (implicit `\\text "..."`) and is left
    for `_resolve_arg`; only parse-replay auto-creates Text by id. Anything
    that isn't a name passes through unchanged."""
    if isinstance(arg, UnresolvedId):
        name = arg.name
    elif isinstance(arg, str) and p.type != "Text":
        name = arg
    else:
        return arg
    found = store.nodes.get(name)
    if found is not None:
        return found
    if not _auto_create_enabled.get():
        raise TypeError(
            f"unknown node id {name!r} — define-before-use is enforced here"
        )
    if p.type not in _AUTO_CREATE_TYPES:
        raise TypeError(
            f"\\{fdef.keyword}: parameter '{p.name}' expects {p.type}; node "
            f"{name!r} does not exist and {p.type} cannot be auto-created "
            "(only Point, Scalar and Text can)"
        )
    return _auto_create(name, p.type, store)


# A gm.ui span, as `render_widget_html` writes it: `class`, `data-kind` and
# `data-node` are always first and always unescaped, so this stays a simple
# pattern. Readouts and controls both match — both carry `data-node`.
_UI_SPAN_RE = re.compile(
    r'<span class="nova-ui" data-kind="[^"]*" data-node="([a-zA-Z][a-zA-Z0-9-]*)"[^>]*></span>'
)


def _spans_to_interpolation(value: str) -> str:
    """Turn gm.ui spans in canvas text into the canvas's own `${node}` form.

    `GNode.__format__` builds a readout span wherever a value node is
    interpolated, which is right for prose but not for `gm.text`: the canvas
    draws plain text and would paint the markup literally. It has its own live
    interpolation, so translate rather than reject —

        gm.text(f"scale = {x}")  ==  gm.text("scale = ${x}")

    both emit `\\text "scale = ${x}"` and both track `x` on the canvas.

    A number format is lost on the way (`${}` has no format spec): the canvas
    prints integers plain and everything else to 2 dp.
    """
    return _UI_SPAN_RE.sub(r"${\g<1>}", value)


def _implicit_text(value: str, store: Store) -> Text:
    node = Text._new(value)
    node_id = store.allocate_id("Text", None)
    store.register(node, node_id)
    store.record("text", [TextLit(value)], node_id)
    return node


def _implicit_bool(value: bool, store: Store) -> Bool:
    node = Bool._new(value)
    node_id = store.allocate_id("Bool", None)
    store.register(node, node_id)
    store.record("bool", [1 if value else 0], node_id)
    return node


def _resolve_arg(fdef: FunctionDef, p: P, arg: Any, store: Store) -> tuple[ArgToken, Any]:
    """Returns (token for the tape, value passed to the numeric body).

    Node arguments go through `_resolve_gnode` in `_bind` (they may expand into
    several tokens); this handles the single-token literal kinds.
    """
    if isinstance(arg, bool):  # before int: bool is an int subclass
        if p.type == "Bool":
            node = _implicit_bool(arg, store)
            return node.ref, node
        if p.type == "Any":
            # A bare Python bool in an untyped slot is just its 0/1 value (bool
            # is an int subclass), like passing 1/0 — e.g. `gm.bool_(True)`
            # records `\bool 1`. Scalar/Text params stay strict (they reject a
            # bool below), so this only relaxes genuinely untyped parameters.
            return int(arg), int(arg)
        raise TypeError(
            f"\\{fdef.keyword}: parameter '{p.name}' expects {p.type}, got bool"
        )
    if isinstance(arg, (int, float)):
        if p.type not in _NUMERIC_PARAM_TYPES:
            raise TypeError(
                f"\\{fdef.keyword}: parameter '{p.name}' expects {p.type}, "
                "cannot use a numeric literal"
            )
        return arg, arg
    if isinstance(arg, str):
        if p.type == "Text":
            # The DSL is line-based and SVG <text> is single-line: newlines
            # can neither be emitted nor rendered, so collapse them now (the
            # node's value must match what goes on the tape).
            arg = _spans_to_interpolation(sanitize_text(arg))
            if fdef.keyword == "text":
                return TextLit(arg), arg
            node = _implicit_text(arg, store)
            return node.ref, node
        raise TypeError(
            f"\\{fdef.keyword}: parameter '{p.name}' expects {p.type}, got str "
            "(strings are only valid for Text parameters)"
        )
    raise TypeError(
        f"\\{fdef.keyword}: parameter '{p.name}' got unsupported argument "
        f"{type(arg).__name__!r}; pass a pygeomatic node or a number"
    )


@dataclass
class _Resolved:
    """A slot already resolved to its tape token + body value (a node argument,
    possibly one piece of a multi-slot coercion expansion)."""

    token: ArgToken
    value: Any


def _bind(
    fdef: FunctionDef, args: tuple, kwargs: dict, store: Store
) -> tuple[list[ArgToken], list[Any]]:
    """Map positional/keyword python args to (tape tokens, values for the body).

    The body receives exactly len(params) values; a variadic last parameter is
    passed as a list. Keyword arguments are matched to parameter names, so a
    caller can leave an optional *middle* parameter at its default while
    supplying a later one (`annotate_text_box(t, p, width=0, height=0)` keeps
    fontSize=14). Because the DSL tape is positional, a defaulted parameter that
    sits *before* a supplied one is materialised as an explicit token (its
    literal default) rather than omitted; only trailing optionals stay off the
    tape. A node-id default like 'p0' can't be materialised, so filling past
    such a parameter by keyword is rejected — pass it positionally.

    Node arguments are resolved as they are placed (resolution is pure): a
    node coercion may expand one python argument into several tape tokens,
    each consuming its own parameter slot (a Point in a Scalar slot fills both
    x and y), mirroring CommandExecutor.ts advancing `paramIndex` by
    `coercedIds.length`. Literal arguments stay raw until the final pass so
    implicit `\\text`/`\\bool` commands are recorded in parameter order.
    """
    params = fdef.params
    variadic = bool(params) and params[-1].variadic
    max_fixed = len(params) - 1 if variadic else len(params)

    args = list(args)
    # Strip trailing Nones (explicitly omitted optionals).
    while args and args[-1] is None:
        args.pop()
    if any(a is None for a in args):
        raise TypeError(
            f"\\{fdef.keyword}: cannot omit an earlier parameter (None) while "
            "providing later ones — pass it by keyword instead"
        )
    if not variadic and len(args) > len(params):
        raise TypeError(
            f"\\{fdef.keyword} takes at most {len(params)} argument(s), got {len(args)}"
        )

    # Positional args fill fixed slots first (a coerced node fills as many
    # slots as it expands to); overflow feeds the variadic tail.
    slots: list[Any] = [UNSET] * max_fixed
    rest: list[Any] = []
    idx = 0
    for a in args:
        if idx >= max_fixed:
            rest.append(a)
            continue
        a = _deref_name(fdef, params[idx], a, store)
        if isinstance(a, GNode):
            pieces = _resolve_gnode(fdef, params[idx], a)
            for tok, val in pieces:
                if idx < max_fixed:
                    slots[idx] = _Resolved(tok, val)
                    idx += 1
                elif variadic:
                    rest.append(_Resolved(tok, val))
                else:
                    raise TypeError(
                        f"\\{fdef.keyword} takes at most {len(params)} argument(s) "
                        "after coercion"
                    )
        else:
            slots[idx] = a
            idx += 1

    name_to_index = {p.name: i for i, p in enumerate(params[:max_fixed])}
    for key, val in kwargs.items():
        if key not in name_to_index:
            if variadic and params[-1].name == key:
                raise TypeError(
                    f"\\{fdef.keyword}: variadic parameter '{key}' takes positional values only"
                )
            raise TypeError(f"\\{fdef.keyword}: unknown parameter '{key}'")
        idx = name_to_index[key]
        val = _deref_name(fdef, params[idx], val, store)
        pieces = (
            _resolve_gnode(fdef, params[idx], val)
            if isinstance(val, GNode)
            else [None]  # literal: fills one slot, resolved in the final pass
        )
        for j, piece in enumerate(pieces):
            if idx + j >= max_fixed:
                raise TypeError(
                    f"\\{fdef.keyword}: coerced argument for '{key}' overflows the "
                    "parameter list"
                )
            if slots[idx + j] is not UNSET:
                raise TypeError(
                    f"\\{fdef.keyword}: parameter '{params[idx + j].name}' given by "
                    "both position and keyword"
                )
            slots[idx + j] = val if piece is None else _Resolved(*piece)

    # A defaulted hole before the last supplied fixed slot (or before variadic
    # values) must emit its literal default; trailing holes stay off the tape.
    provided = [i for i, s in enumerate(slots) if s is not UNSET]
    last_required = (max_fixed - 1) if rest else (max(provided) if provided else -1)

    tokens: list[ArgToken] = []
    bound: list[Any] = []

    for i in range(max_fixed):
        p = params[i]
        if isinstance(slots[i], _Resolved):
            tokens.append(slots[i].token)
            bound.append(slots[i].value)
        elif slots[i] is not UNSET:
            tok, val = _resolve_arg(fdef, p, slots[i], store)
            tokens.append(tok)
            bound.append(val)
        elif not p.has_default:
            raise TypeError(f"\\{fdef.keyword}: missing required parameter '{p.name}'")
        elif i <= last_required:
            # Hole before a supplied arg: the tape is positional, so the default
            # must go on it explicitly. Only true literal defaults can be
            # emitted — a str default is a node id ('p0') unless the param is
            # Text, so those are rejected.
            emittable = isinstance(p.default, (int, float)) or (
                isinstance(p.default, str) and p.type == "Text"
            )
            if not emittable:
                raise TypeError(
                    f"\\{fdef.keyword}: cannot leave '{p.name}' at its default while "
                    "supplying a later parameter by keyword — pass it positionally"
                )
            tok, val = _resolve_arg(fdef, p, p.default, store)
            tokens.append(tok)
            bound.append(val)
        else:
            # Trailing omission → not on the tape; the engine applies the same
            # default. It still has to reach the BODY as the thing it names,
            # though: a node-id default ('p0') left as a bare string made every
            # implementation see a str where it expected a node and quietly
            # compute nothing — `gm.distance(p)` returned None instead of the
            # distance from the origin. Resolving here changes no emitted DSL,
            # since nothing is appended to `tokens`.
            bound.append(_default_value(fdef, p, store))

    if variadic:
        p = params[-1]
        # The engine accepts zero values for a variadic parameter (bare
        # `\gradient-descent-step` steps every param; the builtin
        # zero-back-step macro relies on it), so an empty tail is valid here too.
        vals = []
        for a in rest:
            if isinstance(a, _Resolved):
                tokens.append(a.token)
                vals.append(a.value)
                continue
            a = _deref_name(fdef, p, a, store)
            if isinstance(a, GNode):
                # A coerced node in the variadic tail contributes each of its
                # expanded pieces as a separate variadic value.
                for tok, val in _resolve_gnode(fdef, p, a):
                    tokens.append(tok)
                    vals.append(val)
            else:
                tok, val = _resolve_arg(fdef, p, a, store)
                tokens.append(tok)
                vals.append(val)
        bound.append(vals)

    return tokens, bound


# ---------------------------------------------------------------------------
# Broadcasting (mirror of functions/broadcasting.ts)
# ---------------------------------------------------------------------------


def _flatten_bound(fdef: FunctionDef, bound: list) -> list:
    """The bound arguments as a flat list. A variadic function's tail arrives as
    a single list in the last slot."""
    if fdef.params and fdef.params[-1].variadic and bound and isinstance(bound[-1], list):
        return [*bound[:-1], *bound[-1]]
    return list(bound)


def _rebuild_bound(fdef: FunctionDef, flat: list) -> list:
    """Inverse of `_flatten_bound`: re-nest the variadic tail."""
    if fdef.params and fdef.params[-1].variadic:
        fixed = len(fdef.params) - 1
        return [*flat[:fixed], list(flat[fixed:])]
    return list(flat)


def _slot_element(value, nd_idx, rank):
    """One broadcast slot's value: an Array contributes its clamped element,
    anything else passes through unchanged (broadcasting.ts:101-105)."""
    if not isinstance(value, Array):
        return value
    return value._elements[nd_to_flat_clamped(nd_idx, value._shape or (), rank)]


def _broadcast_plan(fdef: FunctionDef, bound: list):
    """(flat args, array args, out_shape) when this call broadcasts, else None.

    Mirrors `tryBroadcast`'s entry test: ANY Array input triggers it, whatever
    the declared parameter type — an Array in a Scalar slot included.
    """
    if not fdef.broadcasts:
        return None
    flat = _flatten_bound(fdef, bound)
    arrays = [v for v in flat if isinstance(v, Array)]
    if not arrays:
        return None
    return flat, arrays, broadcast_shapes([a._shape for a in arrays])


def _unknown_broadcast_result(fdef: FunctionDef, out_shape) -> Array:
    """The output when its shape or its elements are unknown: record the
    command, keep whatever shape we do have, invent nothing."""
    element_type = fdef.output_type if fdef.output_type not in ("Any", "Dummy") else None
    return Array._new(
        element_type=element_type,
        elements=[],
        shape=out_shape,
        shape_unknown=out_shape is None,
    )


def _try_broadcast(fdef: FunctionDef, fn: Callable, bound: list) -> Optional[GNode]:
    """Run `fn` once per element over the broadcast shape, assembling an Array.

    Mirror of `tryBroadcast` (broadcasting.ts:83) — including that the element
    type comes from the FIRST element's result rather than `fdef.output_type`.

    `fn` is the raw implementation, never another command's wrapper, so calling
    it per element records nothing on the tape: the implementations reach for
    module-private helpers (`_project`, `_line_intersection`, …) rather than
    registered functions. That is what makes per-element evaluation safe.
    """
    plan = _broadcast_plan(fdef, bound)
    if plan is None:
        return None
    flat, arrays, out_shape = plan

    # No shape, or an Array whose elements Python does not have (a record-only
    # extension output): there is nothing to iterate over.
    if out_shape is None or any(len(a._elements) != a._length() for a in arrays):
        return _unknown_broadcast_result(fdef, out_shape)

    rank = len(out_shape)
    total = int(np.prod(out_shape)) if out_shape else 1
    elements: list[GNode] = []
    for k in range(total):
        nd_idx = flat_to_nd(k, out_shape)
        args = [_slot_element(v, nd_idx, rank) for v in flat]
        result = fn(*_rebuild_bound(fdef, args))
        if not isinstance(result, GNode):
            raise TypeError(
                f"\\{fdef.keyword}: implementation must return a node to broadcast, "
                f"got {type(result)!r}"
            )
        elements.append(result)

    element_type = elements[0].type if elements else fdef.output_type
    return Array._new(element_type=element_type, elements=elements, shape=out_shape)


class _NotBroadcast:
    """Sentinel: this call did not broadcast, so run `fn` normally."""


def _try_imperative_broadcast(fdef: FunctionDef, fn: Callable, bound: list):
    """Mirror of `applyImperativeBroadcast` (broadcasting.ts:197).

    Calls `fn` once per broadcast slot for its side effects. Unlike the
    declarative version this builds NO Array — the engine returns early with a
    dummy and the mutated nodes are the whole point.

    Returns `_NotBroadcast` when there was nothing to broadcast. Otherwise it
    returns the node this command should hand back: pygeomatic's mutating
    commands (`\\rotate`, `\\translate`) return the object they mutated, which
    shows up as the implementation returning its own first argument — so return
    the whole Array in that case, and the last per-element result (a Dummy, for
    the record-only stubs) in every other.
    """
    plan = _broadcast_plan(fdef, bound)
    if plan is None:
        return _NotBroadcast
    flat, arrays, out_shape = plan
    first = bound[0] if bound else None
    if out_shape is None or any(len(a._elements) != a._length() for a in arrays):
        # Nothing to iterate over here; the engine still mutates the real
        # elements, and the command is recorded either way.
        return first if isinstance(first, GNode) else fn(*bound)

    rank = len(out_shape)
    result = None
    returned_its_argument = False
    for k in range(int(np.prod(out_shape)) if out_shape else 1):
        nd_idx = flat_to_nd(k, out_shape)
        args = _rebuild_bound(fdef, [_slot_element(v, nd_idx, rank) for v in flat])
        result = fn(*args)
        returned_its_argument = bool(args) and result is args[0]
    if returned_its_argument and isinstance(first, GNode):
        return first
    return result if isinstance(result, GNode) else Dummy._new()


# ---------------------------------------------------------------------------
# The decorator
# ---------------------------------------------------------------------------


def geomatic_fn(
    *,
    keyword: str,
    name: str,
    output: str,
    params: Sequence[P],
    category: str,
    imperative: bool = False,
    is_async: bool = False,
    assigns_output: Optional[bool] = None,
    operand_types: Optional[list[str]] = None,
    broadcasts: Optional[bool] = None,
    pre_broadcast: Optional[Callable] = None,
    register: bool = True,
):
    """Register a geomatic command mirror.

    `assigns_output` overrides the default "declarative commands get an output
    id, imperative ones don't" (e.g. `\\copy` is imperative but assigns).

    `broadcasts` overrides the default "declarative commands run element-wise
    over an Array argument, imperative ones don't". In the engine every
    declarative implementation opts in with
    `tryBroadcast(inner, inputs) ?? inner(inputs)`; the exceptions are the
    operations defined over a whole array (`\\array`, `\\get-array-element`,
    `\\fft`, `\\ifft`, `\\filter` and everything in tensor-functions.ts), which
    pass `broadcasts=False`. Five imperative commands DO broadcast via
    `applyImperativeBroadcast` and pass `broadcasts=True`.

    `pre_broadcast` validates the arguments BEFORE any slicing happens, for the
    checks the engine deliberately runs outside its `tryBroadcast` call — see
    `\\partial`, whose target must be rejected as a whole rather than sliced
    into scalars (autograd-functions.ts:126-133).
    """
    assigns = (not imperative) if assigns_output is None else assigns_output
    does_broadcast = (not imperative) if broadcasts is None else broadcasts

    def deco(fn: Callable) -> Callable:
        fdef = FunctionDef(
            keyword=keyword,
            name=name,
            params=list(params),
            output_type=output,
            category=category,
            is_imperative=imperative,
            is_async=is_async,
            operand_types=operand_types,
            broadcasts=does_broadcast,
        )

        @wraps(fn)
        def wrapper(*args, out: Optional[str] = None, **kwargs):
            store = current_store()
            tokens, bound = _bind(fdef, tuple(args), kwargs, store)
            if pre_broadcast is not None:
                pre_broadcast(*bound)
            if imperative:
                result = _try_imperative_broadcast(fdef, fn, bound)
                if result is _NotBroadcast:
                    result = fn(*bound)
            else:
                result = _try_broadcast(fdef, fn, bound)
                if result is None:
                    result = fn(*bound)
            if assigns:
                node = result if isinstance(result, GNode) else None
                if node is None:
                    raise TypeError(
                        f"\\{keyword} implementation must return a node, got {type(result)!r}"
                    )
                if node.type == "Dummy":
                    # Degenerate result (e.g. no intersection): the engine
                    # produces a Dummy, which is never assigned an id.
                    store.record(keyword, tokens, None)
                    return node
                extra_ids: list[str] = []
                if out is None:
                    inferred = infer_out_names(sys._getframe(1), store)
                    if inferred:
                        # chained `a = b = call(...)`: first name goes to the
                        # node, each extra gets its own cloned command below
                        out, extra_ids = inferred[0], inferred[1:]
                infix = _infix_call.get()
                if infix and keyword in _FUSABLE_KEYWORDS:
                    tokens = store.fuse_variadic(keyword, tokens)
                node_id = store.allocate_id(node.type, out)
                store.register(node, node_id)
                store.record(
                    keyword,
                    tokens,
                    node_id,
                    fusable=infix and out is None and keyword in _FUSABLE_KEYWORDS,
                )
                for extra in extra_ids:
                    clone = node.model_copy()
                    clone_id = store.allocate_id(clone.type, extra)
                    store.register(clone, clone_id)
                    store.record(keyword, list(tokens), clone_id)
                return node
            store.record(keyword, tokens, None)
            return result

        fdef.py_func = wrapper
        wrapper.geomatic = fdef  # type: ignore[attr-defined]
        if register:
            if keyword in REGISTRY:
                raise ValueError(f"duplicate geomatic keyword {keyword!r}")
            REGISTRY[keyword] = fdef
        return wrapper

    return deco
