"""Typed node models mirroring src/lib/geomatic/state/Node.ts.

Only the properties whitelisted in src/lib/geomatic/state/nodeProperties.ts are
accessible on a node (plus ``id``). Every property access returns another node,
exactly as `node.prop` does in the geomatic DSL, and carries a `PropRef` so it
can be serialized back to the `base.field` argument form.

Numeric payloads live in private attributes and may be ``None`` when a value is
not computable in Python (record-only commands). Read them via ``.numeric`` /
``float(node)`` / ``complex(node)`` — these are inspection helpers, not DSL
properties.

Scalar / Complex / Array nodes support infix arithmetic (`+ - * /`, unary
`-`) and Arrays support `arr[i]` / `len(arr)`: each operation routes through
the corresponding overload command (`\\add`, `\\get-array-element`, ...) and
records exactly like the explicit call. Chained `a + b + c` fuses into ONE
variadic `\\add a b c` (store.fuse_variadic). Other node types (Point, Circle,
...) keep instructive errors, as do `**` and `@`.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import ClassVar, Optional, Union

import numpy as np
from pydantic import BaseModel, ConfigDict, PrivateAttr

# ---------------------------------------------------------------------------
# Argument references (how a node is rendered as a DSL argument token)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdRef:
    """A stored node, referenced by its id."""

    id: str

    def render(self) -> str:
        return self.id


@dataclass(frozen=True)
class PropRef:
    """A `base.field1.field2` property-access chain rooted at a stored node."""

    base: str
    path: tuple[str, ...]

    def render(self) -> str:
        return ".".join((self.base, *self.path))


Ref = Union[IdRef, PropRef]

_NO_INFIX_MSG = (
    "pygeomatic does not support infix {op} for {types}; "
    "use the explicit pygeomatic function for the operation instead"
)

# Set while an operator dunder routes through a registered command, so the
# recording wrapper knows the call is infix-originated: it hops the inference
# frame to the user's BINARY_OP/BINARY_SUBSCR and enables variadic fusion.
_infix_call: ContextVar[bool] = ContextVar("pygeomatic_infix_call", default=False)

# Operand kinds the arithmetic overload commands (`\add`, `\mul`, ...) accept.
_ARITHMETIC_NODES = ("Scalar", "Complex", "Array")


def _is_arithmetic_operand(v) -> bool:
    if isinstance(v, GNode):
        return v.type in _ARITHMETIC_NODES
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _infix(keyword: str, *operands):
    """Route an operator dunder through the registered command `keyword`."""
    from .registry import REGISTRY

    token = _infix_call.set(True)
    try:
        return REGISTRY[keyword].py_func(*operands)
    finally:
        _infix_call.reset(token)


def _arith(op: str, keyword: str, *operands):
    for v in operands:
        if not _is_arithmetic_operand(v):
            if isinstance(v, GNode):
                raise TypeError(_NO_INFIX_MSG.format(op=op, types=f"{v.type} nodes"))
            return NotImplemented
    return _infix(keyword, *operands)


def _reject(op: str):
    def method(self, *_args):
        raise TypeError(_NO_INFIX_MSG.format(op=op, types=f"{self.type} nodes"))

    return method


def _reject_inplace(op: str):
    # `acc += x` would rebind the python variable to a NEW node while the
    # DSL node `acc` keeps its old value — silent divergence. Refuse it.
    def method(self, _other):
        binop = op.rstrip("=")
        raise TypeError(
            f"in-place {op} is not supported on geomatic nodes: it rebinds the "
            f"python variable to a NEW node while the original DSL node keeps "
            f"its id and value. Assign a new name instead: c = a {binop} b"
        )

    return method


# ---------------------------------------------------------------------------
# Base node
# ---------------------------------------------------------------------------


class GNode(BaseModel):
    """Base of all geomatic nodes. Subclasses set ``type`` and private payload."""

    model_config = ConfigDict(extra="forbid")

    type: ClassVar[str] = "Node"

    id: Optional[str] = None
    _ref: Optional[Ref] = PrivateAttr(default=None)

    @property
    def ref(self) -> Ref:
        if self._ref is None:
            raise ValueError(
                f"{self.type} node has no reference yet — it was not produced by a "
                "pygeomatic function call, so it cannot be used as an argument"
            )
        return self._ref

    def _prop(self, field: str) -> Ref:
        """Ref for accessing `field` on this node (`p.x`, `circ.center.x`)."""
        r = self.ref
        if isinstance(r, IdRef):
            return PropRef(r.id, (field,))
        return PropRef(r.base, (*r.path, field))

    def _as_prop(self, base: "GNode", field: str) -> "GNode":
        """Clone of this node re-referenced as `base.field` (numerics preserved)."""
        clone = self.model_copy()
        clone.id = None
        clone._ref = base._prop(field)
        return clone

    # Infix arithmetic on Scalar/Complex/Array routes through the overload
    # commands and records on the tape; other node types raise instructively.
    def __add__(self, other):
        return _arith("+", "add", self, other)

    def __radd__(self, other):
        return _arith("+", "add", other, self)

    def __sub__(self, other):
        return _arith("-", "sub", self, other)

    def __rsub__(self, other):
        return _arith("-", "sub", other, self)

    def __mul__(self, other):
        return _arith("*", "mul", self, other)

    def __rmul__(self, other):
        return _arith("*", "mul", other, self)

    def __truediv__(self, other):
        return _arith("/", "div", self, other)

    def __rtruediv__(self, other):
        return _arith("/", "div", other, self)

    def __neg__(self):
        if not _is_arithmetic_operand(self):
            raise TypeError(_NO_INFIX_MSG.format(op="unary -", types=f"{self.type} nodes"))
        return _infix("neg", self)

    __pow__ = __rpow__ = _reject("**")
    __matmul__ = __rmatmul__ = _reject("@")
    __iadd__ = _reject_inplace("+=")
    __isub__ = _reject_inplace("-=")
    __imul__ = _reject_inplace("*=")
    __itruediv__ = _reject_inplace("/=")

    def __repr__(self) -> str:  # concise, id-first
        return f"{self.type}(id={self.id!r})"


# ---------------------------------------------------------------------------
# Leaf value nodes
# ---------------------------------------------------------------------------


class Scalar(GNode):
    type: ClassVar[str] = "Scalar"
    _value: Optional[float] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, value: Optional[float] = None) -> "Scalar":
        n = cls()
        n._value = None if value is None else float(value)
        return n

    @property
    def value(self) -> "Scalar":
        return self._as_prop(self, "value")  # type: ignore[return-value]

    @property
    def numeric(self) -> Optional[float]:
        return self._value

    def __float__(self) -> float:
        if self._value is None:
            raise TypeError(f"Scalar {self.id!r} has no numeric value")
        return float(self._value)

    def __repr__(self) -> str:
        return f"Scalar(id={self.id!r}, value={self._value})"


class Complex(GNode):
    type: ClassVar[str] = "Complex"
    _re: Optional[float] = PrivateAttr(default=None)
    _im: Optional[float] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, re: Optional[float] = None, im: Optional[float] = None) -> "Complex":
        n = cls()
        n._re = None if re is None else float(re)
        n._im = None if im is None else float(im)
        return n

    @property
    def re(self) -> Scalar:
        return Scalar._new(self._re)._as_prop(self, "re")  # type: ignore[return-value]

    @property
    def im(self) -> Scalar:
        return Scalar._new(self._im)._as_prop(self, "im")  # type: ignore[return-value]

    @property
    def numeric(self) -> Optional[complex]:
        if self._re is None or self._im is None:
            return None
        return complex(self._re, self._im)

    def __complex__(self) -> complex:
        n = self.numeric
        if n is None:
            raise TypeError(f"Complex {self.id!r} has no numeric value")
        return n

    def __repr__(self) -> str:
        return f"Complex(id={self.id!r}, value={self.numeric})"


class Point(GNode):
    type: ClassVar[str] = "Point"
    _x: Optional[float] = PrivateAttr(default=None)
    _y: Optional[float] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, x: Optional[float] = None, y: Optional[float] = None) -> "Point":
        n = cls()
        n._x = None if x is None else float(x)
        n._y = None if y is None else float(y)
        return n

    @property
    def x(self) -> Scalar:
        return Scalar._new(self._x)._as_prop(self, "x")  # type: ignore[return-value]

    @property
    def y(self) -> Scalar:
        return Scalar._new(self._y)._as_prop(self, "y")  # type: ignore[return-value]

    @property
    def numeric(self) -> Optional[tuple[float, float]]:
        if self._x is None or self._y is None:
            return None
        return (self._x, self._y)

    def __repr__(self) -> str:
        return f"Point(id={self.id!r}, x={self._x}, y={self._y})"


class ScalarGradient(Scalar):
    """Reactive partial derivative d(target)/d(of) for a Scalar variable
    (`\\partial` output). Subclasses Scalar: same `value` payload, accepted
    anywhere a Scalar is (mirrors the engine's dispatchType mapping)."""

    type: ClassVar[str] = "ScalarGradient"

    def __repr__(self) -> str:
        return f"ScalarGradient(id={self.id!r}, value={self._value})"


class PointGradient(Point):
    """Reactive gradient (d(target)/dx, d(target)/dy) for a Point variable
    (`\\partial` output). Subclasses Point: same `x`/`y` payload."""

    type: ClassVar[str] = "PointGradient"

    def __repr__(self) -> str:
        return f"PointGradient(id={self.id!r}, x={self._x}, y={self._y})"


class Text(GNode):
    type: ClassVar[str] = "Text"
    _value: Optional[str] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, value: Optional[str] = None) -> "Text":
        n = cls()
        n._value = value
        return n

    @property
    def numeric(self) -> Optional[str]:
        return self._value


