"""A web page's main content as blocks, readability-style, with the standard library only (html.parser).

No new dependency: bs4 / lxml / readability-lxml / trafilatura are not in server/pyproject.toml, and a page is small
(at most 2 MB is read), so a hand tree over html.parser is enough. Steps:

1. Parse into a light tree (implied end tags for p / li / td ... the common cases).
2. Read the head: <title>, og:title, og:site_name, author (meta, article:author, JSON-LD, a byline), JSON-LD
   isAccessibleForFree, canonical.
3. Look for a paywall or a sign-in wall BEFORE anything is dropped (its markers are often in the parts dropped next).
4. Drop what is never content: script, style, nav, aside, footer, forms, svg, iframes, images, hidden elements, and
   elements whose class / id / role says cookie banner, share bar, sidebar, comments, related posts, ads, menus.
5. Pick the main element: [itemprop=articleBody], the largest <article>, <main> / [role=main], a content-looking
   class or id, else the element whose paragraphs score best (text length and commas, less link text).
6. Walk it into blocks: h1-h6 headings (with their id as the anchor), paragraphs, list items (ordered, numbered,
   nested), and <pre> code kept verbatim with the language the page names (class language-x / lang-x / brush: x /
   highlight-x / sourceCode x, data-lang). Inline <code> becomes `code`. Links keep their text only. Images dropped.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .model import Block

log = logging.getLogger("server.linkread")

MAX_DEPTH = 200  # elements deeper than this are flattened into their parent (the walk below recurses per level)
VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
DROP_TAGS = frozenset("script style noscript template svg canvas iframe frame frameset object embed nav aside "
                      "footer form time button select textarea input label dialog img picture video audio map "
                      "figure-img math head".split())
HEADINGS = {f"h{i}": i for i in range(1, 7)}
BLOCK_TAGS = frozenset("p div section article main header blockquote dl dt dd table thead tbody tfoot tr td th "
                       "caption figure figcaption details summary hr address center ul ol li h1 h2 h3 h4 h5 h6 "
                       "pre body html".split())
_SAME_CLOSES = {"p": {"p"}, "li": {"li"}, "dt": {"dt", "dd"}, "dd": {"dt", "dd"}, "tr": {"tr"}, "td": {"td", "th"},
                "th": {"td", "th"}, "option": {"option"}}
_STOPS = {"p": frozenset(BLOCK_TAGS - {"p"}) | {"button", "td", "th"}, "li": frozenset({"ul", "ol"}),
          "dt": frozenset({"dl"}), "dd": frozenset({"dl"}), "tr": frozenset({"table", "thead", "tbody", "tfoot"}),
          "td": frozenset({"tr", "table"}), "th": frozenset({"tr", "table"}), "option": frozenset({"select"})}
_P_CLOSERS = frozenset("p div section article ul ol pre table blockquote h1 h2 h3 h4 h5 h6 header footer nav "
                       "aside form dl figure hr main details".split())

_UNLIKELY = re.compile(
    r"(?:^|[\s_-])(cookie|cookies|consent|gdpr|banner|newsletter|subscribe|signup|share|sharing|social|related|recommended|"
    r"recommendations|sidebar|comments?|disqus|breadcrumbs?|pagination|pager|toc|table-of-contents|menu|navbar|nav|"
    r"masthead|footer|header|advert|advertisement|ads?|sponsor(ed)?|promo|popup|modal|skip-link|skip|visually-hidden|"
    r"sr-only|edit-on-github|feedback|rating|copy|clipboard|tags|author-bio|bio|announcement|toolbar|language-name)"
    r"(?=$|[\s_-])", re.IGNORECASE)
_ALWAYS_DROP = re.compile(r"(?:^|[\s_-])(entry-meta|post-meta|article-meta|posted-on|byline|dateline|timestamp|post-date|"
                          r"entry-date|published-date|reading-time|headerlink|anchorjs-link|permalink)(?=$|[\s_-])|"
                          r"(?:^|\s)meta(?=$|\s)", re.IGNORECASE)  # dates and bylines change the content hash, not the lesson
_LIKELY = re.compile(r"(?:^|[\s_-])(article|body|content|main|post|entry|markdown|prose|documentation|rst-content|"
                     r"page-content|blog-post|story)(?=$|[\s_-])", re.IGNORECASE)
_DROP_ROLES = frozenset({"navigation", "banner", "contentinfo", "complementary", "dialog", "alertdialog", "search",
                         "menu", "menubar", "toolbar"})
_PAYWALL_CLASS = re.compile(r"(?:^|[\s_-])(paywall|piano|tp-container|subscriber-only|subscribers-only|premium-content|"
                            r"metered|meteredcontent|regwall|registration-wall|login-wall|loginwall|gated|gated-content|"
                            r"members-only|locked-content)", re.IGNORECASE)
_PAYWALL_TEXT = re.compile(
    r"subscribe (now )?to (continue|keep) reading|to continue reading,? (please )?(subscribe|sign in|log in)|"
    r"(sign|log) in to (continue|read|keep reading|view|access)|this (article|story|post|content) is (only )?"
    r"(available|for|reserved for) (to )?(paid )?(subscribers|members)|members[- ]only (content|article|post)|"
    r"create a free account to (continue|read|keep reading)|already a (subscriber|member)\?|"
    r"you('ve| have) reached your (free )?(article )?limit|unlock this (article|story|post)", re.IGNORECASE)
_LANG_PATTERNS = (
    re.compile(r"(?:^|\s)(?:language|lang)-([\w+#.-]+)", re.IGNORECASE),
    re.compile(r"(?:^|\s)brush:\s*([\w+#.-]+)", re.IGNORECASE),
    re.compile(r"(?:^|\s)highlight-(?:source-)?([\w+#.-]+)", re.IGNORECASE),
    re.compile(r"(?:^|\s)sourceCode\s+([\w+#.-]+)", re.IGNORECASE),
)
_NOT_LANGS = frozenset({"notranslate", "default", "none", "plain", "highlight", "sourcecode", "source", "code", "hljs",
                        "prettyprint", "linenums", "line-numbers", "nohighlight", "wrap", "example", "js-file-line"})
_LANG_ALIASES = {"py": "python", "python3": "python", "py3": "python", "js": "javascript", "ts": "typescript",
                 "sh": "bash", "shell": "bash", "zsh": "bash", "console": "console", "shell-session": "console",
                 "sh-session": "console", "ps": "powershell", "ps1": "powershell", "yml": "yaml", "rb": "ruby",
                 "rs": "rust", "golang": "go", "c++": "cpp", "cs": "csharp", "c#": "csharp", "md": "markdown",
                 "htm": "html", "xhtml": "html", "pycon": "pycon", "ipython3": "ipython", "jsonc": "json"}


def norm_lang(lang: str | None) -> str | None:
    if not lang:
        return None
    l = lang.strip().lower().strip(".:")
    if not l or l in _NOT_LANGS or len(l) > 24:
        return None
    return _LANG_ALIASES.get(l, l)


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    parent: Node | None = None
    children: list = field(default_factory=list)  # Node | str
    depth: int = 0

    def cls(self) -> str:
        return f"{self.attrs.get('class', '')} {self.attrs.get('id', '')}"

    def iter(self):
        """This node and every element under it, in document order (no recursion: a deep page cannot overflow)."""
        stack: list[Node] = [self]
        while stack:
            n = stack.pop()
            yield n
            stack.extend(c for c in reversed(n.children) if isinstance(c, Node))

    def text(self) -> str:
        return "".join(_texts(self))


_INVISIBLE = frozenset({"script", "style", "template", "noscript", "head"})


def _texts(node: Node, skip: frozenset[str] = frozenset()):
    stack: list = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, str):
            yield n
            continue
        if n.tag in skip:
            continue
        stack.extend(reversed(n.children))


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.cur = self.root
        self.ld_json: list[str] = []
        self._in_ld = False

    def _open_tags(self) -> list[str]:
        out, n = [], self.cur
        while n is not None:
            out.append(n.tag)
            n = n.parent
        return out

    def _close(self, tag: str, stop_at: frozenset[str] = frozenset()) -> bool:
        n = self.cur
        while n is not None and n is not self.root:
            if n.tag == tag:
                self.cur = n.parent or self.root
                return True
            if n.tag in stop_at:
                return False
            n = n.parent
        return False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in _SAME_CLOSES:
            self._implied_close(_SAME_CLOSES[tag], _STOPS[tag])
        if tag in _P_CLOSERS:
            self._implied_close({"p"}, _STOPS["p"])
        if tag == "script" and "ld+json" in a.get("type", "").lower():
            self._in_ld = True
        if self.cur.depth >= MAX_DEPTH:
            return  # a page nested this deep is broken or hostile: its deeper tags are ignored (their text is kept)
        node = Node(tag, a, self.cur, depth=self.cur.depth + 1)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def _implied_close(self, tags: set[str], stop: frozenset[str]) -> None:
        """<li> after an open <li>, <p> after an open <p>, a <div> inside an open <p>: close the open one (as HTML does),
        unless a stop tag (the list, the table, another block) is in between."""
        n = self.cur
        while n is not None and n is not self.root:
            if n.tag in tags:
                self.cur = n.parent or self.root
                return
            if n.tag in stop:
                return
            n = n.parent

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID and self.cur.tag == tag.lower():
            self.cur = self.cur.parent or self.root

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script":
            self._in_ld = False
        if tag in VOID:
            return
        if tag == "p" and not self._close("p", frozenset(BLOCK_TAGS - {"p"})):
            return
        self._close(tag)

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self.ld_json.append(data)
        if data:
            self.cur.children.append(data)


def parse(html: str) -> tuple[Node, list[str]]:
    b = _TreeBuilder()
    try:
        b.feed(html)
        b.close()
    except Exception as e:  # noqa: BLE001  html.parser is lenient; a broken page keeps what was built
        log.info("linkread: html parse stopped early: %s", type(e).__name__)
    return b.root, ["".join(b.ld_json)] if b.ld_json else []


# ------------------------------------------------------------------------------------------------ the head


def _ws(s: str) -> str:
    return " ".join((s or "").split())


def _meta(root: Node) -> dict[str, str]:
    out: dict[str, str] = {}
    for n in root.iter():
        if n.tag == "meta":
            key = (n.attrs.get("property") or n.attrs.get("name") or n.attrs.get("itemprop") or "").lower()
            if key and "content" in n.attrs and key not in out:
                out[key] = _ws(n.attrs["content"])
        elif n.tag == "link" and "canonical" in n.attrs.get("rel", "").lower() and "canonical" not in out:
            out["canonical"] = n.attrs.get("href", "")
        elif n.tag == "title" and "title" not in out:
            out["title"] = _ws(n.text())
    return out


def _ld_objects(ld: list[str]) -> list[dict]:
    out: list[dict] = []
    for raw in ld:
        for chunk in re.split(r"(?<=[}\]])\s*(?=[\[{])", raw.strip()) if raw.strip() else []:
            try:
                v = json.loads(chunk)
            except (ValueError, RecursionError):
                continue
            stack = [v]
            while stack and len(out) < 50:
                x = stack.pop()
                if isinstance(x, list):
                    stack.extend(x)
                elif isinstance(x, dict):
                    out.append(x)
                    if isinstance(x.get("@graph"), list):
                        stack.extend(x["@graph"])
    return out


def _ld_author(objs: list[dict]) -> str | None:
    for o in objs:
        a = o.get("author")
        if isinstance(a, list) and a:
            a = a[0]
        if isinstance(a, dict) and isinstance(a.get("name"), str):
            return _ws(a["name"])
        if isinstance(a, str) and not a.startswith("http"):
            return _ws(a)
    return None


def _not_free(objs: list[dict]) -> bool:
    for o in objs:
        v = o.get("isAccessibleForFree")
        if v is False or (isinstance(v, str) and v.strip().lower() == "false"):
            return True
    return False


_BYLINE = re.compile(r"(?:^|[\s_-])(byline|author|post-author|entry-author|author-name)(?=$|[\s_-])", re.IGNORECASE)


def _byline(root: Node) -> str | None:
    for n in root.iter():
        if n.attrs.get("rel", "").lower() == "author" or n.attrs.get("itemprop") == "author" or _BYLINE.search(n.cls()):
            t = _ws(n.text())
            t = re.sub(r"^(by|written by|posted by)\s+", "", t, flags=re.IGNORECASE)
            if 2 <= len(t) <= 60 and not re.search(r"\d{4}|http", t):
                return t
    return None


def _strip_site_suffix(title: str, site_names: list[str]) -> str:
    for sep in (" | ", " - ", " — ", " – ", " · ", " :: "):
        if sep in title:
            head, _, tail = title.rpartition(sep)
            if head and (any(s and s.lower() in tail.lower() for s in site_names) or len(tail) < len(head) // 2 + 4):
                return head.strip()
    return title


# ------------------------------------------------------------------------------------------------ walls


def wall_reason(root: Node, ld: list[dict], main_text_len: int) -> str | None:
    """A paywall or a sign-in wall: the plain reason, or None. Markers alone are not enough when the page still shows
    a full article (a free article with a 'Subscribe to our newsletter' box); isAccessibleForFree: false is."""
    if _not_free(ld):
        return "This page is behind a paywall, so I can't read it."
    has_password = any(n.tag == "input" and n.attrs.get("type", "").lower() == "password" for n in root.iter())
    paywall_box = any(n is not root and _PAYWALL_CLASS.search(n.cls()) for n in root.iter())
    body_text = _ws("".join(_texts(root, skip=_INVISIBLE)))
    paywall_words = bool(_PAYWALL_TEXT.search(body_text))
    if has_password and main_text_len < 1500:
        return "This page needs a sign-in, so I can't read it."
    if (paywall_box or paywall_words) and main_text_len < 2500:
        return "This page is behind a paywall or a sign-in, so I can't read it."
    return None


# ------------------------------------------------------------------------------------------------ cleaning


def _hidden(n: Node) -> bool:
    a = n.attrs
    if "hidden" in a or a.get("aria-hidden", "").lower() == "true":
        return True
    style = a.get("style", "").replace(" ", "").lower()
    return "display:none" in style or "visibility:hidden" in style


def _droppable(n: Node, in_content: bool) -> bool:
    if n.tag in DROP_TAGS:
        return True
    if n.tag == "header" and not in_content:
        return True
    if _hidden(n):
        return True
    if n.attrs.get("role", "").lower() in _DROP_ROLES:
        return True
    if n.tag in ("pre", "code") or n.tag in HEADINGS:
        return False
    c = n.cls()
    if _ALWAYS_DROP.search(c):
        return True
    return bool(c.strip()) and bool(_UNLIKELY.search(c)) and not _LIKELY.search(c)


def clean(node: Node, in_content: bool = False) -> None:
    keep: list = []
    for c in node.children:
        if isinstance(c, str):
            keep.append(c)
            continue
        if _droppable(c, in_content):
            continue
        clean(c, in_content or c.tag in ("article", "main") or c.attrs.get("role") == "main")
        keep.append(c)
    node.children = keep


# ------------------------------------------------------------------------------------------------ the main element


def _text_len(n: Node) -> int:
    return len(_ws(n.text()))


def _link_density(n: Node) -> float:
    total = _text_len(n) or 1
    links = sum(len(_ws(a.text())) for a in n.iter() if a.tag == "a")
    return min(1.0, links / total)


_CONTENT_HINT = re.compile(r"(?:^|[\s_-])(post-content|entry-content|article-content|article-body|post-body|"
                           r"markdown-body|rst-content|main-content|page-content|content|documentation|docs-content|"
                           r"prose|blog-post|story-body)(?=$|[\s_-])", re.IGNORECASE)


def main_node(root: Node) -> Node:
    body = next((n for n in root.iter() if n.tag == "body"), root)
    total = _text_len(body) or 1
    for n in body.iter():
        if n.attrs.get("itemprop") == "articleBody" and _text_len(n) > 200:
            return n
    articles = [n for n in body.iter() if n.tag == "article"]
    if articles:
        best = max(articles, key=_text_len)
        if _text_len(best) >= 0.3 * total or len(articles) <= 2 and _text_len(best) > 400:
            return best
    for n in body.iter():
        if (n.tag == "main" or n.attrs.get("role") == "main") and _text_len(n) > 200:
            return n
    hinted = [n for n in body.iter() if n.tag in ("div", "section") and _CONTENT_HINT.search(n.cls())]
    hinted = [n for n in hinted if _text_len(n) >= 0.3 * total]
    if hinted:
        return max(hinted, key=lambda n: (_text_len(n) * (1 - _link_density(n)), -_depth(n)))
    return _scored(body)


def _depth(n: Node) -> int:
    d = 0
    while n.parent is not None:
        d, n = d + 1, n.parent
    return d


def _scored(body: Node) -> Node:
    scores: dict[int, float] = {}
    nodes: dict[int, Node] = {}
    for p in body.iter():
        if p.tag not in ("p", "pre", "td", "li") or p.parent is None:
            continue
        t = _ws(p.text())
        if len(t) < 25 and p.tag != "pre":
            continue
        s = 1 + t.count(",") + min(len(t) / 100, 3) + (3 if p.tag == "pre" else 0)
        for up, share in ((p.parent, 1.0), (p.parent.parent if p.parent else None, 0.5)):
            if up is not None:
                scores[id(up)] = scores.get(id(up), 0) + s * share
                nodes[id(up)] = up
    if not scores:
        return body
    best = max(nodes.values(), key=lambda n: scores[id(n)] * (1 - _link_density(n)))
    return best


# ------------------------------------------------------------------------------------------------ blocks


def code_lang(pre: Node) -> str | None:
    cands = [pre] + [c for c in pre.iter() if c.tag == "code"][:1]
    up = pre.parent
    for _ in range(3):
        if up is None:
            break
        cands.append(up)
        up = up.parent
    for n in cands:
        for key in ("data-lang", "data-language", "lang"):
            if l := norm_lang(n.attrs.get(key)):
                return l
        c = n.attrs.get("class", "")
        for pat in _LANG_PATTERNS:
            for m in pat.finditer(c):
                if l := norm_lang(m.group(1)):
                    return l
    return None


def _pre_text(pre: Node) -> str:
    t = "".join(_texts(pre)).replace("\r\n", "\n").replace(" ", " ")
    lines = t.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(l.rstrip() for l in lines)


class _Walker:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.buf: list[str] = []
        self.list_stack: list[list] = []  # [ordered, next number]
        self.pending_anchor: str | None = None

    def flush(self) -> None:
        t = _ws("".join(self.buf))
        self.buf = []
        if t:
            self.blocks.append(Block("text", t))

    def inline(self, n: Node) -> str:
        out: list[str] = []
        for c in n.children:
            if isinstance(c, str):
                out.append(c)
            elif c.tag == "br":
                out.append(" ")
            elif c.tag == "code":
                t = _ws("".join(_texts(c)))
                out.append(f"`{t}`" if t else "")
            elif c.tag in ("ul", "ol", "pre") or c.tag in HEADINGS:
                continue  # walked as blocks of their own
            elif c.tag in BLOCK_TAGS:
                out.append(" " + self.inline(c) + " ")
            else:
                out.append(self.inline(c))
        return "".join(out)

    def walk(self, n: Node) -> None:
        for c in n.children:
            if isinstance(c, str):
                self.buf.append(c)
                continue
            tag = c.tag
            if tag in HEADINGS:
                self.flush()
                t = _ws(self.inline(c))
                if t:
                    anchor = c.attrs.get("id") or next((a.attrs.get("id") or a.attrs.get("name") for a in c.iter()
                                                        if a is not c and (a.attrs.get("id") or a.attrs.get("name"))), None)
                    if not anchor and c.parent is not None and c.parent.tag == "section":
                        anchor = c.parent.attrs.get("id")
                    t = re.sub(r"\s*[#¶§]\s*$", "", t)  # a "#" / pilcrow permalink after the heading
                    self.blocks.append(Block("heading", t, level=HEADINGS[tag], anchor=anchor or None))
            elif tag == "pre":
                self.flush()
                code = _pre_text(c)
                if code.strip():
                    self.blocks.append(Block("code", code, lang=code_lang(c)))
            elif tag in ("ul", "ol"):
                self.flush()
                self.list_stack.append([tag == "ol", _start(c)])
                self.walk_list(c)
                self.list_stack.pop()
            elif tag == "code" and not self.buf_has_text() and _is_block_code(c):
                self.flush()
                self.blocks.append(Block("code", _pre_text(c), lang=code_lang(c)))
            elif tag == "br":
                self.buf.append(" ")
            elif tag == "hr":
                self.flush()
            elif tag == "tr":
                self.flush()
                cells = [_ws(self.inline(td)) for td in c.children if isinstance(td, Node) and td.tag in ("td", "th")]
                row = " | ".join(x for x in cells if x)
                if row:
                    self.blocks.append(Block("text", row))
            elif tag == "code":
                t = _ws("".join(_texts(c)))
                self.buf.append(f"`{t}`" if t else "")
            elif tag in BLOCK_TAGS:
                self.flush()
                self.walk(c)
                self.flush()
            else:
                self.walk(c)

    def buf_has_text(self) -> bool:
        return bool("".join(self.buf).strip())

    def walk_list(self, lst: Node) -> None:
        depth = len(self.list_stack) - 1
        ordered, _ = self.list_stack[-1]
        for li in lst.children:
            if not isinstance(li, Node):
                continue
            if li.tag in ("ul", "ol"):  # a list nested without an <li>
                self.list_stack.append([li.tag == "ol", _start(li)])
                self.walk_list(li)
                self.list_stack.pop()
                continue
            if li.tag != "li":
                continue
            num = self.list_stack[-1][1]
            self.list_stack[-1][1] += 1
            t = _ws(self.inline(li))
            if t:
                self.blocks.append(Block("item", t, level=depth, ordered=ordered, number=num if ordered else 0))
            for sub in li.iter():  # code blocks and nested lists inside the item, in order
                if sub is li:
                    continue
                if sub.tag == "pre" and _owner(sub, li) is li and not _inside(sub, ("pre",), li):
                    code = _pre_text(sub)
                    if code.strip():
                        self.blocks.append(Block("code", code, lang=code_lang(sub)))
                elif sub.tag in ("ul", "ol") and _owner(sub, li) is li:
                    self.list_stack.append([sub.tag == "ol", _start(sub)])
                    self.walk_list(sub)
                    self.list_stack.pop()


def _start(lst: Node) -> int:
    try:
        return int(lst.attrs.get("start", "1"))
    except ValueError:
        return 1


def _inside(n: Node, tags: tuple[str, ...], stop: Node) -> bool:
    p = n.parent
    while p is not None and p is not stop:
        if p.tag in tags:
            return True
        p = p.parent
    return False


def _owner(n: Node, li: Node) -> Node | None:
    """li when n sits in li's own content (None when another list or item is in between)."""
    p = n.parent
    while p is not None and p is not li:
        if p.tag in ("ul", "ol", "li"):
            return None
        p = p.parent
    return p


