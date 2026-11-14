"""build_lesson: YouTube URL -> validated, workdir-adapted step graph (cached)."""

from __future__ import annotations

import asyncio
import contextvars
import copy
import hashlib
import json
import logging
import re
import time
from pathlib import Path

import os

from . import claude, gemini, transcript
from .schema import (
    CHECK_TYPES,
    PRECISION_TYPES,
    REPO_ROOT,
    SCREEN_TYPES,
    check_problems,
    is_output_check,
    lint,
    stack_of,
    standard_error_pattern,
    schema_errors,
    standard_output_check,
    step_check_problems,
)
from .workdir import WorkdirInfo, scan

# Progress for the UI. Stable stage ids (the app maps them to text; log wording may change):
#   cache_hit, watching (Gemini watches the video), reading_transcript, writing_steps (Claude),
#   engine_switch (Gemini failed/slow -> transcript path; message says why), steps_ready (message = engine),
#   adapting (fitting checks to the learner's project), done
STAGES = ("cache_hit", "watching", "reading_transcript", "writing_steps", "engine_switch", "steps_ready", "adapting", "done")
_progress: contextvars.ContextVar = contextvars.ContextVar("lesson_progress", default=None)


def _emit(stage: str, message: str = "") -> None:
    cb = _progress.get()
    if cb is None:
        return
    try:
        r = cb(stage, message)
        if asyncio.iscoroutine(r):
            asyncio.ensure_future(r)
    except Exception as e:  # noqa: BLE001  a UI callback must never break a build
        log.debug("progress callback failed: %s", e)

log = logging.getLogger("server.lesson")

CACHE_DIR = REPO_ROOT / "demo" / "cache" / "lessons"
RAW_DIR = CACHE_DIR / "raw"  # video-only drafts, reusable across workdirs
ADAPT_ATTEMPTS = 3
DETAIL_CONCURRENCY = 2  # free tier: 5 requests/min per model

_CHECK_FIELDS = {
    "screen_contains": ("app", "pattern"),
    "screen_absent": ("app", "pattern"),
    "file_exists": ("file",),
    "file_contains": ("file", "pattern"),
    "command_exit_ok": ("command",),
    "output_contains": ("pattern",),
    "metric_threshold": ("metric", "metric_pattern", "op", "value", "by_step"),
    "metric_trend": ("metric", "metric_pattern", "trend", "window"),
}