class Bool(GNode):
    type: ClassVar[str] = "Bool"
    _value: Optional[bool] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, value: Optional[bool] = None) -> "Bool":
        n = cls()
        n._value = None if value is None else bool(value)
        return n

    @property
    def numeric(self) -> Optional[bool]:
        return self._value

    def __bool__(self) -> bool:
        if self._value is None:
            raise TypeError(f"Bool {self.id!r} has no value")
        return self._value


class Dummy(GNode):
    """Output of imperative commands that produce nothing."""

    type: ClassVar[str] = "Dummy"

    @classmethod
    def _new(cls) -> "Dummy":
        return cls()


# ---------------------------------------------------------------------------
# Composite geometric nodes
# ---------------------------------------------------------------------------


def _child(stored: Optional[GNode], base: GNode, field: str, cls: type[GNode]) -> GNode:
    node = stored if stored is not None else cls._new()  # type: ignore[attr-defined]
    return node._as_prop(base, field)


class Line(GNode):
    type: ClassVar[str] = "Line"
    _p1: Optional[Point] = PrivateAttr(default=None)
    _p2: Optional[Point] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, p1: Optional[Point] = None, p2: Optional[Point] = None) -> "Line":
        n = cls()
        n._p1, n._p2 = p1, p2
        return n

    @property
    def p1(self) -> Point:
        return _child(self._p1, self, "p1", Point)  # type: ignore[return-value]

    @property
    def p2(self) -> Point:
        return _child(self._p2, self, "p2", Point)  # type: ignore[return-value]


