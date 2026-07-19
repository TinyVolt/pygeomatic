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
import sys
from dataclasses import dataclass, field as dc_field
from functools import wraps
from typing import Any, Callable, Optional, Sequence

from .coercions import NODE_COERCIONS, VALUE_COERCIONS, coerce_gnode, coercions_enabled
from .inference import infer_out_names
from .nodes import Bool, GNode, Point, Scalar, Text, _infix_call

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
    if node_type == "Array":
        if element_type == p.type or (
            coercions_enabled() and (element_type, p.type) in VALUE_COERCIONS
        ):
            return [(arg.ref, arg)]
    elif coercions_enabled() and (node_type, p.type) in NODE_COERCIONS:
        return coerce_gnode(arg, node_type, p.type)
    got = f"{arg.type}<{element_type}>" if arg.type == "Array" else arg.type
    raise TypeError(
        f"\\{fdef.keyword}: parameter '{p.name}' expects {p.type}, got a {got} node"
    )


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
            arg = sanitize_text(arg)
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
            # default. Node-id defaults ('p0') reach the body as the raw string.
            bound.append(p.default)

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
    register: bool = True,
):
    """Register a geomatic command mirror.

    `assigns_output` overrides the default "declarative commands get an output
    id, imperative ones don't" (e.g. `\\copy` is imperative but assigns).
    """
    assigns = (not imperative) if assigns_output is None else assigns_output

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
        )

        @wraps(fn)
        def wrapper(*args, out: Optional[str] = None, **kwargs):
            store = current_store()
            tokens, bound = _bind(fdef, tuple(args), kwargs, store)
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
