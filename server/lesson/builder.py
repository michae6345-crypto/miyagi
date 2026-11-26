"""build_lesson: YouTube URL -> validated, workdir-adapted step graph (cached)."""

from __future__ import annotations

import asyncio
import contextvars
import copy
import hashlib
import itertools
import json
import logging
import re
import time
from pathlib import Path

import os

from . import app_lesson, batched, budget, claude, first_step, gemini, links, materials, timing, transcript
from .transcript import parse_ts  # noqa: F401  (re-exported: claude.py, progressive.py, tests use builder.parse_ts)
from .schema import (
    CHECK_TYPES,
    PRECISION_TYPES,
    REPO_ROOT,
    allowed_for,
    SCREEN_TYPES,
    check_problems,
    is_output_check,
    is_scene_check,
    lint,
    stack_of,
    standard_error_pattern,
    schema_errors,
    spans_lines,
    standard_output_check,
    step_check_problems,
    validate_untrusted_lesson,
    value_line,
)
from .notebook_steps import use_lesson_notebook
from .venv_steps import use_lesson_venv
from .workdir import WorkdirInfo, scan
from server.safety.patterns import safe_search
from server.safety import regex_worker
from server.untrusted import flag_injection

# Progress for the UI. Stable stage ids (the app maps them to text; log wording may change):
#   cache_hit, watching (Gemini watches the video), reading_transcript, writing_steps (Claude),
#   engine_switch (Gemini failed/slow -> transcript path; message says why), steps_ready (message = engine),
#   adapting (fitting checks to the learner's project), done
#   transcript_only (the learner chose "Try transcript only": no video model runs; message = why)
#   long videos also: planning (msg = "N parts"), first_steps (part 1 ready), more_steps (msg = "part k/N")
STAGES = ("cache_hit", "watching", "reading_transcript", "writing_steps", "engine_switch", "steps_ready", "adapting", "done",
          "planning", "first_steps", "more_steps", "provisional", "transcript_only")
_progress: contextvars.ContextVar = contextvars.ContextVar("lesson_progress", default=None)
_material_urls: contextvars.ContextVar = contextvars.ContextVar("lesson_material_urls", default=())
# this build's captions + linked code, fetched from the start while the lesson caches are asked (_start_prefetch)
_prefetched: contextvars.ContextVar = contextvars.ContextVar("lesson_prefetched", default=None)
_first: contextvars.ContextVar = contextvars.ContextVar("lesson_first_step", default=None)  # first_step.FirstStep
_batched: contextvars.ContextVar = contextvars.ContextVar("lesson_batched", default=None)  # batched.BatchedAdapt


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

_BUILD_SERIAL = itertools.count(1)  # each build's regex budget key
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


QUICK_START_S = float(os.environ.get("LESSON_QUICK_START_S", "8"))


async def build_lesson(
    source_url: str,
    goal: str,
    workdir: str,
    *,
    on_update=None,
    on_progress=None,
    video_meta: dict | None = None,
    transcript_only: bool = False,
    _prebuild: bool = False,
    **kw,
) -> dict:
    """See _build_lesson_impl. Adds two speed-ups around it:
    - attaches to a speculative prebuild (prebuild.prebuild) of the same video + workdir, if any;
    - quick start: when on_update is given and no real steps arrive within LESSON_QUICK_START_S (8 s),
      a provisional step 1 built from the chapter list is sent (lesson.provisional=True, step.provisional
      =True); the real steps replace it via on_update (same ids s1, s2, ...), ending with complete=True."""
    from . import prebuild

    on_update = _validated_updates(on_update, workdir)  # LLM06: every graph streamed to the session is checked too
    vid = gemini.youtube_id(source_url)
    if vid and not _prebuild:
        prebuild.cancel(except_vid=vid)  # a lesson is starting: stop speculating on the other results
        # transcript_only never attaches: a speculative prebuild may be Gemini watching the video
        attached = None if transcript_only else await prebuild.attach(vid, workdir, on_update, on_progress)
        if attached is not None:
            _share_fresh(attached, vid)  # a speculative prebuild the learner just picked: its good build is shared now
            return _untrusted(attached, workdir)
    from . import cost

    counter = cost.current() if _prebuild else None
    counter = counter or cost.start("prebuild" if _prebuild else "lesson")
    qs = _QuickStart(on_update, vid, source_url, goal, workdir, video_meta) if (on_update and vid) else None
    # build_cost is emitted however the build ends (ok / failed / cancelled), so its dollars are never lost. The
    # build's own regex budget: the model's patterns it lints never count against (or stop) the lesson running now
    with cost.build_scope(counter, kind="prebuild" if _prebuild else "video") as scope, \
            regex_worker.budget(("build", next(_BUILD_SERIAL))):
        try:
            g = await _build_lesson_impl(source_url, goal, workdir, on_update=qs.wrapped if qs else on_update,
                                         on_progress=on_progress, video_meta=video_meta,
                                         transcript_only=transcript_only, **({"claim": False} if _prebuild else {}), **kw)
            if not g.get("build", {}).get("cost") and counter.get("tokens"):
                g.setdefault("build", {})["cost"] = json.loads(json.dumps(counter))  # model calls + tokens + dollars per model
            scope["lesson_id"] = (g.get("lesson") or {}).get("id")
            _untrusted(g, workdir)  # a model's (or the cache's) graph: paths, commands, regexes, sources checked
            if not _prebuild:
                _share_fresh(g, vid, share=not (kw.get("refresh") or kw.get("readapt")))  # a prebuild keeps its marker for the attach that adopts it
            if qs:
                await qs.finish(g)
            return g
        except BaseException:
            if qs:
                qs.stop(delivery=True)
            raise
        finally:
            if qs:
                qs.stop()


def _share_fresh(graph: dict, vid: str | None, share: bool = True) -> None:
    """A graph this process just built (build.fresh, set where it is written to the cache): upload it to the shared
    lesson cache in the background when it is a good build. The marker is dropped so it never reaches the app or a
    saved session. A refresh / readapt build (the learner asked for a new one) is not shared."""
    build = graph.get("build") if isinstance(graph, dict) else None
    if not isinstance(build, dict) or not build.pop("fresh", None) or not vid or not share:
        return
    from . import cloud_cache

    cloud_cache.share_later(copy.deepcopy(graph), vid)


def _untrusted(graph: dict, workdir: str | None) -> dict:
    """schema.validate_untrusted_lesson on a built or cached graph (in place); logs what it changed."""
    if isinstance(graph, dict):
        for note in validate_untrusted_lesson(graph, workdir):
            log.warning("lesson %s: %s", (graph.get("lesson") or {}).get("id"), note)
    return graph


def _validated_updates(on_update, workdir: str | None):
    """on_update(graph, complete) with each streamed graph validated first (None stays None)."""
    if on_update is None:
        return None

    def wrapped(graph: dict, complete: bool):
        return on_update(_untrusted(graph, workdir), complete)

    return wrapped


class _QuickStart:
    def __init__(self, on_update, vid, url, goal, workdir, video_meta):
        self.on_update, self.vid, self.url, self.goal, self.workdir, self.video_meta = on_update, vid, url, goal, workdir, video_meta
        self.real_sent = self.final_sent = self.provisional_sent = False
        self.timer = asyncio.ensure_future(self._fire())

    async def wrapped(self, graph: dict, complete: bool) -> None:
        self.real_sent = True
        self.final_sent = self.final_sent or complete
        self.stop()
        r = self.on_update(graph, complete)
        if asyncio.iscoroutine(r):
            await r

    async def _fire(self) -> None:
        await asyncio.sleep(QUICK_START_S)
        if self.real_sent:
            return
        try:
            meta = normalize_video_meta(self.video_meta) if self.video_meta else {}
            if not meta.get("title"):
                meta = {**await asyncio.wait_for(transcript.fetch_metadata(self.vid), 5), **{k: v for k, v in meta.items() if v}}
            g = provisional_graph(meta, self.vid, self.url, self.goal, self.workdir)
        except Exception as e:  # noqa: BLE001  quick start is a bonus
            log.info("quick start skipped: %s", e)
            return
        if self.real_sent:
            return
        self.provisional_sent = True
        log.info("quick start: provisional step 1 (%s) sent after %.0fs", g["steps"][0]["title"], QUICK_START_S)
        _emit("provisional", g["steps"][0]["title"])
        try:
            r = self.on_update(g, False)
            if asyncio.iscoroutine(r):
                await r
        except Exception as e:  # noqa: BLE001
            log.warning("on_update failed: %s", e)

    async def finish(self, graph: dict) -> None:
        """The app saw a provisional step: make sure it gets the real, complete lesson through on_update too."""
        self.stop()
        if self.provisional_sent and not self.final_sent:
            await self.wrapped(graph, True)

    def stop(self, *, delivery: bool = False) -> None:
        """No placeholder any more. One already on its way (its on_update may be preparing the lesson folder, a
        Claude call of up to ~25 s, or in the "ready" hold) is left to land, so the real steps that follow it are
        loaded over it, not into a lesson that never loaded; `delivery` (the build failed or was cancelled) stops it
        too."""
        if delivery or not self.provisional_sent:
            self.timer.cancel()


