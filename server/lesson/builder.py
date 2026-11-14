"""build_lesson: YouTube URL -> validated, workdir-adapted step graph (cached)."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import re
import time
from pathlib import Path

from . import gemini
from .schema import CHECK_TYPES, PRECISION_TYPES, REPO_ROOT, SCREEN_TYPES, check_problems, lint, schema_errors
from .workdir import WorkdirInfo, scan

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
) -> dict:
    """Return a step graph that validates against shared/contracts/step-graph.schema.json.

    Each step has screen-first `checks` (screen_* / metric_* with metric_pattern) and, as an
    extra field, `precision_checks` (file_* / command_* / ::metric:: backups for `tut run`).
    api_key: the app's bring-your-own Gemini key (config.keys.gemini); falls back to .env.
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
    vid = gemini.youtube_id(source_url)
    if not vid:
        raise ValueError(f"only YouTube sources are supported for now: {source_url!r}")
    info = scan(workdir)
    key = cache_key(source_url, goal, workdir, info)
    path = CACHE_DIR / f"{key}.json"
    if path.is_file() and not (refresh or readapt):
        graph = json.loads(path.read_text())
        graph["lesson"]["workdir"] = workdir
        log.info("lesson cache hit %s", path.name)
        return graph

    if api_key:
        gemini.set_api_key(api_key)
    t0 = time.time()
    draft = await _video_draft(source_url, vid, goal, refresh=refresh, detail=detail)
    graph, warnings, adapted_ok = await _adapt(draft, goal, info)
    warnings = list(draft.get("detail_failures") or []) + warnings
    if not adapted_ok:
        warnings = ["adapt pass failed (quota?): checks come from the video draft, not the learner's workdir; not cached, retry with readapt=True"] + warnings
    n_signals = await add_community_mistakes(graph, source_url)
    graph["lesson"]["id"] = f"lesson-{key[:8]}"
    graph["lesson"]["workdir"] = workdir
    graph["sources"] = [{"id": "src1", "kind": "video", "title": draft.get("title") or "Tutorial", "url": source_url, "videoId": vid}]
    graph["build"] = {
        "adapted": adapted_ok,
        "models": {"video": gemini.model(), "detail+adapt": gemini.model(fast=True)},
        "seconds": round(time.time() - t0, 1),
        "workdir_metrics": sorted(info.metrics),
        "community_signals": n_signals,
        "warnings": warnings,
    }
    errs = schema_errors(graph)
    if errs:
        raise RuntimeError("step graph failed contract validation:\n" + "\n".join(errs))
    if not adapted_ok:
        log.warning("lesson built in %.1fs WITHOUT adapt pass; not cached", time.time() - t0)
        return graph
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, indent=2))
    log.info("lesson built in %.1fs -> %s (%d warnings)", time.time() - t0, path, len(warnings))
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


def cache_key(source_url: str, goal: str, workdir: str, info: WorkdirInfo | None = None) -> str:
    vid = gemini.youtube_id(source_url) or source_url
    norm_goal = " ".join(goal.lower().split())
    name = Path(workdir).expanduser().resolve().name
    info = info or scan(workdir)
    fingerprint = [sorted(info.files), sorted(info.metrics)]
    return hashlib.sha256(json.dumps([vid, norm_goal, name, fingerprint]).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Pass 1: video -> draft (cached per video+goal)
# --------------------------------------------------------------------------- #


async def _video_draft(url: str, vid: str, goal: str, *, refresh: bool, detail: bool) -> dict:
    gh = hashlib.sha256(" ".join(goal.lower().split()).encode()).hexdigest()[:8]
    raw_path = RAW_DIR / f"{vid}-{gh}.json"
    if raw_path.is_file() and not refresh:
        return json.loads(raw_path.read_text())

    last_err = None
    for _ in range(2):
        draft = await gemini.watch_video(url, goal)
        try:
            draft = normalize_draft(draft)
            break
        except ValueError as e:  # unusable timestamps / no steps: ask again
            last_err = e
            log.warning("video draft rejected: %s", e)
    else:
        raise RuntimeError(f"Gemini returned no usable step list: {last_err}")

    if detail:
        await _add_detail(url, draft)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(draft, indent=2))
    return draft


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
    for i, s in enumerate(steps, 1):
        s["index"] = i
    draft["steps"] = steps
    return draft


# --------------------------------------------------------------------------- #
# Pass 2: adapt checks to the workdir, validate, retry with feedback, repair
# --------------------------------------------------------------------------- #


async def _adapt(draft: dict, goal: str, info: WorkdirInfo) -> tuple[dict, list[str], bool]:
    """-> (graph, leftover warnings, whether any adapt call succeeded)."""
    feedback: list[str] | None = None
    graph = None
    ok = False
    known_files = set(info.files)
    for attempt in range(ADAPT_ATTEMPTS):
        try:
            adapted = await gemini.adapt_checks(goal, draft["steps"], info.summary_for_prompt(), feedback)
            ok = True
        except RuntimeError as e:
            log.warning("adapt pass failed (attempt %d): %s", attempt + 1, e)
            if not ok:  # nothing to improve on; the video draft's checks are the fallback
                graph = repair(normalize_checks(assemble(draft, goal, {"steps": []}), info.metrics), info)
                return graph, lint(graph, info.metrics, known_files), False
            break
        graph = normalize_checks(assemble(draft, goal, adapted), info.metrics)
        feedback = schema_errors(graph) + lint(graph, info.metrics, known_files)
        if not feedback:
            return graph, [], True
        log.info("adapt attempt %d: %d problems, retrying", attempt + 1, len(feedback))
    # Out of retries: drop checks that are still broken so the graph is at least runnable.
    graph = repair(graph, info)
    return graph, lint(graph, info.metrics, known_files), ok


def assemble(draft: dict, goal: str, adapted: dict) -> dict:
    by_index = {s.get("index"): s for s in adapted.get("steps") or []}
    libs: dict[str, str] = {}
    for lib in draft.get("libraries") or []:
        name, ver = (lib.get("name") or "").strip(), (lib.get("version") or "").strip()
        if name and (name not in libs or (ver and not libs[name])):
            libs[name] = ver
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
            }
        )
    return {
        "lesson": {"id": "", "title": draft.get("title") or goal, "goal": goal, "libraries": libs},
        "sources": [],
        "steps": steps,
    }


def normalize_checks(graph: dict, known_metrics: set[str]) -> dict:
    """Deterministic fixes applied before lint (no model call)."""
    for step in graph["steps"]:
        for c in step["checks"] + step.get("precision_checks", []):
            if c.get("pattern") and looks_like_literal(c["pattern"]):
                c["pattern"] = literal_pattern(c["pattern"])
    return complete_metric_checks(graph, known_metrics)


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
            kept = [c for c in step.get(key, []) if not check_problems(c, allowed, key, info.metrics, set(info.files))]
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
