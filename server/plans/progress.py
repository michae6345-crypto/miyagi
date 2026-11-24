"""Plans in progress on this Mac: <state dir>/plans.json. Local only; nothing here leaves the Mac.

A plan in progress is a catalog plan (key = its id) or a YouTube playlist (key = "yt-<playlist id>", its videos kept
in the record since a playlist can change). Per plan: the lessons done, the lesson started last (current), when each
plan lesson was started and the engine lesson it became (lessonId).

A plan lesson is done when its engine lesson finished: history.json (sessions.store.record_completed, the last step
passed) has its lessonId. The link from plan lesson to engine lesson is made when the lesson starts (link_lesson), or
found later (reconcile): the lesson saved in current.json that started right after the plan lesson was asked for (a
video lesson: its sourceUrl names the video), or a finished lesson that covered the plan lesson's goal.
Writes are atomic (sessions.store._write_atomic) and serialized by one lock (the engine reads in worker threads).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from server.sessions import store
from server.sessions.store import _read, _write_atomic, state_dir

from . import catalog

log = logging.getLogger("plans.progress")

VERSION = 1
LINK_WINDOW_S = 30 * 60.0  # a lesson that started this long after the plan lesson was asked for is not that lesson
MAX_PLANS = 60
KEY_RE = re.compile(r"^(?:[a-z0-9][a-z0-9-]{0,63}|yt-[A-Za-z0-9_-]{10,64})$")

_lock = threading.RLock()


def _path():
    return state_dir() / "plans.json"


def _load() -> dict:
    data = _read(_path())
    if not isinstance(data, dict) or not isinstance(data.get("plans"), dict):
        return {"version": VERSION, "active": None, "plans": {}}
    data["plans"] = {k: v for k, v in data["plans"].items() if isinstance(v, dict) and KEY_RE.fullmatch(k)}
    if data.get("active") not in data["plans"]:
        data["active"] = None
    return data


def _save(data: dict) -> None:
    if len(data["plans"]) > MAX_PLANS:  # the oldest untouched plans go first
        keep = sorted(data["plans"].items(), key=lambda kv: -float(kv[1].get("lastActiveAt") or 0))[:MAX_PLANS]
        data["plans"] = dict(keep)
    _write_atomic(_path(), data)


def playlist_key(playlist_id: str) -> str:
    return "yt-" + playlist_id


def _lessons(rec: dict) -> list[dict]:
    """The plan's lessons: a catalog plan's from the catalog (so a catalog update shows), a playlist's from the record."""
    if rec.get("kind") == "catalog":
        plan = catalog.get(rec.get("planId"))
        return plan["lessons"] if plan else []
    return [le for le in rec.get("lessons") or [] if isinstance(le, dict)]


def _ints(v: Any, n: int) -> list[int]:
    return sorted({i for i in v if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < n}) if isinstance(v, list) else []


# ------------------------------------------------------------------------------------------------ starting a plan


def start_catalog(plan_id: str, *, goal: str | None = None) -> dict:
    """Add a catalog plan (or touch it when already added) and make it the active plan. Returns its view.
    Raises KeyError for an id that is not in the catalog."""
    plan = catalog.get(plan_id)
    if plan is None:
        raise KeyError(plan_id)
    with _lock:
        data = _load()
        now = time.time()
        rec = data["plans"].get(plan_id) or {"key": plan_id, "kind": "catalog", "planId": plan_id, "done": [],
                                             "started": {}, "current": None, "startedAt": now}
        rec["title"] = plan["title"]
        if goal:
            rec["goal"] = goal[:300]
        rec["lastActiveAt"] = now
        data["plans"][plan_id] = rec
        data["active"] = plan_id
        _save(data)
        return _view(rec, data)


def start_playlist(pl: dict) -> dict:
    """Add a playlist (from playlist.list_videos) as a plan; one lesson per video. Re-adding it keeps what is done and
    takes the playlist's current videos (done marks follow their video, not their position)."""
    from .playlist import lessons_from

    key = playlist_key(pl["playlistId"])
    with _lock:
        data = _load()
        now = time.time()
        old = data["plans"].get(key)
        lessons = lessons_from(pl)
        rec = {"key": key, "kind": "playlist", "playlistId": pl["playlistId"], "title": pl.get("title") or "Playlist",
               "channel": pl.get("channel") or "", "url": pl.get("url"), "lessons": lessons, "done": [], "started": {},
               "current": None, "startedAt": now}
        if old:
            by_vid = {le.get("videoId"): i for i, le in enumerate(lessons)}
            old_lessons = old.get("lessons") or []

            def moved(i: Any) -> int | None:
                if isinstance(i, int) and 0 <= i < len(old_lessons):
                    return by_vid.get(old_lessons[i].get("videoId"))
                return None

            rec["done"] = sorted({j for j in (moved(i) for i in old.get("done") or []) if j is not None})
            rec["started"] = {str(j): v for k, v in (old.get("started") or {}).items()
                              if (j := moved(_int_key(k))) is not None}
            rec["current"] = moved(old.get("current"))
            rec["startedAt"] = old.get("startedAt") or now
        rec["lastActiveAt"] = now
        data["plans"][key] = rec
        data["active"] = key
        _save(data)
        return _view(rec, data)


