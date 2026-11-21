"""Resume-or-new across app quits AND engine restarts: progress on disk, offered back, never auto-continued.

    Resumer(session)   # the whole hook (one line in Engine.__init__): it wraps the session's methods

E4's session already freezes a lesson in memory when the app comes back (snapshot(ask_resume=True) ->
video.pause + card {kind:"resume"}; action resume / end_lesson). This adds:
  - autosave to ~/miyagi/state on lesson.ready / lesson.updated (graph + progress: video AND "Just teach
    me" text lessons) and step.started / step.passed (passed + skipped) / video.state (throttled); cleared on
    POST /end and when the last step passes; KEPT on lesson.ended "stopped" (the bar's End) and "end_lesson"
    (the resume card's "Start a new lesson", E11: it threw the lesson away for good, and a stray click near
    Continue did it), marked `stopped`: offered back by the resume card when the app next connects, restored
    only by its Continue, replaced once another lesson is actually built (a rebuild of the same lesson starts
    over and replaces it). The lesson it replaced goes on the recent list (store.recent()).
  - snapshot() with no lesson in memory: status idle only (Nov 21, launch-quiet: nothing on connect). A saved
    lesson is offered (pending_offer(): the resume card) after the app's library.list, never on connect
  - resume() with no lesson in memory: reload the cached step graph (no rebuild) at the saved step and
    seek the video to the saved position; with one in memory: the session's own resume
  - resume_card(): "<title> · Step 3 of 7 · 12 min ago" for the in-memory case too

The save made before a restart is protected until the learner answers the card: while it is pending
nothing saves or clears it (an app connect, a snapshot, a disconnect, the engine stopping, the frozen
in-memory lesson). Continue restores it; Start new (end_lesson) keeps it, marked stopped; POST /end clears
it; a different lesson replaces it; the SAME lesson loaded again (a rebuild that hit the lesson cache) continues at the
saved step instead of starting over, except for a save the bar's End kept (`stopped`): that one starts over.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from . import mastery, store

log = logging.getLogger("sessions")

VIDEO_SAVE_EVERY_S = 3.0
EXPLICIT_END = ("end_lesson", "POST /end")  # the learner chose "Start a new lesson" / a terminal ended it
# the bar's / launcher's End, and the resume card's "Start a new lesson": stop for now; the save stays (offered back
# like a restart's) until another lesson is built (E11). Only POST /end and a finished lesson clear it.
KEEP_END = ("stopped", "end_lesson")
# Nov 15: `curl -X POST localhost:8787/end` before every engine deploy cleared the learner's place, so after the restart
# the app was back on the start sheet and typing the goal again began at step 1. That end now keeps the save, NOT marked
# stopped: the next connection after the restart continues at that exact step (POST /end?forget=1 still clears it).
INTERRUPTED = "interrupted"
PROMPT_EVENTS = ("card", "video.pause", "status", "spotlight", "error")  # sending the prompt isn't activity


def is_demo(graph: dict | None) -> bool:
    """A Demo take (orchestrator/stage.py marks lesson.stage): never saved, resumed or offered back. Michael runs the
    Demo many times in a row and every start must be a fresh take at step 1 (no resume card, no auto-resume)."""
    return bool(((graph or {}).get("lesson") or {}).get("stage"))


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
        self._restoring = False  # resume() is reloading: its lesson.ready must not overwrite the saved step
        if (old := store.load()) is not None and is_demo(store.load_graph(old)):
            store.clear()  # a Demo take saved by an older engine: never offered back
        self._pending = store.load() is not None  # saved before this engine started, not answered yet
        self._emit = session.emit
        self._load_graph = session.load_graph
        self._video_state = session.video_state
        self._snapshot = session.snapshot
        self._resume = session.resume
        self._resume_card = session.resume_card
        session.emit = self._emit_and_save
        session.video_state = self._video_state_and_save
        session.snapshot = self.snapshot
        session.resume = self.resume
        session.resume_card = self.resume_card
        session.load_graph = self.load_graph

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
        skipped = set(getattr(s, "skipped_steps", None) or [])
        return {
            "lessonId": lid, "sourceUrl": _source_url(g), "title": lesson.get("title") or "Lesson",
            "stepIndex": idx, "stepCount": len(s.steps), "stepId": step["id"], "stepTitle": step.get("title"),
            "mode": lesson.get("mode") or ("lesson" if not g.get("sources") else "video"),
            "passedSteps": [st["id"] for st in s.steps[:idx] if st["id"] not in skipped],
            "skippedSteps": [st["id"] for st in s.steps[:idx] if st["id"] in skipped],  # Skip: left unfinished
            "checks": {cid: st.get("status") for cid, st in (s.check_state or {}).items()} if here else {},
            "videoT": self.video_t if here else None,
            "workdir": s.workdir, "editorOpen": bool(getattr(s, "editor_open", False)),
            "startedAt": self._started_at[lid], "lastActiveAt": self._last_activity or self.clock(),
        }

    def save_now(self, step_index: int | None = None, with_graph: bool = False) -> dict | None:
        if self._pending or getattr(self.s, "awaiting_resume", False):
            return None  # the save on disk is the learner's place until they answer the resume card
        if getattr(self.s, "phase", None) == "done":
            return None  # t5: the lesson ran to its end (cleared at its last step.passed): an app quit must not save it back
        if is_demo(self.s.graph):
            return None  # a Demo take is never resumed: each Demo start is step 1 (stage.py)
        st = self.capture(step_index)
        if st is None:
            return None
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
        if type_ not in PROMPT_EVENTS and not self._restoring:  # a restore's replay isn't the learner's activity
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
                if not p.get("skipped"):  # E23: what this step practised, evidence for later lessons' prerequisites
                    mastery.record_step_safely(self.s.graph or {}, p.get("stepId"))
                if p.get("nextStepId") or p.get("pending"):
                    self.save_now(self.s.idx + 1)  # quit before the advance -> resume on the next step
                else:
                    store.clear()  # lesson complete: nothing to resume
                    skipped = set(getattr(self.s, "skipped_steps", None) or []) | ({p.get("stepId")} if p.get("skipped") else set())
                    store.record_completed(self.s.graph or {}, skipped)  # evidence for later lessons' prerequisites
            elif type_ == "lesson.ended":
                if (payload or {}).get("reason") == INTERRUPTED:  # a deploy's end: the place stays (POST /end saved it
                    self._pending = self._pending or store.load() is not None  # just before), resumed after the restart
                    return
                if self._pending and (payload or {}).get("reason") not in EXPLICIT_END:
                    return
                if (payload or {}).get("reason") in KEEP_END:  # protected until Continue / another lesson / POST /end
                    saved = store.load()
                    if saved is not None:  # marked: only Continue restores it, never a rebuild (also after a restart)
                        store.save({**saved, "stopped": True})
                    self._pending = saved is not None
                    return
                self._pending = False
                if (payload or {}).get("reason") == "new lesson" and (saved := store.load()) is not None:
                    store.remember(saved)  # E11: a new learn / "Learn X first" replaced it: on the recent list
                store.clear()
                self._graph_saved_for = None
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
    def snapshot(self, ask_resume: bool = False, **kw: Any) -> list[tuple[str, dict]]:
        """What a newly connected app gets. Nov 21 (launch-quiet): with no lesson in memory (a fresh engine, the
        engine restarted mid-lesson) only status idle: no spotlight clear, no video.pause and no resume card on
        connect, so the app's sign-in comes first. A saved lesson is offered when the app asks for the library
        (pending_offer(), sent after `library` by main.py) and stays on disk for Continue / action resume."""
        s = self.s
        if s.graph is None and s.phase == "idle":
            return [("status", {"state": "idle"})]
        return self._snapshot(ask_resume=ask_resume, **kw)

    def pending_offer(self) -> dict | None:
        """The resume card for a saved lesson still waiting for the learner (not ended with End / Start new, not a
        Demo, its graph still on disk), or None. Only with no lesson in memory."""
        s = self.s
        if s.graph is not None or s.phase != "idle":
            return None
        state = store.load()
        if state is None or state.get("stopped") or store.load_graph(state) is None:
            return None
        return resume_offer(state, self.clock())

    def resume_card(self) -> dict:
        st = self.capture()
        return resume_offer(st, self.clock()) if st else self._resume_card()

    # ------------------------------------------------------------------ resume
    async def load_graph(self, graph: dict) -> None:
        """Every load goes through here. While a pre-restart save is pending, the same lesson loaded
        again continues at the saved step (not one the bar's End kept: only Continue restores that); any other
        lesson replaces the save."""
        if self._pending:
            saved = store.load()
            self._pending = False
            lid = (graph.get("lesson") or {}).get("id")
            if (saved is not None and lid and lid == saved.get("lessonId") and not saved.get("stopped")
                    and not is_demo(graph)):  # a Demo start is always step 1, never a save's step
                old = store.load_graph(saved)
                if old is not None and len(old.get("steps") or []) > len(graph.get("steps") or []):
                    graph = old  # a partial rebuild: keep the full saved graph (later parts merge by id)
                await self._restore(saved, graph)
                return
        await self._load_graph(graph)

    async def resume(self) -> bool:
        """action {kind:"resume"}."""
        self._pending = False
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
        await self._restore(state, graph)
        return True

    async def _restore(self, state: dict, graph: dict) -> None:
        s = self.s
        idx = max(0, min(int(state["stepIndex"]), len(graph["steps"]) - 1))
        self._started_at[state["lessonId"]] = state.get("startedAt") or self.clock()
        if isinstance(state.get("lastActiveAt"), (int, float)):  # Nov 21: the restore keeps "12 min ago" honest: the
            self._last_activity = float(state["lastActiveAt"])  # saves it makes carry the saved time, not now
        self._graph_saved_for = None  # the first save after a restore rewrites the graph file too
        editor_open = bool(state.get("editorOpen"))
        t = state.get("videoT")
        seg = s._segment(graph["steps"][idx])
        at = float(t) if seg and isinstance(t, (int, float)) and seg["start"] + 1 < t < seg["end"] - 1 else None
        skipped = [x for x in state.get("skippedSteps") or [] if isinstance(x, str)]
        await self._load_at(graph, idx, at, editor_open, skipped)
        if at is not None:
            self.video_t = at
            self.save_now()

    async def _load_at(self, graph: dict, idx: int, seek_to: float | None, editor_open: bool,
                       skipped: list[str]) -> None:
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
            if hasattr(s, "skipped_steps"):  # load_graph just reset it: the saved skips come back
                s.skipped_steps = list(skipped)
            await real_start(idx, seek_to=seek_to)

        s.emit = filtered
        s.start_step = saved_step
        self._restoring = True
        s.restoring = True  # start_step: the saved position is sought paused (video.seek play false, no video.play)
        try:
            await self._load_graph(graph)  # the session's own, not this wrapper
        finally:
            self._restoring = False
            s.restoring = False
            s.emit = wrapped
            if "start_step" in vars(s):
                del s.start_step
