"""Plans in progress on this Mac: <state dir>/plans.json. Local only; nothing here leaves the Mac.

A plan in progress (ui-v4 contract PlanState, shared/contracts/events.py) is one of:
- preset: a catalog plan. id = its catalog id; its lessons are read from the catalog (so a catalog update shows).
- playlist: a YouTube playlist. id = "pl-<playlistId>"; its lessons (one per video) are kept in the record, since a
  playlist can change.
- goal: lessons proposed for the learner's goal (proposal.py). id = "goal-<8 hex>" (from the goal); lessons kept.
Per plan: the lessons done and skipped, the lesson started last (current), when each plan lesson was opened and the
engine lesson it became (lessonId), and the lessons the learner un-marked (undone: never re-marked by reconcile).

A plan lesson is done when its engine lesson finished: history.json (sessions.store.record_completed, the last step
passed) has its lessonId. The link from plan lesson to engine lesson is made when the lesson starts (link_lesson), or
found later (reconcile): the lesson saved in current.json that started right after the plan lesson was asked for (a
video lesson: its sourceUrl names the video), or a finished lesson that covered the plan lesson's goal.
Writes are atomic (sessions.store._write_atomic) and serialized by one lock (the engine reads in worker threads).

Times are kept as epoch seconds (time.time()) and sent as ISO strings. Wall-clock jumps: the link window below is a
two-sided comparison (a lesson stamped before the plan lesson was opened, or long after it, is never linked), so a
clock moved backwards or forwards can at worst leave a lesson unlinked; the learner's own mark still counts.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from datetime import datetime
from typing import Any

from server.sessions import store
from server.sessions.store import _read, _write_atomic, state_dir

from . import catalog

log = logging.getLogger("plans.progress")

VERSION = 2
LINK_WINDOW_S = 30 * 60.0  # a lesson that started this long after the plan lesson was asked for is not that lesson
MAX_PLANS = 60
MAX_LESSONS = 200
# a catalog id ("intro-python"), "goal-<8 hex>" (same shape), or "pl-<playlistId>"
KEY_RE = re.compile(r"^(?:[a-z0-9][a-z0-9-]{0,63}|pl-[A-Za-z0-9_-]{10,64})$")
SOURCES = ("preset", "playlist", "goal")

_lock = threading.RLock()


def _path():
    return state_dir() / "plans.json"


def _migrate(key: str, rec: dict) -> tuple[str, dict] | None:
    """A v1 record (kind catalog | playlist, planId, "yt-<id>" keys) as a v2 one. None: unusable."""
    if rec.get("source") in SOURCES:
        return key, rec
    kind = rec.get("kind")
    if kind == "catalog" and isinstance(rec.get("planId"), str):
        rec = {k: v for k, v in rec.items() if k not in ("kind", "planId", "key")}
        rec.update(source="preset", catalogId=key)
        return key, rec
    if kind == "playlist" and isinstance(rec.get("playlistId"), str):
        rec = {k: v for k, v in rec.items() if k not in ("kind", "key")}
        rec["source"] = "playlist"
        return playlist_key(rec["playlistId"]), rec
    return None


def _load() -> dict:
    data = _read(_path())
    if not isinstance(data, dict) or not isinstance(data.get("plans"), dict):
        return {"version": VERSION, "plans": {}}
    plans: dict[str, dict] = {}
    for k, v in data["plans"].items():
        got = _migrate(k, v) if isinstance(v, dict) and isinstance(k, str) else None
        if got and KEY_RE.fullmatch(got[0]):
            plans[got[0]] = dict(got[1], id=got[0])
    return {"version": VERSION, "plans": plans}


def _save(data: dict) -> None:
    if len(data["plans"]) > MAX_PLANS:  # the oldest untouched plans go first
        keep = sorted(data["plans"].items(), key=lambda kv: -_num(kv[1].get("lastActiveAt")))[:MAX_PLANS]
        data["plans"] = dict(keep)
    _write_atomic(_path(), {"version": VERSION, "plans": data["plans"]})


def _num(v: Any) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def iso(t: Any) -> str | None:
    """Epoch seconds as a local ISO 8601 string ("2026-11-22T19:31:00-08:00"); None for no time."""
    if not isinstance(t, (int, float)) or isinstance(t, bool) or t <= 0:
        return None
    try:
        return datetime.fromtimestamp(float(t)).astimezone().isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def playlist_key(playlist_id: str) -> str:
    return "pl-" + playlist_id


def goal_key(goal: str) -> str:
    norm = " ".join(re.findall(r"[a-z0-9]+", (goal or "").lower()))
    return "goal-" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:8]


def _lessons(rec: dict) -> list[dict]:
    """The plan's lessons: a preset's from the catalog, a playlist's or goal's from the record."""
    if rec.get("source") == "preset":
        plan = catalog.get(rec.get("catalogId"))
        return plan["lessons"] if plan else []
    return [le for le in rec.get("lessons") or [] if isinstance(le, dict)]


def _ints(v: Any, n: int) -> set[int]:
    return {i for i in v if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < n} if isinstance(v, list) else set()


def _int_key(k: Any) -> int | None:
    try:
        return int(k)
    except (TypeError, ValueError):
        return None


def _settle(rec: dict, now: float | None = None) -> bool:
    """finishedAt follows the plan being finished (every lesson done or skipped). True when it changed."""
    n = len(_lessons(rec))
    over = _ints(rec.get("done"), n) | _ints(rec.get("skipped"), n)
    finished = n > 0 and len(over) == n and bool(_ints(rec.get("done"), n))
    if finished and not rec.get("finishedAt"):
        rec["finishedAt"] = now or time.time()
        return True
    if not finished and rec.get("finishedAt"):
        rec.pop("finishedAt")
        return True
    return False


def _touch(data: dict, rec: dict, now: float) -> dict:
    rec["lastActiveAt"] = now
    _settle(rec, now)
    data["plans"][rec["id"]] = rec
    _save(data)
    return _view(rec, store.load())


# ------------------------------------------------------------------------------------------------ adding a plan


def start_catalog(catalog_id: str) -> dict:
    """Add a catalog plan, or touch it when it is already there (the same catalogId answers with that plan).
    Returns its PlanState. Raises KeyError for an id that is not in the catalog."""
    plan = catalog.get(catalog_id)
    if plan is None:
        raise KeyError(catalog_id)
    with _lock:
        data = _load()
        now = time.time()
        rec = data["plans"].get(catalog_id) or {"id": catalog_id, "source": "preset", "catalogId": catalog_id,
                                                "done": [], "started": {}, "current": None, "startedAt": now}
        rec["title"] = plan["title"]
        return _touch(data, rec, now)


def start_playlist(playlist_id: str, lessons: list[dict], *, title: str = "", channel: str = "", url: str | None = None,
                   tool: dict | None = None, project: dict | None = None, skipped: set[int] | None = None) -> dict:
    """Add a playlist plan (lessons: one per video, {title, videoId, seconds?, minutes?, grows?}). Re-adding it keeps
    what is done and takes the new lessons: done marks follow their video, not their position."""
    key = playlist_key(playlist_id)
    lessons = lessons[:MAX_LESSONS]
    with _lock:
        data = _load()
        now = time.time()
        old = data["plans"].get(key)
        rec = {"id": key, "source": "playlist", "playlistId": playlist_id, "title": title or "Playlist",
               "channel": channel, "url": url or f"https://www.youtube.com/playlist?list={playlist_id}",
               "lessons": lessons, "done": [], "skipped": sorted(skipped or ()), "started": {}, "current": None,
               "startedAt": now}
        if tool:
            rec["tool"] = tool
        if project:
            rec["project"] = project
        if old:
            by_vid = {le.get("videoId"): i for i, le in enumerate(lessons)}
            old_lessons = old.get("lessons") or []

            def moved(i: Any) -> int | None:
                if isinstance(i, int) and 0 <= i < len(old_lessons) and isinstance(old_lessons[i], dict):
                    return by_vid.get(old_lessons[i].get("videoId"))
                return None

            for f in ("done", "undone"):
                rec[f] = sorted({j for j in (moved(i) for i in old.get(f) or []) if j is not None})
            for f in ("started", "doneAt"):
                rec[f] = {str(j): v for k, v in (old.get(f) or {}).items() if (j := moved(_int_key(k))) is not None}
            rec["current"] = moved(old.get("current"))
            rec["startedAt"] = old.get("startedAt") or now
        return _touch(data, rec, now)


def start_goal(goal: str, lessons: list[dict], *, title: str = "", tool: dict | None = None,
               project: dict | None = None, skipped: set[int] | None = None) -> dict:
    """Add a goal plan from an accepted proposal (lessons: {title, goal?, videoId?, minutes?, grows?, from?}).
    The same goal again answers with the plan already there."""
    key = goal_key(goal)
    with _lock:
        data = _load()
        now = time.time()
        rec = data["plans"].get(key)
        if rec is None:
            rec = {"id": key, "source": "goal", "goal": goal[:300], "title": title or goal[:80],
                   "lessons": lessons[:MAX_LESSONS], "done": [], "skipped": sorted(skipped or ()), "started": {},
                   "current": None, "startedAt": now}
            if tool:
                rec["tool"] = tool
            if project:
                rec["project"] = project
        return _touch(data, rec, now)


def remove(key: str) -> bool:
    with _lock:
        data = _load()
        if key not in data["plans"]:
            return False
        del data["plans"][key]
        _save(data)
        return True


# ------------------------------------------------------------------------------------------------ lessons


def lesson_starting(key: str, index: int, *, library_id: str | None = None) -> dict | None:
    """The learner started plan lesson `index` (learn / learn_url / library.start carrying plan {id, index}): it is
    now in progress. A re-opened lesson starts over: its old link and any un-mark are dropped. Returns the PlanState."""
    with _lock:
        data = _load()
        rec = data["plans"].get(key)
        if rec is None or not 0 <= index < len(_lessons(rec)):
            return None
        now = time.time()
        ent: dict[str, Any] = {"at": now}
        if library_id:
            ent["libraryId"] = library_id
        rec.setdefault("started", {})[str(index)] = ent
        rec["undone"] = [i for i in rec.get("undone") or [] if i != index]
        rec["skipped"] = [i for i in rec.get("skipped") or [] if i != index]
        rec["current"] = index
        return _touch(data, rec, now)


def link_lesson(key: str, index: int, lesson_id: str) -> bool:
    """The engine lesson plan lesson `index` became (the engine knows it when the lesson loads)."""
    if not isinstance(lesson_id, str) or not lesson_id:
        return False
    with _lock:
        data = _load()
        rec = data["plans"].get(key)
        if rec is None or not 0 <= index < len(_lessons(rec)):
            return False
        ent = rec.setdefault("started", {}).setdefault(str(index), {"at": time.time()})
        if ent.get("lessonId") == lesson_id:
            return True
        ent["lessonId"] = lesson_id
        _save(data)
        return True


def mark_done(key: str, index: int, done: bool = True) -> dict | None:
    """The learner's own mark on a plan lesson. Un-marking sticks: the lesson goes on `undone`, which reconcile never
    re-marks from history (the linked engine lesson stays finished), until the learner opens the lesson again."""
    with _lock:
        data = _load()
        rec = data["plans"].get(key)
        if rec is None or not 0 <= index < len(_lessons(rec)):
            return None
        now = time.time()
        s = set(rec.get("done") or [])
        u = set(rec.get("undone") or [])
        at = rec.setdefault("doneAt", {})
        if done:
            s.add(index)
            u.discard(index)
            at.setdefault(str(index), now)
        else:
            s.discard(index)
            u.add(index)
            at.pop(str(index), None)
        rec["done"], rec["undone"] = sorted(s), sorted(u)
        return _touch(data, rec, now)


def _next_index(rec: dict, n: int) -> int | None:
    over = _ints(rec.get("done"), n) | _ints(rec.get("skipped"), n)
    cur = rec.get("current")
    if isinstance(cur, int) and 0 <= cur < n and cur not in over:
        return cur
    return next((i for i in range(n) if i not in over), None)


# ------------------------------------------------------------------------------------------------ reconcile


def _norm(s: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", s.lower())) if isinstance(s, str) else ""


def _reconcile(rec: dict, history: list[dict], current: dict | None, linked: set[str]) -> bool:
    """Link started plan lessons to engine lessons and mark finished ones done. True when the record changed.
    A lesson the learner un-marked (undone) is never marked again from history."""
    lessons = _lessons(rec)
    started = rec.get("started") if isinstance(rec.get("started"), dict) else {}
    done = _ints(rec.get("done"), len(lessons))
    undone = _ints(rec.get("undone"), len(lessons))
    done_at = rec.get("doneAt") if isinstance(rec.get("doneAt"), dict) else {}
    changed = False
    by_id = {e["lessonId"]: e for e in history}
    for k, ent in sorted(started.items(), key=lambda kv: _num((kv[1] or {}).get("at") if isinstance(kv[1], dict) else 0)):
        i = _int_key(k)
        if i is None or not 0 <= i < len(lessons) or not isinstance(ent, dict) or i in undone:
            continue
        at = _num(ent.get("at"))
        le = lessons[i]
        lid = ent.get("lessonId")
        if not lid and isinstance(current, dict) and isinstance(current.get("lessonId"), str) \
                and current["lessonId"] not in linked:
            c_at = _num(current.get("startedAt"))
            vid = le.get("videoId")
            # guarded both ways: a clock jump never links a lesson from before the ask or far after it
            if vid and vid in str(current.get("sourceUrl") or "") and at - 1 <= c_at <= at + LINK_WINDOW_S \
                    or not vid and at - 1 <= c_at <= at + LINK_WINDOW_S and _is_latest_start(started, at, c_at):
                lid = ent["lessonId"] = current["lessonId"]
                linked.add(lid)
                changed = True
        if not lid and i not in done:
            goal = _norm(le.get("goal") or le.get("title"))
            for e in history:
                if _num(e.get("finishedAt")) >= at and e["lessonId"] not in linked and goal and \
                        any(_norm(c) == goal for c in [e.get("title")] + list(e.get("covered") or [])):
                    lid = ent["lessonId"] = e["lessonId"]
                    linked.add(lid)
                    changed = True
                    break
        if lid and lid in by_id and i not in done:
            done.add(i)
            done_at[str(i)] = _num(by_id[lid].get("finishedAt")) or time.time()
            changed = True
    if changed:
        rec["done"] = sorted(done)
        rec["doneAt"] = done_at
    return _settle(rec) or changed


def _is_latest_start(started: dict, at: float, c_at: float) -> bool:
    """No other plan lesson was asked for between this one and the lesson's start (that lesson would be the one)."""
    return not any(at < _num(e.get("at")) <= c_at for e in started.values() if isinstance(e, dict))


