"""The lesson library: lessons already built on this Mac (the lesson cache), ready to start with zero model calls.

    from server.lesson import library
    library.listing()             -> {"items": [LibraryItem], "continue": [ContinueItem]}   GET /library, library.list
    library.item("text-nn-...")   -> {"item": LibraryDetail} | None                          GET /library/{id}, library.get
    library.load_graph(id)        -> the cached step graph | None                            library.start (engine only)
    library.valid_id(id) / library.resolve(id)                                               id check + containment
    library.scrub(obj)                                                                       payload safety net

Source: the builder's cache (server/lesson/builder.CACHE_DIR, demo/cache/lessons/<id>.json; MIYAGI_LIBRARY_DIR
overrides it, tests do). An id is the cache file's stem ("516197461c0dacf3", "text-nn-from-scratch"): it must match
ID_RE (`^[A-Za-z0-9_-]{1,64}$`) and resolve to a regular file directly inside the cache dir (no subfolders, no
symlink that leads out of it). The raw/ drafts are never listed.

Payload rules (BUILD-PLAN section 6): fields are allowlisted, never the graph's `workdir` (an absolute path on
someone's Mac), never a file path, never a key; `scrub()` is the last pass over every payload this module returns
(progress.py uses it too). Nothing here is invented: a lesson with no time estimate has no
`estMinutes`, a source with no channel has no creator.

Pure reads, no model calls, no network. Every function returns an empty result rather than raising on a bad or
missing cache file. Contract shapes (W0-1 `library`, `library.item`): listed in app/agents/eng-modules.md.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("server.lesson.library")

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_ITEMS = 200
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_STEPS_SHOWN = 40
MAX_TEXT = 600  # characters for any free text (overview, a step title, a check label)

TOOLS = ("vscode", "jupyter", "terminal")  # display order; the app draws the tool icons ("VS", "Jn", ">_")

# ------------------------------------------------------------------------------------------------ payload safety
_SECRET_RES = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),
    re.compile(r"postgres(?:ql)?://\S+", re.I),
    re.compile(r"\bxi-[A-Za-z0-9]{16,}"),
)
# an absolute path (Mac / Linux / Windows), a home path, or a file URL
# anywhere it doesn't continue a word, a dotted name or another path (so `/Users/..`, cwd:/Users, [~/x] all count, while
# https://x.com/Users/a does not: its "/Users" follows "m")
_PATH_RE = re.compile(r"(?<![\w.\-/])(?:~/|/(?:Users|home|private|tmp|var|Volumes|opt)/|[A-Za-z]:\\|file://)")
_DROP_KEYS = frozenset({"workdir", "workdir_fp", "path", "abspath", "cwd", "folder", "graphFile", "keys", "token"})


def _clean_text(s: str) -> str | None:
    """The string with any key-shaped text removed; None when it holds a filesystem path (the caller drops it)."""
    if _PATH_RE.search(s):
        return None
    for rx in _SECRET_RES:
        s = rx.sub("", s)
    return s


def scrub(value: Any) -> Any:
    """A copy of `value` safe to send: keys named like paths/keys dropped, strings that hold an absolute path dropped,
    key-shaped text removed. Lists and dicts are walked; other JSON scalars pass through."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k) in _DROP_KEYS:
                continue
            if isinstance(v, str):
                v = _clean_text(v)
                if v is None:
                    continue
            else:
                v = scrub(v)
            out[str(k)] = v
        return out
    if isinstance(value, (list, tuple)):
        out_l = []
        for v in value:
            if isinstance(v, str):
                v = _clean_text(v)
                if v is None:
                    continue
            else:
                v = scrub(v)
            out_l.append(v)
        return out_l
    if isinstance(value, str):
        return _clean_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return None


