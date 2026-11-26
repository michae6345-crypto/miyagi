"""The setup gate: while the lesson's environment is still being installed, the lesson waits (user test Nov 25).

MacBook Neo, fresh install: the learner pressed Install all, the packages were still installing (TensorFlow: minutes),
and the lesson had already started and its video played. Nov 22's rule was "setup is a companion, not a gate"
(setup.holdVideo true only on the install step itself). The gate changes that for installs actually running:

    idle     nothing is installing for this lesson (the setup card stays a companion, as before)
    running  something is queued or installing        -> the lesson holds: video paused, no segment end, no nags
    failed   a required row failed, nothing running   -> still held: Retry / Show details / Continue anyway
    done     everything settled (installed, skipped optional, or Continue anyway) -> released, the video starts

Engine -> app: `setup.gate` {phase, holds, items: [{tool, label, status, optional, phase?, pct?, error?, errorCode?,
log?, note?}], done, total, current?, elapsedS, startedAt (epoch ms)}. App -> engine: action setup_retry {text?: tool},
setup_continue, setup_skip {text: tool} (an optional row: cancels it if it is installing). Contract: events.ts.

SetupGate is pure (a clock in, payloads out): tests drive it without a session. The functions below glue it to
Session._install (session.py) and setup_rows.install_all.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("orchestrator.session")

QUEUED, INSTALLING, DONE, FAILED, SKIPPED = "queued", "installing", "done", "failed", "skipped"
SETTLED = (DONE, SKIPPED)
# Rows the lesson runs fine without: the gate offers Skip for them, and their failure never holds the lesson.
OPTIONAL_TOOLS = frozenset({"tensorflow-metal", "jupyterlab-widgets", "ipywidgets", "tensorboard"})
PUBLISH_EVERY_S = 0.5  # progress updates: at most two a second


@dataclass
class Row:
    tool: str
    label: str
    optional: bool = False
    status: str = QUEUED
    started: float | None = None
    ended: float | None = None
    progress: dict = field(default_factory=dict)
    last_line: str = ""
    error: str = ""
    error_code: str = ""
    note: str = ""
    log: str = ""

    def payload(self, now: float) -> dict:
        out: dict[str, Any] = {"tool": self.tool, "label": self.label, "status": self.status, "optional": self.optional}
        if self.status == INSTALLING:
            out.update({k: v for k, v in self.progress.items() if k in ("phase", "pct", "bytes", "totalBytes", "attempt")})
            if self.last_line:
                out["line"] = self.last_line[:160]
            if self.started is not None:
                out["elapsedS"] = round(now - self.started)
        if self.error:
            out["error"] = self.error
        if self.error_code:
            out["errorCode"] = self.error_code
        if self.note:
            out["note"] = self.note
        if self.status == FAILED and self.log:
            out["log"] = self.log[-6000:]
        return out


class SetupGate:
    def __init__(self, clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time) -> None:
        self.clock, self.wall = clock, wall
        self.rows: dict[str, Row] = {}
        self.started: float | None = None
        self.started_wall: float | None = None
        self.continued = False

    # ---------------------------------------------------------------- transitions
    def queue(self, tool: str, label: str = "", optional: bool = False) -> Row:
        """Add a row (or put a settled / failed one back in line). A new round of installs clears Continue anyway."""
        r = self.rows.get(tool)
        if r is None:
            r = self.rows[tool] = Row(tool, label or tool, optional)
        elif r.status != INSTALLING:
            r.status, r.error, r.error_code, r.log, r.progress, r.ended = QUEUED, "", "", "", {}, None
        if self.started is None or not self.active():
            self.started, self.started_wall = self.clock(), self.wall()
        self.continued = False
        return r

    def start(self, tool: str, label: str = "", optional: bool = False) -> Row:
        """A row's install begins. Already queued (Install all, Retry): it keeps the round's Continue anyway, so "Continue
        without it" isn't undone by the next row starting. A new press (no row, or a settled one) is a new round."""
        r = self.rows.get(tool)
        if r is None or r.status not in (QUEUED, INSTALLING):
            r = self.queue(tool, label, optional)
        r.status, r.started, r.progress, r.last_line = INSTALLING, self.clock(), {"phase": "starting"}, ""
        return r

    def progress(self, tool: str, data: dict) -> None:
        r = self.rows.get(tool)
        if r is not None and r.status == INSTALLING:
            r.progress = {**r.progress, **{k: v for k, v in data.items() if v is not None}}
            if data.get("phase") and data["phase"] != "downloading":  # a new phase: the old bar goes
                for k in ("pct", "bytes", "totalBytes"):
                    if k not in data:
                        r.progress.pop(k, None)

    def line(self, tool: str, text: str) -> None:
        r = self.rows.get(tool)
        if r is not None and r.status == INSTALLING and text and not text.startswith("Progress "):
            r.last_line = text

    def finish(self, tool: str, res: dict) -> Row | None:
        r = self.rows.get(tool)
        if r is None:
            return None
        r.ended, r.progress = self.clock(), {}
        r.note = str(res.get("note") or "")
        if res.get("cancelled") or (res.get("skipped") and not res.get("ok")):
            r.status, r.error, r.error_code = SKIPPED, "", str(res.get("errorCode") or "")
        elif res.get("ok"):
            r.status = SKIPPED if res.get("skipped") else DONE
            r.error, r.error_code = "", str(res.get("errorCode") or "") if res.get("skipped") else ""
        else:
            r.status = FAILED
            r.error = str(res.get("error") or "unknown error").strip()[:400]
            r.error_code = str(res.get("errorCode") or ("network" if res.get("offline") else "unknown"))
            r.log = str(res.get("log") or "")
        return r

    def skip(self, tool: str) -> bool:
        """An optional row: skipped (the caller cancels it if it was installing). A required row can't be."""
        r = self.rows.get(tool)
        if r is None or not r.optional or r.status in SETTLED:
            return False
        r.status, r.ended, r.progress = SKIPPED, self.clock(), {}
        return True

    def retry(self, tool: str | None = None) -> list[str]:
        """Failed rows (or the one named) back in line. -> their tools, for the caller to install again."""
        tools = [t for t, r in self.rows.items() if r.status == FAILED and (tool in (None, "", t))]
        for t in tools:
            self.queue(t)
        return tools

    def continue_anyway(self) -> None:
        self.continued = True

    def reset(self) -> None:
        self.rows.clear()
        self.started = self.started_wall = None
        self.continued = False

    # ---------------------------------------------------------------- state
    def active(self) -> bool:
        return any(r.status in (QUEUED, INSTALLING) for r in self.rows.values())

    @property
    def phase(self) -> str:
        if not self.rows:
            return "idle"
        if self.active():
            return "running"
        if not self.continued and any(r.status == FAILED and not r.optional for r in self.rows.values()):
            return "failed"
        return "done"

    @property
    def holds(self) -> bool:
        """The lesson waits: something required is installing / queued, or failed and not waved through.
        Continue anyway releases it even while an optional row still installs."""
        if self.continued:
            return False
        p = self.phase
        if p == "running":
            return any(r.status in (QUEUED, INSTALLING) and not r.optional for r in self.rows.values()) or \
                any(r.status == FAILED and not r.optional for r in self.rows.values())
        return p == "failed"

    def payload(self) -> dict:
        now = self.clock()
        rows = list(self.rows.values())
        cur = next((r for r in rows if r.status == INSTALLING), None)
        out: dict[str, Any] = {"phase": self.phase, "holds": self.holds,
                               "items": [r.payload(now) for r in rows],
                               "done": sum(r.status in SETTLED for r in rows), "total": len(rows)}
        if cur is not None:
            out["current"] = cur.tool
        if self.started is not None:
            out["elapsedS"] = round(now - self.started)
            out["startedAt"] = int((self.started_wall or 0) * 1000)
        return out