_INTRO = re.compile(r"\b(intro(duction)?|welcome|overview|about|agenda|preview|demo|what we.?ll build)\b", re.I)
_SETUP_CHAPTER = re.compile(r"\b(install(ing|ation)?|download(ing)?|set\s*-?\s*up|setup|prerequisites?|requirements|getting\s+started|environment)\b", re.I)


def provisional_graph(meta: dict, vid: str, url: str, goal: str, workdir: str) -> dict:
    """Step 1 from the chapter list alone, shown while the video is still being watched."""
    chapters = meta.get("chapters") or []
    length = float(meta.get("length_s") or 0) or None
    start, title = 0.0, ""
    if meta.get("first_hands_on"):
        start = float(meta["first_hands_on"])
        title = next((c["title"] for c in reversed(chapters) if c["t"] <= start), "")
    elif chapters:
        # the placeholder is a watch-along step: start at the first hands-on chapter, not an intro or install chapter
        hands_on = [c for c in chapters if not (_INTRO.search(c["title"]) or _SETUP_CHAPTER.search(c["title"]))]
        c = hands_on[0] if hands_on else (chapters[1] if len(chapters) > 1 else chapters[0])
        start, title = float(c["t"]), c["title"]
    if title and flag_injection(title):  # the uploader's text talking to an AI: never the learner's step title
        log.warning("provisional step: chapter title dropped (talks to an AI): %r", title[:120])
        title = ""
    nxt = [c["t"] for c in chapters if c["t"] > start]
    end = min(nxt[0] if nxt else start + 300, length or start + 300, start + 600)
    end = max(end, start + 30)
    label = _clip_words(title or "Follow along with the video", 6)
    # Nov 22: "type along in your editor" only where there is an editor: an AutoCAD video follows along in AutoCAD,
    # a no-code / conceptual one (preflight's style) just follows along
    # a coding video that names an app ("Automate Excel with Python openpyxl") still types along in the editor, as
    # app_lesson.adapt never touches a code lesson
    style = str(meta.get("style") or "").lower()
    coding = style == "coding" or (not style and app_lesson.CODE_TITLE.search(str(meta.get("title") or "")))
    app = None if coding else app_lesson.work_app({"lesson": {"title": meta.get("title") or ""}})
    along = (f"follow along in {app_lesson._apps().label(app)}" if app
             else "follow along" if style in ("no-code", "no_code", "conceptual") else "type along in your editor")
    step = {
        "id": "s1", "index": 1, "title": label, "provisional": True,
        "instructions": (f"Watch {gemini._mmss(start)}-{gemini._mmss(end)}"
                         + (f" ({title})" if title else "") + f" and {along}; detailed steps are on the way."),
        "video": {"sourceId": "src1", "start": start, "end": end},
        "checks": [],  # a watch-along placeholder must never gate (an app-scoped check can wait forever); the real lesson replaces it
        "targets": [], "explanations": [], "hints": [], "common_mistakes": [],
    }
    g = {"lesson": {"id": f"lesson-{cache_key(url, goal, workdir)[:8]}", "title": meta.get("title") or goal or "Tutorial",
                    "goal": goal, "workdir": workdir, "libraries": {}, "complete": False, "provisional": True, "builtBy": "chapters"},
         "sources": [{"id": "src1", "kind": "video", "title": meta.get("title") or "Tutorial", "url": url, "videoId": vid}],
         "steps": [step], "build": {"provisional": True, "warnings": []}}
    return g


