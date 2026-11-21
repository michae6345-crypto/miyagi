"""Preflight: a <= 5 s look at the picked video BEFORE the lesson build starts.

    res = await preflight(url, goal)          # metadata + Claude's read + an early tool check
    card = preflight_card(res)                # card {kind: "preflight"}; buttons build / pick_another (+ install)

Stages (one shared deadline, default 5 s; a stage that misses it is listed in `missing`, keeps running for
up to LATE_S more seconds and, if it lands, the filled-in result goes to on_late so the card can be re-sent):
  1. metadata  (~1 s)  oEmbed + watch page (plain fetch); chapters
  2. in parallel:
     - Claude   (~2 s)  claude-haiku-5-5, structured output: style, topic, goalMatch, first hands-on chapter
     - tools    (~2-3 s) server.workspace.requirements() on a metadata-level graph (S2), checked locally
  3. buildPlan (deterministic): whole video, or chapter by chapter for long videos (E2's progressive build)

Rules kept: no fake data (a stage that fails is reported missing, never invented), works for any topic,
Claude reads text (Gemini only watches YouTube; preflight never calls Gemini, it reuses the finder's skim).
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

from server.finder import youtube
from server.finder.env import CACHE_DIR, Keys, resolve_keys

from . import meta as meta_mod

log = logging.getLogger("server.preflight")

DEFAULT_MODEL = "claude-haiku-5-5"
TIMEOUT_S = 5.0
# Build plan: mirrors E2's progressive build (server/lesson/progressive.py, uses it when importable):
# videos longer than 30 min are built window by window; window 1 = chapters from 0:00 grouped to 3-6 min.
LONG_VIDEO_S = float(os.environ.get("LESSON_LONG_VIDEO_S", str(30 * 60)))
FIRST_MIN_S, FIRST_MAX_S = 3 * 60, 6 * 60
FIRST_HARD_MAX_S = 8 * 60  # a part 1 still under 3 min may take one more chapter, up to this (E2 d701162)
WINDOW_TARGET_S, WINDOW_MAX_S = 12 * 60, 15 * 60  # E2 splits a chapter longer than 15 min into ~12 min spans
FIRST_WINDOW_NO_CHAPTERS_S = 8 * 60
HANDS_ON_MIN_S = 60  # E2 skips an intro only from 1 min on
HANDS_ON_MAX_S = 10 * 60  # a "first hands-on chapter" later than this would skip real work: not passed on
LOW_MATCH = 0.5
STYLES = ["coding", "no-code", "conceptual"]  # same vocabulary as the finder rows' `style` (E7)

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "style": {"type": "string", "enum": STYLES},
        "styleWhy": {"type": "string"},
        "topic": {"type": "string"},
        "goalMatch": {
            "type": "object",
            "properties": {"score": {"type": "number"}, "note": {"type": "string"}},
            "required": ["score", "note"],
            "additionalProperties": False,
        },
        "firstHandsOnChapter": {"type": "integer"},
        "libraries": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["style", "styleWhy", "topic", "goalMatch", "firstHandsOnChapter", "libraries"],
    "additionalProperties": False,
}

SYSTEM = """You check a YouTube tutorial for a learner BEFORE we turn it into a hands-on lesson.
You only see its metadata (title, channel, length, description, chapters, tags) and maybe a short note
from someone who skimmed the video, and the search's own style guess. Judge from that; do not invent
content it doesn't support.

style:
- coding: the presenter writes and runs code (any language, notebooks included).
- no-code: hands-on without code: GUI / no-code platforms and web apps (Zapier, Botpress, Bubble, ChatGPT's
  UI, Excel, Notion), drag-and-drop, prompting a product, or creative/desktop tools (Blender, Figma, a DAW).
- conceptual: a lecture or explainer; nothing for the learner to build along.
styleWhy: <= 12 words.
topic: one line, <= 14 words, what the video actually teaches and with what (e.g. "Builds a GPT language
model from scratch in PyTorch").
goalMatch.score 0-1: if the learner follows this video, how much of THEIR goal do they achieve? Same
words are not a match: the platform, depth and outcome must fit. 0.9+ = exactly the goal, 0.5 = related
but a different route/outcome, <= 0.3 = a different thing (e.g. goal "build chat gpt" vs a video that
configures support bots in Zapier/Botpress: ~0.2).
goalMatch.note: <= 16 words, to the learner, concrete. When the score is low, say what the video builds instead,
e.g. "This video builds no-code support bots, not an LLM."
firstHandsOnChapter: index of the FIRST chapter where the learner starts doing something (setting up,
loading data, writing the first code or first click). Skip only a pure intro / sponsor / preview; usually
0 or 1. Never skip hands-on chapters to reach the "main" part. -1 if there are no chapters.
libraries: languages, libraries, platforms and apps the video uses (<= 8, short names)."""


def _fmt(secs: int | None) -> str:
    return youtube.fmt_duration(secs) or "?"


def _ts(secs: float | None) -> str:
    return youtube.fmt_duration(int(secs)) if secs else "0:00"


def _prompt(goal: str, m: dict, skim: dict | None, prior: dict | None = None) -> str:
    chs = m.get("chapters") or []
    lines = [
        f"Learner's goal: {goal or '(none given)'}",
        f"Title: {m.get('title') or '?'}",
        f"Channel: {m.get('channel') or '?'}",
        f"Length: {_fmt(m.get('duration_s'))}",
    ]
    if m.get("category"):
        lines.append(f"Category: {m['category']}")
    if m.get("keywords"):
        lines.append("Tags: " + ", ".join(m["keywords"][:15]))
    if chs:
        lines.append("Chapters:\n" + "\n".join(f"{c['index']}. [{_ts(c['start'])}] {c['title']}" for c in chs[:60]))
    else:
        lines.append("Chapters: none")
    if prior and prior.get("style"):
        lines.append(f"Search's style guess (from the results page): {prior['style']}")
    if skim:
        lines.append(f"Skim note (Gemini watched it at low fps for the search; score {skim.get('score')}/100): {skim.get('reason', '')}")
    lines.append("Description:\n<description>\n" + (m.get("description") or "(empty)")[:4000] + "\n</description>")
    return "\n".join(lines)


async def classify(key: str, goal: str, m: dict, skim: dict | None, *, timeout: float, client=None,
                   prior: dict | None = None) -> dict:
    """Claude's read of the metadata. Raises on failure (the caller marks it missing)."""
    if client is None:
        from server.finder import claude as finder_claude

        client = finder_claude.client(key)
    resp = await client.messages.create(
        model=os.environ.get("PREFLIGHT_MODEL", DEFAULT_MODEL),
        max_tokens=1200,
        system=SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA}},
        messages=[{"role": "user", "content": _prompt(goal, m, skim, prior)}],
        timeout=timeout,
    )
    if getattr(resp, "stop_reason", None) == "refusal":
        raise RuntimeError("Claude declined")
    text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "{}")
    out = json.loads(text)
    style = out.get("style") if out.get("style") in STYLES else None
    gm = out.get("goalMatch") or {}
    try:
        score = max(0.0, min(1.0, float(gm.get("score", 0))))
    except (TypeError, ValueError):
        score = 0.0
    return {
        "style": style,
        "styleWhy": str(out.get("styleWhy") or "")[:120],
        "topic": str(out.get("topic") or "")[:160],
        # E2/S2 shape: score null when there is no goal to compare against
        "goalMatch": {"score": round(score, 2), "note": str(gm.get("note") or "")[:160]} if (goal or "").strip()
        else {"score": None, "note": ""},
        "firstHandsOnChapter": int(out.get("firstHandsOnChapter", 0) or 0),
        "libraries": [str(x)[:40] for x in (out.get("libraries") or [])][:8],
    }