async def build_lesson(
    source_url: str,
    goal: str,
    workdir: str,
    *,
    refresh: bool = False,
    readapt: bool = False,
    detail: bool = False,
    api_key: str | None = None,
    anthropic_key: str | None = None,
    cache: bool = True,
    on_progress=None,
) -> dict:
    """Return a step graph that validates against shared/contracts/step-graph.schema.json.

    Each step has screen-first `checks` (screen_* / metric_* with metric_pattern) and, as an
    extra field, `precision_checks` (file_* / command_* / ::metric:: backups for `tut run`).
    Engines (LESSON_ENGINE=auto|gemini|claude, default auto): Gemini watches the video directly;
    if every Gemini model fails (quota, outage, no key), Claude builds the same graph from the
    video's transcript + title/description/chapters. build.model records which model did what.
    If both fail the error is raised, never papered over with made-up steps.
    api_key / anthropic_key: the app's bring-your-own keys (config.keys.gemini / .anthropic).
    on_progress(stage, message): optional callback (sync or async) with a stage id from STAGES.
    refresh: rebuild everything (new video pass). readapt: reuse the cached video draft, redo only
    the cheap adapt pass (e.g. after the workdir changed or an adapt pass ran out of quota).
    detail: per-step clip pass at 2 fps (costs one request per step; off by default on the free tier).

    Cached at demo/cache/lessons/<hash>.json; the cache wins unless refresh/readapt, so the
    demo never waits on Gemini. The hash covers the video, the goal, the workdir folder name and
    a fingerprint of its file names + printed ::metric:: names (not the absolute path or file
    contents, so the cache survives other laptops and the learner's edits, but a different
    project layout gets checks adapted to it). A graph whose adapt pass failed is returned
    with build.adapted=False and is NOT cached (the video draft is, so a retry is cheap).
    """
    _progress.set(on_progress)  # also clears a callback left by an earlier build in the same task
    vid = gemini.youtube_id(source_url)
    if not vid:
        raise ValueError(f"only YouTube sources are supported for now: {source_url!r}")
    info = scan(workdir)
    key = cache_key(source_url, goal, workdir, info)
    path = CACHE_DIR / f"{key}.json"
    if cache and not (refresh or readapt):
        hit = path if path.is_file() else find_cached(vid, workdir, info)
        if hit:
            graph = json.loads(hit.read_text())
            graph["lesson"]["workdir"] = workdir
            log.info("lesson cache hit %s%s", hit.name, "" if hit == path else " (same video + workdir, different goal wording)")
            _emit("cache_hit", hit.name)
            _emit("done", hit.name)
            return graph

    if api_key:
        gemini.set_api_key(api_key)
    if anthropic_key:
        claude.set_api_key(anthropic_key)
    t0 = time.time()
    draft = await _video_draft(source_url, vid, goal, refresh=refresh or not cache, detail=detail, write=cache)
    graph, warnings, adapted_ok, adapt_model = await _adapt(draft, goal, info)
    warnings = list(draft.get("detail_failures") or []) + warnings
    if not adapted_ok:
        warnings = ["adapt pass failed (quota?): checks come from the video draft, not the learner's workdir; not cached, retry with readapt=True"] + warnings
    n_signals = await add_community_mistakes(graph, source_url)
    graph["lesson"]["id"] = f"lesson-{key[:8]}"
    graph["lesson"]["builtBy"] = draft.get("_engine", "unknown")  # "gemini" = watched the video; "claude" = read the transcript
    graph["lesson"]["workdir"] = workdir
    graph["sources"] = [{"id": "src1", "kind": "video", "title": draft.get("title") or "Tutorial", "url": source_url, "videoId": vid}]
    graph["build"] = {
        "adapted": adapted_ok,
        "model": {"video": draft.get("_built_by", "unknown"), "adapt": adapt_model},
        "seconds": round(time.time() - t0, 1),
        "workdir_metrics": sorted(info.metrics),
        "workdir_fp": workdir_fingerprint(workdir, info),
        "community_signals": n_signals,
        "warnings": warnings,
    }
    errs = schema_errors(graph)
    if errs:
        raise RuntimeError("step graph failed contract validation:\n" + "\n".join(errs))
    if not adapted_ok or not cache:
        log.warning("lesson built in %.1fs; not cached (%s)", time.time() - t0, "adapt pass failed" if not adapted_ok else "cache=False")
        _emit("done", f"{time.time() - t0:.0f}s")
        return graph
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, indent=2))
    log.info("lesson built in %.1fs -> %s (%d warnings)", time.time() - t0, path, len(warnings))
    _emit("done", f"{time.time() - t0:.0f}s")
    return graph


async def add_community_mistakes(graph: dict, source_url: str) -> int:
    """Attach timestamped community reports (YouTube comments, Stack Overflow, Reddit, GitHub issues)
    from server.finder.web.community_signals (E7) to the step they happened in, as common_mistakes.
    Optional: skipped silently until that module exists or if it fails. Accepts items shaped like
    {"t"|"timestamp": seconds or "MM:SS", "text"|"mistake": str, "source"?: str, "url"?: str}."""
    try:
        from server.finder.web import community_signals  # type: ignore[import-not-found]
    except ImportError:
        return 0
    try:
        res = community_signals(source_url)
        items = (await res if asyncio.iscoroutine(res) else res) or []
    except Exception as e:  # noqa: BLE001  live-web enrichment must never break a build
        log.warning("community_signals failed: %s", e)
        return 0
    added = 0
    for it in items:
        t = parse_ts(it.get("t", it.get("timestamp")))
        text = (it.get("text") or it.get("mistake") or "").strip()
        if t is None or not text:
            continue
        for step in graph["steps"]:
            v = step.get("video") or {}
            if v.get("start", 0) <= t < v.get("end", 0):
                src = f", {it['source']}" if it.get("source") else ""
                step.setdefault("common_mistakes", []).append(f"{text[:200]} (at {int(t) // 60}:{int(t) % 60:02d}{src})")
                added += 1
                break
    return added


def workdir_fingerprint(workdir: str, info: WorkdirInfo) -> str:
    """Folder name + file names + printed ::metric:: names (not contents, not the absolute path)."""
    name = Path(workdir).expanduser().resolve().name
    return hashlib.sha256(json.dumps([name, sorted(info.files), sorted(info.metrics)]).encode()).hexdigest()[:12]