class Circle(GNode):
    type: ClassVar[str] = "Circle"
    _center: Optional[Point] = PrivateAttr(default=None)
    _radius: Optional[Scalar] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, center: Optional[Point] = None, radius: Optional[Scalar] = None) -> "Circle":
        n = cls()
        n._center, n._radius = center, radius
        return n

    @property
    def center(self) -> Point:
        return _child(self._center, self, "center", Point)  # type: ignore[return-value]

    @property
    def radius(self) -> Scalar:
        return _child(self._radius, self, "radius", Scalar)  # type: ignore[return-value]


class Ellipse(GNode):
    type: ClassVar[str] = "Ellipse"
    _center: Optional[Point] = PrivateAttr(default=None)
    _radiusX: Optional[Scalar] = PrivateAttr(default=None)
    _radiusY: Optional[Scalar] = PrivateAttr(default=None)
    _rotation: Optional[Scalar] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, center=None, radiusX=None, radiusY=None, rotation=None) -> "Ellipse":
        n = cls()
        n._center, n._radiusX, n._radiusY, n._rotation = center, radiusX, radiusY, rotation
        return n

    @property
    def center(self) -> Point:
        return _child(self._center, self, "center", Point)  # type: ignore[return-value]

    @property
    def radiusX(self) -> Scalar:
        return _child(self._radiusX, self, "radiusX", Scalar)  # type: ignore[return-value]

    @property
    def radiusY(self) -> Scalar:
        return _child(self._radiusY, self, "radiusY", Scalar)  # type: ignore[return-value]

    @property
    def rotation(self) -> Scalar:
        return _child(self._rotation, self, "rotation", Scalar)  # type: ignore[return-value]


