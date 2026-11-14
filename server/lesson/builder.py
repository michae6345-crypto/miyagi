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
from .schema import CHECK_TYPES, REPO_ROOT, lint, schema_errors
from .workdir import WorkdirInfo, scan

log = logging.getLogger("server.lesson")

CACHE_DIR = REPO_ROOT / "demo" / "cache" / "lessons"
RAW_DIR = CACHE_DIR / "raw"  # video-only drafts, reusable across workdirs
ADAPT_ATTEMPTS = 3
DETAIL_CONCURRENCY = 4

_CHECK_FIELDS = {
    "file_exists": ("file",),
    "file_contains": ("file", "pattern"),
    "command_exit_ok": ("command",),
    "output_contains": ("pattern",),
    "metric_threshold": ("metric", "op", "value", "by_step"),
    "metric_trend": ("metric", "trend", "window"),
}


async def build_lesson(source_url: str, goal: str, workdir: str, *, refresh: bool = False, detail: bool = True) -> dict:
    """Return a step graph that validates against shared/contracts/step-graph.schema.json.

    Cached at demo/cache/lessons/<hash>.json; the cache wins unless refresh=True, so the
    demo never waits on Gemini. The hash covers the video, the goal and the workdir *name*
    (not its absolute path or contents, so the cache survives other laptops and edits).
    """
    vid = gemini.youtube_id(source_url)
    if not vid:
        raise ValueError(f"only YouTube sources are supported for now: {source_url!r}")
    key = cache_key(source_url, goal, workdir)
    path = CACHE_DIR / f"{key}.json"
    if path.is_file() and not refresh:
        graph = json.loads(path.read_text())
        graph["lesson"]["workdir"] = workdir
        log.info("lesson cache hit %s", path.name)
        return graph

    t0 = time.time()
    draft = await _video_draft(source_url, vid, goal, refresh=refresh, detail=detail)
    info = scan(workdir)
    graph, warnings = await _adapt(draft, goal, info)
    graph["lesson"]["id"] = f"lesson-{key[:8]}"
    graph["lesson"]["workdir"] = workdir
    graph["sources"] = [{"id": "src1", "kind": "video", "title": draft.get("title") or "Tutorial", "url": source_url, "videoId": vid}]
    graph["build"] = {
        "models": {"video": gemini.model(), "detail+adapt": gemini.model(fast=True)},
        "seconds": round(time.time() - t0, 1),
        "workdir_metrics": sorted(info.metrics),
        "warnings": warnings,
    }
    errs = schema_errors(graph)
    if errs:
        raise RuntimeError("step graph failed contract validation:\n" + "\n".join(errs))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, indent=2))
    log.info("lesson built in %.1fs -> %s (%d warnings)", time.time() - t0, path, len(warnings))
    return graph


def cache_key(source_url: str, goal: str, workdir: str) -> str:
    vid = gemini.youtube_id(source_url) or source_url
    norm_goal = " ".join(goal.lower().split())
    name = Path(workdir).expanduser().resolve().name
    return hashlib.sha256(json.dumps([vid, norm_goal, name]).encode()).hexdigest()[:16]


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
            except Exception as e:  # detail is an enhancement; never fail the build on it
                log.warning("detail pass failed for step %s: %s", step["index"], e)
                return
        if len(d.get("code") or "") > len(step.get("code") or ""):
            step["code"] = d["code"]
        for k in ("file", "run_command"):
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


async def _adapt(draft: dict, goal: str, info: WorkdirInfo) -> tuple[dict, list[str]]:
    feedback: list[str] | None = None
    graph = None
    known_files = set(info.files)
    for attempt in range(ADAPT_ATTEMPTS):
        try:
            adapted = await gemini.adapt_checks(goal, draft["steps"], info.summary_for_prompt(), feedback)
        except RuntimeError as e:
            log.warning("adapt pass failed (attempt %d): %s", attempt + 1, e)
            adapted = {"steps": []}
        graph = assemble(draft, goal, adapted)
        feedback = schema_errors(graph) + lint(graph, info.metrics, known_files)
        if not feedback:
            return graph, []
        log.info("adapt attempt %d: %d problems, retrying", attempt + 1, len(feedback))
    # Out of retries: drop checks that are still broken so the graph is at least runnable.
    graph = repair(graph, info)
    return graph, lint(graph, info.metrics, known_files)


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
        checks = a.get("checks") if a.get("checks") else s.get("checks") or []
        targets = a.get("targets") if a.get("targets") else s.get("targets") or []
        steps.append(
            {
                "id": f"s{i}",
                "index": i,
                "title": _clip_words(s.get("title", f"Step {i}"), 6),
                "instructions": (a.get("instructions") or s.get("instructions") or "").strip(),
                "video": {"sourceId": "src1", "start": s["start"], "end": s["end"]},
                "checks": [c for j, raw in enumerate(checks, 1) if (c := clean_check(raw, f"s{i}c{j}"))],
                "targets": [{k: t[k] for k in ("file", "match", "caption") if t.get(k)} for t in targets if t.get("match")],
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
    """Deterministically remove checks that lint still rejects."""
    g = copy.deepcopy(graph)
    for step in g["steps"]:
        keep = []
        for c in step["checks"]:
            probe = {"steps": [{"id": step["id"], "title": "x", "checks": [c]}]}
            if not lint(probe, info.metrics, set(info.files)):
                keep.append(c)
        step["checks"] = keep
        # renumber so ids stay unique and stable
        for j, c in enumerate(step["checks"], 1):
            c["id"] = f"{step['id']}c{j}"
    return g


def _clip_words(s: str, n: int) -> str:
    words = re.sub(r"\s+", " ", s or "").strip().split(" ")
    return " ".join(words[:n])
