"""Activity and bon: minutes and passes per day, totals, dated milestones, the last counted passes, and the lifetime
passed-step counter bon (the buddy) grows from. One file on this Mac: <state_dir>/activity.json. Nothing here leaves the
Mac. The payloads are the ui-v4 contract's (shared/contracts/UI-V4.md sections 1 and 2: `activity`, `bon`).

    a = Activity.load()                     # reads activity.json (a missing or broken file starts empty)
    a.add_seconds(dt, now)                  # active lesson time (the caller has already left idle time out)
    a.pass_step(key, row, now)              # -> (counted, milestones): a key counts once, ever
    a.finish_lesson(lesson_id, title, now)  # a finished lesson (once per lesson id)
    a.import_count(steps, seen)             # bon.import: the app's old localStorage count, once per Mac
    a.snapshot(now)                         # the `activity` payload (activity.get / the activity push)
    bon(a.count)                            # the `bon` payload (events.bon_state)
    a.to_json() / a.save()                  # save() writes atomically (store._write_atomic)

The counter (Adrian, Nov 22: "store passed-step count in the engine, not localStorage; can step.passed repeat under a
different id?"): step ids are per lesson ("s1", "s2" ...), so the stable id of a step is `<lessonId>:<stepId>`
(step.passed.key). step.passed can repeat for the same step in three ways, and each is counted once:
- a review (review.start) replays a finished lesson's steps under its own lesson id ("review-<skill>-<lessonId>"):
  the key uses the lesson it came from (lesson.review.lessonId, sessions/review.py), so a review pass is not new;
- the same lesson started again from the library (library.start keeps the cached lesson id): same keys, not new;
- the reconnect snapshot never replays step.passed, and one step passes once per run (session._pass_step guard).
A skipped step ({skipped: true}) and a step that was already in the file ({already: true}) are not passes. Rebuilding a
video lesson in another folder gives a new lesson id (builder.cache_key hashes the folder): those are new steps.

Under pytest with no MIYAGI_STATE_DIR (a test that builds main.Engine() outside orchestrator/tests), the file is never
read or written: ~/miyagi/state/activity.json is the learner's (the build_metrics / fast_ask guard).
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import time
from typing import Any

from shared.contracts import events as _contract

from . import store

log = logging.getLogger("sessions.activity")

VERSION = 2
FILE = "activity.json"
DAYS_SHOWN = _contract.ACTIVITY_DAYS  # 84: 12 weeks on the wire, the last day is today
WEEK_DAYS = 7
DAYS_KEPT = 400  # per-day seconds / passes kept on disk (totals are kept apart, so pruning never lowers them)
RECENT_MAX = _contract.RECENT_PASSED_MAX  # 20
MILESTONES_MAX = 100
KEYS_MAX = 50_000  # every counted step id is remembered (a forgotten key could count again)
IMPORT_SEEN_MAX = 400  # bon.import.seen (contract max_length)
ACTIVE_DAY_S = 60  # a day counts as active from its first whole minute

# bon's levels: the contract's table (events.BON_LEVELS = app features/buddy/growth.ts LEVELS): (name, steps)
LEVELS: tuple[tuple[str, int], ...] = tuple((lv["name"], lv["at"]) for lv in _contract.BON_LEVELS)
STEP_MARKS = (10, 50, 100, 250, 500, 1000)
HOUR_MARKS = (1, 10, 50, 100)
WIRE_KINDS = frozenset({"first_step", "first_lesson", "steps"})  # the contract's MilestoneKind values this file makes


def disk_ok() -> bool:
    """False under pytest without MIYAGI_STATE_DIR: never touch the learner's real activity.json from a test."""
    return not (os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("MIYAGI_STATE_DIR"))


def level_for(steps: int) -> int:
    """bon's level (1..8) for this many passed steps."""
    level = 1
    for i, (_name, at) in enumerate(LEVELS):
        if steps >= at:
            level = i + 1
    return level


