"""Client for miyagi-cloud's shared lesson cache: a YouTube video is built into a lesson once across all users.

Routes (cloud/app.py "shared lesson cache"; every call is `Authorization: Bearer <install token>` to the proxy the
engine already uses, config.cloud_url() / config.cloud_token(), so config.py's host allowlist applies):

    GET  {cloud}/lessons/{video_id}?schema=N   200 {video_id, schema, created_at, lesson} | 404 lesson_not_cached
    POST {cloud}/lessons/{video_id}/build?schema=N  claim a build (free for a video this install already claimed this
                                               month): 200 {ok, builds} | 401 signin_required | 429 lesson_builds
    PUT  {cloud}/lessons/{video_id}            {schema, lesson}: 201 {stored, status: pending|approved} | 4xx/5xx

    lookup(vid)                -> the lesson graph for this Mac, or None. A download is never trusted: it is checked
                                  against the cloud's own rules (validate_shared, a port of cloud validate_lesson),
                                  rebuilt into a graph and run through validate_untrusted_lesson + the step-graph
                                  contract before anything sees it.
    claim(vid)                 -> "ok" | "held" | "denied" | "error"
    share(graph, vid)          -> upload a good build (lesson.complete, every step present, validates)
    fetch_graph / claim_build  -> the builder's two hooks (builder._build_lesson_impl)

Every failure (cloud down, 401 signin_required or unknown token, 429 caps, a bad or oversized download, a malformed
reply) ends in the normal local build with ONE log line and no card. After a transport failure the cloud is left alone
for COOLDOWN_S so a dead cloud never adds more than one short timeout to a lesson. The install token is never logged
and this module never reports a verdict to config (a 401 here is not "unknown token": the model calls decide that).

The shared form (to_shared) is the graph without anything of this Mac or this learner: no workdir, no goal (it is the
learner's own search text), no build record. restore() puts those back for the learner who downloads it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from server import config

from .schema import LESSON_SCHEMA_VERSION, schema_errors

log = logging.getLogger("server.lesson.cloud_cache")

ENV_OFF = "MIYAGI_LESSON_CACHE"  # =0: never use the shared cache (tests, offline demos)
GET_TIMEOUT_S = 5.0
CLAIM_TIMEOUT_S = 5.0
PUT_TIMEOUT_S = 15.0
COOLDOWN_S = 60.0  # after a transport failure or a 5xx: no cloud lesson calls for this long
HELD_WAIT_S = 12.0  # claim said someone else is building this video: poll for their lesson this long, then build
HELD_POLL_S = 3.0
MAX_DOWNLOAD_BYTES = 1024 * 1024
MAX_UPLOAD_BYTES = 128 * 1024  # the cloud's MAX_LESSON_KB default; a bigger lesson is not sent
VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")

_down_until = 0.0
_claimed: dict[str, bool] = {}  # video id -> this process holds a claim for it (False: the cloud refused one)
_shared: set[str] = set()  # video ids uploaded (or refused for good) by this process
_tasks: set[asyncio.Task] = set()


def _client(timeout: float) -> httpx.AsyncClient:
    """The one place an HTTP client is made (tests replace it with a mock transport). No redirects: the proxy
    answers directly, and a redirect must never carry the install token to another host."""
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False)


def enabled() -> bool:
    return os.environ.get(ENV_OFF, "") != "0" and config.cloud_on()


def reset() -> None:
    """Forget cooldown and per-video state (tests)."""
    global _down_until, last_notice
    _down_until = 0.0
    last_notice = None
    _claimed.clear()
    _shared.clear()


def _usable() -> bool:
    return enabled() and time.monotonic() >= _down_until and not config.region_blocked(None)


def _region(r: httpx.Response) -> bool:
    """451 region_unavailable (the cloud's region block): tell config (no more cloud calls this run, AI calls included)
    and the notice listeners. Never retried, never a token verdict."""
    if r.status_code != 451:
        return False
    config.note_region_unavailable()
    _announce(r)
    return True


def _note(what: str) -> None:
    log.info("shared lesson cache: %s; building locally", what)


def _cool_down() -> None:
    global _down_until
    _down_until = time.monotonic() + COOLDOWN_S


_listeners: list[Callable[[dict], Any]] = []
last_notice: dict | None = None


def on_notice(fn: Callable[[dict], Any]) -> Callable[[], None]:
    """Hear why the cloud would not take a build claim: {"reason": "signin_required" | "lesson_builds" |
    "anon_daily_cap" | "region_unavailable" | ..., "status": 401|403|429|451, "resets_at"?: ISO time}. For the app to surface a sign-in prompt
    or a cap card. The lesson itself is built locally either way. Returns the remover."""
    _listeners.append(fn)
    return lambda: _listeners.remove(fn) if fn in _listeners else None


def _announce(r: httpx.Response) -> None:
    """A 401 signin_required (REQUIRE_SIGNIN build/all) or a 429 cap on a claim: tell the listeners. Never a verdict
    on the install token: no re-mint is asked for, and config.cloud_error is not involved."""
    global last_notice
    b = _err_body(r)
    e = b.get("error") if isinstance(b.get("error"), dict) else {}
    kind = _err_kind(r)
    notice = {"reason": str(e.get("limit") or kind or r.status_code)[:60], "status": r.status_code}
    if isinstance(e.get("resets_at"), str):
        notice["resets_at"] = e["resets_at"][:40]
    last_notice = notice
    for fn in _listeners:
        try:
            fn(dict(notice))
        except Exception:
            log.debug("shared lesson cache listener failed", exc_info=True)


def _url(vid: str, suffix: str = "") -> str:
    return f"{config.cloud_url()}/lessons/{vid}{suffix}"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {config.cloud_token()}"}


def _err_body(r: httpx.Response) -> dict:
    try:
        b = r.json()
    except ValueError:
        return {}
    return b if isinstance(b, dict) else {}


def _err_kind(r: httpx.Response) -> str:
    """The cloud's error name: {"error": "signin_required"} (flat, the sign-in gate) or {"error": {"type": ...}}."""
    b = _err_body(r)
    e = b.get("error")
    if isinstance(e, dict):
        return str(e.get("type") or "")[:60]
    return str(e or b.get("type") or "")[:60]


def _why(r: httpx.Response) -> str:
    kind = _err_kind(r)
    if r.status_code == 401:
        return "sign-in required" if kind == "signin_required" else "install token not accepted"
    if r.status_code == 429:
        return "caps reached"
    if r.status_code == 451:
        return "not available in this region"
    return f"HTTP {r.status_code}" + (f" {kind}" if kind else "")


# ------------------------------------------------------------------------------------------ the shared form
LESSON_KEYS = frozenset({"title", "summary", "libraries", "files", "steps", "lesson", "sources"})
LESSON_META_KEYS = frozenset({"id", "title", "goal", "summary", "libraries"})
STEP_KEYS = frozenset({"start", "end", "title", "instructions", "file", "code", "run_command", "expected_output", "checks",
                       "targets", "explanations", "hints", "common_mistakes", "id", "index", "video", "precision_checks",
                       "sample_output", "solution", "setup", "requires"})
CHECK_KEYS = frozenset({"id", "type", "label", "app", "metric_pattern", "file", "pattern", "command", "metric", "op", "value",
                        "by_step", "trend", "window"})
CHECK_TYPES = frozenset({"screen_contains", "screen_absent", "metric_threshold", "metric_trend", "file_exists",
                         "file_contains", "command_exit_ok", "output_contains"})
TARGET_KEYS = frozenset({"app", "file", "match", "caption"})
EXPLANATION_KEYS = frozenset({"topic", "t", "sourceId"})
VIDEO_KEYS = frozenset({"sourceId", "start", "end"})
SOURCE_KEYS = frozenset({"id", "type", "url", "title"})

# validate_shared: a port of cloud/app.py validate_lesson and its helpers (the cloud refuses an upload that fails
# them; we refuse a download that does, so a poisoned cache entry never reaches the learner's machine).
RUN_COMMAND_RE = re.compile(r"(?:python3?|pytest|node|npm run) [A-Za-z0-9_./ -]+")
NOTEBOOK_RUN = "Run the cell (Shift+Enter)"
PYTHON_MODULES_OK = frozenset({"pytest", "unittest", "venv", "flask", "streamlit"})
PYTHON_FLAGS_OK = frozenset({"-u", "-B", "-O"})
_REFUSED_ANYWHERE = ("--require", "--import", "--eval", "--print", "--loader", "--experimental-loader", "--inspect")
_PYTEST_REFUSED = ("-p", "-c", "--pyargs", "--rootdir", "--confcutdir")
_LIB_NAME_RE = re.compile(r"(?:@[a-z0-9][a-z0-9._-]{0,60}/)?[A-Za-z0-9][A-Za-z0-9._-]{0,80}(?:\[[A-Za-z0-9_,-]{1,80}\])?")
_LIB_VERSION_PART = r"[<>=!~^]{0,3}[0-9A-Za-z*][0-9A-Za-z.*+-]{0,30}"
_LIB_VERSION_RE = re.compile(rf"{_LIB_VERSION_PART}(?:,{_LIB_VERSION_PART}){{0,3}}")
_TOOL_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
_MAX_STR = 20_000
_MAX_DEPTH = 12


def _ok_command(cmd: Any) -> bool:
    if cmd is None or cmd == "":
        return True
    if not isinstance(cmd, str) or len(cmd) > 300:
        return False
    cmd = cmd.strip()
    if cmd in ("pytest", NOTEBOOK_RUN):
        return True
    if not RUN_COMMAND_RE.fullmatch(cmd) or "//" in cmd or "www." in cmd.lower() or ".." in cmd:
        return False
    words = cmd.split()
    if "npx" in words or any(w.startswith(_REFUSED_ANYWHERE) for w in words):
        return False
    prog, args = words[0], words[1:]
    if prog == "npm":
        return len(args) >= 2 and not args[1].startswith("-")
    if prog == "pytest":
        return not any(a.startswith(_PYTEST_REFUSED) for a in args)
    i = 0
    if prog.startswith("python"):
        while i < len(args) and args[i] in PYTHON_FLAGS_OK:
            i += 1
        if i < len(args) and args[i] == "-m":
            module = args[i + 1] if i + 1 < len(args) else ""
            return module in PYTHON_MODULES_OK and (module != "pytest" or not any(a.startswith(_PYTEST_REFUSED) for a in args[i + 2:]))
    return i < len(args) and not args[i].startswith("-")


def _ok_path(p: Any) -> bool:
    if p is None or p == "":
        return True
    if not isinstance(p, str) or len(p) > 260 or "\x00" in p or ":" in p:
        return False
    if p.startswith(("/", "\\", "~")):
        return False
    return ".." not in re.split(r"[\\/]", p)


def _ok_source(s: Any) -> bool:
    if isinstance(s, dict) and set(s) - SOURCE_KEYS:
        return False
    url = s.get("url") if isinstance(s, dict) else s
    return isinstance(url, str) and url.startswith("https://") and len(url) <= 2000 and not re.search(r"\s", url)


def _library_pairs(libs: Any) -> list[tuple] | None:
    if libs is None:
        return []
    if isinstance(libs, dict):
        return list(libs.items())
    if isinstance(libs, list) and all(isinstance(x, dict) and not set(x) - {"name", "version"} for x in libs):
        return [(x.get("name"), x.get("version")) for x in libs]
    return None


def _ok_libraries(libs: Any) -> bool:
    pairs = _library_pairs(libs)
    if pairs is None or len(pairs) > 100:
        return False
    for name, version in pairs:
        if not isinstance(name, str) or not _LIB_NAME_RE.fullmatch(name):
            return False
        if version not in (None, "") and not (isinstance(version, str) and _LIB_VERSION_RE.fullmatch(version)):
            return False
    return True


def _walk_bounded(v: Any, depth: int = 0) -> bool:
    if depth > _MAX_DEPTH:
        return False
    if isinstance(v, str):
        return len(v) <= _MAX_STR
    if isinstance(v, dict):
        return all(isinstance(k, str) and len(k) <= 100 and _walk_bounded(x, depth + 1) for k, x in v.items())
    if isinstance(v, list):
        return len(v) <= 1000 and all(_walk_bounded(x, depth + 1) for x in v)
    return v is None or isinstance(v, (bool, int, float))


def _items(v: Any) -> list:
    return v if isinstance(v, list) else []


def _extra(d: dict, allowed: frozenset) -> str | None:
    extra = sorted(k for k in d if k not in allowed)
    return extra[0][:40] if extra else None


def _check_problem(c: Any) -> str | None:
    if not isinstance(c, dict):
        return "checks must be objects"
    if key := _extra(c, CHECK_KEYS):
        return f"unknown check key {key!r}"
    if "type" in c and c["type"] not in CHECK_TYPES:
        return f"unknown check type {str(c['type'])[:40]!r}"
    if not _ok_path(c.get("file")):
        return "check files must be relative paths inside the project"
    if not _ok_command(c.get("command")):
        return "check commands must be plain python, pytest, node or npm run"
    return None


def _step_problem(s: dict) -> str | None:
    if key := _extra(s, STEP_KEYS):
        return f"unknown step key {key!r}"
    if not _ok_command(s.get("run_command")):
        return "run_command must be python, pytest, node or npm run with plain arguments"
    if not _ok_path(s.get("file")):
        return "file must be a relative path inside the project"
    for c in _items(s.get("checks")) + _items(s.get("precision_checks")):
        if why := _check_problem(c):
            return why
    for t in _items(s.get("targets")):
        if not isinstance(t, dict) or _extra(t, TARGET_KEYS) or not _ok_path(t.get("file")):
            return "targets must be {app, file, match, caption} with relative files"
    for e in _items(s.get("explanations")):
        if not isinstance(e, dict) or _extra(e, EXPLANATION_KEYS):
            return "explanations must be {topic, t, sourceId}"
    if "video" in s and (not isinstance(s["video"], dict) or _extra(s["video"], VIDEO_KEYS)):
        return "video must be {sourceId, start, end}"
    if not all(isinstance(r, str) and _TOOL_ID_RE.fullmatch(r) for r in _items(s.get("requires"))):
        return "requires must be tool ids"
    return None


def validate_shared(lesson: Any) -> str | None:
    """Why this shared lesson is refused, or None. The cloud's validate_lesson, rule for rule."""
    if not isinstance(lesson, dict):
        return "lesson must be an object with 1 to 300 steps"
    steps = lesson.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 300 or not all(isinstance(s, dict) for s in steps):
        return "lesson must be an object with 1 to 300 steps"
    if not _walk_bounded(lesson):
        return f"a string over {_MAX_STR} characters or nested too deep"
    if key := _extra(lesson, LESSON_KEYS):
        return f"unknown lesson key {key!r}"
    meta = lesson.get("lesson")
    if meta is not None and (not isinstance(meta, dict) or _extra(meta, LESSON_META_KEYS)):
        return "lesson.lesson holds a key that is not allowed"
    if not _ok_libraries(lesson.get("libraries")) or not _ok_libraries((meta or {}).get("libraries")):
        return "libraries must be plain package names with plain versions"
    if not all(_ok_path(f) for f in _items(lesson.get("files"))):
        return "lesson files must be relative paths inside the project"
    if not all(_ok_source(s) for s in _items(lesson.get("sources"))):
        return "lesson sources must be https URLs"
    for i, s in enumerate(steps, 1):
        if why := _step_problem(s):
            return f"step {i}: {why}"
    return None


def schema_fingerprint() -> dict[str, list[str]]:
    """Every key a lesson can carry, by place: what the draft and adapt passes are asked for, what the step-graph
    contract names, and what the shared form allows. test_cloud_cache.py compares it with its snapshot, so a change
    to any of them cannot ship without bumping LESSON_SCHEMA_VERSION."""
    from . import schema as S

    draft = S.VIDEO_DRAFT_SCHEMA["properties"]
    draft_step = draft["steps"]["items"]["properties"]
    adapted_step = S.ADAPTED_SCHEMA["properties"]["steps"]["items"]["properties"]
    graph = json.loads((S.CONTRACTS / "step-graph.schema.json").read_text(encoding="utf-8"))["properties"]
    check = json.loads((S.CONTRACTS / "check.schema.json").read_text(encoding="utf-8")).get("properties", {})
    return {
        "draft": sorted(draft),
        "draft.step": sorted(draft_step),
        "draft.check": sorted(S._CHECK_DRAFT["properties"]),
        "adapted.step": sorted(adapted_step),
        "graph": sorted(graph),
        "graph.lesson": sorted(graph["lesson"]["properties"]),
        "graph.source": sorted(graph["sources"]["items"]["properties"]),
        "graph.step": sorted(graph["steps"]["items"]["properties"]),
        "contract.check": sorted(check),
        "shared": sorted(LESSON_KEYS),
        "shared.lesson": sorted(LESSON_META_KEYS),
        "shared.step": sorted(STEP_KEYS),
        "shared.check": sorted(CHECK_KEYS),
        "shared.check_types": sorted(CHECK_TYPES),
    }


# ------------------------------------------------------------------------------------------ graph <-> shared form
def watch_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def good_build(graph: Any, vid: str) -> str | None:
    """Why this graph is not worth sharing, or None for a good build: a finished (lesson.ready), adapted, plain video
    lesson of this video with every step present."""
    if not isinstance(graph, dict):
        return "not a lesson graph"
    les, build = graph.get("lesson"), graph.get("build") or {}
    steps = graph.get("steps")
    if not isinstance(les, dict) or not isinstance(steps, list) or not steps:
        return "no steps"
    if les.get("complete") is not True or les.get("provisional") or les.get("transcriptOnly"):
        return "not a finished, full build"
    if les.get("builtBy") in ("shared", "chapters"):
        return "not built here"
    if build.get("adapted") is not True or build.get("provisional"):
        return "the adapt pass did not finish"
    if (les.get("parts") or {}).get("failed"):
        return "a part of the video failed"
    srcs = graph.get("sources")
    if not isinstance(srcs, list) or len(srcs) != 1 or not isinstance(srcs[0], dict) or srcs[0].get("videoId") != vid:
        return "not a single-video lesson of this video"
    for i, s in enumerate(steps, 1):
        if (not isinstance(s, dict) or s.get("provisional") or s.get("pending") or not s.get("id") or s.get("index") != i
                or not str(s.get("title") or "").strip() or not str(s.get("instructions") or "").strip()):
            return f"step {i} is not complete"
    return None


def to_shared(graph: dict, vid: str) -> dict | None:
    """The lesson in its shared form (the cloud's allowed keys only, nothing of this Mac or this learner), or None."""
    from . import library

    les = graph.get("lesson") or {}
    meta: dict = {"title": str(les.get("title") or "Tutorial")[:300]}
    libs = les.get("libraries")
    if isinstance(libs, (dict, list)) and libs:
        meta["libraries"] = libs
    src = (graph.get("sources") or [{}])[0]
    shared = {
        "lesson": meta,
        "sources": [{"id": "src1", "type": "video", "url": watch_url(vid), "title": str(src.get("title") or "Tutorial")[:300]}],
        "steps": [{k: v for k, v in s.items() if k in STEP_KEYS} for s in graph["steps"]],
    }
    shared = json.loads(json.dumps(shared))  # a deep copy that is plain JSON
    blob = json.dumps(shared, ensure_ascii=False)
    if library._PATH_RE.search(blob) or any(r.search(blob) for r in library._SECRET_RES):
        return None  # a path of this Mac or a key-shaped string: never leaves it
    return shared


def restore(shared: dict, vid: str, *, source_url: str, goal: str, workdir: str, key: str,
            workdir_fp: str | None = None) -> dict | None:
    """A downloaded lesson as this learner's step graph. None unless it passes the cloud's rules, the step-graph
    contract and validate_untrusted_lesson's repairs leave a lesson with every step."""
    from .builder import (
        _untrusted,  # the same LLM06 pass every built or cached graph gets
    )

    if why := validate_shared(shared):
        log.warning("shared lesson %s refused: %s", vid, why)
        return None
    meta = shared.get("lesson") or {}
    libs = meta.get("libraries", shared.get("libraries")) or {}
    if isinstance(libs, list):
        libs = {x["name"]: x.get("version") or "" for x in libs}
    title = str(meta.get("title") or shared.get("title") or "Tutorial")
    steps = json.loads(json.dumps(shared["steps"]))
    for s in steps:
        if isinstance(s.get("video"), dict):
            s["video"]["sourceId"] = "src1"
    graph = {
        "lesson": {"id": f"lesson-{key[:8]}", "title": title, "goal": goal or title, "workdir": workdir,
                   "libraries": libs, "builtBy": "shared", "complete": True},
        "sources": [{"id": "src1", "kind": "video", "title": title, "url": source_url, "videoId": vid}],
        "steps": steps,
        "build": {"adapted": True, "model": {"video": "shared", "adapt": "shared"}, "seconds": 0, "workdir_fp": workdir_fp,
                  "shared": {"schema": LESSON_SCHEMA_VERSION}, "warnings": ["from the shared lesson cache"]},
    }
    n = len(steps)
    _untrusted(graph, workdir)
    if len(graph.get("steps") or []) != n:
        log.warning("shared lesson %s refused: validation removed steps", vid)
        return None
    if errs := schema_errors(graph):
        log.warning("shared lesson %s refused: %s", vid, errs[0][:200])
        return None
    return graph


# ------------------------------------------------------------------------------------------ the cloud calls
async def _get(vid: str) -> dict | None:
    """The cloud's lesson body for `vid`, or None on a miss or any failure (one log line unless a plain miss)."""
    try:
        async with _client(GET_TIMEOUT_S) as c:
            r = await c.get(_url(vid), params={"schema": LESSON_SCHEMA_VERSION}, headers=_headers())
    except (httpx.HTTPError, OSError) as e:
        _cool_down()
        _note(f"cloud unreachable ({type(e).__name__})")
        return None
    if r.status_code == 404 and _err_kind(r) in ("lesson_not_cached", ""):
        return None
    if r.status_code != 200:
        _region(r)
        if r.status_code >= 500 or r.status_code in (401, 403):
            _cool_down()  # a server in trouble, or a token it does not accept: nothing else would work either
        _note(_why(r))
        return None
    if len(r.content) > MAX_DOWNLOAD_BYTES:
        _note("download too large")
        return None
    try:
        body = r.json()
    except ValueError:
        _note("download is not JSON")
        return None
    if (not isinstance(body, dict) or body.get("video_id") != vid or body.get("schema") != LESSON_SCHEMA_VERSION
            or not isinstance(body.get("lesson"), dict)):
        _note("download is not the lesson asked for")
        return None
    return body["lesson"]


async def lookup(vid: str, *, source_url: str, goal: str, workdir: str, key: str, workdir_fp: str | None = None) -> dict | None:
    """The shared lesson for `vid` as a graph for this Mac (see restore), or None."""
    if not VIDEO_ID_RE.fullmatch(vid or "") or not _usable():
        return None
    shared = await _get(vid)
    if shared is None:
        return None
    graph = await asyncio.to_thread(restore, shared, vid, source_url=source_url, goal=goal, workdir=workdir, key=key,
                                    workdir_fp=workdir_fp)
    if graph is None:
        _note("download failed validation")
    return graph


async def claim(vid: str) -> str:
    """Claim a build of `vid`. "ok": go ahead and build. "held": another install is building it right now (the cloud
    says so with a 409, or 200 {"held": true}); poll for it. "denied": sign-in or the monthly cap said no (the build
    still runs here, it is just not shared). "error": cloud trouble. One claim per video per process."""
    if vid in _claimed:
        return "ok" if _claimed[vid] else "denied"
    if not VIDEO_ID_RE.fullmatch(vid or "") or not _usable():
        return "error"
    try:
        async with _client(CLAIM_TIMEOUT_S) as c:
            r = await c.post(_url(vid, "/build"), params={"schema": LESSON_SCHEMA_VERSION}, headers=_headers())
    except (httpx.HTTPError, OSError) as e:
        _cool_down()
        _note(f"cloud unreachable ({type(e).__name__})")
        return "error"
    if r.status_code == 409 or (r.status_code == 200 and _err_body(r).get("held") is True):
        return "held"
    if r.status_code == 200:
        _claimed[vid] = True
        return "ok"
    if r.status_code == 451:
        _claimed[vid] = False
        _note(_why(r))
        _region(r)
        return "denied"
    if r.status_code in (401, 403, 429):
        _claimed[vid] = False
        _note(_why(r))
        _announce(r)
        return "denied"
    if r.status_code >= 500:
        _cool_down()
    _note(_why(r))
    return "error"


async def claim_build(vid: str, poll: Callable[[], Any]) -> dict | None:
    """The builder's hook for a local and shared miss: claim the build. When another install holds it, wait up to
    HELD_WAIT_S polling `poll()` (an awaitable returning the lesson graph or None) and return the graph it yields;
    None means build here."""
    state = await claim(vid)
    if state != "held":
        return None
    _note("another install is building this video; waiting briefly")
    deadline = time.monotonic() + HELD_WAIT_S
    while time.monotonic() < deadline:
        await asyncio.sleep(min(HELD_POLL_S, max(0.0, deadline - time.monotonic())))
        graph = await poll()
        if graph is not None:
            return graph
        if not _usable():
            break
    _note("still not there")
    return None


async def share(graph: dict, vid: str) -> str:
    """Upload a good build. Returns "stored" | "skipped" | "failed" (every reason logged once)."""
    if vid in _shared or not _usable():
        return "skipped"
    if why := good_build(graph, vid):
        log.info("shared lesson cache: not uploading %s (%s)", vid, why)
        return "skipped"
    shared = to_shared(graph, vid)
    if shared is None:
        log.info("shared lesson cache: not uploading %s (a path or key in the text)", vid)
        return "skipped"
    if why := validate_shared(shared):
        log.info("shared lesson cache: not uploading %s (%s)", vid, why)
        return "skipped"
    body = json.dumps({"schema": LESSON_SCHEMA_VERSION, "lesson": shared}, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_UPLOAD_BYTES:
        log.info("shared lesson cache: not uploading %s (over %d KB)", vid, MAX_UPLOAD_BYTES // 1024)
        _shared.add(vid)
        return "skipped"
    if vid not in _claimed and await claim(vid) != "ok":
        return "failed"
    if _claimed.get(vid) is False:
        return "skipped"
    try:
        async with _client(PUT_TIMEOUT_S) as c:
            r = await c.put(_url(vid), content=body, headers={**_headers(), "Content-Type": "application/json"})
    except (httpx.HTTPError, OSError) as e:
        _cool_down()
        log.info("shared lesson cache: upload failed (%s); the lesson stays on this Mac", type(e).__name__)
        return "failed"
    if r.status_code == 201:
        _shared.add(vid)
        log.info("shared lesson cache: uploaded %s (%s)", vid, _err_body(r).get("status", "stored"))
        return "stored"
    if r.status_code >= 500:
        _cool_down()
    _region(r)
    if r.status_code in (400, 413):
        _shared.add(vid)  # the cloud will refuse it again: do not retry
    log.info("shared lesson cache: upload refused (%s); the lesson stays on this Mac", _why(r))
    return "failed"


def share_later(graph: dict, vid: str) -> None:
    """share() in the background: never delays or fails the lesson."""
    if not _usable() or vid in _shared:
        return
    try:
        task = asyncio.ensure_future(_share_quietly(graph, vid))
    except RuntimeError:
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _share_quietly(graph: dict, vid: str) -> None:
    try:
        await share(graph, vid)
    except Exception as e:  # noqa: BLE001  sharing is a bonus
        log.info("shared lesson cache: upload failed (%s)", type(e).__name__)