class Arc(GNode):
    type: ClassVar[str] = "Arc"
    _center: Optional[Point] = PrivateAttr(default=None)
    _radius: Optional[Scalar] = PrivateAttr(default=None)
    _startAngle: Optional[Scalar] = PrivateAttr(default=None)
    _endAngle: Optional[Scalar] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, center=None, radius=None, startAngle=None, endAngle=None) -> "Arc":
        n = cls()
        n._center, n._radius, n._startAngle, n._endAngle = center, radius, startAngle, endAngle
        return n

    @property
    def center(self) -> Point:
        return _child(self._center, self, "center", Point)  # type: ignore[return-value]

    @property
    def radius(self) -> Scalar:
        return _child(self._radius, self, "radius", Scalar)  # type: ignore[return-value]

    @property
    def startAngle(self) -> Scalar:
        return _child(self._startAngle, self, "startAngle", Scalar)  # type: ignore[return-value]

    @property
    def endAngle(self) -> Scalar:
        return _child(self._endAngle, self, "endAngle", Scalar)  # type: ignore[return-value]


class RegularPolygon(GNode):
    type: ClassVar[str] = "RegularPolygon"
    _center: Optional[Point] = PrivateAttr(default=None)
    _radius: Optional[Scalar] = PrivateAttr(default=None)
    _numVertices: Optional[Scalar] = PrivateAttr(default=None)
    _startAngle: Optional[Scalar] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, center=None, radius=None, numVertices=None, startAngle=None) -> "RegularPolygon":
        n = cls()
        n._center, n._radius, n._numVertices, n._startAngle = center, radius, numVertices, startAngle
        return n

    @property
    def center(self) -> Point:
        return _child(self._center, self, "center", Point)  # type: ignore[return-value]

    @property
    def radius(self) -> Scalar:
        return _child(self._radius, self, "radius", Scalar)  # type: ignore[return-value]

    @property
    def numVertices(self) -> Scalar:
        return _child(self._numVertices, self, "numVertices", Scalar)  # type: ignore[return-value]

    @property
    def startAngle(self) -> Scalar:
        return _child(self._startAngle, self, "startAngle", Scalar)  # type: ignore[return-value]


class BezierQuadratic(GNode):
    type: ClassVar[str] = "BezierQuadratic"
    _p1: Optional[Point] = PrivateAttr(default=None)
    _control: Optional[Point] = PrivateAttr(default=None)
    _p2: Optional[Point] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, p1=None, control=None, p2=None) -> "BezierQuadratic":
        n = cls()
        n._p1, n._control, n._p2 = p1, control, p2
        return n

    @property
    def p1(self) -> Point:
        return _child(self._p1, self, "p1", Point)  # type: ignore[return-value]

    @property
    def control(self) -> Point:
        return _child(self._control, self, "control", Point)  # type: ignore[return-value]

    @property
    def p2(self) -> Point:
        return _child(self._p2, self, "p2", Point)  # type: ignore[return-value]