def bon(steps: int, *, grew: bool | None = None, last_key: str | None = None) -> dict:
    """The `bon` payload (BonState): {steps, level, name, next?, fraction, grew?, lastKey?}."""
    return _contract.bon_state(steps, grew=grew, last_key=last_key)


def day_of(now: float) -> str:
    """The learner's local calendar day of a wall-clock time."""
    return time.strftime("%Y-%m-%d", time.localtime(now))


def iso(now: float) -> str:
    """Stored times: UTC (the wire shows them with the learner's offset: local_iso)."""
    return _dt.datetime.fromtimestamp(now, _dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_iso(v: Any) -> str | None:
    """A stored time (UTC text or a timestamp) as ISO 8601 with the learner's UTC offset ("2026-11-22T16:12:00-08:00")."""
    try:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            t = _dt.datetime.fromtimestamp(v, _dt.timezone.utc)
        elif isinstance(v, str) and v:
            t = _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=_dt.timezone.utc)
        else:
            return None
        return t.astimezone().isoformat(timespec="seconds")
    except (ValueError, OverflowError, OSError):
        return None


def tz_name() -> str | None:
    """The learner's IANA zone ("America/Los_Angeles"), when this Mac says it; else None (the field is optional)."""
    env = os.environ.get("TZ") or ""
    if "/" in env and not env.startswith((":", "/")):
        return env[:64]
    try:
        target = os.readlink("/etc/localtime")
    except OSError:
        return None
    _, sep, name = target.partition("zoneinfo/")
    return name[:64] if sep and name else None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def _list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _str(v: Any, n: int = 200) -> str | None:
    if not isinstance(v, str):
        return None
    t = " ".join(v.split())
    return t[:n] if t else None


def _day_map(v: Any, cast: type) -> dict:
    d = v if isinstance(v, dict) else {}
    return {k: cast(x) for k, x in d.items() if isinstance(k, str) and len(k) == 10 and _num(x) is not None}