def _int_key(k: Any) -> int | None:
    try:
        return int(k)
    except (TypeError, ValueError):
        return None


def remove(key: str) -> bool:
    with _lock:
        data = _load()
        if key not in data["plans"]:
            return False
        del data["plans"][key]
        if data["active"] == key:
            data["active"] = None
        _save(data)
        return True


# ------------------------------------------------------------------------------------------------ lessons


def lesson_spec(key: str, index: int | None = None) -> dict | None:
    """What to start for a plan lesson: {key, index, title, query} (a catalog lesson: learn {query: goal, mode: lesson})
    or {key, index, title, url} (a video). index None: the next lesson. None: no such plan / lesson, or all done."""
    with _lock:
        data = _load()
        rec = data["plans"].get(key)
        if rec is None:
            return None
        lessons = _lessons(rec)
        if index is None:
            index = _next_index(rec, len(lessons))
        if index is None or not isinstance(index, int) or not 0 <= index < len(lessons):
            return None
        le = lessons[index]
        spec = {"key": key, "index": index, "title": le.get("title") or f"Lesson {index + 1}"}
        if rec["kind"] == "catalog":
            spec["query"] = le["goal"]
        else:
            spec["url"] = le["url"]
        return spec


def lesson_starting(key: str, index: int) -> dict | None:
    """The learner started plan lesson `index`: it becomes current and the active plan. Returns the plan's view."""
    with _lock:
        data = _load()
        rec = data["plans"].get(key)
        if rec is None or not 0 <= index < len(_lessons(rec)):
            return None
        now = time.time()
        rec.setdefault("started", {})[str(index)] = {"at": now}
        rec["current"] = index
        rec["lastActiveAt"] = now
        data["active"] = key
        _save(data)
        return _view(rec, data)


def link_lesson(key: str, index: int, lesson_id: str) -> bool:
    """The engine lesson plan lesson `index` became (the engine knows it when the lesson loads)."""
    if not isinstance(lesson_id, str) or not lesson_id:
        return False
    with _lock:
        data = _load()
        rec = data["plans"].get(key)
        if rec is None:
            return False
        ent = rec.setdefault("started", {}).setdefault(str(index), {"at": time.time()})
        ent["lessonId"] = lesson_id
        _save(data)
        return True


def mark_done(key: str, index: int, done: bool = True) -> dict | None:
    """Mark a plan lesson done (or not): the learner's own "I did this" on the plan page."""
    with _lock:
        data = _load()
        rec = data["plans"].get(key)
        if rec is None or not 0 <= index < len(_lessons(rec)):
            return None
        s = set(rec.get("done") or [])
        (s.add if done else s.discard)(index)
        rec["done"] = sorted(s)
        rec["lastActiveAt"] = time.time()
        _save(data)
        return _view(rec, data)


def _next_index(rec: dict, n: int) -> int | None:
    done = set(_ints(rec.get("done"), n))
    cur = rec.get("current")
    if isinstance(cur, int) and 0 <= cur < n and cur not in done:
        return cur
    return next((i for i in range(n) if i not in done), None)


# ------------------------------------------------------------------------------------------------ reconcile


