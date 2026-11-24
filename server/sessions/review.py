"""Spaced review: which mastered skills are due for a quick check, and when the next ones come up.

    review.items(history, state, now, tz)   -> [ReviewItem]     (pure: due first, then upcoming)
    review.payload(now=None)                -> {"items": [...], "due": n} | None   (reads ~/miyagi/state; additive `review` of progress)
    review.record_result(key, passed, ...)  -> the skill's new schedule entry      (a review step passed / was missed)
    review.review_graph(graph, label, ...)  -> a one-lesson step graph for "Start review" (pure: no model call)

Leitner boxes, intervals in days: 1, 3, 7, 14, 30 (INTERVALS). A skill enters box 0 when a finished lesson's skill map
first shows it mastered, due one day after that lesson finished. Passing its review moves it up a box (the last box
repeats at 30 days); a failed check (a review step skipped or missed) sends it back to box 0, due the next day. A
review is due from the start of its local day, so "Due today" and the due count agree whatever time it is.

Where it comes from (all on this Mac): history.json (store.completed(): every entry's skillMap says which skills were
mastered and when the lesson finished) and review.json (this module's own record of the reviews taken: box, last
result, last time). mastery.json lists phrases practised per step, never skills, so it does not drive the schedule.
Nothing is invented: a skill with no mastered skill map is never scheduled, and a skill nobody reviewed keeps box 0.

Everything that reads the time takes `now` (epoch seconds) and `tz` so tests are deterministic. No model call, no
network. Wire shape (progress.review, additive; both the dashboard's and the reminder's readers accept it):
    {"due": 2, "items": [{"skillId", "label", "track", "dueAt" (epoch s), "when" ("Today", "Tomorrow", "Friday", "Dec 3"),
                          "interval" (days), "checks": 1, "lastResult"?, "lastAt"?}]}
"""

from __future__ import annotations

import copy
import logging
import re
import time
from datetime import datetime, time as dtime, timedelta, tzinfo
from typing import Any

from . import store

log = logging.getLogger("sessions")

INTERVALS = (1, 3, 7, 14, 30)  # days; box i waits INTERVALS[i] after its last review (or the lesson's finish)
MAX_ITEMS = 50
MAX_SKILLS = 500
_BOXES = len(INTERVALS)


def _path():
    return store.state_dir() / "review.json"


def skill_key(track: str, label: str) -> str:
    """One scheduled skill: its track and label, case-insensitive (the same merge rule as progress.tracks)."""
    return f"{' '.join(str(track).split()).lower()}::{' '.join(str(label).split()).lower()}"


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def _due_at(base: float, days: int, tz: tzinfo | None) -> float:
    """The start of the local day `days` calendar days after `base`'s day (a DST change never moves it)."""
    day = datetime.fromtimestamp(base, tz).date() + timedelta(days=days)
    return datetime.combine(day, dtime.min, tzinfo=tz).timestamp()


# ------------------------------------------------------------------------------------------------ what was mastered
def mastered_skills(history: list[dict]) -> dict[str, dict]:
    """key -> {track, label, skillId, lessonId, masteredAt} from the finished lessons' skill maps (oldest first).
    masteredAt is the first finish that showed the skill mastered; lessonId the latest one that did (its steps are
    what a review replays). A map without a finish time is skipped: it cannot be scheduled honestly."""
    out: dict[str, dict] = {}
    for e in history or []:
        if not isinstance(e, dict):
            continue
        m = e.get("skillMap")
        at = _num(e.get("finishedAt"))
        track = " ".join(str(m.get("track") or "").split()) if isinstance(m, dict) else ""
        if not track or at is None:
            continue
        for n in m.get("nodes") or []:
            if not isinstance(n, dict) or n.get("state") != "mastered":
                continue
            label = " ".join(str(n.get("label") or "").split())
            if not label:
                continue
            k = skill_key(track, label)
            row = out.get(k)
            if row is None:
                if len(out) >= MAX_SKILLS:
                    continue
                out[k] = {"track": track, "label": label, "skillId": str(n.get("id") or "")[:80] or label.lower(),
                          "lessonId": e.get("lessonId"), "masteredAt": at}
            else:
                row["lessonId"] = e.get("lessonId") or row["lessonId"]
                row["skillId"] = str(n.get("id") or "")[:80] or row["skillId"]
    return out


