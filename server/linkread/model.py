"""What reading a link produces: an Extraction (blocks of headings, text, list items and code) or a LinkUnreadable.

Pure data, no I/O. `Extraction.text()` is the readable text a lesson is built from (and the content hash is of), in a
small markdown dialect: `#` headings, paragraphs, `-` / `1.` list items and fenced code blocks with their language.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from shared.contracts.events import link_cache_key, link_content_hash

BlockKind = Literal["heading", "text", "item", "code"]
UnreadableCode = Literal["unsupported", "blocked", "not_found", "offline", "busy", "unknown", "no_content"]


@dataclass
class Block:
    kind: BlockKind
    text: str
    level: int = 0  # heading: 1..6; item: nesting depth (0 = top level)
    lang: str | None = None  # code: the language the page names ("python", "bash"), lower case
    ordered: bool = False  # item: in a numbered list
    number: int = 0  # item: its number in a numbered list
    anchor: str | None = None  # heading: the id the page gives it (a #fragment)
    url: str | None = None  # the page this block came from (a GitHub docs file); None = the Extraction's url


@dataclass
class Extraction:
    kind: Literal["web", "github"]
    url: str  # what the learner pasted
    final_url: str  # where it ended after redirects (a web page) / the repo's page (github)
    title: str
    site: str  # "docs.python.org", "github.com/pallets/flask"
    blocks: list[Block]
    author: str | None = None
    description: str | None = None
    truncated: bool = False  # the page was longer than MAX_TEXT_CHARS: the blocks are its first sections
    github: dict | None = None  # github: owner, repo, ref, language, languages, files, files_truncated, docs

    # ------------------------------------------------------------------ the readable text and its key

    def text(self) -> str:
        return render(self.blocks)

    @property
    def content_hash(self) -> str:
        return link_content_hash(self.text())

    @property
    def cache_key(self) -> str:
        """Keyed on where the link ended (final_url), so a short link, a redirect and the page's own link share a lesson;
        normalize_link_url folds the remaining spellings (www., http, utm_*, a trailing slash, GitHub case and .git)."""
        return link_cache_key(self.kind, self.final_url or self.url, self.content_hash)

    # ------------------------------------------------------------------ counts the preview and the build use

    @property
    def code_blocks(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == "code"]

    @property
    def headings(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == "heading"]

    @property
    def words(self) -> int:
        return sum(len(b.text.split()) for b in self.blocks if b.kind != "code")

    def page_ref(self, block: Block) -> dict:
        """The contract's PageRef {url, heading} for a heading block (never the page's words beyond the heading)."""
        base = block.url or self.final_url
        base = base.split("#", 1)[0]
        return {"url": f"{base}#{block.anchor}" if block.anchor else base, "heading": block.text if block.kind == "heading" else None}

    def outline(self, max_lines: int = 60) -> str:
        """Headings, the code block count and each section's first line: what a small model judges teachability on."""
        out = [f"Title: {self.title}", f"Site: {self.site}", f"Code blocks: {len(self.code_blocks)}"]
        first_after: set[int] = set()
        for i, b in enumerate(self.blocks):
            if b.kind == "heading":
                out.append("#" * max(1, b.level) + " " + b.text)
                first_after.add(i + 1)
            elif i in first_after or i == 0:
                line = b.text.strip().splitlines()[0] if b.text.strip() else ""
                if line:
                    out.append(("    " if b.kind == "code" else "  ") + line[:160])
            if len(out) >= max_lines:
                break
        return "\n".join(out)

    def cut(self, max_chars: int) -> Extraction:
        """The first sections that fit in max_chars of text(), cut at a heading (a section boundary) when there is one
        in the second half; never mid-code-block. truncated is set when anything was dropped."""
        if len(self.text()) <= max_chars:
            return self
        kept: list[Block] = []
        size = 0
        last_heading = 0
        for b in self.blocks:
            n = len(render([b])) + 2
            if size + n > max_chars:
                break
            if b.kind == "heading":
                last_heading = len(kept)
            kept.append(b)
            size += n
        if last_heading > len(kept) // 2:
            kept = kept[:last_heading]
        if not kept and self.blocks:  # one block bigger than the budget: its start
            b = self.blocks[0]
            kept = [Block(b.kind, b.text[:max_chars], b.level, b.lang, b.ordered, b.number, b.anchor, b.url)]
        return Extraction(self.kind, self.url, self.final_url, self.title, self.site, kept, self.author,
                          self.description, True, self.github)


class LinkUnreadable(Exception):
    """The link cannot become a lesson. code: a LookupError ("unsupported", "blocked", "not_found", "offline", "busy",
    "unknown") or "no_content" (a BuildFailCode: the page has no readable text). reason: one plain line for the
    learner. title / site: what is known of the page (a no_content page still has a title)."""

    def __init__(self, code: UnreadableCode, reason: str, *, title: str | None = None, site: str | None = None,
                 final_url: str | None = None) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.title = title
        self.site = site
        self.final_url = final_url

    @property
    def fail_code(self) -> str:
        """The lesson.building failCode for this refusal."""
        return {"blocked": "blocked", "no_content": "no_content", "offline": "network", "busy": "network",
                "not_found": "no_content", "unsupported": "blocked"}.get(self.code, "unknown")


# ---------------------------------------------------------------------------------------------- rendering


def _fence(code: str) -> str:
    longest = max((len(m) for m in re.findall(r"`{3,}", code)), default=0)
    return "`" * max(3, longest + 1)


def render(blocks: list[Block]) -> str:
    parts: list[str] = []
    prev: Block | None = None
    for b in blocks:
        if b.kind == "heading":
            s = "#" * min(6, max(1, b.level)) + " " + b.text
        elif b.kind == "item":
            mark = f"{b.number or 1}." if b.ordered else "-"
            s = "  " * b.level + f"{mark} {b.text}"
        elif b.kind == "code":
            f = _fence(b.text)
            s = f"{f}{b.lang or ''}\n{b.text}\n{f}"
        else:
            s = b.text
        sep = "\n" if prev is not None and prev.kind == "item" and b.kind == "item" else "\n\n"
        parts.append(s if not parts else sep + s)
        prev = b
    return "".join(parts)


def slug(text: str) -> str:
    """GitHub's heading anchor: lower case, punctuation dropped (but - and _), spaces to hyphens."""
    s = text.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")
