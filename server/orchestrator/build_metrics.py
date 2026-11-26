"""Lesson build time, by stage (lane build-metrics).

One record per lesson build: from the learner's command (learn / learn_url / build_lesson / library.start /
review.start, stamped when the engine RECEIVES it, so a wait in the command queue counts) to `lesson.ready` and to the
first `step.started`. When the build ends (first step, failure, cancel) the record is

* logged as one line, `build.metrics {json}`, on the `orchestrator.build_metrics` logger (the engine log), and
* appended to `<state dir>/build-metrics.jsonl` (server.sessions.store.state_dir(): $MIYAGI_STATE_DIR, else
  ~/miyagi/state), a rolling file that keeps the last MAX_LINES builds.

Marks are taken on the session's clock (LessonSession.clock, monotonic; tests pass a fake one). A stage is the time
from its mark to the next mark seen, so the stages add up to the whole build with no gaps. Marks, in build order:

  command     the learner's command arrived            -> stage "preflight": search rows, the preflight card and the
                                                           learner's Build press, the command queue (not the build)
  build       the build task starts (_run_build)       -> "setup": cache lookup, workdir scan, the watch-page
                                                           metadata fetch (<= 10 s when preflight had no length)
  captions    builder stage reading_transcript         -> "captions": captions + the tutorial's linked code
  watch       builder stage watching (Gemini; off)      -> "watch"
  plan        builder stage planning                   -> "plan": the text lesson's plan call / a long video's parts
  steps       builder stage writing_steps              -> "steps": Claude writes the steps (text: step 1)
  checks      builder stage steps_ready / adapting     -> "checks": link checks, the adapt pass that fits the checks
                                                           to the learner's folder, community mistakes, goal match
  handoff     builder stage done / cache_hit /          -> "handoff": the builder returned (or a first part / step 1
              first_steps / provisional                    / the quick-start placeholder arrived)
  workspace   the lesson folder is being prepared      -> "workspace": workspace.prepare (starter files)
  hold        the "Lesson ready" moment                -> "hold": ORCH_READY_HOLD_S (1.5 s; 0.6 s cache / curated)
  ready       lesson.ready went out                    -> "start": opening the editor (lesson mode), step 1's file
  first_step  the first step.started went out          (end)

A mark is kept the first time it is seen; a mark the build never reaches is simply absent (a cache hit has no
captions / steps / checks). Nothing here may ever break a build: every entry point swallows its own errors.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("orchestrator.build_metrics")

FILE_NAME = "build-metrics.jsonl"
MAX_LINES = 500  # the rolling file keeps this many builds (one line each, ~0.5 KB)
VERSION = 1

# builder (server.lesson.builder.STAGES) stage id -> our mark
PROGRESS_MARKS = {
    "reading_transcript": "captions",
    "watching": "watch",
    "planning": "plan",
    "writing_steps": "steps",
    "steps_ready": "checks",
    "adapting": "checks",
    "done": "handoff",
    "cache_hit": "handoff",
    "first_steps": "handoff",
    "provisional": "handoff",
}
# mark -> the stage that starts at it
STAGE_OF_MARK = {
    "command": "preflight", "build": "setup", "captions": "captions", "watch": "watch", "plan": "plan",
    "steps": "steps", "checks": "checks", "handoff": "handoff", "workspace": "workspace", "hold": "hold",
    "ready": "start",
}
MARKS = ("command", *[m for m in STAGE_OF_MARK if m != "command"], "first_step")


def metrics_path() -> Path:
    from server.sessions import store

    return store.state_dir() / FILE_NAME


def _r(x: float) -> float:
    return round(max(0.0, x), 2)


class BuildRecord:
    """One build's marks. Callbacks from a build that was replaced talk to their own (closed) record: no-ops."""

    def __init__(self, owner: "BuildMetrics", kind: str, command: str | None, cmd_t: float | None,
                 t0: float, source: str | None = None) -> None:
        self.owner = owner
        self.kind = kind
        self.command = command
        self.source = source
        self.marks: dict[str, float] = {}
        self.flags: dict[str, Any] = {}
        self.closed = False
        if cmd_t is not None:
            self.marks["command"] = cmd_t
        self.marks["build"] = t0

    def mark(self, name: str) -> None:
        try:
            if not self.closed and name not in self.marks:
                self.marks[name] = self.owner.clock()
        except Exception:  # noqa: BLE001 - metrics never break a build
            log.debug("build metrics mark failed", exc_info=True)

    def progress(self, stage: str, message: str = "") -> None:
        """The builder's on_progress(stage, message) callback (sync; safe to call from any build task)."""
        if self.closed:
            return
        if stage == "cache_hit":
            self.flags["cacheHit"] = True
        elif stage == "provisional":
            self.flags["provisional"] = True
        elif stage == "transcript_only":
            self.flags["transcriptOnly"] = True
        elif stage == "engine_switch":
            self.flags["engineSwitch"] = str(message or "")[:40]
        elif stage == "steps_ready" and message:
            self.flags["engine"] = str(message)[:20]
        if (m := PROGRESS_MARKS.get(stage)) is not None:
            self.mark(m)

    def stages(self, end: float | None = None) -> dict[str, float]:
        """Stage -> seconds: each mark until the next one (by time), the last one until `end` (or nothing)."""
        seq = sorted(self.marks.items(), key=lambda kv: kv[1])
        out: dict[str, float] = {}
        for i, (name, t) in enumerate(seq):
            nxt = seq[i + 1][1] if i + 1 < len(seq) else end
            if name in STAGE_OF_MARK and nxt is not None:
                out[STAGE_OF_MARK[name]] = _r(nxt - t)
        return out

    def summary(self, outcome: str, **extra: Any) -> dict:
        m = self.marks
        start = m.get("command", m["build"])
        end = m.get("first_step") or m.get("ready")
        out: dict[str, Any] = {"v": VERSION, "at": round(self.owner.wall(), 3), "kind": self.kind, "outcome": outcome}
        if self.command:
            out["command"] = self.command
        if self.source:
            out["source"] = self.source
        for key, mark in (("toReadyS", "ready"), ("toFirstStepS", "first_step")):
            if mark in m:
                out[key] = _r(m[mark] - start)
        if "command" in m:
            for key, mark in (("buildToReadyS", "ready"), ("buildToFirstStepS", "first_step")):
                if mark in m:
                    out[key] = _r(m[mark] - m["build"])
        if end is None:  # failed / cancelled: how long it ran before that
            end = self.owner.clock()
            out["elapsedS"] = _r(end - start)
        out["stages"] = self.stages(end)
        out["marks"] = {k: _r(t - start) for k, t in sorted(m.items(), key=lambda kv: kv[1])}
        out.update(self.flags)
        out.update({k: v for k, v in extra.items() if v is not None})
        return out


