"""A github.com repo link as a lesson's text: the README and docs/*.md, plus the repo's languages and file list.

Public endpoints only, no token (60 API calls an hour per IP; a link costs at most 4 API calls plus raw files):

- GET api.github.com/repos/{o}/{r}               name, description, default branch, language, owner
- GET api.github.com/repos/{o}/{r}/git/trees/{ref}?recursive=1   every file path (GitHub truncates huge repos)
- GET api.github.com/repos/{o}/{r}/languages     bytes per language
- GET raw.githubusercontent.com/{o}/{r}/{ref}/{path}             the README, the docs files (not rate limited)

When the API says rate limited (403 / 429 with x-ratelimit-remaining: 0) the repo is read from raw files alone: the
README at HEAD under its usual names, no file list. A 404 is "not found" (GitHub answers 404 for a private repo too).

Link shapes: github.com/{o}/{r} (README + docs/), /tree/{ref}/{folder} (the .md files in that folder), /blob/{ref}/{path}
(that file: a .md / .rst as text, any other text file as one code block). A ref with a slash in it (feature/x) is read
as ref "feature" and path "x/...": GitHub's own URLs are ambiguous there; the API call then 404s and the link reads as
not found. Every fetch goes through server.netsafe (fetch.py's `_get`).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from .markdown import parse_markdown, parse_plain, parse_rst
from .model import Block, Extraction, LinkUnreadable

log = logging.getLogger("server.linkread.github")

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
MAX_DOCS = 10  # docs files read beside the README
MAX_DOC_BYTES = 400 * 1024  # one README / docs file
MAX_TOTAL_DOC_BYTES = 1024 * 1024  # all of them
MAX_FILES_LISTED = 300  # paths kept in Extraction.github["files"]
_RESERVED = frozenset("about account apps blog collections contact customer-stories enterprise events explore "
                      "features issues login logout marketplace new notifications orgs organizations pricing "
                      "pulls readme search security settings site sponsors topics trending users codespaces "
                      "copilot dashboard".split())
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_README = re.compile(r"^readme(\.(md|markdown|mdown|mkdn|rst|txt))?$", re.IGNORECASE)
_DOC_EXT = (".md", ".markdown", ".mdx", ".rst", ".txt")
_DOCS_DIRS = ("docs/", "doc/", "documentation/")
_EXT_LANG = {".py": "python", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript", ".tsx": "tsx", ".jsx": "jsx",
             ".sh": "bash", ".rb": "ruby", ".go": "go", ".rs": "rust", ".java": "java", ".c": "c", ".h": "c", ".cpp": "cpp",
             ".cs": "csharp", ".swift": "swift", ".kt": "kotlin", ".php": "php", ".html": "html", ".css": "css",
             ".json": "json", ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".sql": "sql", ".r": "r", ".ipynb": "json",
             ".dockerfile": "dockerfile", ".ini": "ini", ".cfg": "ini", ".lua": "lua", ".dart": "dart"}


@dataclass
class RepoRef:
    owner: str
    repo: str
    mode: str  # "repo" | "tree" | "blob"
    ref: str | None = None
    path: str = ""

    @property
    def site(self) -> str:
        return f"github.com/{self.owner}/{self.repo}"

    @property
    def html_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"


def parse_repo_url(url: str) -> RepoRef | None:
    """A github.com repo link (repo root, tree or blob), else None (a user page, an issue, gist: read as a web page)."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or host not in ("github.com", "www.github.com"):
        return None
    segs = [s for s in parts.path.split("/") if s]
    if len(segs) < 2 or segs[0].lower() in _RESERVED:
        return None
    owner, repo = segs[0], segs[1].removesuffix(".git")
    if not (_NAME.match(owner) and _NAME.match(repo)) or repo in (".", ".."):
        return None
    if len(segs) == 2:
        return RepoRef(owner, repo, "repo")
    if segs[2] in ("tree", "blob") and len(segs) >= 4:
        path = "/".join(segs[4:])
        if ".." in path.split("/"):
            return None
        return RepoRef(owner, repo, segs[2] if path else "repo", segs[3], path)  # tree/<ref> alone: the repo at that ref
    return None


