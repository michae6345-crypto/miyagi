"""Read a saved page into what a link lesson is built from: title, site, author, sections, code blocks, readable text.

The eval's page reader, written to the any-link contract (shared/contracts/ANY-LINK.md): navigation, headers, footers,
sidebars, cookie banners, newsletter boxes, share bars, comments and dates are dropped before anything is counted, so
the content hash (events.link_content_hash) is of the readable text only and a page whose chrome changes keeps its
cache key. A github.com link is read as its README (Markdown). Pure functions on a string: no network.

    page = read_html(html, url)           # a web page
    page = read_markdown(md, url)         # a github.com repo (its README)
    page.refusal                          # None | "blocked" | "no_content"

The engine lane's own reader can replace this one: the runner takes any `read(text, url, kind) -> Page`.
"""
from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlsplit

from shared.contracts.events import (
    link_cache_key,
    link_content_hash,
    normalize_link_url,
)

# elements that are never the page's content
DROP_TAGS = frozenset({"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "iframe",
                       "button", "template", "time", "select", "input", "label", "dialog"})
# class / id / role words that mark chrome: cookie banners, newsletter boxes, sidebars, share bars, ads, comments
_CHROME = re.compile(
    r"(?:^|[\s_-])(cookie|consent|gdpr|banner|newsletter|subscribe|signup|sign-up|sidebar|side-bar|sidenav|breadcrumbs?|"
    r"toc|table-of-contents|share|social|advert|ads?|ad-slot|sponsor|promo|related|comments?|disqus|footer|header|"
    r"navbar|nav|menu|skip-link|edit-this-page|last-updated|byline-date|post-date|pagination|prev-next|feedback|"
    r"announcement|popup|modal|linenos|line-numbers|gutter|copy-button|headerlink)(?:$|[\s_-])", re.IGNORECASE)
_CHROME_ROLES = frozenset({"navigation", "banner", "contentinfo", "complementary", "search", "dialog"})
_VOID = frozenset({"br", "hr", "img", "meta", "link", "input", "source", "wbr", "area", "base", "col", "embed", "param",
                   "track"})
_BLOCKS = frozenset({"p", "li", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "dt", "dd", "td", "th", "tr",
                     "div", "section", "article", "main", "ol", "ul", "table"})
_PAYWALL = re.compile(r"(?:^|[\s_-])(paywall|regwall|login-wall|members-only|premium-content)(?:$|[\s_-])", re.IGNORECASE)
_PAYWALL_TEXT = re.compile(r"\b(sign in to (continue|read)|subscribe to (continue|read|unlock)|this (story|article|post) is "
                           r"for (paid )?(members|subscribers)|log in to view|create a free account to (continue|read))\b",
                           re.IGNORECASE)
_DATE_LINE = re.compile(r"^\s*(last (updated|modified)|updated|published|posted)( on)?\s*:?\s*\w+.{0,40}$", re.IGNORECASE)
_LANG = re.compile(r"(?:^|\s)(?:(?:language|lang|highlight-source|highlight)-|brush:\s*)([a-z0-9+#-]+)", re.IGNORECASE)
MIN_WORDS = 40  # less readable text than this (and no code) is "no_content"


@dataclass
class Code:
    text: str
    lang: str = ""
    section: int = 0  # index into Page.sections


@dataclass
class Section:
    heading: str
    level: int
    anchor: str = ""
    text: list[str] = field(default_factory=list)  # paragraphs and list items, in order
    ordered: list[str] = field(default_factory=list)  # items of numbered lists
    code: list[int] = field(default_factory=list)  # indexes into Page.code


@dataclass
class Page:
    url: str
    kind: str  # "web" | "github"
    title: str = ""
    site: str = ""
    author: str = ""
    sections: list[Section] = field(default_factory=list)
    code: list[Code] = field(default_factory=list)
    text: str = ""  # the readable text (what the content hash is of)
    refusal: str | None = None  # None, "blocked" or "no_content"

    @property
    def content_hash(self) -> str:
        return link_content_hash(self.text)

    @property
    def cache_key(self) -> str:
        return link_cache_key(self.kind, self.url, self.content_hash)

    @property
    def words(self) -> int:
        return len(self.text.split())


# --------------------------------------------------------------------------- a small DOM


@dataclass
class _Node:
    tag: str
    attrs: dict
    children: list = field(default_factory=list)  # _Node | str
    parent: _Node | None = None

    def cls(self) -> str:
        return " ".join(str(self.attrs.get(k) or "") for k in ("class", "id"))


class _Tree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {})
        self.cur = self.root
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and "content" in a:
                self.meta.setdefault(key, a["content"])
            return
        if tag == "title":
            self._in_title = True
        if tag in _VOID:
            if tag == "br":
                self.cur.children.append("\n")
            return
        if tag in ("p", "li") and self.cur.tag == tag:  # unclosed <p>/<li>
            self.cur = self.cur.parent or self.root
        n = _Node(tag, a, parent=self.cur)
        self.cur.children.append(n)
        self.cur = n

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        self.cur.children.append(data)


