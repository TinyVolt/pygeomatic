"""gm.cond — conditions over store nodes, for gating markdown with gm.when.

A condition is pure configuration: a small JSON tree naming nodes and constants,
recorded into the article and evaluated in the browser whenever one of those
nodes changes. It records no DSL and has no engine command behind it.

    show = gm.ui.checkbox(False, label="Show the proof")
    with gm.when(show):
        gm.md("Because $ab=ba$, the map commutes.")

    with gm.when(gm.cond.ge(k, 2)):
        gm.md("Now the second eigenvector matters.")

**Why a `gm.cond` namespace instead of `k >= 2`.** Overloading comparison
operators on nodes would collide with geomatic's own comparison commands
(`\\gt`, `\\lt`, ...), which record DSL and return Bool nodes — the opposite of
what a condition is. Keeping them apart means `k >= 2` stays available for its
real meaning. `&`, `|` and `~` ARE overloaded, but only on `Cond` itself, which
is our own type and has no other reading.

The JSON shape is shared with the browser's `predicate.ts`; keep the two in
step.
"""

from __future__ import annotations

from typing import Union

from .nodes import GNode

Operand = Union[GNode, float, int, str, bool]

_ORDERED_OPS = ("ge", "gt", "le", "lt")


class CondError(ValueError):
    """A condition could not be built (bad operand or comparison)."""


class Cond:
    """A built condition. Combine with `&`, `|`, `~`; pass to `gm.when`."""

    __slots__ = ("payload",)

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __and__(self, other: "Cond") -> "Cond":
        return all_(self, other)

    def __or__(self, other: "Cond") -> "Cond":
        return any_(self, other)

    def __invert__(self) -> "Cond":
        return not_(self)

    def __bool__(self):
        raise CondError(
            "a condition cannot be used in a python `if` — it describes something "
            "the READER's browser decides, not something known while compiling. "
            "Use `with gm.when(...)`. For a compile-time branch, test the plain "
            "python value instead."
        )

    def __repr__(self) -> str:
        return f"Cond({self.payload!r})"


def _operand(value: Operand, where: str) -> dict:
    if isinstance(value, Cond):
        raise CondError(f"{where}: expected a node or a constant, got a condition")
    if isinstance(value, GNode):
        if not value.id:
            raise CondError(f"{where}: node has no id yet, so it cannot be referenced")
        return {"node": value.id}
    if isinstance(value, bool):
        return {"const": value}
    if isinstance(value, (int, float)):
        return {"const": float(value)}
    if isinstance(value, str):
        return {"const": value}
    raise CondError(f"{where}: unsupported operand {value!r}")


def _compare(op: str, a: Operand, b: Operand) -> Cond:
    left = _operand(a, f"gm.cond.{op}")
    right = _operand(b, f"gm.cond.{op}")
    if op in _ORDERED_OPS:
        for side in (left, right):
            if isinstance(side.get("const"), str):
                raise CondError(
                    f"gm.cond.{op} orders numbers; compare text with "
                    "gm.cond.eq / gm.cond.ne instead"
                )
    return Cond({"op": op, "a": left, "b": right})


def ge(a: Operand, b: Operand) -> Cond:
    """a >= b"""
    return _compare("ge", a, b)


def gt(a: Operand, b: Operand) -> Cond:
    """a > b"""
    return _compare("gt", a, b)


def le(a: Operand, b: Operand) -> Cond:
    """a <= b"""
    return _compare("le", a, b)


def lt(a: Operand, b: Operand) -> Cond:
    """a < b"""
    return _compare("lt", a, b)


def eq(a: Operand, b: Operand) -> Cond:
    """a == b (numbers, text or booleans)"""
    return _compare("eq", a, b)


def ne(a: Operand, b: Operand) -> Cond:
    """a != b (numbers, text or booleans)"""
    return _compare("ne", a, b)


def _fold(op: str, conds: tuple, name: str) -> Cond:
    if not conds:
        raise CondError(f"gm.cond.{name} needs at least one condition")
    built = []
    for c in conds:
        if not isinstance(c, Cond):
            raise CondError(f"gm.cond.{name}: expected conditions, got {c!r}")
        built.append(c.payload)
    folded = built[0]
    for nxt in built[1:]:
        folded = {"op": op, "a": folded, "b": nxt}
    return Cond(folded)


def all_(*conds: Cond) -> Cond:
    """Every condition holds."""
    return _fold("and", conds, "all_")


def any_(*conds: Cond) -> Cond:
    """At least one condition holds."""
    return _fold("or", conds, "any_")


def not_(c: Cond) -> Cond:
    """The condition does not hold."""
    if not isinstance(c, Cond):
        raise CondError(f"gm.cond.not_: expected a condition, got {c!r}")
    return Cond({"op": "not", "a": c.payload})


def to_payload(condition: Union[Cond, GNode]) -> dict:
    """The JSON for a condition, or for a bare node used as a truth gate."""
    if isinstance(condition, Cond):
        return condition.payload
    if isinstance(condition, GNode):
        if not condition.id:
            raise CondError("node has no id yet, so it cannot gate anything")
        if condition.type not in ("Bool", "Scalar"):
            raise CondError(
                f"a {condition.type} node cannot be a gate on its own — compare it, "
                f"e.g. gm.cond.eq({condition.id}, ...)"
            )
        return {"node": condition.id}
    raise CondError(
        f"gm.when() takes a Bool/Scalar node or a gm.cond condition, got {condition!r}"
    )


# ---------------------------------------------------------------------------
# Compile-time evaluation
# ---------------------------------------------------------------------------


def _truthy(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


def evaluate(payload: dict, values: dict) -> bool:
    """Whether the condition holds for `values` (node id → current value).

    Used only to decide whether a block starts hidden, so the reader never sees
    it flash before the browser takes over. A node with no known value counts as
    absent, which reads as false — the safe direction: a block that should have
    been visible appears a frame later, rather than one that should have been
    hidden appearing at all.

    Mirrors `evalPredicate` in the browser; keep the two in step.
    """
    if "node" in payload:
        return _truthy(values.get(payload["node"]))
    op = payload["op"]
    if op == "not":
        return not evaluate(payload["a"], values)
    if op in ("and", "or"):
        left = evaluate(payload["a"], values)
        right = evaluate(payload["b"], values)
        return (left and right) if op == "and" else (left or right)

    def side(operand: dict):
        return values.get(operand["node"]) if "node" in operand else operand["const"]

    a, b = side(payload["a"]), side(payload["b"])
    if op == "eq":
        return a == b
    if op == "ne":
        return a != b
    if a is None or b is None or isinstance(a, str) or isinstance(b, str):
        return False
    if op == "ge":
        return a >= b
    if op == "gt":
        return a > b
    if op == "le":
        return a <= b
    return a < b


def node_refs(payload: dict, into: set) -> set:
    """Every node id the condition reads."""
    if "node" in payload:
        into.add(payload["node"])
        return into
    op = payload["op"]
    if op == "not":
        return node_refs(payload["a"], into)
    if op in ("and", "or"):
        node_refs(payload["a"], into)
        return node_refs(payload["b"], into)
    for operand in (payload["a"], payload["b"]):
        if "node" in operand:
            into.add(operand["node"])
    return into
