"""The engine side of Activity and bon (server/sessions/activity.py): what counts, when it is saved, when it is pushed.

    feed = ActivityFeed(push)            # push(type_, payload) -> awaitable; the Engine passes hub.emit
    payload = feed.annotate(session, type_, payload)   # Engine._emit, before step.passed goes out: key / counted / ...
    await feed.observe(session, type_, payload)        # after it went out: step.passed, the complete card
    await feed.tick(session)             # ~1/s (Engine._tick_loop): active lesson time
    feed.get() / feed.bon()              # activity.get's / bon.get's answer
    await feed.import_bon(steps, seen)   # bon.import
    await feed.flush()                   # engine stop: save what is pending
    await feed.erase()                   # Delete my data

Minutes are active lesson time: a lesson is running (graph loaded, phase active, no "Continue?" card, not paused, an
app connected) and the learner did something in the last IDLE_S seconds (a key, a save, a run, an action, a screen
change: session.last_activity / inputs.seconds_since_key) or the lesson video is playing. A tick gap over MAX_TICK_S
(the Mac slept, the loop stalled) never counts.

The wire is the ui-v4 contract's (shared/contracts/UI-V4.md sections 1 and 2):
- step.passed gets `key` ("<lessonId>:<stepId>"), `counted`, `assisted` and `skillIds` (annotate(), before it goes out);
- `bon` is pushed after every counted pass (`grew` on the pass that crossed a level), and after Delete my data;
- `activity` is pushed on a change (a counted pass, a finished lesson, today's minutes going up by a whole minute), at
  most one every PUSH_EVERY_S, and only once an app has asked (activity.get).
Saves: at once after a pass / milestone, else at most every SAVE_EVERY_S while minutes accrue, in a worker thread. An
erase bumps a generation number: a save snapshotted before it is dropped, so Delete my data is never undone.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from server.sessions import activity as act

log = logging.getLogger("orchestrator.activity")

EVENT = "activity"
BON = "bon"
PUSH_EVERY_S = 10.0  # contract: an activity push at most every 10 s
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


def base_lesson(lesson: dict) -> str:
    """The lesson a step belongs to: a review's is the lesson it replays."""
    review = lesson.get("review") if isinstance(lesson.get("review"), dict) else {}
    return str(review.get("lessonId") or lesson.get("id") or "")


def step_key(lesson: dict, step_id: str) -> str:
    """The stable id of a step (step.passed.key): <lessonId>:<stepId>, where a review's lesson is the lesson it replays."""
    base = base_lesson(lesson)
    return f"{base}:{step_id}" if base and step_id else ""


