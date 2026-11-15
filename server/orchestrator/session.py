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
import contextvars
import copy
import hashlib
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

# The lesson "epoch" a piece of work belongs to. Every spawned task and every app action captures it when it
# starts; the session's emit drops events from work whose epoch is no longer current (e.g. a coach card or a
# diagram that finishes after end_lesson). Unset (None) = not tied to a lesson (end_lesson itself, search...).
_EPOCH: contextvars.ContextVar[int | None] = contextvars.ContextVar("lesson_epoch", default=None)
ALWAYS_SENT = {"lesson.ended"}


def video_id_from_url(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else None


class BuildStage(logging.Handler):
    """Turns the lesson builder's own log lines (server.lesson) into an honest stage label."""

    RULES = [
        ("lesson cache hit", "Loading the saved lesson"),
        ("daily quota exhausted", "Gemini is at its limit; trying another model"),
        ("too slow; switching engine", "Gemini is slow; reading the transcript instead"),
        ("video pass failed", "Couldn't watch the video; reading the transcript instead"),
        ("video pass:", "Writing the steps"),
        ("claude adapt pass", "Fitting the checks to your project"),
        ("adapt attempt", "Fitting the checks to your project"),
        ("lesson built", "Finishing up"),
    ]

    STAGE_LABELS = {  # E2's build_lesson(on_progress=...) stage ids (server.lesson.builder.STAGES)
        "cache_hit": "Loading the saved lesson",
        "watching": "Watching the video",
        "reading_transcript": "Reading the transcript",
        "writing_steps": "Writing the steps",
        "steps_ready": "Writing the steps",
        "adapting": "Fitting the checks to your project",
        "done": "Finishing up",
    }
    SWITCH_LABELS = {
        "quota": "Gemini is rate-limited; using the transcript",
        "slow": "Gemini is slow; using the transcript",
        "key": "No Gemini key; using the transcript",
        "error": "Couldn't watch the video; using the transcript",
        "budget": "Today's Gemini budget is used up — reading the transcript instead",
    }

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.text = "Watching the video"
        self.structured = False  # once the builder reports stages, ignore log matching

    def on_progress(self, stage: str, message: str = "") -> None:
        """E2's progress callback: honest, stable stage ids."""
        self.structured = True
        msg = (message or "").strip()
        if stage == "engine_switch":
            self.text = self.SWITCH_LABELS.get(msg, "Switching to the transcript")
        elif stage == "steps_ready":
            self.text = "Fitting the checks to your project"
        elif stage == "adapting":
            self.text = "Fitting the checks to your project"
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
    # strip our own wrapper ("lesson.build_lesson failed: RuntimeError: ...") so only the builder's words remain
    raw = re.sub(r"^\s*[\w.]+ failed: [\w.]+: ", "", str(e))
    first = raw.strip().splitlines()[0].strip() if raw.strip() else ""
    if first.lower().startswith(("couldn't read this video", "couldn't build", "couldn't watch")) and len(first) < 400:
        return first  # E2's learner-facing sentence (e.g. Gemini credits used up + YouTube blocking transcripts)
    if ("no engine could build the lesson" in raw.lower() and "no engine could build" not in first.lower()
            and len(first) < 300):
        return first  # E2: a learner-facing first line, then the raw detail (which stays in the log)
    low = raw.lower()
    if "gemini budget" in low:  # E2's daily cap (LESSON_GEMINI_DAILY_CAP) and the transcript path failed too
        return "Today's Gemini budget is used up, and I couldn't read this video's transcript. Try another video."
    quota = "quota" in low or "resource_exhausted" in low
    yt_limited = ("429" in low or "too many requests" in low) and ("transcript" in low or "caption" in low)
    if quota and yt_limited:  # E2: "no engine could build the lesson" with both causes
        return ("Couldn't watch this video: Gemini is rate-limited and YouTube is rate-limiting this network. "
                "Try again in a minute, a lesson that's already built, or another network (hotspot).")
    if "took over" in low or "no answer within" in low or isinstance(e, TimeoutError):
        return "Building this lesson is taking too long. Try again, or pick another video."
    if "quota" in low or "resource_exhausted" in low:
        return "Gemini is rate-limited right now, so I couldn't watch this video. Try again in a minute or pick another video."
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


def notebook_sources(text: str) -> str | None:
    """A Jupyter notebook's JSON -> its code cells' source with `# %% [cell N]` markers (N = index among all
    cells, E5's numbering), outputs dropped. Cutting the raw JSON leaves invalid JSON and mostly outputs, so
    excerpts are cut after this. None if the text isn't valid notebook JSON."""
    import json

    try:
        nb = json.loads(text)
    except ValueError:
        return None
    if not isinstance(nb, dict) or not isinstance(nb.get("cells"), list):
        return None
    out = []
    for i, c in enumerate(nb["cells"]):
        if not isinstance(c, dict) or c.get("cell_type") != "code":
            continue
        src = c.get("source") or ""
        src = "".join(src) if isinstance(src, list) else str(src)
        out.append(f"# %% [cell {i}]\n" + src.rstrip("\n"))
    return "\n".join(out) if out else "# (notebook: no code cells)"


def _has_parts(graph: dict | None) -> bool:
    parts = ((graph or {}).get("lesson") or {}).get("parts") or {}
    return bool(parts.get("total") or parts.get("list"))


def is_provisional(graph: dict | None) -> bool:
    """E2's quick-start placeholder (built from the chapter list after 8 s): replaced, never extended."""
    if not graph:
        return False
    lesson = graph.get("lesson") or {}
    return bool(lesson.get("provisional") or lesson.get("builtBy") == "chapters"
                or any(st.get("provisional") for st in graph.get("steps") or []))


CODE_APP_NAMES = {"code", "vs code", "vscode", "visual studio code", "cursor"}


def is_notebook_lesson(graph: dict) -> bool:
    """A lesson done in a notebook (Colab / Jupyter), often in a browser rather than an editor."""
    blob = " ".join([str((graph.get("lesson") or {}).get(k) or "") for k in ("title", "goal")]
                    + [s.get("url") or "" for s in graph.get("sources", [])]).lower()
    if "colab" in blob or "jupyter" in blob:
        return True
    for st in graph.get("steps", []):
        text = f"{st.get('title', '')} {st.get('instructions', '')}".lower()
        if "colab" in text or "jupyter" in text:
            return True
        for x in (st.get("targets") or []) + (st.get("checks") or []) + (st.get("precision_checks") or []):
            if str(x.get("file") or "").endswith(".ipynb"):
                return True
    return False


def unscope_editor_apps(graph: dict) -> None:
    """Screen checks/targets scoped to VS Code also accept any app (the notebook may be open in a browser)."""
    for st in graph.get("steps", []):
        for x in (st.get("targets") or []) + (st.get("checks") or []):
            if str(x.get("app") or "").strip().lower() in CODE_APP_NAMES:
                x.pop("app", None)


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
        self._emit_raw = emit
        self.lesson_epoch = 0  # bumped by load_graph and end_lesson
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
        self.ready_hold_s = float(os.environ.get("ORCH_READY_HOLD_S", "1.5"))
        self.offtrack_grace_s = float(os.environ.get("ORCH_OFFTRACK_GRACE_S", "20"))  # no offtrack this early in a step
        self.check_wait_s = float(os.environ.get("ORCH_CHECK_WAIT_S", "1.2"))  # check_step: wait for a fresh frame

        self.phase = "idle"  # idle | searching | building | active | done
        self.query = ""
        self.results: dict[str, dict] = {}
        self.build_progress: dict | None = None  # last lesson.building payload while a build runs
        self.notebook_lesson = False  # Colab / Jupyter lesson: the browser counts as the workspace
        self._build_task: asyncio.Task | None = None
        self._quiet_cancel = False
        self.editor_open = False  # VS Code opened for this lesson (only after the learner said yes)
        self.awaiting_resume = False  # "Continue where you left off?" shown: the lesson is frozen until answered
        self.reqs: list[dict] | None = None  # S2's setup items for this lesson
        self.resources: list[dict] = []  # S2: files the video links (download button)
        self.waiting_more = False  # passed the last built step of a long video that's still building
        self.skipped_steps: list[str] = []
        self._parts_building = False  # build_lesson itself is still adding parts (non-lazy long video)
        self._extend_task: asyncio.Task | None = None  # E2 lazy parts: the next part being built
        self._extend_failed = False  # extend raised for this lesson: don't retry on every step
        self.pending_pick: dict | None = None  # S8: the picked result awaiting build / pick_another
        self._installing: set[str] = set()  # tools being installed right now (one install per tool)
        self._deferred_installs: list[dict] = []  # pip installs chosen before the lesson folder existed
        self._download_after_build = False  # "Download tutorial files" pressed on the preflight card
        self._setup_card: dict | None = None  # the last setup card sent (re-sent with install status)
        self.graph: dict | None = None
        self.workdir = str(config.default_workdir())
        self.on_workdir: Callable[[str], None] | None = None  # main.py hooks the file watcher here
        self.idx = -1
        self.runs: dict[str, RunInfo] = {}
        self.video_t: float | None = None  # last position the player reported
        self.video_playing = False
        self.judge: Any = None  # E5's StepJudge (made per lesson in load_graph), None without the coach
        self._screen_down_since: float | None = None
        self._screen_notice_sent = False
        self.voice = False
        self.status = "idle"
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._timers: set[asyncio.Task] = set()
        self._metric_eval_pending = False
        self._reset_step_state()

    # ------------------------------------------------------------------ basics
    def _reset_step_state(self) -> None:
        self._placeholder_hold = False
        self.check_state: dict[str, dict] = {}  # what the app was last told, per checkId
        self.last_results: list[dict] = []
        self.last_failed: list[dict] = []
        self._recent_cards: dict[tuple, float] = {}
        self._offtrack_key: tuple | None = None  # (step, level, title) of the last offtrack sent
        self._action_spot = False  # a spotlight from show_me / hint / explain is up
        self._coach_error_sent = False  # "Coach unavailable" at most once per step
        self._coach_backoff = 0.0
        self._coach_retry_at = 0.0
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
        self.confirm_check_ids: list[str] = []  # E5 judge's "Looks done?": the checks `confirm` passes
        self.judged_pass: set[str] = set()  # checks E5's judge saw done on screen (count as passed)
        self._carded_checks: set[str] = set()  # checks a hint / "Not yet" card already covers (no offtrack too)
        self._offtracked_checks: set[str] = set()  # checks an offtrack already covers (no "Not yet" card too)
        self._judging = False
        self._stuck_card_sent = False
        self.segment_end_t: float | None = None
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

    async def emit(self, type_: str, payload: dict | None = None) -> None:
        if type_.startswith("video.") and self.lesson_mode:
            return  # "Just teach me": there is no player
        ep = _EPOCH.get()
        if ep is not None and ep != self.lesson_epoch and type_ not in ALWAYS_SENT:
            log.info("dropped stale %s (lesson epoch %s, now %s)", type_, ep, self.lesson_epoch)
            return
        await self._emit_raw(type_, payload or {})

    def _bind_epoch(self) -> None:
        """Tie the current task's later emits to the current lesson."""
        _EPOCH.set(self.lesson_epoch)

    def _spawn(self, coro, *, timer: bool = False) -> asyncio.Task:
        """Background work, tied to the current lesson epoch. `timer` tasks (long sleeps) are not awaited by drain()."""
        ep = self.lesson_epoch

        async def bound():
            _EPOCH.set(ep)
            return await coro

        t = asyncio.create_task(bound())
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

    async def _offer_editor(self, graph: dict, folder: str) -> None:
        """Ask before opening VS Code or installing anything (S2's setup card), in the background so the
        first step isn't delayed. Lessons that don't happen in an editor never get an open_editor button."""
        self.reqs = None
        self._setup_card = None
        if self.workspace is None or not getattr(self.workspace, "enabled", False):
            return
        self._spawn(self._setup_card_task(graph, folder))

    async def _setup_card_task(self, graph: dict, folder: str) -> None:
        from . import workspace as wsmod

        items, found = await asyncio.gather(  # what it needs (3-6 s first time, cached) + the video's own files
            asyncio.to_thread(wsmod.requirements, graph, folder), asyncio.to_thread(wsmod.find_resources, graph))
        self.resources = found
        if self.lesson_mode:  # the editor is already open: only a card for tools that are really missing
            self.reqs = items or None
            miss = [it for it in items or [] if it.get("needed") and not it.get("ok") and it.get("kind") != "editor"]
            card = wsmod.setup_card(miss) if miss else None
            if card:
                card["actions"] = [a for a in card.get("actions") or [] if a != "open_editor"]
                self._setup_card = card
                await self.emit("card", card)
            await self._maybe_pass_setup_step()
            return
        if items:  # S2: what this lesson needs, what's installed, install recipes (+ "Download tutorial files")
            self.reqs = items
            card = wsmod.setup_card(items, resources=found)
            if card:
                self._setup_card = card
                await self.emit("card", card)
            await self._maybe_pass_setup_step()  # an install step for tools that are already here
            return
        # no setup check available (module missing, no key): a plain offer, only for editor lessons
        if not wsmod.needs_editor(graph):
            return
        label = wsmod.editor_label()  # S2: Cursor when that's the learner's editor
        await self.emit("card", {"kind": "hint", "title": f"Open {label}?",
                                 "body": f"This lesson works in {label}. Open the {Path(folder).name} folder there?",
                                 "actions": ["open_editor"]})

    async def _open_in_browser(self, tool: str) -> None:
        """Open a no-code lesson's web app (the learner pressed its button). Only the lesson's own https URLs."""
        item = next((it for it in self.reqs or [] if it.get("tool") == tool), None)
        url = ((item or {}).get("install") or {}).get("url") or ""
        if not url.startswith("https://"):
            await self.emit("error", {"message": f"No link to open for {tool or 'that app'}."})
            return
        if self.workspace is not None:
            self.workspace.run(["open", url])  # macOS: the default browser

    async def _install(self, tool: str, item: dict | None = None) -> None:
        """Install one setup item (the learner pressed Install). One install per tool at a time. Progress goes
        out as setup.progress AND as the (re-sent) setup/preflight card's body, so it's visible either way.
        pip installs go into the LESSON's own .venv (S2: <lesson folder>/.venv), never the engine's or the
        system's Python; on the preflight card (no lesson folder yet) they wait until the lesson exists."""
        from . import workspace as wsmod

        if item is None:
            items = list(self.reqs or []) + list(((self.pending_pick or {}).get("card") or {}).get("items") or [])
            item = next((it for it in items if it.get("tool") == tool), None)
        if item is None:
            await self.emit("setup.progress", {"tool": tool or "?", "done": True, "ok": False,
                                               "error": "Unknown tool for this lesson"})
            return
        label = item.get("label") or tool
        if tool in self._installing:
            log.info("install %s already running; ignoring the repeat", tool)
            return
        if (item.get("install") or {}).get("method") == "pip" and self.graph is None:
            if all(d.get("tool") != tool for d in self._deferred_installs):
                self._deferred_installs.append(item)
            await self._install_status(f"{label} will be installed into this lesson's own Python environment "
                                       "as soon as the lesson is built.")
            return
        self._installing.add(tool)
        try:
            loop = asyncio.get_running_loop()
            ep = self.lesson_epoch
            last_shown = [0.0]

            def on_line(line: str) -> None:  # installer thread -> loop
                if ep != self.lesson_epoch:
                    return
                text = str(line).strip()[:300]

                def deliver() -> None:
                    self._spawn(self.emit("setup.progress", {"tool": tool, "line": text}))
                    now = self.clock()
                    if text and now - last_shown[0] >= 1.0:  # the card body: at most one update a second
                        last_shown[0] = now
                        self._spawn(self._install_status(f"Installing {label}… {text[:120]}"))

                loop.call_soon_threadsafe(deliver)

            await self.emit("setup.progress", {"tool": tool, "line": f"Installing {label}…"})
            await self._install_status(f"Installing {label}…")
            res = await asyncio.to_thread(wsmod.install, item, self.workdir, on_line)
            done = {"tool": tool, "done": True, "ok": bool(res.get("ok"))}
            for k in ("error", "url", "version"):
                if res.get(k):
                    done[k] = str(res[k])
            await self.emit("setup.progress", done)
            if res.get("ok"):
                status = f"{label} installed ✓"
            else:
                reason = (str(res.get("error") or "unknown error").strip().splitlines() or ["unknown error"])[-1]
                status = f"{label} failed: {reason[:160]}"
            if self.graph is not None:  # re-check so the row flips to installed
                fresh = await asyncio.to_thread(wsmod.requirements, self.graph, self.workdir)
                if fresh:
                    self.reqs = fresh
                    self._setup_card = wsmod.setup_card(fresh)
            await self._install_status(status)
        finally:
            self._installing.discard(tool)

    async def _install_status(self, text: str) -> None:
        """Re-send the card the learner is looking at (setup or preflight) with the install status as its body."""
        base = (self.pending_pick or {}).get("card") if self.pending_pick else self._setup_card
        if not base:
            return
        await self.emit("card", {**base, "body": text})

    async def _run_deferred_installs(self) -> None:
        items, self._deferred_installs = self._deferred_installs, []
        for it in items:
            await self._install(it.get("tool", ""), item=it)

    async def _open_editor(self) -> None:
        if self.workspace is None or self.graph is None:
            return
        from . import workspace as wsmod

        if self.reqs is not None and not wsmod.editor_needed(self.reqs):
            return  # e.g. a Blender/Figma lesson: never open VS Code
        self.workspace.open(self.workdir, force=True)
        self.editor_open = True
        if self.step is not None:
            self.workspace.goto_target(self.workdir, self.step)

    def _prefetch_voice(self) -> None:
        """Synthesize every step's spoken line ahead of time (only while voice is on: it costs TTS credits)."""
        if not self.graph:
            return
        lines = [self.m.voice_line("step.started", self._step_started_payload(st)) for st in self.steps]
        self._spawn(self.m.prefetch_voice([ln for ln in lines if ln]), timer=True)

    def _record(self, kind: str, payload: dict | None = None, step: dict | None = None) -> None:
        """A learning event for Tiger's stats (step_started, check_pass/fail, offtrack, fix_applied, question, step_passed)."""
        step = step or self.step
        seg = self._segment(step) if step else None
        try:
            self.m.record(kind, (self.graph or {}).get("lesson", {}).get("id"), step["id"] if step else None,
                          self.video_t, payload or {}, source_id=(seg or {}).get("videoId") or None)
        except Exception:  # noqa: BLE001 - stats must never break the lesson
            log.exception("record %s failed", kind)

    def _say(self, kind: str, payload: dict) -> None:
        """Voice (when toggled on): speak this event in the background, never over the learner's typing."""
        if not self.voice or self.typing():
            return
        gen = self.step_gen

        async def go() -> None:
            s = await self.m.speak_event(kind, payload)
            if s and (gen == self.step_gen or kind == "step.passed"):
                await self.emit("speak", s)

        self._spawn(go(), timer=True)

    async def _status(self, state: str) -> None:
        self.status = state
        await self.emit("status", {"state": state})

    @property
    def steps(self) -> list[dict]:
        return (self.graph or {}).get("steps", [])

    @property
    def lesson_mode(self) -> bool:
        """A "Just teach me" lesson: no video, the editor full screen, each step spotlights where to type."""
        return ((self.graph or {}).get("lesson") or {}).get("mode") == "lesson"

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
    async def learn(self, query: str, mode: str | None = None) -> None:
        if mode == "lesson":  # "Just teach me": no video search, a text lesson for the goal
            await self.learn_text(query)
            return
        if self.graph is not None or self.phase == "building":
            await self.end_lesson("new lesson")  # a new search cleanly ends the current lesson
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
        if self.results and self.m.has_preflight():  # S8: preflight the top videos now, so the pick is instant
            self.m.prefetch_preflight(list(self.results.values()), self.query)
        self.phase = "idle" if self.graph is None else self.phase
        await self._status("idle")

    async def build_lesson(self, result_ids: list[str]) -> None:
        picked = [self.results[i] for i in result_ids if i in self.results]
        if not picked and self.results:
            picked = [next(iter(self.results.values()))]
        url = picked[0].get("url", "") if picked else ""
        await self._pick(url, picked[0] if picked else None)

    async def learn_url(self, url: str, skip_preflight: bool = False) -> None:
        if skip_preflight:  # e.g. the demo's autostart: no learner pick to confirm
            await self._run_build(url, self.query)
            return
        await self._pick(url, None)

    async def _pick(self, url: str, row: dict | None) -> None:
        """S8 pipeline: pick -> PREFLIGHT card (kind, length, goal match, tools; <= 5 s) -> the learner presses
        build (or pick_another). Without the preflight module: build right away, as before."""
        if not self.m.has_preflight():
            await self._run_build(url, self.query)
            return
        if self.graph is not None or self.building():
            await self.end_lesson("new lesson")
        self.pending_pick = {"url": url, "row": row}
        self.phase = "preflight"
        await self._status("thinking")
        pick = self.pending_pick

        def on_late(res: dict) -> None:  # the full answer after a partial card: replace it while still pending
            if self.pending_pick is pick:
                pick["preflight"] = res
                self._spawn(self._show_preflight(pick, res))

        try:
            res = await self.m.preflight(url, self.query, row, on_late)
        except Exception as e:  # preflight never raises by contract; if it does, don't block the learner
            log.exception("preflight failed")
            res = None
            await self.emit("error", {"message": f"Couldn't check this video first ({e}); building it anyway."})
        if self.pending_pick is not pick:
            return  # ended / replaced meanwhile
        if res is None:
            self.pending_pick = None
            await self._run_build(url, self.query)
            return
        pick["preflight"] = res
        await self._show_preflight(pick, res)
        await self._status("idle")

    async def _show_preflight(self, pick: dict, res: dict) -> None:
        if self.pending_pick is not pick:
            return
        card = self.m.preflight_card(res)
        self.reqs = list(card.get("items") or res.get("items") or []) or self.reqs  # Install on this card uses S2's flow
        pick["card"] = card
        await self.emit("card", card)

    async def _build_pick(self) -> None:
        pick, self.pending_pick = self.pending_pick, None
        if pick is None:
            return
        await self._run_build(pick["url"], self.query, video_meta=self.m.preflight_video_meta(pick.get("preflight")))

    async def _pick_another(self) -> None:
        """Back to the result list: re-send the last search's rows (never searches again), then idle."""
        self.pending_pick = None
        self.phase = "idle"
        for r in self.results.values():
            await self.emit("search.result", r)
        if self.results:
            await self.emit("search.done", {"total": len(self.results)})
        await self._status("idle")  # the app reopens the launcher on the result list

    async def _run_build(self, url: str, goal: str, video_meta: dict | None = None, *,
                         factory: Callable[[], Awaitable[None]] | None = None) -> None:
        """Builds run as their own task so end_lesson / a new learn can cancel them mid-flight."""
        if self.graph is not None:
            await self.end_lesson("new lesson")
        await self.cancel_build()
        task = asyncio.ensure_future(factory() if factory is not None else self._build(url, goal, video_meta))
        self._build_task = task
        try:
            await task
        except asyncio.CancelledError:
            cur = asyncio.current_task()
            if cur is not None and cur.cancelling():
                raise  # we ourselves are being cancelled (shutdown)
        finally:
            if self._build_task is task:
                self._build_task = None

    def building(self) -> bool:
        return self._build_task is not None and not self._build_task.done()

    async def cancel_build(self) -> None:
        """Cancel an in-flight build quietly (the caller reports what happens next)."""
        task = self._build_task
        if task is None or task.done():
            return
        self._quiet_cancel = True
        task.cancel()
        try:
            await task
        except BaseException:  # noqa: BLE001 - cancelled on purpose
            pass
        finally:
            self._quiet_cancel = False

    async def end_lesson(self, reason: str = "end_lesson") -> None:
        """Stop everything: cancel the build / diagnosis / timers, clear spotlight + video, record it,
        then `lesson.ended` + `status idle`. Safe to call when nothing is running."""
        token = _EPOCH.set(None)  # end_lesson's own messages must always go out, whoever calls it
        try:
            await self._end_lesson(reason)
        finally:
            _EPOCH.reset(token)

    async def _end_lesson(self, reason: str) -> None:
        lesson_id = (self.graph or {}).get("lesson", {}).get("id")
        had_lesson = self.graph is not None
        await self.cancel_build()
        self.m.cancel_coach()
        if self.screen is not None:
            self.screen.unwatch()
        if had_lesson:
            self._record("lesson_ended", {"reason": reason})
            self.m.clear_diagrams()  # no diagram (or prefetch) may leak into the next lesson
        self.lesson_epoch += 1  # anything still running for the old lesson can no longer emit
        me = asyncio.current_task()
        for t in list(self._timers) + list(self._tasks):
            if t is not me:
                t.cancel()
        self._reset_step_state()  # bumps step_gen: stale coach/metric/advance tasks become no-ops
        self.graph, self.idx, self.phase, self.runs = None, -1, "idle", {}
        self.pending_patch, self.undo, self.build_progress = None, None, None
        self.pending_pick = None
        self._deferred_installs, self._setup_card = [], None
        self.editor_open = False
        self.awaiting_resume = False
        self.waiting_more = False
        self._extend_task, self._extend_failed = None, False
        self._download_after_build = False
        if had_lesson:
            await self.emit("spotlight", {"clear": True})
            await self.emit("video.pause", {})
        await self.emit("lesson.ended", {**({"lessonId": lesson_id} if lesson_id else {}), "reason": reason})
        await self._status("idle")

    async def _build(self, url: str, goal: str, video_meta: dict | None = None) -> None:
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
            expected = float(os.environ.get("ORCH_BUILD_EXPECTED_S", "45"))  # E2: first steps ~25-58 s (long videos: part 1)
            while not done.is_set():
                el = self.clock() - t0
                # message = the stage only (changes when the stage does); the timer travels in elapsedS
                self.build_progress = {"message": stage.text, "progress": round(min(0.95, el / expected), 2),
                                       "elapsedS": round(el, 1)}
                await self.emit("lesson.building", self.build_progress)
                try:
                    await asyncio.wait_for(done.wait(), self.build_tick_s)
                except TimeoutError:
                    pass

        tick = asyncio.create_task(ticker())
        from . import workspace as wsmod

        ok = False
        progressive = {"loaded": False}
        updates = asyncio.Lock()  # E2's quick-start timer and the build call on_update from different tasks

        async def on_update(g: dict, complete: bool) -> None:
            async with updates:  # one at a time, in order: the real lesson must never overtake the placeholder
                await on_update_locked(g, complete)

        async def on_update_locked(g: dict, complete: bool) -> None:
            """E2, long videos (> 30 min): the first part's steps arrive first -> start the lesson now;
            later parts append steps -> lesson.updated. Quick start: a provisional placeholder is REPLACED."""
            if not progressive["loaded"]:
                progressive["loaded"] = True
                done.set()
                self.build_progress = {"message": "Setting up your project folder", "progress": 0.97}
                await self.emit("lesson.building", self.build_progress)
                first = copy.deepcopy(g)
                folder = await asyncio.to_thread(wsmod.prepare, first, goal)
                if folder:
                    first.setdefault("lesson", {})["workdir"] = folder
                self.build_progress = None
                await self.emit("lesson.building", {"message": "First steps ready; the rest builds while you work",
                                                    "progress": 1.0})
                await asyncio.sleep(self.ready_hold_s)  # let the "ready" moment be seen before the lesson UI
                await self.load_graph(first)
                return
            if is_provisional(self.graph) and not is_provisional(g):
                await self._replace_provisional(g, complete)  # E2 quick start: the real lesson replaces s1
                return
            await self._extend_lesson(g, complete)

        try:
            self._parts_building = True
            try:
                with stage.listening():
                    graph = await self.m.build_lesson(url, goal, wsmod.build_workdir(url, goal),
                                                      on_progress=stage.on_progress, on_update=on_update,
                                                      video_meta=video_meta)
            finally:
                self._parts_building = False
            # E2 lazy parts: a long video comes back with complete=false and later parts "pending"
            complete = (graph.get("lesson") or {}).get("complete") is not False
            if progressive["loaded"]:  # already running: make sure every built part made it in
                async with updates:
                    if is_provisional(self.graph) and not is_provisional(graph):
                        await self._replace_provisional(graph, complete)
                    else:
                        await self._extend_lesson(graph, complete)
                self._maybe_extend()
                ok = True
                return
            done.set()
            await tick
            self.build_progress = {"message": "Setting up your project folder", "progress": 0.97}
            await self.emit("lesson.building", self.build_progress)
            folder = await asyncio.to_thread(wsmod.prepare, graph, goal)  # S2: starter files (Claude), 0-25 s
            if folder:
                graph.setdefault("lesson", {})["workdir"] = folder
            self.build_progress = None
            await self.emit("lesson.building", {"message": "Lesson ready", "progress": 1.0})
            await asyncio.sleep(self.ready_hold_s)  # let the "ready" moment be seen before the lesson UI
            ok = True
        except BaseException as e:
            if isinstance(e, Exception) and progressive["loaded"] and self.graph is not None:
                log.exception("building the rest of the lesson failed")  # the lesson keeps its finished parts
                await self.emit("error", {"message": "Couldn't build the rest of this lesson; you can finish the steps you have."})
                await self._extend_lesson({**self.graph, "lesson": {**self.graph.get("lesson", {}), "complete": True}}, True)
                ok = True
                return
            if isinstance(e, Exception):
                log.exception("build_lesson failed")
                await self._build_failed(human_build_error(e))
                return
            if self._quiet_cancel:  # end_lesson / a new learn: they report what happens next
                raise
            log.warning("lesson build interrupted")
            await asyncio.shield(self._build_failed("The lesson build was interrupted. Try again."))
            raise
        finally:
            done.set()
            if not tick.done():
                tick.cancel()
            if not ok:
                self.phase = "idle" if self.graph is None else self.phase
        await self.load_graph(graph)

    # ---------------------------------------------------------- "Just teach me" (no video)
    async def learn_text(self, goal: str) -> None:
        if self.graph is not None or self.phase in ("building", "searching"):
            await self.end_lesson("new lesson")
        self.query = goal
        self.results, self.pending_pick = {}, None
        await self._run_build("", goal, factory=lambda: self._build_text(goal))

    @staticmethod
    def _as_text_lesson(g: dict) -> dict:
        new = copy.deepcopy(g)
        new.setdefault("lesson", {})["mode"] = "lesson"
        for st in new.get("steps", []):
            st.pop("video", None)
        return new

    async def _build_text(self, goal: str) -> None:
        """E2's build_text_lesson: step 1 arrives first (on_update) and the lesson starts on it; the rest are
        appended (lesson.updated). Same progress / failure handling as a video build, minus the player."""
        self.phase = "building"
        await self._status("thinking")
        t0 = self.clock()
        state = {"text": "Planning your lesson", "loaded": False}
        done = asyncio.Event()

        async def ticker() -> None:
            p = 0.05
            while not done.is_set():
                p = min(0.9, p + 0.02)
                self.build_progress = {"message": state["text"], "progress": round(p, 2),
                                       "elapsedS": int(self.clock() - t0)}
                await self.emit("lesson.building", self.build_progress)
                try:
                    await asyncio.wait_for(done.wait(), self.build_tick_s)
                except TimeoutError:
                    pass

        tick = asyncio.create_task(ticker())
        from . import workspace as wsmod

        async def start(g: dict) -> None:
            state["loaded"] = True
            done.set()
            self.build_progress = {"message": "Setting up your project folder", "progress": 0.97}
            await self.emit("lesson.building", self.build_progress)
            first = self._as_text_lesson(g)
            folder = state.get("folder") or await asyncio.to_thread(wsmod.prepare, first, goal)  # S2: folder + starters
            if folder:
                first["lesson"]["workdir"] = folder
            self.build_progress = None
            await self.emit("lesson.building", {"message": "Lesson ready", "progress": 1.0})
            await asyncio.sleep(self.ready_hold_s)
            await self.load_graph(first)

        async def on_update(g: dict, complete: bool) -> None:
            if not state["loaded"]:
                state["text"] = "Writing the first step"
                await start(g)
                return
            await self._extend_lesson(self._as_text_lesson(g), complete)

        labels = {"planning": "Planning your lesson", "first_steps": "Writing the first step",
                  "more_steps": "Writing the next steps", "cache_hit": "Loading the saved lesson"}

        def on_progress(stage: str, message: str = "") -> None:  # E2's stage ids
            if stage in labels and not state["loaded"]:
                state["text"] = labels[stage]

        ok = False
        try:
            state["text"] = "Setting up your project folder"
            # S2 first: the builder adapts the steps to the starter files it finds in the lesson folder
            seed = {"lesson": {"id": "text-" + hashlib.sha1(goal.strip().lower().encode()).hexdigest()[:10],
                               "title": goal, "goal": goal, "mode": "lesson"}, "steps": [], "sources": []}
            state["folder"] = await asyncio.to_thread(wsmod.prepare, seed, goal)
            state["text"] = "Planning your lesson"
            graph = await self.m.build_text_lesson(goal, state["folder"] or wsmod.build_workdir("", goal),
                                                   on_update=on_update, on_progress=on_progress)
            if state["loaded"]:
                await self._extend_lesson(self._as_text_lesson(graph), True)
            else:
                await start(graph)
            ok = True
        except BaseException as e:
            if isinstance(e, Exception) and state["loaded"] and self.graph is not None:
                log.exception("building the rest of the text lesson failed")
                await self.emit("error", {"message": "Couldn't write the rest of this lesson; you can finish the steps you have."})
                await self._extend_lesson({**self.graph, "lesson": {**self.graph.get("lesson", {}), "complete": True}}, True)
                ok = True
                return
            if isinstance(e, Exception):
                log.exception("build_text_lesson failed")
                await self._build_failed(human_build_error(e).replace("this video", "this lesson"))
                return
            if self._quiet_cancel:
                raise
            await asyncio.shield(self._build_failed("The lesson build was interrupted. Try again."))
            raise
        finally:
            done.set()
            if not tick.done():
                tick.cancel()
            if not ok:
                self.phase = "idle" if self.graph is None else self.phase

    async def _open_editor_full(self, folder: str) -> None:
        """Lesson mode: the editor IS the lesson, so it opens (full screen) without asking."""
        if self.workspace is None:
            return
        await asyncio.to_thread(self.workspace.open, folder, True, True)
        self.editor_open = True

    def _snippet(self, step: dict | None) -> dict:
        code = (step or {}).get("code") or ""
        return {"snippet": code[:1200]} if self.lesson_mode and code.strip() else {}

    def _type_caption(self, step: dict, target: dict | None = None) -> str:
        cap = (target or {}).get("caption") or ""
        if cap:
            return cap
        file = self._step_file(step)
        return f"Type this in {file}" if file else "Type this here"

    async def _lesson_spot(self, gen: int, step: dict, tries: int = 8) -> None:
        """Lesson mode, step start: box where to type (the target line), dim the rest, caption + snippet.
        The editor may still be opening: retry for a few seconds; the tracked target then follows the screen."""
        for _ in range(max(1, tries)):
            if gen != self.step_gen or self.passed:
                return
            if await self._spotlight_target(step):
                return
            if (spot := await self._editor_line_spot(step)) is not None:
                await self._show_spot(spot)
                return
            await asyncio.sleep(1.0)  # no whole-window box: the exact line, or nothing

    async def _editor_line_spot(self, step: dict) -> dict | None:
        """S2 + E6: the exact editor line of the step's target (Accessibility, else E6's locate_line on the OCR'd
        gutter). Scrolled off: jump there (`-g file:line`) and ask once more. Only with the real screen reader
        (never in tests: it reads the real editor)."""
        if getattr(self.screen, "reader", None) is None:
            return None
        from . import workspace as wsmod

        loc = wsmod.target_location(self.workdir, step)
        if loc is None:
            return None
        path, line = loc
        where = await asyncio.to_thread(wsmod.line_location, path, line)
        if not where.get("rect") and (where.get("direction") or where.get("reason") == "not_visible"):
            if self.workspace is not None and self.editor_open:
                self.workspace.goto(str(path), line)
                await asyncio.sleep(0.4)
                where = await asyncio.to_thread(wsmod.line_location, path, line)
        r = where.get("rect")
        if not r:
            return None
        target = next((t for t in step.get("targets") or [] if t.get("match")), None)
        return {"rect": {k: float(r[k]) for k in ("x", "y", "w", "h")}, "caption": self._type_caption(step, target),
                **self._snippet(step)}

    def _ensure_step_file(self, step: dict) -> None:
        """Lesson mode: the step's file exists in the lesson folder before it starts, so step 1 is "type this"
        (never "mkdir … && touch …" in a terminal)."""
        from . import workspace as wsmod

        rel = (self._step_file(step) or step.get("file") or "").strip()
        if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts or not Path(self.workdir).is_dir():
            return
        if wsmod.resolve_file(self.workdir, rel) is not None:
            return
        p = Path(self.workdir) / rel
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch(exist_ok=True)
            log.info("lesson mode: created %s", p)
        except OSError as e:
            log.warning("could not create %s: %s", p, e)

    async def _replace_provisional(self, g: dict, complete: bool) -> None:
        """E2 quick start: the placeholder lesson (one step 'watch and type along', shown after 8 s) is
        replaced by the real one with the same ids; the learner keeps watching, the checklist becomes real."""
        if self.graph is None:
            return
        new = copy.deepcopy(g)
        new.setdefault("lesson", {})["workdir"] = self.graph.get("lesson", {}).get("workdir") or self.workdir
        new["lesson"]["complete"] = bool(complete or new["lesson"].get("complete"))
        new["lesson"]["provisional"] = False  # the app drops the placeholder on this lesson.ready
        for st in new.get("steps", []):
            st.pop("provisional", None)
        log.info("quick start: the real lesson (%d steps) replaces the placeholder", len(new.get("steps", [])))
        idx = 0  # the placeholder had one step: the learner restarts on the REAL s1
        self.graph = new
        self.m.set_lesson(new)
        await self.emit("lesson.ready", self._lesson_ready_payload())
        self.waiting_more = False  # even if they skipped the placeholder: the real s1 starts now
        if self.steps:
            seg = self._segment(self.steps[min(idx, len(self.steps) - 1)])
            keep = self.video_t if (seg and self.video_t is not None and seg["start"] <= self.video_t < seg["end"]) else None
            await self.start_step(min(idx, len(self.steps) - 1), seek_to=keep)  # keep the video where it is

    async def _extend_lesson(self, g: dict, complete: bool) -> None:
        """Append a progressive build's new steps to the running lesson (ids never change, earlier steps are
        never edited) and tell the app; a learner waiting at the end of the built part moves on."""
        if self.graph is None:
            return
        known = {st["id"] for st in self.steps}
        new = [copy.deepcopy(st) for st in g.get("steps", []) if st["id"] not in known]
        self.graph["steps"].extend(new)
        lesson = self.graph.setdefault("lesson", {})
        for k in ("parts", "builtBy", "goalMatch"):
            if k in (g.get("lesson") or {}):
                lesson[k] = copy.deepcopy(g["lesson"][k])
        was_complete = lesson.get("complete") is True
        lesson["complete"] = bool(complete or (g.get("lesson") or {}).get("complete"))
        if not new and (not complete or was_complete):
            return  # nothing changed: no empty lesson.updated
        payload: dict[str, Any] = {"steps": [self._step_summary(st, i) for i, st in
                                             enumerate(self.steps) if st["id"] in {n["id"] for n in new}],
                                   "complete": lesson["complete"]}
        parts = lesson.get("parts") or {}
        if parts:
            payload["parts"] = {k: parts.get(k) for k in ("done", "failed", "total") if k in parts}
        await self.emit("lesson.updated", payload)
        if self.waiting_more and self.step is not None:
            if self.idx + 1 < len(self.steps):
                self.waiting_more = False
                await self.start_step(self.idx + 1)
            elif lesson["complete"]:
                self.waiting_more = False
                self.phase = "done"
                await self.emit("video.play", {})

    async def _build_failed(self, message: str) -> None:
        self.build_progress = None
        self.phase = "idle" if self.graph is None else "active"
        await self.emit("error", {"message": message})
        await self.emit("lesson.building", {"message": message, "progress": 0.0, "failed": True})
        await self._status("idle" if self.graph is None else "watching")

    async def load_graph(self, graph: dict) -> None:
        self.lesson_epoch += 1
        self._bind_epoch()  # this task (the build / autostart) now speaks for the new lesson
        self.notebook_lesson = is_notebook_lesson(graph)
        if self.notebook_lesson:
            unscope_editor_apps(graph)  # Colab/Jupyter in a browser counts, not just VS Code
        self.graph = graph
        self.runs = {}
        self._extend_failed = False
        self.skipped_steps = []  # ids the learner skipped (S7 saves them apart from passed steps)
        self.judge = self.m.make_step_judge()
        new_wd = str(config.resolve_workdir(graph.get("lesson", {}).get("workdir")))
        self.workdir = new_wd
        if self.on_workdir:
            self.on_workdir(new_wd)
        self.m.set_lesson(graph)
        self._spawn(self.m.warm(), timer=True)  # pre-warm the coach's cached lesson prefix
        if self.voice:
            self._prefetch_voice()
        await self.emit("lesson.ready", self._lesson_ready_payload())
        self.editor_open = False
        if self.lesson_mode:
            await self._open_editor_full(new_wd)
        await self.start_step(0)
        await self._offer_editor(graph, new_wd)  # after step.started (the app clears cards on a new step)
        if self._deferred_installs:  # pip installs picked on the preflight card: now there's a lesson .venv
            self._spawn(self._run_deferred_installs())
        if self._download_after_build:  # "Download tutorial files" on the preflight card
            self._download_after_build = False
            self._spawn(self.action("download"))

    def _step_summary(self, st: dict, i: int) -> dict:
        summary = {"id": st["id"], "index": st.get("index", i), "title": st["title"]}
        seg = self._segment(st)
        if seg:
            summary["video"] = seg
        return summary

    def _lesson_ready_payload(self) -> dict:
        g = self.graph or {}
        lesson = g.get("lesson", {})
        sources = [
            {k: v for k, v in s.items() if k in ("id", "kind", "title", "url", "meta", "videoId")}
            for s in g.get("sources", [])
        ]
        steps = [self._step_summary(st, i) for i, st in enumerate(self.steps)]
        info: dict[str, Any] = {"id": lesson.get("id", "lesson"), "title": lesson.get("title", "Lesson"), "sources": sources}
        for k in ("complete", "builtBy", "mode", "provisional"):  # E2: progressive builds / who watched the video / no-video lesson
            if k in lesson:
                info[k] = lesson[k]
        if lesson.get("goalMatch"):
            info["goalMatch"] = lesson["goalMatch"]
        return {"lesson": info, "steps": steps}

    # ------------------------------------------------------------------ steps
    def _action_line(self, step: dict) -> str:
        """ONE concrete thing to do now, for the app to show under the current chapter: E2's own `action`, else
        "Create <file> and type <first line>" from the step's code, else the instructions' first sentence."""
        for k in ("action", "todo"):
            if isinstance(step.get(k), str) and step[k].strip():
                return step[k].strip()
        code, file = (step.get("code") or "").strip(), (step.get("file") or self._step_file(step) or "").strip()
        first = next((ln.strip() for ln in code.splitlines() if ln.strip() and not ln.strip().startswith("#")), "")
        if first and file:
            from . import workspace as wsmod

            exists = Path(self.workdir).is_dir() and wsmod.resolve_file(self.workdir, file) is not None
            more = " …" if len([ln for ln in code.splitlines() if ln.strip()]) > 1 else ""
            line = first if len(first) <= 60 else first[:57] + "…"
            return (f"In {Path(file).name}, type {line}{more}" if exists
                    else f"Create {Path(file).name} and type {line}{more}")
        text = " ".join((step.get("instructions") or "").split())
        m = re.match(r"(.+?[.!?])(\s|$)", text)
        sent = m.group(1) if m else text
        words = sent.split()
        return " ".join(words[:20]) + ("…" if len(words) > 20 else "")

    def _step_started_payload(self, step: dict) -> dict:
        full = step.get("instructions", "")
        action = self._action_line(step) or full
        p = {"stepId": step["id"], "index": step.get("index", self.idx), "title": step["title"],
             "instructions": action}
        if full and " ".join(full.split()) != action:
            p["details"] = full  # the step's full explanation (the app may show it on expand)
        seg = self._segment(step)
        if seg:
            p["video"] = seg
        return p

    async def start_step(self, idx: int, seek_to: float | None = None) -> None:
        """seek_to: resume mid-segment (a restored session) instead of from the segment's start."""
        if not (0 <= idx < len(self.steps)):
            return
        self.idx = idx
        self.phase = "active"
        self._reset_step_state()
        step = self.steps[idx]
        if self.lesson_mode:
            self._ensure_step_file(step)  # before the payload: step 1 reads "In calc.py, type …"
        started = self._step_started_payload(step)
        await self.emit("step.started", started)
        self._say("step.started", started)
        self._maybe_extend()  # E2 lazy parts: nearing the last built step -> build the next part now
        self._record("step_started", {"title": step.get("title")}, step)
        for c in self.display_checks(step):
            self.check_state[c["id"]] = {"label": c.get("label", c["id"]), "status": "pending", "detail": None}
            await self.emit("check.updated", {"stepId": step["id"], "checkId": c["id"],
                                              "label": c.get("label", c["id"]), "status": "pending"})
        seg = self._segment(step)
        resuming = seek_to is not None and seg is not None and seg["start"] <= seek_to < seg["end"]
        if seg is None or not (resuming or self._video_needed(step, seg)):
            seg = None  # setup / nothing to watch: the video stays where it is (Show me still plays it)
            self.segment_done = True
            self.segment_end_t = self.clock()
        self._watch_screen_metrics(step)
        if self.m.has_diagrams() and os.environ.get("ORCH_DIAGRAM_PREFETCH", "1") == "1":
            self._spawn(self._prefetch_diagram(self.step_gen, step), timer=True)
        if self.workspace is not None and self.editor_open:  # `code -g` would itself launch VS Code
            self.workspace.goto_target(self.workdir, step)
        await self._status("watching")
        await self.evaluate("start")
        if seg is not None and not self.passed and self.step is step:
            ahead = any(r.get("status") == "pass" for r in self.last_results)  # already doing it: don't replay
            if not ahead or resuming:
                t0 = float(seek_to) if resuming else seg["start"]
                play = not self.typing()  # never start the video over the learner's typing
                await self.emit("video.seek", {"t": t0, "play": play})
                if play:
                    await self.emit("video.play", {})
                self._spawn(self._segment_timer(self.step_gen, seg["end"] - t0), timer=True)
            else:
                self.segment_done = True
                self.segment_end_t = self.clock()
                await self.evaluate("start")  # already done before the clip: ask "Looks done?" now
        await self._maybe_pass_setup_step()
        if self.lesson_mode and not self.passed and self.step is step:
            self._spawn(self._lesson_spot(self.step_gen, step), timer=True)

    MIN_SEGMENT_S = 3.0

    def _video_needed(self, step: dict, seg: dict) -> bool:
        """Play the clip only when it teaches something: not for setup / install steps (E2 tags them setup: true)
        and not for a sliver of video."""
        if step.get("setup") or self.SETUP_STEP.search(step.get("title", "")):
            return False
        return seg["end"] - seg["start"] >= self.MIN_SEGMENT_S

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
        self.segment_end_t = self.clock()
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
            self.spot_track = (t["match"], None if self.lesson_mode else t.get("app"), t.get("caption", ""))
        for t in tlist:
            cap = self._type_caption(step, t) if self.lesson_mode else t.get("caption", "")
            app = None if self.lesson_mode else t.get("app")  # lesson mode: whichever editor they use
            spot = self._locate(t["match"], app, cap)
            if spot:
                self.spot_track = (t["match"], app, cap)
                await self._show_spot({**spot, **self._snippet(step)})
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
        if any(t.get("match") == match for t in self.step.get("targets") or []):
            spot = {**spot, **self._snippet(self.step)}  # lesson mode: the step's own target keeps its snippet
        await self._show_spot(spot)

    async def _pass_step(self, skipped: bool = False) -> None:
        """skipped: the learner pressed Skip (action skip_step): move on, but it's not a pass (never green)."""
        step = self.step
        if step is None or self.passed:
            return
        if step.get("provisional") or is_provisional(self.graph):
            # E2 quick start: the placeholder is watch-along only. It never passes or pends: at the end of its
            # clip we hold quietly until the real lesson replaces it (_replace_provisional starts the real s1).
            if not self._placeholder_hold:
                self._placeholder_hold = True
                await self._status("thinking")
            return
        self.passed = True
        nxt = self.steps[self.idx + 1]["id"] if self.idx + 1 < len(self.steps) else None
        more_coming = nxt is None and (self.graph or {}).get("lesson", {}).get("complete") is False
        payload: dict[str, Any] = {"stepId": step["id"]}
        if nxt:
            payload["nextStepId"] = nxt
        if more_coming:
            payload["pending"] = True  # the next part of a long video is still being built
        if skipped:
            payload["skipped"] = True
            self.m.cancel_coach()
            if step["id"] not in self.skipped_steps:
                self.skipped_steps.append(step["id"])  # a diagnosis for the step they left is no longer wanted
        await self.emit("step.passed", payload)
        if not skipped:
            self._say("step.passed", payload)
        self._record("step_skipped" if skipped else "step_passed", {"nextStepId": payload.get("nextStepId")}, step)
        await self._status("watching" if skipped else "passed")
        await self.emit("spotlight", {"clear": True})
        if nxt:
            self._spawn(self._advance(self.step_gen, self.idx + 1))
        elif more_coming and not self._more_in_flight():
            await self._finish_partial(step)  # nothing can build the rest (DEMO / extend failed): finish here
        elif more_coming:
            self.waiting_more = True  # _extend_lesson starts the next step when it arrives
            await self._status("thinking")
            parts = (self.graph or {}).get("lesson", {}).get("parts") or {}
            if parts.get("total") or parts.get("list"):  # only a real long-video part build gets this card
                done, total = int(parts.get("done") or 0), int(parts.get("total") or 0)
                where = f" (part {min(done + 1, total)} of {total})" if total else ""
                await self._emit_card({"stepId": step["id"], "kind": "hint", "title": "Building the next part…",
                                       "body": f"The next part of this video is being built{where}. "
                                               "Keep watching; its steps start here as soon as they're ready."})
            await self.emit("video.play", {})  # the video keeps playing meanwhile
        else:
            self.phase = "done"
            await self.emit("video.play", {})

    # ---------------------------------------------------------- E2 lazy parts (long videos)
    def _more_in_flight(self) -> bool:
        """Is anything building more steps for this lesson (the build itself, or an extend)? Starts an
        extend if one is due."""
        self._maybe_extend()
        return (self.building() or self._parts_building
                or (self._extend_task is not None and not self._extend_task.done()))

    def _maybe_extend(self) -> None:
        """Near the last built step of a lazily built long video, build the next part in the background
        (one Gemini call per part the learner actually reaches)."""
        g = self.graph
        if (g is None or self._parts_building or self.building() or self._extend_failed
                or (self._extend_task is not None and not self._extend_task.done())
                or (g.get("lesson") or {}).get("complete") is not False
                or is_provisional(g)  # a placeholder is replaced by the running build, never extended
                or not _has_parts(g)):  # only lazily built long videos have parts to extend
            return
        step = self.step
        cur = step.get("index", self.idx) if step else self.idx
        if not self.m.lesson_needs_more(g, cur):
            return
        self._extend_task = self._spawn(self._extend_parts(g))

    async def _extend_parts(self, graph: dict) -> None:
        try:
            g = await self.m.extend_lesson(copy.deepcopy(graph), on_update=self._extend_lesson)
        except Exception as e:
            log.exception("building the next part failed")
            self._extend_failed = True
            if self.graph is not None and self.waiting_more and self.step is not None:
                await self.emit("error", {"message": f"Couldn't build the next part of this video: {human_build_error(e)}"})
                await self._finish_partial(self.step)
            return
        self._extend_task = None
        if self.graph is None:
            return
        await self._extend_lesson(g, (g.get("lesson") or {}).get("complete") is not False)
        self._maybe_extend()  # a skipped / failed part, or still close to the end: the next one

    async def _finish_partial(self, step: dict) -> None:
        """The rest of the video can't be built now: the lesson ends at the steps it has."""
        self.waiting_more = False
        if self.graph is not None:
            self.graph.setdefault("lesson", {})["complete"] = True
        self.phase = "done"
        await self._status("passed")
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
        if self._action_spot:  # a show_me / hint / explain spotlight: done its job once the learner acts
            self._action_spot = False
            self.spot_track = None
            self._spawn(self.emit("spotlight", {"clear": True}))
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
        """trigger: start | segment | file | run_end | metric | screen | manual | check (the learner asked)"""
        learner = trigger in ("file", "run_end", "metric", "check", "judge")
        if self.awaiting_resume:
            return  # frozen until the learner picks Continue / Start new
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
            if gate.get("passed") and gate.get("via") == "precision":
                # a visible error (a failing screen_absent check, e.g. "Failed to compile" / a Traceback) vetoes
                # the files-only route: the files can be right while the app on screen is broken
                kinds = {c["id"]: c.get("type") for c in step.get("checks") or []}
                if any(r.get("status") == "fail" and kinds.get(r.get("checkId")) == "screen_absent"
                       for r in gate.get("checks") or []):
                    gate = {**gate, "passed": False, "via": None}
            shown_list, other = ("precision", "checks") if self._precision_display(step) else ("checks", "precision")
            results = list(gate.get(shown_list) or [])
            if gate.get("passed") and gate.get("via") != shown_list:  # green by the other route: show it green
                why = "confirmed by your files" if gate.get("via") == "precision" else "confirmed on screen"
                results = [r if r.get("status") == "pass" else {**r, "status": "pass", "detail": why} for r in results]
            if self.judged_pass:  # E5's judge saw these done on screen: they count like any pass
                results = [r if r.get("checkId") not in self.judged_pass or r.get("status") == "pass"
                           else {**r, "status": "pass", "detail": r.get("judgedDetail") or "Claude saw it on screen"}
                           for r in results]
                if not gate.get("passed") and results and all(r.get("status") == "pass" for r in results):
                    gate = {**gate, "passed": True, "via": "judge"}
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
            if shown in ("pass", "fail") and (not prev or prev["status"] != shown):
                self._record(f"check_{shown}", {"check_id": cid, "label": label, "detail": detail}, step)
            self.check_state[cid] = {"label": label, "status": shown, "detail": detail}
            payload = {"stepId": step["id"], "checkId": cid, "label": label, "status": shown}
            if detail:
                payload["detail"] = detail
            await self.emit("check.updated", payload)

    async def tick(self) -> None:
        """Called ~1/s: idle-after-action, stuck, and typing-deferred speech."""
        step = self.step
        await self._check_screen_health()
        if step is not None and not self.passed and not self.awaiting_resume:
            self._maybe_judge(step)
            await self._maybe_stuck_card(step)
        if (step is None or self.passed or self.coaching or not self.last_failed or not self.engaged
                or self.awaiting_resume):
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
        from . import workspace as wsmod

        titles = [getattr(w, "title", "") or "" for w in getattr(self.last_obs, "windows", None) or []]
        for f in files:
            p = wsmod.resolve_file(self.workdir, f, titles)  # nested project dirs, .git/rebase-merge, open file
            if p is not None:
                try:
                    text = p.read_text(errors="replace")
                except OSError:
                    continue
                if p.suffix.lower() == ".ipynb":  # cell sources, then the limit (S9: raw JSON cut = invalid)
                    text = notebook_sources(text) or text
                return text[:limit], f
        lines = self._screen_lines() or {}  # screen-first: the code the learner is looking at
        for app in [t.get("app") for t in step.get("targets") or [] if t.get("app")] + ["Code"]:
            for a, ls in lines.items():
                if app.lower() in (a or "").lower() and ls:
                    return "\n".join(ls)[:limit], None
        return "", None

    def learner_started(self) -> bool:
        """Did the learner do anything on this step: a save, a run, an action, or typing since it started?"""
        if self.last_action_t >= self.step_t0:
            return True
        v = self.inputs.seconds_since_key() if self.inputs is not None else None
        return v is not None and v <= self.clock() - self.step_t0

    def _consider_speaking(self, reason: str, step: dict, failed: list[dict], ctx: RunContext) -> None:
        """reason: breakpoint | repeat | stuck | idle. Decides whether, and at which ladder level, to speak."""
        if self.coaching or self.passed or not failed:
            return
        if not self.learner_started() or self.clock() - self.step_t0 < self.offtrack_grace_s:
            return  # never "off track" before the learner did anything on this step, nor in its first ~20 s
        if self.clock() < self._coach_retry_at:
            return  # the coach failed recently (e.g. offline): wait before trying again
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

    def _screen_error_lines(self, n: int = 40) -> list[str]:
        lines = self._screen_lines() or {}
        apps = ["Terminal", "iTerm", "Warp"] + (list(self.BROWSER_APPS) if self.notebook_lesson else []) + ["Code", "Cursor"]
        out: list[str] = []
        for want in apps:
            for app, ls in lines.items():
                if want.lower() in (app or "").lower():
                    out.extend(ls[-n:])
            if out:
                break
        return out[-n:]

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
                if not tail:  # screen-first (no `tut run`): what the terminal / notebook shows is the error text
                    tail = self._screen_error_lines()
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
                        self.spoken_sig = None  # a later breakpoint may try again...
                        if "cancelled" in str(e):
                            log.info("diagnosis cancelled: the learner acted")
                        else:  # ...but back off (offline: no error storm), and say it once per step
                            self._coach_backoff = min(120.0, max(15.0, self._coach_backoff * 2))
                            self._coach_retry_at = self.clock() + self._coach_backoff
                            log.warning("coach.diagnose failed (%s); retry in %.0fs", e, self._coach_backoff)
                            if not self._coach_error_sent:
                                self._coach_error_sent = True
                                await self.emit("error", {"message": f"Coach unavailable: {e}"})
                        await self._status("watching")
                    return
                self._coach_backoff, self._coach_retry_at = 0.0, 0.0
            if gen != self.step_gen or self.passed:
                return
            ids = {r.get("checkId") for r in failed if r.get("checkId")}
            if card.get("notStarted"):  # E5: nothing done yet -> one plain instruction, never amber / "off track"
                self.spoken_sig = None  # a real diagnosis may follow once they've worked on it
                self._carded_checks |= ids
                await self._emit_card({"stepId": step["id"], "kind": "hint", "title": card.get("title") or "Start here",
                                       "body": card.get("body") or step.get("instructions", "")}, window_s=120.0)
                await self._status("watching")
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
            key = (step["id"], level, (full.get("title") or "").strip().lower())
            if level == 2 and ids and ids <= self._carded_checks:
                log.info("a card already covers %s; no offtrack on top of it", sorted(ids))
                await self._status("watching")
                return
            self._offtracked_checks |= ids
            if key != self._offtrack_key:  # only a NEW card: new step, higher level or a different diagnosis
                self._offtrack_key = key  # (re-sending the same one reopens a card the learner just closed)
                await self.emit("offtrack", shown)
                self._say("offtrack", shown)
            else:
                log.info("same offtrack as before (%s, level %s); not re-sent", step["id"], level)
            self._record("offtrack", {"title": full.get("title"), "level": level,
                                      "check_ids": [r.get("checkId") for r in failed]}, step)
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
        self.video_t = t
        self.video_playing = playing
        seg = self._segment(step)
        if seg and not self.segment_done and t >= seg["end"] - 0.3 and t <= seg["end"] + 5:
            await self._segment_end()

    async def resume(self) -> None:
        """"Continue": replay the lesson state and pick the video up where it was."""
        if self.graph is None or self.step is None:
            self.awaiting_resume = False
            await self._status("idle")
            return
        self.awaiting_resume = False
        now = self.clock()
        self.last_progress_t = now  # time away doesn't count as being stuck
        self.last_action_t = max(self.last_action_t, now)
        for type_, payload in self.snapshot():
            if type_ != "status":
                await self.emit(type_, payload)
        seg = self._segment(self.step)
        t = self.video_t if self.video_t is not None else (seg or {}).get("start")
        if seg is not None and t is not None:
            await self.emit("video.seek", {"t": float(t), "play": not self.segment_done})
        await self._status("offtrack" if self.last_offtrack and not self.passed else "watching")

    async def action(self, kind: str, text: str | None = None) -> None:
        if kind == "resume":
            await self.resume()
            return
        if kind == "end_lesson":  # the resume card's "Start a new lesson"
            await self.end_lesson("end_lesson")
            return
        if kind == "build":  # preflight card: build the picked video
            await self._build_pick()
            return
        if kind == "pick_another":
            await self._pick_another()
            return
        if self.step is None and self.pending_pick is not None and kind == "download":
            self._download_after_build = True  # no lesson folder yet: download into it once it exists
            await self.emit("card", {"kind": "answer", "title": "Tutorial files",
                                     "body": "I'll save the video's files in your lesson folder as soon as it's ready."})
            return
        if self.step is None and self.pending_pick is not None and kind in ("install", "open_in_browser"):
            # the preflight card's tool buttons, before any lesson exists
            if kind == "install":
                self._spawn(self._install((text or "").strip()))
            else:
                await self._open_in_browser((text or "").strip())
            return
        token = _EPOCH.set(self.lesson_epoch)  # a card that finishes after end_lesson is dropped
        try:
            await self._action(kind, text)
        except Exception as e:  # live mode: a missing/failing module is reported, never faked
            log.exception("action %s failed", kind)
            await self.emit("error", {"message": f"{kind}: {e}"})
            if self.step is not None:
                await self._status("offtrack" if self.last_offtrack else ("passed" if self.passed else "watching"))
        finally:
            _EPOCH.reset(token)

    async def _action(self, kind: str, text: str | None = None) -> None:
        step = self.step
        if step is not None:
            self._acted()
        if kind == "confirm":  # "Apply this fix?" preview, or "Looks done? Confirm"
            if step is not None and self.pending_patch is not None:
                await self._apply_patch(step)
            elif step is not None and self.confirm_pending and not self.passed:
                self.confirm_pending = False
                for cid in self.confirm_check_ids:  # E5's "Looks done?": the learner vouches for these checks
                    label = (self.check_state.get(cid) or {}).get("label", cid)
                    await self.emit("check.updated", {"stepId": step["id"], "checkId": cid, "label": label,
                                                      "status": "pass", "detail": "You confirmed it"})
                self.confirm_check_ids = []
                await self._pass_step()
            return
        if kind == "undo":
            await self._undo_fix()
            return
        if step is None:
            await self.emit("error", {"message": "No lesson is running yet."})
            return
        self._touch()
        if kind == "check_step":  # "Can I move on?"
            await self._check_step(step)
            return
        if kind == "skip_step":  # leave this step unfinished and start the next one
            await self._pass_step(skipped=True)
            return
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
                await self.emit("video.play", {})
            gen = self.step_gen
            if reason := self.screen_down_reason():  # say at once why there's no spotlight (no capture attempt)
                await self._emit_card({"stepId": step["id"], "kind": "hint", "title": "I can't see your screen",
                                       "body": self.screen_down_message(reason)})
                return
            quick = await self._show_where(step)  # exact match / window: instant
            if quick and self.lesson_mode:
                return  # the target box + what to type there is the whole answer
            if self.m.has_pointing():  # E5: the diagnosed line, the step's target, else Haiku (<= 3 s)
                screen = await self._screen_for_coach(step)
                r = await self.m.show_me(step, screen, self.last_offtrack) if screen is not None else None
                if gen != self.step_gen:
                    return
                if r and r.get("targets"):
                    spot = self._target_spot({**r["targets"][0], "label": r.get("caption") or r["targets"][0].get("label")})
                    if spot:
                        self._action_spot = True
                        await self._show_spot({**spot, **self._snippet(step)})
                        return
                if r and r.get("where") and not quick:
                    await self._emit_card({"stepId": step["id"], "kind": "hint", "title": "Where to work",
                                           "body": r["where"]})
                    return
            if not quick and self._can_see():
                await self._emit_card(self._where_card(step))
            return
        if kind in ("explain", "ask"):
            self._record("question", {"kind": kind, "text": (text or "")[:300]}, step)
            await self._status("thinking")  # visible at once; the spotlight follows, the card after
            gen = self.step_gen
            await self._show_where(step)
            ctx = self._explain_context()
            screen = await self._screen_for_coach(step)
            if screen is not None:
                ctx["screen"] = screen

                def on_targets(targets: list[dict]) -> None:  # the coach points while it answers
                    if gen == self.step_gen and targets:
                        spot = self._target_spot(targets[0])
                        if spot:
                            self._action_spot = True
                            self._spawn(self._show_spot(spot))

                ctx["on_targets"] = on_targets
            card = await self.m.explain(step, text if kind == "ask" else (text or None), ctx)
            if gen != self.step_gen:
                return  # the learner moved to another step meanwhile: an answer about the old one would mislead
            card = dict(card)
            card["stepId"] = step["id"]
            if card.get("targets"):
                spot = self._target_spot(card["targets"][0])
                if spot:
                    self._action_spot = True
                    await self._show_spot(spot)
            await self._emit_card(card)
            await self._status("offtrack" if self.last_offtrack else ("passed" if self.passed else "watching"))
            return
        if kind == "hint":
            gen = self.step_gen
            await self._status("thinking")
            shown = await self._show_where(step)
            screen = await self._screen_for_coach(step) if self.m.has_pointing() else None
            if screen is None and ((not shown and self._can_see()) or self._code_not_visible()):  # say WHERE to go
                await self._emit_card(self._where_card(step))
                await self._status("offtrack" if self.last_offtrack else "watching")
                return
            card = dict(await self.m.hint(step, self.hint_level, self.last_offtrack, screen=screen))
            if gen != self.step_gen:
                return
            card["stepId"] = step["id"]
            self.hint_level += 1
            if card.get("targets"):  # E5 pointed at the exact spot
                spot = self._target_spot(card["targets"][0])
                if spot:
                    self._action_spot = True
                    await self._show_spot(spot)
            await self._emit_card(card)
            await self._status("offtrack" if self.last_offtrack else "watching")
            return
        if kind == "diagram":
            want = (text or "").strip().lower()
            if want not in DIAGRAM_KINDS and not self.m.has_diagrams():  # stubs (DEMO) pick from the failing checks
                metric_fail = any(r.get("status") == "fail" and r.get("checkId") in
                                  {c["id"] for c in step.get("checks", []) if c.get("type", "").startswith("metric")}
                                  for r in self.last_results)
                want = "gradients" if metric_fail or self.last_offtrack else "network"
            await self._status("thinking")
            gen, graph = self.step_gen, self.graph
            d = await self.m.diagram(want if want in DIAGRAM_KINDS else None, self._diagram_step(step), self.context(),
                                     self._diagram_context(step, None if want in DIAGRAM_KINDS else (text or None)))
            if self.graph is not graph or gen != self.step_gen:
                return  # the lesson/step changed while drawing: never show it in the wrong place
            d = dict(d)
            d["stepId"] = step["id"]
            await self.emit("diagram", d)
            await self._status("offtrack" if self.last_offtrack else ("passed" if self.passed else "watching"))
            return
        if kind == "open_editor":
            await self._open_editor()
            return
        if kind == "install":  # text = the setup item's tool id
            self._spawn(self._install((text or "").strip()))
            return
        if kind == "skip_setup":  # the app dismisses the setup card; nothing to undo here
            return
        if kind == "download":  # S2: the video's linked code / notebooks -> <lesson folder>/tutorial/ (never run)
            from . import workspace as wsmod

            await self._status("thinking")
            res, summary = await asyncio.to_thread(wsmod.download_resources, self.graph or {}, self.workdir)
            await self._emit_card({"stepId": step["id"], "kind": "answer", "title": "Tutorial files", "body": summary})
            await self._status("offtrack" if self.last_offtrack else ("passed" if self.passed else "watching"))
            return
        if kind == "open_in_browser":  # text = a web_app setup item's tool id (no-code lessons)
            await self._open_in_browser((text or "").strip())
            return
        if kind == "voice_toggle":
            self.voice = not self.voice
            if self.voice:
                self._prefetch_voice()
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

    # ------------------------------------------------------------------ pointing (show_me / hint / explain)
    BROWSER_APPS = ("Google Chrome", "Safari", "Arc", "Firefox", "Brave Browser", "Microsoft Edge")

    def _work_apps(self, step: dict) -> list[str]:
        apps = [t.get("app") for t in step.get("targets") or [] if t.get("app")]
        apps += [c.get("app") for c in step.get("checks") or [] if c.get("app")]
        if self.notebook_lesson:
            apps += list(self.BROWSER_APPS) + ["Code", "Cursor", "Jupyter"]
        return list(dict.fromkeys(apps or ["Code", "Cursor", "Terminal"]))

    def _window_spot(self, step: dict, caption: str) -> dict | None:
        """The window the learner should work in, when the exact target isn't on screen."""
        obs = self.last_obs
        for want in self._work_apps(step):
            for w in getattr(obs, "windows", None) or []:
                if want.lower() in (getattr(w, "app", "") or "").lower():
                    r = w.rect.to_dict() if hasattr(w.rect, "to_dict") else w.rect
                    return {"rect": {k: float(r[k]) for k in ("x", "y", "w", "h")}, "caption": caption, "app": w.app}
        return None

    async def _show_where(self, step: dict) -> bool:
        """Spotlight where to work NOW: the step's target on screen, else its app's window. False = nothing visible."""
        if await self._spotlight_target(step):
            self._action_spot = True
            return True
        file = self._step_file(step)
        if self.lesson_mode:  # the exact line (S2 / E6), never the whole editor window
            spot = await self._editor_line_spot(step)
            if spot:
                self._action_spot = True
                await self._show_spot(spot)
                return True
            return False
        caption = f"Work here: {file}" if file else "Work here"
        spot = self._window_spot(step, caption)
        if spot:
            self._action_spot = True
            await self._show_spot({**spot, **self._snippet(step)})
            return True
        return False

    def _step_file(self, step: dict) -> str | None:
        for t in step.get("targets") or []:
            if t.get("file"):
                return t["file"]
        for c in (step.get("checks") or []) + (step.get("precision_checks") or []):
            if c.get("file"):
                return c["file"]
        return None

    def _can_see(self) -> bool:
        """The screen reader is running and has a frame: 'nothing found' then really means 'not on screen'."""
        return self.screen_active() and self.last_obs is not None

    @staticmethod
    def _editor_label() -> str:
        from . import workspace as wsmod

        return wsmod.editor_label()

    def _code_not_visible(self) -> bool:
        details = " ".join(str(r.get("detail") or "") for r in self.last_results if r.get("status") != "pass").lower()
        return any(k in details for k in ("not visible", "not on screen", "waiting for screen"))

    def _where_card(self, step: dict) -> dict:
        """A card that says WHERE to go when I can't see the learner's work."""
        file = self._step_file(step)
        if self.notebook_lesson:
            return {"stepId": step["id"], "kind": "hint", "title": "Open the notebook",
                    "body": f"Open {file or 'the notebook'} in Colab or Jupyter so I can see it."}
        untitled = self._untitled_editor()
        if file and untitled:  # the learner typed into a new, unsaved editor tab: say exactly what to do
            return {"stepId": step["id"], "kind": "hint", "title": f"Save it as {Path(file).name}",
                    "body": f"Your code is in an unsaved {untitled} tab. Save it (⌘S) as {Path(file).name} in "
                            f"{self.workdir} so I can check it."}
        card: dict[str, Any] = {"stepId": step["id"], "kind": "hint", "title": f"Open {file}" if file else "Show me your code",
                                "body": (f"Open {file} in {self._editor_label()} so I can see it and point at the right line."
                                         if file else "Bring your editor to the front so I can see your code.")}
        from . import workspace as wsmod

        if self.workspace is not None and self.graph is not None and wsmod.needs_editor(self.graph):
            card["actions"] = ["open_editor"]
        return card

    def _untitled_editor(self) -> str | None:
        """The code editor (VS Code / Cursor) showing an unsaved 'Untitled-N' tab, if any."""
        for w in getattr(self.last_obs, "windows", None) or []:
            app = (getattr(w, "app", "") or "")
            title = (getattr(w, "title", "") or "").lstrip("● ")
            if app.lower() in CODE_APP_NAMES | {"code"} and title.lower().startswith("untitled"):
                return "Cursor" if app.lower() == "cursor" else "VS Code"
        return None

    def _diagram_step(self, step: dict) -> dict:
        """Step ids repeat across lessons (s1, s2...): namespace the id by lesson so S4's cache can't
        hand one lesson's diagram to another."""
        lesson_id = (self.graph or {}).get("lesson", {}).get("id", "lesson")
        return {**step, "id": f"{lesson_id}:{step['id']}"}

    async def _prefetch_diagram(self, gen: int, step: dict) -> None:
        """Warm S4's diagram cache for this step so the diagram button is instant (errors are ignored)."""
        await asyncio.sleep(2.0)  # let the step settle (code on screen, video playing)
        if gen != self.step_gen or not self.m.has_diagrams():
            return
        try:
            await self.m.diagram(None, self._diagram_step(step), self.context(), self._diagram_context(step, None))
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

    async def _emit_card(self, card: dict, window_s: float = 15.0) -> None:
        """Send a card unless the same one (step + kind + level + title + body) went out moments ago: repeated
        key presses or overlapping triggers must not stack identical cards."""
        sig = (card.get("stepId"), card.get("kind"), card.get("level"), card.get("title"), card.get("body"))
        now = self.clock()
        last = self._recent_cards.get(sig)
        if last is not None and now - last < window_s:
            log.info("dropped duplicate card %r", card.get("title"))
            return
        self._recent_cards[sig] = now
        await self.emit("card", card)

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
        if not (file and yours and expected) and self.lesson_mode and (step.get("code") or "").strip():
            await self._type_step_for_them(step)  # "Do it for me" on a lesson step: its code, previewed first
            return
        if not (file and yours and expected):
            await self._card(step, "No automatic fix", "This one needs your hands. Try a hint.")
            return
        from . import workspace as wsmod
        from .inputs import dirty_files

        titles = [getattr(w, "title", "") or "" for w in getattr(self.last_obs, "windows", None) or []]
        path = wsmod.resolve_file(self.workdir, file, titles) or (Path(file) if Path(file).is_absolute()
                                                                    else Path(self.workdir) / file)

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
        if self.workspace is not None and self.editor_open:
            self.workspace.goto(str(path), line)
        first = expected.strip().splitlines()[0]
        spot = self._locate(re.escape(first), None, "Fixed")
        if spot:
            await self._show_spot(spot)
        self._record("fix_applied", {"file": path.name}, step)
        await self._card(step, "Fix applied", "Re-run to check it. Undo if you'd rather type it yourself.",
                         kind="answer", actions=["undo"])
        await self.on_file_change([str(path)])

    async def _check_step(self, step: dict) -> None:
        """"Can I move on?": re-run the checks on a fresh frame now (asking counts as acting, so a pass moves on
        at once), then E5's Claude judge looks at the screen + files. Done -> step.passed. Not done -> ONE card
        "Not yet" saying what's missing (<= 12 words), with the spot to fix when the judge gives one. Without the
        judge (offline / no key) the deterministic checks decide alone."""
        gen = self.step_gen
        await self._status("thinking")
        if self.screen is not None:
            self.screen.poke()  # a new frame, not one from before their last keystroke
            if self.check_wait_s:
                await asyncio.sleep(self.check_wait_s)
        if gen != self.step_gen:
            return
        self.engaged = True
        await self.evaluate("check")
        if self.passed or gen != self.step_gen:
            return
        code, file = self._code_excerpt(step)
        try:
            verdict = await self.m.judge_step(step, screen=self._screen_lines(), files={file: code} if file and code else {},
                                              check_results=self.last_results, focused_app=self._focused_app(),
                                              lesson=(self.graph or {}).get("lesson"))
        except Exception as e:  # noqa: BLE001 - the judge is a bonus
            log.info("check_step: no judge (%s)", e)
            verdict = None
        if gen != self.step_gen or self.passed:
            return
        if verdict and verdict.get("done"):
            for cid, v in (verdict.get("checks") or {}).items():
                if v.get("verdict") == "done":
                    self.judged_pass.add(cid)
            await self.evaluate("check")
            if not self.passed and gen == self.step_gen:  # the judge says every check is done: trust it
                await self._pass_step()
            return
        missing = (verdict or {}).get("missing") or ""
        if not missing:
            labels = [r.get("label") or r.get("checkId") for r in self.last_failed or
                      [r for r in self.last_results if r.get("status") != "pass"]]
            missing = ("Still missing: " + "; ".join(str(x) for x in labels[:3])) if labels else "The checks haven't passed yet"
        body = " ".join(missing.split()[:12])
        ids = {r.get("checkId") for r in self.last_failed if r.get("checkId")}
        if ids and ids <= self._offtracked_checks and self.last_offtrack:
            await self._status("offtrack")  # the offtrack card on screen already says what's missing
            return
        self._carded_checks |= ids
        target = (verdict or {}).get("target") or {}
        if target.get("rect"):
            await self._show_spot({"rect": target["rect"], "caption": body})
            self._action_spot = True
        await self._emit_card({"stepId": step["id"], "kind": "answer", "title": "Not yet", "body": body,
                               "actions": ["skip_step"]}, window_s=2.0)
        await self._status("offtrack" if self.last_offtrack else "watching")

    SCREEN_DOWN_S = 15.0  # a Space switch / screen lock is brief: only a lasting failure is reported

    def screen_down_reason(self) -> str | None:
        fn = getattr(self.screen, "down_reason", None) if self.screen is not None else None
        try:
            return fn() if fn else None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def screen_down_message(reason: str) -> str:
        return "Miyagi can't see your screen. Check Screen Recording in System Settings."

    async def _check_screen_health(self) -> None:
        """S1: a dead capture was silent (checks stuck on 'waiting for screen'). Tell the app once."""
        reason = self.screen_down_reason()
        if reason is None:
            if self._screen_notice_sent:
                log.info("screen reader recovered")
            self._screen_down_since, self._screen_notice_sent = None, False
            return
        if self._screen_down_since is None:
            self._screen_down_since = self.clock()
        if not self._screen_notice_sent and self.clock() - self._screen_down_since >= self.SCREEN_DOWN_S:
            self._screen_notice_sent = True
            log.warning("screen reader down: %s", reason)
            await self.emit("error", {"message": self.screen_down_message(reason)})

    def _focused_app(self) -> str:
        return str(getattr(self.last_obs, "app", "") or "")

    def _maybe_judge(self, step: dict) -> None:
        """E5's StepJudge in the background: when the learner is idle and the deterministic checks can't tell
        (pending), Claude (Haiku) looks; gates (idle >= 8 s, <= 1 per 20 s, only on change) are E5's."""
        j = self.judge
        if j is None or self._judging or not self.last_results:
            return
        screen = self._screen_lines()
        code, file = self._code_excerpt(step)
        files = {file: code} if file and code else {}
        try:
            if not j.should_judge(step, self.last_results, idle_s=self.learner_idle_s(),
                                  video_playing=self.video_playing and not self.segment_done,
                                  screen=screen, files=files, focused_app=self._focused_app()):
                return
        except Exception:  # noqa: BLE001
            log.exception("should_judge failed")
            return
        self._judging = True
        self._spawn(self._run_judge(self.step_gen, step, screen, files))

    async def _run_judge(self, gen: int, step: dict, screen: Any, files: dict) -> None:
        try:
            j = await self.judge.judge(step, self.last_results, screen=screen, files=files,
                                       focused_app=self._focused_app(), lesson=(self.graph or {}).get("lesson"))
        except Exception:  # noqa: BLE001
            log.exception("step judge failed")
            j = None
        finally:
            self._judging = False
        if not j or gen != self.step_gen or self.passed:
            return
        for ev in j.get("events") or []:
            p = ev.get("payload") or {}
            if ev.get("type") == "check.updated" and p.get("status") == "pass" and p.get("checkId"):
                self.judged_pass.add(p["checkId"])
        if self.judged_pass:
            await self.evaluate("judge")
        card = j.get("card")
        if card and not self.passed and gen == self.step_gen:
            if "confirm" in (card.get("actions") or []):
                self.confirm_pending = True
                self.confirm_check_ids = list(card.get("checkIds") or [])
            await self._emit_card(card)

    SETUP_STEP = re.compile(r"\b(install(ing|ation|ed)?|download(ing)?|set\s*-?\s*up|setup)\b", re.I)

    async def _maybe_pass_setup_step(self) -> None:
        """Never trap the learner on an install step for tools S2's check already found on this Mac."""
        step = self.step
        if step is None or self.passed or not self.reqs:
            return
        requires = {str(t).lower() for t in step.get("requires") or []}
        if step.get("setup") and requires:  # E2 tags real setup steps: setup: true, requires: [tool ids]
            items = [it for it in self.reqs if str(it.get("tool", "")).lower() in requires]
            if len(items) < len(requires):
                return  # S2's check doesn't cover every required tool: can't vouch for it
        else:
            text = f"{step.get('title', '')} {step.get('instructions', '')}"
            if not self.SETUP_STEP.search(text):
                return
            low = text.lower()
            named = [it for it in self.reqs if any(n and str(n).lower() in low for n in (it.get("label"), it.get("tool")))]
            items = named or [it for it in self.reqs if it.get("needed")]
        if not items or not all(it.get("ok") for it in items):
            return
        for c in self.display_checks(step):
            await self.emit("check.updated", {"stepId": step["id"], "checkId": c["id"], "label": c.get("label", c["id"]),
                                              "status": "pass", "detail": "Already installed"})
        self._record("step_passed_installed", {"tools": [it.get("tool") for it in items]}, step)
        await self._pass_step()

    STUCK_CARD_S = 90.0

    async def _maybe_stuck_card(self, step: dict) -> None:
        """Pending > 90 s after the clip ended and the learner is idle: offer Skip, once per step."""
        if (self._stuck_card_sent or not self.segment_done or self.segment_end_t is None
                or self.clock() - self.segment_end_t < self.STUCK_CARD_S or self.learner_idle_s() < self.idle_gate_s):
            return
        if self.last_results and all(r.get("status") == "pass" for r in self.last_results):
            return
        self._stuck_card_sent = True
        await self._emit_card({"stepId": step["id"], "kind": "hint", "title": "Stuck on this step?",
                               "body": "Skip it, or ask for a hint.", "actions": ["skip_step"]})

    async def _type_step_for_them(self, step: dict) -> None:
        """Lesson mode "Do it for me": E5 places the step's code in the file (preview -> confirm -> apply);
        a new / empty file just gets the code. Never types into the editor."""
        from . import workspace as wsmod
        from .inputs import dirty_files

        file = self._step_file(step) or step.get("file") or ""
        if not file:
            await self._card(step, "Type it yourself", step["code"], kind="answer")
            return
        titles = [getattr(w, "title", "") or "" for w in getattr(self.last_obs, "windows", None) or []]
        path = wsmod.resolve_file(self.workdir, file, titles) or (Path(file) if Path(file).is_absolute()
                                                                    else Path(self.workdir) / file)
        if path.name in dirty_files(self.last_obs):
            await self._card(step, f"Save {path.name} first", "Press ⌘S, then Do it for me again.")
            return
        try:
            text = path.read_text() if path.exists() else ""
        except OSError as e:
            await self.emit("error", {"message": f"Could not open {file}: {e}"})
            return
        code = step["code"].rstrip("\n") + "\n"
        new_text, summary, line = None, f"Adds this step's code to {path.name}.", 1
        if not text.strip():
            new_text = code
        elif self.m.has_do_it_for_me():
            await self._status("thinking")
            try:
                p = await self.m.do_it_for_me(step, path.name, text, None)
                new_text, summary, line = p.get("new_text"), p.get("summary") or summary, p.get("line") or 1
            except Exception as e:  # noqa: BLE001
                log.info("do_it_for_me (lesson step) failed: %s", e)
            await self._status("watching")
        if not new_text or new_text == text:
            await self._card(step, "Type it yourself", step["code"], kind="answer")
            return
        import difflib

        diff = "".join(difflib.unified_diff(text.splitlines(True), new_text.splitlines(True),
                                            f"a/{path.name}", f"b/{path.name}"))
        self.pending_patch = {"path": path, "old": text, "new": new_text, "line": line,
                              "first": code.strip().splitlines()[:1]}
        await self._card(step, "Type this for you?", summary, kind="answer", diff=diff, actions=["confirm"])

    async def _apply_patch(self, step: dict) -> None:
        """Confirmed preview: re-check (unsaved edits? file changed since the preview?), back up, write."""
        from .inputs import dirty_files

        pp, self.pending_patch = self.pending_patch, None
        path: Path = pp["path"]
        if path.name in dirty_files(self.last_obs):
            await self._card(step, f"Save {path.name} first", "Press ⌘S, then Do it for me again.")
            return
        try:
            current = path.read_text() if (path.exists() or pp["old"]) else ""
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
        path.parent.mkdir(parents=True, exist_ok=True)  # lesson mode: a step may create its file
        path.write_text(pp["new"])
        if self.workspace is not None and self.editor_open:
            self.workspace.goto(str(path), int(pp["line"]))
        if pp["first"]:
            spot = self._locate(re.escape(pp["first"][0]), None, "Fixed")
            if spot:
                await self._show_spot(spot)
        self._record("fix_applied", {"file": path.name}, step)
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
    def resume_card(self) -> dict:
        lesson = (self.graph or {}).get("lesson", {})
        step = self.step or {}
        where = f"step {step.get('index', self.idx) if step else '?'}: {step.get('title', '')}".strip()
        return {"kind": "resume", "title": "Continue where you left off?",
                "body": f"{lesson.get('title', 'Your lesson')} · {where}", "actions": ["resume", "end_lesson"]}

    def snapshot(self, ask_resume: bool = False) -> list[tuple[str, dict]]:
        """Messages that bring a freshly connected client up to date. ask_resume (the app came back
        after being away): pause and offer "Continue / Start new" instead of jumping back in."""
        out: list[tuple[str, dict]] = []
        if ask_resume and self.graph is not None and self.step is not None:
            self.awaiting_resume = True
            return [("video.pause", {}), ("card", self.resume_card())]
        if self.awaiting_resume and self.graph is not None:  # still undecided: show the question again
            return [("video.pause", {}), ("card", self.resume_card())]
        if self.pending_pick is not None and self.pending_pick.get("card"):  # preflight card awaiting build / pick_another
            return [("status", {"state": "idle"}), ("card", self.pending_pick["card"])]
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
            "screen": bool(self.screen is not None and getattr(self.screen, "active", False))
            and not self.screen_down_reason(),  # false while frames fail (E6 status error / no_permission)
            "screenDown": self.screen_down_reason(),  # S1: E6 status error / no_permission
            "voice": self.voice,
        }