def _is_block_code(c: Node) -> bool:
    t = "".join(_texts(c))
    return "\n" in t.strip() and len(t.strip()) > 40


def _merge(blocks: list[Block]) -> list[Block]:
    out: list[Block] = []
    for b in blocks:
        if b.kind == "text" and len(b.text) < 2:
            continue
        if b.kind == "text" and re.fullmatch(r"[|\s]+", b.text):
            continue
        out.append(b)
    return out


# ------------------------------------------------------------------------------------------------ the whole page


@dataclass
class HtmlPage:
    title: str
    author: str | None
    description: str | None
    blocks: list[Block]
    wall: str | None  # a paywall / sign-in reason
    script_only: bool  # nothing readable and the page has scripts: it draws its text with JavaScript
    canonical: str | None


def extract(html: str, *, site: str = "") -> HtmlPage:
    root, ld_raw = parse(html)
    ld = _ld_objects(ld_raw)
    meta = _meta(root)
    author = meta.get("author") or (meta.get("article:author") if not meta.get("article:author", "").startswith("http") else None)
    author = author or _ld_author(ld) or _byline(root)
    scripts = sum(1 for n in root.iter() if n.tag == "script")
    clean(root)
    main = main_node(root)
    w = _Walker()
    w.walk(main)
    w.flush()
    blocks = _merge(w.blocks)
    main_len = sum(len(b.text) for b in blocks)
    # the wall check needs the uncleaned page: parse again (cleaning mutated the tree)
    raw_root, _ = parse(html)
    wall = wall_reason(raw_root, ld, main_len)
    h1 = next((b.text for b in blocks if b.kind == "heading" and b.level == 1), None)
    site_names = [s for s in (meta.get("og:site_name"), site, site.split(".")[0] if site else None) if s]
    title = meta.get("og:title") or meta.get("twitter:title") or ""
    if not title:
        title = _strip_site_suffix(meta.get("title", ""), site_names) if meta.get("title") else (h1 or "")
    title = _ws(title) or (h1 or "")
    if h1 and title != h1 and title.lower().startswith(h1.lower()):
        title = h1  # "Array.prototype.map() - JavaScript | MDN" -> the page's own heading
    return HtmlPage(title=title[:200], author=author[:80] if author else None,
                    description=meta.get("og:description") or meta.get("description") or None, blocks=blocks,
                    wall=wall, script_only=main_len < 200 and scripts > 0 and not any(b.kind == "code" for b in blocks),
                    canonical=meta.get("canonical") or None)