class ActivityFeed:
    def __init__(self, push: Callable[[str, dict], Awaitable[None]], *, wall: Callable[[], float] = time.time,
                 mono: Callable[[], float] = time.monotonic, data: act.Activity | None = None,
                 sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep) -> None:
        self.push = push
        self.wall, self.mono, self.sleep = wall, mono, sleep
        self.a = data if data is not None else act.Activity.load()
        self.asked = False  # an app sent activity.get: `activity` pushes go out from now on
        self._last_tick: float | None = None
        self._dirty = False
        self._gen = 0  # bumped by erase(): a save snapshotted under an older generation is dropped
        self._saved_t = mono()
        self._pushed_t = float("-inf")
        self._push_later: asyncio.Task | None = None
        self._pushed_minutes = self.a.minutes_on(act.day_of(wall()))
        self._skills: dict[tuple, dict[str, list[tuple[str, str]]]] = {}
        self._lock = asyncio.Lock()  # one write at a time, in order
        self._tasks: set[asyncio.Task] = set()
        self._bon_out: dict | None = None  # the bon push owed by the last counted pass

    def snapshot(self) -> dict:
        return self.a.snapshot(self.wall())

    def bon(self) -> dict:
        return act.bon(self.a.count)

    def get(self) -> dict:
        """activity.get: the snapshot; `activity` pushes go out from now on."""
        self.asked = True
        self._pushed_t = self.mono()  # the answer counts as a push: the next one waits PUSH_EVERY_S
        self._pushed_minutes = self.a.minutes_on(act.day_of(self.wall()))
        return self.snapshot()

    async def import_bon(self, steps: Any, seen: Any) -> dict:
        """bon.import: the app's localStorage count, once per Mac. The answer is `bon`."""
        if self.a.import_count(steps, seen):
            self._dirty = True
            self._save_soon()
            await self._push()
        return self.bon()

    # ------------------------------------------------------------------ events
    def annotate(self, s: Any, type_: str, payload: dict | None) -> dict | None:
        """Before step.passed goes out: count it and add key / counted / assisted / skillIds. Never raises."""
        if type_ != "step.passed" or not isinstance(payload, dict):
            return payload
        try:
            extra = self._passed(s, payload)
        except Exception:  # noqa: BLE001 - activity must never cost the lesson an event
            log.exception("activity: step.passed not recorded")
            return payload
        if not extra:
            return payload
        out = {**payload, **extra}
        # the skill tree (skill_hooks.on_pass) already set the catalog skillIds (the SkillInfo ids) and its own assist
        # rule: keep its ids, and a pass either side calls assisted stays assisted
        if payload.get("skillIds"):
            out["skillIds"] = payload["skillIds"]
        if payload.get("assisted") is not None or "assisted" in extra:
            out["assisted"] = bool(payload.get("assisted")) or bool(extra.get("assisted"))
        return out

    async def observe(self, s: Any, type_: str, payload: dict | None) -> None:
        """After an event went out: the saves and pushes it owes (a counted pass, a finished lesson)."""
        p = payload or {}
        try:
            if type_ == "step.passed":
                if "key" not in p:  # not annotated (a direct caller): count it now
                    self._passed(s, p)
                out, self._bon_out = self._bon_out, None
                changed = out is not None
            elif type_ == "card" and isinstance(p.get("result"), dict):
                out, changed = None, self._finished(s, p)
            else:
                return
        except Exception:  # noqa: BLE001
            log.exception("activity: %s not recorded", type_)
            return
        if changed:
            self._save_soon()  # in the background: the event that triggered it is never held up by a disk write
            if out is not None:
                await self._send(BON, out)
            await self._push()

    def _passed(self, s: Any, p: dict) -> dict:
        """Count a pass. Returns the step.passed fields to add ({} when it is not a step of the running lesson)."""
        step_id = p.get("stepId")
        if not isinstance(step_id, str):
            return {}
        graph = getattr(s, "graph", None) or {}
        lesson = graph.get("lesson") if isinstance(graph.get("lesson"), dict) else {}
        step = next((x for x in graph.get("steps") or [] if isinstance(x, dict) and x.get("id") == step_id), None)
        key = step_key(lesson, step_id)
        if step is None or step.get("provisional") or not key:
            return {}
        skills = self._skills_of(graph).get(step_id, [])
        extra: dict[str, Any] = {"key": key, "counted": False}
        if skills:
            extra["skillIds"] = [i for i, _ in skills]
        assisted = step_id in (getattr(s, "assisted_steps", None) or ())
        if assisted:
            extra["assisted"] = True
        if p.get("skipped") or p.get("already"):
            return extra
        row = {"lessonId": base_lesson(lesson)[:120], "stepId": step_id, "stepTitle": act._str(step.get("title")),
               "lessonTitle": act._str(lesson.get("title") or lesson.get("goal")),
               "skillIds": extra.get("skillIds"), "skills": [lb for _, lb in skills] or None,
               "assisted": True if assisted else None}
        before = act.level_for(self.a.count)
        counted, _marks = self.a.pass_step(key, row, self.wall())
        log.info("activity: step %s passed (%s; %d counted)", key, "new" if counted else "seen before", self.a.count)
        if counted:
            self._dirty = True
            extra["counted"] = True
            self._bon_out = act.bon(self.a.count, grew=act.level_for(self.a.count) > before, last_key=key)
        return extra

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

    def _skills_of(self, graph: dict) -> dict[str, list[tuple[str, str]]]:
        """stepId -> [(skill id, label)]: the skills each step teaches, with the ids lesson.ready's StepSummary.skillIds
        and the Skills page use (skillmap.node_steps + skills_graph.skill_id, as session._skill_ids; cached per lesson)."""
        lesson = graph.get("lesson") or {}
        k = (lesson.get("id"), len(graph.get("steps") or []))
        if k not in self._skills:
            out: dict[str, list[tuple[str, str]]] = {}
            try:
                from server.lesson.skillmap import node_steps
                from server.sessions.skills_graph import skill_id

                ns = node_steps(graph)
                for t in ns.get("taught") or []:
                    sid, label = skill_id(ns["track"], t["label"]), str(t["label"])[:80]
                    for step_id in t.get("steps") or []:
                        out.setdefault(step_id, []).append((sid, label))
            except Exception as e:  # noqa: BLE001 - tags are a nicety
                log.debug("activity: no skill tags: %s", e)
            if len(self._skills) > 8:
                self._skills.clear()
            self._skills[k] = out
        return self._skills[k]

    # ------------------------------------------------------------------ minutes
    async def tick(self, s: Any) -> None:
        """Only the monotonic gap counts (a wall-clock jump never adds or removes time); the day is the wall clock's."""
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
        if marks:
            self._save_soon()
        if self.a.minutes_on(act.day_of(wall)) != self._pushed_minutes:
            await self._push()
        if now - self._saved_t >= SAVE_EVERY_S:
            self._save_soon()

    # ------------------------------------------------------------------ out
    async def _send(self, type_: str, payload: dict) -> None:
        try:
            await self.push(type_, payload)
        except Exception:  # noqa: BLE001
            log.exception("%s push failed", type_)

    async def _push(self, *, now: bool = False) -> None:
        """The `activity` push: only once an app asked, at most one every PUSH_EVERY_S (a change inside that window
        waits for the next slot, and the newest snapshot goes then)."""
        if not self.asked:
            self._pushed_minutes = self.a.minutes_on(act.day_of(self.wall()))
            return
        wait = self._pushed_t + PUSH_EVERY_S - self.mono()
        if now or wait <= 0:
            if self._push_later is not None:
                self._push_later.cancel()
                self._push_later = None
            await self._push_snapshot()
        elif self._push_later is None:
            self._push_later = asyncio.get_running_loop().create_task(self._push_after(wait))
            self._pushed_minutes = self.a.minutes_on(act.day_of(self.wall()))  # one push owed, not one per tick

    async def _push_after(self, wait: float) -> None:
        try:
            await self.sleep(wait)
        finally:
            if self._push_later is asyncio.current_task():
                self._push_later = None
        await self._push_snapshot()

    async def _push_snapshot(self) -> None:
        snap = self.snapshot()
        self._pushed_t = self.mono()
        self._pushed_minutes = self.a.minutes_on(act.day_of(self.wall()))
        await self._send(EVENT, snap)

    async def _save_now(self) -> None:
        if not self._dirty:
            return
        gen = self._gen
        self._dirty, self._saved_t = False, self.mono()
        data = self.a.to_json()
        async with self._lock:
            if gen != self._gen:
                return  # Delete my data ran after this snapshot was taken: never write the old data back
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
        if self._push_later is not None:
            self._push_later.cancel()
            self._push_later = None
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
        await self._save_now()

    async def erase(self) -> None:
        """Delete my data: the counter, minutes and milestones go; the app gets the empty `bon` and `activity`."""
        async with self._lock:
            self._gen += 1
            self.a, self._dirty, self._bon_out = act.Activity(), False, None
            await asyncio.to_thread(act.Activity.erase)
        self._pushed_minutes = 0
        await self._send(BON, self.bon())
        await self._push(now=True)


