"""Resume-or-new: a lesson survives an app quit (and an engine restart) and is offered back, never auto-continued.

    resumer = Resumer(session)          # wraps session.emit + session.video_state to autosave progress
    msgs = await resumer.on_connect(n)  # what a NEW app connection gets (instead of session.snapshot())
    await resumer.resume()              # action {kind:"resume"}: back to the saved step + video position
    resumer.on_disconnect(n)            # a client left (n = clients still connected)

Saved on step.started / step.passed / video.state (throttled) and on park; cleared on lesson.ended
(end_lesson, a new learn, POST /end) and when the last step passes. On a new connection with a lesson
running, the lesson is *parked*: progress saved, work cancelled quietly (no lesson.ended, no Tiger
"lesson_ended"), and the app gets spotlight clear + video.pause + status idle + the resume card.
A reconnect within RESUME_GRACE_S of the last disconnect (a socket blip, not a quit) keeps the old
snapshot behaviour.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any

from . import store

log = logging.getLogger("sessions")

VIDEO_SAVE_EVERY_S = 3.0


def _grace_s() -> float:
    try:
        return float(os.environ.get("RESUME_GRACE_S", "3"))
    except ValueError:
        return 3.0


def ago(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        h = s // 3600
        return f"{h} h ago"
    d = s // 86400
    return "yesterday" if d == 1 else f"{d} days ago"


def resume_offer(state: dict, now: float | None = None) -> dict:
    """The `card {kind:"resume"}` payload for a saved lesson."""
    now = time.time() if now is None else now
    idx, n = int(state.get("stepIndex") or 0), int(state.get("stepCount") or 0)
    title = state.get("title") or "Your lesson"
    parts = [title, f"Step {idx + 1} of {n}" if n else f"Step {idx + 1}"]
    if state.get("lastActiveAt"):
        parts.append(ago(now - float(state["lastActiveAt"])))
    return {
        "kind": "resume",
        "title": "Continue where you left off?",
        "body": " · ".join(parts),
        "actions": ["resume", "end_lesson"],
        "resume": {k: state.get(k) for k in ("lessonId", "title", "stepIndex", "stepCount", "stepTitle", "lastActiveAt")},
    }


def _source_url(graph: dict) -> str | None:
    srcs = [s for s in graph.get("sources", []) if isinstance(s, dict) and s.get("url")]
    vids = [s for s in srcs if s.get("kind") == "video"]
    return (vids or srcs or [{}])[0].get("url") or (graph.get("lesson") or {}).get("sourceUrl")


class Resumer:
    def __init__(self, session: Any, clock: Callable[[], float] = time.time):
        self.s = session
        self.clock = clock
        self.video_t: float | None = None
        self._playing: bool | None = None
        self._last_video_save = -1e9
        self._graph_saved_for: str | None = None
        self._started_at: dict[str, float] = {}
        self._last_disconnect = -1e9
        self._parking = False
        self._last_activity: float | None = None  # last event / player report: "N min ago" counts from here
        self._emit = session.emit
        self._video_state = session.video_state
        session.emit = self._emit_and_save
        session.video_state = self._video_state_and_save

    # ------------------------------------------------------------------ autosave
    def capture(self, step_index: int | None = None) -> dict | None:
        s = self.s
        g = s.graph
        if not g or not s.steps:
            return None
        lesson = g.get("lesson") or {}
        lid = lesson.get("id") or "lesson"
        idx = s.idx if step_index is None else step_index
        idx = max(0, min(idx, len(s.steps) - 1))
        step = s.steps[idx]
        saved = store.load()
        started = self._started_at.setdefault(
            lid, saved["startedAt"] if saved and saved.get("lessonId") == lid and saved.get("startedAt") else self.clock())
        passed = [st["id"] for st in s.steps[:idx]]
        return {
            "lessonId": lid, "sourceUrl": _source_url(g), "title": lesson.get("title") or "Lesson",
            "stepIndex": idx, "stepCount": len(s.steps), "stepId": step["id"], "stepTitle": step.get("title"),
            "passedSteps": passed,
            "checks": {cid: st.get("status") for cid, st in (s.check_state or {}).items()} if idx == s.idx else {},
            "videoT": self.video_t if idx == s.idx else None,
            "workdir": s.workdir, "editorOpen": bool(getattr(s, "editor_open", False)),
            "startedAt": started, "lastActiveAt": self._last_activity or self.clock(),
        }

    def save_now(self, step_index: int | None = None) -> dict | None:
        st = self.capture(step_index)
        if st is None:
            return None
        graph = None
        if self._graph_saved_for != st["lessonId"] or store.load_graph(st) is None:
            graph = self.s.graph
        try:
            out = store.save(st, graph)
        except OSError as e:
            log.warning("could not save lesson progress: %s", e)
            return None
        if graph is not None:
            self._graph_saved_for = st["lessonId"]
        return out

    async def _emit_and_save(self, type_: str, payload: dict | None = None) -> None:
        await self._emit(type_, payload)
        if not self._parking:
            self._last_activity = self.clock()
        try:
            if type_ == "step.started":
                seg = (payload or {}).get("video")
                self.video_t = seg["start"] if seg else None
                self.save_now()
            elif type_ == "step.passed":
                if (payload or {}).get("nextStepId"):
                    self.save_now(self.s.idx + 1)  # quit before the advance -> resume on the next step
                else:
                    store.clear()  # lesson complete: nothing to resume
            elif type_ == "lesson.ended" and not self._parking:
                store.clear()
                self._graph_saved_for = None
        except Exception:  # noqa: BLE001 - saving must never break the lesson
            log.exception("autosave failed")

    async def _video_state_and_save(self, t: float, playing: bool) -> None:
        await self._video_state(t, playing)
        if self.s.step is None or self.s.passed:
            return
        self.video_t = float(t)
        now = self._last_activity = self.clock()
        if playing != self._playing or now - self._last_video_save >= VIDEO_SAVE_EVERY_S:
            self._playing = playing
            self._last_video_save = now
            self.save_now()

    # ------------------------------------------------------------------ connections
    def on_disconnect(self, remaining: int = 0) -> None:
        if remaining == 0:
            self._last_disconnect = self.clock()

    async def on_connect(self, others: int = 0) -> list[tuple[str, dict]]:
        """Messages for a NEW app connection (`others` = clients already connected)."""
        s = self.s
        if others or s.phase in ("building", "searching") or self.clock() - self._last_disconnect < _grace_s():
            return s.snapshot()
        if s.graph is not None and s.phase == "active" and s.step is not None:
            await self.park()
        if s.graph is not None:  # done (or anything else we don't park): unchanged behaviour
            return s.snapshot()
        state = store.load()
        if state is None or store.load_graph(state) is None:
            return s.snapshot()
        return [("spotlight", {"clear": True}), ("video.pause", {}), ("status", {"state": "idle"}),
                ("card", resume_offer(state, self.clock()))]

    async def park(self) -> None:
        """Save progress, then stop the lesson quietly (nothing sent, nothing recorded as ended)."""
        self.save_now()
        s = self.s
        wrapped = s.emit

        async def mute(*_a: Any, **_k: Any) -> None:
            return None

        self._parking = True
        s.emit = mute
        s._record = lambda *a, **k: None  # instance attr shadows the method while parking
        try:
            await s.end_lesson("parked")
        finally:
            s.emit = wrapped
            del s._record
            self._parking = False

    # ------------------------------------------------------------------ resume
    async def resume(self) -> bool:
        """action {kind:"resume"}: rebuild the lesson from disk at the saved step + video position."""
        s = self.s
        if s.graph is not None:  # a lesson is already running (stale card): nothing to do
            return False
        state = store.load()
        graph = store.load_graph(state) if state else None
        if state is None or graph is None:
            store.clear()
            await s.emit("error", {"message": "That lesson can't be resumed any more. Start a new one."})
            await s.emit("status", {"state": "idle"})
            return False
        idx = max(0, min(int(state["stepIndex"]), len(graph["steps"]) - 1))
        self._started_at[state["lessonId"]] = state.get("startedAt") or self.clock()
        self._graph_saved_for = state["lessonId"]
        editor_open = bool(state.get("editorOpen"))
        await self._load_without_step0(graph, drop_editor_offer=editor_open)
        s.editor_open = editor_open
        await s.start_step(idx)
        seg = (s.step or {}) and s._segment(s.step)
        t = state.get("videoT")
        if seg and isinstance(t, (int, float)) and seg["start"] + 1 < t < seg["end"] - 1:
            self.video_t = float(t)
            await s.emit("video.seek", {"t": float(t), "play": True})
            self.save_now()
        return True

    async def _load_without_step0(self, graph: dict, drop_editor_offer: bool) -> None:
        s = self.s
        wrapped = s.emit

        async def filtered(type_: str, payload: dict | None = None) -> None:
            if drop_editor_offer and type_ == "card" and "open_editor" in ((payload or {}).get("actions") or []):
                return
            await wrapped(type_, payload)

        async def no_step(_idx: int) -> None:
            return None

        s.emit = filtered
        s.start_step = no_step  # load_graph ends with start_step(0); resume starts the saved step itself
        try:
            await s.load_graph(graph)
        finally:
            s.emit = wrapped
            del s.start_step