# ------------------------------------------------------------------------- session glue

def gate(s: Any) -> SetupGate:
    """This lesson's gate (a new lesson gets a fresh one: keyed on lesson_epoch)."""
    g = getattr(s, "_setup_gate", None)
    ep = getattr(s, "lesson_epoch", 0)
    if g is None or getattr(s, "_setup_gate_epoch", None) != ep:
        g = SetupGate(getattr(s, "clock", time.monotonic))
        s._setup_gate, s._setup_gate_epoch = g, ep
        s._setup_gate_held, s._setup_gate_pub = False, 0.0
        s._setup_cancels = {}
    return g


def applies(s: Any) -> bool:
    """Installs gate a lesson that exists (not the preflight card's, before any lesson) and isn't a Demo take."""
    if getattr(s, "graph", None) is None:
        return False
    try:
        from . import stage

        return not stage.on(s)
    except Exception:  # noqa: BLE001
        return True


def optional(item: dict | None) -> bool:
    it = item or {}
    return it.get("needed") is False or str(it.get("tool") or "") in OPTIONAL_TOOLS


def cancel_event(s: Any, tool: str) -> threading.Event:
    gate(s)
    ev = threading.Event()
    s._setup_cancels[tool] = ev
    return ev


async def publish(s: Any, *, force: bool = True) -> None:
    """setup.gate out (progress: at most every PUBLISH_EVERY_S unless force), and the hold's edges: on engage the
    video pauses; on release the step's segment clock starts again (it never ran while held)."""
    g = gate(s)
    now = s.clock() if hasattr(s, "clock") else time.monotonic()
    if not force and now - getattr(s, "_setup_gate_pub", 0.0) < PUBLISH_EVERY_S:
        return
    s._setup_gate_pub = now
    held, was = g.holds, getattr(s, "_setup_gate_held", False)
    s._setup_gate_held = held
    await s.emit("setup.gate", g.payload())
    if held and not was:
        log.info("setup gate: the lesson waits for %s", [r.tool for r in g.rows.values() if r.status != DONE])
        await s.emit("video.pause", {})
    elif was and not held:
        log.info("setup gate released (%s)", g.phase)
        restart = getattr(s, "_restart_segment_clock", None)
        if restart is not None:
            await restart()


