"""Emit the recorded tape as geomatic DSL lines (stage 2, minimal version).

The tape is an ordered, flat record of every pygeomatic call, so emission is
deterministic and unambiguous: one Command → one line, arguments rendered as
node ids, `base.prop` chains, plain numbers, or the quoted string of `\\text`.

Numbers are rendered in the DSL grammar `-?digits(.digits)?` — positional
notation only, never scientific.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .nodes import IdRef, PropRef
from .store import ArgToken, Command, Store, TextLit, current_store


def _render_number(value: float) -> str:
    if isinstance(value, (int, np.integer)) or float(value).is_integer():
        return str(int(value))
    # positional notation, trimmed trailing zeros; the grammar has no exponent
    return np.format_float_positional(float(value), trim="0")


def render_token(token: ArgToken) -> str:
    if isinstance(token, (IdRef, PropRef)):
        return token.render()
    if isinstance(token, TextLit):
        return f'"{token.text}"'
    return _render_number(token)


def render_command(cmd: Command) -> str:
    parts = [f"\\{cmd.keyword}", *(render_token(t) for t in cmd.args)]
    line = " ".join(parts)
    if cmd.output_id is not None:
        return f"{cmd.output_id} = {line}"
    return line


def emit(store: Optional[Store] = None) -> str:
    """The whole tape as newline-joined geomatic commands."""
    store = store or current_store()
    return "\n".join(render_command(cmd) for cmd in store.commands)