def _sync(data: dict) -> bool:
    history = store.completed()
    current = store.load()
    changed = False
    linked = {str(ent.get("lessonId")) for rec in data["plans"].values()
              for ent in (rec.get("started") or {}).values() if isinstance(ent, dict) and ent.get("lessonId")}
    for rec in data["plans"].values():
        changed = _reconcile(rec, history, current, linked) or changed
    return changed


# ------------------------------------------------------------------------------------------------ views


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _lesson_row(rec: dict, i: int, le: dict, state: str, ent: dict, done_at: Any) -> dict:
    preset = rec.get("source") == "preset"
    grows = le.get("grows")
    return _clean({
        "index": i, "title": le.get("title") or f"Lesson {i + 1}", "goal": le.get("goal") or None,
        "videoId": le.get("videoId"), "seconds": le.get("seconds"), "minutes": le.get("minutes"),
        "stepCount": le.get("steps") if preset else le.get("stepCount"), "check": le.get("check"),
        "passes": le.get("passes") or None, "skillIds": list(grows) if isinstance(grows, list) and grows else None,
        "state": state, "lessonId": ent.get("lessonId"), "libraryId": ent.get("libraryId"),
        "openedAt": iso(ent.get("at")), "doneAt": iso(done_at) if state == "done" else None,
    })