class BuildMetrics:
    """The session's build timer: at most one open record (the build in flight)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time,
                 path: Callable[[], Path] | None = None, max_lines: int = MAX_LINES) -> None:
        self.clock = clock
        self.wall = wall
        self._path = path or metrics_path
        self.max_lines = max_lines
        self.current: BuildRecord | None = None
        self._cmd: tuple[str, float] | None = None
        self.last: dict | None = None  # the last finished record (tests, the lesson.ready buildS field)

    # ------------------------------------------------------------------ marks
    def command(self, kind: str) -> None:
        """A lesson-start command arrived (main.py's receive loop). The next build started counts from here."""
        try:
            self._cmd = (str(kind), self.clock())
        except Exception:  # noqa: BLE001
            log.debug("build metrics command failed", exc_info=True)

    def begin(self, kind: str, source: str | None = None) -> BuildRecord:
        """A build task starts (_run_build). A build still open is closed as cancelled (it was replaced)."""
        self.cancel("replaced")
        cmd, self._cmd = self._cmd, None
        self.current = BuildRecord(self, kind, cmd[0] if cmd else None, cmd[1] if cmd else None, self.clock(), source)
        return self.current

    def _open(self) -> BuildRecord | None:
        rec = self.current
        return rec if rec is not None and not rec.closed else None

    def mark(self, name: str) -> None:
        if (rec := self._open()) is not None:
            rec.mark(name)

    def ready(self, **info: Any) -> float | None:
        """lesson.ready went out for the build in flight. -> seconds from the command (None: no build in flight)."""
        rec = self._open()
        if rec is None or "ready" in rec.marks:
            return None
        rec.mark("ready")
        for k, v in info.items():
            if v is not None:
                rec.flags[k] = v
        m = rec.marks
        return _r(m["ready"] - m.get("command", m["build"]))

    def first_step(self, index: int | None = None) -> None:
        """The first step.started after this build's lesson.ready: the record is complete."""
        rec = self._open()
        if rec is None or "ready" not in rec.marks:
            return
        rec.mark("first_step")
        self._finish(rec, "ok", firstStepIndex=index)

    def failed(self, code: str | None = None) -> None:
        if (rec := self._open()) is not None:
            self._finish(rec, "failed", failCode=code)

    def cancel(self, reason: str = "cancelled") -> None:
        """end_lesson / a new build while this one is open (lesson.ready not reached, or no step started yet)."""
        if (rec := self._open()) is not None:
            self._finish(rec, "cancelled", reason=reason)

    # ------------------------------------------------------------------ output
    def _finish(self, rec: BuildRecord, outcome: str, **extra: Any) -> None:
        rec.closed = True
        if self.current is rec:
            self.current = None
        try:
            line = rec.summary(outcome, **extra)
        except Exception:  # noqa: BLE001
            log.debug("build metrics summary failed", exc_info=True)
            return
        self.last = line
        text = json.dumps(line, separators=(",", ":"), ensure_ascii=False)
        log.info("build.metrics %s", text)
        self._append(text)

    def _append(self, text: str) -> None:
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("MIYAGI_STATE_DIR"):
            return  # a test that didn't isolate the state folder never writes the learner's real file
        try:
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(text + "\n")
            self._trim(path)
        except Exception:  # noqa: BLE001 - a full disk / read-only folder: the log line still has it
            log.debug("build metrics write failed", exc_info=True)

    def _trim(self, path: Path) -> None:
        """Keep the last max_lines lines. Rewritten (atomically) only once the file is 10% over, not on every build."""
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= self.max_lines + max(1, self.max_lines // 10):
            return
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text("\n".join(lines[-self.max_lines:]) + "\n", encoding="utf-8")
        os.replace(tmp, path)


def read(path: Path | None = None, limit: int | None = None) -> list[dict]:
    """The rolling file's records, oldest first (bad lines skipped)."""
    p = path or metrics_path()
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-limit:] if limit else lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out