def cache_key(source_url: str, goal: str, workdir: str, info: WorkdirInfo | None = None) -> str:
    vid = gemini.youtube_id(source_url) or source_url
    norm_goal = " ".join(goal.lower().split())
    name = Path(workdir).expanduser().resolve().name
    info = info or scan(workdir)
    fingerprint = [sorted(info.files), sorted(info.metrics)]
    return hashlib.sha256(json.dumps([vid, norm_goal, name, fingerprint]).encode()).hexdigest()[:16]


def find_cached(vid: str, workdir: str, info: WorkdirInfo) -> Path | None:
    """Goal-agnostic fallback: the launcher passes the learner's free-text query as the goal, so an
    exact-goal miss falls back to the newest cached lesson for the same video adapted to the same
    workdir layout (step framing barely depends on the goal wording)."""
    if not CACHE_DIR.is_dir():
        return None
    fp = workdir_fingerprint(workdir, info)
    best: tuple[float, Path] | None = None
    for p in CACHE_DIR.glob("*.json"):
        try:
            g = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if (g.get("sources") or [{}])[0].get("videoId") == vid and (g.get("build") or {}).get("workdir_fp") == fp:
            m = p.stat().st_mtime
            if best is None or m > best[0]:
                best = (m, p)
    return best[1] if best else None


# --------------------------------------------------------------------------- #
# Pass 1: video -> draft (cached per video+goal)
# --------------------------------------------------------------------------- #


async def _video_draft(url: str, vid: str, goal: str, *, refresh: bool, detail: bool, write: bool = True) -> dict:
    gh = hashlib.sha256(" ".join(goal.lower().split()).encode()).hexdigest()[:8]
    raw_path = RAW_DIR / f"{vid}-{gh}.json"
    if raw_path.is_file() and not refresh:
        return json.loads(raw_path.read_text())

    draft = await _watch(url, vid, goal)
    if detail and draft.get("_engine") == "gemini":  # clips need a model that sees the video
        await _add_detail(url, draft)
    if write:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(draft, indent=2))
    return draft


# Gemini watching the video gives better step boundaries and reads names/versions off the screen
# (S3 eval: median start error 1 s vs 15 s), so auto prefers it: it gets up to LESSON_GEMINI_TIMEOUT
# seconds, and the Claude transcript draft (running in parallel from t=0) is used only if Gemini fails
# or runs out of time. Paid tier: a 20-min video takes Gemini ~35-60 s at 0.5 fps.
GEMINI_VIDEO_TIMEOUT_S = 75.0
GEMINI_GRACE_S = GEMINI_VIDEO_TIMEOUT_S  # LESSON_GEMINI_GRACE: extra wait for Gemini once Claude's draft is ready


def engines() -> list[str]:
    """Video-pass engines in order. Rule: Gemini only ever *watches* the video; Claude does
    everything else (transcript drafts, the adapt pass, check writing)."""
    gemini._load_env()
    e = os.environ.get("LESSON_ENGINE", "auto").strip().lower()
    return {"gemini": ["gemini"], "claude": ["claude"]}.get(e, ["gemini", "claude"])


