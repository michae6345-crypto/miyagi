"""SceneWatch: the session side of the Haiku scene look (server/coach/scene.py). Michael: Miyagi should notice what's
on screen every ~5 s during a lesson instead of only reacting.

Hooks in LessonSession (kept tiny for merges): `await scene_watch.tick(self)` in tick() (~1/s) and
`"scene": scene_watch.state(self)` in state(). Everything else lives here.

A look runs only when ALL hold:
- MIYAGI_SCENE_EVERY_S (default 5; 0 = off) since the last look of this step (coach.gate.PeriodicGate's interval);
- a lesson step is active: not passed, not awaiting "Continue?", not while the step's video clip plays;
- the reader is up and the display awake (session.screen_down_reason() is None: no ScreenUnavailableError, no
  missing permission) and its latest frame is < 30 s old;
- the screen changed since the last look: a newer OCR'd frame (obs.frame) whose text differs (PeriodicGate:
  clocks / dates / percentages and line order ignored), or a step file was saved;
- the learner isn't typing into Miyagi itself, and no private app (1Password, Messages, …) is frontmost;
- no look in flight. Budget: PeriodicGate stops after MIYAGI_SCENE_STOP_AFTER (30) looks in a row that saw the same
  scene, until a save or a big screen change (>= 25% of the lines); a hard cap of MIYAGI_SCENE_MAX_PER_HOUR (720)
  looks in any hour; a failed look backs off 15 s, 30 s … 5 min; no key turns it off (logged once);
- not in demo / offline mode (DEMO=1, ORCH_STUBS=coach), never without the real screen reader (FakeScreen tests:
  off), and not under pytest, unless a fake look is injected (attach(session, look=FakeLook(...), frame=...)) or
  MIYAGI_SCENE_EVERY_S is set explicitly.

What a look is used for (no new card types, no spam):
(a) the editor is in front but the step's file isn't its active tab, in 2 looks in a row -> the existing "where"
    card (with Open), once per step, paced like every proactive card (_emit_card auto); never when the reader's own
    active-file read (companion extension / AX / title + OCR) says the step's file IS the active one;
(b) error_visible on a step that ran something -> diagnose appends it to its error text (coach.scene.with_error),
    no extra call;
(c) the latest look in session.state()["scene"]; judge / explain / hint read coach.scene.fresh() (< 8 s);
(d) spotlight_target_visible false in 2 looks in a row while the editor shows the step's file (or it's a run step)
    -> the existing spotlight placement re-runs once per step.
A look never passes or fails a check.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Any

from . import config

log = logging.getLogger("orchestrator.scene")

WHERE_AFTER = 2  # looks in a row without the step's file as the active tab -> the where card
SPOT_AFTER = 2  # looks in a row without the spotlight's target on screen -> place the spotlight again
RESPOT_EVERY_S = 15.0  # E16: a look that sees the step's file with no box up places it again, at most this often
FRAME_MAX_AGE_S = 30.0  # the reader re-OCRs at least every ~15 s while the display is awake
EDITOR_APPS = {"code", "vs code", "vscode", "visual studio code", "cursor"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _scene_mod() -> Any:
    try:
        from server.coach import scene
    except Exception:
        log.exception("server.coach.scene unavailable; scene looks off")
        return None
    return scene


class SceneWatch:
    def __init__(self, session: Any, *, look: Any = None, frame: Any = None, every_s: float | None = None,
                 max_per_hour: int | None = None, stop_after: int | None = None):
        self.s = session
        self._look = look  # None: coach.scene.look (Haiku); tests inject coach.scene.FakeLook
        self._frame = frame  # None: reader.latest_frame(); tests: a callable -> (PIL image, obs)
        self.injected = look is not None
        self.every_s = _env_float("MIYAGI_SCENE_EVERY_S", 5.0) if every_s is None else float(every_s)
        self.max_per_hour = int(_env_float("MIYAGI_SCENE_MAX_PER_HOUR", 720) if max_per_hour is None else max_per_hour)
        self.stop_after = max(1, int(_env_float("MIYAGI_SCENE_STOP_AFTER", 30) if stop_after is None else stop_after))
        self._gate: Any = None  # coach.gate.PeriodicGate, made on the first look (no coach import while off)
        self.off_reason: str | None = None  # "no_key" / "offline" / "no coach": off for this process
        self.latest: Any = None
        self.looks = 0
        self._task: asyncio.Task | None = None
        self._key: str | None = None
        self._last_frame: Any = None
        self._hour: deque[float] = deque()
        self._cap_logged = False
        self._fails = 0
        self._retry_at = -1e9
        self._epoch: Any = None
        self._gen: Any = None
        self._reset_step()

    # ------------------------------------------------------------------ gates
    @property
    def gate(self) -> Any:
        """PeriodicGate: interval MIYAGI_SCENE_EVERY_S (MIYAGI_SCENE_CAP_S > it lets a repeated scene back off), only on a
        changed screen / saved file, stop after `stop_after` identical scenes until a save or a big screen change."""
        if self._gate is None:
            from server.coach.gate import PeriodicGate

            base = self.every_s if self.every_s > 0 else 5.0
            self._gate = PeriodicGate(base_s=base, cap_s=max(base, _env_float("MIYAGI_SCENE_CAP_S", base)),
                                      stop_after=self.stop_after, clock=self.s.clock)
        return self._gate

    def enabled(self) -> bool:
        if self.every_s <= 0 or self.off_reason:
            return False
        if self.injected:
            return True
        if "PYTEST_CURRENT_TEST" in os.environ and "MIYAGI_SCENE_EVERY_S" not in os.environ:
            return False
        try:
            from server.coach import llm

            if llm.offline_mode():  # DEMO=1 / ORCH_STUBS=coach: zero-cost mode
                return False
        except Exception:  # noqa: BLE001
            return False
        return getattr(self.s.screen, "reader", None) is not None

    def _reset_step(self) -> None:
        self._off_file = 0
        self._where_sent = False
        self._spot_miss = 0
        self._spot_redone = False

    def _clear(self) -> None:
        if self.latest is not None and (m := _scene_mod()) is not None:
            m.clear()  # judge / explain / hint must not read the last lesson's (or step's) look
        self.latest = None
        self._last_frame = None

    def _typing_in_miyagi(self) -> bool:
        inp = self.s.inputs
        own = getattr(inp, "miyagi_in_front", None) if inp is not None else None
        try:
            if not (callable(own) and own()):
                return False
            v = inp.seconds_since_key()
        except Exception:  # noqa: BLE001
            return False
        return v is not None and v < max(config.TYPING_GUARD_S, 3.0)

    def _budget(self, now: float) -> bool:
        while self._hour and now - self._hour[0] > 3600.0:
            self._hour.popleft()
        if len(self._hour) < self.max_per_hour:
            self._cap_logged = False
            return True
        if not self._cap_logged:
            self._cap_logged = True
            log.warning("scene: %d looks in the last hour (MIYAGI_SCENE_MAX_PER_HOUR); paused", self.max_per_hour)
        return False

    @staticmethod
    def _private_front(obs: Any) -> bool:
        try:
            from server.screen.privacy import is_private_app
        except Exception:  # noqa: BLE001
            return False
        return is_private_app(getattr(obs, "app", None))

    def _screen_text(self, obs: Any) -> str:
        """What PeriodicGate compares: the OCR lines by app (+ VS Code's terminal panel) and the window titles."""
        rows = [f"@front {getattr(obs, 'app', '') or ''}"]
        rows += [f"@win {getattr(w, 'app', '')} {getattr(w, 'title', '')}" for w in getattr(obs, "windows", None) or []]
        for app, lines in (self.s._screen_lines() or {}).items():
            rows += [f"{app}: {ln}" for ln in lines or []]
        return "\n".join(rows)

    # ------------------------------------------------------------------ the tick
    async def tick(self) -> None:
        s = self.s
        if s.lesson_epoch != self._epoch:  # a new lesson (or none): forget the old one's looks
            self._epoch = s.lesson_epoch
            self._clear()
        step = s.step
        if step is None or s.phase != "active":
            if self.latest is not None:
                self._clear()
            return
        if s.step_gen != self._gen:
            self._gen = s.step_gen
            self._reset_step()
        if not self.enabled() or s.passed or s.awaiting_resume:
            return
        if self._task is not None and not self._task.done():
            return  # one look in flight at most
        now = s.clock()
        if now < self._retry_at or (s.video_playing and not s.segment_done):
            return
        if s.screen_down_reason() or self._typing_in_miyagi():
            return  # asleep / locked / capture failing; or the learner is typing into Miyagi
        obs = s.last_obs
        if obs is None or self._private_front(obs):
            return
        frame_no = getattr(obs, "frame", None)
        if frame_no is not None and frame_no == self._last_frame:
            return  # no new OCR'd frame since the last look: nothing changed
        t = getattr(obs, "t", None)
        if not self.injected and isinstance(t, (int, float)) and t > 0 and time.time() - t > FRAME_MAX_AGE_S:
            return  # the reader stopped producing frames (asleep, Space switch): don't look at a stale screen
        gk = s._judge_gate_kwargs(step)
        screen = self._screen_text(obs)
        key = f"{s.lesson_epoch}:{s.step_gen}"
        if not self.gate.allow(key, screen=screen, files=gk["file_mtimes"], screen_ok=gk["screen_ok"],
                               asleep=gk["display_asleep"]):
            return  # unchanged, too soon, or stopped after the same scene 30 times
        if not self._budget(now):
            return
        self.gate.started(key, screen=screen, files=gk["file_mtimes"])
        self._key, self._last_frame = key, frame_no
        self._hour.append(now)
        self._task = s._spawn(self._run(s.step_gen, step, key, frame_no))

    # ------------------------------------------------------------------ one look
    def _grab(self) -> tuple[Any, Any] | None:
        if self._frame is not None:
            return self._frame()
        reader = getattr(self.s.screen, "reader", None)
        if reader is None or not hasattr(reader, "latest_frame"):
            return None
        img, obs = reader.latest_frame()  # overlay + other folders' VS Code windows already blacked out
        return (img, obs) if img is not None and obs is not None else None

    @staticmethod
    def _mask_args(obs: Any) -> dict:
        """Private apps' windows (1Password, Messages, …) are blacked out before the image leaves the Mac."""
        try:
            from server.screen.privacy import is_private_app
        except Exception:  # noqa: BLE001
            def is_private_app(app: Any) -> bool:
                return False
        rects = [w.rect for w in getattr(obs, "windows", None) or [] if is_private_app(getattr(w, "app", None))]
        scr = getattr(obs, "screen", None)
        return {"mask": rects, "scale": float(getattr(obs, "scale", 1.0) or 1.0),
                "origin": (float(getattr(scr, "x", 0.0) or 0.0), float(getattr(scr, "y", 0.0) or 0.0))}

    def _spot_text(self, step: dict, run: str) -> str:
        """What Miyagi's spotlight points at for this step, in words."""
        s = self.s
        if run:
            return f"VS Code's integrated terminal panel, where `{run.splitlines()[0][:80]}` is run"
        f = s._step_file(step)
        target = next((t for t in step.get("targets") or [] if t.get("match")), None)
        if s.lesson_mode or target is None:
            return f"the line in {Path(f).name} where the step's code goes" if f else ""
        return target.get("caption") or f"the line matching {str(target['match'])[:80]}"

    def _ran(self) -> bool:
        """Did this step run something: a `tut run` / screen-read run, Run it for me, or new terminal output?"""
        s = self.s
        if getattr(s, "step_runs", None):
            return True
        if getattr(s, "_ext_run_t", 0.0) >= getattr(s, "_step_wall_t0", float("inf")):
            return True
        try:
            now = tuple(s._vscode_terminal_lines())
        except Exception:  # noqa: BLE001
            return False
        return bool(now) and now != getattr(s, "_term_at_start", ())

    async def _run(self, gen: int, step: dict, key: str, frame_no: Any) -> None:
        s = self.s
        mod = _scene_mod()
        if mod is None:
            self.off_reason = "no coach"
            return
        try:
            got = await asyncio.to_thread(self._grab)
        except Exception:
            log.exception("scene: no frame")
            return
        if got is None or gen != s.step_gen:
            return
        image, obs = got
        run = s._run_command(step)
        look = self._look or mod.look
        try:
            sc = await look(image, step, step_file=s._step_file(step), run=run or None, spot=self._spot_text(step, run),
                            front_app=str(getattr(obs, "app", "") or ""), frame=frame_no, **self._mask_args(obs))
        except Exception as e:  # noqa: BLE001
            kind = getattr(e, "kind", None)
            if kind in ("no_key", "offline"):
                self.off_reason = kind
                log.warning("scene looks off: %s", e)
                return
            self._fails += 1
            delay = min(300.0, 15.0 * 2 ** (self._fails - 1))
            self._retry_at = s.clock() + delay
            log.warning("scene look failed (%s: %s); next try in %.0f s", type(e).__name__, e, delay)
            return
        self._fails = 0
        if gen != s.step_gen or s.passed or s.step is not step:
            return  # the learner moved on meanwhile: this look is about the old step
        sc.step_id = step.get("id")
        sc.after_run = self._ran()
        self.gate.record(key, sc.signature())
        mod.publish(sc)
        self.latest = sc
        self.looks += 1
        try:
            await self._react(step, sc, obs, run)
        except Exception:
            log.exception("scene reaction failed")

    # ------------------------------------------------------------------ reactions
    async def _react(self, step: dict, sc: Any, obs: Any, run: str) -> None:
        s = self.s
        frozen = getattr(s, "_spot_frozen", None)
        if frozen is not None and frozen():
            return  # E7: the resume card is up / no app: no where card, no box, no targeter call
        f = s._step_file(step)
        editor_front = bool({str(getattr(obs, "app", "") or "").lower(), sc.app.lower()} & EDITOR_APPS)
        if f and not run and not s.notebook_lesson:  # (a) the step's file isn't the active tab
            name = Path(f).name.lower()
            # only while the editor is in front: reading docs in Chrome says nothing about VS Code's active tab
            off = editor_front and not sc.step_file_open and (sc.active_file or "").lower() != name
            self._off_file = self._off_file + 1 if off else 0
            if self._off_file >= WHERE_AFTER and not self._where_sent:
                await self._where(step, name)
        if self._spot_text(step, run):  # (d) the spotlight's target isn't on screen
            in_editor = editor_front and (sc.step_file_open or bool(run))
            self._spot_miss = self._spot_miss + 1 if (in_editor and not sc.spotlight_target_visible) else 0
            if self._spot_miss >= SPOT_AFTER and not self._spot_redone and not s.typing() and not s.coaching:
                self._spot_redone = True
                log.info("scene: the spotlight's target wasn't on screen in %d looks; placing it again (%s)",
                         self._spot_miss, step.get("id"))
                if s.lesson_mode:
                    s._spawn(s._lesson_spot(s.step_gen, step, tries=3), timer=True)
                else:
                    await s._spotlight_target(step)
            elif (s.lesson_mode and in_editor and getattr(s, "spot_rect", 0) is None and not getattr(s, "_spot_away", False)
                  and not s.coaching and not (run and s._step_ran())
                  and not getattr(s, "_respot_held", lambda: False)()  # the targeter just refused it: backing off
                  and s.clock() - getattr(self, "_respot_t", -1e9) >= RESPOT_EVERY_S):
                # (e) E16: the step's file is in front and no box is up (the first tries ran under a save dialog, or
                # the targeter said no then): place it again, one Haiku pick at most (tries=2; the engine's own
                # no-model retry runs every few seconds on new frames, session._maybe_respot)
                self._respot_t = s.clock()
                log.info("scene: %s is in front with no box; placing it again (%s)",
                         "the terminal" if run else Path(s._step_file(step) or "").name, step.get("id"))
                s._spawn(s._lesson_spot(s.step_gen, step, tries=2), timer=True)

    async def _where(self, step: dict, name: str) -> None:
        s = self.s
        if s.coaching or s._ask_held() or s.typing():
            return  # the next look tries again
        reader = getattr(s.screen, "reader", None)
        if reader is not None and hasattr(reader, "active_file"):  # the authoritative read wins over the glance
            try:
                af = await asyncio.to_thread(reader.active_file, False)
            except Exception:  # noqa: BLE001
                af = None
            if af and af.get("confidence") in ("exact", "agreed") and str(af.get("file") or "").lower() == name:
                log.info("scene: Haiku didn't see %s as the active tab, but %s says it is; no where card",
                         name, af.get("source"))
                self._off_file = 0
                return
        card = s._where_card(step)
        if await s._emit_card(card, window_s=60.0, auto=True):
            self._where_sent = True
            log.info("scene: %s not the active file in %d looks -> where card %r", name, self._off_file,
                     card.get("title"))

    # ------------------------------------------------------------------ state
    def state(self) -> dict:
        task_busy = self._task is not None and not self._task.done()
        mod = _scene_mod() if self.looks else None
        return {"enabled": self.enabled(), "off": self.off_reason, "everyS": self.every_s, "looks": self.looks,
                "lastHour": len(self._hour), "maxPerHour": self.max_per_hour, "inFlight": task_busy,
                "costUsd": (mod.stats().get("cost_usd") if mod is not None else 0.0),
                "gate": self.gate.state(self._key) if self._key else None,
                "latest": self.latest.to_dict() if self.latest is not None else None}


# ---------------------------------------------------------------------- session hooks

def attach(session: Any, **kw: Any) -> SceneWatch:
    """Give `session` its SceneWatch (tests: attach(session, look=FakeLook([...]), frame=lambda: (img, obs)))."""
    w = SceneWatch(session, **kw)
    session._scene_watch = w
    return w


def _get(session: Any) -> SceneWatch | None:
    w = getattr(session, "_scene_watch", None)
    if w is None:
        try:
            w = attach(session)
        except Exception:
            log.exception("scene watch unavailable")
            session._scene_watch = False  # don't retry every second
            return None
    return w or None


async def tick(session: Any) -> None:
    """LessonSession.tick() hook (~1/s). Never raises."""
    try:
        if (w := _get(session)) is not None:
            await w.tick()
    except Exception:
        log.exception("scene tick failed")


def state(session: Any) -> dict | None:
    """LessonSession.state() hook: the latest look + the watch's counters, or None."""
    try:
        w = _get(session)
        return w.state() if w is not None else None
    except Exception:
        log.exception("scene state failed")
        return None