def load_state() -> dict[str, dict]:
    """review.json: key -> {box, lastResult, lastAt, reps}. Unreadable or foreign content reads as empty."""
    data = store._read(_path())
    rows = data.get("skills") if isinstance(data, dict) else None
    out: dict[str, dict] = {}
    for k, v in (rows.items() if isinstance(rows, dict) else []):
        if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("box"), int) and 0 <= v["box"] < _BOXES:
            out[k] = {"box": v["box"], "lastResult": v.get("lastResult") if v.get("lastResult") in ("passed", "missed") else None,
                      "lastAt": _num(v.get("lastAt")), "reps": v["reps"] if isinstance(v.get("reps"), int) and v["reps"] >= 0 else 0}
    return out


def record_result(key: str, passed: bool, *, now: float | None = None) -> dict:
    """A review of the skill `key` ended: passed moves it up a box (the last box repeats), a miss resets it to box 0.
    Returns the new entry. Raises OSError only when review.json cannot be written (callers use record_result_safely)."""
    now = time.time() if now is None else float(now)
    state = load_state()
    old = state.get(key) or {"box": 0, "reps": 0}
    box = min(old["box"] + 1, _BOXES - 1) if passed else 0
    entry = {"box": box, "lastResult": "passed" if passed else "missed", "lastAt": now,
             "reps": old["reps"] + (1 if passed else 0)}
    state[key] = entry
    keep = dict(sorted(state.items(), key=lambda kv: kv[1].get("lastAt") or 0, reverse=True)[:MAX_SKILLS])
    store._write_atomic(_path(), {"version": 1, "skills": keep})
    return entry


def record_result_safely(key: str | None, passed: bool, *, now: float | None = None) -> None:
    try:
        if key and not key.startswith("skilltree::"):  # a catalog skill's review: server/skilltree/ledger.py schedules it
            record_result(key, passed, now=now)
    except Exception as e:  # noqa: BLE001 - remembering a review must never break the lesson
        log.warning("could not record the review: %s", e)


# ------------------------------------------------------------------------------------------------ the schedule
def when_word(due_at: float, now: float, tz: tzinfo | None = None) -> str:
    """"Today" (due now or overdue), "Tomorrow", a weekday within the week, else "Dec 3" (local calendar days)."""
    today = datetime.fromtimestamp(now, tz).date()
    day = datetime.fromtimestamp(due_at, tz).date()
    n = (day - today).days
    if n <= 0:
        return "Today"
    if n == 1:
        return "Tomorrow"
    if n < 7:
        return day.strftime("%A")
    return f"{day.strftime('%b')} {day.day}"


def items(history: list[dict], state: dict[str, dict] | None, now: float, tz: tzinfo | None = None) -> list[dict]:
    """Every mastered skill's review, due ones first (oldest due first), then upcoming by date. Pure."""
    state = state or {}
    rows = []
    for k, s in mastered_skills(history).items():
        st = state.get(k)
        if st and st.get("lastAt"):
            box, base = st["box"], st["lastAt"]
        else:
            box, base, st = 0, s["masteredAt"], None
        interval = INTERVALS[box]
        due = _due_at(base, interval, tz)
        row: dict[str, Any] = {"skillId": s["skillId"], "label": s["label"], "track": s["track"], "dueAt": round(due, 3),
                               "when": when_word(due, now, tz), "interval": interval, "checks": 1}
        if st and st.get("lastResult"):
            row["lastResult"], row["lastAt"] = st["lastResult"], round(st["lastAt"], 3)
        row["_key"], row["_lessonId"] = k, s["lessonId"]
        rows.append(row)
    rows.sort(key=lambda r: (r["dueAt"], r["label"].lower(), r["track"].lower()))
    return rows[:MAX_ITEMS]


