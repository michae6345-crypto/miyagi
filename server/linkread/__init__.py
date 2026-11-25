"""Any link (shared/contracts/ANY-LINK.md): read a web page or a GitHub repo into teachable text.

    ex = await read_link(url)            # Extraction, or raises LinkUnreadable(code, reason)
    ex.text()                            # the readable text (markdown-ish: headings, paragraphs, items, fenced code)
    ex.cache_key                         # link_cache_key(kind, url, link_content_hash(text))
    ex.outline()                         # headings + code count + first lines, for a small model's verdict
    ex.page_ref(heading_block)           # StepSummary.pageRef {url#anchor, heading}
    payload, ex = await link_preview(url, reqId)   # link.preview (kind web / github), heuristic teachable verdict

Modules: fetch.py (netsafe fetch, robots.txt, status and content-type rules), html.py (readability-style main content,
standard library only), markdown.py (README / docs markdown, rst, plain text), github.py (public API + raw files, no
token), preview.py (LinkPreview from an extraction), model.py (Block, Extraction, LinkUnreadable).
"""

from .fetch import link_kind, read_link
from .model import Block, Extraction, LinkUnreadable
from .preview import preview as link_preview
from .preview import preview_error, preview_from, verdict

__all__ = ["Block", "Extraction", "LinkUnreadable", "link_kind", "link_preview", "preview_error", "preview_from",
           "read_link", "verdict"]