def _chrome(n: _Node, *, in_main: bool = False) -> bool:
    """Page chrome. Inside the page's <main> / <article>, a <header> is the article's own (its h1), not the site's."""
    if n.tag in DROP_TAGS and not (in_main and n.tag == "header"):
        return True
    if (n.attrs.get("role") or "").lower() in _CHROME_ROLES or "hidden" in n.attrs or n.attrs.get("aria-hidden") == "true":
        return True
    return bool(_CHROME.search(n.cls()))


def _text(n, *, keep_ws: bool = False) -> str:
    if isinstance(n, str):
        return n
    if n.tag != "pre" and _chrome(n) or n.tag in ("script", "style", "button"):
        return ""
    return "".join(_text(c, keep_ws=keep_ws) for c in n.children)


def _clean(s: str) -> str:
    return " ".join(htmllib.unescape(s).split())


def _main(root: _Node) -> _Node:
    """<main>, <article> or role=main when the page has one (the biggest), else <body>."""
    found: list[_Node] = []

    def walk(n: _Node) -> None:
        for c in n.children:
            if isinstance(c, _Node):
                if c.tag in ("main", "article") or (c.attrs.get("role") or "").lower() == "main":
                    found.append(c)
                walk(c)

    walk(root)
    if found:
        return max(found, key=lambda n: len(_text(n)))
    return root


