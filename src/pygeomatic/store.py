"""The command tape and node store.

Every pygeomatic function call appends one `Command` to the active `Store` —
the exact, ordered record from which geomatic DSL lines are emitted (emit.py).
Because Python evaluates arguments before a call, the tape automatically
satisfies the DSL's one-command-per-line / no-nesting / define-before-use rules.

Auto-generated output ids replicate src/lib/geomatic/state/NameGenerator.ts
(`p0`, `num0`, `circ0`, ...). Explicit ids must match the DSL identifier
grammar: start with a letter, then letters/digits/dashes — NO underscores.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional, Union

from .nodes import GNode, IdRef, PropRef, Ref
from .system_nodes import SYSTEM_NODE_IDS, register_system_nodes

# ---------------------------------------------------------------------------
# Argument tokens
# ---------------------------------------------------------------------------


# The DSL is line-based and the canvas renders text as single-line SVG
# <text>, so a newline can neither be emitted nor displayed: collapse any
# newline (with its surrounding indentation) to a single space.
_NEWLINE_RUN_RE = re.compile(r"[ \t]*[\r\n]+[ \t]*")


def sanitize_text(value: str) -> str:
    """Make a string safe as a single-line DSL text value."""
    return _NEWLINE_RUN_RE.sub(" ", value).strip()


@dataclass(frozen=True)
class TextLit:
    """The quoted string of a `\\text "..."` command (the only quoted form)."""

    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", sanitize_text(self.text))


ArgToken = Union[int, float, IdRef, PropRef, TextLit]


@dataclass
class Command:
    """One geomatic DSL line: `output_id = \\keyword args...` (or no output)."""

    output_id: Optional[str]
    keyword: str
    args: list[ArgToken] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------

IDENTIFIER_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9-]*\Z")

# Per-type prefixes from NameGenerator.ts NAMING_PATTERNS — but python ids put
# a DASH before the counter (`num-0`, not `num0`). The engine auto-generates
# undashed `prefix{counter}` ids for its own internal nodes (property-access
# accessors, numeric literals, auxiliary blueprint nodes like linspace
# elements), and it resolves inputs BEFORE reserving a command's assigned id.
# An emitted line like `num0 = \mul p0.x scale` therefore lets the `p0.x`
# accessor claim `num0` first, the assignment then clobbers its own input, and
# the reactive graph loops forever. Dashed ids can never collide: the engine
# never generates them.
NAMING_PATTERNS: dict[str, str] = {
    "Text": "text-{counter}",
    "Bool": "bool-{counter}",
    "Point": "p-{counter}",
    "Scalar": "num-{counter}",
    "ScalarGradient": "dgrad-{counter}",
    "PointGradient": "pgrad-{counter}",
    "Complex": "z-{counter}",
    "Line": "line-{counter}",
    "Triangle": "tr-{counter}",
    "Circle": "circ-{counter}",
    "Ellipse": "ell-{counter}",
    "Polygon": "poly-{counter}",
    "RegularPolygon": "repo-{counter}",
    "BezierQuadratic": "bq-{counter}",
    "BezierCubic": "bc-{counter}",
    "Arc": "arc-{counter}",
    "Dummy": "",
    "Array": "arr-{counter}",
    "Trail": "trail-{counter}",
    "Plot": "plot-{counter}",
    "Polynomial": "polynomial-{counter}",
    "VectorField": "vf-{counter}",
    "Trajectory": "de-{counter}",
    "Arrow": "arrow-{counter}",
    "CurvedArrow": "carrow-{counter}",
    "DimensionLine": "dim-{counter}",
    "AngleMark": "amk-{counter}",
    "CurlyBracket": "brace-{counter}",
    "TextBox": "tbox-{counter}",
    "LeaderLine": "lead-{counter}",
    "Pin": "pin-{counter}",
}

# Undashed engine auto-name prefixes: ids of the form `<prefix><digits>` are
# claimed by the engine's own NameGenerator for internal nodes, so explicit
# `out=` ids must not take that shape.
_ENGINE_PREFIXES = sorted(
    {p.replace("-{counter}", "") for p in NAMING_PATTERNS.values() if p},
    key=len,
    reverse=True,
)
ENGINE_AUTO_ID_RE = re.compile(rf"({'|'.join(_ENGINE_PREFIXES)})\d+\Z")


# Set while replaying parsed DSL (parse.py): ids the ENGINE itself generated
# (`p0`, `num1`, ...) are legitimate in pasted scenes and must round-trip, so
# the engine-auto-shape rejection is suspended. New pygeomatic-authored ids
# stay strict.
_allow_engine_ids: ContextVar[bool] = ContextVar("pygeomatic_allow_engine_ids", default=False)

# Set while a macro body is being replayed (macros.py). Inside it the store
# mirrors the ENGINE's macro execution instead of pygeomatic authoring rules:
# body commands are not recorded on the tape (only the macro invocation is),
# auto ids use the engine's undashed NameGenerator patterns (`p1`, `num0`) so
# body-internal references to them resolve, and an explicit id may overwrite
# an existing node (the engine's saveNode is last-write-wins).
_macro_replay: ContextVar[bool] = ContextVar("pygeomatic_macro_replay", default=False)


def validate_identifier(name: str) -> str:
    if not IDENTIFIER_RE.match(name):
        hint = " (underscores are not allowed in geomatic ids; use dashes)" if "_" in name else ""
        raise ValueError(
            f"invalid geomatic identifier {name!r}: must start with a letter and "
            f"contain only letters, digits and dashes{hint}"
        )
    if _allow_engine_ids.get():
        return name
    m = ENGINE_AUTO_ID_RE.match(name)
    if m:
        prefix = m.group(1)
        suggestion = f"{prefix}-{name[len(prefix):]}"
        raise ValueError(
            f"unsafe geomatic identifier {name!r}: ids of the form <prefix><digits> "
            f"(num0, p3, text1, ...) are auto-generated by the engine for internal "
            f"nodes (property accessors, literals, array elements) and can collide, "
            f"creating a reactive cycle. Use {suggestion!r} or a descriptive name."
        )
    return name


class NameGenerator:
    """Per-store counters, mirroring NameGenerator.ts."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def generate(self, node_type: str) -> str:
        # Unknown types (extension outputTypes) get a dashed pattern too — the
        # engine never generates dashed ids, so these can't collide with its
        # internal auto-names.
        pattern = NAMING_PATTERNS.get(node_type, f"{node_type.lower()}-{{counter}}")
        return self._next(pattern)

    def generate_engine(self, node_type: str) -> str:
        """The ENGINE's undashed auto id (`p1`, `num0`), used only while
        replaying a macro body: its commands run inside the engine's own
        NameGenerator, and later body lines reference those undashed ids."""
        pattern = NAMING_PATTERNS.get(node_type) or "node-{counter}"
        return self._next(pattern.replace("-{counter}", "{counter}"))

    def _next(self, pattern: str) -> str:
        prefix = pattern.replace("{counter}", "")
        current = self._counters.get(prefix, 0)
        self._counters[prefix] = current + 1
        return pattern.replace("{counter}", str(current))

    def reserve(self, node_id: str) -> None:
        m = re.match(r"([a-zA-Z-]*?)(\d+)\Z", node_id)
        if m:
            prefix, num = m.group(1), int(m.group(2))
            if num >= self._counters.get(prefix, 0):
                self._counters[prefix] = num + 1


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class Store:
    """Ordered tape of commands + id → node map. Usable as a context manager
    (`with Store() as s:`) to scope a fresh tape."""

    def __init__(self) -> None:
        self.commands: list[Command] = []
        self.nodes: dict[str, GNode] = {}
        self.names = NameGenerator()
        self._token = None
        # Every canvas starts with the engine's default nodes (`p0`, `T`/`F`,
        # `learning-rate`, ...); seed them so a scene can reference them without
        # defining them. They record no command, so emit() is unaffected.
        register_system_nodes(self)

    # -- registration -------------------------------------------------------

    def allocate_id(self, node_type: str, out: Optional[str]) -> str:
        if out is not None:
            validate_identifier(out)
            # A user command may reassign a system default (e.g. the fermat macro's
            # `learning-rate = \scalar 0.5`); the engine's saveNode is last-write-wins.
            # Any OTHER duplicate is an authoring mistake and stays rejected —
            # except inside a macro body, which runs with full engine semantics.
            if out in self.nodes and out not in SYSTEM_NODE_IDS and not _macro_replay.get():
                raise ValueError(f"node id {out!r} already exists in this store")
            self.names.reserve(out)
            return out
        if _macro_replay.get():
            return self.names.generate_engine(node_type)
        return self.names.generate(node_type)

    def register(self, node: GNode, node_id: str) -> GNode:
        node.id = node_id
        node._ref = IdRef(node_id)
        self.nodes[node_id] = node
        return node

    def record(self, keyword: str, args: list[ArgToken], output_id: Optional[str]) -> None:
        # A macro body's commands never reach the tape — the single macro
        # invocation line stands for all of them (recorded by its wrapper
        # AFTER the replay context exits, so nested macros stay suppressed).
        if _macro_replay.get():
            return
        self.commands.append(Command(output_id=output_id, keyword=keyword, args=args))

    # -- context manager ----------------------------------------------------

    def __enter__(self) -> "Store":
        self._token = _current_store.set(self)
        return self

    def __exit__(self, *exc) -> None:
        if self._token is not None:
            _current_store.reset(self._token)
            self._token = None


_current_store: ContextVar[Optional[Store]] = ContextVar("pygeomatic_store", default=None)
_default_store = Store()


def current_store() -> Store:
    return _current_store.get() or _default_store


def reset_default_store() -> Store:
    """Replace the module-level default store with a fresh one (mainly for tests)."""
    global _default_store
    _default_store = Store()
    return _default_store