def _norm(s: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", s.lower())) if isinstance(s, str) else ""


def _reconcile(rec: dict, history: list[dict], current: dict | None, linked: set[str]) -> bool:
    """Link started plan lessons to engine lessons and mark finished ones done. True when the record changed."""
    lessons = _lessons(rec)
    started = rec.get("started") if isinstance(rec.get("started"), dict) else {}
    done = set(_ints(rec.get("done"), len(lessons)))
    changed = False
    by_id = {e["lessonId"]: e for e in history}
    for k, ent in sorted(started.items(), key=lambda kv: float((kv[1] or {}).get("at") or 0)):
        i = _int_key(k)
        if i is None or not 0 <= i < len(lessons) or not isinstance(ent, dict):
            continue
        at = float(ent.get("at") or 0)
        le = lessons[i]
        lid = ent.get("lessonId")
        if not lid and isinstance(current, dict) and isinstance(current.get("lessonId"), str) \
                and current["lessonId"] not in linked:
            c_at = float(current.get("startedAt") or 0)
            vid = le.get("videoId")
            if vid and vid in str(current.get("sourceUrl") or "") and c_at >= at - 1 \
                    or not vid and at - 1 <= c_at <= at + LINK_WINDOW_S and _is_latest_start(started, at, c_at):
                lid = ent["lessonId"] = current["lessonId"]
                linked.add(lid)
                changed = True
        if not lid and i not in done:
            goal = _norm(le.get("goal") or le.get("title"))
            for e in history:
                if float(e.get("finishedAt") or 0) >= at and e["lessonId"] not in linked and goal and \
                        any(_norm(c) == goal for c in [e.get("title")] + list(e.get("covered") or [])):
                    lid = ent["lessonId"] = e["lessonId"]
                    linked.add(lid)
                    changed = True
                    break
        if lid and lid in by_id and i not in done:
            done.add(i)
            changed = True
    if changed:
        rec["done"] = sorted(done)
    return changed


def _is_latest_start(started: dict, at: float, c_at: float) -> bool:
    """No other plan lesson was asked for between this one and the lesson's start (that lesson would be the one)."""
    return not any(at < float((e or {}).get("at") or 0) <= c_at for e in started.values() if isinstance(e, dict))


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


def _view(rec: dict, data: dict, current: dict | None = None) -> dict:
    lessons = _lessons(rec)
    n = len(lessons)
    done = set(_ints(rec.get("done"), n))
    nxt = _next_index(rec, n)
    started = rec.get("started") if isinstance(rec.get("started"), dict) else {}
    rows = []
    for i, le in enumerate(lessons):
        row = {"index": i, "title": le.get("title") or f"Lesson {i + 1}", "minutes": le.get("minutes"),
               "state": "done" if i in done else "current" if i == nxt and str(i) in started else "todo"}
        if le.get("videoId"):
            row["videoId"] = le["videoId"]
        if le.get("seconds") is not None:
            row["seconds"] = le["seconds"]
        rows.append(row)
    out = {"key": rec["key"], "kind": rec["kind"], "title": rec.get("title") or "", "lessons": rows,
           "done": len(done), "total": n, "complete": n > 0 and len(done) == n,
           "next": None if nxt is None else {"index": nxt, "title": rows[nxt]["title"]},
           "active": data.get("active") == rec["key"],
           "startedAt": rec.get("startedAt"), "lastActiveAt": rec.get("lastActiveAt")}
    for k in ("planId", "playlistId", "channel", "url", "goal"):
        if rec.get(k):
            out[k] = rec[k]
    minutes = [r["minutes"] for i, r in enumerate(rows) if i not in done and isinstance(r["minutes"], int)]
    out["minutesLeft"] = sum(minutes) if minutes else 0
    # the lesson running now, when it is this plan's current lesson: its step count (the plan page's "3 of 7")
    if nxt is not None and isinstance(current, dict):
        lid = (started.get(str(nxt)) or {}).get("lessonId")
        if lid and current.get("lessonId") == lid:
            out["next"]["steps"] = {"passed": len(current.get("passedSteps") or []), "total": current.get("stepCount")}
    return out


def view(key: str) -> dict | None:
    with _lock:
        data = _load()
        if key not in data["plans"]:
            return None
        if _sync(data):
            _save(data)
        return _view(data["plans"][key], data, store.load())


def all_views() -> list[dict]:
    """Every plan in progress, the most recently used first."""
    with _lock:
        data = _load()
        if _sync(data):
            _save(data)
        cur = store.load()
        recs = sorted(data["plans"].values(), key=lambda r: -float(r.get("lastActiveAt") or 0))
        return [_view(r, data, cur) for r in recs]


def resume() -> dict | None:
    """The active plan (else the most recent unfinished one) with its next lesson; None when there is none."""
    views = all_views()
    active = next((v for v in views if v["active"] and not v["complete"]), None)
    return active or next((v for v in views if not v["complete"]), None)


def done_plan_ids() -> set[str]:
    """Catalog plans finished on this Mac (goal matching skips their `needs`)."""
    return {v["planId"] for v in all_views() if v["kind"] == "catalog" and v["complete"] and v.get("planId")}