async def settle(s: Any, tool: str, *, failed: bool = False) -> None:
    """A row still queued / installing after its install returned (an early return, an exception): settle it, so the
    lesson never waits on a row nothing will finish. failed: as a failure (Retry / Continue anyway), else skipped."""
    g = gate(s)
    r = g.rows.get(tool)
    if r is None or r.status not in (QUEUED, INSTALLING):
        return
    if failed and r.status == INSTALLING:
        g.finish(tool, {"ok": False, "error": "The install stopped unexpectedly.", "errorCode": "unknown"})
    else:
        g.finish(tool, {"skipped": True, "cancelled": True})
    await publish(s)


def current_payload(s: Any) -> dict | None:
    """This lesson's gate as setup.gate sends it, or None when it is idle (no rows). Sent right after every lesson.ready
    (replays included) and on every client connect, so an app that restarted or reconnected mid-install gets the live
    gate back (review H2). An idle gate isn't sent: the app clears its gate on every lesson.ready and on a disconnect,
    and the connect burst of an engine with nothing going on stays exactly as it was (test_launch_contract)."""
    p = gate(s).payload()
    return None if p["phase"] == "idle" else p


def holds(s: Any) -> bool:
    g = getattr(s, "_setup_gate", None)
    return g is not None and getattr(s, "_setup_gate_epoch", None) == getattr(s, "lesson_epoch", 0) and g.holds


def call_install(fn: Callable, item: dict, folder: Any, on_line: Callable, **extra: Any) -> dict:
    """fn(item, folder, on_line) plus on_progress / cancel when it takes them (tests stub a 3-argument install)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    takes_any = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    kw = {k: v for k, v in extra.items() if takes_any or k in params}
    return dict(fn(item, folder, on_line, **kw))


async def act(s: Any, kind: str, text: str | None) -> bool:
    """The gate's buttons. -> True when handled."""
    g = gate(s)
    tool = (text or "").strip()
    if kind == "setup_continue":  # "Continue anyway": the lesson starts with what's there
        g.continue_anyway()
        await publish(s)
        return True
    if kind == "setup_skip":
        if g.skip(tool):
            ev = getattr(s, "_setup_cancels", {}).get(tool)
            if ev is not None:
                ev.set()  # install() kills its pip; its result lands as "cancelled" (stays skipped)
            await publish(s)
        return True
    if kind == "setup_retry":
        tools = g.retry(tool or None)
        await publish(s)
        # Never inside the command queue (review H1): a TensorFlow install can take an hour, and Skip / Continue anyway
        # / step changes must still get through. One task runs the retried rows in turn.
        spawn = getattr(s, "_spawn", None)
        job = retry_rows(s, tools)
        if spawn is not None:
            spawn(job)
        else:
            await job
        return True
    return False


async def retry_rows(s: Any, tools: list[str]) -> None:
    """Install the retried rows one after another. The .venv row builds the environment again (run_venv); any row an
    install left queued (an early return) is settled, so the gate never waits on it (review H3)."""
    for t in tools:
        if t == KERNEL:
            await retry_kernel(s)
            await settle(s, t, failed=True)
            continue
        if t == VENV:
            job = getattr(s, "_venv_job", None)
            if job is not None:
                await run_venv(s, *job)
            await settle(s, t, failed=job is None)
            continue
        item = next((it for it in getattr(s, "reqs", None) or [] if it.get("tool") == t), None)
        await s._install(t, item=item)
        await settle(s, t)


VENV = "venv"


def _venv_exists(folder: str) -> bool:
    try:
        from server.workspace import setup as ws_setup

        return bool(ws_setup.venv_python(folder))
    except Exception:  # noqa: BLE001
        return False


async def run_venv(s: Any, folder: str, fn: Callable[[], Any]) -> Any:
    """The background .venv build (ensure_lesson_venv: a fresh Mac's lesson gets its .venv from miyagi's Python) as a
    gate row, "Python environment": the lesson waits for it like any install. Kept (s._venv_job) so Retry can run it
    again."""
    s._venv_job = (folder, fn)
    g = gate(s)
    g.start(VENV, "Python environment")
    await publish(s)
    try:
        made = await asyncio.to_thread(fn)
    except Exception as e:  # noqa: BLE001 - ensure_lesson_venv never raises; belt and braces
        made = None
        log.exception("lesson .venv failed")
        g.finish(VENV, {"ok": False, "error": f"Couldn't make the lesson's Python environment: {e}"})
    else:
        if made or _venv_exists(folder):
            g.finish(VENV, {"ok": True})
        else:  # ensure_lesson_venv never raises: False with no .venv after it is a failure (its log says why)
            g.finish(VENV, {"ok": False, "errorCode": "no_python",
                            "error": "Couldn't make the lesson's Python environment. Press Retry, or Continue anyway."})
    await publish(s)
    return made