# ------------------------------------------------------------------------------------------------ ids + files
def cache_dir() -> Path:
    """The lesson cache the builder writes (read at call time, so a test's override of either one counts)."""
    env = os.environ.get("MIYAGI_LIBRARY_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    from . import builder  # the package already imported it; deferred so this module never pulls it in first

    return Path(builder.CACHE_DIR)


def valid_id(lid: Any) -> bool:
    return isinstance(lid, str) and bool(ID_RE.fullmatch(lid))


def _root(root: Path | None = None) -> Path | None:
    try:
        r = (root or cache_dir()).resolve()
    except OSError:
        return None
    return r if r.is_dir() else None


def _contained(p: Path, root: Path) -> Path | None:
    """`p` resolved, when it is a regular file directly inside `root` (symlinks followed first), else None."""
    try:
        rp = p.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if rp.parent != root or not rp.is_file() or rp.suffix != ".json" or not valid_id(rp.stem):
        return None
    return rp


def resolve(lid: Any, root: Path | None = None) -> Path | None:
    """The cache file for library id `lid`, or None (bad id, missing, or outside the cache dir)."""
    if not valid_id(lid):
        return None
    r = _root(root)
    if r is None:
        return None
    name = f"{lid}.json"
    try:
        if name not in os.listdir(r):
            return None  # exact match: on case-insensitive APFS "GOOD-1" would open good-1.json (one lesson, two ids)
    except OSError:
        return None
    return _contained(r / name, r)


def _read_graph(p: Path) -> dict | None:
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            log.warning("library: skipping oversized cache file %s", p.name)
            return None
        g = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.debug("library: unreadable %s: %s", p.name, e)
        return None
    if not isinstance(g, dict) or not isinstance(g.get("lesson"), dict):
        return None
    steps = g.get("steps")
    if not isinstance(steps, list) or not any(isinstance(s, dict) and s.get("id") for s in steps):
        return None
    les = g["lesson"]
    if les.get("provisional") or les.get("complete") is False:
        return None  # a long video still being built is not ready to start
    return g


def load_graph(lid: Any, root: Path | None = None) -> dict | None:
    """The cached step graph for `lid`, for library.start (the engine's own use: it holds the graph's workdir, so it
    is never sent to the app as is). None for a bad id, a missing file or a graph that isn't ready."""
    p = resolve(lid, root)
    g = _read_graph(p) if p is not None else None
    if g is not None:
        from .schema import validate_untrusted_lesson

        for note in validate_untrusted_lesson(g):  # LLM06: a cached graph is untrusted
            log.warning("library lesson %s: %s", lid, note)
    return g


# ------------------------------------------------------------------------------------------------ fields
def _text(v: Any, limit: int = MAX_TEXT) -> str | None:
    """Display text, or None when empty or when it holds a filesystem path: the caller's fallback ("Lesson",
    "Step N") then applies, so scrub() never has to drop a required field. Key-shaped text is removed."""
    if not isinstance(v, str):
        return None
    c = _clean_text(v)
    if c is None:
        return None
    t = " ".join(c.split())
    if not t:
        return None
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def _steps(g: dict) -> list[dict]:
    return [s for s in g.get("steps") or [] if isinstance(s, dict) and s.get("id")]


def _mode(g: dict) -> str:
    les = g.get("lesson") or {}
    if les.get("mode") == "lesson" or (g.get("build") or {}).get("mode") == "lesson":
        return "lesson"
    return "video"


def tools(g: dict) -> list[str]:
    """Where the lesson runs, from its own steps (files, check apps, run steps) and libraries; display order."""
    found: set[str] = set()
    les = g.get("lesson") or {}
    libs = les.get("libraries")
    names = {str(n).lower() for n in (libs if isinstance(libs, (dict, list)) else [])}
    if names & {"jupyter", "notebook", "jupyterlab", "ipykernel"}:
        found.add("jupyter")
    for st in _steps(g):
        f = str(st.get("file") or "").lower()
        if f.endswith(".ipynb"):
            found.add("jupyter")
        elif f:
            found.add("vscode")
        if st.get("kind") == "run" or (isinstance(st.get("run_command"), str) and st["run_command"].strip()):
            found.add("terminal")
        for c in st.get("checks") or []:
            app = str((c or {}).get("app") or "").lower() if isinstance(c, dict) else ""
            if app in ("code", "vscode", "visual studio code"):
                found.add("vscode")
            elif app == "terminal":
                found.add("terminal")
            elif app == "jupyter":
                found.add("jupyter")
    if "jupyter" in found:
        found.add("vscode")  # notebooks open in VS Code
    return [t for t in TOOLS if t in found]


def est_minutes(g: dict) -> int | None:
    """The lesson's own estimate: build.estMinutes, else the sum of every step's estMinutes (only when every step has
    one). None when the lesson doesn't say: never a guess."""
    les = g.get("lesson") or {}
    b = les.get("build")
    v = b.get("estMinutes") if isinstance(b, dict) else None
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v < 1000:
        return int(round(v))
    mins = [s.get("estMinutes") for s in _steps(g)]
    if mins and all(isinstance(m, (int, float)) and not isinstance(m, bool) and m > 0 for m in mins):
        total = int(round(sum(mins)))
        return total if 0 < total < 1000 else None
    return None


def _source(g: dict) -> dict:
    """{kind: "video", title, url, videoId} for a lesson from a video (https URLs only), else {kind: "text"}."""
    srcs = [s for s in g.get("sources") or [] if isinstance(s, dict)]
    vid = next((s for s in srcs if s.get("kind") == "video" or s.get("videoId")), None)
    if vid is None:
        return {"kind": "text"}
    out: dict[str, Any] = {"kind": "video"}
    if t := _text(vid.get("title"), 200):
        out["title"] = t
    url = vid.get("url")
    if isinstance(url, str) and url.startswith("https://") and len(url) < 500:
        out["url"] = url
    if isinstance(vid.get("videoId"), str) and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", vid["videoId"]):
        out["videoId"] = vid["videoId"]
    for k in ("channel", "author"):
        if c := _text(vid.get(k), 120):
            out["creator"] = c
            break
    return out


def _dedupe_key(g: dict) -> tuple[str, str]:
    src = _source(g)
    if src.get("videoId"):
        return ("video", src["videoId"])
    les = g.get("lesson") or {}
    return ("text", " ".join(str(les.get("title") or les.get("id") or "").lower().split()))


def summary(g: dict, lid: str, updated_at: float | None = None) -> dict:
    """One library row (LibraryItem). Allowlisted fields only."""
    les = g.get("lesson") or {}
    steps = _steps(g)
    out: dict[str, Any] = {
        "id": lid,
        "lessonId": _text(les.get("id"), 120) or lid,
        "title": _text(les.get("title"), 200) or _text(les.get("goal"), 200) or "Lesson",
        "mode": _mode(g),
        "steps": len(steps),
        "tools": tools(g),
        "source": _source(g),
    }
    if (m := est_minutes(g)) is not None:
        out["estMinutes"] = m
    if les.get("builtBy") in ("gemini", "claude", "mixed", "chapters", "curated"):
        out["builtBy"] = les["builtBy"]
    if les.get("curated"):
        out["curated"] = True
    if isinstance(updated_at, (int, float)):
        out["updatedAt"] = round(float(updated_at), 3)
    return out


def detail(g: dict, lid: str, updated_at: float | None = None) -> dict:
    """The lesson preview (LibraryDetail): the row plus its overview, its steps (title + first check label) and its
    libraries. Step bodies, code, targets and hints stay in the engine."""
    les = g.get("lesson") or {}
    out = summary(g, lid, updated_at)
    b = les.get("build") if isinstance(les.get("build"), dict) else {}
    if about := (_text(les.get("overview")) or _text(b.get("summary"))):
        out["overview"] = about
    if outcome := _text(b.get("outcome")):
        out["outcome"] = outcome
    rows = []
    for i, st in enumerate(_steps(g)[:MAX_STEPS_SHOWN]):
        row: dict[str, Any] = {"n": i + 1, "title": _text(st.get("title"), 200) or f"Step {i + 1}"}
        check = next((c for c in st.get("checks") or [] if isinstance(c, dict) and _text(c.get("label"))), None)
        if check is not None:
            row["check"] = _text(check.get("label"), 160)
        rows.append(row)
    out["stepList"] = rows
    libs = les.get("libraries")
    names = [str(n) for n in (libs if isinstance(libs, (dict, list)) else []) if isinstance(n, str)]
    if names:
        out["libraries"] = [n for n in (_text(x, 60) for x in names[:20]) if n]
    pre = [p.get("title") for p in les.get("prerequisites") or [] if isinstance(p, dict)]
    if pre := [t for t in (_text(x, 120) for x in pre[:10]) if t]:
        out["prerequisites"] = pre
    return out


# ------------------------------------------------------------------------------------------------ listing
def _entries(root: Path | None = None) -> list[tuple[str, Path, float, dict]]:
    """(id, file, mtime, graph) for every ready lesson in the cache, newest first, one per video / text lesson."""
    r = _root(root)
    if r is None:
        return []
    found: list[tuple[str, Path, float, dict]] = []
    try:
        files = sorted(r.glob("*.json"))
    except OSError:
        return []
    for p in files:
        rp = _contained(p, r)
        if rp is None:
            continue
        g = _read_graph(rp)
        if g is None:
            continue
        try:
            mtime = rp.stat().st_mtime
        except OSError:
            continue
        found.append((rp.stem, rp, mtime, g))
    found.sort(key=lambda e: e[2], reverse=True)
    seen: set[tuple[str, str]] = set()
    out = []
    for e in found:
        key = _dedupe_key(e[3])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out[:MAX_ITEMS]


def items(root: Path | None = None) -> list[dict]:
    """Every ready lesson as a LibraryItem, newest first."""
    return [scrub(summary(g, lid, mtime)) for lid, _p, mtime, g in _entries(root)]


def index_by_lesson_id(root: Path | None = None) -> dict[str, str]:
    """lesson.id (what progress and the session store use) -> library id, for linking Continue / Completed rows."""
    out: dict[str, str] = {}
    for lid, _p, _m, g in _entries(root):
        les_id = (g.get("lesson") or {}).get("id")
        if isinstance(les_id, str) and les_id not in out:
            out[les_id] = lid
    return out


def continuing(index: dict[str, str] | None = None) -> list[dict]:
    """The "Continue" rows: the saved lesson (sessions/store current.json) and the recent unfinished ones, newest
    first, one per lesson: {lessonId, title, mode, stepIndex, stepCount, stepTitle?, lastActiveAt?, libraryId?}.
    libraryId only when that lesson is in the library (Continue can start it without a build)."""
    from server.sessions import progress, store  # light: json files under ~/miyagi/state

    rows: list[dict] = []
    try:
        # A lesson finished after it was last active is not "continue" any more (recent.json keeps its entry when
        # the lesson later finishes). Same rule as progress inProgress; a replay of a finished lesson stays.
        finished = progress.finished_at([e for e in store.completed() if isinstance(e, dict)])
        cur = store.load()
        if isinstance(cur, dict) and not progress.superseded(cur, finished, is_current=True):
            rows.append(cur)
        rows += [r for r in store.recent() if isinstance(r, dict) and not progress.superseded(r, finished)]
    except Exception as e:  # noqa: BLE001 - a bad state file must not break the library
        log.warning("library: could not read saved lessons: %s", e)
        return []
    if index is None:
        index = index_by_lesson_id()
    out, seen = [], set()
    for r in rows:
        les_id = r.get("lessonId")
        if not isinstance(les_id, str) or les_id in seen:
            continue
        seen.add(les_id)
        row: dict[str, Any] = {"lessonId": les_id, "title": _text(r.get("title"), 200) or "Lesson",
                               "mode": "lesson" if r.get("mode") == "lesson" else "video"}
        for k in ("stepIndex", "stepCount"):
            if isinstance(r.get(k), int) and not isinstance(r.get(k), bool) and r[k] >= 0:
                row[k] = r[k]
        if t := _text(r.get("stepTitle"), 200):
            row["stepTitle"] = t
        if isinstance(r.get("lastActiveAt"), (int, float)):
            row["lastActiveAt"] = round(float(r["lastActiveAt"]), 3)
        if les_id in index:
            row["libraryId"] = index[les_id]
        out.append(row)
    return [scrub(r) for r in out]


def listing(root: Path | None = None) -> dict:
    """GET /library and library.list: {items, continue}. Empty lists when there is no cache."""
    entries = _entries(root)
    idx: dict[str, str] = {}
    for lid, _p, _m, g in entries:
        les_id = (g.get("lesson") or {}).get("id")
        if isinstance(les_id, str) and les_id not in idx:
            idx[les_id] = lid
    return {"items": [scrub(summary(g, lid, mtime)) for lid, _p, mtime, g in entries],
            "continue": continuing(idx)}


def item(lid: Any, root: Path | None = None) -> dict | None:
    """GET /library/{id} and library.get: {"item": LibraryDetail}, or None (bad id, missing, not ready)."""
    p = resolve(lid, root)
    if p is None:
        return None
    g = _read_graph(p)
    if g is None:
        return None
    try:
        mtime = p.stat().st_mtime
    except OSError:
        mtime = None
    return {"item": scrub(detail(g, p.stem, mtime))}