class BezierCubic(GNode):
    type: ClassVar[str] = "BezierCubic"
    _p1: Optional[Point] = PrivateAttr(default=None)
    _control1: Optional[Point] = PrivateAttr(default=None)
    _control2: Optional[Point] = PrivateAttr(default=None)
    _p2: Optional[Point] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, p1=None, control1=None, control2=None, p2=None) -> "BezierCubic":
        n = cls()
        n._p1, n._control1, n._control2, n._p2 = p1, control1, control2, p2
        return n

    @property
    def p1(self) -> Point:
        return _child(self._p1, self, "p1", Point)  # type: ignore[return-value]

    @property
    def control1(self) -> Point:
        return _child(self._control1, self, "control1", Point)  # type: ignore[return-value]

    @property
    def control2(self) -> Point:
        return _child(self._control2, self, "control2", Point)  # type: ignore[return-value]

    @property
    def p2(self) -> Point:
        return _child(self._p2, self, "p2", Point)  # type: ignore[return-value]


class Triangle(GNode):
    type: ClassVar[str] = "Triangle"
    _vertices: list[Point] = PrivateAttr(default_factory=list)

    @classmethod
    def _new(cls, vertices: Optional[list[Point]] = None) -> "Triangle":
        n = cls()
        n._vertices = list(vertices or [])
        return n

    @property
    def vertices(self) -> "Array":
        arr = Array._new(element_type="Point", elements=list(self._vertices))
        return arr._as_prop(self, "vertices")  # type: ignore[return-value]


class Polygon(GNode):
    type: ClassVar[str] = "Polygon"
    _vertices: list[Point] = PrivateAttr(default_factory=list)

    @classmethod
    def _new(cls, vertices: Optional[list[Point]] = None) -> "Polygon":
        n = cls()
        n._vertices = list(vertices or [])
        return n

    @property
    def vertices(self) -> "Array":
        arr = Array._new(element_type="Point", elements=list(self._vertices))
        return arr._as_prop(self, "vertices")  # type: ignore[return-value]


class Array(GNode):
    type: ClassVar[str] = "Array"
    _element_type: str = PrivateAttr(default="Scalar")
    _elements: list[GNode] = PrivateAttr(default_factory=list)
    _shape: tuple[int, ...] = PrivateAttr(default=())

    @classmethod
    def _new(
        cls,
        element_type: str = "Scalar",
        elements: Optional[list[GNode]] = None,
        shape: Optional[tuple[int, ...]] = None,
    ) -> "Array":
        n = cls()
        n._element_type = element_type
        n._elements = list(elements or [])
        n._shape = tuple(shape) if shape is not None else (len(n._elements),)
        return n

    @property
    def length(self) -> Scalar:
        return Scalar._new(len(self._elements))._as_prop(self, "length")  # type: ignore[return-value]

    @property
    def numeric(self) -> Optional[np.ndarray]:
        """Element values as an ndarray of self.shape (None if any is unknown)."""
        vals = []
        for el in self._elements:
            v = getattr(el, "numeric", None)
            if v is None:
                return None
            vals.append(v)
        if not vals:
            return np.array([]).reshape(self._shape)
        return np.array(vals).reshape(
            self._shape if self._element_type != "Point" else (*self._shape, 2)
        )

    def __len__(self) -> int:
        """Record-time element count (a plain int; records no command).

        Enables `for k in range(len(arr)): arr[k]` loops that unroll into
        commands. Record-only arrays (extension outputs) report 0.
        """
        return len(self._elements)

    def __getitem__(self, key):
        """`arr[i]` records `\\get-array-element arr i` (i: int or Scalar).

        A literal negative index is normalized against the record-time length
        (the engine has no negative indexing). With `__len__`, this also makes
        `for el in arr:` work via the sequence protocol, one command per
        element.
        """
        if isinstance(key, slice):
            raise TypeError(
                "geomatic has no array-slice command; index elements one at a "
                "time (arr[i]) or build a new \\array from the elements you need"
            )
        if isinstance(key, (int, np.integer)) and not isinstance(key, bool):
            key = int(key)
            if key < 0:
                if not self._elements:
                    raise IndexError(
                        f"cannot normalize negative index {key}: array length "
                        "is unknown at record time"
                    )
                key %= len(self._elements)
        elif not isinstance(key, Scalar):
            raise TypeError(
                f"array index must be an int or a Scalar node, got {type(key).__name__!r}"
            )
        return _infix("get-array-element", self, key)

    def __setitem__(self, key, value):
        raise TypeError(
            "geomatic arrays are reactive outputs and have no element-assignment "
            "command; build a new \\array instead"
        )

    def __iter__(self):
        # BaseModel.__iter__ yields pydantic fields; iterate elements instead,
        # recording one \get-array-element per element.
        for k in range(len(self._elements)):
            yield self[k]