def _raw_url(r: RepoRef, ref: str, path: str) -> str:
    return f"{RAW}/{quote(r.owner)}/{quote(r.repo)}/{quote(ref, safe='')}/{quote(path)}"


def _blob_url(r: RepoRef, ref: str, path: str) -> str:
    return f"{r.html_url}/blob/{quote(ref, safe='')}/{quote(path)}"


def _rate_limited(resp) -> bool:
    return resp.status_code in (403, 429) and (resp.headers.get("x-ratelimit-remaining") == "0"
                                               or "rate limit" in resp.text[:300].lower())


def _blocks_for(path: str, text: str, url: str) -> list[Block]:
    low = path.lower()
    if low.endswith(".rst"):
        return parse_rst(text, url=url)
    if low.endswith(".txt") or ("." not in low.rsplit("/", 1)[-1] and not _README.match(low.rsplit("/", 1)[-1])):
        return parse_plain(text, url=url)
    return parse_markdown(text, url=url)


async def read_repo(r: RepoRef, get, url: str) -> Extraction:
    """`get(url, *, accept=None, max_bytes=...)` is fetch.py's guarded GET (returns an httpx.Response)."""
    meta: dict = {}
    limited = False
    resp = await get(f"{API}/repos/{r.owner}/{r.repo}", accept="application/vnd.github+json")
    if resp.status_code == 404:
        raise LinkUnreadable("not_found", "I can't find that repo on GitHub. It may be private or misspelled.",
                             site=r.site)
    if resp.status_code == 451:
        raise LinkUnreadable("blocked", "GitHub won't show this repo here.", site=r.site)
    if _rate_limited(resp):
        limited = True
        log.info("github: API rate limited, reading %s from raw files", r.site)
    elif resp.status_code >= 400:
        raise LinkUnreadable("unknown", f"GitHub didn't answer properly (error {resp.status_code}). Try again in a bit.",
                             site=r.site)
    else:
        try:
            meta = json.loads(resp.text)
        except ValueError:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
    if meta.get("private"):
        raise LinkUnreadable("not_found", "That repo is private, so I can't read it.", site=r.site)
    # GitHub redirects a renamed repo; take its current name for the links we build
    full = meta.get("full_name")
    if isinstance(full, str) and "/" in full and _NAME.match(full.split("/")[0]) and _NAME.match(full.split("/")[1]):
        r = RepoRef(full.split("/")[0], full.split("/")[1], r.mode, r.ref, r.path)
    ref = r.ref or meta.get("default_branch") or "HEAD"

    files: list[str] = []
    files_truncated = False
    languages: list[str] = []
    if not limited:
        tr = await get(f"{API}/repos/{r.owner}/{r.repo}/git/trees/{quote(ref, safe='')}?recursive=1",
                       accept="application/vnd.github+json", max_bytes=4 * 1024 * 1024)
        if tr.status_code == 200:
            try:
                tree = json.loads(tr.text)
                files = sorted(e["path"] for e in tree.get("tree", []) if e.get("type") == "blob"
                               and isinstance(e.get("path"), str))
                files_truncated = bool(tree.get("truncated"))
            except (ValueError, TypeError, KeyError, AttributeError):
                files = []
        elif tr.status_code == 404 and r.ref:
            raise LinkUnreadable("not_found", f"That repo has no branch or tag named {r.ref!r}.", site=r.site)
        elif _rate_limited(tr):
            limited = True
        lr = None if limited else await get(f"{API}/repos/{r.owner}/{r.repo}/languages",
                                            accept="application/vnd.github+json")
        if lr is not None and lr.status_code == 200:
            try:
                langs = json.loads(lr.text)
                languages = [k for k, _ in sorted(langs.items(), key=lambda kv: -kv[1])] if isinstance(langs, dict) else []
            except (ValueError, TypeError, AttributeError):
                languages = []
    if not languages and isinstance(meta.get("language"), str):
        languages = [meta["language"]]

    # what to read
    paths: list[str]
    if r.mode == "blob":
        paths = [r.path]
    elif r.mode == "tree":
        prefix = r.path.rstrip("/") + "/" if r.path else ""
        paths = [f for f in files if f.startswith(prefix) and f.lower().endswith(_DOC_EXT)]
        readme_here = [f for f in paths if "/" not in f[len(prefix):] and _README.match(f[len(prefix):])]
        paths = readme_here + [f for f in paths if f not in readme_here]
        paths = paths[:MAX_DOCS + 1]
    else:
        readme = [f for f in files if "/" not in f and _README.match(f)]
        readme.sort(key=lambda f: (not f.lower().endswith((".md", ".markdown")), f))
        docs = [f for f in files if f.lower().startswith(_DOCS_DIRS) and f.lower().endswith((".md", ".markdown", ".rst"))]
        paths = readme[:1] + docs[:MAX_DOCS]
        if not readme and not files:  # no file list (rate limited or an empty answer): the usual README names
            paths = []
            for name in ("README.md", "readme.md", "README.rst", "README", "Readme.md"):
                rr = await get(_raw_url(r, ref, name), max_bytes=MAX_DOC_BYTES)
                if rr.status_code == 200 and rr.text.strip():
                    blocks = _blocks_for(name, rr.text, r.html_url)
                    return _extraction(url, r, ref, meta, blocks, languages, files, files_truncated, [name])

    blocks: list[Block] = []
    read: list[str] = []
    total = 0
    for p in paths:
        if total >= MAX_TOTAL_DOC_BYTES:
            break
        rr = await get(_raw_url(r, ref, p), max_bytes=MAX_DOC_BYTES)
        if rr.status_code == 404 and r.mode == "blob":
            raise LinkUnreadable("not_found", f"There's no file {p!r} in that repo.", site=r.site)
        if rr.status_code != 200:
            continue
        text = rr.text
        total += len(text)
        is_readme = _README.match(p.rsplit("/", 1)[-1]) is not None
        page = r.html_url if (is_readme and "/" not in p and r.mode == "repo") else _blob_url(r, ref, p)
        if r.mode == "blob" and not p.lower().endswith(_DOC_EXT) and not is_readme:
            if "\x00" in text[:4096]:
                raise LinkUnreadable("no_content", "That file isn't text, so I can't read it.", site=r.site)
            ext = "." + p.rsplit(".", 1)[-1].lower() if "." in p.rsplit("/", 1)[-1] else ""
            blocks.append(Block("heading", p, level=1, url=page))
            blocks.append(Block("code", text.strip("\n"), lang=_EXT_LANG.get(ext), url=page))
            read.append(p)
            continue
        fb = _blocks_for(p, text, page)
        if read and not (fb and fb[0].kind == "heading" and fb[0].level == 1):
            blocks.append(Block("heading", p, level=1, url=page))  # where the next file starts
        blocks.extend(fb)
        read.append(p)
    return _extraction(url, r, ref, meta, blocks, languages, files, files_truncated, read)


