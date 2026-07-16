"""Mirror of src/lib/geomatic/functions/implementations/property-functions.ts.

In TypeScript this file generates one hidden `_prop-<field>` accessor function
per distinct property name; those back the DSL's dot access (`p.x`,
`circle.center`). In Python, dot access is native: the node classes in
nodes.py expose exactly the whitelisted properties, each returning a node that
serializes to the `base.field` argument form. So there are no standalone
functions here — only the derived list of accessor keywords, used by the
parity test against registry.json.
"""

from __future__ import annotations

from ...nodes import NODE_PROPERTIES


def all_property_names() -> list[str]:
    """Every distinct accessible property name (mirror of allPropertyNames())."""
    names: set[str] = set()
    for props in NODE_PROPERTIES.values():
        names.update(props.keys())
    return sorted(names)


PROPERTY_ACCESSOR_KEYWORDS = [f"_prop-{name}" for name in all_property_names()]
