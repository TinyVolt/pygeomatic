"""Parsing and emitting helpers shared by the templates."""

import csv
import json
import re
import textwrap


def _q(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


class TemplateError(ValueError):
    pass


_FRONTMATTER = re.compile(r"\A﻿?---[ \t]*\r?\n(?:([\s\S]*?)\r?\n)?---[ \t]*(?:\r?\n|\Z)")


def _frontmatter(data: str) -> tuple[dict[str, str], str, int]:
    """Split a `---` fenced `key: value` block off the top of `data`; return
    `(fields, rest, number of lines taken)`. Mirrors readFrontmatter in
    tinyvolt-web's frontmatter.ts."""
    if not isinstance(data, str):
        raise TemplateError(f"template data must be a string, got {type(data).__name__}")
    match = _FRONTMATTER.match(data)
    if not match:
        return {}, data, 0
    fields = {}
    for line in (match.group(1) or "").splitlines():
        pair = re.match(r"^\s*([\w-]+)\s*:\s*(.*?)\s*$", line)
        if pair:
            fields[pair.group(1)] = re.sub(r"^(['\"])(.*)\1$", r"\2", pair.group(2))
    return fields, data[match.end():], match.group(0).count("\n")


def _rows(data: str, first_line: int = 1) -> list[tuple[int, list[str]]]:
    if not isinstance(data, str):
        raise TemplateError(f"template data must be a string, got {type(data).__name__}")
    rows = []
    for lineno, line in enumerate(data.splitlines(), start=first_line):
        if not line.strip():
            continue
        fields = next(csv.reader([line], skipinitialspace=True))
        rows.append((lineno, [field.strip() for field in fields]))
    if not rows:
        raise TemplateError("template data has no lines")
    return rows


def _block(text: str, depth: int) -> str:
    return textwrap.indent(textwrap.dedent(text).strip("\n"), "    " * depth)
