"""Lessons from any link (shared/contracts/ANY-LINK.md): an article's, a docs page's or a GitHub repo's readable text ->
the same step graph as a "Just teach me" lesson.

    from server.lesson.pagelesson import ExtractedPage, build_page_lesson
    page = ExtractedPage.from_markdown("github", "https://github.com/pallets/flask", readme, title="Flask")
    graph = await build_page_lesson(page, workdir, on_update=on_update)

The fetch (netsafe, robots.txt, redirects, HTML -> readable text) happens before this module: it takes the extracted
text, as sections (heading, prose, code blocks, the page's anchor for the heading) or as Markdown (a README).

The build is textlesson's (`_build_text_lesson(..., page=PageBuild)`): the plan call (Sonnet, role "segment"), step 1
first through on_update (progressive first step), then the other steps drafted in parallel (role "detail"), the same
lint / repair / check kinds (screen checks on the editor and the terminal, file_* / command_exit_ok precision checks,
the lesson's .venv and notebook passes) and the step-graph contract. What changes for a page:

* no web research: the page itself is the notes, fenced as <untrusted source="page"> in the cached part of every step
  prompt, numbered by section (§1, §2, ...). EXTRACT_RULE instead of DATA_RULE: the page's own code and commands are
  what the lesson teaches (strip_injection still blanks any command outside the allowlist);
* the plan follows the page's sections in order; each plan step names the section it comes from, and the built step
  carries `pageRef {url[#anchor], heading}` (StepSummary.pageRef), never the page's own words;
* a page over PAGE_TEXT_BUDGET is cut at a section boundary (the overview says the lesson covers its first part);
  a section that addresses an AI (flag_injection, strict) is left out of the prompt;
* lesson.mode "lesson" (no video), lesson.origin = the BuildSource, sources = the page (blog / repo, meta = site),
  lesson id "web-<cache key>";
* cache: (link_cache_key(kind, url, content_hash), LESSON_SCHEMA_VERSION), the contract's key, at
  CACHE_DIR/links/<key>.s<version>.json, whatever the workdir. The shared (cloud) cache skips link lessons until
  miyagi-cloud's /lessons/{id} accepts LINK_CACHE_KEY_RE ids (ANY-LINK.md "Cloud"); `cached()` answers for this Mac;
* build.metrics: the build-time record (plan / first step / total seconds, sections, code blocks, characters, cut or
  not, cache hit, model calls and dollars), also logged as one `page_lesson.metrics {json}` line and handed to the
  cost event handlers as `page_build`.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from server.untrusted import (
    DATA_RULE,
    EXTRACT_RULE,
    clean,
    flag_injection,
    wrap,
    wrap_stable,
)
from shared.contracts.events import link_cache_key, link_content_hash

from . import builder, cost, textlesson
from .schema import LESSON_SCHEMA_VERSION

log = logging.getLogger("server.lesson")

LinkKind = Literal["web", "github"]
PAGE_TEXT_BUDGET = int(os.environ.get("LESSON_PAGE_TEXT_BUDGET", "15000"))  # characters of page digest in a prompt
CODE_BLOCK_CAP = 4000  # characters of one code block in the digest
MAX_SECTIONS = 80
METRICS_VERSION = 1


class NoContent(RuntimeError):
    """The page has no readable text to teach (lesson.building failCode "no_content")."""

    code = "no_content"


# --------------------------------------------------------------------------- the extracted page

@dataclass
class CodeBlock:
    code: str
    lang: str = ""


@dataclass
class PageSection:
    heading: str = ""  # "" for the text before the first heading
    text: str = ""  # the section's prose (readable text, no code)
    code: list[CodeBlock] = field(default_factory=list)
    anchor: str | None = None  # the page's id for the heading, for a #fragment
    level: int = 2

    def empty(self) -> bool:
        return not (self.heading.strip() or self.text.strip() or any(b.code.strip() for b in self.code))


@dataclass
class ExtractedPage:
    kind: LinkKind
    url: str  # the link the learner pasted
    title: str
    site: str  # "docs.python.org", "github.com/pallets/flask"
    sections: list[PageSection]
    author: str | None = None
    final_url: str | None = None  # where the link ended after redirects
    text: str | None = None  # the readable text the content hash is of (default: the sections joined)
    content_hash: str | None = None  # the extractor's link_content_hash, when it has one

    @property
    def page_url(self) -> str:
        return self.final_url or self.url

    def readable_text(self) -> str:
        if self.text is not None:
            return self.text
        parts = []
        for s in self.sections:
            parts += [s.heading, s.text] + [b.code for b in s.code]
        return "\n\n".join(p for p in parts if p and p.strip())

    def hash(self) -> str:
        return self.content_hash or link_content_hash(self.readable_text())

    def cache_key(self) -> str:
        return link_cache_key(self.kind, self.page_url, self.hash())

    def code_blocks(self) -> int:
        return sum(1 for s in self.sections for b in s.code if b.code.strip())

    def source(self) -> dict:
        """The contract's BuildSource (lesson.building.source, lesson.ready.lesson.origin)."""
        out = {"kind": self.kind, "title": _one_line(self.title or self.site, 300), "url": self.page_url, "site": self.site}
        if self.author and self.author.strip():
            out["author"] = _one_line(self.author, 120)
        return out

    @classmethod
    def from_markdown(cls, kind: LinkKind, url: str, markdown: str, *, title: str | None = None, site: str | None = None,
                      author: str | None = None, final_url: str | None = None) -> ExtractedPage:
        """A README (or a docs page the extractor turned into Markdown). GitHub heading anchors are GitHub's slugs."""
        sections = sections_from_markdown(markdown, slugs=kind == "github")
        first = next((s.heading for s in sections if s.heading), "")
        return cls(kind=kind, url=url, title=title or first or (site or ""), site=site or site_of(final_url or url),
                   sections=sections, author=author, final_url=final_url, text=markdown)

    @classmethod
    def from_dict(cls, d: dict) -> ExtractedPage:
        """{kind, url, title, site?, author?, finalUrl?, text?, contentHash?, sections: [{heading, text, code: [{code,
        lang} | str], anchor?, level?}]} or {..., markdown}."""
        kind = d.get("kind") or ("github" if site_of(d.get("finalUrl") or d.get("url") or "").startswith("github.com/") else "web")
        if kind not in ("web", "github"):
            raise ValueError(f"not a link kind: {kind!r}")
        if isinstance(d.get("markdown"), str):
            p = cls.from_markdown(kind, d["url"], d["markdown"], title=d.get("title"), site=d.get("site"),
                                  author=d.get("author"), final_url=d.get("finalUrl"))
            p.content_hash = d.get("contentHash")
            return p
        sections = []
        for s in d.get("sections") or []:
            if not isinstance(s, dict):
                continue
            code = [CodeBlock(b, "") if isinstance(b, str) else CodeBlock(str(b.get("code") or ""), str(b.get("lang") or ""))
                    for b in s.get("code") or [] if isinstance(b, (str, dict))]
            sections.append(PageSection(heading=str(s.get("heading") or ""), text=str(s.get("text") or ""), code=code,
                                        anchor=s.get("anchor") or None, level=int(s.get("level") or 2)))
        url = d["url"]
        return cls(kind=kind, url=url, title=str(d.get("title") or ""), site=d.get("site") or site_of(d.get("finalUrl") or url),
                   sections=sections, author=d.get("author"), final_url=d.get("finalUrl"), text=d.get("text"),
                   content_hash=d.get("contentHash"))