def _extraction(url: str, r: RepoRef, ref: str, meta: dict, blocks: list[Block], languages: list[str],
                files: list[str], files_truncated: bool, read: list[str]) -> Extraction:
    desc = meta.get("description") if isinstance(meta.get("description"), str) else None
    title = meta.get("name") if isinstance(meta.get("name"), str) else r.repo
    if r.mode == "blob" and r.path:
        title = f"{r.path.rsplit('/', 1)[-1]} in {r.repo}"
    elif r.mode == "tree" and r.path:
        title = f"{r.repo}: {r.path.rstrip('/')}"
    owner = meta.get("owner") if isinstance(meta.get("owner"), dict) else {}
    author = owner.get("login") if isinstance(owner.get("login"), str) else r.owner
    final = r.html_url if r.mode == "repo" else (f"{r.html_url}/{r.mode}/{quote(ref, safe='')}/{quote(r.path)}"
                                                 if r.path else r.html_url)
    topics = [t for t in meta.get("topics") or [] if isinstance(t, str)][:10]
    info = {"owner": r.owner, "repo": r.repo, "ref": ref, "path": r.path, "mode": r.mode,
            "language": meta.get("language") or (languages[0] if languages else None), "languages": languages[:10],
            "files": files[:MAX_FILES_LISTED], "fileCount": len(files),
            "filesTruncated": files_truncated or len(files) > MAX_FILES_LISTED, "docs": read, "topics": topics,
            "archived": bool(meta.get("archived"))}
    return Extraction(kind="github", url=url, final_url=final, title=title, site=r.site, blocks=blocks, author=author,
                      description=desc, github=info)