# --------------------------------------------------------------------------- Claude's read, kept on disk
# The same (video, goal) always gets the same read, so it is kept like the finder's search cache: a demo re-run (or any
# pick after an engine restart, when the 10 min memo is gone) shows its card without a Claude call or its ~2-3 s wait.
CLASSIFY_TTL_S = float(os.environ.get("PREFLIGHT_CACHE_TTL", 7 * 24 * 3600))
_CLASSIFY_KEYS = ("style", "styleWhy", "topic", "goalMatch", "firstHandsOnChapter", "libraries")


def classify_cache_dir() -> Path | None:
    """PREFLIGHT_CACHE_DIR > demo/cache/preflight (beside the finder's demo/cache/search); PREFLIGHT_CACHE=0: off."""
    if os.environ.get("PREFLIGHT_CACHE", "1") == "0":
        return None
    return Path(os.environ.get("PREFLIGHT_CACHE_DIR") or (CACHE_DIR.parent / "preflight")).expanduser()


def _norm_goal(goal: str) -> str:
    return " ".join((goal or "").lower().split())


def _classify_path(root: Path, vid: str, goal: str) -> Path:
    return root / f"{vid}-{hashlib.sha1(_norm_goal(goal).encode()).hexdigest()[:8]}.json"


def classify_cached(root: Path | None, vid: str | None, goal: str) -> dict | None:
    """Claude's saved read of this video for this goal (classify()'s dict), or None (none / stale / unreadable)."""
    if root is None or not vid:
        return None
    try:
        data = json.loads(_classify_path(root, vid, goal).read_text())
    except (OSError, ValueError):
        return None
    c = data.get("classify") if isinstance(data, dict) else None
    if (data.get("videoId") != vid or data.get("goal") != _norm_goal(goal) or not isinstance(c, dict)
            or any(k not in c for k in _CLASSIFY_KEYS) or time.time() - float(data.get("created") or 0) > CLASSIFY_TTL_S):
        return None
    return c


def classify_save(root: Path | None, vid: str | None, goal: str, c: dict) -> None:
    if root is None or not vid or not isinstance(c, dict):
        return
    try:
        p = _classify_path(root, vid, goal)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"videoId": vid, "goal": _norm_goal(goal), "created": int(time.time()),
                                   "classify": {k: c.get(k) for k in _CLASSIFY_KEYS}}, indent=1))
        tmp.replace(p)
    except OSError as e:  # a read-only checkout: no cache, same card
        log.debug("preflight: couldn't keep Claude's read (%s)", e)


async def _classify_kept(root: Path | None, vid: str | None, goal: str, coro) -> dict:
    c = await coro
    classify_save(root, vid, goal, c)
    return c


async def _known(c: dict) -> dict:
    return dict(c)


# --------------------------------------------------------------------------- finder skim (cached, no new Gemini call)

def cached_skim(video_id: str | None, row: dict | None = None, *, cache_dir: Path | None = None) -> dict | None:
    """The finder's Gemini skim for this video: from the picked search row, else from demo/cache/search."""
    def from_row(r: dict, query: str = "") -> dict | None:
        if r.get("videoId") != video_id and youtube.video_id(r.get("url", "")) != video_id:
            return None
        if "gemini-watch" not in str(r.get("scoredBy") or r.get("scored_by") or "") and not r.get("skim"):
            return None
        sk = r.get("skim") or {}
        return {"score": sk.get("score", r.get("score")), "reason": sk.get("reason") or r.get("reason") or "", "query": query}

    if not video_id:
        return None
    if row and (hit := from_row(row)):
        return hit
    root = cache_dir or CACHE_DIR
    try:
        files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:50]
    except OSError:
        return None
    for p in files:
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        for r in data.get("results") or []:
            if isinstance(r, dict) and (hit := from_row(r, data.get("query", ""))):
                return hit
    return None