# ---------------------------------------------------------------------------
# Curve / plot / trajectory nodes
# ---------------------------------------------------------------------------


class Trail(GNode):
    type: ClassVar[str] = "Trail"

    @classmethod
    def _new(cls) -> "Trail":
        return cls()


class Plot(GNode):
    type: ClassVar[str] = "Plot"

    @classmethod
    def _new(cls) -> "Plot":
        return cls()


class Polynomial(GNode):
    type: ClassVar[str] = "Polynomial"
    _coefficients: list[Scalar] = PrivateAttr(default_factory=list)

    @classmethod
    def _new(cls, coefficients: Optional[list[Scalar]] = None) -> "Polynomial":
        n = cls()
        n._coefficients = list(coefficients or [])
        return n

    @property
    def numeric(self) -> Optional[np.ndarray]:
        """Coefficients (ascending order: a0, a1, ...) as an ndarray."""
        vals = [c.numeric for c in self._coefficients]
        if any(v is None for v in vals):
            return None
        return np.array(vals)


class VectorField(GNode):
    type: ClassVar[str] = "VectorField"

    @classmethod
    def _new(cls) -> "VectorField":
        return cls()


class Trajectory(GNode):
    type: ClassVar[str] = "Trajectory"
    # Raw integrated samples (x = t or x-coord, y = value), None when the ODE
    # could not be solved in Python (record-only).
    _points: Optional[list[tuple[float, float]]] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, points: Optional[list[tuple[float, float]]] = None) -> "Trajectory":
        n = cls()
        n._points = points
        return n

    @property
    def numeric(self) -> Optional[np.ndarray]:
        if self._points is None:
            return None
        return np.array(self._points)


# ---------------------------------------------------------------------------
# Annotation nodes
# ---------------------------------------------------------------------------


class Arrow(GNode):
    type: ClassVar[str] = "Arrow"
    _p1: Optional[Point] = PrivateAttr(default=None)
    _p2: Optional[Point] = PrivateAttr(default=None)
    _label: str = PrivateAttr(default="")

    @classmethod
    def _new(cls, p1=None, p2=None, label: str = "") -> "Arrow":
        n = cls()
        n._p1, n._p2, n._label = p1, p2, label
        return n

    @property
    def p1(self) -> Point:
        return _child(self._p1, self, "p1", Point)  # type: ignore[return-value]

    @property
    def p2(self) -> Point:
        return _child(self._p2, self, "p2", Point)  # type: ignore[return-value]


class CurvedArrow(GNode):
    type: ClassVar[str] = "CurvedArrow"
    _p1: Optional[Point] = PrivateAttr(default=None)
    _p2: Optional[Point] = PrivateAttr(default=None)
    _control: Optional[Point] = PrivateAttr(default=None)
    _label: str = PrivateAttr(default="")

    @classmethod
    def _new(cls, p1=None, p2=None, control=None, label: str = "") -> "CurvedArrow":
        n = cls()
        n._p1, n._p2, n._control, n._label = p1, p2, control, label
        return n


class DimensionLine(GNode):
    type: ClassVar[str] = "DimensionLine"
    _p1: Optional[Point] = PrivateAttr(default=None)
    _p2: Optional[Point] = PrivateAttr(default=None)
    _label: str = PrivateAttr(default="")

    @classmethod
    def _new(cls, p1=None, p2=None, label: str = "") -> "DimensionLine":
        n = cls()
        n._p1, n._p2, n._label = p1, p2, label
        return n


class AngleMark(GNode):
    type: ClassVar[str] = "AngleMark"
    _label: str = PrivateAttr(default="")

    @classmethod
    def _new(cls, label: str = "") -> "AngleMark":
        n = cls()
        n._label = label
        return n


