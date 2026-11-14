"""The lesson state machine (one learner, one lesson at a time).

Flow:
  learn -> search.result* -> search.done
  build_lesson / learn_url -> lesson.building* -> lesson.ready -> step 0
  step start -> step.started, check.updated(pending)*, video.seek(play) + video.play, status watching
  segment end (video.state reaches step.video.end) -> pass if checks already pass,
                                                       else video.pause + spotlight
  file save / run end / metrics / screen frames -> checks.evaluate_gate -> check.updated (changes only)
     PASS needs the checks AND a learner action this step (save, run, keystroke/click); checks
     passing with no action -> a "Looks done? Confirm" card (step confirm = action + screen).
     FAILING -> speak only at breakpoints or when stuck (docs/research/screen-understanding.md):
       breakpoints: a run ends failing; the same failure on two saves in a row
       stuck: no check progress for STUCK_S, or IDLE_AFTER_ACTION_S idle after the learner acted
       never within TYPING_GUARD_S of a keystroke (retried on the next tick)
     Hint ladder per step: 0 title (step.started) -> 1 spotlight (clip ends) -> 2 concept card
     (offtrack, no fix) -> 3 exact fix + "Do it for me" (offtrack with diff + apply_fix), the last
     only on a repeat/stuck >= LADDER_MIN_S after level 2. A failing check shows as `pending`
     until a learner-driven evaluation (save/run/metrics) or the coach has surfaced it.
  apply_fix ("Do it for me"): refuses while VS Code shows the file unsaved, backs it up, writes the
     coach's patch (only if it compiles), jumps VS Code there, spotlights it; `undo` restores it.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from . import config
from .context import RunContext, RunInfo, metrics_summary
from .modules import Modules

log = logging.getLogger("orchestrator.session")

Emit = Callable[[str, dict], Awaitable[None]]

DIAGRAM_KINDS = ("network", "gradients", "heatmap")


def video_id_from_url(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else None


class BuildStage(logging.Handler):
    """Turns the lesson builder's own log lines (server.lesson) into an honest stage label."""

    RULES = [
        ("lesson cache hit", "Loading the saved lesson"),
        ("daily quota exhausted", "Gemini is out of quota; trying another model"),
        ("too slow; switching engine", "Gemini is slow; reading the transcript instead"),
        ("video pass failed", "Couldn't watch the video; reading the transcript instead"),
        ("video pass:", "Claude is writing the steps"),
        ("claude adapt pass", "Fitting the checks to your project"),
        ("adapt attempt", "Fitting the checks to your project"),
        ("lesson built", "Finishing up"),
    ]

    STAGE_LABELS = {  # E2's build_lesson(on_progress=...) stage ids (server.lesson.builder.STAGES)
        "cache_hit": "Loading the saved lesson",
        "watching": "Gemini is watching the video",
        "reading_transcript": "Reading the transcript",
        "writing_steps": "Claude is writing the steps",
        "steps_ready": "Steps ready",
        "adapting": "Fitting the checks to your project",
        "done": "Finishing up",
    }
    SWITCH_LABELS = {
        "quota": "Gemini is out of quota; using the transcript",
        "slow": "Gemini is slow; using the transcript",
        "key": "No Gemini key; using the transcript",
        "error": "Couldn't watch the video; using the transcript",
    }

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.text = "Gemini is watching the video"
        self.structured = False  # once the builder reports stages, ignore log matching

    def on_progress(self, stage: str, message: str = "") -> None:
        """E2's progress callback: honest, stable stage ids."""
        self.structured = True
        msg = (message or "").strip()
        if stage == "engine_switch":
            self.text = self.SWITCH_LABELS.get(msg, "Switching to the transcript")
        elif stage == "steps_ready":
            self.text = "Steps ready (from the video)" if msg == "gemini" else "Steps ready (from the transcript)"
        elif stage == "adapting" and msg == "retry":
            self.text = "Fitting the checks to your project (second pass)"
        elif stage in self.STAGE_LABELS:
            self.text = self.STAGE_LABELS[stage]

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401 - logging API (fallback for older builders)
        if self.structured:
            return
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return
        for needle, label in self.RULES:
            if needle in msg:
                self.text = label
                return

    def listening(self):
        import contextlib

        lg = logging.getLogger("server.lesson")

        @contextlib.contextmanager
        def cm():
            old = lg.level
            if lg.getEffectiveLevel() > logging.INFO:
                lg.setLevel(logging.INFO)
            lg.addHandler(self)
            try:
                yield self
            finally:
                lg.removeHandler(self)
                lg.setLevel(old)

        return cm()


def human_build_error(e: BaseException) -> str:
    """A message the learner can act on (the raw reason stays in the engine log)."""
    raw = str(e)
    low = raw.lower()
    quota = "quota" in low or "resource_exhausted" in low
    yt_limited = ("429" in low or "too many requests" in low) and ("transcript" in low or "caption" in low)
    if quota and yt_limited:  # E2: "no engine could build the lesson" with both causes
        return ("Couldn't watch this video: Gemini's quota is used up and YouTube is rate-limiting this network. "
                "Try a lesson that's already built, another network (hotspot), or add a Gemini key in Settings.")
    if "took over" in low or "no answer within" in low or isinstance(e, TimeoutError):
        return "Building this lesson is taking too long. Try again, or pick another video."
    if "quota" in low or "resource_exhausted" in low:
        return "Gemini's daily quota is used up, so I couldn't watch this video. Try another video or add a key in Settings."
    if "429" in low or "too many requests" in low or ("rate" in low and "limit" in low):
        if "transcript" in low or "caption" in low or "youtube" in low:
            return ("Couldn't get this video's transcript: YouTube is rate-limiting this network. "
                    "Try another video or the hotspot.")
        return "The video service is rate-limiting us right now. Try again in a minute, or pick another video."
    if "only youtube" in low or "youtube sources" in low:
        return "I can only build lessons from YouTube videos for now. Pick a video result."
    if "api key" in low or "api_key" in low or "authentication" in low or "401" in low:
        return "A model API key is missing or invalid. Add it in Settings and try again."
    if "transcript" in low:
        return "Couldn't get this video's transcript. Try another video."
    return f"Couldn't build this lesson: {raw[:160]}"


