"""The lesson state machine (one learner, one lesson at a time).

Flow:
  learn -> search.result* -> search.done
  build_lesson / learn_url -> lesson.building* -> lesson.ready -> step 0
  step start -> step.started, check.updated(pending)*, video.seek(play) + video.play, status watching
  segment end (video.state reaches step.video.end) -> pass if checks already pass,
                                                       else video.pause + spotlight
  file change / run end / metrics -> checks.evaluate_step -> check.updated (changes only)
     all pass (and the learner engaged or the segment ended) -> step.passed, then the next
     step's step.started + video.seek + video.play
     failing -> don't-nag gate: opens on a run ending with fails, 2 consecutive failing
     evaluations, or >= IDLE_GATE_S idle after the learner engaged. Until the gate opens
     a failing check is shown as `pending` (calm UI); once open -> coach.diagnose ->
     offtrack + spotlight + status offtrack.
"""

from __future__ import annotations

import asyncio
import logging
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

BUILD_MESSAGES = [
    "Watching the tutorial",
    "Finding the steps",
    "Writing checks for each step",
    "Lining up the video",
    "Almost ready",
]
DIAGRAM_KINDS = ("network", "gradients", "heatmap")


def video_id_from_url(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else None


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
        build_tick_s: float = 0.5,
        screen: Any = None,
        seen_interval_s: float = 5.0,
    ):
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
        self.consecutive_fails = 0
        self.engaged = False  # learner touched files / ran something during this step
        self.gate_open = False
        self.segment_done = False
        self.video_reports = 0
        self.coached_key: Any = None
        self.coaching = False
        self.hint_level = 0
        self.step_runs: list[RunInfo] = []
        self.last_activity = self.clock()
        self.passed = False
        self.last_offtrack: dict | None = None
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
        """Known workdir on disk, or a `tut run` this step -> precision_checks may also pass the step."""
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
        try:
            results = await self.m.search(query)
        except Exception as e:  # stubs never raise; real ones fall back inside Modules
            log.exception("search failed")
            await self.emit("error", {"message": f"Search failed: {e}"})
            results = []
        self.results = {}
        for r in results:
            self.results[r["id"]] = r
            await self.emit("search.result", r)
            if self.result_stagger_s:
                await asyncio.sleep(self.result_stagger_s)
        await self.emit("search.done", {"total": len(results)})
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
        self.phase = "building"
        await self._status("thinking")
        done = asyncio.Event()

        async def ticker() -> None:
            i = 0
            while not done.is_set():
                msg = BUILD_MESSAGES[min(i, len(BUILD_MESSAGES) - 1)]
                await self.emit("lesson.building", {"message": msg, "progress": round(min(0.9, 0.1 + 0.18 * i), 2)})
                i += 1
                try:
                    await asyncio.wait_for(done.wait(), self.build_tick_s)
                except TimeoutError:
                    pass

        tick = asyncio.create_task(ticker())
        try:
            graph = await self.m.build_lesson(url, goal, str(config.default_workdir()))
        except Exception as e:
            log.exception("build_lesson failed")
            done.set()
            await tick
            self.phase = "idle"
            await self.emit("error", {"message": f"Could not build the lesson: {e}"})
            await self._status("idle")
            return
        done.set()
        await tick
        await self.emit("lesson.building", {"message": "Lesson ready", "progress": 1.0})
        await self.load_graph(graph)

    async def load_graph(self, graph: dict) -> None:
        self.graph = graph
        self.runs = {}
        new_wd = str(config.resolve_workdir(graph.get("lesson", {}).get("workdir")))
        self.workdir = new_wd
        if self.on_workdir:
            self.on_workdir(new_wd)
        self.m.set_lesson(graph)
        await self.emit("lesson.ready", self._lesson_ready_payload())
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
        """Spotlight the step's first target that is visible on screen (rect in screen points)."""
        for t in step.get("targets") or []:
            spot = self._locate(t.get("match") or "", t.get("app"), t.get("caption", ""))
            if spot:
                await self.emit("spotlight", spot)
                return True
        return False

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
            except Exception as e:  # pragma: no cover - Modules already falls back
                log.exception("evaluate_gate failed")
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
            if failed and learner:
                self.consecutive_fails += 1
            elif not failed:
                self.consecutive_fails = 0
            if failed and (trigger == "run_end" or self.consecutive_fails >= 2):
                self.gate_open = True
            await self._publish(step, results)
            if gate.get("passed") and (self.segment_done or self.engaged):
                await self._pass_step()
                return
            if failed and self.gate_open:
                self._maybe_coach(step, failed, ctx)

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
        """Called ~1/s: opens the idle gate."""
        step = self.step
        if step is None or self.passed or self.gate_open or not self.engaged or self.coaching:
            return
        if self.clock() - self.last_activity < self.idle_gate_s:
            return
        failed = list(self.last_failed)
        if not failed:
            return
        async with self._lock:
            if self.step is not step or self.passed:
                return
            self.gate_open = True
            await self._publish(step, self.last_results)
            self._maybe_coach(step, failed, self.context())

    # ------------------------------------------------------------------ coaching
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

    def _maybe_coach(self, step: dict, failed: list[dict], ctx: RunContext) -> None:
        last = ctx.last_run
        key = (step["id"], tuple(sorted(r.get("checkId", "") for r in failed)), last.run_id if last else None)
        if self.coaching or key == self.coached_key:
            return
        self.coached_key = key
        self.coaching = True
        self._spawn(self._coach(self.step_gen, step, failed, ctx))

    async def _coach(self, gen: int, step: dict, failed: list[dict], ctx: RunContext) -> None:
        try:
            await self._status("thinking")
            by_id = {c["id"]: c for c in (step.get("checks") or []) + (step.get("precision_checks") or [])}
            failed_checks = [{**by_id.get(r.get("checkId"), {}), **r} for r in failed]
            code, _file = self._code_excerpt(step)
            tail = ctx.output_tail[-40:] if isinstance(ctx.output_tail, list) else []
            card = await self.m.diagnose(step, failed_checks, ctx.metrics, code, error_text="\n".join(tail))
            if gen != self.step_gen or self.passed:
                return
            card = dict(card)
            card.setdefault("stepId", step["id"])
            card.setdefault("severity", "warn")
            card.setdefault("actions", ["explain", "show_me", "hint"])
            self.last_offtrack = card
            await self.emit("offtrack", card)
            diff = card.get("diff") or {}
            first = (diff.get("yours") or "").strip().splitlines()[:1]
            spot = self._locate(re.escape(first[0]), None, card.get("title", "")) if first else None
            if spot:
                await self.emit("spotlight", spot)
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
        now = self.clock()
        if obs is not None and now - self._last_seen >= self.seen_interval_s:
            self._last_seen = now
            app = getattr(obs, "app", None) or ""
            lines = self._screen_lines() or {}
            summary = " · ".join((lines.get(app) or [])[:2])[:140]
            await self.emit("screen.seen", {"app": app, "summary": summary, "t": float(getattr(obs, "t", 0) or 0)})
        if self.step is not None:
            await self.evaluate("screen")

    def overlay_bounds(self, rects: list[dict]) -> None:
        if self.screen is not None:
            self.screen.set_overlay(rects)

    async def on_file_change(self, paths: list[str] | None = None) -> None:
        self._touch()
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
            return
        if kind in ("metric", "metrics"):
            items = ev.get("metrics") or ev.get("items") or [ev]
            for it in items:
                try:
                    step_n, name, value = int(it["step"]), str(it["name"]), float(it["value"])
                except (KeyError, TypeError, ValueError):
                    continue
                run.add_metric(step_n, name, value)
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

        async def later() -> None:
            await asyncio.sleep(self.metric_eval_s)
            self._metric_eval_pending = False
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
        step = self.step
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
            if want not in DIAGRAM_KINDS:
                metric_fail = any(r.get("status") == "fail" and r.get("checkId") in
                                  {c["id"] for c in step.get("checks", []) if c.get("type", "").startswith("metric")}
                                  for r in self.last_results)
                want = "gradients" if metric_fail or self.last_offtrack else "network"
            d = await self.m.diagram(want, step, self.context())
            await self.emit("diagram", d)
            return
        if kind == "voice_toggle":
            self.voice = not self.voice
            return
        if kind == "apply_fix":
            await self._apply_fix(step)
            return
        await self.emit("error", {"message": f"Unknown action: {kind}"})

    def _explain_context(self) -> dict:
        code, file = self._code_excerpt(self.step) if self.step else ("", None)
        return {
            "lesson": (self.graph or {}).get("lesson", {}),
            "query": self.query,
            "checks": self.last_results,
            "metrics": metrics_summary(self.context().metrics),
            "metrics_summary": self.context().metrics,  # coach (E5) wants the raw series
            "code": code,
            "file": file,
            "offtrack": self.last_offtrack,
        }

    async def _apply_fix(self, step: dict) -> None:
        diff = (self.last_offtrack or {}).get("diff") or {}
        file, yours, expected = diff.get("file"), diff.get("yours"), diff.get("expected")
        if not (file and yours and expected):
            await self.emit("card", {"stepId": step["id"], "kind": "hint", "title": "No automatic fix",
                                     "body": "This one needs your hands. Try a hint."})
            return
        path = Path(file) if Path(file).is_absolute() else Path(self.workdir) / file
        try:
            text = path.read_text()
        except OSError as e:
            await self.emit("error", {"message": f"Could not open {file}: {e}"})
            return
        new_text = self.m.propose_fix(diff, text)
        if new_text is not None and path.suffix == ".py":
            try:
                compile(new_text, str(path), "exec")
            except SyntaxError:
                log.warning("proposed fix for %s does not compile; asking the learner to do it", path.name)
                new_text = None
        if new_text is None or new_text == text:
            await self.emit("card", {"stepId": step["id"], "kind": "hint", "title": "Fix it by hand",
                                     "body": f"Replace `{yours.strip()}` with `{expected.strip()}`."})
            return
        path.write_text(new_text)  # the learner asked for it (apply_fix action)
        await self.on_file_change([str(path)])

    # ------------------------------------------------------------------ reconnect
    def snapshot(self) -> list[tuple[str, dict]]:
        """Messages that bring a freshly connected client up to date."""
        out: list[tuple[str, dict]] = []
        if self.graph is None:
            out.append(("status", {"state": self.status}))
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
            "consecutiveFails": self.consecutive_fails,
            "runs": [r.run_id for r in self.step_runs],
            "modules": self.m.describe(),
            "precisionMode": self.precision_mode(),
            "screen": bool(self.screen is not None and getattr(self.screen, "active", False)),
            "voice": self.voice,
        }
