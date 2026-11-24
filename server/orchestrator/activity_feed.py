"""The engine side of Activity and bon (server/sessions/activity.py): what counts, when it is saved, when it is pushed.

    feed = ActivityFeed(push)            # push(type_, payload) -> awaitable; the Engine passes hub.emit
    await feed.observe(session, type_, payload)   # every outgoing event (Engine._emit): step.passed, the complete card
    await feed.tick(session)             # ~1/s (Engine._tick_loop): active lesson time
    feed.snapshot()                      # activity.get's answer
    await feed.flush()                   # engine stop: save what is pending
    await feed.erase()                   # Delete my data

Minutes are active lesson time: a lesson is running (graph loaded, phase active, no "Continue?" card, not paused, an
app connected) and the learner did something in the last IDLE_S seconds (a key, a save, a run, an action, a screen
change: session.last_activity / inputs.seconds_since_key) or the lesson video is playing. A tick gap over MAX_TICK_S
(the Mac slept, the loop stalled) never counts.

Pushes (the `activity` event, the same payload as the snapshot): a counted pass, a milestone, a finished lesson, and
today's minutes going up by a whole minute (at most one a minute). Saves: at once after a pass / milestone, else at
most every SAVE_EVERY_S while minutes accrue, in a worker thread.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from server.sessions import activity as act

log = logging.getLogger("orchestrator.activity")

EVENT = "activity"
IDLE_S = 120.0
MAX_TICK_S = 5.0
SAVE_EVERY_S = 60.0


def lesson_running(s: Any) -> bool:
    if getattr(s, "graph", None) is None or getattr(s, "phase", None) != "active":
        return False
    if getattr(s, "awaiting_resume", False) or getattr(s, "paused", None) is not None:
        return False
    left = getattr(s, "app_left", None)
    return not (callable(left) and left())


def idle_for(s: Any) -> float:
    """Seconds since the learner last did anything the engine sees (0 while the lesson video plays)."""
    if getattr(s, "video_playing", False) and not getattr(s, "segment_done", False) \
            and not getattr(s, "lesson_mode", False):
        return 0.0
    best = float("inf")
    clock = getattr(s, "clock", None)
    last = getattr(s, "last_activity", None)
    if callable(clock) and isinstance(last, (int, float)):
        best = max(0.0, clock() - last)
    inputs = getattr(s, "inputs", None)
    since_key = getattr(inputs, "seconds_since_key", None)
    if callable(since_key):
        try:
            v = since_key()
        except Exception:  # noqa: BLE001 - an input probe never breaks the count
            v = None
        if isinstance(v, (int, float)):
            best = min(best, max(0.0, float(v)))
    return best


def step_key(lesson: dict, step_id: str) -> str:
    """The stable id of a step: <lessonId>:<stepId>, where a review's lesson is the lesson it replays."""
    review = lesson.get("review") if isinstance(lesson.get("review"), dict) else {}
    base = review.get("lessonId") or lesson.get("id") or ""
    return f"{base}:{step_id}" if base and step_id else ""