def public(rows: list[dict], now: float) -> dict:
    """The wire shape: items without the private fields, and `due` = how many are due now."""
    return {"due": sum(1 for r in rows if r["dueAt"] <= now),
            "items": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]}


def payload(now: float | None = None, tz: tzinfo | None = None) -> dict | None:
    """progress.review from what is saved on this Mac. None when no skill has been mastered yet (nothing to review;
    the app shows its empty state) or the state folder cannot be read."""
    now = time.time() if now is None else float(now)
    try:
        rows = items(store.completed(), load_state(), now, tz)
    except Exception as e:  # noqa: BLE001
        log.warning("review: could not read the saved state: %s", e)
        return None
    return public(rows, now) if rows else None


def find(selector: dict, now: float | None = None, tz: tzinfo | None = None) -> dict | None:
    """The private row for a review.start {skillId?, label?}: the skill id or label (case-insensitive), the most overdue
    when it matches several; with neither, the first due one. None when nothing matches (or nothing is mastered)."""
    now = time.time() if now is None else float(now)
    rows = items(store.completed(), load_state(), now, tz)
    sid = str(selector.get("skillId") or "").strip().lower()
    label = " ".join(str(selector.get("label") or "").split()).lower()
    if not sid and not label:
        return next((r for r in rows if r["dueAt"] <= now), None)
    return next((r for r in rows if (sid and r["skillId"].lower() == sid) or (label and r["label"].lower() == label)), None)


# ------------------------------------------------------------------------------------------------ Start review
def steps_behind(graph: dict, label: str) -> list[str]:
    """The ids of the steps a skill-map node with this label rests on (case-insensitive): the steps whose passing it
    needs. Found with the skill map itself, no model: a node is mastered only when every step behind it passed, so a
    step is behind it when passing all the others is not enough. Empty when the graph has no such node."""
    from server.lesson import skillmap

    ids = [s["id"] for s in graph.get("steps") or [] if isinstance(s, dict) and s.get("id")]

    def mastered(passed: list[str]) -> bool:
        m = skillmap.skill_map(graph, {"passed": passed, "skipped": []})
        return any(n.get("state") == "mastered" and " ".join(str(n.get("label")).split()).lower() == label.lower()
                   for n in m.get("nodes") or [])

    if not ids or not mastered(ids):
        return []
    return [s for s in ids if not mastered([i for i in ids if i != s])]


def review_graph(graph: dict, label: str, key: str, *, skill_id: str = "") -> dict | None:
    """A step graph of just the steps behind `label`, to replay as a quick review (zero model calls). Its lesson id is
    its own (review-...) so it never overwrites the finished lesson; lesson.review marks it for the engine, which
    records the result here instead of in history. None when the lesson has no steps behind that skill."""
    steps = steps_behind(graph, label)
    if not steps:
        return None
    g = copy.deepcopy(graph)
    les = g.setdefault("lesson", {})
    base = str(les.get("id") or "lesson")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", label.lower()).strip("-")[:40] or "skill"
    les["id"] = f"review-{slug}-{base}"[:120]
    les["title"] = f"Review: {label}"[:200]
    les["goal"] = f"A quick check on {label}"
    les["mode"] = "lesson"
    les["review"] = {"key": key, "label": label, "skillId": skill_id}
    for k in ("nextTopics", "learnFirst", "prerequisites", "curated", "provisional", "complete"):
        les.pop(k, None)
    g["steps"] = [dict(s) for s in g.get("steps") or [] if isinstance(s, dict) and s.get("id") in steps]
    return g


def review_of(graph: dict | None) -> dict | None:
    """lesson.review of a review graph ({key, label, skillId}), else None."""
    r = ((graph or {}).get("lesson") or {}).get("review")
    return r if isinstance(r, dict) and isinstance(r.get("key"), str) else None