async def _watch(url: str, vid: str, goal: str) -> dict:
    """Video pass. In auto mode Gemini (watching the video, capped at LESSON_GEMINI_TIMEOUT) races the
    Claude transcript path, which starts at t=0: Gemini's draft wins if it arrives in time (it sees the
    screen); otherwise Claude's is used, usually already finished. Errors from every engine are raised
    together; nothing is made up."""
    order = engines()
    errors: list[str] = []

    async def claude_draft() -> dict:
        t0 = time.time()
        _emit("reading_transcript")
        info = await transcript.fetch_video_info(vid)
        _emit("writing_steps", f"{len(info.get('transcript') or [])} transcript lines")
        last: Exception | None = None
        for _attempt in range(2):
            try:
                draft = normalize_draft(await claude.watch_transcript(info, goal))
                break
            except ValueError as e:  # unusable timestamps / no steps: ask again
                last = e
        else:
            raise RuntimeError(f"unusable step list ({last})")
        log.info("claude video pass: %.1fs", time.time() - t0)
        draft["_built_by"] = f"{claude.last_model} (transcript via {info['sources'].get('transcript')})"
        draft["_engine"] = "claude"
        return draft

    async def gemini_draft() -> dict:
        t0 = time.time()
        cap = float(os.environ.get("LESSON_GEMINI_TIMEOUT", GEMINI_VIDEO_TIMEOUT_S))
        _emit("watching")
        try:
            meta = await asyncio.wait_for(transcript.fetch_metadata(vid), 10)
            context = transcript.format_metadata(meta) if meta.get("title") else ""
        except Exception:  # noqa: BLE001  metadata is a bonus for Gemini
            context = ""
        try:
            raw = await asyncio.wait_for(gemini.watch_video(url, goal, context=context), cap - (time.time() - t0))
        except TimeoutError as e:
            raise RuntimeError(f"no answer within {cap:.0f}s") from e
        try:
            draft = normalize_draft(raw)
        except ValueError as e:
            raise RuntimeError(f"unusable step list ({e})") from e
        log.info("gemini video pass: %.1fs", time.time() - t0)
        draft["_built_by"] = f"{gemini.last_model} (watched the video)"
        draft["_engine"] = "gemini"
        return draft

    tasks: dict[str, asyncio.Task] = {}
    if "claude" in order:
        tasks["claude"] = asyncio.create_task(claude_draft())
    if "gemini" in order:
        tasks["gemini"] = asyncio.create_task(gemini_draft())
    # LESSON_PREFER=claude goes back to Claude-first: Gemini only gets a short grace once Claude is ready
    default_grace = 8.0 if os.environ.get("LESSON_PREFER", "gemini").strip().lower() == "claude" else GEMINI_GRACE_S
    grace = float(os.environ.get("LESSON_GEMINI_GRACE", default_grace))
    claude_ready: dict | None = None
    try:
        pending = set(tasks.values())
        while pending:
            timeout = grace if claude_ready is not None else None
            done, pending = await asyncio.wait(pending, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if not done:  # Claude is ready and Gemini used up its grace period: don't keep the learner waiting
                errors.append(f"gemini: still watching {grace:.0f}s after the transcript draft was ready")
                _emit("engine_switch", "slow")
                break
            for t in done:
                eng = next(k for k, v in tasks.items() if v is t)
                try:
                    draft = t.result()
                except RuntimeError as e:
                    errors.append(f"{eng}: {str(e)[:300]}")
                    log.warning("%s video pass failed: %s", eng, str(e)[:200])
                    if eng == "gemini" and "claude" in tasks:
                        _emit("engine_switch", _short_reason(str(e)))
                    continue
                if eng == "gemini":
                    _emit("steps_ready", "gemini")
                    return draft  # it saw the screen: preferred whenever it is in time
                claude_ready = draft
            if claude_ready is not None and "gemini" not in tasks:
                break
        if claude_ready is not None:
            _emit("steps_ready", "claude")
            if errors:
                claude_ready.setdefault("_notes", []).append("fallback engine: " + " | ".join(errors))
            return claude_ready
    finally:
        for t in tasks.values():
            if not t.done():
                t.cancel()  # the loser stops costing money
            elif not t.cancelled():
                t.exception()  # mark a failure we didn't need as retrieved
    raise RuntimeError("no engine could build the lesson:\n" + "\n".join(errors))


def _short_reason(err: str) -> str:
    e = err.lower()
    if "429" in e or "quota" in e or "resource_exhausted" in e:
        return "quota"
    if "no answer within" in e or "timeout" in e:
        return "slow"
    if "api key" in e or "401" in e or "403" in e:
        return "key"
    return "error"


ADAPT_BATCH = 3  # steps per adapt call; batches run in parallel


async def _adapt_call(goal: str, draft: dict, summary: str, feedback: list[str] | None) -> tuple[dict, str]:
    """The adapt pass is Claude's job (Gemini only watches videos). Steps go in parallel batches of
    ADAPT_BATCH, each with only its own feedback (plus graph-level problems). A batch that fails is
    left out (those steps keep the draft's checks); if every batch fails, the error is raised."""
    t0 = time.time()
    _emit("adapting", "retry" if feedback else "")
    steps = draft["steps"]
    batches = [steps[i:i + ADAPT_BATCH] for i in range(0, len(steps), ADAPT_BATCH)] or [[]]

    def fb_for(batch: list[dict]) -> list[str] | None:
        if not feedback:
            return feedback
        ids = {st["index"] for st in batch}
        return [p for p in feedback if not (m := _STEP_PROBLEM.match(p)) or int(m.group(1)) in ids] or None

    results = await asyncio.gather(*(claude.adapt_checks(goal, b, summary, fb_for(b)) for b in batches), return_exceptions=True)
    errs = [r for r in results if isinstance(r, BaseException)]
    if len(errs) == len(results):
        raise errs[0] if isinstance(errs[0], RuntimeError) else RuntimeError(str(errs[0]))
    for e in errs:
        log.warning("adapt batch failed: %s", str(e)[:200])
    merged = [st for r in results if isinstance(r, dict) for st in r.get("steps") or []]
    log.info("claude adapt pass: %.1fs (%d batch(es))", time.time() - t0, len(batches))
    return {"steps": merged}, str(claude.last_model)


async def _add_detail(url: str, draft: dict) -> None:
    sem = asyncio.Semaphore(DETAIL_CONCURRENCY)

    async def one(step: dict) -> None:
        async with sem:
            try:
                d = await gemini.step_detail(url, step["start"], step["end"], step["title"])
            except Exception as e:  # noqa: BLE001  detail is an enhancement; never fail the build on it
                log.warning("detail pass failed for step %s: %s", step["index"], e)
                draft.setdefault("detail_failures", []).append(f"s{step['index']}: clip pass failed ({str(e)[:120]})")
                return
        if len(d.get("code") or "") > len(step.get("code") or ""):
            step["code"] = d["code"]
        for k in ("file", "run_command", "terminal_output"):
            if d.get(k) and not step.get(k):
                step[k] = d[k]
        if d.get("printed_metrics"):
            step["printed_metrics"] = d["printed_metrics"]
        for lib in d.get("library_versions") or []:
            draft.setdefault("libraries", []).append(lib)

    await asyncio.gather(*(one(s) for s in draft["steps"]))


def parse_ts(v) -> float | None:
    """'7:42' -> 462, '1:02:03' -> 3723, '75s' / 75 -> 75."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower().rstrip("s")
    if not s:
        return None
    try:
        parts = [float(p) for p in s.split(":")]
    except ValueError:
        return None
    out = 0.0
    for p in parts:
        out = out * 60 + p
    return out


def normalize_draft(draft: dict) -> dict:
    """Parse timestamps, order steps, remove overlaps, number them 1..N."""
    steps = []
    for s in draft.get("steps") or []:
        start, end = parse_ts(s.get("start")), parse_ts(s.get("end"))
        if start is None or end is None:
            continue
        s = dict(s, start=start, end=max(end, start + 1))
        s["explanations"] = [
            {"topic": e.get("topic", ""), "t": t} for e in s.get("explanations") or [] if (t := parse_ts(e.get("t"))) is not None
        ]
        steps.append(s)
    if not steps:
        raise ValueError("no steps with parseable start/end timestamps")
    steps.sort(key=lambda s: s["start"])
    for a, b in zip(steps, steps[1:]):
        if a["end"] > b["start"]:
            a["end"] = max(b["start"], a["start"] + 1)
    steps = merge_micro_steps(steps)
    rehome_explanations(steps)
    for i, s in enumerate(steps, 1):
        s["index"] = i
    draft["steps"] = steps
    return draft


MIN_STEP_S = 20.0  # shorter steps pause the video every few seconds; fold them into a neighbour
_LIST_FIELDS = ("checks", "precision_checks", "targets", "explanations", "hints", "common_mistakes")


def merge_micro_steps(steps: list[dict], min_s: float = MIN_STEP_S, min_steps: int = 3) -> list[dict]:
    steps = [dict(s) for s in steps]
    while len(steps) > min_steps:
        short = [i for i, s in enumerate(steps) if s["end"] - s["start"] < min_s]
        if not short:
            break
        i = short[0]
        j = i - 1 if i > 0 else i + 1  # into the previous step (it usually set this one up), else the next
        a, b = sorted((i, j))
        x, y = steps[a], steps[b]
        keep = x if x["end"] - x["start"] >= y["end"] - y["start"] else y
        merged = {**y, **x, "start": x["start"], "end": y["end"], "title": keep.get("title", "")}
        merged["instructions"] = " ".join(t for t in (x.get("instructions"), y.get("instructions")) if t)
        for k in ("code", "expected_output", "terminal_output"):
            vals = [v for v in (x.get(k), y.get(k)) if v]
            if vals:
                merged[k] = "\n".join(vals)
        merged["run_command"] = y.get("run_command") or x.get("run_command")
        for k in _LIST_FIELDS:
            seen, out = set(), []
            for v in (x.get(k) or []) + (y.get(k) or []):
                key = json.dumps(v, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    out.append(v)
            merged[k] = out
        steps[a:b + 1] = [merged]
    return steps


def rehome_explanations(steps: list[dict]) -> None:
    """Each explanation goes to the step whose time range contains it (else the nearest), in time order."""
    pool = [e for s in steps for e in s.get("explanations") or []]
    for s in steps:
        s["explanations"] = []
    for e in pool:
        t = e["t"]
        best = min(steps, key=lambda s: 0 if s["start"] <= t < s["end"] else min(abs(t - s["start"]), abs(t - s["end"])))
        best["explanations"].append(e)
    for s in steps:
        s["explanations"].sort(key=lambda e: e["t"])


# --------------------------------------------------------------------------- #
# Pass 2: adapt checks to the workdir, validate, retry with feedback, repair
# --------------------------------------------------------------------------- #


_STEP_PROBLEM = re.compile(r"^s(\d+)[:/]")


async def _adapt(draft: dict, goal: str, info: WorkdirInfo) -> tuple[dict, list[str], bool, str | None]:
    """-> (graph, leftover warnings, whether any adapt call succeeded, model that served it).

    Round 1 adapts every step. Later rounds re-send only the steps that still have problems (with
    just their feedback), and the loop stops as soon as a round doesn't reduce the problem count,
    keeping the best graph seen; repair cleans up whatever is left."""
    known_files = set(info.files)
    adapted: dict[int, dict] = {}
    used: str | None = None
    best: tuple[int, dict] | None = None
    targets = list(draft["steps"])
    feedback: list[str] | None = None
    for attempt in range(ADAPT_ATTEMPTS):
        try:
            out, used = await _adapt_call(goal, {"steps": targets}, info.summary_for_prompt(), feedback)
        except RuntimeError as e:
            log.warning("adapt pass failed (attempt %d): %s", attempt + 1, e)
            if not adapted:  # nothing to improve on; the video draft's checks are the fallback
                graph = repair(normalize_checks(assemble(draft, goal, {"steps": []}), info.metrics), info)
                return graph, lint(graph, info.metrics, known_files), False, None
            break
        for st in out.get("steps") or []:
            if isinstance(st.get("index"), int):
                adapted[st["index"]] = st
        graph = normalize_checks(assemble(draft, goal, {"steps": list(adapted.values())}), info.metrics)
        problems = schema_errors(graph) + lint(graph, info.metrics, known_files)
        if not problems:
            return graph, [], True, used
        if best is not None and len(problems) >= best[0]:
            log.info("adapt attempt %d: %d problems (no better than %d); stopping", attempt + 1, len(problems), best[0])
            break
        best = (len(problems), graph)
        bad = {int(m.group(1)) for p in problems if (m := _STEP_PROBLEM.match(p))}
        graph_level = [p for p in problems if not _STEP_PROBLEM.match(p)]
        targets = [st for st in draft["steps"] if graph_level or st["index"] in bad]
        feedback = problems
        log.info("adapt attempt %d: %d problems in %d step(s), retrying those", attempt + 1, len(problems), len(targets))
    graph = repair(best[1] if best else graph, info)
    return graph, lint(graph, info.metrics, known_files), True, used


def assemble(draft: dict, goal: str, adapted: dict) -> dict:
    by_index = {s.get("index"): s for s in adapted.get("steps") or []}
    libs: dict[str, str] = {}
    for lib in draft.get("libraries") or []:
        name, ver = (lib.get("name") or "").strip(), (lib.get("version") or "").strip()
        if name and (name not in libs or (ver and not libs[name])):
            libs[name] = ver
    # notebook tutorials: a cell with code is "run" too, so its output rule applies (Gemini drafts leave run_command empty)
    files = " ".join(draft.get("files") or []) + " " + " ".join(libs)
    notebook = bool(re.search(r"\.ipynb\b|jupyter|ipykernel|colab|notebook", files, re.I))
    steps = []
    for s in draft["steps"]:
        i = s["index"]
        a = by_index.get(i) or {}
        draft_checks = s.get("checks") or []
        checks = a.get("checks") or [c for c in draft_checks if c.get("type") in SCREEN_TYPES]
        precision = a.get("precision_checks") or []
        if not a:  # adapt pass gave nothing for this step: keep the video draft's file/command checks as backups
            precision = [c for c in draft_checks if c.get("type") in PRECISION_TYPES and c.get("type") not in SCREEN_TYPES]
        targets = a.get("targets") if a.get("targets") else s.get("targets") or []
        checks = [c for j, raw in enumerate(checks, 1) if (c := clean_check(raw, f"s{i}c{j}"))]
        precision = [c for j, raw in enumerate(precision, 1) if (c := clean_check(raw, f"s{i}p{j}"))]
        steps.append(
            {
                "id": f"s{i}",
                "index": i,
                "title": _clip_words(s.get("title", f"Step {i}"), 6),
                "instructions": (a.get("instructions") or s.get("instructions") or "").strip(),
                "video": {"sourceId": "src1", "start": s["start"], "end": s["end"]},
                "checks": checks,
                "precision_checks": precision,
                "targets": [{k: t[k] for k in ("app", "file", "match", "caption") if t.get(k)} for t in targets if t.get("match")],
                "explanations": [{"topic": e["topic"], "t": e["t"], "sourceId": "src1"} for e in s.get("explanations") or []],
                "hints": [h for h in s.get("hints") or [] if h],
                "common_mistakes": [m for m in s.get("common_mistakes") or [] if m],
                **({"run_command": s["run_command"].strip()} if (s.get("run_command") or "").strip()
                   else {"run_command": NOTEBOOK_RUN} if notebook and (s.get("code") or "").strip() else {}),
                **({"code": s["code"]} if (s.get("code") or "").strip() else {}),
            }
        )
    return {
        "lesson": {"id": "", "title": draft.get("title") or goal, "goal": goal, "libraries": libs},
        "sources": [],
        "steps": steps,
    }


BROWSER_APPS = {"google chrome", "chrome", "safari", "arc", "firefox", "microsoft edge", "edge", "brave browser", "brave", "browser"}


def normalize_checks(graph: dict, known_metrics: set[str]) -> dict:
    """Deterministic fixes applied before lint (no model call)."""
    libs = (graph.get("lesson") or {}).get("libraries") or {}
    for step in graph["steps"]:
        # "it runs" checks: a Python Traceback never shows up in a Vite/cargo/git terminal
        stack = stack_of(step, libs if not step.get("run_command") and not step.get("code") else None)
        for c in step["checks"]:
            if c.get("type") == "screen_absent" and "Traceback" in (c.get("pattern") or "") and stack and stack != "python":
                c["pattern"] = standard_error_pattern(stack)
        # The learner's browser is unknown: a browser-scoped check/target matches text in any window instead.
        for item in step["checks"] + step.get("targets", []):
            if (item.get("app") or "").strip().lower() in BROWSER_APPS:
                item.pop("app")
        for c in step["checks"] + step.get("precision_checks", []):
            if c.get("pattern") and looks_like_literal(c["pattern"]):
                c["pattern"] = literal_pattern(c["pattern"])
    complete_metric_checks(graph, known_metrics)
    return align_precision_metrics(graph)


def align_precision_metrics(graph: dict) -> dict:
    """A precision-mode backup must never be looser than the screen check for the same metric in the
    same step: in precision mode the gate passes on the backups, so a looser one turns a failing
    run green (e.g. screen loss < 1e-2 by 2000 but backup loss < 0.05 with no deadline)."""
    for step in graph["steps"]:
        screen = {c.get("metric"): c for c in step["checks"] if c.get("type") == "metric_threshold" and c.get("metric")}
        for c in step.get("precision_checks", []):
            ref = screen.get(c.get("metric")) if c.get("type") == "metric_threshold" else None
            if not ref or ref.get("op") is None or c.get("op") is None:
                continue
            down = ref["op"] in ("<", "<=")
            if down != (c["op"] in ("<", "<=")):
                continue
            looser_value = c.get("value") is None or (c["value"] > ref["value"] if down else c["value"] < ref["value"])
            looser_op = ref["op"] in ("<", ">") and c["op"] in ("<=", ">=") and c.get("value") == ref["value"]
            looser_deadline = ref.get("by_step") is not None and (c.get("by_step") is None or c["by_step"] > ref["by_step"])
            if looser_value or looser_op or looser_deadline:
                c.update(op=ref["op"], value=ref["value"], label=ref.get("label", c.get("label")))
                if ref.get("by_step") is not None:
                    c["by_step"] = ref["by_step"]
    return graph


def looks_like_literal(p: str) -> bool:
    """A code snippet pasted as a regex, e.g. "lhs(2, Nf)": its parentheses become a group, so it
    can never match the very text it was copied from. Real regexes with groups use \\ or |."""
    if "\\" in p or "|" in p or not re.search(r"[()\[\].+*?]", p):
        return False
    try:
        return re.search(p, p) is None
    except re.error:
        return True


def literal_pattern(text: str) -> str:
    """Literal text as an OCR/whitespace-tolerant regex."""
    return r"\s*".join(re.escape(tok) for tok in text.split())


def protocol_metric_pattern(metric: str) -> str:
    """Reads one ::metric:: line (shared/contracts/metric-protocol.md) off the screen.
    Punctuation-agnostic (\\W+) because OCR mangles quotes and braces."""
    return r"step\W+(?P<step>\d+)\W+name\W+" + re.escape(metric) + r"\W+value\W+(?P<value>[0-9.eE+-]+)"


def complete_metric_checks(graph: dict, known_metrics: set[str]) -> dict:
    """Deterministic fixes for metric checks on ::metric:: names the workdir really prints:
    give screen metric checks the protocol metric_pattern when the model left it out, and
    promote a step's precision-only metric check to a screen check (screen mode would
    otherwise never grade the loss)."""
    if not known_metrics:
        return graph
    for step in graph["steps"]:
        screen_metrics = [c for c in step["checks"] if c["type"].startswith("metric_")]
        for c in screen_metrics:
            if not c.get("metric_pattern") and c.get("metric") in known_metrics:
                c["metric_pattern"] = protocol_metric_pattern(c["metric"])
        if not screen_metrics:
            for c in step.get("precision_checks", []):
                if c["type"].startswith("metric_") and c.get("metric") in known_metrics:
                    promoted = dict(c, metric_pattern=c.get("metric_pattern") or protocol_metric_pattern(c["metric"]))
                    promoted["id"] = f"{step['id']}c{len(step['checks']) + 1}"
                    step["checks"].append(promoted)
                    break
    return graph


NOTEBOOK_RUN = "Run the cell (Shift+Enter)"


def clean_check(raw: dict, cid: str) -> dict | None:
    t = raw.get("type")
    if t not in CHECK_TYPES:
        return None
    c = {"id": cid, "type": t, "label": _clip_words(raw.get("label") or t.replace("_", " "), 6)}
    for k in _CHECK_FIELDS[t]:
        v = raw.get(k)
        if v is None or v == "":
            continue
        if k in ("by_step", "window"):
            try:
                v = int(v)
            except (TypeError, ValueError):
                continue
        c[k] = v
    return c


def repair(graph: dict, info: WorkdirInfo) -> dict:
    """Deterministically remove checks that lint still rejects; never leave a step ungradable."""
    g = copy.deepcopy(graph)
    for step in g["steps"]:
        # file_*/command_* placed in the screen list: move them to the backups instead of dropping them
        misplaced = [c for c in step.get("checks", []) if c.get("type") in PRECISION_TYPES and c.get("type") not in SCREEN_TYPES]
        step["checks"] = [c for c in step.get("checks", []) if c not in misplaced]
        step["precision_checks"] = step.get("precision_checks", []) + misplaced
        for key, allowed, tag in (("checks", SCREEN_TYPES, "c"), ("precision_checks", PRECISION_TYPES, "p")):
            kept = [c for c in step.get(key, []) if not check_problems(c, allowed, key, info.metrics, set(info.files))
                    and not (key == "checks" and step_check_problems(c, step))]
            if key == "checks" and (step.get("run_command") or "").strip() and not any(is_output_check(c, step) for c in kept):
                std = standard_output_check(step)  # a run step the model left without an output check
                if std and not step_check_problems(std, step):
                    kept.append(std)
            if key == "checks" and not kept:
                kept = fallback_screen_checks(step)
            for j, c in enumerate(kept, 1):  # renumber so ids stay unique and stable
                c["id"] = f"{step['id']}{tag}{j}"
            step[key] = kept
    return g


def fallback_screen_checks(step: dict) -> list[dict]:
    """Last resort: the step's first target, as a literal on-screen match."""
    for t in step.get("targets", []):
        frag = (t.get("match") or "").strip()
        if 3 <= len(frag):
            return [{"id": "", "type": "screen_contains", "label": _clip_words(t.get("caption") or frag, 6),
                     "app": t.get("app") or "Code", "pattern": literal_pattern(frag)[:80]}]
    return []


def _clip_words(s: str, n: int) -> str:
    words = re.sub(r"\s+", " ", s or "").strip().split(" ")
    return " ".join(words[:n])
