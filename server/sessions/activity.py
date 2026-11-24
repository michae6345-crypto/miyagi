"""Activity and bon: minutes per day, totals, dated milestones, the last passed steps, and the lifetime passed-step
counter bon (the buddy) grows from. One file on this Mac: <state_dir>/activity.json. Nothing here leaves the Mac.

    a = Activity.load()                     # reads activity.json (a missing or broken file starts empty)
    a.add_seconds(dt, now)                  # active lesson time (the caller has already left idle time out)
    a.pass_step(key, row, now)              # -> True when it counted (a key counts once, ever)
    a.finish_lesson(lesson_id, title, now)  # a finished lesson (once per lesson id)
    a.snapshot(now)                         # the app's payload (activity.get / the activity push)
    a.to_json() / a.save()                  # save() writes atomically (store._write_atomic)

The counter (Adrian, Nov 22: "store passed-step count in the engine, not localStorage; can step.passed repeat under a
different id?"): step ids are per lesson ("s1", "s2" ...), so the stable id of a step is `<lessonId>:<stepId>`.
step.passed can repeat for the same step in three ways, and each is counted once:
- a review (review.start) replays a finished lesson's steps under its own lesson id ("review-<skill>-<lessonId>"):
  the key uses the lesson it came from (lesson.review.lessonId, sessions/review.py), so a review pass is not new;
- the same lesson started again from the library (library.start keeps the cached lesson id): same keys, not new;
- the reconnect snapshot never replays step.passed, and one step passes once per run (session._pass_step guard).
A skipped step ({skipped: true}) and a step that was already in the file ({already: true}) are not passes. Rebuilding a
video lesson in another folder gives a new lesson id (builder.cache_key hashes the folder): those are new steps.

bon's levels are the app's (app features/buddy/growth.ts LEVELS, origin/michael/app-ui-v4): 0, 3, 8, 15, 25, 40, 60, 90.
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from typing import Any

from . import store

log = logging.getLogger("sessions.activity")

VERSION = 1
FILE = "activity.json"
DAYS_SHOWN = 84  # 12 weeks of minutes on the wire
DAYS_KEPT = 400  # per-day seconds kept on disk (totals are kept apart, so pruning never lowers them)
RECENT_MAX = 20
MILESTONES_MAX = 100
KEYS_MAX = 50_000  # every counted step id is remembered (a forgotten key could count again)
ACTIVE_DAY_S = 60  # a day counts as active from its first whole minute

# app features/buddy/growth.ts LEVELS: (name, steps)
LEVELS: tuple[tuple[str, int], ...] = (
    ("Seed", 0), ("Sprout", 3), ("Shoot", 8), ("Sapling", 15),
    ("Budding", 25), ("In bloom", 40), ("Young tree", 60), ("Bonsai", 90),
)
STEP_MARKS = (10, 50, 100, 250, 500, 1000)
HOUR_MARKS = (1, 10, 50, 100)


def level_for(steps: int) -> int:
    """bon's level (1..8) for this many passed steps."""
    level = 1
    for i, (_name, at) in enumerate(LEVELS):
        if steps >= at:
            level = i + 1
    return level


def bon(steps: int) -> dict:
    """{steps, level, name, next?: {level, name, at, left}, fraction}: what the growth card shows (growth.ts progressOf)."""
    n = max(0, int(steps))
    level = level_for(n)
    name, at = LEVELS[level - 1]
    out: dict[str, Any] = {"steps": n, "level": level, "name": name}
    if level < len(LEVELS):
        up_name, up_at = LEVELS[level]
        out["next"] = {"level": level + 1, "name": up_name, "at": up_at, "left": up_at - n}
        out["fraction"] = round((n - at) / (up_at - at), 4)
    else:
        out["fraction"] = 1.0
    return out


def day_of(now: float) -> str:
    """The learner's local calendar day of a wall-clock time."""
    return time.strftime("%Y-%m-%d", time.localtime(now))


