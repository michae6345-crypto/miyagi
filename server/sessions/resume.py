"""Resume-or-new across app quits AND engine restarts: progress on disk, offered back, never auto-continued.

    Resumer(session)   # the whole hook (one line in Engine.__init__): it wraps the session's methods

E4's session already freezes a lesson in memory when the app comes back (snapshot(ask_resume=True) ->
video.pause + card {kind:"resume"}; action resume / end_lesson). This adds:
  - autosave to ~/miyagi/state on lesson.ready / lesson.updated (graph + progress: video AND "Just teach
    me" text lessons) and step.started / step.passed (passed + skipped) / video.state (throttled); cleared on
    lesson.ended (end_lesson, a new learn, POST /end) and when the last step passes
  - snapshot() with no lesson in memory but one saved (the engine restarted): spotlight clear,
    video.pause, status idle, the resume card
  - resume() with no lesson in memory: reload the cached step graph (no rebuild) at the saved step and
    seek the video to the saved position; with one in memory: the session's own resume
  - resume_card(): "<title> · Step 3 of 7 · 12 min ago" for the in-memory case too
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from . import store

log = logging.getLogger("sessions")

VIDEO_SAVE_EVERY_S = 3.0
PROMPT_EVENTS = ("card", "video.pause", "status", "spotlight", "error")  # sending the prompt isn't activity


def ago(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    d = s // 86400
    return "yesterday" if d == 1 else f"{d} days ago"


def resume_offer(state: dict, now: float | None = None) -> dict:
    """The `card {kind:"resume"}` payload for a saved lesson."""
    now = time.time() if now is None else now
    idx, n = int(state.get("stepIndex") or 0), int(state.get("stepCount") or 0)
    parts = [state.get("title") or "Your lesson", f"step {idx + 1} of {n}" if n else f"step {idx + 1}"]
    if state.get("lastActiveAt"):
        parts.append(ago(now - float(state["lastActiveAt"])))
    return {"kind": "resume", "title": "Continue where you left off?", "body": " · ".join(parts),
            "actions": ["resume", "end_lesson"]}


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
        self._last_activity: float | None = None
        self._lesson_id: str | None = None  # the lesson the passed/skipped lists belong to
        self._passed: list[str] = []
        self._skipped: list[str] = []
        self._restoring = False  # resume() is reloading: its lesson.ready must not overwrite the saved step
        self._emit = session.emit
        self._video_state = session.video_state
        self._snapshot = session.snapshot
        self._resume = session.resume
        self._resume_card = session.resume_card
        session.emit = self._emit_and_save
        session.video_state = self._video_state_and_save
        session.snapshot = self.snapshot
        session.resume = self.resume
        session.resume_card = self.resume_card

    # ------------------------------------------------------------------ autosave
    def capture(self, step_index: int | None = None) -> dict | None:
        s = self.s
        g = s.graph
        if not g or not s.steps:
            return None
        lesson = g.get("lesson") or {}
        lid = lesson.get("id") or "lesson"
        idx = max(0, min(s.idx if step_index is None else step_index, len(s.steps) - 1))
        step = s.steps[idx]
        if lid not in self._started_at:
            saved = store.load()
            self._started_at[lid] = (saved.get("startedAt") if saved and saved.get("lessonId") == lid else None) \
                or self.clock()
        here = idx == s.idx
        return {
            "lessonId": lid, "sourceUrl": _source_url(g), "title": lesson.get("title") or "Lesson",
            "stepIndex": idx, "stepCount": len(s.steps), "stepId": step["id"], "stepTitle": step.get("title"),
            "mode": lesson.get("mode") or ("lesson" if not g.get("sources") else "video"),
            "passedSteps": list(self._passed) if self._lesson_id == lid else [],
            "skippedSteps": list(self._skipped) if self._lesson_id == lid else [],
            "checks": {cid: st.get("status") for cid, st in (s.check_state or {}).items()} if here else {},
            "videoT": self.video_t if here else None,
            "workdir": s.workdir, "editorOpen": bool(getattr(s, "editor_open", False)),
            "startedAt": self._started_at[lid], "lastActiveAt": self._last_activity or self.clock(),
        }

    def _track(self, lid: str | None) -> None:
        if lid and lid != self._lesson_id:
            self._lesson_id, self._passed, self._skipped = lid, [], []

    def save_now(self, step_index: int | None = None, with_graph: bool = False) -> dict | None:
        st = self.capture(step_index)
        if st is None:
            return None
        self._track(st["lessonId"])
        graph = self.s.graph if with_graph or self._graph_saved_for != st["lessonId"] else None
        try:
            out = store.save(st, graph)
        except OSError as e:
            log.warning("could not save lesson progress: %s", e)
            return None
        self._graph_saved_for = st["lessonId"]
        return out

    async def _emit_and_save(self, type_: str, payload: dict | None = None) -> None:
        await self._emit(type_, payload)
        if type_ not in PROMPT_EVENTS:
            self._last_activity = self.clock()
        try:
            if type_ in ("lesson.ready", "lesson.updated"):  # a new / replaced / extended graph: write it now
                if not self._restoring:
                    self.save_now(with_graph=True)
            elif type_ == "step.started":
                seg = (payload or {}).get("video")
                self.video_t = seg["start"] if seg else None
                self.save_now()
            elif type_ == "step.passed":
                p = payload or {}
                lid = ((self.s.graph or {}).get("lesson") or {}).get("id")
                self._track(lid)
                bucket = self._skipped if p.get("skipped") else self._passed
                if p.get("stepId") and p["stepId"] not in bucket:
                    bucket.append(p["stepId"])
                if p.get("nextStepId") or p.get("pending"):
                    self.save_now(self.s.idx + 1)  # quit before the advance -> resume on the next step
                else:
                    store.clear()  # lesson complete: nothing to resume
            elif type_ == "lesson.ended":
                store.clear()
                self._graph_saved_for = None
                self._lesson_id, self._passed, self._skipped = None, [], []
        except Exception:  # noqa: BLE001 - saving must never break the lesson
            log.exception("autosave failed")

    async def _video_state_and_save(self, t: float, playing: bool) -> None:
        await self._video_state(t, playing)
        s = self.s
        if s.step is None or s.passed or getattr(s, "awaiting_resume", False):
            return
        self.video_t = float(t)
        now = self._last_activity = self.clock()
        if playing != self._playing or now - self._last_video_save >= VIDEO_SAVE_EVERY_S:
            self._playing = playing
            self._last_video_save = now
            self.save_now()

    # ------------------------------------------------------------------ connections
    def snapshot(self, ask_resume: bool = False) -> list[tuple[str, dict]]:
        """What a newly connected app gets. Differs from the session's own snapshot only when no lesson is
        in memory but one is saved on disk (the engine restarted mid-lesson)."""
        s = self.s
        if s.graph is None and s.phase == "idle":
            state = store.load()
            if state is not None and store.load_graph(state) is not None:
                return [("spotlight", {"clear": True}), ("video.pause", {}), ("status", {"state": "idle"}),
                        ("card", resume_offer(state, self.clock()))]
        return self._snapshot(ask_resume=ask_resume)

    def resume_card(self) -> dict:
        st = self.capture()
        return resume_offer(st, self.clock()) if st else self._resume_card()

    # ------------------------------------------------------------------ resume
    async def resume(self) -> bool:
        """action {kind:"resume"}."""
        s = self.s
        if s.graph is not None:
            await self._resume()
            return True
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
        self._lesson_id = state["lessonId"]
        self._passed = [x for x in state.get("passedSteps") or [] if isinstance(x, str)]
        self._skipped = [x for x in state.get("skippedSteps") or [] if isinstance(x, str)]
        editor_open = bool(state.get("editorOpen"))
        t = state.get("videoT")
        seg = s._segment(graph["steps"][idx])
        at = float(t) if seg and isinstance(t, (int, float)) and seg["start"] + 1 < t < seg["end"] - 1 else None
        await self._load_at(graph, idx, at, editor_open)
        if at is not None:
            self.video_t = at
            self.save_now()
        return True

    async def _load_at(self, graph: dict, idx: int, seek_to: float | None, editor_open: bool) -> None:
        """The session's own load_graph (lesson.ready, editor, workdir, coach) with NO build call, except that
        its start_step(0) starts the saved step (mid-segment) instead; its editor offer is dropped when the
        editor was already open."""
        s = self.s
        wrapped = s.emit
        real_start = s.start_step

        async def filtered(type_: str, payload: dict | None = None) -> None:
            if editor_open and type_ == "card" and "open_editor" in ((payload or {}).get("actions") or []):
                return
            await wrapped(type_, payload)

        async def saved_step(_idx: int, seek_to_: float | None = None) -> None:
            del s.start_step  # once: later steps start normally
            s.editor_open = bool(s.editor_open or editor_open)
            await real_start(idx, seek_to=seek_to)

        s.emit = filtered
        s.start_step = saved_step
        self._restoring = True
        try:
            await s.load_graph(graph)
        finally:
            self._restoring = False
            s.emit = wrapped
            if "start_step" in vars(s):
                del s.start_step
