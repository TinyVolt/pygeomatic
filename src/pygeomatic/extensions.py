"""Dynamic extension registration from manifest.json files.

Geomatic extensions are async `GeometricFunction`s the app loads into
sandboxed workers (src/lib/geomatic/functions/extensionLoader.ts). pygeomatic
never needs their `compute`: emitting `out = \\keyword args...` only needs the
signature metadata, and the extension manifest carries exactly that:

    {"name": ..., "version": ..., "extensions": [
        {"name", "keyword", "outputType",
         "parameters": [{"name", "type", "default"?, "variadic"?}]}, ...]}

`load_extensions(source)` reads a manifest (local path or URL) and registers a
pure graph-record function per entry into the live REGISTRY and the package
namespace, so `gm.la_vec2d(...)`, `system_prompt()` and validation all pick
them up immediately. `unload_extensions(source)` removes them again.

Rules:
- a required parameter must OMIT `default` in the manifest (`default: null`
  also counts as omitted); a present non-null `default` makes it optional
- colliding with a builtin keyword is an error; re-loading the same manifest
  source replaces its previous functions; two different sources claiming the
  same keyword is an error
- outputs are record-only nodes of the declared outputType (`.numeric` None);
  only the extension's `main` output is addressable — aux composite keys
  (hidden helper points etc.) exist host-side only
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Callable, ClassVar, Optional

from .nodes import GNode, NODE_CLASSES
from .prompting import python_name
from .registry import P, REGISTRY, UNSET, geomatic_fn
from .store import IDENTIFIER_RE

EXTENSION_CATEGORY = "Extensions"

# manifest source → keywords it registered (provenance for unload/replace)
_LOADED: dict[str, list[str]] = {}
# keyword → manifest source that owns it
_KEYWORD_SOURCE: dict[str, str] = {}
# dynamically created GNode subclasses for outputTypes outside NODE_CLASSES
_CUSTOM_NODE_CLASSES: dict[str, type[GNode]] = {}


class ManifestError(ValueError):
    """The manifest is missing, malformed, or conflicts with loaded functions."""


# ---------------------------------------------------------------------------
# Manifest reading & validation
# ---------------------------------------------------------------------------


def _fetch_manifest(source: str) -> Any:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return json.loads(Path(source).read_text())


def _parse_params(keyword: str, raw_params: Any) -> list[P]:
    if not isinstance(raw_params, list):
        raise ManifestError(f"extension {keyword!r}: 'parameters' must be a list")
    params: list[P] = []
    for i, rp in enumerate(raw_params):
        if not isinstance(rp, dict) or not rp.get("name") or not rp.get("type"):
            raise ManifestError(
                f"extension {keyword!r}: parameter {i} must have 'name' and 'type'"
            )
        variadic = bool(rp.get("variadic"))
        if variadic and i != len(raw_params) - 1:
            raise ManifestError(
                f"extension {keyword!r}: variadic parameter {rp['name']!r} must be last"
            )
        # A required param omits `default` (or sets it to null); a present
        # non-null `default` makes the param optional.
        default = rp["default"] if rp.get("default") is not None else UNSET
        params.append(P(name=rp["name"], type=rp["type"], variadic=variadic, default=default))

    # The DSL is positional: once a param is optional, everything after it
    # must be optional too (variadic aside), or omission is ambiguous.
    seen_default = False
    for p in params:
        if p.variadic:
            continue
        if p.has_default:
            seen_default = True
        elif seen_default:
            raise ManifestError(
                f"extension {keyword!r}: required parameter {p.name!r} follows an "
                "optional one — defaults must be trailing"
            )
    return params


def _validate_manifest(source: str, manifest: Any) -> list[dict]:
    if not isinstance(manifest, dict) or not manifest.get("name") or not manifest.get("version"):
        raise ManifestError(f"{source}: manifest must have 'name' and 'version'")
    exts = manifest.get("extensions")
    if not isinstance(exts, list) or not exts:
        raise ManifestError(f"{source}: manifest must list at least one extension")
    specs: list[dict] = []
    seen: set[str] = set()
    for ext in exts:
        if not isinstance(ext, dict):
            raise ManifestError(f"{source}: each extension must be an object")
        keyword = ext.get("keyword")
        if not keyword or not ext.get("name") or not ext.get("outputType"):
            raise ManifestError(
                f"{source}: each extension must have 'name', 'keyword' and 'outputType'"
            )
        if not IDENTIFIER_RE.match(keyword):
            raise ManifestError(
                f"{source}: keyword {keyword!r} is not a valid geomatic identifier "
                "(letters, digits, dashes; must start with a letter)"
            )
        if keyword in seen:
            raise ManifestError(f"{source}: duplicate keyword {keyword!r} in manifest")
        seen.add(keyword)
        specs.append(
            {
                "keyword": keyword,
                "name": ext["name"],
                "output_type": ext["outputType"],
                "params": _parse_params(keyword, ext.get("parameters", [])),
            }
        )
    return specs


# ---------------------------------------------------------------------------
# Record-only function construction
# ---------------------------------------------------------------------------


def _custom_node_class(type_name: str) -> type[GNode]:
    cls = _CUSTOM_NODE_CLASSES.get(type_name)
    if cls is None:
        cls = type(
            type_name,
            (GNode,),
            {"__annotations__": {"type": ClassVar[str]}, "type": type_name, "__module__": __name__},
        )
        _CUSTOM_NODE_CLASSES[type_name] = cls
    return cls


def _output_factory(output_type: str) -> Callable[[], GNode]:
    cls = NODE_CLASSES.get(output_type) or _custom_node_class(output_type)
    new = getattr(cls, "_new", None)
    if callable(new):
        return lambda: new()
    return lambda: cls()


def _pkg():
    import pygeomatic

    return pygeomatic


def _register_one(spec: dict, source: str) -> str:
    keyword = spec["keyword"]
    factory = _output_factory(spec["output_type"])

    def _impl(*bound):
        return factory()

    _impl.__name__ = python_name(keyword)
    _impl.__doc__ = f"Extension \\{keyword} (record-only; loaded from {source})"

    wrapper = geomatic_fn(
        keyword=keyword,
        name=spec["name"],
        output=spec["output_type"],
        params=spec["params"],
        category=EXTENSION_CATEGORY,
        is_async=True,
    )(_impl)
    setattr(_pkg(), python_name(keyword), wrapper)
    _KEYWORD_SOURCE[keyword] = source
    return keyword


def _unregister_keywords(keywords: list[str]) -> None:
    pkg = _pkg()
    for kw in keywords:
        REGISTRY.pop(kw, None)
        _KEYWORD_SOURCE.pop(kw, None)
        py = python_name(kw)
        if getattr(pkg, py, None) is not None:
            delattr(pkg, py)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_extensions(source: str) -> list[str]:
    """Load a manifest.json (local path or URL) and register its extensions.

    Returns the registered keywords. Re-loading a source replaces its previous
    functions; builtin collisions and cross-source collisions raise.
    """
    specs = _validate_manifest(source, _fetch_manifest(source))

    # Validate all collisions before touching the registry (atomic load).
    for spec in specs:
        kw = spec["keyword"]
        owner = _KEYWORD_SOURCE.get(kw)
        if kw in REGISTRY and owner is None:
            raise ManifestError(
                f"{source}: keyword {kw!r} collides with a builtin geomatic command"
            )
        if owner is not None and owner != source:
            raise ManifestError(
                f"{source}: keyword {kw!r} is already provided by {owner!r} — "
                "unload that manifest first"
            )

    # Replace: drop everything this source registered previously.
    previous = _LOADED.pop(source, None)
    if previous:
        _unregister_keywords(previous)

    keywords = [_register_one(spec, source) for spec in specs]
    _LOADED[source] = keywords
    return keywords


def unload_extensions(source: str) -> list[str]:
    """Remove every function registered from `source`. Returns their keywords."""
    keywords = _LOADED.pop(source, None)
    if keywords is None:
        known = ", ".join(sorted(_LOADED)) or "none"
        raise KeyError(f"no extensions loaded from {source!r} (loaded sources: {known})")
    _unregister_keywords(keywords)
    return keywords


def loaded_extensions() -> dict[str, list[str]]:
    """Currently loaded manifest sources and the keywords each provides."""
    return {src: list(kws) for src, kws in _LOADED.items()}