def _code_text(pre: _Node) -> tuple[str, str]:
    lang = ""
    n: _Node | None = pre
    for _ in range(3):  # the class sits on <pre>, its <code>, or the highlight <div> around it
        if n is None:
            break
        if m := _LANG.search(n.cls()):
            lang = m.group(1).lower()
            break
        n = n.parent
    if not lang:
        for c in pre.children:
            if isinstance(c, _Node) and (m := _LANG.search(c.cls())):
                lang = m.group(1).lower()
    raw = htmllib.unescape(_text(pre, keep_ws=True))
    lines = raw.replace("\r\n", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(ln.rstrip() for ln in lines), lang


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def read_html(raw: str, url: str, *, status: int = 200) -> Page:
    kind = "github" if (urlsplit(url).hostname or "").lower().removeprefix("www.") == "github.com" else "web"
    t = _Tree()
    t.feed(raw)
    t.close()
    page = Page(url=normalize_link_url(url), kind=kind, site=_site(url))
    page.author = _clean(t.meta.get("author") or t.meta.get("article:author") or "")
    main = _main(t.root)
    in_main = main is not t.root
    paywalled = False
    cur = Section(heading="", level=1)
    page.sections.append(cur)
    text_parts: list[str] = []

    def add_text(s: str, ordered: bool = False) -> None:
        s = _clean(s)
        if not s or _DATE_LINE.match(s):
            return
        cur.text.append(s)
        if ordered:
            cur.ordered.append(s)
        text_parts.append(s)

    def walk(n: _Node, in_ol: bool = False) -> None:
        nonlocal cur, paywalled
        for c in n.children:
            if isinstance(c, str):
                if n.tag not in _BLOCKS or not c.strip():
                    continue
                add_text(c)
                continue
            if _PAYWALL.search(c.cls()):
                paywalled = True
                continue
            if c.tag == "pre":
                code, lang = _code_text(c)
                if code.strip():
                    page.code.append(Code(code, lang, len(page.sections) - 1))
                    cur.code.append(len(page.code) - 1)
                    text_parts.append(code)
                continue
            if _chrome(c, in_main=in_main):
                continue
            if c.tag in ("h1", "h2", "h3", "h4"):
                h = _clean(_text(c))
                if h:
                    cur = Section(heading=h.rstrip("¶#").strip(), level=int(c.tag[1]), anchor=c.attrs.get("id") or "")
                    if not cur.anchor and c.parent is not None and c.parent.tag == "section":
                        cur.anchor = c.parent.attrs.get("id") or ""
                    page.sections.append(cur)
                    text_parts.append(cur.heading)
                continue
            if c.tag in ("p", "li", "dt", "dd", "blockquote", "td", "th"):
                nested = [x for x in c.children if isinstance(x, _Node) and x.tag in ("pre", "ul", "ol")]
                if nested:  # an item with a code block or a sub-list: its own words, then those
                    add_text("".join(_text(x) for x in c.children if not (isinstance(x, _Node) and x.tag in ("pre", "ul", "ol"))),
                             ordered=(c.tag == "li" and in_ol))
                    walk(_Node("div", {}, nested, c), in_ol=in_ol)
                else:
                    add_text(_text(c), ordered=(c.tag == "li" and in_ol))
                continue
            walk(c, in_ol=(c.tag == "ol") or (in_ol and c.tag not in ("ul",)))

    walk(main)
    page.sections = [s for s in page.sections if s.heading or s.text or s.code]
    for i, s in enumerate(page.sections):
        for ci in s.code:
            page.code[ci].section = i
    page.text = "\n".join(text_parts)
    h1 = next((s.heading for s in page.sections if s.level == 1 and s.heading), "")
    page.title = re.sub(r"^\d+(?:\.\d+)*\.?\s+(?=\w)", "", _clean(_unsuffixed(t.meta.get("og:title") or "") or h1 or _unsuffixed(t.title)))
    if status in (401, 403, 451) or (paywalled or _PAYWALL_TEXT.search(page.text)) and page.words < 250 and not page.code:
        page.refusal = "blocked"
    elif page.words < MIN_WORDS and not page.code:
        page.refusal = "no_content"
    return page


# --------------------------------------------------------------------------- GitHub: the README (Markdown)

_FENCE = re.compile(r"^(\s*)(```+|~~~+)\s*([\w+#.-]*)")
_MD_HEAD = re.compile(r"^(#{1,4})\s+(.*?)\s*#*\s*$")
_MD_OL = re.compile(r"^\s*\d+[.)]\s+(.*)")
_MD_UL = re.compile(r"^\s*[-*+]\s+(.*)")
_MD_INLINE = re.compile(r"!\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])|<[^>]+>")  # images (badges) and inline HTML
_MD_LINK = re.compile(r"\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])")
_MD_REFDEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*\S+")  # [npm-url]: https://...


def read_markdown(md: str, url: str, *, status: int = 200) -> Page:
    kind = "github" if (urlsplit(url).hostname or "").lower().removeprefix("www.") == "github.com" else "web"
    page = Page(url=normalize_link_url(url), kind=kind, site=_site(url))
    cur = Section(heading="", level=1)
    page.sections.append(cur)
    text_parts: list[str] = []
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    para: list[str] = []

    def flush() -> None:
        if para:
            s = _clean(_MD_LINK.sub(r"\1", _MD_INLINE.sub("", " ".join(para))))
            if s:
                cur.text.append(s)
                text_parts.append(s)
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if m := _FENCE.match(ln):
            flush()
            fence, lang, body = m.group(2), m.group(3).lower(), []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence):
                body.append(lines[i])
                i += 1
            code = "\n".join(body).strip("\n")
            if code.strip():
                page.code.append(Code(code, lang, len(page.sections) - 1))
                cur.code.append(len(page.code) - 1)
                text_parts.append(code)
            i += 1
            continue
        if m := _MD_HEAD.match(ln):
            flush()
            h = _clean(_MD_LINK.sub(r"\1", _MD_INLINE.sub("", m.group(2))))
            if h:
                cur = Section(heading=h, level=len(m.group(1)), anchor=_slug(h))
                page.sections.append(cur)
                text_parts.append(h)
            i += 1
            continue
        if m := (_MD_OL.match(ln) or _MD_UL.match(ln)):
            flush()
            s = _clean(_MD_LINK.sub(r"\1", _MD_INLINE.sub("", m.group(1))))
            if s:
                cur.text.append(s)
                if _MD_OL.match(ln):
                    cur.ordered.append(s)
                text_parts.append(s)
            i += 1
            continue
        if not ln.strip() or _MD_REFDEF.match(ln):
            flush()
        else:
            para.append(ln.strip())
        i += 1
    flush()
    page.sections = [s for s in page.sections if s.heading or s.text or s.code]
    for k, s in enumerate(page.sections):
        for ci in s.code:
            page.code[ci].section = k
    page.text = "\n".join(text_parts)
    page.title = next((s.heading for s in page.sections if s.level == 1 and s.heading), "") or page.site.split("/")[-1]
    if status in (401, 403, 451):
        page.refusal = "blocked"
    elif page.words < MIN_WORDS and not page.code:
        page.refusal = "no_content"
    return page


def _unsuffixed(title: str) -> str:
    """"Using the Fetch API - Web APIs | MDN" -> "Using the Fetch API": a page title without the site's name."""
    return re.split(r"\s+[|—–·]\s+|\s+-\s+", title.strip())[0] if title.strip() else ""


def _site(url: str) -> str:
    parts = urlsplit(normalize_link_url(url))
    host = parts.hostname or ""
    if host == "github.com":
        segs = [s for s in parts.path.split("/") if s]
        return "github.com/" + "/".join(segs[:2]) if len(segs) >= 2 else host
    return host


def read(raw: str, url: str, kind: str = "", *, status: int = 200, fmt: str = "") -> Page:
    """A saved page: Markdown (a README) or HTML, by `fmt` ("md" / "html") or a sniff of the text."""
    md = fmt == "md" or (not fmt and not re.search(r"<(html|body|div|p|pre|h1)\b", raw[:4000], re.IGNORECASE))
    page = read_markdown(raw, url, status=status) if md else read_html(raw, url, status=status)
    if kind:
        page.kind = kind
    return page