async def _build_lesson_impl(
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
    claim: bool = True,
    on_progress=None,
    on_update=None,
    video_meta: dict | None = None,
    transcript_only: bool = False,
    material_urls: list[str] | None = None,
) -> dict:
    """Return a step graph that validates against shared/contracts/step-graph.schema.json.

    Each step has screen-first `checks` (screen_* / metric_* with metric_pattern) and, as an
    extra field, `precision_checks` (file_* / command_* / ::metric:: backups for `tut run`).
    Engines (LESSON_ENGINE=claude|auto|claude-first|gemini, default claude; see engine_mode): by default Claude
    builds the graph from the video's transcript + title/description/chapters (and the tutorial's linked code), with
    step starts pinned to chapter marks / caption lines; Gemini is never called. Gemini watches the video only when
    LESSON_ENGINE names it explicitly AND a Gemini key is present (gemini_enabled); a gemini_disabled 403 from the
    miyagi cloud turns it off for the process. build.model records which model did what. If every engine tried fails
    the error is raised, never papered over with made-up steps.
    api_key / anthropic_key: the app's bring-your-own keys (config.keys.gemini / .anthropic).
    on_progress(stage, message): optional callback (sync or async) with a stage id from STAGES.
    on_update(graph, complete): long videos (> LESSON_LONG_VIDEO_S, 30 min) are built progressively:
      part 1 first (complete=False), then each later part appended in time order, then complete=True.
      Step ids never change once sent. The return value is always the complete graph.
    video_meta: what preflight (S8) already knows, to skip a watch-page fetch: {title?, description?,
      length_s|duration_s?, chapters?: [{t|start|startSeconds, title}], firstHandsOn?: seconds}.
    transcript_only: the learner's "Try transcript only" (Build failed card): no video or visual analysis. Only
      Claude runs, over the transcript + title/description/chapters; Gemini is never called, long videos are not
      split into Gemini parts, and nothing is read from or written to the lesson / draft caches (its looser checks
      must never be served to a normal build). A video with no transcript fails; nothing is made up.
    refresh: rebuild everything (new video pass). readapt: reuse the cached video draft, redo only
    the cheap adapt pass (e.g. after the workdir changed or an adapt pass ran out of quota).
    detail: per-step clip pass at 2 fps (costs one request per step; off by default on the free tier).
    material_urls: links to the tutorial's own code found elsewhere, read with the description's links (materials.py);
      also taken from video_meta["materials"]. No caller passes them yet (the finder's rows are not video-specific).

    Cached at demo/cache/lessons/<hash>.json; the cache wins unless refresh/readapt, so the
    demo never waits on a model. The hash covers the video, the goal, the workdir folder name and
    a fingerprint of its file names + printed ::metric:: names (not the absolute path or file
    contents, so the cache survives other laptops and the learner's edits, but a different
    project layout gets checks adapted to it). A graph whose adapt pass failed is returned
    with build.adapted=False and is NOT cached (the video draft is, so a retry is cheap).
    """
    _progress.set(on_progress)  # also clears a callback left by an earlier build in the same task
    _material_urls.set(tuple(material_urls or (video_meta or {}).get("materials") or ()))
    vid = gemini.youtube_id(source_url)
    if not vid:
        raise ValueError(f"only YouTube sources are supported for now: {source_url!r}")
    if transcript_only:
        cache, detail = False, False  # see the docstring: no cache reads or writes, no per-step Gemini clips
        _emit("transcript_only", "no video analysis")
    info = scan(workdir)
    key = cache_key(source_url, goal, workdir, info)
    path = CACHE_DIR / f"{key}.json"
    # Step 1 first (first_step.py) and the captions fetched while the caches are asked: the Claude transcript path only
    fast = first_step.enabled() and "claude" in (["claude"] if transcript_only else engines())
    pre = _start_prefetch(vid) if fast and (transcript_only or refresh or not cache or not _draft_cached(vid, goal)) else None
    first = (first_step.FirstStep(url=source_url, vid=vid, goal=goal, workdir=workdir, info=info, key=key,
                                  on_update=on_update, transcript_only=transcript_only)
             if fast and on_update is not None and (transcript_only or engines() == ["claude"]) else None)
    # the adapt pass's first round starts batch by batch as the step details land (batched.py)
    bat = (batched.BatchedAdapt(goal=goal, info=info, first=first, batch=ADAPT_BATCH, vid=vid)
           if fast and batched.enabled() and (transcript_only or engines() == ["claude"]) else None)
    tokens = (_prefetched.set(pre), _first.set(first), _batched.set(bat))
    try:
        if cache and not (refresh or readapt):
            hit = path if path.is_file() else find_cached(vid, workdir, info)
            if hit:
                graph = json.loads(hit.read_text(encoding="utf-8"))
                graph["lesson"]["workdir"] = workdir
                log.info("lesson cache hit %s%s", hit.name, "" if hit == path else " (same video + workdir, different goal wording)")
                _emit("cache_hit", hit.name)
                _emit("done", hit.name)
                return graph
            shared = await _shared_lesson(vid, source_url, goal, workdir, info, key, path, claim)
            if shared is not None:
                return shared

        if api_key:
            gemini.set_api_key(api_key)
        if anthropic_key:
            claude.set_api_key(anthropic_key)
        t0 = time.time()
        from . import progressive

        meta = normalize_video_meta(video_meta) if video_meta else {}
        if not meta.get("length_s"):
            try:
                meta = {**await asyncio.wait_for(transcript.fetch_metadata(vid), 10), **{k: v for k, v in meta.items() if v}}
            except Exception:  # noqa: BLE001  without metadata we can't plan parts; build in one go
                pass
        if (not transcript_only and (meta.get("length_s") or 0) > progressive.LONG_VIDEO_S and engines()[0] == "gemini"
                and not gemini.is_down() and budget.remaining() > 0):
            try:
                graph = await progressive.build(source_url, vid, goal, workdir, info, meta, key, on_update=on_update, cache=cache, t0=t0)
            except RuntimeError as e:
                raise RuntimeError(human_error(str(e), meta)) from e
            if cache and graph["build"]["adapted"] and not graph["lesson"]["parts"]["failed"]:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
                graph["build"]["fresh"] = True  # build_lesson shares it (never written to the cache file)
            _emit("done", f"{time.time() - t0:.0f}s")
            return graph

        goal_task = asyncio.ensure_future(progressive.goal_match(goal, meta)) if meta.get("title") else None
        if first is not None:
            first.goal_task = goal_task
        try:
            draft = await _video_draft(source_url, vid, goal, refresh=refresh or not cache, detail=detail, write=cache,
                                       transcript_only=transcript_only)
        except RuntimeError as e:
            if goal_task:
                goal_task.cancel()
            # a mid-length video Gemini couldn't finish in one go: build it in parts (shorter clips are what it handles)
            if not transcript_only and (meta.get("length_s") or 0) > PARTS_FALLBACK_MIN_S and "gemini" in engines() and not gemini.is_down() and budget.remaining() > 0:
                log.warning("one-pass build failed (%s); building in parts", str(e)[:150])
                _emit("planning", "retrying in parts")
                try:
                    graph = await progressive.build(source_url, vid, goal, workdir, info, meta, key, on_update=on_update, cache=cache, t0=t0)
                except RuntimeError as e2:
                    raise RuntimeError(human_error(f"{e}\nparts: {e2}", meta)) from e2
                if cache and graph["build"]["adapted"] and not graph["lesson"]["parts"]["failed"]:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
                    graph["build"]["fresh"] = True
                _emit("done", f"{time.time() - t0:.0f}s")
                return graph
            raise RuntimeError(human_error(str(e), meta)) from e
        if first is not None and draft.get("_engine") == "claude" and (transcript_only or engines() == ["claude"]):
            first.start_from_draft(draft)  # a cached video draft: step 1 is built while the rest is adapted (no-op if
            # it is already building from the watched draft)
        known_text, checked = await _known_text(vid), (first.checked if first is not None else {})
        bad_urls = await _bad_urls(draft["steps"], known_text, checked)
        # step 1, when it was built early, is final: its adapt result is reused and it is never re-sent (locked)
        locked = first.lock() if first is not None and first.building() else None
        graph, warnings, adapted_ok, adapt_model = await _adapt(draft, goal, info, bad_urls, locked=locked)
        # the adapt pass may write new links: verify the final text too, and strip what is still dead
        final_bad = await _bad_urls(graph["steps"], known_text, checked)
        warnings = warnings + links.strip_bad_urls(graph["steps"], final_bad)
        warnings = list(draft.get("detail_failures") or []) + warnings
        if not adapted_ok:
            warnings = ["adapt pass failed (quota?): checks come from the video draft, not the learner's workdir; not cached, retry with readapt=True"] + warnings
        n_signals = await add_community_mistakes(graph, source_url)
        graph["lesson"]["id"] = f"lesson-{key[:8]}"
        graph["lesson"]["builtBy"] = draft.get("_engine", "unknown")  # "gemini" = watched the video; "claude" = read the transcript
        graph["lesson"]["workdir"] = workdir
        graph["sources"] = [{"id": "src1", "kind": "video", "title": draft.get("title") or "Tutorial", "url": source_url, "videoId": vid}]
        graph["lesson"]["complete"] = True
        if transcript_only:
            graph["lesson"]["transcriptOnly"] = True
        if goal_task is not None:
            try:
                graph["lesson"]["goalMatch"] = await asyncio.wait_for(goal_task, 10)
            except Exception:  # noqa: BLE001
                pass
        graph["build"] = {
            "adapted": adapted_ok,
            "model": {"video": draft.get("_built_by", "unknown"), "adapt": adapt_model},
            "seconds": round(time.time() - t0, 1),
            "workdir_metrics": sorted(info.metrics),
            "workdir_fp": workdir_fingerprint(workdir, info),
            "community_signals": n_signals,
            "warnings": warnings,
        }
        if draft.get("_timing"):
            graph["build"]["timing"] = draft["_timing"]  # how many step starts were pinned to a chapter / caption line
        if draft.get("_materials"):
            graph["build"]["materials"] = draft["_materials"]  # the tutorial files the steps' code came from
        lock = first.result if first is not None else None
        if lock is not None and lock.get("notebook"):
            graph["lesson"]["notebook"] = lock["notebook"]  # the notebook step 1 already named (and the workspace made)
        use_lesson_venv(graph)  # t9 V6: no second venv / reinstall in a step (Miyagi's setup card fills the lesson's .venv)
        if lock is None or lock.get("notebook"):  # step 1 went out as a non-notebook lesson: the lesson stays one
            use_lesson_notebook(graph)  # t10: a Jupyter lesson's own notebook (mnist.ipynb) in VS Code, never Untitled.ipynb
        if lock is not None:
            _lock_first_step(graph, lock)
        errs = schema_errors(graph)
        if errs:
            raise RuntimeError("step graph failed contract validation:\n" + "\n".join(errs))
        if first is not None:
            await first.delivered()  # the full lesson never reaches the app before its step 1 did
        if not adapted_ok or not cache:
            log.warning("lesson built in %.1fs; not cached (%s)", time.time() - t0, "adapt pass failed" if not adapted_ok else "cache=False")
            _emit("done", f"{time.time() - t0:.0f}s")
            return graph
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
        log.info("lesson built in %.1fs -> %s (%d warnings)", time.time() - t0, path, len(warnings))
        graph["build"]["fresh"] = True
        _emit("done", f"{time.time() - t0:.0f}s")
        return graph

    except Exception:
        if first is not None and first.sending:
            await first.delivered()  # step 1 is with the learner (or on its way): it lands before the error does
        raise
    finally:
        _prefetched.reset(tokens[0])
        _first.reset(tokens[1])
        _batched.reset(tokens[2])
        if bat is not None:
            bat.close()
        _stop_prefetch(pre)
        if first is not None:
            first.close()


class _DetailHooks:
    """claude.DETAIL_HOOKS for both watchers of the per-step detail calls: step 1 first (its steps go first) and the
    batched adapt pass. Neither may break the build: each hook's own errors are its own."""

    def __init__(self, first, bat) -> None:
        self.first, self.bat = first, bat

    def segment(self, seg: dict) -> set[int]:
        if self.bat is not None:
            try:
                self.bat.segment(seg)
            except Exception as e:  # noqa: BLE001
                log.warning("batched adapt hook (segment) failed: %s", e)
        return self.first.segment(seg) if self.first is not None else set()

    def detail(self, i: int, step: dict) -> None:
        if self.first is not None:
            self.first.detail(i, step)  # step 1 first: it may start building now
        if self.bat is not None:
            self.bat.detail(i, step)


def _draft_cached(vid: str, goal: str) -> bool:
    """Is this video's draft for this goal in the raw draft cache (_video_draft reads it instead of watching)?"""
    gh = hashlib.sha256(" ".join(goal.lower().split()).encode()).hexdigest()[:8]
    return (RAW_DIR / f"{vid}-{gh}.json").is_file()


def _start_prefetch(vid: str) -> dict:
    """The captions (and the watch page they come with) and the tutorial's linked code, started at the top of a build
    so they load while the local and shared lesson caches are asked; claude_draft takes them over. Free requests only
    (YouTube, the linked code), never a model call. Cancelled if the build ends without using them (a cache hit)."""
    tasks = {"info": asyncio.ensure_future(transcript.fetch_video_info(vid)),
             "materials": asyncio.ensure_future(_materials(vid, _material_urls.get()))}
    for t in tasks.values():
        t.add_done_callback(first_step._retrieve)  # a failure no one awaited (a cache hit) is not an asyncio warning
    return tasks


def _stop_prefetch(pre: dict | None) -> None:
    for t in (pre or {}).values():
        if not t.done():
            t.cancel()