def _view(rec: dict, current: dict | None = None) -> dict:
    """A record as a contract PlanState."""
    lessons = _lessons(rec)
    n = len(lessons)
    done = _ints(rec.get("done"), n)
    skipped = _ints(rec.get("skipped"), n) - done
    nxt = _next_index(rec, n)
    started = rec.get("started") if isinstance(rec.get("started"), dict) else {}
    done_at = rec.get("doneAt") if isinstance(rec.get("doneAt"), dict) else {}
    rows = []
    for i, le in enumerate(lessons):
        ent = started.get(str(i)) if isinstance(started.get(str(i)), dict) else {}
        state = ("done" if i in done else "skipped" if i in skipped
                 else ("in_progress" if ent else "next") if i == nxt else "todo")
        row = _lesson_row(rec, i, le, state, ent, done_at.get(str(i)))
        # the lesson running now, when it is this plan lesson's engine lesson: its step count (the plan page's "2 of 5")
        if state == "in_progress" and isinstance(current, dict) and ent.get("lessonId") \
                and current.get("lessonId") == ent["lessonId"] and isinstance(current.get("stepCount"), int):
            row["steps"] = {"done": len(current.get("passedSteps") or []), "total": current["stepCount"]}
        rows.append(row)
    plan = catalog.get(rec.get("catalogId")) if rec.get("source") == "preset" else None
    tool = plan["tool"] if plan else rec.get("tool")
    project = dict(plan["project"]) if plan else rec.get("project")
    if isinstance(project, dict) and project.get("title"):
        project = dict(project, state="ready" if n and nxt is None else "locked")
    else:
        project = None
    minutes = [r["minutes"] for r in rows if r["state"] not in ("done", "skipped") and isinstance(r.get("minutes"), int)]
    return _clean({
        "id": rec["id"], "title": rec.get("title") or (plan or {}).get("title") or "Plan", "source": rec["source"],
        "catalogId": rec.get("catalogId"), "playlistId": rec.get("playlistId"), "url": rec.get("url"),
        "goal": rec.get("goal"), "track": (plan or {}).get("track") or rec.get("track") or None,
        "tool": dict(tool) if isinstance(tool, dict) and tool.get("id") else None,
        "lessons": rows, "project": project, "done": len(done), "total": n - len(skipped), "nextIndex": nxt,
        "minutesLeft": sum(minutes), "startedAt": iso(rec.get("startedAt")), "updatedAt": iso(rec.get("lastActiveAt")),
        "finishedAt": iso(rec.get("finishedAt")),
    })


def view(key: str) -> dict | None:
    with _lock:
        data = _load()
        if key not in data["plans"]:
            return None
        if _sync(data):
            _save(data)
        return _view(data["plans"][key], store.load())


def all_views() -> list[dict]:
    """Every plan in progress (PlanState), the most recently used first."""
    with _lock:
        data = _load()
        if _sync(data):
            _save(data)
        cur = store.load()
        recs = sorted(data["plans"].values(), key=lambda r: -_num(r.get("lastActiveAt")))
        return [_view(r, cur) for r in recs]


def done_plan_ids() -> set[str]:
    """Catalog plans finished on this Mac (goal matching skips their `needs`)."""
    return {v["catalogId"] for v in all_views() if v["source"] == "preset" and v.get("finishedAt") and v.get("catalogId")}


def skills_done() -> set[str]:
    """Skill ids grown by plan lessons done on this Mac (a proposal's `have`)."""
    out: set[str] = set()
    for v in all_views():
        for le in v["lessons"]:
            if le["state"] == "done":
                out.update(le.get("skillIds") or [])
    return out