class CurlyBracket(GNode):
    type: ClassVar[str] = "CurlyBracket"
    _p1: Optional[Point] = PrivateAttr(default=None)
    _p2: Optional[Point] = PrivateAttr(default=None)
    _label: str = PrivateAttr(default="")

    @classmethod
    def _new(cls, p1=None, p2=None, label: str = "") -> "CurlyBracket":
        n = cls()
        n._p1, n._p2, n._label = p1, p2, label
        return n


class TextBox(GNode):
    type: ClassVar[str] = "TextBox"
    _text: str = PrivateAttr(default="")
    _position: Optional[Point] = PrivateAttr(default=None)

    @classmethod
    def _new(cls, text: str = "", position=None) -> "TextBox":
        n = cls()
        n._text, n._position = text, position
        return n


class LeaderLine(GNode):
    type: ClassVar[str] = "LeaderLine"
    _p1: Optional[Point] = PrivateAttr(default=None)
    _p2: Optional[Point] = PrivateAttr(default=None)
    _label: str = PrivateAttr(default="")

    @classmethod
    def _new(cls, p1=None, p2=None, label: str = "") -> "LeaderLine":
        n = cls()
        n._p1, n._p2, n._label = p1, p2, label
        return n


class Pin(GNode):
    type: ClassVar[str] = "Pin"
    _position: Optional[Point] = PrivateAttr(default=None)
    _label: str = PrivateAttr(default="")

    @classmethod
    def _new(cls, position=None, label: str = "") -> "Pin":
        n = cls()
        n._position, n._label = position, label
        return n


# ---------------------------------------------------------------------------
# Property whitelist (python mirror of nodeProperties.ts NODE_PROPERTIES)
# ---------------------------------------------------------------------------

NODE_PROPERTIES: dict[str, dict[str, str]] = {
    "Scalar": {"value": "Scalar"},
    "Complex": {"re": "Scalar", "im": "Scalar"},
    "Point": {"x": "Scalar", "y": "Scalar"},
    "ScalarGradient": {"value": "Scalar"},
    "PointGradient": {"x": "Scalar", "y": "Scalar"},
    "Line": {"p1": "Point", "p2": "Point"},
    "Arrow": {"p1": "Point", "p2": "Point"},
    "Circle": {"center": "Point", "radius": "Scalar"},
    "Ellipse": {
        "center": "Point",
        "radiusX": "Scalar",
        "radiusY": "Scalar",
        "rotation": "Scalar",
    },
    "Arc": {
        "center": "Point",
        "radius": "Scalar",
        "startAngle": "Scalar",
        "endAngle": "Scalar",
    },
    "RegularPolygon": {
        "center": "Point",
        "radius": "Scalar",
        "numVertices": "Scalar",
        "startAngle": "Scalar",
    },
    "BezierQuadratic": {"p1": "Point", "control": "Point", "p2": "Point"},
    "BezierCubic": {
        "p1": "Point",
        "control1": "Point",
        "control2": "Point",
        "p2": "Point",
    },
    "Triangle": {"vertices": "Point"},
    "Polygon": {"vertices": "Point"},
    "Array": {"length": "Scalar"},
}

NODE_CLASSES: dict[str, type[GNode]] = {
    "Text": Text,
    "Bool": Bool,
    "Point": Point,
    "Scalar": Scalar,
    "ScalarGradient": ScalarGradient,
    "PointGradient": PointGradient,
    "Complex": Complex,
    "Triangle": Triangle,
    "Line": Line,
    "Circle": Circle,
    "Ellipse": Ellipse,
    "RegularPolygon": RegularPolygon,
    "BezierQuadratic": BezierQuadratic,
    "BezierCubic": BezierCubic,
    "Polygon": Polygon,
    "Arc": Arc,
    "Dummy": Dummy,
    "Array": Array,
    "Trail": Trail,
    "Plot": Plot,
    "Polynomial": Polynomial,
    "VectorField": VectorField,
    "Trajectory": Trajectory,
    "Arrow": Arrow,
    "CurvedArrow": CurvedArrow,
    "DimensionLine": DimensionLine,
    "AngleMark": AngleMark,
    "CurlyBracket": CurlyBracket,
    "TextBox": TextBox,
    "LeaderLine": LeaderLine,
    "Pin": Pin,
}