def _lock_first_step(graph: dict, lock: dict) -> None:
    """The finished graph's step 1 is the one the learner already has (first_step.py), byte for byte. Logs when the full
    build would have made it differently (a lesson-wide decision the early step could not see yet)."""
    sent = copy.deepcopy(lock["step"])
    full = graph["steps"][0]
    same = full == sent
    if not same:
        keys = sorted(k for k in set(sent) | set(full) if sent.get(k) != full.get(k))
        log.warning("first step early: the full build's step 1 differs in %s; keeping the one the learner has", keys)
    # explanations the full build placed in step 1 (step 2's call reads 15 s before its start) go to step 2, never lost
    def key(e: dict) -> tuple:
        return (e.get("t"), e.get("topic"))

    have = {key(e) for e in sent.get("explanations") or []}
    extra = [e for e in full.get("explanations") or [] if key(e) not in have]
    if extra and len(graph["steps"]) > 1:
        nxt = graph["steps"][1]
        own = nxt.get("explanations") or []
        seen = {key(e) for e in own}
        moved = sorted((e for e in extra if key(e) not in seen), key=lambda e: e.get("t", 0))
        # step 2's own (inside its clip) stay first, in time order: its "jump to the explanation" is the first one
        nxt["explanations"] = sorted(own, key=lambda e: e.get("t", 0)) + moved
    graph["steps"][0] = sent
    graph["build"]["firstStep"] = {"seconds": lock.get("seconds"), "same": same, "adaptModel": lock.get("adapt_model")}


async def _shared_lesson(vid: str, source_url: str, goal: str, workdir: str, info: WorkdirInfo, key: str, path: Path,
                         claim: bool) -> dict | None:
    """A local cache miss: the shared lesson cache (miyagi-cloud, lesson/cloud_cache.py). A hit is validated, saved to
    the local library like a built lesson and returned. A miss claims the build (not for a speculative prebuild:
    claim=False) so two installs do not both pay; when another install holds it, wait briefly for their lesson. Any
    failure is None (one log line) and the normal build runs. Never raises."""
    from . import cloud_cache

    if not cloud_cache.enabled():
        return None
    fp = workdir_fingerprint(workdir, info)

    async def fetch() -> dict | None:
        return await cloud_cache.lookup(vid, source_url=source_url, goal=goal, workdir=workdir, key=key, workdir_fp=fp)

    try:
        graph = await fetch()
        if graph is None and claim:
            graph = await cloud_cache.claim_build(vid, fetch)
        if graph is None:
            return None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001  the shared cache is a bonus, never a reason a build fails
        log.info("shared lesson cache: %s; building locally", type(e).__name__)
        return None
    log.info("lesson from the shared cache %s -> %s", vid, path.name)
    _emit("cache_hit", f"shared-{vid}")
    _emit("done", f"shared-{vid}")
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
            g = json.loads(p.read_text(encoding="utf-8"))
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


async def _video_draft(url: str, vid: str, goal: str, *, refresh: bool, detail: bool, write: bool = True,
                       transcript_only: bool = False) -> dict:
    if transcript_only:  # never the cached draft (may be a Gemini one), never written: see _build_lesson_impl
        return await _watch(url, vid, goal, transcript_only=True)
    gh = hashlib.sha256(" ".join(goal.lower().split()).encode()).hexdigest()[:8]
    raw_path = RAW_DIR / f"{vid}-{gh}.json"
    if raw_path.is_file() and not refresh:
        return json.loads(raw_path.read_text(encoding="utf-8"))

    draft = await _watch(url, vid, goal)
    if detail and draft.get("_engine") == "gemini":  # clips need a model that sees the video
        await _add_detail(url, draft)
    if write:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(draft, indent=2), encoding="utf-8")
    return draft


# D1 (founders, Nov 22: "make it all Claude"): the default engine is Claude on the transcript + title, description,
# chapters and the tutorial's own linked code (materials.py), with step starts pinned to chapter marks and caption
# lines (timing.py). Gemini watching the video is opt-in only: LESSON_ENGINE=auto|gemini|claude-first AND a Gemini key.
# The miyagi cloud answers Gemini calls with 403 gemini_disabled; gemini.py marks Gemini off on the first one.
# When Gemini is enabled (auto), it races the Claude draft: it gets up to LESSON_GEMINI_TIMEOUT seconds and the Claude
# draft (running in parallel from t=0) is used if Gemini fails or runs out of time.
GEMINI_VIDEO_TIMEOUT_S = 75.0  # preferred limit while a Claude draft is available
GEMINI_MAX_TIMEOUT_S = 110.0  # LESSON_GEMINI_MAX_TIMEOUT: when Claude has nothing (e.g. no captions), Gemini may keep going
GEMINI_GRACE_S = GEMINI_VIDEO_TIMEOUT_S  # LESSON_GEMINI_GRACE: extra wait for Gemini once Claude's draft is ready
ENGINE_MODES = ("claude", "auto", "claude-first", "gemini")
DEFAULT_ENGINE = "claude"


def engine_mode() -> str:
    """LESSON_ENGINE: claude (default: transcript path only, Gemini never called) | auto (Gemini preferred, Claude
    races it) | claude-first (Claude; Gemini only if the transcript path fails) | gemini. An unknown value is claude."""
    gemini._load_env()
    e = os.environ.get("LESSON_ENGINE", DEFAULT_ENGINE).strip().lower().replace("_", "-")
    return e if e in ENGINE_MODES else DEFAULT_ENGINE


def gemini_enabled() -> bool:
    """May this build call Gemini at all? Only when LESSON_ENGINE names it explicitly, a Gemini key is present and the
    miyagi cloud hasn't said gemini_disabled (then Gemini is off for the process, without another request)."""
    if engine_mode() == "claude" or not gemini.has_key():
        return False
    return not (gemini.is_down() or "").startswith(gemini.OFF_PREFIX)


def engines() -> list[str]:
    """Video-pass engines in order. Rule: Gemini only ever *watches* the video; Claude does
    everything else (transcript drafts, the adapt pass, check writing). Without gemini_enabled() it is Claude only,
    whatever LESSON_ENGINE says."""
    if not gemini_enabled():
        return ["claude"]
    return {"gemini": ["gemini"], "claude-first": ["claude", "gemini"]}.get(engine_mode(), ["gemini", "claude"])


