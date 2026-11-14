"""Progressive build for long videos (> LONG_VIDEO_S).

One Gemini call can't watch a 2-hour video inside any reasonable cap, so the video is split into
windows (chapters grouped to ~6-15 min, or fixed windows when there are no chapters). Window 1 is
built first and handed to the app via on_update(graph, complete=False); the rest are built in
parallel and appended strictly in time order, so step ids never change once the learner has seen
them. Each window is watched as a clip (start/end offsets, low media resolution, 0.5 fps) with a
cap that scales with its length; if Gemini fails on a window and a transcript is available, Claude
builds that window from the transcript slice instead.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import time

from . import builder, claude, gemini, links, transcript
from .schema import schema_errors

log = logging.getLogger("server.lesson")

LONG_VIDEO_S = float(os.environ.get("LESSON_LONG_VIDEO_S", 30 * 60))
FIRST_MIN_S, FIRST_MAX_S = 3 * 60, 6 * 60  # window 1: small, so the first steps arrive fast (Gemini ~40 s on 6 min)
FIRST_HARD_MAX_S = 8 * 60  # a part 1 still under FIRST_MIN_S may take one more chapter, up to this
WINDOW_MIN_S, WINDOW_TARGET_S, WINDOW_MAX_S = 6 * 60, 12 * 60, 15 * 60
PARALLEL_WINDOWS = int(os.environ.get("LESSON_PARALLEL_WINDOWS", "3"))
PART_MIN_STEP_S = 45.0  # parts are cut by time, so their steps run short; fold sub-45 s steps into a neighbour
MINUTES_PER_STEP = 3.0  # step budget per part (a 12-min part gets at most 4 steps)


def clip_cap_s(start: float, end: float, first: bool = True) -> float:
    """Gemini's time budget for a clip grows with its length. Part 1 is latency-critical (6 min -> ~49 s);
    later parts build in the background while the learner works, and run in parallel (which slows each
    call), so they get a generous budget (14 min -> ~172 s)."""
    minutes = (end - start) / 60.0
    return 25.0 + 4.0 * minutes if first else 60.0 + 8.0 * minutes


def plan_windows(length_s: float, chapters: list[dict], first_hands_on: float | None = None) -> list[tuple[float, float, list[str]]]:
    """[(start, end, chapter titles)] covering the video. Chapters are grouped (never split mid-chapter
    unless one chapter is longer than WINDOW_MAX_S); without chapters, fixed windows. With
    first_hands_on (from preflight), everything before it is one "intro" window and part 1 starts there."""
    if first_hands_on and 60 <= first_hands_on < length_s - 60:
        later = [c for c in chapters if c["t"] > first_hands_on]
        rest = plan_windows(length_s - first_hands_on, [{"t": 0, "title": "hands-on"}] + [dict(c, t=c["t"] - first_hands_on) for c in later]
                            if chapters else [])
        intro_titles = [c["title"] for c in chapters if c["t"] < first_hands_on]
        return [(0.0, float(first_hands_on), ["(intro) " + "; ".join(intro_titles)])] + \
            [(a + first_hands_on, b + first_hands_on, t) for a, b, t in rest]
    spans: list[tuple[float, float, str]] = []
    if len(chapters) >= 3:
        for c, nxt in zip(chapters, chapters[1:] + [{"t": length_s}]):
            a, b = float(c["t"]), float(nxt["t"])
            if b <= a:
                continue
            if b - a > WINDOW_MAX_S:  # a very long chapter: split it
                n = int((b - a) // WINDOW_TARGET_S) + 1
                for k in range(n):
                    spans.append((a + k * (b - a) / n, a + (k + 1) * (b - a) / n, f"{c['title']} ({k + 1}/{n})"))
            else:
                spans.append((a, b, c["title"]))
    else:
        t, first = 0.0, True
        while t < length_s:
            w = 8 * 60 if first else WINDOW_TARGET_S
            spans.append((t, min(length_s, t + w), ""))
            t, first = t + w, False

    windows: list[tuple[float, float, list[str]]] = []
    cur: list[tuple[float, float, str]] = []
    for sp in spans:
        lo, hi = (FIRST_MIN_S, FIRST_MAX_S) if not windows else (WINDOW_MIN_S, WINDOW_MAX_S)
        cur_len, with_next = (cur[-1][1] - cur[0][0]) if cur else 0.0, sp[1] - (cur[0][0] if cur else sp[0])
        too_short_first = not windows and cur_len < lo and with_next <= FIRST_HARD_MAX_S  # don't ship a 1-step part 1
        if cur and with_next > hi and cur_len >= min(lo, 60) and not too_short_first:
            windows.append((cur[0][0], cur[-1][1], [c[2] for c in cur if c[2]]))
            cur = []
        cur.append(sp)
        lo, hi = (FIRST_MIN_S, FIRST_MAX_S) if not windows else (WINDOW_MIN_S, WINDOW_MAX_S)
        if cur[-1][1] - cur[0][0] >= (lo if not windows else WINDOW_TARGET_S):
            windows.append((cur[0][0], cur[-1][1], [c[2] for c in cur if c[2]]))
            cur = []
    if cur:
        if windows and cur[-1][1] - cur[0][0] < WINDOW_MIN_S / 2:  # a tiny tail joins the previous window
            a, _b, titles = windows.pop()
            windows.append((a, cur[-1][1], titles + [c[2] for c in cur if c[2]]))
        else:
            windows.append((cur[0][0], cur[-1][1], [c[2] for c in cur if c[2]]))
    return windows


def _absolutize(raw: dict, start: float, end: float) -> dict:
    """Clip answers sometimes use clip-relative times: shift them if they fall before the clip."""
    steps = raw.get("steps") or []
    starts = [t for s in steps if (t := builder.parse_ts(s.get("start"))) is not None]
    if start > 30 and starts and max(starts) < start - 5:
        for s in steps:
            for k in ("start", "end"):
                t = builder.parse_ts(s.get(k))
                if t is not None:
                    s[k] = t + start
            for e in s.get("explanations") or []:
                t = builder.parse_ts(e.get("t"))
                if t is not None:
                    e["t"] = t + start
    for s in steps:  # clamp into the window
        a, b = builder.parse_ts(s.get("start")), builder.parse_ts(s.get("end"))
        if a is not None:
            s["start"] = min(max(a, start), end - 1)
        if b is not None:
            s["end"] = min(max(b, start + 1), end)
    return raw


async def _window_draft(url: str, vid: str, goal: str, win: tuple, meta: dict, context: str, engines: list[str], first: bool = True) -> dict:
    start, end, titles = win
    errors = []
    if "gemini" in engines:
        cap = clip_cap_s(start, end, first)
        try:
            raw = await asyncio.wait_for(
                gemini.watch_video(url, goal, context=context, start=start, end=end, media_low=True), cap)
            if not (raw.get("steps") or []):  # a talk-only part (intro, outro, theory): nothing to code along with
                return {"steps": [], "_empty": True, "_engine": "gemini", "_built_by": f"{gemini.last_model} (watched the video)"}
            d = builder.normalize_draft(_absolutize(raw, start, end), min_step_s=PART_MIN_STEP_S, min_steps=1)
            d["_engine"], d["_built_by"] = "gemini", f"{gemini.last_model} (watched the video)"
            return d
        except TimeoutError:
            errors.append(f"gemini: no answer within {cap:.0f}s")
        except (RuntimeError, ValueError) as e:
            errors.append(f"gemini: {str(e)[:200]}")
    if "claude" in engines:
        try:
            info = await transcript.fetch_video_info(vid)
            part = dict(info, transcript=[ln for ln in info["transcript"] if start - 5 <= ln["t"] <= end + 5],
                        chapters=[c for c in info.get("chapters") or [] if start <= c["t"] < end])
            d = builder.normalize_draft(_absolutize(await claude.watch_transcript(part, goal), start, end), min_step_s=PART_MIN_STEP_S, min_steps=1)
            d["_engine"], d["_built_by"] = "claude", f"{claude.last_model} (transcript via {info['sources'].get('transcript')})"
            return d
        except (RuntimeError, ValueError) as e:
            errors.append(f"claude: {str(e)[:200]}")
    raise RuntimeError(" | ".join(errors) or "no engine enabled")


def _renumber(steps: list[dict], first_index: int) -> list[dict]:
    out = []
    for k, s in enumerate(steps):
        s = copy.deepcopy(s)
        i = first_index + k
        s["index"], s["id"] = i, f"s{i}"
        for key, tag in (("checks", "c"), ("precision_checks", "p")):
            for j, c in enumerate(s.get(key) or [], 1):
                c["id"] = f"s{i}{tag}{j}"
        out.append(s)
    return out


async def build(source_url: str, vid: str, goal: str, workdir: str, info, meta: dict, key: str, *,
                on_update=None, cache: bool = True, t0: float | None = None) -> dict:
    t0 = t0 or time.time()
    engines = builder.engines()
    fho = meta.get("first_hands_on")
    windows = plan_windows(float(meta["length_s"]), meta.get("chapters") or [], fho)
    intro = 1 if (windows and windows[0][2] and windows[0][2][0].startswith("(intro)")) else 0
    context = transcript.format_metadata(meta)
    known_text, checked = await builder._known_text(vid), {}
    goal_task = asyncio.ensure_future(goal_match(goal, meta))
    log.info("long video (%s): %d windows %s", gemini._mmss(meta["length_s"]), len(windows),
             [f"{gemini._mmss(a)}-{gemini._mmss(b)}" for a, b, _ in windows])
    builder._emit("planning", f"{len(windows)} parts")

    async def draft_for(i: int) -> dict:
        """A part's draft; a background part that fails is retried once as two half-length clips
        (long dense clips are where Gemini stalls)."""
        try:
            return await _window_draft(source_url, vid, goal, windows[i], meta, context, engines, first=(i == intro))
        except RuntimeError as e:
            a, b, titles = windows[i]
            if i == intro or b - a < 6 * 60:
                raise
            log.warning("part %d failed (%s); retrying as two halves", i + 1, str(e)[:100])
            mid = a + (b - a) / 2
            halves = await asyncio.gather(
                *(_window_draft(source_url, vid, goal, w, meta, context, engines, first=False) for w in ((a, mid, titles), (mid, b, titles))),
                return_exceptions=True)
            ok = [h for h in halves if isinstance(h, dict)]
            if not ok:
                raise RuntimeError(f"{e} | halves: " + " | ".join(str(h)[:120] for h in halves)) from e
            merged = {**ok[0], "steps": [st for h in ok for st in h.get("steps") or []]}
            if not merged["steps"]:
                return {**ok[0], "steps": [], "_empty": True}
            return builder.normalize_draft(merged, min_step_s=PART_MIN_STEP_S, min_steps=1) | {"_engine": ok[0].get("_engine"), "_built_by": ok[0].get("_built_by")}

    async def one(i: int) -> tuple[list[dict], dict]:
        d = await draft_for(i)
        if d.get("_empty"):
            return [], {"draft": d, "graph": {"lesson": {}}, "warnings": [], "adapted": True, "adapt_model": None, "empty": True}
        bad = await builder._bad_urls(d["steps"], known_text, checked)
        g, warns, ok, adapt_model = await builder._adapt(d, goal, info, bad)
        warns += links.strip_bad_urls(g["steps"], await builder._bad_urls(g["steps"], known_text, checked))
        return g["steps"], {"draft": d, "graph": g, "warnings": warns, "adapted": ok, "adapt_model": adapt_model}

    steps: list[dict] = []
    parts: list[dict] = [{"start": a, "end": b, "chapters": t, "status": "pending"} for a, b, t in windows]
    meta_out: dict = {"warnings": [], "adapted": True, "engines": set(), "adapt_model": None, "libraries": {}, "title": meta.get("title")}

    def graph_now(complete: bool) -> dict:
        g = {
            "lesson": {"id": f"lesson-{key[:8]}", "title": meta.get("title") or goal, "goal": goal, "workdir": workdir,
                       "libraries": meta_out["libraries"], "complete": complete,
                       "builtBy": "gemini" if meta_out["engines"] == {"gemini"} else "claude" if meta_out["engines"] == {"claude"}
                       else "mixed" if meta_out["engines"] else "unknown",
                       "parts": {"done": sum(p["status"] == "done" for p in parts), "failed": sum(p["status"] == "failed" for p in parts),
                                 "skipped": sum(p["status"] == "skipped" for p in parts),
                                 "total": len(parts), "list": [{k: p[k] for k in ("start", "end", "chapters", "status")} for p in parts]}},
            "sources": [{"id": "src1", "kind": "video", "title": meta.get("title") or "Tutorial", "url": source_url, "videoId": vid}],
            "steps": copy.deepcopy(steps),
            "build": {"adapted": meta_out["adapted"], "progressive": True,
                      "model": {"video": ", ".join(sorted(meta_out["engines"])) or "unknown", "adapt": meta_out["adapt_model"]},
                      "seconds": round(time.time() - t0, 1), "workdir_metrics": sorted(info.metrics),
                      "workdir_fp": builder.workdir_fingerprint(workdir, info), "warnings": list(meta_out["warnings"])},
        }
        if goal_task.done() and not goal_task.cancelled() and goal_task.exception() is None:
            g["lesson"]["goalMatch"] = goal_task.result()
        return g

    def absorb(i: int, res: tuple[list[dict], dict] | BaseException) -> bool:
        if isinstance(res, BaseException):
            parts[i]["status"] = "failed"
            parts[i]["error"] = str(res)[:300]
            meta_out["warnings"].append(f"part {i + 1} ({gemini._mmss(windows[i][0])}-{gemini._mmss(windows[i][1])}) failed: {str(res)[:160]}")
            return False
        new_steps, extra = res
        steps.extend(_renumber(new_steps, len(steps) + 1))
        parts[i]["status"] = "skipped" if extra.get("empty") else "done"
        if extra.get("empty"):
            return False  # nothing new to show
        meta_out["warnings"] += [f"part {i + 1}: {w}" for w in extra["warnings"]]
        meta_out["adapted"] &= extra["adapted"]
        meta_out["engines"].add(extra["draft"].get("_engine", "unknown"))
        meta_out["adapt_model"] = extra["adapt_model"] or meta_out["adapt_model"]
        meta_out["libraries"].update({k: v for k, v in extra["graph"]["lesson"].get("libraries", {}).items() if k not in meta_out["libraries"]})
        return True

    async def emit(complete: bool) -> None:
        if on_update is None:
            return
        try:
            r = on_update(graph_now(complete), complete)
            if asyncio.iscoroutine(r):
                await r
        except Exception as e:  # noqa: BLE001  a UI callback must never break a build
            log.warning("on_update failed: %s", e)

    # All parts start now (part 1 outside the limit, so it never waits); results are absorbed strictly
    # in time order, so the first part that builds is the first thing the learner sees and later steps
    # are only ever appended.
    sem = asyncio.Semaphore(PARALLEL_WINDOWS)

    async def guarded(i: int):
        if i == intro:  # the first hands-on part never waits for a slot
            return await one(i)
        async with sem:
            return await one(i)

    async def skipped_intro():
        return [], {"draft": {}, "graph": {"lesson": {}}, "warnings": [], "adapted": True, "adapt_model": None, "empty": True}

    # an intro before preflight's firstHandsOn is talk: record it as skipped instead of watching it
    tasks = [asyncio.ensure_future(skipped_intro() if (intro and i == 0) else guarded(i)) for i in range(len(windows))]
    shown_first = False
    try:
        for i, task in enumerate(tasks):
            try:
                res = await task
            except RuntimeError as e:
                res = e
            if not absorb(i, res):
                continue
            if not shown_first:
                shown_first = True
                log.info("first part ready in %.1fs (%d steps)", time.time() - t0, len(steps))
                builder._emit("first_steps", f"{len(steps)} steps")
            else:
                builder._emit("more_steps", f"part {i + 1}/{len(windows)}")
            await emit(complete=False)
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
    if not steps:
        goal_task.cancel()
        raise RuntimeError("; ".join(p.get("error", "") for p in parts if p.get("error")) or "no part of the video could be read")

    try:
        await asyncio.wait_for(asyncio.shield(goal_task), 5)
    except Exception:  # noqa: BLE001
        pass
    g = graph_now(complete=True)
    errs = schema_errors(g)
    if errs:
        raise RuntimeError("step graph failed contract validation:\n" + "\n".join(errs))
    await emit(complete=True)
    return g


GOAL_SCHEMA = {"type": "object", "properties": {"score": {"type": "number"}, "note": {"type": "string"}}, "required": ["score", "note"]}


async def goal_match(goal: str, meta: dict) -> dict:
    """How well this video fits what the learner asked for (0..1), from its title/description/chapters."""
    if not (goal or "").strip():
        return {"score": None, "note": "no goal given"}
    prompt = (f"A learner asked to: {goal!r}.\nThis is the video they would follow:\n{transcript.format_metadata(meta)}\n\n"
              "Score 0..1 how well following this video achieves what they asked (1 = exactly, 0.5 = related but a "
              "different project/tool, 0 = unrelated). note: one short sentence a learner would understand.")
    try:
        r = await asyncio.wait_for(claude._generate_json("You judge whether a tutorial fits a learner's goal.", prompt, GOAL_SCHEMA, effort="low"), 30)
        return {"score": max(0.0, min(1.0, float(r.get("score", 0)))), "note": str(r.get("note", ""))[:200]}
    except Exception as e:  # noqa: BLE001
        return {"score": None, "note": f"not scored ({str(e)[:80]})"}
