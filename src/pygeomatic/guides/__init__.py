"""Topic guides for LLMs writing pygeomatic: one markdown file per topic.

Each file starts with a `# Title` line followed by a one-sentence summary
paragraph; `list_guides()` returns those, `read_guide(name)` the whole file.
"""

from __future__ import annotations

from importlib import resources


def _files() -> dict[str, str]:
    root = resources.files(__name__)
    return {
        entry.name[: -len(".md")]: entry.read_text(encoding="utf-8")
        for entry in root.iterdir()
        if entry.name.endswith(".md")
    }


def _summary(text: str) -> str:
    lines = text.splitlines()
    for line in lines[1:]:
        if line.strip():
            return line.strip()
    return ""


def list_guides() -> list[dict[str, str]]:
    """Every guide as `{"name", "title", "summary"}`, sorted by name."""
    return [
        {
            "name": name,
            "title": text.splitlines()[0].lstrip("# ").strip(),
            "summary": _summary(text),
        }
        for name, text in sorted(_files().items())
    ]


def read_guide(name: str) -> str:
    """The full markdown of one guide. Raises KeyError for an unknown name."""
    files = _files()
    if name not in files:
        raise KeyError(f"no guide named {name!r}; available: {', '.join(sorted(files))}")
    return files[name]