# ------------------------------------------------------------------------- the notebook kernel (user test Nov 26)

KERNEL = "kernel"
KERNEL_LABEL = "Notebook kernel"
# installs after which a VS Code notebook lesson checks that its kernel starts in the lesson's .venv
KERNEL_TOOLS = frozenset({"ipykernel", "jupyter", "notebook", "jupyterlab"})


def kernel_repair(folder: str, on_line: Callable[[str], None], cancel: threading.Event | None) -> dict:
    """server.workspace.setup.repair_kernel: pip install --force-reinstall ipykernel pyzmq (tests replace this)."""
    from server.workspace import setup as ws_setup

    return ws_setup.repair_kernel(folder, on_line=on_line, cancel=cancel)


async def retry_kernel(s: Any) -> None:
    """Retry on the "Notebook kernel" row. A broken import (ipykernel / zmq there but failing to load): reinstall
    ipykernel and pyzmq by force, as the row, then check again. Missing: install ipykernel (its install checks the
    kernel after). Else: check again."""
    folder = getattr(s, "workdir", None)
    row = gate(s).rows.get(KERNEL)
    code = getattr(s, "_kernel_failure", "") or ""
    if folder and code == "broken_import":
        g = gate(s)
        g.start(KERNEL, KERNEL_LABEL)
        await publish(s)
        loop = asyncio.get_running_loop()

        def on_line(text: str) -> None:
            loop.call_soon_threadsafe(lambda: g.line(KERNEL, str(text)[:300]))

        res = dict(await asyncio.to_thread(kernel_repair, folder, on_line, cancel_event(s, KERNEL)))
        if not res.get("ok"):
            g.finish(KERNEL, res)
            await publish(s)
            return
        await check_kernel(s)
        return
    item = next((it for it in getattr(s, "reqs", None) or [] if it.get("tool") == "ipykernel"), None)
    if item is not None and code == "missing":
        await s._install("ipykernel", item=item)  # its install checks the kernel (in the background)
        await settle(s, "ipykernel")
        job = getattr(s, "_kernel_job", None)
        if job is not None:
            await job
    if row is None or gate(s).rows[KERNEL].status == QUEUED:
        await check_kernel(s)


def _kernel_applies(s: Any) -> bool:
    if not getattr(s, "workdir", None) or not applies(s):
        return False
    from . import lesson_notebook

    return bool(lesson_notebook.name(s))


def check_kernel_soon(s: Any) -> None:
    """check_kernel in the background (review of #296): Install all goes on to TensorFlow while the kernel loads. The
    row is queued right away, so the gate never releases between the kernel's install and its check."""
    spawn = getattr(s, "_spawn", None)
    if spawn is None or not _kernel_applies(s):
        return
    gate(s).queue(KERNEL, KERNEL_LABEL)
    s._kernel_job = spawn(check_kernel(s))


def kernel_probe(folder: str) -> dict:
    """server.workspace.setup.kernel_check (tests replace this). Blocking."""
    from server.workspace import setup as ws_setup

    return ws_setup.kernel_check(folder)


async def check_kernel(s: Any) -> dict | None:
    """A VS Code notebook lesson, right after its kernel package installed: can the notebook kernel start in the
    lesson's .venv (ipykernel and its imports, no kernel started)? A gate row "Notebook kernel": done, or failed with a
    plain sentence (Retry installs ipykernel again; Continue anyway), so the learner never meets VS Code's "No kernel"
    picker with nothing said. None when it doesn't apply (not gated, not a VS Code notebook lesson, no folder)."""
    if not _kernel_applies(s):
        return None
    folder = s.workdir
    g = gate(s)
    g.start(KERNEL, KERNEL_LABEL)
    await publish(s)
    try:
        res = dict(await asyncio.to_thread(kernel_probe, folder))
    except Exception as e:  # noqa: BLE001 - kernel_check never raises; belt and braces
        log.exception("notebook kernel check failed")
        res = {"ok": False, "errorCode": "unknown", "error": f"Couldn't check the notebook kernel: {e}"}
    g.finish(KERNEL, res)
    s._kernel_failure = "" if res.get("ok") else str(res.get("errorCode") or "")
    log.info("notebook kernel in %s: %s", folder, "ready" if res.get("ok") else res.get("error"))
    await publish(s)
    return res