class ActivityFeed:
    def __init__(self, push: Callable[[str, dict], Awaitable[None]], *, wall: Callable[[], float] = time.time,
                 mono: Callable[[], float] = time.monotonic, data: act.Activity | None = None) -> None:
        self.push = push
        self.wall, self.mono = wall, mono
        self.a = data if data is not None else act.Activity.load()
        self._last_tick: float | None = None
        self._dirty = False
        self._saved_t = mono()
        self._pushed_minutes = self.a.minutes_on(act.day_of(wall()))
        self._skills: dict[tuple, dict[str, list[dict]]] = {}
        self._lock = asyncio.Lock()  # one write at a time, in order
        self._tasks: set[asyncio.Task] = set()

    def snapshot(self) -> dict:
        return self.a.snapshot(self.wall())

    # ------------------------------------------------------------------ events
    async def observe(self, s: Any, type_: str, payload: dict | None) -> None:
        p = payload or {}
        try:
            if type_ == "step.passed":
                changed = self._passed(s, p)
            elif type_ == "card" and isinstance(p.get("result"), dict):
                changed = self._finished(s, p)
            else:
                return
        except Exception:  # noqa: BLE001 - activity must never cost the lesson an event
            log.exception("activity: %s not recorded", type_)
            return
        if changed:
            self._save_soon()  # in the background: the event that triggered it is never held up by a disk write
            await self._push()

    def _passed(self, s: Any, p: dict) -> bool:
        step_id = p.get("stepId")
        if not isinstance(step_id, str) or p.get("skipped") or p.get("already"):
            return False
        graph = getattr(s, "graph", None) or {}
        lesson = graph.get("lesson") if isinstance(graph.get("lesson"), dict) else {}
        step = next((x for x in graph.get("steps") or [] if isinstance(x, dict) and x.get("id") == step_id), None)
        if step is None or step.get("provisional"):
            return False
        key = step_key(lesson, step_id)
        if not key:
            return False
        row = {"stepId": step_id, "lessonId": str(lesson.get("id") or "")[:120],
               "title": act._str(step.get("title")), "lessonTitle": act._str(lesson.get("title") or lesson.get("goal")),
               "skills": self._skills_of(graph).get(step_id, [])}
        if isinstance(lesson.get("review"), dict):
            row["review"] = True
        counted, marks = self.a.pass_step(key, row, self.wall())
        log.info("activity: step %s passed (%s; %d counted)", key, "new" if counted else "seen before", self.a.count)
        self._dirty = True
        return True  # the recent list changed even when the counter did not

    def _finished(self, s: Any, p: dict) -> bool:
        graph = getattr(s, "graph", None) or {}
        lesson = graph.get("lesson") if isinstance(graph.get("lesson"), dict) else {}
        if lesson.get("review"):
            return False  # a review is not a lesson finished
        res = p["result"]
        lid = res.get("lessonId") or lesson.get("id")
        if not isinstance(lid, str) or not lid:
            return False
        marks = self.a.finish_lesson(lid, act._str(res.get("title") or lesson.get("title")), self.wall())
        if marks:
            self._dirty = True
        return bool(marks)

    def _skills_of(self, graph: dict) -> dict[str, list[dict]]:
        """stepId -> [{id, label}]: the skills each step teaches (skillmap.node_steps; pure, cached per lesson)."""
        lesson = graph.get("lesson") or {}
        k = (lesson.get("id"), len(graph.get("steps") or []))
        if k not in self._skills:
            out: dict[str, list[dict]] = {}
            try:
                from server.lesson.skillmap import node_steps

                for t in node_steps(graph).get("taught") or []:
                    for sid in t.get("steps") or []:
                        out.setdefault(sid, []).append({"id": str(t["id"])[:80], "label": str(t["label"])[:80]})
            except Exception as e:  # noqa: BLE001 - tags are a nicety
                log.debug("activity: no skill tags: %s", e)
            if len(self._skills) > 8:
                self._skills.clear()
            self._skills[k] = out
        return self._skills[k]

    # ------------------------------------------------------------------ minutes
    async def tick(self, s: Any) -> None:
        now = self.mono()
        last, self._last_tick = self._last_tick, now
        if last is None:
            return
        dt = now - last
        if not (0 < dt <= MAX_TICK_S) or not lesson_running(s) or idle_for(s) > IDLE_S:
            return
        wall = self.wall()
        marks = self.a.add_seconds(dt, wall)
        self._dirty = True
        mins = self.a.minutes_on(act.day_of(wall))
        if marks:
            self._save_soon()
            await self._push()
            return
        if mins != self._pushed_minutes:
            await self._push()
        if now - self._saved_t >= SAVE_EVERY_S:
            self._save_soon()

    # ------------------------------------------------------------------ out
    async def _push(self) -> None:
        snap = self.snapshot()
        self._pushed_minutes = snap["today"]
        try:
            await self.push(EVENT, snap)
        except Exception:  # noqa: BLE001
            log.exception("activity push failed")

    async def _save_now(self) -> None:
        if not self._dirty:
            return
        self._dirty, self._saved_t = False, self.mono()
        data = self.a.to_json()
        async with self._lock:
            try:
                await asyncio.to_thread(act.Activity.write, data)
            except Exception as e:  # noqa: BLE001 - the next change saves again
                self._dirty = True
                log.warning("activity: save failed: %s", e)

    def _save_soon(self) -> None:
        task = asyncio.get_running_loop().create_task(self._save_now())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def flush(self) -> None:
        """Engine stop (and tests): wait for background saves, then save what is still pending."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
        await self._save_now()

    async def erase(self) -> None:
        """Delete my data: the counter, minutes and milestones go; the app gets the empty snapshot."""
        async with self._lock:
            await asyncio.to_thread(act.Activity.erase)
        self.a, self._dirty = act.Activity(), False
        self._pushed_minutes = 0
        await self._push()