def iso(now: float) -> str:
    return _dt.datetime.fromtimestamp(now, _dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def _list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _str(v: Any, n: int = 200) -> str | None:
    if not isinstance(v, str):
        return None
    t = " ".join(v.split())
    return t[:n] if t else None


class Activity:
    def __init__(self, data: dict | None = None) -> None:
        d = data if isinstance(data, dict) else {}
        days = d.get("days") if isinstance(d.get("days"), dict) else {}
        self.days: dict[str, float] = {k: float(v) for k, v in days.items()
                                       if isinstance(k, str) and len(k) == 10 and _num(v) is not None}
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
        path = store.state_dir() / FILE
        raw = store._read(path)
        if raw is not None and not isinstance(raw, dict):
            log.warning("activity.json is not an object; starting a new one")
            raw = None
        return cls(raw)

    def to_json(self) -> dict:
        return {"version": VERSION, "days": dict(self.days),
                "totals": {"seconds": round(self.total_s, 1), "activeDays": self.active_days},
                "count": self.count, "keys": list(self.keys), "recent": [dict(r) for r in self.recent],
                "milestones": [dict(m) for m in self.milestones], "lessons": list(self.lessons)}

    @staticmethod
    def write(data: dict) -> None:
        """Atomic write of to_json() output (call it in a thread: it fsyncs)."""
        store._write_atomic(store.state_dir() / FILE, data)

    def save(self) -> None:
        self.write(self.to_json())

    @staticmethod
    def erase() -> None:
        """Delete my data: the file goes (bon starts again from a seed)."""
        try:
            (store.state_dir() / FILE).unlink()
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------------ minutes
    def add_seconds(self, dt: float, now: float) -> list[dict]:
        """Active lesson time. Returns the milestones it reached (an hours mark)."""
        if isinstance(dt, bool) or not (isinstance(dt, (int, float)) and 0 < dt < 3600):
            return []
        day = day_of(now)
        before_day = self.days.get(day, 0.0)
        self.days[day] = before_day + dt
        if before_day < ACTIVE_DAY_S <= self.days[day]:
            self.active_days += 1
        hours_before = int(self.total_s // 3600)
        self.total_s += dt
        self._prune(now)
        got: list[dict] = []
        for h in HOUR_MARKS:
            if hours_before < h <= self.total_s / 3600:
                got += self._mark(f"hours:{h}", "hours", f"{h} hour{'s' if h > 1 else ''} of lessons", now, h)
        return got

    def minutes_on(self, day: str) -> int:
        return int(self.days.get(day, 0.0) // 60)

    def _prune(self, now: float) -> None:
        if len(self.days) <= DAYS_KEPT:
            return
        keep = sorted(self.days)[-DAYS_KEPT:]
        self.days = {k: self.days[k] for k in keep}

    # ------------------------------------------------------------------ steps
    def has(self, key: str) -> bool:
        return key in self._seen

    def pass_step(self, key: str, row: dict, now: float) -> tuple[bool, list[dict]]:
        """A passed step. (counted, milestones reached). A key counts once, ever; the recent row is added either way
        (a review pass is a pass the learner made today), but a repeat of the newest row is not added twice."""
        if not key:
            return False, []
        entry = {k: v for k, v in row.items() if v not in (None, [], "")}
        entry["at"] = iso(now)
        last = self.recent[-1] if self.recent else None
        if not (last and last.get("key") == key):
            self.recent.append({"key": key, **entry})
            self.recent = self.recent[-RECENT_MAX:]
        if key in self._seen:
            return False, []
        self._seen.add(key)
        self.keys.append(key)
        if len(self.keys) > KEYS_MAX:
            self._seen.discard(self.keys.pop(0))
        before = level_for(self.count)
        self.count += 1
        got: list[dict] = []
        if self.count == 1:
            got += self._mark("first_step", "first_step", "First step passed", now, 1)
        level = level_for(self.count)
        if level > before:
            name = LEVELS[level - 1][0]
            got += self._mark(f"level:{level}", "level", f"bon grew to {name}", now, level)
        if self.count in STEP_MARKS:
            got += self._mark(f"steps:{self.count}", "steps", f"{self.count} steps passed", now, self.count)
        return True, got

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
        now = time.time() if now is None else now
        today = _dt.date.fromisoformat(day_of(now))
        days = [(today - _dt.timedelta(days=i)).isoformat() for i in range(DAYS_SHOWN - 1, -1, -1)]
        return {
            "days": [{"date": d, "minutes": self.minutes_on(d)} for d in days],
            "today": self.minutes_on(days[-1]),
            "totals": {"minutes": int(self.total_s // 60), "passedSteps": self.count,
                       "lessonsCompleted": len(self.lessons), "activeDays": self.active_days},
            "milestones": [{k: m[k] for k in ("id", "kind", "label", "value", "at", "date") if k in m}
                           for m in reversed(self.milestones)],
            "recent": [{k: v for k, v in r.items() if k != "key"} for r in reversed(self.recent)],
            "bon": bon(self.count),
        }
