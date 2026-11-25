"""link.preview for a web / github link, from the extraction alone (no model call, no cost).

`verdict(ex)` judges teachability from the page's shape: code blocks (code), numbered lists and step-like headings
(steps). It is the fast, free answer; ANY-LINK.md's Haiku call on `Extraction.outline()` may refine teach / why later
(the lane that wires link.get decides). `preview(url)` reads the link and answers; `preview_from(ex)` /
`preview_error(err)` build the LinkPreview payload when the caller already has one.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from shared.contracts.events import LinkPreview, LinkTeachable, normalize_link_url

from . import fetch, github
from .model import Extraction, LinkUnreadable

_SHELL = frozenset({"bash", "console", "powershell", "cmd", "bat", "batch", "fish", "terminal", "shellsession", "nushell"})
_PROGRAMMING = frozenset({"python", "javascript", "typescript", "jsx", "tsx", "html", "css", "scss", "java", "c", "cpp",
                          "csharp", "rust", "go", "ruby", "php", "swift", "kotlin", "dart", "lua", "r", "julia", "scala",
                          "sql", "json", "yaml", "toml", "vue", "svelte", "elixir", "haskell", "pycon", "dockerfile",
                          "ini", "xml", "graphql", "markdown", "objective-c", "perl", "zig", "solidity"})
_CLI_START = re.compile(r"^\s*(\$|>|%|PS>|C:\\>)?\s*(pip3?|python3?\s+-m|uv|poetry|conda|npm|npx|yarn|pnpm|bun|deno|git|"
                        r"brew|cargo|go\s+(run|get|install|mod)|docker|kubectl|curl|wget|cd|mkdir|ls|export|source|"
                        r"apt(-get)?|sudo|gem|bundle|rails|dotnet|mvn|gradle|make|code|touch|chmod|ssh|flask|django-admin|"
                        r"uvicorn|node)\b", re.MULTILINE)
_STEP_HEADING = re.compile(r"^(step\s*\d+|part\s*\d+|\d+[.)]\s|install|installation|installing|set ?up|setup|setting up|"
                           r"getting started|get started|quick ?start|usage|tutorial|how to|create|creating|build|building|"
                           r"run|running|configure|configuration|add|adding|write|writing|deploy|deploying|first|your first|"
                           r"prerequisites|requirements|next steps|example|examples|try it)", re.IGNORECASE)
_NOTEBOOK = re.compile(r"(^|\n)\s*(%pip|%matplotlib|!pip|In \[\d*\]:)|jupyter|\.ipynb\b", re.IGNORECASE)
_EXCEL = re.compile(r"=\s*(SUM|VLOOKUP|XLOOKUP|INDEX|MATCH|IF|COUNTIF|SUMIF|AVERAGE)\s*\(|\bexcel\b|\bspreadsheet\b", re.IGNORECASE)


@dataclass
class Verdict:
    steps: bool
    code: bool
    why: str
    tools: list[str]
    est_minutes: int

    @property
    def teachable(self) -> bool:
        return self.steps or self.code


def _real_code(ex: Extraction) -> list:
    return [b for b in ex.code_blocks if len(re.sub(r"\s", "", b.text)) >= 8]


def tools_for(ex: Extraction) -> list[str]:
    code = _real_code(ex)
    langs = {b.lang for b in code if b.lang}
    text_all = "\n".join(b.text for b in code)
    tools: list[str] = []
    gh = ex.github or {}
    gh_langs = {str(l).lower() for l in gh.get("languages") or []}
    files = gh.get("files") or []
    notebook = bool(_NOTEBOOK.search(text_all)) or "ipython" in langs or "jupyter notebook" in gh_langs or \
        (files and sum(f.endswith(".ipynb") for f in files) * 3 >= len(files))
    if langs & _PROGRAMMING or (code and not langs and not _CLI_START.search(text_all)) or \
            (ex.kind == "github" and gh_langs and not notebook):
        tools.append("vscode")
    if notebook:
        tools.append("jupyter")
    if langs & _SHELL or _CLI_START.search(text_all):
        tools.append("terminal")
    if "excel" in langs or "vba" in langs or _EXCEL.search(text_all) and not langs & _PROGRAMMING:
        tools.append("excel")
    return tools


def verdict(ex: Extraction) -> Verdict:
    code = _real_code(ex)
    has_code = bool(code)
    ordered_items = sum(1 for b in ex.blocks if b.kind == "item" and b.ordered)
    step_heads = sum(1 for b in ex.headings if _STEP_HEADING.match(b.text))
    has_steps = ordered_items >= 3 or step_heads >= 2 or (step_heads >= 1 and has_code)
    if has_code and has_steps:
        why = "Walks through steps, with code you type and run."
    elif has_code:
        why = "Has code you can type and run."
    elif has_steps:
        why = "Walks through steps you can follow."
    elif ex.words >= 250:
        why = "It's mostly reading, with nothing to do or type."
    else:
        why = "There's not much on this page to do or type."
    if ex.kind == "github" and not has_code and not has_steps:
        why = "The README doesn't show how to install or use it."
    lines = sum(b.text.count("\n") + 1 for b in code)
    minutes = ex.words / 200 + 1.5 * len(code) + lines / 15
    est = int(min(180, max(3, math.ceil(minutes))))
    return Verdict(has_steps, has_code, why, tools_for(ex) if (has_code or has_steps) else [], est)


def _final_url(url: str, ex_final: str | None) -> str | None:
    try:
        a, b = normalize_link_url(url), normalize_link_url(ex_final or url)
    except ValueError:
        return None
    return b if a != b else None


def preview_from(ex: Extraction, url: str | None = None, req_id: str | None = None, *, pending: bool = False,
                 cached: bool | None = None) -> LinkPreview:
    v = verdict(ex)
    url = url or ex.url
    return LinkPreview(url=url, reqId=req_id, kind=ex.kind, pending=pending, title=ex.title or None, site=ex.site,
                       author=ex.author, estMinutes=v.est_minutes if v.teachable else None, teachable=v.teachable,
                       teach=LinkTeachable(steps=v.steps, code=v.code), why=v.why, tools=v.tools or None,
                       cached=cached, finalUrl=_final_url(url, ex.final_url) if ex.kind == "web" else None)


def preview_error(url: str, err: LinkUnreadable, req_id: str | None = None) -> LinkPreview:
    """A refusal as a preview: "unsupported" is kind unsupported; "no_content" is a readable answer (not teachable, with
    the reason); every other code is `error`."""
    kind = fetch.link_kind(url)
    kind = kind if kind in ("web", "github") else "unsupported"
    if err.code == "unsupported":
        return LinkPreview(url=url, reqId=req_id, kind="unsupported", pending=False, error="unsupported", why=err.reason)
    if err.code == "no_content":
        return LinkPreview(url=url, reqId=req_id, kind=kind, pending=False, title=err.title, site=err.site,
                           teachable=False, teach=LinkTeachable(steps=False, code=False), why=err.reason,
                           finalUrl=_final_url(url, err.final_url) if kind == "web" else None)
    return LinkPreview(url=url, reqId=req_id, kind=kind, pending=False, title=err.title, site=err.site, error=err.code,
                       why=err.reason)


async def preview(url: str, req_id: str | None = None, *,
                  is_cached: Callable[[str], bool] | None = None) -> tuple[LinkPreview, Extraction | None]:
    """Read the link and answer link.preview. Returns (preview, extraction or None) so the caller can keep the
    extraction for a learn_url that follows. is_cached(cache_key) says whether the lesson is already built."""
    try:
        ex = await fetch.read_link(url)
    except LinkUnreadable as e:
        return preview_error(url, e, req_id), None
    cached = None
    if is_cached is not None:
        try:
            cached = bool(is_cached(ex.cache_key))
        except Exception:  # noqa: BLE001  a cache that cannot answer: unknown, not a failed preview
            cached = None
    return preview_from(ex, url, req_id, cached=cached), ex


def site_for(url: str) -> str:
    """The `site` a preview shows before anything is read (the fast pending answer)."""
    r = github.parse_repo_url(url)
    return r.site if r is not None else fetch.site_of(url)