class LessonSession:
    def __init__(
        self,
        emit: Emit,
        modules: Modules | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        idle_gate_s: float | None = None,
        advance_delay_s: float | None = None,
        metric_eval_s: float | None = None,
        result_stagger_s: float = 0.06,
        build_tick_s: float = 1.0,
        screen: Any = None,
        seen_interval_s: float = 5.0,
        workspace: Any = None,
        inputs: Any = None,
    ):
        self.inputs = inputs  # inputs.Inputs (cursor, last key/click) or None
        self.last_obs: Any = None
        self.undo: tuple[Path, str] | None = None
        self.pending_patch: dict | None = None  # "Do it for me" preview awaiting confirm
        self.workspace = workspace  # workspace.Workspace (opens VS Code) or None
        self.emit = emit
        self.screen = screen  # ScreenBridge / FakeScreen / None
        self.seen_interval_s = seen_interval_s
        self._last_seen = -1e9
        self.m = modules or Modules()
        self.clock = clock
        self.idle_gate_s = config.IDLE_GATE_S if idle_gate_s is None else idle_gate_s
        self.advance_delay_s = config.ADVANCE_DELAY_S if advance_delay_s is None else advance_delay_s
        self.metric_eval_s = config.METRIC_EVAL_INTERVAL_S if metric_eval_s is None else metric_eval_s
        self.result_stagger_s = result_stagger_s
        self.build_tick_s = build_tick_s

        self.phase = "idle"  # idle | searching | building | active | done
        self.query = ""
        self.results: dict[str, dict] = {}
        self.build_progress: dict | None = None  # last lesson.building payload while a build runs
        self.graph: dict | None = None
        self.workdir = str(config.default_workdir())
        self.on_workdir: Callable[[str], None] | None = None  # main.py hooks the file watcher here
        self.idx = -1
        self.runs: dict[str, RunInfo] = {}
        self.voice = False
        self.status = "idle"
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._timers: set[asyncio.Task] = set()
        self._metric_eval_pending = False
        self._reset_step_state()

    # ------------------------------------------------------------------ basics
    def _reset_step_state(self) -> None:
        self.check_state: dict[str, dict] = {}  # what the app was last told, per checkId
        self.last_results: list[dict] = []
        self.last_failed: list[dict] = []
        self._eval_error_sent = False
        self.engaged = False  # learner touched files / ran something during this step
        self.gate_open = False  # failing checks are shown as fail (else pending)
        self.step_t0 = self.clock()
        self.last_action_t = -1e9  # last save / run start / explicit action (session clock)
        self.best_pass = 0
        self.last_progress_t = self.clock()
        self.last_bp_sig: tuple | None = None
        self.pending_speak: str | None = None  # deferred by the typing guard
        self.ladder = 1  # 0 title, 1 spotlight; 2 concept card; 3 exact fix
        self.spoken_sig: tuple | None = None
        self.spoken_t = -1e9
        self.full_card: dict | None = None
        self.confirm_pending = False
        self.segment_done = False
        self.video_reports = 0
        self.coached_key: Any = None
        self.coaching = False
        self.hint_level = 0
        self.step_runs: list[RunInfo] = []
        self.last_activity = self.clock()
        self.passed = False
        self.last_offtrack: dict | None = None
        self.spot_track: tuple[str, str | None, str] | None = None  # (match, app, caption) to follow on screen
        self.spot_rect: dict | None = None
        self.step_gen = getattr(self, "step_gen", 0) + 1  # invalidates stale timers/coach results

    def _spawn(self, coro, *, timer: bool = False) -> asyncio.Task:
        """Background work. `timer` tasks (long sleeps) are not awaited by drain()."""
        t = asyncio.create_task(coro)
        (self._timers if timer else self._tasks).add(t)
        t.add_done_callback(self._task_done)
        return t

    def _task_done(self, t: asyncio.Task) -> None:
        self._tasks.discard(t)
        self._timers.discard(t)
        if not t.cancelled() and t.exception() is not None:
            log.error("background task failed", exc_info=t.exception())

    async def drain(self) -> None:
        """Wait for background work (tests)."""
        while True:
            pending = [t for t in self._tasks if not t.done()]
            if not pending:
                await asyncio.sleep(0)  # let done-callbacks run; they may have spawned more
                if not [t for t in self._tasks if not t.done()]:
                    return
                continue
            await asyncio.wait(pending)

    async def _status(self, state: str) -> None:
        self.status = state
        await self.emit("status", {"state": state})

    @property
    def steps(self) -> list[dict]:
        return (self.graph or {}).get("steps", [])

    @property
    def step(self) -> dict | None:
        if self.phase in ("active", "done") and 0 <= self.idx < len(self.steps):
            return self.steps[self.idx]
        return None

    def context(self) -> RunContext:
        # a `tut run` (exact ::metric:: lines) beats the same curve read off the screen
        tut = [r for r in self.step_runs if not r.run_id.startswith("screen-")]
        last = (tut or self.step_runs or [None])[-1]
        return RunContext(workdir=self.workdir, last_run=last, runs=list(self.step_runs),
                          screen=self._screen_lines())

    def _screen_lines(self) -> dict | None:
        if self.screen is None:
            return None
        try:
            return self.screen.lines()
        except Exception:  # noqa: BLE001
            log.exception("screen lines failed")
            return None

    def screen_active(self) -> bool:
        return self.screen is not None and bool(getattr(self.screen, "active", True))

    def _precision_display(self, step: dict) -> bool:
        """Without a screen reader the screen checks can never move, so the checklist the app
        shows is the step's precision_checks (when it has them and we're in precision mode)."""
        return not self.screen_active() and bool(step.get("precision_checks")) and self.precision_mode()

    def display_checks(self, step: dict) -> list[dict]:
        return (step.get("precision_checks") if self._precision_display(step) else step.get("checks")) or []

    def precision_mode(self) -> bool:
        """Known workdir on disk, or a `tut run` this step -> precision_checks may also pass the step.
        ORCH_PRECISION=on/off overrides (off = screen checks only, e.g. live screen demos)."""
        setting = config.precision_setting()
        if setting != "auto":
            return setting == "on"
        if any(not r.run_id.startswith("screen-") for r in self.step_runs):
            return True
        return Path(self.workdir).is_dir()

    def _touch(self) -> None:
        self.last_activity = self.clock()

    def _segment(self, step: dict) -> dict | None:
        v = step.get("video")
        if not v:
            return None
        vid = v.get("videoId")
        if not vid:
            src = next((s for s in (self.graph or {}).get("sources", []) if s.get("id") == v.get("sourceId")), None)
            if src is None:
                src = next((s for s in (self.graph or {}).get("sources", []) if s.get("kind") == "video"), {})
            vid = src.get("videoId") or video_id_from_url(src.get("url", "")) or ""
        return {"videoId": vid, "start": float(v.get("start", 0)), "end": float(v.get("end", 0))}

    # ------------------------------------------------------------------ search + build
    async def learn(self, query: str) -> None:
        self.phase = "searching"
        self.query = query
        await self._status("thinking")
        self.results = {}
        try:
            async for r in self.m.search(query):  # streamed as the finder produces them
                self.results[r["id"]] = r
                await self.emit("search.result", r)
                if self.result_stagger_s and self.m.demo:
                    await asyncio.sleep(self.result_stagger_s)
        except Exception as e:
            log.exception("search failed")
            await self.emit("error", {"message": f"Search failed: {e}. Paste a YouTube link instead."})
        await self.emit("search.done", {"total": len(self.results)})
        self.phase = "idle" if self.graph is None else self.phase
        await self._status("idle")

    async def build_lesson(self, result_ids: list[str]) -> None:
        picked = [self.results[i] for i in result_ids if i in self.results]
        if not picked and self.results:
            picked = [next(iter(self.results.values()))]
        url = picked[0].get("url", "") if picked else ""
        await self._build(url, self.query)

    async def learn_url(self, url: str) -> None:
        await self._build(url, self.query)

    async def _build(self, url: str, goal: str) -> None:
        """Build a lesson with live progress (>= 1 tick/s, stage names from the builder's own log
        events). Any failure, timeout or cancellation ends with `error` (human wording), a final
        `lesson.building {failed: true}` and `status idle`, so the app never stays on "building"."""
        self.phase = "building"
        await self._status("thinking")
        done = asyncio.Event()
        t0 = self.clock()
        stage = BuildStage()
        self.build_progress = {"message": "Starting the lesson builder", "progress": 0.0}

        async def ticker() -> None:
            expected = float(os.environ.get("ORCH_BUILD_EXPECTED_S", "75"))
            while not done.is_set():
                el = self.clock() - t0
                msg = f"{stage.text} · {int(el) // 60}:{int(el) % 60:02d}" if el >= 1 else stage.text
                self.build_progress = {"message": msg, "progress": round(min(0.95, el / expected), 2)}
                await self.emit("lesson.building", self.build_progress)
                try:
                    await asyncio.wait_for(done.wait(), self.build_tick_s)
                except TimeoutError:
                    pass

        tick = asyncio.create_task(ticker())
        from . import workspace as wsmod

        ok = False
        try:
            with stage.listening():
                graph = await self.m.build_lesson(url, goal, wsmod.build_workdir(url, goal),
                                                  on_progress=stage.on_progress)
            done.set()
            await tick
            self.build_progress = {"message": "Setting up your project folder", "progress": 0.97}
            await self.emit("lesson.building", self.build_progress)
            folder = await asyncio.to_thread(wsmod.prepare, graph, goal)  # S2: starter files (Claude), 0-25 s
            if folder:
                graph.setdefault("lesson", {})["workdir"] = folder
            self.build_progress = None
            await self.emit("lesson.building", {"message": "Lesson ready", "progress": 1.0})
            ok = True
        except BaseException as e:
            log.exception("build_lesson failed")
            if isinstance(e, Exception):
                await self._build_failed(human_build_error(e))
            raise_after = not isinstance(e, Exception)
            if raise_after:  # cancelled (engine shutting down / client gone): still tell the app
                await asyncio.shield(self._build_failed("The lesson build was interrupted. Try again."))
                raise
            return
        finally:
            done.set()
            if not tick.done():
                tick.cancel()
            if not ok:
                self.phase = "idle" if self.graph is None else self.phase
        await self.load_graph(graph)

    async def _build_failed(self, message: str) -> None:
        self.build_progress = None
        self.phase = "idle" if self.graph is None else "active"
        await self.emit("error", {"message": message})
        await self.emit("lesson.building", {"message": message, "progress": 0.0, "failed": True})
        await self._status("idle" if self.graph is None else "watching")

    async def load_graph(self, graph: dict) -> None:
        self.graph = graph
        self.runs = {}
        new_wd = str(config.resolve_workdir(graph.get("lesson", {}).get("workdir")))
        self.workdir = new_wd
        if self.on_workdir:
            self.on_workdir(new_wd)
        self.m.set_lesson(graph)
        self._spawn(self.m.warm(), timer=True)  # pre-warm the coach's cached lesson prefix
        await self.emit("lesson.ready", self._lesson_ready_payload())
        if self.workspace is not None:
            self.workspace.open(new_wd)
        await self.start_step(0)

    def _lesson_ready_payload(self) -> dict:
        g = self.graph or {}
        lesson = g.get("lesson", {})
        sources = [
            {k: v for k, v in s.items() if k in ("id", "kind", "title", "url", "meta", "videoId")}
            for s in g.get("sources", [])
        ]
        steps = []
        for i, s in enumerate(self.steps):
            summary = {"id": s["id"], "index": s.get("index", i), "title": s["title"]}
            seg = self._segment(s)
            if seg:
                summary["video"] = seg
            steps.append(summary)
        return {"lesson": {"id": lesson.get("id", "lesson"), "title": lesson.get("title", "Lesson"), "sources": sources},
                "steps": steps}

    # ------------------------------------------------------------------ steps
    def _step_started_payload(self, step: dict) -> dict:
        p = {"stepId": step["id"], "index": step.get("index", self.idx), "title": step["title"],
             "instructions": step.get("instructions", "")}
        seg = self._segment(step)
        if seg:
            p["video"] = seg
        return p

    async def start_step(self, idx: int) -> None:
        if not (0 <= idx < len(self.steps)):
            return
        self.idx = idx
        self.phase = "active"
        self._reset_step_state()
        step = self.steps[idx]
        await self.emit("step.started", self._step_started_payload(step))
        for c in self.display_checks(step):
            self.check_state[c["id"]] = {"label": c.get("label", c["id"]), "status": "pending", "detail": None}
            await self.emit("check.updated", {"stepId": step["id"], "checkId": c["id"],
                                              "label": c.get("label", c["id"]), "status": "pending"})
        seg = self._segment(step)
        if seg:
            await self.emit("video.seek", {"t": seg["start"], "play": True})
            await self.emit("video.play", {})
            self._spawn(self._segment_timer(self.step_gen, seg["end"] - seg["start"]), timer=True)
        else:
            self.segment_done = True
        self._watch_screen_metrics(step)
        if self.m.has_diagrams() and os.environ.get("ORCH_DIAGRAM_PREFETCH", "1") == "1":
            self._spawn(self._prefetch_diagram(self.step_gen, step), timer=True)
        if self.workspace is not None:
            self.workspace.goto_target(self.workdir, step)
        await self._status("watching")
        await self.evaluate("start")

    def _watch_screen_metrics(self, step: dict) -> None:
        if self.screen is None:
            return
        patterns = {c["metric"]: c["metric_pattern"]
                    for c in (step.get("checks") or []) + (step.get("precision_checks") or [])
                    if c.get("metric") and c.get("metric_pattern")}
        lesson_id = (self.graph or {}).get("lesson", {}).get("id", "lesson")
        if patterns:
            self.screen.watch(lesson_id, patterns, self._on_screen_metric)
        else:
            self.screen.unwatch()

    def _on_screen_metric(self, run_id: str, name: str, step: int, value: float) -> None:
        """Called on the loop by the screen bridge for each metric read off the terminal."""
        self._spawn(self.ingest({"kind": "metric", "run_id": run_id, "step": step, "name": name,
                                 "value": value, "source": "screen"}))

    async def _segment_timer(self, gen: int, duration: float) -> None:
        """Fallback when the player never reports video.state: end the segment by wall clock."""
        await asyncio.sleep(max(0.0, duration) + 1.0)
        if gen == self.step_gen and self.video_reports == 0 and not self.segment_done:
            await self._segment_end()

    async def _segment_end(self) -> None:
        if self.segment_done or self.step is None:
            return
        self.segment_done = True
        step = self.step
        if not step.get("checks") and not step.get("precision_checks"):
            await self._pass_step()
            return
        await self.evaluate("segment")
        if self.passed or self.step is not step:
            return
        await self.emit("video.pause", {})
        await self._spotlight_target(step)
        if self.status != "offtrack":
            await self._status("watching")

    def _locate(self, match: str, app: str | None, caption: str) -> dict | None:
        if self.screen is None or not match:
            return None
        spot = self.screen.locate(match, app)
        if not spot:
            return None
        return {**spot, "caption": caption}

    async def _spotlight_target(self, step: dict) -> bool:
        """Spotlight the step's first target that is visible on screen (rect in screen points).
        The target is remembered, so later frames re-place the spotlight when it scrolls into view or moves."""
        tlist = [t for t in step.get("targets") or [] if t.get("match")]
        if tlist and self.spot_track is None:
            t = tlist[0]
            self.spot_track = (t["match"], t.get("app"), t.get("caption", ""))
        for t in tlist:
            spot = self._locate(t["match"], t.get("app"), t.get("caption", ""))
            if spot:
                self.spot_track = (t["match"], t.get("app"), t.get("caption", ""))
                await self._show_spot(spot)
                return True
        return False

    async def _show_spot(self, spot: dict) -> None:
        self.spot_rect = spot["rect"]
        await self.emit("spotlight", spot)

    async def _follow_spot(self) -> None:
        """On a new frame: move the spotlight with its target (only if it moved > 4pt)."""
        if self.spot_track is None or self.passed or self.step is None:
            return
        match, app, caption = self.spot_track
        spot = self._locate(match, app, caption)
        if not spot:
            return
        r, old = spot["rect"], self.spot_rect
        if old and all(abs(r[k] - old[k]) <= 4 for k in ("x", "y", "w", "h")):
            return
        await self._show_spot(spot)

    async def _pass_step(self) -> None:
        step = self.step
        if step is None or self.passed:
            return
        self.passed = True
        nxt = self.steps[self.idx + 1]["id"] if self.idx + 1 < len(self.steps) else None
        payload = {"stepId": step["id"]}
        if nxt:
            payload["nextStepId"] = nxt
        await self.emit("step.passed", payload)
        await self._status("passed")
        await self.emit("spotlight", {"clear": True})
        if nxt:
            self._spawn(self._advance(self.step_gen, self.idx + 1))
        else:
            self.phase = "done"
            await self.emit("video.play", {})

    async def _advance(self, gen: int, idx: int) -> None:
        await asyncio.sleep(self.advance_delay_s)
        if gen == self.step_gen:
            await self.start_step(idx)

    async def force_pass(self) -> None:
        """Debug: mark every check of the active step as passed."""
        step = self.step
        if step is None or self.passed:
            return
        for c in self.display_checks(step):
            await self.emit("check.updated", {"stepId": step["id"], "checkId": c["id"],
                                              "label": c.get("label", c["id"]), "status": "pass",
                                              "detail": "forced"})
        await self._pass_step()

    async def goto_step(self, idx: int) -> None:
        await self.start_step(idx)

    # ------------------------------------------------------------------ learner signals
    def _acted(self) -> None:
        self.last_action_t = self.clock()
        self._touch()
        if self.coaching:  # a real user action makes the pending diagnosis stale: close the stream
            self.m.cancel_coach()

    def learner_idle_s(self) -> float:
        own = self.clock() - self.last_action_t
        v = self.inputs.seconds_since_input() if self.inputs is not None else None
        return own if v is None else min(own, v)

    def typing(self) -> bool:
        v = self.inputs.seconds_since_key() if self.inputs is not None else None
        return v is not None and v < config.TYPING_GUARD_S

    def acted_since_step_start(self) -> bool:
        if self.last_action_t >= self.step_t0:
            return True
        v = self.inputs.seconds_since_input() if self.inputs is not None else None
        return v is not None and v <= self.clock() - self.step_t0

    @staticmethod
    def _sig(failed: list[dict]) -> tuple:
        return tuple(sorted(r.get("checkId", "") for r in failed))

    # ------------------------------------------------------------------ evaluation
    async def evaluate(self, trigger: str) -> None:
        """trigger: start | segment | file | run_end | metric | screen | manual"""
        learner = trigger in ("file", "run_end", "metric")
        async with self._lock:
            step = self.step
            if step is None or self.passed or self.phase != "active":
                return
            if learner or (trigger == "screen" and self.segment_done):
                self.engaged = True  # screen changes count once the clip is over (the learner is working)
            ctx = self.context()
            precision = self.precision_mode()
            try:
                gate = self.m.evaluate_gate(step, ctx, ctx.screen, precision)
            except Exception as e:
                log.exception("evaluate_gate failed")
                if not self._eval_error_sent:  # once per step, not once per frame
                    self._eval_error_sent = True
                    await self.emit("error", {"message": f"Check evaluation failed: {e}"})
                return
            shown_list, other = ("precision", "checks") if self._precision_display(step) else ("checks", "precision")
            results = list(gate.get(shown_list) or [])
            if gate.get("passed") and gate.get("via") != shown_list:  # green by the other route: show it green
                why = "confirmed by your files" if gate.get("via") == "precision" else "confirmed on screen"
                results = [r if r.get("status") == "pass" else {**r, "status": "pass", "detail": why} for r in results]
            self.last_results = results
            failed = [r for r in results if r.get("status") == "fail"]
            if not gate.get("passed"):
                seen = {r.get("checkId") for r in failed}
                failed += [r for r in gate.get(other) or [] if r.get("status") == "fail" and r.get("checkId") not in seen]
            self.last_failed = failed
            n_pass = sum(1 for r in results if r.get("status") == "pass")
            if n_pass > self.best_pass:
                self.best_pass, self.last_progress_t = n_pass, self.clock()
            if failed and learner:
                self.gate_open = True
            await self._publish(step, results)
            if gate.get("passed"):
                if learner or self.acted_since_step_start():
                    await self._pass_step()
                elif self.segment_done and not self.confirm_pending:
                    # the screen says done but we never saw the learner act: ask, don't assert
                    self.confirm_pending = True
                    await self.emit("card", {"stepId": step["id"], "kind": "hint", "title": "Looks done?",
                                             "body": "The checks pass. Confirm and I'll move on.",
                                             "actions": ["confirm"]})
                return
            self.confirm_pending = False
            if failed and trigger in ("file", "run_end"):  # breakpoints
                sig = self._sig(failed)
                repeat = sig == self.last_bp_sig
                self.last_bp_sig = sig
                if trigger == "run_end" or repeat:
                    self._consider_speaking("repeat" if repeat else "breakpoint", step, failed, ctx)

    async def _publish(self, step: dict, results: list[dict]) -> None:
        for r in results:
            cid = r.get("checkId")
            shown = r.get("status", "pending")
            if shown == "fail" and not self.gate_open:
                shown = "pending"
            detail = r.get("detail")
            prev = self.check_state.get(cid)
            label = r.get("label") or (prev or {}).get("label") or cid
            if prev and prev["status"] == shown and prev.get("detail") == detail:
                continue
            self.check_state[cid] = {"label": label, "status": shown, "detail": detail}
            payload = {"stepId": step["id"], "checkId": cid, "label": label, "status": shown}
            if detail:
                payload["detail"] = detail
            await self.emit("check.updated", payload)

    async def tick(self) -> None:
        """Called ~1/s: idle-after-action, stuck, and typing-deferred speech."""
        step = self.step
        if step is None or self.passed or self.coaching or not self.last_failed or not self.engaged:
            return
        async with self._lock:
            if self.step is not step or self.passed:
                return
            ctx = self.context()
            if self.pending_speak and not self.typing():
                reason, self.pending_speak = self.pending_speak, None
                self._consider_speaking(reason, step, self.last_failed, ctx)
                return
            if self.clock() - self.last_progress_t >= config.STUCK_S:
                self.last_progress_t = self.clock()  # one "stuck" per window
                await self._open_gate(step)
                self._consider_speaking("stuck", step, self.last_failed, ctx)
            elif self.learner_idle_s() >= self.idle_gate_s:
                await self._open_gate(step)
                self._consider_speaking("idle", step, self.last_failed, ctx)

    async def _open_gate(self, step: dict) -> None:
        if not self.gate_open:
            self.gate_open = True
            await self._publish(step, self.last_results)

    # ------------------------------------------------------------------ coaching (hint ladder)
    def _code_excerpt(self, step: dict, limit: int = 6000) -> tuple[str, str | None]:
        files = [t.get("file") for t in step.get("targets") or [] if t.get("file")]
        files += [c.get("file") for c in (step.get("checks") or []) + (step.get("precision_checks") or [])
                  if c.get("file")]
        if not files:
            files = [p.name for p in sorted(Path(self.workdir).glob("*.py"))[:1]] if Path(self.workdir).is_dir() else []
        for f in files:
            p = Path(self.workdir) / f
            if p.is_file():
                try:
                    return p.read_text(errors="replace")[:limit], f
                except OSError:
                    continue
        lines = self._screen_lines() or {}  # screen-first: the code the learner is looking at
        for app in [t.get("app") for t in step.get("targets") or [] if t.get("app")] + ["Code"]:
            for a, ls in lines.items():
                if app.lower() in (a or "").lower() and ls:
                    return "\n".join(ls)[:limit], None
        return "", None

    def _consider_speaking(self, reason: str, step: dict, failed: list[dict], ctx: RunContext) -> None:
        """reason: breakpoint | repeat | stuck | idle. Decides whether, and at which ladder level, to speak."""
        if self.coaching or self.passed or not failed:
            return
        if self.typing():
            self.pending_speak = reason  # never talk over the learner's typing; the tick retries
            return
        sig = self._sig(failed)
        if sig != self.spoken_sig:  # a new problem (or the first one): concept card
            level = 2
        elif (self.ladder == 2 and reason in ("repeat", "stuck")
              and self.clock() - self.spoken_t >= config.LADDER_MIN_S):
            level = 3  # same failure again / still stuck: the exact fix + "Do it for me"
        else:
            return
        self.coaching = True
        self.spoken_sig, self.spoken_t = sig, self.clock()
        self._spawn(self._coach(self.step_gen, step, failed, ctx, level))

    def _target_spot(self, target: dict) -> dict | None:
        r = target.get("rect")
        if isinstance(r, (list, tuple)) and len(r) == 4:
            r = {"x": r[0], "y": r[1], "w": r[2], "h": r[3]}
        if not isinstance(r, dict) or not all(k in r for k in ("x", "y", "w", "h")):
            return None
        spot = {"rect": {k: float(r[k]) for k in ("x", "y", "w", "h")}, "caption": target.get("label") or ""}
        if target.get("text"):
            spot["matched"] = str(target["text"])[:200]
        return spot

    async def _screen_for_coach(self, step: dict) -> Any:
        """E5's ScreenContext: OCR boxes + a screenshot + the cursor (+ the step's file/line), or None."""
        if not self.screen_active() or self.last_obs is None or not hasattr(self.screen, "screenshot"):
            return None
        image = await asyncio.to_thread(self.screen.screenshot)
        if image is None:
            return None
        pos = self.inputs.cursor() if self.inputs is not None else None
        if pos is None:
            r = getattr(self.last_obs, "screen", None)
            pos = (getattr(r, "w", 0) / 2, getattr(r, "h", 0) / 2)
        extra: dict[str, Any] = {}
        from .workspace import target_location

        loc = target_location(self.workdir, step)
        if loc:
            extra = {"file": str(loc[0]), "line": loc[1]}
        return self.m.screen_context(self.last_obs, image, pos, **extra)

    def cursor_context(self) -> dict | None:
        from .inputs import text_under

        pos = self.inputs.cursor() if self.inputs is not None else None
        if pos is None:
            return None
        out: dict[str, Any] = {"x": round(pos[0], 1), "y": round(pos[1], 1)}
        under = text_under(self.last_obs, *pos) if self.last_obs is not None else None
        if under:
            out["under"] = under
        return out

    async def _coach(self, gen: int, step: dict, failed: list[dict], ctx: RunContext, level: int) -> None:
        try:
            card = self.full_card if (level == 3 and self.full_card) else None
            if card is None:
                await self._status("thinking")
                by_id = {c["id"]: c for c in (step.get("checks") or []) + (step.get("precision_checks") or [])}
                failed_checks = [{**by_id.get(r.get("checkId"), {}), **r} for r in failed]
                code, _file = self._code_excerpt(step)
                tail = ctx.output_tail[-40:] if isinstance(ctx.output_tail, list) else []
                screen = await self._screen_for_coach(step)

                def on_targets(targets: list[dict]) -> None:  # streamed mid-reply: spotlight before the card lands
                    if gen == self.step_gen and targets and not self.passed:
                        spot = self._target_spot(targets[0])
                        if spot:
                            self._early_spot = True
                            self._spawn(self._show_spot(spot))

                self._early_spot = False
                try:
                    card = await self.m.diagnose(step, failed_checks, ctx.metrics, code, error_text="\n".join(tail),
                                                 cursor=self.cursor_context(), screen=screen, on_targets=on_targets)
                except Exception as e:
                    if gen == self.step_gen:
                        self.spoken_sig = None  # let a later breakpoint try again
                        if "cancelled" in str(e):
                            log.info("diagnosis cancelled: the learner acted")
                        else:
                            log.exception("coach.diagnose failed")
                            await self.emit("error", {"message": f"Coach unavailable: {e}"})
                        await self._status("watching")
                    return
            if gen != self.step_gen or self.passed:
                return
            full = dict(card)
            full.setdefault("stepId", step["id"])
            full.setdefault("severity", "warn")
            full.setdefault("actions", ["explain", "show_me", "hint"])
            self.full_card = full
            if level == 2:  # concept: what's wrong and why, not the patch
                shown = {k: v for k, v in full.items() if k != "diff"}
                shown["actions"] = [a for a in full["actions"] if a != "apply_fix"] or ["explain", "hint"]
            else:
                shown = dict(full)
                if full.get("diff") and "apply_fix" not in shown["actions"]:
                    shown["actions"] = [*shown["actions"], "apply_fix"]
            shown["level"] = level
            self.ladder = level
            self.last_offtrack = full
            await self.emit("offtrack", shown)
            diff = full.get("diff") or {}
            first = (diff.get("yours") or "").strip().splitlines()[:1]
            spot = self._locate(re.escape(first[0]), None, full.get("title", "")) if first else None
            if spot is None and full.get("targets"):  # the coach pointed at screen boxes (set-of-mark)
                spot = self._target_spot(full["targets"][0])
            if getattr(self, "_early_spot", False) and spot is None:
                pass  # the streamed target spotlight is already up
            elif spot:
                self.spot_track = (re.escape(first[0]), None, full.get("title", ""))
                await self._show_spot(spot)
            else:
                await self._spotlight_target(step)
            await self._status("offtrack")
        finally:
            if gen == self.step_gen:
                self.coaching = False

    # ------------------------------------------------------------------ inputs
    async def on_screen(self, obs: Any = None) -> None:
        """A new screen observation (only fires when the screen actually changed)."""
        self._touch()
        if obs is not None:
            self.last_obs = obs
        now = self.clock()
        if obs is not None and now - self._last_seen >= self.seen_interval_s:
            self._last_seen = now
            app = getattr(obs, "app", None) or ""
            lines = self._screen_lines() or {}
            summary = " · ".join((lines.get(app) or [])[:2])[:140]
            await self.emit("screen.seen", {"app": app, "summary": summary, "t": float(getattr(obs, "t", 0) or 0)})
        if self.step is not None:
            await self.evaluate("screen")
            await self._follow_spot()

    def overlay_bounds(self, rects: list[dict]) -> None:
        if self.screen is not None:
            self.screen.set_overlay(rects)

    async def on_file_change(self, paths: list[str] | None = None) -> None:
        self._acted()  # a save is a learner action (and a breakpoint)
        if self.step is not None:
            await self.evaluate("file")

    async def ingest(self, ev: dict) -> None:
        kind = ev.get("kind")
        run_id = str(ev.get("run_id") or "run")
        run = self.runs.get(run_id)
        if kind == "run_started" or run is None:
            if run is None:
                run = RunInfo(run_id=run_id)
                self.runs[run_id] = run
                if self.step is not None and not self.passed:
                    self.step_runs.append(run)
            run.command = ev.get("command", run.command) or run.command
            run.cwd = ev.get("cwd", run.cwd) or run.cwd
        self._touch()
        in_step = run in self.step_runs
        if kind == "run_started":
            if in_step:
                self.engaged = True
                if ev.get("source") != "screen":
                    self._acted()  # the learner launched a run
            return
        if kind in ("metric", "metrics"):
            items = ev.get("metrics") or ev.get("items") or [ev]
            for it in items:
                try:
                    step_n, name = int(it["step"]), str(it["name"])
                    raw = it.get("value")
                    value = None if raw is None or it.get("nonfinite") else float(raw)
                except (KeyError, TypeError, ValueError):
                    continue
                if value is not None and not math.isfinite(value):
                    value = None
                # NaN/inf arrive as None and stay None: a NaN loss must FAIL its metric check, not vanish
                run.add_metric(step_n, name, value)
                if value is not None:  # the app's live curve only takes finite numbers
                    await self.emit("metric", {"runId": run_id, "step": step_n, "name": name, "value": value})
            if in_step:
                self._schedule_metric_eval()
            return
        if kind == "output":
            lines = ev.get("lines") or []
            run.add_output([str(x) for x in lines])
            return
        if kind == "run_ended":
            try:
                run.exit_code = int(ev.get("exit_code", 0))
            except (TypeError, ValueError):
                run.exit_code = 1
            if in_step:
                await self.evaluate("run_end")
            return

    def _schedule_metric_eval(self) -> None:
        if self._metric_eval_pending:
            return
        self._metric_eval_pending = True
        gen = self.step_gen

        async def later() -> None:
            await asyncio.sleep(self.metric_eval_s)
            self._metric_eval_pending = False
            if gen == self.step_gen:  # metrics of a step that already passed must not grade the next one
                await self.evaluate("metric")

        self._spawn(later())

    async def video_state(self, t: float, playing: bool) -> None:
        step = self.step
        if step is None or self.passed:
            return
        self.video_reports += 1
        seg = self._segment(step)
        if seg and not self.segment_done and t >= seg["end"] - 0.3 and t <= seg["end"] + 5:
            await self._segment_end()

    async def action(self, kind: str, text: str | None = None) -> None:
        try:
            await self._action(kind, text)
        except Exception as e:  # live mode: a missing/failing module is reported, never faked
            log.exception("action %s failed", kind)
            await self.emit("error", {"message": f"{kind}: {e}"})
            if self.step is not None:
                await self._status("offtrack" if self.last_offtrack else ("passed" if self.passed else "watching"))

    async def _action(self, kind: str, text: str | None = None) -> None:
        step = self.step
        if step is not None:
            self._acted()
        if kind == "confirm":  # "Apply this fix?" preview, or "Looks done? Confirm"
            if step is not None and self.pending_patch is not None:
                await self._apply_patch(step)
            elif step is not None and self.confirm_pending and not self.passed:
                self.confirm_pending = False
                await self._pass_step()
            return
        if kind == "undo":
            await self._undo_fix()
            return
        if step is None:
            await self.emit("error", {"message": "No lesson is running yet."})
            return
        self._touch()
        if kind == "back":
            idx = self.idx
            seg = self._segment(step)
            if (text or "").strip().lower() in ("prev", "previous") and idx > 0:
                await self.start_step(idx - 1)
                return
            if seg:
                self.segment_done = False
                await self.emit("video.seek", {"t": seg["start"], "play": True})
            return
        if kind == "show_me":
            seg = self._segment(step)
            if seg:
                self.segment_done = False
                await self.emit("video.seek", {"t": seg["start"], "play": True})
            await self._spotlight_target(step)
            return
        if kind in ("explain", "ask"):
            await self._status("thinking")
            card = await self.m.explain(step, text if kind == "ask" else (text or None), self._explain_context())
            card = dict(card)
            card.setdefault("stepId", step["id"])
            await self.emit("card", card)
            await self._status("offtrack" if self.last_offtrack else ("passed" if self.passed else "watching"))
            return
        if kind == "hint":
            card = dict(await self.m.hint(step, self.hint_level, self.last_offtrack))
            card.setdefault("stepId", step["id"])
            self.hint_level += 1
            await self.emit("card", card)
            return
        if kind == "diagram":
            want = (text or "").strip().lower()
            if want not in DIAGRAM_KINDS and not self.m.has_diagrams():  # stubs (DEMO) pick from the failing checks
                metric_fail = any(r.get("status") == "fail" and r.get("checkId") in
                                  {c["id"] for c in step.get("checks", []) if c.get("type", "").startswith("metric")}
                                  for r in self.last_results)
                want = "gradients" if metric_fail or self.last_offtrack else "network"
            await self._status("thinking")
            d = await self.m.diagram(want if want in DIAGRAM_KINDS else None, step, self.context(),
                                     self._diagram_context(step, None if want in DIAGRAM_KINDS else (text or None)))
            d = dict(d)
            d.setdefault("stepId", step["id"])
            await self.emit("diagram", d)
            await self._status("offtrack" if self.last_offtrack else ("passed" if self.passed else "watching"))
            return
        if kind == "voice_toggle":
            self.voice = not self.voice
            return
        if kind == "apply_fix":
            await self._apply_fix(step)
            return
        await self.emit("error", {"message": f"Unknown action: {kind}"})

    def _diagram_context(self, step: dict, question: str | None) -> dict:
        ctx = self._explain_context()
        return {"code": ctx.get("code"), "file": ctx.get("file"), "screen": self._screen_lines(),
                "question": question, "lesson": ctx.get("lesson"),
                "offtrack": {k: (self.last_offtrack or {}).get(k) for k in ("title", "body")} if self.last_offtrack else None}

    async def _prefetch_diagram(self, gen: int, step: dict) -> None:
        """Warm S4's diagram cache for this step so the diagram button is instant (errors are ignored)."""
        await asyncio.sleep(2.0)  # let the step settle (code on screen, video playing)
        if gen != self.step_gen or not self.m.has_diagrams():
            return
        try:
            await self.m.diagram(None, step, self.context(), self._diagram_context(step, None))
        except Exception as e:  # noqa: BLE001 - a prefetch must never surface
            log.info("diagram prefetch skipped: %s", e)

    def _explain_context(self) -> dict:
        code, file = self._code_excerpt(self.step) if self.step else ("", None)
        return {
            "lesson": (self.graph or {}).get("lesson", {}),
            "query": self.query,
            "checks": self.last_results,
            "metrics": metrics_summary(self.context().metrics),
            "metrics_summary": self.context().metrics,  # coach (E5) wants the raw series
            "cursor": self.cursor_context(),  # {x, y, under: {text, app, rect}} in screen points
            "code": code,
            "file": file,
            "offtrack": self.last_offtrack,
        }

    async def _card(self, step: dict, title: str, body: str, kind: str = "hint", **extra: Any) -> None:
        await self.emit("card", {"stepId": step["id"], "kind": kind, "title": title, "body": body, **extra})

    async def _apply_fix(self, step: dict) -> None:
        """"Do it for me": the learner saw the diff on the offtrack card and pressed the button.
        Preview -> confirm -> act -> undo; never types into the editor, never presses Return."""
        diff = (self.last_offtrack or {}).get("diff") or {}
        command = diff.get("command")
        file, yours, expected = diff.get("file"), diff.get("yours"), diff.get("expected")
        if command:  # terminal fix: stage it on the clipboard, the learner presses Enter (never sent for them)
            ok = await self._clipboard(command)
            await self._card(step, "Command copied" if ok else "Run this command",
                             "Paste it in your terminal (⌘V) and press Enter." if ok else command)
            if not (file and yours and expected):
                return  # command-only fix; otherwise continue with the code part below
        if not (file and yours and expected):
            await self._card(step, "No automatic fix", "This one needs your hands. Try a hint.")
            return
        path = Path(file) if Path(file).is_absolute() else Path(self.workdir) / file
        from .inputs import dirty_files

        if path.name in dirty_files(self.last_obs):  # VS Code has unsaved edits: writing would clobber them
            await self._card(step, f"Save {path.name} first", "Press ⌘S, then Do it for me again.")
            return
        try:
            text = path.read_text()
        except OSError as e:
            await self.emit("error", {"message": f"Could not open {file}: {e}"})
            return
        if self.m.has_do_it_for_me():  # E5: a minimal, compiling patch -> preview -> confirm -> apply
            await self._status("thinking")
            try:
                p = await self.m.do_it_for_me(step, path.name, text, self.last_offtrack)
            except Exception as e:
                await self._card(step, "Fix it by hand", f"I couldn't make a safe patch: {e}")
                await self._status("offtrack" if self.last_offtrack else "watching")
                return
            if not p.get("new_text"):
                await self._card(step, "Fix it by hand", p.get("summary") or "No safe patch for this one.")
                return
            self.pending_patch = {"path": path, "old": text, "new": p["new_text"], "line": p.get("line") or 1,
                                  "first": (expected or "").strip().splitlines()[:1]}
            await self._card(step, "Apply this fix?", p.get("summary") or "Here's the change.", kind="answer",
                             diff=p.get("unified_diff", ""), actions=["confirm"])
            await self._status("offtrack" if self.last_offtrack else "watching")
            return
        new_text = self.m.propose_fix(diff, text)
        if new_text is not None and path.suffix == ".py":
            try:
                compile(new_text, str(path), "exec")
            except SyntaxError:
                log.warning("proposed fix for %s does not compile; asking the learner to do it", path.name)
                new_text = None
        if new_text is None or new_text == text:
            await self._card(step, "Fix it by hand", f"Replace `{yours.strip()}` with `{expected.strip()}`.")
            return
        backup_dir = config.REPO_ROOT / "demo" / "runs" / "backups"
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            (backup_dir / f"{path.name}.{int(time.time())}.bak").write_text(text)
        except OSError:
            log.warning("could not write a backup of %s", path)
        self.undo = (path, text)
        path.write_text(new_text)
        line = next((i for i, (a, b) in enumerate(zip(text.splitlines(), new_text.splitlines()), 1) if a != b), 1)
        if self.workspace is not None:
            self.workspace.goto(str(path), line)
        first = expected.strip().splitlines()[0]
        spot = self._locate(re.escape(first), None, "Fixed")
        if spot:
            await self._show_spot(spot)
        await self._card(step, "Fix applied", "Re-run to check it. Undo if you'd rather type it yourself.",
                         kind="answer", actions=["undo"])
        await self.on_file_change([str(path)])

    async def _apply_patch(self, step: dict) -> None:
        """Confirmed preview: re-check (unsaved edits? file changed since the preview?), back up, write."""
        from .inputs import dirty_files

        pp, self.pending_patch = self.pending_patch, None
        path: Path = pp["path"]
        if path.name in dirty_files(self.last_obs):
            await self._card(step, f"Save {path.name} first", "Press ⌘S, then Do it for me again.")
            return
        try:
            current = path.read_text()
        except OSError as e:
            await self.emit("error", {"message": f"Could not open {path}: {e}"})
            return
        if current != pp["old"]:
            await self._card(step, "The file changed", "You edited it after the preview. Ask again for a fresh fix.")
            return
        backup_dir = config.REPO_ROOT / "demo" / "runs" / "backups"
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            (backup_dir / f"{path.name}.{int(time.time())}.bak").write_text(current)
        except OSError:
            log.warning("could not write a backup of %s", path)
        self.undo = (path, current)
        path.write_text(pp["new"])
        if self.workspace is not None:
            self.workspace.goto(str(path), int(pp["line"]))
        if pp["first"]:
            spot = self._locate(re.escape(pp["first"][0]), None, "Fixed")
            if spot:
                await self._show_spot(spot)
        await self._card(step, "Fix applied", "Re-run to check it. Undo if you'd rather type it yourself.",
                         kind="answer", actions=["undo"])
        await self.on_file_change([str(path)])

    async def _undo_fix(self) -> None:
        step = self.step
        if self.undo is None or step is None:
            return
        path, text = self.undo
        self.undo = None
        path.write_text(text)
        await self._card(step, "Undone", "Your version is back.")
        await self.on_file_change([str(path)])

    @staticmethod
    async def _clipboard(text: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec("pbcopy", stdin=asyncio.subprocess.PIPE)
            await proc.communicate(text.encode())
            return proc.returncode == 0
        except OSError:
            return False

    # ------------------------------------------------------------------ reconnect
    def snapshot(self) -> list[tuple[str, dict]]:
        """Messages that bring a freshly connected client up to date."""
        out: list[tuple[str, dict]] = []
        if self.phase == "building" and self.build_progress:  # reconnect mid-build: keep the spinner honest
            out.append(("status", {"state": "thinking"}))
            out.append(("lesson.building", dict(self.build_progress)))
            return out
        if self.graph is None:
            out.append(("status", {"state": "idle" if self.phase != "searching" else self.status}))
            return out
        out.append(("lesson.ready", self._lesson_ready_payload()))
        step = self.step
        if step is not None:
            out.append(("step.started", self._step_started_payload(step)))
            for cid, st in self.check_state.items():
                p = {"stepId": step["id"], "checkId": cid, "label": st["label"], "status": st["status"]}
                if st.get("detail"):
                    p["detail"] = st["detail"]
                out.append(("check.updated", p))
            if self.last_offtrack and not self.passed:
                out.append(("offtrack", self.last_offtrack))
        out.append(("status", {"state": self.status}))
        return out

    def state(self) -> dict:
        step = self.step
        return {
            "phase": self.phase,
            "status": self.status,
            "workdir": self.workdir,
            "lesson": (self.graph or {}).get("lesson"),
            "stepIndex": self.idx,
            "stepId": step["id"] if step else None,
            "step": step,
            "checks": self.check_state,
            "engaged": self.engaged,
            "gateOpen": self.gate_open,
            "segmentDone": self.segment_done,
            "ladder": self.ladder,
            "learnerIdleS": round(self.learner_idle_s(), 1),
            "confirmPending": self.confirm_pending,
            "cursor": self.cursor_context(),
            "runs": [r.run_id for r in self.step_runs],
            "modules": self.m.describe(),
            "precisionMode": self.precision_mode(),
            "screen": bool(self.screen is not None and getattr(self.screen, "active", False)),
            "voice": self.voice,
        }