async def _watch(url: str, vid: str, goal: str, *, transcript_only: bool = False) -> dict:
    """Video pass. In auto mode Gemini (watching the video, capped at LESSON_GEMINI_TIMEOUT) races the
    Claude transcript path, which starts at t=0: Gemini's draft wins if it arrives in time (it sees the
    screen); otherwise Claude's is used, usually already finished. Errors from every engine are raised
    together; nothing is made up."""
    order = ["claude"] if transcript_only else engines()
    errors: list[str] = []

    async def claude_draft() -> dict:
        t0 = time.time()
        _emit("reading_transcript")
        pre = _prefetched.get() or {}  # started at the top of the build (_start_prefetch): taken over once
        info_task = pre.pop("info", None)
        mats = pre.pop("materials", None) or asyncio.ensure_future(_materials(vid, _material_urls.get()))  # in parallel with the captions
        try:
            info = await (info_task if info_task is not None else transcript.fetch_video_info(vid))
        except BaseException:
            mats.cancel()
            raise
        files = await mats
        if files:
            info = {**info, "materials": files}  # a copy: the transcript cache never holds them
        _emit("writing_steps", f"{len(info.get('transcript') or [])} transcript lines")
        first = _first.get() if order == ["claude"] else None  # step 1 first: never while Gemini races this draft
        if first is not None:
            first.video_info = info
        bat = _batched.get() if order == ["claude"] else None
        if bat is not None:
            bat.video_info = info
        both = _DetailHooks(first, bat) if (first is not None or bat is not None) else None
        last: Exception | None = None
        for _attempt in range(2):
            hooks = claude.DETAIL_HOOKS.set(both)
            try:
                draft = normalize_draft(await claude.watch_transcript(info, goal))
                break
            except ValueError as e:  # unusable timestamps / no steps: ask again
                last = e
            finally:
                claude.DETAIL_HOOKS.reset(hooks)
        else:
            raise RuntimeError(f"unusable step list ({last})")
        # no frames: pin each step's start to the chapter mark / caption line where it begins (timing.py)
        draft["_timing"] = timing.pin_starts(draft["steps"], info.get("transcript"), info.get("chapters"))
        rehome_explanations(draft["steps"])
        draft["_materials"] = [{"url": f["url"], "path": f["path"]} for f in files]
        log.info("claude video pass: %.1fs (starts pinned: %s; %d tutorial file(s))", time.time() - t0, draft["_timing"], len(files))
        draft["_built_by"] = f"{claude.last_model} (transcript via {info['sources'].get('transcript')})"
        draft["_engine"] = "claude"
        return draft

    pref_cap = float(os.environ.get("LESSON_GEMINI_TIMEOUT", GEMINI_VIDEO_TIMEOUT_S))
    race_t0 = time.time()

    async def gemini_draft() -> dict:
        t0 = time.time()
        # hard limit; the race below takes Claude's draft at pref_cap if one exists
        long_cap = max(pref_cap, float(os.environ.get("LESSON_GEMINI_MAX_TIMEOUT", GEMINI_MAX_TIMEOUT_S)))
        cap = long_cap if "claude" in order else pref_cap
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

    if transcript_only:  # the transcript path alone: no Gemini task is even created
        try:
            d = await claude_draft()
        except Exception as e:  # noqa: BLE001
            e = e if isinstance(e, RuntimeError) else RuntimeError(f"{type(e).__name__}: {e}")
            raise RuntimeError("couldn't build from the transcript alone:\n" + f"claude: {str(e)[:300]}") from e
        _emit("steps_ready", "claude")
        return d

    if order == ["claude", "gemini"]:  # claude-first
        # Michael's rule: pay for Gemini only when the transcript route can't do it
        try:
            d = await claude_draft()
            _emit("steps_ready", "claude")
            return d
        except Exception as e:  # noqa: BLE001  any transcript-path failure: Gemini watches instead
            e = e if isinstance(e, RuntimeError) else RuntimeError(f"{type(e).__name__}: {e}")
            errors.append(f"claude: {str(e)[:300]}")
            log.warning("claude-first: transcript path failed (%s); asking Gemini to watch the video", str(e)[:150])
            _emit("engine_switch", _short_reason(str(e)) if "transcript" not in str(e).lower() else "no_transcript")
        try:
            d = await gemini_draft()
            _emit("steps_ready", "gemini")
            return d
        except Exception as e:  # noqa: BLE001
            errors.append(f"gemini: {(str(e) if isinstance(e, RuntimeError) else f'{type(e).__name__}: {e}')[:300]}")
        raise RuntimeError("no engine could build the lesson:\n" + "\n".join(errors))

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
            # once Claude's draft exists, Gemini gets until the preferred cap (and at most `grace` more)
            timeout = min(grace, max(0.0, race_t0 + pref_cap - time.time())) if claude_ready is not None else None
            done, pending = await asyncio.wait(pending, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if not done:  # Claude is ready and Gemini used up its grace period: don't keep the learner waiting
                errors.append(f"gemini: still watching {grace:.0f}s after the transcript draft was ready")
                _emit("engine_switch", "slow")
                break
            for t in done:
                eng = next(k for k, v in tasks.items() if v is t)
                try:
                    draft = t.result()
                except Exception as e:  # noqa: BLE001  any failure of one engine (a TypeError from an SDK with no key,
                    # an httpx error) must leave the race to the other one, never end a build Gemini was winning
                    e = e if isinstance(e, RuntimeError) else RuntimeError(f"{type(e).__name__}: {e}")
                    errors.append(f"{eng}: {str(e)[:300]}")
                    log.warning("%s video pass failed: %s", eng, str(e)[:200])
                    if eng == "gemini" and "claude" not in tasks and (gemini.is_down() or "").startswith(gemini.OFF_PREFIX):
                        # LESSON_ENGINE=gemini but the miyagi cloud has Gemini off (D1): build from the transcript
                        tasks["claude"] = asyncio.create_task(claude_draft())
                        pending.add(tasks["claude"])
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


PARTS_FALLBACK_MIN_S = 8 * 60


async def _materials(vid: str, extra_urls) -> list[dict]:
    """The tutorial's own linked code for the Claude draft (materials.py); [] on any failure, never raises.
    One deadline (materials.COLLECT_TIMEOUT_S, env LESSON_MATERIALS_TIMEOUT_S) covers the description lookup AND the
    fetches, so the first Claude draft never waits longer than that for them. The description comes from the watch
    page fetch that fetch_video_info shares (transcript.fetch_metadata runs once per video per process)."""
    if os.environ.get("LESSON_MATERIALS", "1") == "0":
        return []

    async def run() -> list[dict]:
        try:
            meta = await transcript.fetch_metadata(vid)
        except Exception:  # noqa: BLE001  no description: only the caller's links
            meta = {}
        return await materials.collect(vid, meta, list(extra_urls or ()))

    try:
        return await asyncio.wait_for(run(), materials.COLLECT_TIMEOUT_S)
    except Exception as e:  # noqa: BLE001  (TimeoutError too): build without them
        log.info("materials for %s: %s", vid, type(e).__name__)
        return []


def normalize_video_meta(vm: dict) -> dict:
    """Preflight's metadata -> the shape transcript.fetch_metadata returns (+ first_hands_on)."""
    chapters = []
    for c in vm.get("chapters") or []:
        t = parse_ts(c.get("t", c.get("start", c.get("startSeconds", c.get("time")))))
        if t is not None:
            chapters.append({"t": t, "title": c.get("title") or ""})
    chapters.sort(key=lambda c: c["t"])
    length = vm.get("length_s") or vm.get("duration_s") or vm.get("lengthSeconds") or vm.get("duration")
    length = parse_ts(length) if isinstance(length, str) else length
    out = {"title": vm.get("title") or "", "description": vm.get("description") or "", "length_s": length,
           "chapters": chapters if len(chapters) >= 3 else []}
    if isinstance(vm.get("style"), str):  # preflight's coding | no-code | conceptual: the placeholder step's wording
        out["style"] = vm["style"]
    fho = vm.get("firstHandsOn", vm.get("first_hands_on"))
    fho = parse_ts(fho) if isinstance(fho, str) else fho
    if isinstance(fho, (int, float)):
        out["first_hands_on"] = float(fho)
    return out


def human_error(err: str, meta: dict | None = None) -> str:
    """A sentence a learner can act on, followed by the technical detail (the app shows the first line).
    A miyagi cloud refusal (miyagi_quota / _auth / _paused / _region) or no connection is the first line on its own, in
    the cloud's words (config.CLOUD_ERRORS) or the offline line. Gemini is named only when the error came from a Gemini
    call: with Gemini off (the default, D1) a quota or a failure is Claude's, never "Gemini's" or "both engines"."""
    if line := claude.user_line(err):
        return f"{line}\n(no engine could build the lesson) {err[:600]}"
    e = err.lower()
    gem = "gemini" in e and "gemini_disabled" not in e and "gemini is off" not in e
    why = []
    if "gemini budget" in e:
        why.append("today's Gemini budget is used up")
    billing = gem and ("402" in e or "payment required" in e or "prepayment" in e or "credits are depleted" in e
                       or "billing" in e)
    if billing:
        why.append("Gemini credits are used up (top up at ai.studio/projects)")
    elif gem and ("quota" in e or "resource_exhausted" in e):
        why.append("Gemini's quota is used up")
    elif "quota" in e or "resource_exhausted" in e or "claude rate-limited" in e:
        why.append("the model is busy right now")
    blocked = "429" in e and ("timedtext" in e or "transcript" in e or "youtube" in e or "caption" in e)
    if blocked:
        why.append("YouTube is blocking transcripts on this network")
    elif "no transcript" in e:
        why.append("the video's captions couldn't be read")
    if "no answer within" in e and not billing:
        why.append("Gemini didn't finish watching in time" if gem else "the build ran out of time")
    if ("api key" in e or "unauthenticated" in e or "permission_denied" in e) and not billing:
        why.append("an API key was rejected")
    length = (meta or {}).get("length_s")
    head = "Couldn't read this video" + (f" ({gemini._mmss(length)} long)" if length else "")
    if billing or blocked:
        tip = " Try a saved lesson, or switch to your phone hotspot."
    elif (length or 0) > 10 * 60:
        tip = " Try a shorter video from the same search."
    else:
        tip = ""
    fallback = "both engines failed" if gem else "the lesson builder hit a problem"
    return f"{head}: {' and '.join(why) or fallback}.{tip}\n(no engine could build the lesson) {err[:600]}"


def _short_reason(err: str) -> str:
    e = err.lower()
    if claude.user_line(err):  # a miyagi cloud refusal or no connection: not a Gemini quota or key problem
        return "cloud"
    if "gemini budget" in e:
        return "budget"
    if "gemini_disabled" in e or "gemini is off" in e:
        return "off"
    if "402" in e or "payment required" in e or "credits" in e or "billing" in e:
        return "billing"
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

    bat = _batched.get() if not feedback else None  # round 1: batches started as their details landed (batched.py)
    if bat is not None:
        batches = bat.layout(steps) or batches

    fresh: list[bool] = []

    async def one(b: list[dict]):
        started = bat.take(batched.key(goal, b, summary)) if bat is not None else None
        if started is not None:  # the very call this batch would make, already running (or done)
            return await started
        fresh.append(True)
        return await claude.adapt_checks(goal, b, summary, fb_for(b))

    results = await asyncio.gather(*(one(b) for b in batches), return_exceptions=True)
    errs = [r for r in results if isinstance(r, BaseException)]
    if len(errs) == len(results):
        raise errs[0] if isinstance(errs[0], RuntimeError) else RuntimeError(str(errs[0]))
    for e in errs:
        log.warning("adapt batch failed: %s", str(e)[:200])
    ok = [r for r in results if isinstance(r, dict)]
    merged = [st for r in ok for st in r.get("steps") or []]
    log.info("claude adapt pass: %.1fs (%d batch(es))", time.time() - t0, len(batches))
    out: dict = {"steps": merged}
    # batched.py's early results: which steps already had a retry (the per-step retry cap), and the models that served
    # them (an early call leaves claude.last_model alone)
    retried = sorted({k for r in ok for k in r.get("_retried") or []})
    if retried:
        out["_retried"] = retried
        out["_improved"] = sorted({k for r in ok for k in r.get("_improved") or []})
    early = [r for r in ok if "_model" in r]
    used = next((r["_retry_model"] for r in early if r.get("_retry_model")), None)
    if used is None:
        used = str(claude.last_model) if fresh or not early else (early[0].get("_model") or str(claude.last_model))
    return out, used


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


def normalize_draft(draft: dict, *, min_step_s: float | None = None, min_steps: int = 3) -> dict:
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
    steps = merge_micro_steps(steps, MIN_STEP_S if min_step_s is None else min_step_s, min_steps)
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


async def _known_text(vid: str) -> str:
    """What the video itself says: description, chapters and (if fetched) the transcript."""
    parts = []
    try:
        meta = await asyncio.wait_for(transcript.fetch_metadata(vid), 10)
        parts += [meta.get("description") or "", " ".join(c.get("title", "") for c in meta.get("chapters") or [])]
    except Exception:  # noqa: BLE001
        pass
    p = transcript._cache_path(vid)
    if p.is_file():
        try:
            parts.append(" ".join(ln.get("text", "") for ln in json.loads(p.read_text(encoding="utf-8")).get("transcript") or []))
        except (OSError, json.JSONDecodeError):
            pass
    return "\n".join(parts)


async def _bad_urls(steps: list[dict], known_text: str, checked: dict) -> set[str]:
    try:
        return await links.find_bad_urls(steps, known_text, checked)
    except Exception as e:  # noqa: BLE001  link checking must never break a build
        log.warning("link check failed: %s", e)
        return set()


async def _adapt(draft: dict, goal: str, info: WorkdirInfo, bad_urls: set[str] | None = None, *, locked=None,
                 partial: bool = False, context: list[dict] | None = None,
                 keep: dict | None = None) -> tuple[dict, list[str], bool, str | None]:
    """-> (graph, leftover warnings, whether any adapt call succeeded, model that served it).

    Round 1 adapts every step. Later rounds re-send only the steps that still have problems (with
    just their feedback), and the loop stops as soon as a round doesn't reduce the problem count,
    keeping the best graph seen; repair cleans up whatever is left.

    Step 1 first (first_step.py): `locked` is an awaitable of step 1's lock (first_step.FirstStep.result: its adapt
    result and the lesson-wide choices it was built with; None when it was not built early). Round 1 adapts the other steps while it is awaited; a locked step is final: never sent again,
    its problems never retried. `partial`: `draft` is step 1 alone (the early build), so lesson-wide lint problems ("no
    metric check" in a lesson whose training step is not built yet) are not its to fix. `context`: the lesson's other
    steps as known so far, for lesson-wide decisions (normalize_checks). `keep` receives the adapt results by step."""
    known_files = set(info.files)
    adapted: dict[int, dict] = {}
    frozen: set[int] = set()
    # retries left for steps batched.py already retried once: the cap is the old loop's (2 retries, a second one only
    # after the first helped), so 1 if its early retry helped, else none
    retries_left: dict[int, int] = {}
    limit = ADAPT_ATTEMPTS
    used: str | None = None
    best: tuple[int, dict] | None = None
    targets = list(draft["steps"])
    feedback: list[str] | None = None
    summary = info.summary_for_prompt()
    app = ...  # decided here (normalize_checks), unless step 1 went out with its own choice

    def build(steps: list[dict]) -> dict:
        return normalize_checks(assemble(draft, goal, {"steps": steps}), info.metrics, context, app=app)

    def done(*result):
        if keep is not None:
            keep.update(adapted)
        return result

    for attempt in range(ADAPT_ATTEMPTS):
        try:
            if attempt == 0 and locked is not None:
                out, used, lock = await _adapt_with_lock(goal, targets, summary, locked)
                if lock:
                    frozen = set(lock["adapted"])
                    adapted.update(lock["adapted"])
                    app = lock.get("app")  # the lesson-wide app / code choice step 1 went out with
            else:
                out, used = await _adapt_call(goal, {"steps": targets}, summary, feedback)
            if attempt == 0:
                helped = set(out.get("_improved") or [])
                retries_left = {k: (1 if k in helped else 0) for k in out.get("_retried") or []}
                if retries_left:  # batched.py's early retries were the first retry round: one more round at most
                    limit = ADAPT_ATTEMPTS - 1
        except RuntimeError as e:
            log.warning("adapt pass failed (attempt %d): %s", attempt + 1, e)
            if not adapted:  # nothing to improve on; the video draft's checks are the fallback
                graph = repair(build([]), info)
                return done(graph, _leftover(graph, info, known_files, partial), False, None)
            break
        for st in out.get("steps") or []:
            if isinstance(st.get("index"), int) and st["index"] not in frozen:
                adapted[st["index"]] = st
        graph = build(list(adapted.values()))
        problems = schema_errors(graph) + lint(graph, info.metrics, known_files) + links.url_problems(graph["steps"], bad_urls or set())
        if partial:
            problems = [p for p in problems if _STEP_PROBLEM.match(p)]
        if frozen:
            problems = [p for p in problems if not ((m := _STEP_PROBLEM.match(p)) and int(m.group(1)) in frozen)]
        if not problems:
            return done(graph, [], True, used)
        if best is not None and len(problems) >= best[0]:
            log.info("adapt attempt %d: %d problems (no better than %d); stopping", attempt + 1, len(problems), best[0])
            break
        best = (len(problems), graph)
        if attempt + 1 >= limit:
            break
        bad = {int(m.group(1)) for p in problems if (m := _STEP_PROBLEM.match(p))}
        graph_level = [p for p in problems if not _STEP_PROBLEM.match(p)]
        targets = [st for st in draft["steps"] if (graph_level or st["index"] in bad) and st["index"] not in frozen]
        targets = [st for st in targets if retries_left.get(st["index"], 1) > 0]
        for st in targets:
            if st["index"] in retries_left:
                retries_left[st["index"]] -= 1
        if not targets:
            break
        feedback = problems
        log.info("adapt attempt %d: %d problems in %d step(s), retrying those", attempt + 1, len(problems), len(targets))
    graph = repair(best[1] if best else build(list(adapted.values())), info)
    return done(graph, _leftover(graph, info, known_files, partial), True, used)


def _leftover(graph: dict, info: WorkdirInfo, known_files: set[str], partial: bool) -> list[str]:
    problems = lint(graph, info.metrics, known_files)
    return [p for p in problems if _STEP_PROBLEM.match(p)] if partial else problems


async def _adapt_with_lock(goal: str, targets: list[dict], summary: str, locked) -> tuple[dict, str | None, dict | None]:
    """Round 1 when step 1 may be locked. -> (adapt output, model, lock or None); raises RuntimeError like _adapt_call
    when nothing could be adapted.
    - The lock is already known (the usual case: step 1 was built while the other details ran): a lock -> the other
      steps are adapted; no lock -> exactly the old round 1 (every step, the old batches).
    - Still building: the other steps are adapted while it is awaited; if it then fails, step 1 is adapted at once,
      alongside whatever is still running.
    A cancelled build stops waiting for step 1 at once (first_step.close() then stops step 1's build too)."""
    lock_task = asyncio.ensure_future(locked)
    await asyncio.sleep(0)  # a lock that is already there resolves now
    if lock_task.done():
        lock = _lock_result(lock_task)
        if lock is None:
            out, used = await _adapt_call(goal, {"steps": targets}, summary, None)
            return out, used, None
        rest = [st for st in targets if st["index"] != 1]
        out, used = await _adapt_call(goal, {"steps": rest}, summary, None) if rest else ({"steps": []}, None)
        return out, used, lock
    rest = [st for st in targets if st["index"] != 1]
    first = [st for st in targets if st["index"] == 1]

    async def adapt(steps: list[dict]):
        try:
            return await _adapt_call(goal, {"steps": steps}, summary, None)
        except RuntimeError as e:
            return e

    rest_task = asyncio.ensure_future(adapt(rest)) if rest else None
    first_task = None
    try:
        await asyncio.wait({lock_task})  # never raises for the lock's own failure; a cancel of this build does
        lock = _lock_result(lock_task)
        if lock is None and first:
            first_task = asyncio.ensure_future(adapt(first))
        res = await rest_task if rest_task is not None else ({"steps": []}, None)
        res1 = await first_task if first_task is not None else None
    except BaseException:
        for t in (lock_task, rest_task, first_task):
            if t is not None and not t.done():
                t.cancel()
        raise
    if lock:
        if isinstance(res, RuntimeError):
            raise res
        return res[0], res[1], lock
    parts = [r for r in (res, res1) if r is not None]
    ok = [r for r in parts if not isinstance(r, RuntimeError)]
    if not ok:
        raise next(r for r in parts if isinstance(r, RuntimeError))
    for r in parts:
        if isinstance(r, RuntimeError):
            log.warning("adapt batch failed: %s", str(r)[:200])  # like a failed batch: those steps keep the draft's checks
    merged = {"steps": [st for r in ok for st in r[0].get("steps") or []]}
    if retried := sorted({k for r in ok for k in r[0].get("_retried") or []}):
        merged["_retried"] = retried
        merged["_improved"] = sorted({k for r in ok for k in r[0].get("_improved") or []})
    return merged, next((r[1] for r in ok if r[1]), None), None


def _lock_result(t) -> dict | None:
    """The value of step 1's lock (a done task, or a plain value); a failed lock is no lock."""
    if isinstance(t, asyncio.Future):
        if t.cancelled() or t.exception() is not None:
            return None
        return t.result() or None
    return t or None


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
        # a file_contains on a Blender scene dump (mug.scene.json) grades the live scene, so it stays a gating check
        checks = a.get("checks") or [c for c in draft_checks if c.get("type") in SCREEN_TYPES or is_scene_check(c)]
        precision = a.get("precision_checks") or []
        if not a:  # adapt pass gave nothing for this step: keep the video draft's file/command checks as backups
            precision = [c for c in draft_checks if c.get("type") in PRECISION_TYPES and c.get("type") not in SCREEN_TYPES
                         and not is_scene_check(c)]
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


_SETUP_VERB = re.compile(r"\b(install(ing)?|download(ing)?|set\s*-?\s*up|setup|get|update|upgrade)\b", re.I)
_TOOLS = {  # tool id -> how it's named
    "python": r"\bpython\s*3?\b|\bpip\b", "vscode": r"\bvs\s*code\b|visual\s+studio\s+code", "node": r"\bnode(\.?js)?\b|\bnpm\b",
    "git": r"\bgit\b(?!hub)", "rust": r"\brust(up)?\b|\bcargo\b", "docker": r"\bdocker\b", "java": r"\bjava\b|\bjdk\b",
    "go": r"\bgolang\b|\bgo\s+(toolchain|compiler)\b",
}
_WRITES_CODE = re.compile(r"\b(def|class|function|const|let|fn|import|from|return)\b|=>|\{", re.I)
_INSTALL_GOAL = re.compile(r"\b(install|set\s*up|setup|configure)\b", re.I)


def tag_setup_steps(graph: dict) -> None:
    """Mark pure install/setup steps (install Python, install VS Code) with setup: true and requires: [tool ids],
    so the engine can auto-pass them when the tools are already there. Not when the goal is about installing."""
    lesson = graph.get("lesson") or {}
    if _INSTALL_GOAL.search(lesson.get("goal") or ""):
        return
    for step in graph.get("steps") or []:
        text = f"{step.get('title', '')} {step.get('instructions', '')}"
        tools = sorted(t for t, rx in _TOOLS.items() if re.search(rx, text, re.I))
        code = step.get("code") or ""
        if tools and _SETUP_VERB.search(step.get("title", "")) and not _WRITES_CODE.search(code):
            step["setup"], step["requires"] = True, tools


def normalize_checks(graph: dict, known_metrics: set[str], context: list[dict] | None = None, *, app=...) -> dict:
    """Deterministic fixes applied before lint (no model call). `context`: the lesson's other steps when `graph` holds
    only some of them (step 1 built early): a lesson where any of them writes code is a code lesson, never an app one.
    `app`: the app-or-code choice already made for this lesson (step 1 went out with it): lesson["app"] or None."""
    tag_setup_steps(graph)
    if app is ...:
        if not (context and app_lesson.has_code({"steps": context})):
            app_lesson.adapt(graph)  # Nov 22: an AutoCAD / Blender lesson talks about the app and checks the app, never files
    elif app:
        app_lesson.adapt(graph, force=True)
    libs = (graph.get("lesson") or {}).get("libraries") or {}
    for step in graph["steps"]:
        # "it runs" checks: a Python Traceback never shows up in a Vite/cargo/git terminal
        stack = stack_of(step) or stack_of({}, libs)  # the step's own command/code, else the lesson's stack
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
            # the checker reads one printed line at a time: keep the line that holds the number (a trend that loses
            # its step that way is then dropped by lint/repair; a threshold keeps working)
            if c.get("metric_pattern") and spans_lines(c["metric_pattern"]) and (line := value_line(c["metric_pattern"])):
                c["metric_pattern"] = line
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
        return safe_search(p, p) is None  # the model's pattern, before validation: never a catastrophic one
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
    c = {"id": cid, "type": t, "label": ""}
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
    c["label"] = plain_label(raw.get("label") or "", c)
    return c


_FILLER = re.compile(r"\b(still|now|already|successfully|correctly|properly|actually|really|been|being)\b\s*", re.I)
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_REGEX_WORDS = {"def", "function", "class", "const", "let", "var", "return", "import", "from", "self", "true", "false", "none"}
_KEYWORDS = {"if", "elif", "else", "for", "while", "not", "and", "with", "async", "await", "raise", "try", "except"}


def _not_a_phrase(s: str, check: dict) -> bool:
    """Unbalanced brackets/quotes or regex syntax: the model echoed its pattern (or half of it) as the label."""
    if not s:
        return False
    if (check.get("pattern") or "").strip() == s:
        return True
    if any(s.count(a) != s.count(b) for a, b in ("()", "[]", "{}")) or s.count('"') % 2 or s.count("`") % 2:
        return True
    return bool(re.search(r"\\|\.\*|\.\+|\(\?|^\^|\$$", s))


def label_is_cut(label: str, check: dict) -> bool:
    """Cut off mid-phrase ("add function is written in the"), or a regex fragment ("read with float(input(")."""
    s = re.sub(r"\s+", " ", (label or "").strip()).rstrip(".:;,")
    return (bool(re.search(r"\s(in|on|to|at|for|of|with|the|a|an|and|or|is|are|was|be)$", s, re.I))
            or s.endswith(("…", "...")) or _not_a_phrase(s, check))


def plain_label(label: str, check: dict) -> str:
    """A complete, plain checklist phrase of <= 6 words. Never cut mid-phrase: tidy the model's label, and
    if it is still too long, write one from the check itself ("add() is in calculator.py")."""
    s = re.sub(r"\s+", " ", (label or "").strip()).rstrip(".:;,")
    s = re.sub(r"^(code|terminal|editor)\s*:\s*", "", s, flags=re.I)  # "Code: main-guard line is typed"
    cut = label_is_cut(s, check)
    s = re.sub(r"^(the|a|an)\s+", "", s, flags=re.I)
    s = _FILLER.sub("", s).strip()
    s = re.sub(r"\b(has|have|is|are)\s+(written|typed|added|defined|present)\b", r"\2", s, flags=re.I)
    if s and not cut and len(s.split()) <= 6 and len(s) >= 4:
        return label_case(s, check)
    # too long, cut off mid-phrase, or empty: write a complete one from the check itself
    t, f, app = check.get("type"), check.get("file") or "", check.get("app")
    pat = check.get("pattern") or ""
    name = next((w for w in _IDENT.findall(pat) if w.lower() not in _REGEX_WORDS | _KEYWORDS and not w.startswith("__")), "")
    words = " ".join(re.sub(r"\\s[+*]?", " ", pat).split())  # `Unknown\s+operator` -> "Unknown operator"
    phrase = words if (re.fullmatch(r"[A-Za-z][A-Za-z0-9 ]{2,30}", words) and len(words.split()) <= 3
                       and words.split()[0].lower() not in _REGEX_WORDS | _KEYWORDS) else ""
    code = _pattern_code(pat)
    made = _made(code) if t in ("file_contains", "screen_contains") and app not in ("Terminal", "iTerm2") else ""
    if made:  # what the learner made, by its own name: "X = np.array() typed", never "array() is typed"
        return f"{made} is in {f}" if t == "file_contains" and f else f"{made} typed"
    call = next((m.group(1) for m in _CALL.finditer(code) if m.group(1).split(".")[-1].lower() not in _REGEX_WORDS | _KEYWORDS), "")
    if t in ("file_contains", "screen_contains") and (call or name) and "(" in pat and app != "Terminal":
        return f"{call or name}() is in {f}" if f else f"{call or name}() is typed"  # the called name: np.random.default_rng()
    if t == "file_contains":
        return f"{phrase or 'Code'} is in {f}" if f else f"{phrase or 'Code'} is in the file"
    if t == "screen_contains":
        if app in ("Terminal", "iTerm2"):
            return f"The terminal shows {phrase}" if phrase else "The terminal shows the output"
        return f"{phrase or name} is typed" if phrase or name else "The code is typed"
    if t == "screen_absent":
        return "No errors in the terminal" if app in ("Terminal", "iTerm2") else "No errors on screen"
    if t == "command_exit_ok":
        return "The program runs"
    if t == "file_exists":
        return f"{f} exists" if f else "The file exists"
    if t in ("metric_threshold", "metric_trend"):
        m = check.get("metric") or "metric"
        return f"{m} {check.get('op', '<')} {check.get('value')}" if t == "metric_threshold" and check.get("value") is not None else f"{m} is improving"
    return "Step check"


_ASSIGN = re.compile(r"^\s*(?:(?:const|let|var)\s+)?([A-Za-z_]\w*)\s*([-+*/@%]?)=(?!=)\s*(?:([A-Za-z_][\w.]*)\s*\()?")
_LOOP = re.compile(r"^\s*for\s*\(?\s*(?:(?:const|let|var)\s+)?([A-Za-z_]\w*)\s+(?:in|of)\b")
_CALL = re.compile(r"([A-Za-z_][\w.]*)\s*\(")
_FALLBACK_LABEL = re.compile(r"^[A-Za-z_][\w.]*\(\) is (typed|in \S+)$")  # what plain_label wrote before it named the thing made


def _pattern_code(pat: str) -> str:
    """A regex read back as the code it matches, roughly (labels only): `X\\s*=\\s*np\\.array\\(` -> "X = np.array("."""
    return re.sub(r"\\(.)", r"\1", re.sub(r"\\[sSdDwWbB][*+?]?|(?<!\\)\.[*+?]|[\^$]", " ", pat or ""))


def _made(code: str) -> str:
    """What a code check's pattern makes, by the learner's own name: "X = np.array()", "W2 update", "epoch loop"."""
    if m := _LOOP.match(code):
        return f"{m.group(1)} loop"
    if m := _ASSIGN.match(code):
        name, op, callee = m.groups()
        if name.lower() in _REGEX_WORDS | _KEYWORDS:
            return ""
        if callee:
            return f"{name} {op}= {callee}()"
        return f"{name} update" if op else f"{name} value"
    return ""


def _code_tokens(check: dict) -> list[str]:
    """Names and literals a check looks for, in order (its pattern read as code, its command, file, metric)."""
    text = " ".join([_pattern_code(check.get("pattern") or ""), check.get("command") or "", check.get("file") or "", check.get("metric") or ""])
    return [t.rstrip(".") for t in re.findall(r"[A-Za-z_][\w.]*|\d[\w.]*", text)]


def _code_names(code: str) -> dict[str, str]:
    """The names in a step's code (strings and comments left out), lowercase -> as spelled: the learner's variables,
    functions and modules (roll, randint, random). Keywords and builtins are words a label may start with (Print, Return)."""
    import builtins
    import keyword

    bare = re.sub(r"(\"\"\"|''')[\s\S]*?\1|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'", " ", code or "")
    bare = re.sub(r"#[^\n]*|//[^\n]*", " ", bare)
    skip = set(keyword.kwlist) | set(dir(builtins)) | _REGEX_WORDS | _KEYWORDS
    out: dict[str, str] = {}
    for n in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", bare):
        if n not in skip and n.lower() not in skip:
            out.setdefault(n.lower(), n)
    return out


def label_case(label: str, check: dict, code: str = "") -> str:
    """Capitalize a label's first word, except code (nn.py, sigmoid_slope, np.array()) and product names, which keep
    their spelling anywhere ("NumPy is imported", never "Numpy is imported"; "nn.py runs", never "Nn.py runs").
    E25: a first word that names something in the code keeps its spelling too: the step's `code` ("random import typed",
    "roll gets random.randint(1, 6)") or an attribute the check looks for ("randint roll typed", never "Randint roll
    typed"). A backticked first word is code as written."""
    from .textlesson import CASED  # textlesson imports this module

    words = (label or "").split(" ")
    for i, w in enumerate(words):
        bare = w.strip(".,:;!?()\"'")
        canon = CASED.get(bare.lower())
        if i == 0 and bare:
            toks = _code_tokens(check)
            assigned = len(words) > 1 and re.fullmatch(r"[-+*/@%]?=", words[1])  # "y = np.array() typed"
            attrs = {p.lower(): p for t in toks for p in t.split(".")[1:] if p}  # random.randint -> randint
            named = _code_names(code).get(bare.lower()) or attrs.get(bare.lower())
            if w.startswith("`"):
                pass  # `roll` gets `random.randint(1, 6)`: code, exactly as written
            elif re.search(r"[._\d]", bare) or "(" in w or (bare in toks and (len(bare) <= 2 or assigned)):
                words[i] = w.replace(bare, next((t for t in toks if t.lower() == bare.lower()), bare))  # "Nn.py" -> "nn.py"
            elif canon:
                words[i] = w.replace(bare, canon)
            elif named:
                words[i] = w.replace(bare, named)  # "Randint roll typed" -> "randint roll typed"
            else:
                words[i] = w[:1].upper() + w[1:]
        elif canon and bare[:1].isupper() and bare != canon:  # a lowercase mid-label "numpy" is the module: kept
            words[i] = w.replace(bare, canon)
    return " ".join(words)


def tidy_labels(step: dict) -> dict:
    """Labels within a step's checklist are unique and cased: two checks both labelled "array() is typed" get the
    identifier that tells them apart ("array() is typed (X)", "array() is typed (y)"). Deterministic, no model call."""
    code = step.get("code") or ""  # E25: a label starting with a name from the step's code keeps its spelling
    for key in ("checks", "precision_checks"):
        checks = step.get(key) or []
        for c in checks:
            if c.get("label"):
                c["label"] = label_case(c["label"], c, code)
        groups: dict[str, list[dict]] = {}
        for c in checks:
            groups.setdefault((c.get("label") or "").strip().lower(), []).append(c)
        for lbl, same in groups.items():
            if not lbl or len(same) < 2:
                continue
            toks = [_code_tokens(c) for c in same]
            said = set(re.findall(r"[\w.]+", lbl))
            for k, c in enumerate(same):
                others = {t for j, ts in enumerate(toks) if j != k for t in ts}
                ident = next((t for t in toks[k] if t not in others and t.lower() not in said), "")
                if ident or k:
                    c["label"] = f"{c['label']} ({ident or k + 1})"
    return step


def repair(graph: dict, info: WorkdirInfo) -> dict:
    """Deterministically remove checks that lint still rejects; never leave a step ungradable."""
    g = copy.deepcopy(graph)
    for step in g["steps"]:
        # file_*/command_* placed in the screen list: move them to the backups instead of dropping them. A file_contains on
        # a Blender scene dump (mug.scene.json) belongs in `checks` (lint allows it there), so it stays.
        misplaced = [c for c in step.get("checks", []) if c.get("type") in PRECISION_TYPES and c.get("type") not in SCREEN_TYPES
                     and not is_scene_check(c)]
        step["checks"] = [c for c in step.get("checks", []) if c not in misplaced]
        step["precision_checks"] = step.get("precision_checks", []) + misplaced
        for key, allowed, tag in (("checks", SCREEN_TYPES, "c"), ("precision_checks", PRECISION_TYPES, "p")):
            kept = [c for c in step.get(key, []) if not check_problems(c, allowed_for(c, key, allowed), key, info.metrics, set(info.files))
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
        tidy_labels(step)
    return g


def fallback_screen_checks(step: dict) -> list[dict]:
    """Last resort: the step's first target, as a literal on-screen match."""
    for t in step.get("targets", []):
        frag = (t.get("match") or "").strip()
        if 3 <= len(frag):
            return [{"id": "", "type": "screen_contains", "label": plain_label(t.get("caption") or frag, {"type": "screen_contains", "app": t.get("app")}),
                     "app": t.get("app") or "Code", "pattern": literal_pattern(frag)[:80]}]
    return []


def _clip_words(s: str, n: int) -> str:
    words = re.sub(r"\s+", " ", s or "").strip().split(" ")
    return " ".join(words[:n])