def site_of(url: str) -> str:
    """"docs.python.org"; "github.com/<owner>/<repo>" for a GitHub link (ANY-LINK.md)."""
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    host = host.removeprefix("www.")
    if host == "github.com":
        segs = [p for p in parts.path.split("/") if p]
        if len(segs) >= 2:
            return f"github.com/{segs[0].lower()}/{segs[1].lower().removesuffix('.git')}"
    return host


# --------------------------------------------------------------------------- Markdown -> sections

_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*([\w+#.-]*)")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TAG = re.compile(r"<[^>]{1,400}>")


def _plain(text: str) -> str:
    """Markdown inline -> plain text: images and HTML tags out, links as their text, no backticks / emphasis marks."""
    t = _IMAGE.sub("", text)
    t = _LINK.sub(r"\1", t)
    t = _TAG.sub("", t)
    t = re.sub(r"(\*\*|__|`)", "", t)
    return t


def github_slug(heading: str) -> str:
    """GitHub's anchor for a Markdown heading: lower case, punctuation dropped (but - and _), spaces to hyphens."""
    s = _plain(heading).strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def sections_from_markdown(md: str, *, slugs: bool = False) -> list[PageSection]:
    """Split at ATX headings (outside code fences); fenced code blocks become CodeBlocks of their section."""
    sections = [PageSection(heading="", level=0)]
    prose: list[str] = []
    fence: tuple[str, str, list[str]] | None = None  # (marker, lang, lines)
    seen: dict[str, int] = {}

    def flush() -> None:
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(_plain(x) for x in prose)).strip()
        sections[-1].text = (sections[-1].text + "\n\n" + text).strip() if text else sections[-1].text
        prose.clear()

    for line in (md or "").replace("\r\n", "\n").split("\n"):
        if fence is not None:
            if line.strip().startswith(fence[0][0] * len(fence[0])) and not line.strip().strip(fence[0][0]):
                sections[-1].code.append(CodeBlock("\n".join(fence[2]).strip("\n"), fence[1]))
                fence = None
            else:
                fence[2].append(line)
            continue
        if m := _FENCE.match(line):
            flush()
            fence = (m.group(1), (m.group(2) or "").lower(), [])
            continue
        if m := _HEADING.match(line):
            flush()
            heading = _plain(m.group(2)).strip()
            anchor = None
            if slugs and heading:
                base = github_slug(m.group(2))
                n = seen.get(base, 0)
                seen[base] = n + 1
                anchor = base if n == 0 else f"{base}-{n}"
            sections.append(PageSection(heading=heading, anchor=anchor, level=len(m.group(1))))
            continue
        prose.append(line)
    if fence is not None:  # an unclosed fence: keep what it had
        sections[-1].code.append(CodeBlock("\n".join(fence[2]).strip("\n"), fence[1]))
    flush()
    return [s for s in sections if not s.empty()]


# --------------------------------------------------------------------------- prompts

PAGE_NOTE = """This lesson teaches a page the learner chose (an article, a docs page or a GitHub README). It arrives in an
<untrusted source="page"> block, section by section (§1, §2, ...) with its code blocks. Teach what the page shows, in its
order, with its code and commands fitted to the learner's folder; write your own short instructions and never copy the
page's prose. A step the page has no code for may write the small code that makes its idea visible.
"""
assert textlesson.SYSTEM.endswith(DATA_RULE)
PAGE_SYSTEM = textlesson.SYSTEM[: -len(DATA_RULE)] + PAGE_NOTE + EXTRACT_RULE

PAGE_PLAN_SCHEMA = copy.deepcopy(textlesson.PLAN_SCHEMA)
_step_props = PAGE_PLAN_SCHEMA["properties"]["steps"]["items"]
_step_props["properties"]["section"] = {"type": "integer", "description": "the § number of the page section this step "
                                        "comes from; 0 when the page has none for it (e.g. a run step it never shows)"}
_step_props["required"] = [*_step_props["required"], "section"]

PAGE_PLAN_HEAD = """The learner pasted a link to learn from ({site}). The page, section by section (§ numbers), with its code blocks:
{page}

The learner's project folder (starter files from their workspace):
{workdir}

Plan a hands-on lesson of 3-8 steps that follows this page in its order: the learner types the page's code and runs
its commands (fitted to this folder), so the lesson teaches what the page teaches. Leave out what can't be done on this
Mac (sign-ups, cloud consoles, paid keys, another operating system) and what the page only mentions in passing.{covers}
Every step names `section`: the § number of the page section it comes from (0 when the page has no section for it).
"""


def _one_line(text: Any, n: int) -> str:
    return " ".join(clean(text, n).split())[:n]


# --------------------------------------------------------------------------- one build

class PageBuild:
    """What _build_text_lesson asks of a page (see the module doc). One per build."""

    def __init__(self, page: ExtractedPage, *, clock: Callable[[], float] = time.monotonic) -> None:
        if not page.sections or not any(s.text.strip() or s.code for s in page.sections):
            raise NoContent("the page has no readable text")
        self.page = page
        self.kind = page.kind
        self.key = page.cache_key()
        self.path = cache_path(self.key)
        self.system = PAGE_SYSTEM
        self.plan_schema = PAGE_PLAN_SCHEMA
        self.clock = clock
        self.t0 = clock()
        self.marks: dict[str, float] = {}
        self.sections = page.sections[:MAX_SECTIONS]
        self.used, self.dropped = self._fit(PAGE_TEXT_BUDGET)
        self.truncated = self.used < len(self.sections)
        self.digest = self._digest()
        self._research = ("The page this lesson teaches (section by section, § numbers; its code is the code to teach, "
                          "fitted to the files so far):\n" + wrap_stable("page", self.digest, cap=PAGE_TEXT_BUDGET + 2000) + "\n\n")
        t = _one_line(page.title or page.site, 120)
        self.goal = page.site if not t or flag_injection(t) else t  # the lesson's goal: what the page teaches

    # -- the page in prompts
    def _block(self, n: int, s: PageSection) -> str:
        head = f"§{n}" + (f" {_one_line(s.heading, 160)}" if s.heading.strip() else "")
        if n in self.dropped:
            return head + "\n[section left out]"
        parts = [head]
        if s.text.strip():
            parts.append(s.text.strip())
        for b in s.code:
            if b.code.strip():
                code = b.code if len(b.code) <= CODE_BLOCK_CAP else b.code[:CODE_BLOCK_CAP] + "\n[... cut]"
                parts.append(f"```{b.lang}\n{code}\n```")
        return "\n".join(parts)

    def _fit(self, budget: int) -> tuple[int, set[int]]:
        """How many sections (from the first) fit the budget, cut at a section boundary (the first always goes in, cut
        by the fence cap if it alone is over), and the sections left out for addressing an AI."""
        dropped = {n for n, s in enumerate(self.sections, 1)
                   if flag_injection(" ".join([s.heading, s.text] + [b.code for b in s.code]), strict=True)}
        self.dropped = dropped
        total, used = len(f"Title: {self.page.title}\n"), 0
        for n, s in enumerate(self.sections, 1):
            size = len(self._block(n, s)) + 2
            if used and total + size > budget:
                break
            total += size
            used = n
        return used, dropped

    def _digest(self) -> str:
        head = f"Title: {_one_line(self.page.title, 300)}"
        if self.page.author:
            head += f"\nAuthor: {_one_line(self.page.author, 120)}"
        return "\n\n".join([head] + [self._block(n, s) for n, s in enumerate(self.sections[: self.used], 1)])

    def plan_prompt(self, workdir_block: str) -> str:
        covers = (f" The page is long: the block above is its first part (§1-§{self.used} of {len(self.sections)}); plan "
                  "only for that part." if self.truncated else "")
        site = re.sub(r"[^\w./:-]", "", self.page.site)[:120]
        return PAGE_PLAN_HEAD.format(site=site, page=wrap("page", self.digest, cap=PAGE_TEXT_BUDGET + 2000),
                                     workdir=workdir_block, covers=covers) + textlesson.PLAN_RULES

    def research_block(self) -> str:
        return self._research

    def _section(self, sp: dict) -> int | None:
        n = sp.get("section")
        return n if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= self.used else None

    def step_note(self, sp: dict) -> str:
        n = self._section(sp)
        if n is None:
            return ""
        return (f"\nThis step comes from §{n} of the page (above): teach what that section shows, with its code and "
                "commands fitted to the files so far.\n")

    def ref_for(self, sp: dict) -> dict | None:
        """PageRef {url, heading?} for a plan step: the page (with #anchor when the section has one)."""
        n = self._section(sp)
        if n is None:
            return None
        s = self.sections[n - 1]
        parts = urlsplit(self.page.page_url)
        url = urlunsplit(parts._replace(fragment=re.sub(r"[^\w.~-]", "", s.anchor or "")))
        ref = {"url": url}
        if s.heading.strip():
            ref["heading"] = _one_line(s.heading, 160)
        return ref

    # -- the graph
    def decorate(self, g: dict) -> None:
        les = g["lesson"]
        les["id"] = f"web-{self.key[:10]}"
        les["origin"] = self.page.source()
        g["sources"] = [{"id": "src1", "kind": "repo" if self.kind == "github" else "blog",
                         "title": _one_line(self.page.title or self.page.site, 200), "url": self.page.page_url,
                         "meta": self.page.site}]
        if self.truncated:
            note = "This lesson covers the first part of the page."
            les["overview"] = (les.get("overview", "").rstrip() + " " + note).strip()
            g["build"]["warnings"].append(f"the page is long: the lesson covers sections 1-{self.used} of {len(self.sections)}")
        build = g["build"]
        build["model"] = {"plan": build["model"]["plan"], "steps": build["model"]["steps"]}  # no research call
        build["page"] = {"kind": self.kind, "site": self.page.site, "cacheKey": self.key, "schema": LESSON_SCHEMA_VERSION}

    def finish(self, g: dict) -> None:
        """The complete graph, before it is cached: the lesson's .venv and notebook, as for a video lesson; metrics."""
        from .notebook_steps import use_lesson_notebook
        from .venv_steps import use_lesson_venv

        use_lesson_venv(g)
        use_lesson_notebook(g)
        g["build"]["metrics"] = self.record(g, cache_hit=False)

    def cache_hit(self, g: dict) -> None:
        g.setdefault("build", {})["metrics"] = self.record(g, cache_hit=True)

    # -- build-time metrics
    def mark(self, name: str) -> None:
        self.marks.setdefault(name, self.clock() - self.t0)

    def record(self, g: dict, *, cache_hit: bool) -> dict:
        total = self.clock() - self.t0
        c = cost.current() or {}
        rec: dict[str, Any] = {
            "v": METRICS_VERSION, "kind": self.kind, "site": self.page.site, "cacheKey": self.key, "cacheHit": cache_hit,
            "totalS": round(total, 2), "steps": len(g.get("steps") or []), "sections": len(self.page.sections),
            "sectionsUsed": self.used, "sectionsDropped": len(self.dropped), "codeBlocks": self.page.code_blocks(),
            "chars": len(self.page.readable_text()), "promptChars": len(self.digest), "truncated": self.truncated,
        }
        if "plan" in self.marks and "steps" in self.marks:
            rec["planS"] = round(self.marks["steps"] - self.marks["plan"], 2)
        if "first_step" in self.marks:
            rec["firstStepS"] = round(self.marks["first_step"], 2)
        if not cache_hit:
            rec["modelCalls"] = int(c.get("claude_calls", 0) or 0)
            rec["costUsd"] = round(float(c.get("cost_usd", 0.0) or 0.0), 6)
        try:
            log.info("page_lesson.metrics %s", json.dumps(rec, sort_keys=True))
            cost.emit_event("page_build", rec)
        except Exception:
            log.debug("page metrics failed", exc_info=True)
        return rec


# --------------------------------------------------------------------------- cache + entry point

def cache_path(key: str):
    """The local lesson cache file for a page's key (CACHE_DIR read at call time: tests move it)."""
    return builder.CACHE_DIR / "links" / f"{key}.s{LESSON_SCHEMA_VERSION}.json"


def cached(kind: LinkKind, url: str, content_hash: str) -> bool:
    """link.preview's `cached` on this Mac: a lesson for this exact page (normalized URL + content) is already built."""
    try:
        return cache_path(link_cache_key(kind, url, content_hash)).is_file()
    except ValueError:
        return False


async def build_page_lesson(page: ExtractedPage | dict, workdir: str, on_update=None, *, cache: bool = True,
                            refresh: bool = False, clock: Callable[[], float] = time.monotonic) -> dict:
    """See the module doc. Returns the complete graph; on_update(graph, complete) gets step 1 first. Raises NoContent
    for a page with no readable text. A fresh cost counter per build; build_cost is emitted however the build ends."""
    from .builder import (  # LLM06: checked like every built lesson
        _untrusted,
        _validated_updates,
    )

    if not isinstance(page, ExtractedPage):
        page = ExtractedPage.from_dict(page)
    pb = PageBuild(page, clock=clock)
    counter = cost.start()
    with cost.build_scope(counter, kind=page.kind) as scope:
        g = await textlesson._build_text_lesson(pb.goal, workdir, _validated_updates(on_update, workdir), counter,
                                                cache=cache, refresh=refresh, page=pb)
        scope["lesson_id"] = (g.get("lesson") or {}).get("id")
        return _untrusted(g, workdir)
