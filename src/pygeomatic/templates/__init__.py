"""gm.templates — turn plain data into a complete pygeomatic article.

Each template takes the author's data as text and returns the full markdown
source of an article (prose plus a ```pygeomatic block), ready for
`compile_article`. Nothing is recorded on any store: the returned source is
compiled like any hand-written article.

    source = gm.templates.flash_card("What is 2+2?, 4, Count them, 3, 5")
    compiled = gm.compile_article(source)

One module per template.
"""

from ._common import TemplateError
from .flash_card import flash_card
from .flowchart import flowchart

__all__ = ["TemplateError", "flash_card", "flowchart"]