class Activity:
    def __init__(self, data: dict | None = None) -> None:
        d = data if isinstance(data, dict) else {}
        self.days: dict[str, float] = _day_map(d.get("days"), float)
        self.day_steps: dict[str, int] = _day_map(d.get("daySteps"), int)
        t = d.get("totals") if isinstance(d.get("totals"), dict) else {}
        self.total_s = _num(t.get("seconds")) or 0.0
        self.active_days = int(_num(t.get("activeDays")) or 0)
        keys = d.get("keys") if isinstance(d.get("keys"), list) else []
        self.keys: list[str] = [k for k in keys if isinstance(k, str)][-KEYS_MAX:]
        self._seen = set(self.keys)
        self.count = max(int(_num(d.get("count")) or 0), len(self.keys))
        self.recent: list[dict] = [r for r in _list(d.get("recent")) if isinstance(r, dict)][-RECENT_MAX:]
        self.milestones: list[dict] = [m for m in _list(d.get("milestones")) if isinstance(m, dict)][-MILESTONES_MAX:]
        lessons = d.get("lessons") if isinstance(d.get("lessons"), list) else []
        self.lessons: list[str] = [x for x in lessons if isinstance(x, str)]
        self._marks = {m.get("id") for m in self.milestones}

    # ------------------------------------------------------------------ disk
    @classmethod
    def load(cls) -> "Activity":
        if not disk_ok():
            return cls()
        path = store.state_dir() / FILE
        raw = store._read(path)
        if raw is not None and not isinstance(raw, dict):
            log.warning("activity.json is not an object; starting a new one")
            raw = None
        return cls(raw)

    def to_json(self) -> dict:
        return {"version": VERSION, "days": dict(self.days), "daySteps": dict(self.day_steps),
                "totals": {"seconds": round(self.total_s, 1), "activeDays": self.active_days},
                "count": self.count, "keys": list(self.keys), "recent": [dict(r) for r in self.recent],
                "milestones": [dict(m) for m in self.milestones], "lessons": list(self.lessons)}

    @staticmethod
    def write(data: dict) -> None:
        """Atomic write of to_json() output (call it in a thread: it fsyncs)."""
        if disk_ok():
            store._write_atomic(store.state_dir() / FILE, data)

    def save(self) -> None:
        self.write(self.to_json())

    @staticmethod
    def erase() -> None:
        """Delete my data: the file goes (bon starts again from a seed)."""
        if not disk_ok():
            return
        try:
            (store.state_dir() / FILE).unlink()
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------------ minutes
    def add_seconds(self, dt: float, now: float) -> list[dict]:
        """Active lesson time. Returns the milestones it reached (an hours mark, kept on disk only)."""
        if isinstance(dt, bool) or not (isinstance(dt, (int, float)) and 0 < dt < 3600):
            return []
        day = day_of(now)
        before_day = self.days.get(day, 0.0)
        self.days[day] = before_day + dt
        if before_day < ACTIVE_DAY_S <= self.days[day]:
            self.active_days += 1
        hours_before = int(self.total_s // 3600)
        self.total_s += dt
        self._prune()
        got: list[dict] = []
        for h in HOUR_MARKS:
            if hours_before < h <= self.total_s / 3600:
                got += self._mark(f"hours:{h}", "hours", f"{h} hour{'s' if h > 1 else ''} of lessons", now, h)
        return got

    def minutes_on(self, day: str) -> int:
        return int(self.days.get(day, 0.0) // 60)

    def _prune(self) -> None:
        for name in ("days", "day_steps"):
            m = getattr(self, name)
            if len(m) > DAYS_KEPT:
                setattr(self, name, {k: m[k] for k in sorted(m)[-DAYS_KEPT:]})

    # ------------------------------------------------------------------ steps
    def has(self, key: str) -> bool:
        return key in self._seen

    def pass_step(self, key: str, row: dict, now: float) -> tuple[bool, list[dict]]:
        """A passed step. (counted, milestones reached). A key counts once, ever; only a counted pass joins `recent`
        (contract: each recent row is a counted pass). row: lessonId, lessonTitle, stepId, stepTitle, skillIds, skills,
        assisted, review."""
        if not key or key in self._seen:
            return False, []
        self._seen.add(key)
        self.keys.append(key)
        if len(self.keys) > KEYS_MAX:
            self._seen.discard(self.keys.pop(0))
        entry = {k: v for k, v in row.items() if v not in (None, [], "")}
        self.recent.append({**entry, "key": key, "at": iso(now)})
        self.recent = self.recent[-RECENT_MAX:]
        day = day_of(now)
        self.day_steps[day] = self.day_steps.get(day, 0) + 1
        self._prune()
        before = level_for(self.count)
        self.count += 1
        got: list[dict] = []
        if self.count == 1:
            got += self._mark("first_step", "first_step", "First step passed", now, 1)
        level = level_for(self.count)
        if level > before:
            got += self._mark(f"level:{level}", "level", f"bon grew to {LEVELS[level - 1][0]}", now, level)
        if self.count in STEP_MARKS:
            got += self._mark(f"steps:{self.count}", "steps", f"{self.count} steps passed", now, self.count)
        return True, got

    def import_count(self, steps: Any, seen: Any) -> bool:
        """bon.import: keep the larger count and remember the app's counted keys (at most IMPORT_SEEN_MAX). True when it
        changed anything."""
        n = int(_num(steps) or 0)
        added = 0
        for k in _list(seen)[:IMPORT_SEEN_MAX]:
            if isinstance(k, str) and 0 < len(k) <= 200 and k not in self._seen:
                self._seen.add(k)
                self.keys.append(k)
                added += 1
        if len(self.keys) > KEYS_MAX:
            for k in self.keys[:-KEYS_MAX]:
                self._seen.discard(k)
            self.keys = self.keys[-KEYS_MAX:]
        before = self.count
        self.count = max(self.count, n, len(self.keys))
        return added > 0 or self.count != before

    def finish_lesson(self, lesson_id: str, title: str | None, now: float) -> list[dict]:
        if not lesson_id or lesson_id in self.lessons:
            return []
        self.lessons.append(lesson_id)
        got = self._mark(f"lesson:{lesson_id}", "lesson", f"Finished {title or 'a lesson'}", now, len(self.lessons))
        if len(self.lessons) == 1:
            got += self._mark("first_lesson", "first_lesson", "First lesson finished", now, 1)
        return got

    def _mark(self, mid: str, kind: str, label: str, now: float, value: int) -> list[dict]:
        if mid in self._marks:
            return []
        self._marks.add(mid)
        m = {"id": mid[:160], "kind": kind, "label": label[:200], "value": value, "at": iso(now), "date": day_of(now)}
        self.milestones.append(m)
        self.milestones = self.milestones[-MILESTONES_MAX:]
        return [m]

    # ------------------------------------------------------------------ the payload
    def snapshot(self, now: float | None = None) -> dict:
        """The contract's Activity payload (UI-V4.md section 1). skillsMastered is the skills lane's: 0 / left out here."""
        now = time.time() if now is None else now
        today = _dt.date.fromisoformat(day_of(now))
        dates = [(today - _dt.timedelta(days=i)).isoformat() for i in range(DAYS_SHOWN - 1, -1, -1)]
        days = [{"date": d, "minutes": self.minutes_on(d), "steps": self.day_steps.get(d, 0)} for d in dates]
        week = days[-WEEK_DAYS:]
        out: dict[str, Any] = {
            "asOf": local_iso(now), "minutesTracked": True, "days": days,
            "week": {"minutes": int(sum(self.days.get(d["date"], 0.0) for d in week) // 60),
                     "stepsPassed": sum(d["steps"] for d in week), "skillsMastered": 0},
            "totals": {"lessonsFinished": len(self.lessons), "stepsPassed": self.count, "minutes": int(self.total_s // 60)},
            "recent": [r for r in (self._recent_row(r) for r in reversed(self.recent)) if r is not None],
            "milestones": [m for m in (self._milestone_row(m) for m in reversed(self.milestones)) if m is not None],
        }
        if tz := tz_name():
            out["tz"] = tz
        return out

    @staticmethod
    def _recent_row(r: dict) -> dict | None:
        key, at = r.get("key"), local_iso(r.get("at"))
        if not isinstance(key, str) or not at:
            return None
        lesson_id, _, step_id = key.rpartition(":")
        out: dict[str, Any] = {"key": key, "lessonId": _str(r.get("lessonId"), 120) or lesson_id,
                               "lessonTitle": _str(r.get("lessonTitle")) or "A lesson",
                               "stepId": _str(r.get("stepId"), 80) or step_id,
                               "stepTitle": _str(r.get("stepTitle") or r.get("title")) or "A step", "at": at}
        ids = [x for x in _list(r.get("skillIds")) if isinstance(x, str)]
        labels = [x for x in _list(r.get("skills")) if isinstance(x, str)]
        if ids:
            out["skillIds"] = ids
            if len(labels) == len(ids):
                out["skills"] = labels
        if r.get("assisted") is True:
            out["assisted"] = True
        return out

    @staticmethod
    def _milestone_row(m: dict) -> dict | None:
        at = local_iso(m.get("at"))
        if m.get("kind") not in WIRE_KINDS or not at or not isinstance(m.get("id"), str):
            return None
        out: dict[str, Any] = {"id": m["id"], "kind": m["kind"], "title": _str(m.get("label")) or m["id"], "at": at}
        if m["kind"] == "steps" and isinstance(m.get("value"), int):
            out["count"] = m["value"]
        return out