# --------------------------------------------------------------------------- finder row (E7)

def finder_prior(row: dict | None, video_id: str | None) -> dict:
    """What the finder already read for this video (E7's row fields): style coding|no-code|conceptual,
    durationS, durationLabel, long, chapters (a count), captions. {} if no row / another video."""
    if not row or (video_id and row.get("videoId") not in (None, video_id) and youtube.video_id(row.get("url", "")) != video_id):
        return {}
    out = {k: row[k] for k in ("durationS", "durationLabel", "long", "captions", "title", "channel") if row.get(k) not in (None, "")}
    if row.get("style") in STYLES:
        out["style"] = row["style"]
    if isinstance(row.get("chapters"), int):
        out["chapterCount"] = row["chapters"]
    return out


# --------------------------------------------------------------------------- lesson cache (E2)

def _build_workdir(url: str, goal: str) -> str | None:
    """The folder the engine will build into: E4's choice (TUT_WORKDIR, else S2's: the hero video ->
    demo/pinn-lab), else S2's directly."""
    try:
        from server.orchestrator.workspace import build_workdir  # E4

        return str(build_workdir(url, goal))
    except Exception as e:  # noqa: BLE001
        log.debug("preflight: E4's build_workdir unavailable (%s)", type(e).__name__)
    try:
        from server.workspace import build_workdir  # S2

        return str(build_workdir(url))
    except Exception:  # noqa: BLE001
        return None


def cached_lesson(url: str, goal: str) -> dict | None:
    """The lesson E2's build_lesson would return from its cache for (url, goal) right now, with the same
    lookup it uses (exact cache_key, else find_cached: same video + same workdir layout). Blocking
    (reads files): call in a thread. {graph, file, steps, workdir} or None."""
    vid = youtube.video_id(url)
    workdir = _build_workdir(url, goal) if vid else None
    if not workdir:
        return None
    try:
        from server.lesson import builder
        from server.lesson.workdir import scan
    except Exception:  # noqa: BLE001 - lesson module not here
        return None
    info = scan(workdir)
    path = builder.CACHE_DIR / f"{builder.cache_key(url, goal, workdir, info)}.json"
    hit = path if path.is_file() else builder.find_cached(vid, workdir, info)
    if not hit:
        return None
    graph = json.loads(Path(hit).read_text())
    folder = _lesson_folder(graph)
    graph.setdefault("lesson", {})["workdir"] = workdir
    return {"graph": graph, "file": Path(hit).name, "steps": len(graph.get("steps") or []), "workdir": workdir,
            "folder": folder if folder and Path(folder).is_dir() else None}


def _lesson_folder(graph: dict) -> str | None:
    """The folder the build of `graph` works in (E4's lesson_folder, else S2's): the one whose .venv the setup card
    checks after Build. Read-only. Desktop test 10: preflight checked the build's placeholder folder (`_new`), so the
    system Python, and said "tensorflow ✕ · 4 to install" while the lesson's .venv had all four (no setup card came)."""
    try:
        from server.orchestrator.workspace import lesson_folder  # E4: TUT_WORKDIR / demo / S2

        return lesson_folder(graph)
    except Exception as e:  # noqa: BLE001
        log.debug("preflight: E4's lesson_folder unavailable (%s)", type(e).__name__)
    try:
        from server.workspace import lesson_folder  # S2

        return str(lesson_folder(graph))
    except Exception:  # noqa: BLE001
        return None


def _hit_folder(hit: dict | None) -> str | None:
    """The folder the setup check reads for a cached lesson (a lesson_cache without "folder": its workdir)."""
    return (hit.get("folder", hit.get("workdir")) or None) if hit else None


def _venv_mark(folder: str | None) -> str | None:
    """The lesson .venv the setup check reads, as "<python>@<site-packages mtime>"; None when there's no .venv yet. A
    memoised preflight with another mark checked packages that changed since (a build made the .venv, Install added
    to it), so it is checked again."""
    if not folder:
        return None
    venv = Path(folder) / ".venv"
    try:
        if not (venv / "bin" / "python").exists():
            return None
        mtimes = [p.stat().st_mtime for p in (venv / "lib").glob("python*/site-packages")]
    except OSError:
        return None
    return f"{venv / 'bin' / 'python'}@{max(mtimes, default=0.0):.3f}"


def _call_req(req: Callable, graph: dict, workdir: str | None):
    try:
        if workdir and "workdir" in inspect.signature(req).parameters:
            return req(graph, workdir=workdir)
    except (TypeError, ValueError):
        pass
    return req(graph)


# --------------------------------------------------------------------------- tools (S2's requirements)

LOCAL_NOTE = ("How Miyagi runs this lesson: if the learner writes code, they do it LOCALLY in VS Code, in a "
              "project folder on their Mac, with a local Python/Node/... (never in Colab, Kaggle, Replit or "
              "another online notebook, even if the video uses one), so list the local editor, runtime and "
              "packages. If the video is done in web apps or GUI tools without code, list those instead.")


def light_graph(m: dict, goal: str, libraries: list[str] | None = None) -> dict:
    """A metadata-level step graph for server.workspace.requirements: one step per chapter
    (or one step carrying the description). Its lesson id is preflight-<videoId>, so S2's
    per-lesson cache never collides with the real lesson's."""
    chs = m.get("chapters") or []
    steps = [{"index": c["index"], "title": c["title"]} for c in chs[:40]] or [
        {"index": 0, "title": m.get("title") or "Video", "instructions": (m.get("description") or "")[:2500]}
    ]
    if chs and m.get("description"):
        steps[0]["instructions"] = m["description"][:2500]
    steps[0]["instructions"] = LOCAL_NOTE + "\n\n" + steps[0].get("instructions", "")
    return {
        "lesson": {"id": f"preflight-{m.get('videoId') or 'url'}", "title": m.get("title") or "", "goal": goal,
                   "libraries": libraries or m.get("keywords", [])[:10]},
        "sources": [{"kind": "video", "title": m.get("title") or "", "url": m.get("url") or ""}],
        "steps": steps,
    }


def _default_requirements() -> Callable | None:
    try:
        from server.workspace import requirements  # S2 (branch claude/workspace-setup)
    except ImportError:
        return None
    return requirements


# --------------------------------------------------------------------------- build plan

def est_build_s(segment_s: float | None) -> int:
    """Seconds until the learner sees their first steps. Calibrated on Run 3 (paid Gemini, E2 builder):
    react 44 s, pandas 51 s, git 69 s for 10-25 min videos (~30 s + ~1.5 s per minute watched);
    E2: "Gemini ~40 s on 6 min" for a long video's first window."""
    mins = min((segment_s or 600) / 60, 30)
    return round(30 + 1.5 * mins)


def _mirror_first(dur: float, chs: list[dict]) -> tuple[float, float, list[str]]:
    """E2's part-1 rule (progressive.plan_windows, d701162): chapters from the start grouped to 3-6 min; a part 1
    still under 3 min takes one more chapter as long as it stays <= 8 min; a chapter > 15 min is split into
    ~12 min spans; 8 min when there are < 3 chapters."""
    if len(chs) < 3:
        return (0.0, min(dur, FIRST_WINDOW_NO_CHAPTERS_S), [])
    spans: list[tuple[float, float, str]] = []
    for c in chs:
        a, b = float(c["start"]), float(c.get("end") or dur)
        if b <= a:
            continue
        if b - a > WINDOW_MAX_S:
            n = int((b - a) // WINDOW_TARGET_S) + 1
            spans += [(a + k * (b - a) / n, a + (k + 1) * (b - a) / n, f"{c['title']} ({k + 1}/{n})") for k in range(n)]
        else:
            spans.append((a, b, c["title"]))
    cur: list[tuple[float, float, str]] = []
    for sp in spans:
        cur_len = (cur[-1][1] - cur[0][0]) if cur else 0.0
        with_next = sp[1] - (cur[0][0] if cur else sp[0])
        too_short = cur_len < FIRST_MIN_S and with_next <= FIRST_HARD_MAX_S  # don't ship a 1-step part 1
        if cur and with_next > FIRST_MAX_S and cur_len >= 60 and not too_short:
            break
        cur.append(sp)
        if cur[-1][1] - cur[0][0] >= FIRST_MIN_S:
            break
    return (cur[0][0], cur[-1][1], [t for _, _, t in cur if t])


def _windows(dur: float, chs: list[dict], hands_on: float | None) -> tuple[list[tuple[float, float, list[str]]], bool, bool]:
    """(windows, all_known, hands_on_used). E2's plan_windows when importable (its 3rd argument skips
    the intro: everything before hands_on is one "(intro)" window, part 1 starts there), else the
    same rule for the first windows only."""
    try:
        from server.lesson.progressive import plan_windows  # E2

        args = (dur, [{"t": c["start"], "title": c["title"]} for c in chs])
        try:
            return plan_windows(*args, hands_on), True, bool(hands_on)
        except TypeError:  # an E2 version without first_hands_on
            return plan_windows(*args), True, False
    except Exception as e:  # noqa: BLE001 - not merged here / changed signature: local mirror
        log.debug("preflight: E2's plan_windows unavailable (%s), using the local mirror", type(e).__name__)
    if not hands_on:
        return [_mirror_first(dur, chs)], False, False
    later = [c for c in chs if c["start"] > hands_on]
    shifted = [{"start": 0, "title": "hands-on"}] + [dict(c, start=c["start"] - hands_on) for c in later] if chs else []
    for i, c in enumerate(shifted):
        c["end"] = shifted[i + 1]["start"] if i + 1 < len(shifted) else dur - hands_on
    a, b, titles = _mirror_first(dur - hands_on, shifted)
    intro = (0.0, float(hands_on), ["(intro) " + "; ".join(c["title"] for c in chs if c["start"] < hands_on)])
    return [intro, (a + hands_on, b + hands_on, titles)], False, True


def build_plan(m: dict, first_hands_on: int | None = None) -> dict:
    """whole, or chapters (E2's progressive build). firstChapter = the part E2 builds first;
    firstHandsOn = Claude's first chapter where the learner starts doing something. When that is
    between 1 and 10 min in, E2 skips everything before it (skippedIntro) and part 1 starts there;
    later than 10 min is not trusted (it would skip real work)."""
    dur = m.get("duration_s")
    chs = m.get("chapters") or []
    plan: dict = {"strategy": "whole", "firstChapter": None, "estSecondsToFirstSteps": est_build_s(dur)}
    hands_on = None
    if chs and first_hands_on is not None and 0 <= first_hands_on < len(chs):
        c = chs[first_hands_on]
        plan["firstHandsOn"] = {"index": c["index"], "title": c["title"], "start": c["start"]}
        if HANDS_ON_MIN_S <= c["start"] <= HANDS_ON_MAX_S and dur and c["start"] < dur - 60:
            hands_on = float(c["start"])
    if not dur or dur <= LONG_VIDEO_S:
        return plan
    wins, all_known, used = _windows(float(dur), chs, hands_on)
    if used and len(wins) > 1:
        plan["skippedIntro"] = {"start": 0, "end": int(wins[0][1])}
        a, b, titles = wins[1]
    else:
        a, b, titles = wins[0]
    idx = [i for i, c in enumerate(chs) if a <= c["start"] < b]
    first = {"index": idx[0] if idx else 0, "lastIndex": idx[-1] if idx else 0,
             "title": (chs[idx[0]]["title"] if idx else "") or (titles[0] if titles else f"First {round((b - a) / 60)} minutes"),
             "start": int(a), "end": int(b)}
    if not chs:
        first["window"] = True
    plan.update(strategy="chapters", firstChapter=first, estSecondsToFirstSteps=est_build_s(b - a))
    if all_known:
        plan["windows"] = len(wins)
    return plan


def video_meta(res: dict) -> dict | None:
    """What preflight knows, in the shape E2's build_lesson(..., video_meta=...) takes, so the build
    skips its own watch-page fetch and starts part 1 at the first hands-on chapter. None if nothing."""
    if not res.get("durationS"):
        return None
    out = {"title": res.get("title") or "", "description": res.get("description") or "", "duration_s": res["durationS"],
           "chapters": [{"start": c["start"], "title": c["title"]} for c in res.get("chapters") or []]}
    skipped = (res.get("buildPlan") or {}).get("skippedIntro")
    if skipped:
        out["firstHandsOn"] = skipped["end"]
    return out


# --------------------------------------------------------------------------- preflight()

MEMO_TTL_S = 600.0
LATE_S = 12.0  # how long a late stage may still finish (cold requirements: ~4 s; Claude: 1.6-3.7 s measured)
OnLate = Callable[[dict], Awaitable[None] | None]

_memo: dict[Any, tuple[float, dict]] = {}
_inflight: dict[Any, asyncio.Task] = {}
_late: dict[Any, asyncio.Task] = {}
_listeners: dict[Any, list[OnLate]] = {}
_bg: set[asyncio.Task] = set()


def _key(url: str, goal: str) -> tuple[str, str]:
    return (youtube.video_id(url) or url, " ".join((goal or "").lower().split()))


def _memo_get(key) -> dict | None:
    hit = _memo.get(key)
    if hit and time.monotonic() - hit[0] < MEMO_TTL_S:
        return hit[1]
    _memo.pop(key, None)
    return None


def _listen(key, on_late: OnLate | None) -> None:
    if on_late is not None and key in _late and not _late[key].done():
        _listeners.setdefault(key, []).append(on_late)


async def preflight(
    url: str,
    goal: str,
    *,
    row: dict | None = None,
    timeout: float = TIMEOUT_S,
    on_late: OnLate | None = None,
    late_s: float = LATE_S,
    api_keys: dict | None = None,
    keys: Keys | None = None,
    http: httpx.AsyncClient | None = None,
    claude_client=None,
    requirements_fn: Callable | None | bool = True,
    lesson_cache: Callable | bool = True,
    use_memo: bool = True,
    cache_dir: Path | None = None,
    classify_cache: Path | bool | None = None,
) -> dict:
    """Everything we can learn about the picked video within `timeout` seconds (hard). Never raises.

    row: the picked search.result (carries the finder's skim, if any).
    on_late(result): called once if a stage that missed the deadline (a cold tool check, a slow Claude
      reply) lands within `late_s` more seconds; re-emit preflight_card(result) then (same card, filled in).
    requirements_fn: True = server.workspace.requirements when importable; None/False = skip; or a callable.
    Results are memoised per (video, goal) for 10 min, and a call while prefetch() is still working on
    the same video waits for that run instead of starting another.
    classify_cache: where Claude's read is kept per (video, goal) (classify_cache_dir()); None = there unless a
      claude_client is passed (tests), False = never, a Path = that folder."""
    if classify_cache is None:
        classify_cache = classify_cache_dir() if claude_client is None else None
    elif classify_cache is True:
        classify_cache = classify_cache_dir()
    key = _key(url, goal) if use_memo else object()
    if use_memo:
        if (hit := _memo_get(key)) is not None:
            if (fresh := await _recheck_lesson_cache({**hit, "cached": True}, url, goal, lesson_cache)) is not None:
                _listen(key, on_late)
                return fresh
            _memo.pop(key, None)  # the lesson's .venv changed since that check: check it again
        elif (running := _inflight.get(key)) is not None:
            try:
                res = await asyncio.wait_for(asyncio.shield(running), timeout)
                if (fresh := await _recheck_lesson_cache({**res, "cached": True}, url, goal, lesson_cache)) is not None:
                    _listen(key, on_late)
                    return fresh
                _memo.pop(key, None)
            except Exception as e:  # noqa: BLE001 - a prefetch that failed or is slow: run our own
                log.info("preflight: prefetch for %s not usable (%s), running it now", key[0], type(e).__name__)
    if on_late is not None:
        _listeners.setdefault(key, []).append(on_late)
    task = asyncio.ensure_future(_run(key, url, goal, row=row, timeout=timeout, late_s=late_s, keys=keys or resolve_keys(api_keys),
                                      http=http, claude_client=claude_client, requirements_fn=requirements_fn, lesson_cache=lesson_cache,
                                      use_memo=use_memo, cache_dir=cache_dir, classify_cache=classify_cache or None))
    _inflight[key] = task
    try:
        return await task
    finally:
        if _inflight.get(key) is task:
            _inflight.pop(key, None)


async def _recheck_lesson_cache(res: dict, url: str, goal: str, lesson_cache) -> dict | None:
    """A memoised result may predate a build (prefetched, then built, then picked again): the lesson
    cache is re-read (milliseconds) so "Built before: ready instantly" is never stale. None when the lesson's
    .venv changed since (made by the build, added to by Install): its package checks are stale, so check again."""
    if not lesson_cache or not res.get("buildPlan"):
        return res
    look = lesson_cache if callable(lesson_cache) else cached_lesson

    def look_now() -> tuple[dict | None, str | None]:
        h = look(url, goal)
        return h, _venv_mark(_hit_folder(h))

    try:
        hit, venv = await asyncio.wait_for(asyncio.to_thread(look_now), 1.0)
    except Exception:  # noqa: BLE001
        return res
    if venv != res.get("lessonVenv"):
        log.info("preflight: the lesson .venv changed since the memoised check (%s -> %s)", res.get("lessonVenv"), venv)
        return None
    plan = dict(res["buildPlan"])
    if hit:
        res = {**res, "cachedLesson": {"file": hit["file"], "steps": hit["steps"], "workdir": hit["workdir"]}}
        plan.update(cached=True, estSecondsToFirstSteps=0)
    elif plan.pop("cached", None):  # the cached lesson is gone: back to the estimate
        res = {k: v for k, v in res.items() if k != "cachedLesson"}
        span = (plan.get("firstChapter") or {})
        plan["estSecondsToFirstSteps"] = est_build_s((span["end"] - span["start"]) if span else res.get("durationS"))
    return {**res, "buildPlan": plan}


def prefetch(rows: list[dict], goal: str, *, top: int = 3, **kw) -> list[asyncio.Task]:
    """Start preflight for the top video rows in the background (call on search.done). The later
    preflight() on the learner's pick then returns at once from the memo. Returns the tasks."""
    out = []
    for r in [r for r in rows if youtube.video_id(r.get("url", ""))][:top]:
        t = asyncio.ensure_future(preflight(r["url"], goal, row=r, **kw))
        _bg.add(t)
        t.add_done_callback(_bg.discard)
        out.append(t)
    return out


def clear_memo() -> None:
    _memo.clear()


async def _run(key, url: str, goal: str, *, row, timeout: float, late_s: float, keys: Keys, http, claude_client,
               requirements_fn, use_memo: bool, cache_dir, lesson_cache, classify_cache: Path | None = None) -> dict:
    t0 = time.monotonic()
    deadline = t0 + timeout

    def left(margin: float = 0.0) -> float:
        return max(0.0, deadline - time.monotonic() - margin)

    vid = youtube.video_id(url)
    res: dict[str, Any] = {"url": url, "videoId": vid, "goal": goal, "partial": False, "missing": [], "notes": [], "timings": {}}
    own_http = http is None
    http = http or httpx.AsyncClient()
    tasks: dict[str, asyncio.Task] = {}
    late: dict[str, asyncio.Task] = {}
    try:
        cache_task = None
        if lesson_cache:
            look = lesson_cache if callable(lesson_cache) else cached_lesson
            cache_task = asyncio.ensure_future(asyncio.to_thread(look, url, goal))
        # 1. metadata
        try:
            m, notes = await asyncio.wait_for(meta_mod.fetch(http, url, keys, timeout=min(3.0, max(0.5, left(1.5)))),
                                              max(0.1, left(1.2)))
        except TimeoutError:
            m, notes = {"videoId": vid, "url": youtube.watch_url(vid) if vid else url}, ["metadata timed out"]
        res["notes"] += notes
        res["timings"]["meta"] = round(time.monotonic() - t0, 2)
        prior = finder_prior(row, vid)
        for k_row, k_meta in (("durationS", "duration_s"), ("title", "title"), ("channel", "channel")):
            if prior.get(k_row) and not m.get(k_meta):  # watch page / oEmbed failed: the search row still read it
                m[k_meta] = prior[k_row]
        _copy_meta(res, m)
        for k in ("durationLabel", "long"):
            if k in prior:
                res[k] = prior[k]
        # V5: captions are True when the finder saw CC, the watch page lists caption tracks or the builder cached a
        # transcript; a missing CC badge is no proof of "no captions" (auto captions carry none), so never claim False
        if prior.get("captions") or m.get("captions") or _transcript_cached(vid):
            res["captions"] = True
        if not m.get("title"):
            res["missing"].append("metadata")

        skim = cached_skim(vid, row, cache_dir=cache_dir)
        if skim:
            res["skim"] = skim

        # 2. Claude + tools in parallel
        async def timed(name: str, coro):
            t1 = time.monotonic()
            try:
                return await coro
            finally:
                res["timings"][name] = round(time.monotonic() - t1, 2)

        known = classify_cached(classify_cache, vid, goal) if m.get("title") else None
        if known is not None:  # Claude already read this video for this goal: no call, no wait
            tasks["claude"] = asyncio.create_task(timed("claude", _known(known)))
            res["notes"].append("claude: saved read")
        elif m.get("title") and (keys.anthropic or claude_client is not None):
            tasks["claude"] = asyncio.create_task(timed("claude", _classify_kept(classify_cache, vid, goal, classify(
                keys.anthropic or "", goal, m, skim, timeout=max(0.5, left(0.1)) + max(0.0, late_s), client=claude_client,
                prior=prior))))
        elif m.get("title"):
            res["notes"].append("no ANTHROPIC_API_KEY")
        req = _default_requirements() if requirements_fn is True else (requirements_fn or None)
        cached = None
        if cache_task is not None:
            try:
                cached = await asyncio.wait_for(asyncio.shield(cache_task), max(0.05, left(3.5)))
            except Exception as e:  # noqa: BLE001 - slow disk / E2 changed: just no "built before"
                res["notes"].append(f"lesson cache: {type(e).__name__}: {str(e)[:80]}")
            res["timings"]["cache"] = round(time.monotonic() - t0, 2)
        if cached:
            res["cachedLesson"] = {"file": cached["file"], "steps": cached["steps"], "workdir": cached["workdir"]}
            res["lessonFolder"] = _hit_folder(cached)
            res["lessonVenv"] = await asyncio.to_thread(_venv_mark, res["lessonFolder"])
        if req is not None and (m.get("title") or cached):
            if cached:  # the real lesson in its real folder (its .venv, if any): exactly what the setup card will check
                job = functools.partial(_call_req, req, cached["graph"], res["lessonFolder"])
            else:
                job = functools.partial(_call_req, req, light_graph(m, goal), None)
            tasks["requirements"] = asyncio.create_task(timed("requirements", asyncio.to_thread(job)))
        elif requirements_fn is True:
            res["notes"].append("server.workspace.requirements not available (S2's branch claude/workspace-setup not merged here)")
        if tasks:
            await asyncio.wait(tasks.values(), timeout=left(0.05))
        for name, t in tasks.items():
            if not t.done():
                if late_s > 0:  # keep going: on_late gets it (and S2 caches its list for the setup card)
                    late[name] = t
                else:
                    t.cancel()
                res["missing"].append(name)
                res["notes"].append(f"{name}: not back within {timeout:g} s")
                continue
            _merge(res, name, t)
        if not res.get("style") and prior.get("style"):  # Claude late / failed: the search's own read (real, from E7)
            res.update(style=prior["style"], styleFrom="finder")
        res["buildPlan"] = build_plan(m, res.pop("_firstHandsOn", None))
        if res.get("cachedLesson"):  # E2 returns the cached graph at once (measured 0.00-0.02 s on stage)
            res["buildPlan"].update(cached=True, estSecondsToFirstSteps=0)
        res["editorNeeded"] = _editor_needed(res)
    except Exception as e:
        log.exception("preflight failed")
        res["missing"].append("preflight")
        res["notes"].append(f"preflight: {type(e).__name__}: {str(e)[:120]}")
    finally:
        if own_http:
            await http.aclose()
    res["partial"] = bool(res["missing"])
    res["timings"]["total"] = round(time.monotonic() - t0, 2)
    if use_memo and res.get("goalMatch"):
        _memo[key] = (time.monotonic(), res)
    if late:
        lt = asyncio.ensure_future(_finish_late(key, dict(res, missing=list(res["missing"]), notes=list(res["notes"]),
                                                          timings=res["timings"]), late, late_s, t0, use_memo, m))
        _late[key] = lt
        _bg.add(lt)
        lt.add_done_callback(_bg.discard)
    else:
        _listeners.pop(key, None)
    return res


def _merge(res: dict, name: str, t: asyncio.Task) -> bool:
    if t.cancelled():
        res["missing"].append(name)
        return False
    if (e := t.exception()) is not None:
        res["missing"].append(name)
        res["notes"].append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
        return False
    if name == "claude":
        c = t.result()
        res.update({k: c[k] for k in ("topic", "goalMatch", "libraries", "styleWhy")})
        if c["style"]:
            res.update(style=c["style"], styleFrom="claude")
        res["_firstHandsOn"] = c["firstHandsOnChapter"]
        return True
    items = t.result() or []
    if not items:
        res["missing"].append(name)
        res["notes"].append("requirements: empty (no key / Claude failed)")
        return False
    res["requirements"] = items
    return True


async def _finish_late(key, res: dict, late: dict[str, asyncio.Task], late_s: float, t0: float, use_memo: bool,
                       m: dict) -> None:
    try:
        await asyncio.wait(late.values(), timeout=late_s)
        changed = False
        for name, t in late.items():
            if not t.done():
                t.cancel()
                continue
            res["missing"] = [x for x in res["missing"] if x != name]
            res["notes"] = [n for n in res["notes"] if not n.startswith(f"{name}: not back")]
            changed = _merge(res, name, t) or changed
        if not changed:
            return
        if "_firstHandsOn" in res:  # Claude came back late: its first hands-on chapter shapes the plan
            res["buildPlan"] = build_plan(m, res.pop("_firstHandsOn"))
        res["editorNeeded"] = _editor_needed(res)
        res["partial"] = bool(res["missing"])
        res["late"] = True
        res["timings"] = {**res["timings"], "late": round(time.monotonic() - t0, 2)}
        if use_memo and res.get("goalMatch"):
            _memo[key] = (time.monotonic(), res)
        for cb in _listeners.get(key, []):
            try:
                out = cb(res)
                if asyncio.iscoroutine(out):
                    await out
            except Exception:
                log.exception("preflight on_late callback failed")
    finally:
        _listeners.pop(key, None)
        if _late.get(key) is asyncio.current_task():
            _late.pop(key, None)


def _transcript_cached(video_id: str | None) -> bool:
    """A transcript the lesson builder fetched for this video (demo/cache/transcripts/<id>.json, with lines)."""
    if not video_id:
        return False
    try:
        from server.lesson.transcript import _cache_path

        p = _cache_path(video_id)
        return p.is_file() and bool((json.loads(p.read_text()) or {}).get("transcript"))
    except Exception:  # noqa: BLE001
        return False


def _copy_meta(res: dict, m: dict) -> None:
    for src, dst in (("title", "title"), ("channel", "channel"), ("duration_s", "durationS"), ("category", "category"),
                     ("keywords", "keywords"), ("published", "published"), ("thumbnail", "thumbnail"),
                     ("chapters", "chapters"), ("chaptersFrom", "chaptersFrom")):
        if m.get(src) not in (None, "", []):
            res[dst] = m[src]
    if m.get("description"):
        res["description"] = m["description"][:5000]
    if m.get("url"):
        res["url"] = m["url"]
    res.setdefault("chapters", [])


def _editor_needed(res: dict) -> bool | None:
    """Coding lessons always run locally in VS Code (E2 adapts them to a local folder, even when the video
    uses Colab). Otherwise S2's answer when we have it, else from the style (no editor for no-code / conceptual)."""
    if res.get("style") == "coding":
        for it in res.get("requirements") or []:
            if it.get("kind") == "editor" and not it.get("needed"):
                it.update(needed=True, why="You write and run the code locally in VS Code.")
        return True
    for it in res.get("requirements") or []:
        if it.get("kind") == "editor":
            return bool(it.get("needed"))
    if res.get("style"):
        return res["style"] == "coding"
    return None


# --------------------------------------------------------------------------- the card

def _venv_install(it: dict) -> bool:
    """A Python package that isn't there yet: the setup card's Install puts it in the lesson's .venv (made with
    best_python() when there's none yet), so it isn't "✗"."""
    return (it.get("kind") == "python_package" and not it.get("ok")
            and (it.get("install") or {}).get("method") == "pip")


def needs_line(items: list[dict]) -> str:
    """'Needs: VS Code ✓ Python ✓ Git ✗ PyTorch, numpy (to install in the lesson's .venv)' (needed items only; the
    editor only when it's needed; web apps as 'Botpress (web)'). Desktop test 10: a Python package that isn't installed
    yet says what the setup card will do with it, not "✗"."""
    shown = [it for it in items if it.get("needed")]
    if not shown:
        return ""

    def one(it: dict) -> str:
        label = it.get("label") or it.get("tool")
        if it.get("kind") == "web_app":  # S2: a website, nothing to install or check
            return f"{label} (web)"
        return f"{label} {'✓' if it.get('ok') else '✗'}"

    parts = [one(it) for it in shown if not _venv_install(it)]
    venv = [str(it.get("label") or it.get("tool")) for it in shown if _venv_install(it)]
    if venv:
        parts.append(f"{', '.join(venv)} (to install in the lesson's .venv)")
    return "Needs: " + " ".join(parts)


def _sentence(text: str) -> str:
    """V5: a body line ends like a sentence (the app may run the lines together into one paragraph)."""
    text = " ".join((text or "").split())
    return text if not text or text[-1] in ".!?…" else text + "."


def _whole_minutes(secs: Any) -> Any:
    """t12: the card's length as the app shows it ("N min", rounded): whole minutes, rounded down, so an 8:40 video
    reads "8 min" beside the result's 8:40 (it read "9 min"). Under a minute (or unknown): as it is."""
    return 60 * (int(secs) // 60) if isinstance(secs, (int, float)) and secs >= 60 else secs


def preflight_card(res: dict) -> dict:
    """card {kind: "preflight"}: what the video is, how well it fits the goal, what it needs.
    actions: build / pick_another, plus install when a needed tool is missing (S2's install flow).
    Desktop test 10: the body no longer carries the "Coding · 8:40 · 7 chapters · CC" line or the "Needs: …" line; the
    app draws both from card.preflight and card.items ("Coding · 8 min · 7 chapters · Captions", "Needs … · 4 to
    install"), so the card said everything twice."""
    channel, topic = " ".join((res.get("channel") or "").split()), " ".join((res.get("topic") or "").split())
    # V5: a topic that opens with the channel's last word takes the channel as its subject ("Kie Codes codes and
    # trains a…", never "Codes and trains a…" right under the channel)
    if channel and topic and topic.split()[0].strip(",.:;").lower() == channel.split()[-1].lower():
        topic = f"{channel} {topic[0].lower()}{topic[1:]}"
    lines = [_sentence(topic)]
    gm = res.get("goalMatch")
    warning = None
    if gm and gm.get("score") is not None and gm["score"] < LOW_MATCH:  # t12: the fit note only on a poor match
        warning = gm.get("note") or "This video may not teach your goal."  # (a good one's said "though only a basic
        lines.append("⚠ " + _sentence(warning))  # digit classifier on one dataset" under a 0.9 match)
    plan = res.get("buildPlan") or {}
    est = plan.get("estSecondsToFirstSteps")
    if plan.get("cached"):
        n = (res.get("cachedLesson") or {}).get("steps")
        lines.append(f"Built before: ready instantly{f' ({n} steps)' if n else ''}.")
    elif plan.get("strategy") == "chapters" and plan.get("firstChapter"):
        fc = plan["firstChapter"]
        span = f"{_ts(fc['start'])}–{_ts(fc.get('end'))}"
        skip = plan.get("skippedIntro")
        intro = f"skipping the {_ts(skip['end'])} intro, " if skip else ""
        lines.append(f"Long video: {intro}I'll build {span} first (~{est} s), the rest while you work.")
        ho = plan.get("firstHandsOn")
        if ho and not skip and ho["start"] >= fc.get("end", 0):
            lines.append(f"Hands-on starts at {_ts(ho['start'])} ({ho['title']}).")
    elif est:
        lines.append(f"Building takes ~{est} s.")
    if res.get("editorNeeded") is False:
        lines.append("No code editor needed for this one.")
    if res.get("partial") and not res.get("goalMatch"):
        lines.append("I couldn't check this video in time; you can still build it.")
    items = res.get("requirements") or []  # the app's "Needs … · N to install" row (needs_line is the text form)
    missing = [it for it in items if it.get("needed") and not it.get("ok")]
    actions = ["build", "pick_another"] + (["install"] if missing else [])
    card: dict[str, Any] = {
        "kind": "preflight",
        "title": res.get("title") or "This video",
        "body": "\n".join(ln for ln in lines if ln),
        "items": [{
            "tool": it.get("tool"), "label": it.get("label"), "kind": it.get("kind"), "needed": bool(it.get("needed")),
            "installed": bool(it.get("installed")), "ok": bool(it.get("ok")), "version": it.get("version") or None,
            "why": it.get("why") or "",
            "install": {k: (it.get("install") or {}).get(k) or None for k in ("method", "command", "url")},
        } for it in items],
        "actions": actions,
        "preflight": {
            "videoId": res.get("videoId"), "url": res.get("url"), "style": res.get("style"), "styleFrom": res.get("styleFrom"), "topic": res.get("topic"),
            "durationS": _whole_minutes(res.get("durationS")), "chapters": len(res.get("chapters") or []),
            "goalMatch": gm, "buildPlan": plan, "editorNeeded": res.get("editorNeeded"), "partial": res.get("partial", False),
        },
    }
    if warning:
        card["warning"] = warning
        card["recommended"] = "pick_another"
    return card
