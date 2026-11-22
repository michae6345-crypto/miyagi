"""Headless rehearsal of the judged Demo (docs/DEMO.md) against a PRIVATE engine: the regression gate for the run of show.

    python scripts/rehearse_demo.py                    # port 8899: a pass/fail table per DEMO.md step, JSON report
    python -m pytest server/tests/test_demo_rehearsal.py -q          # the same, as a test (marker demo_rehearsal)

It starts its own engine (server/tests/rehearsal_engine.py) on a spare port with HOME, the lessons folder and the
saved-progress folder in a temp dir, every paid key blank (TUT_ENV points at an empty file, so .env can't bring them
back), a dead proxy, no screen reader (ORCH_SCREEN=0), no window arranging, and MIYAGI_VSCODE_PORTS = a fake VS Code
companion served from this process. rehearsal_engine.py makes every desktop side effect a logged no-op. Nothing here
talks to :8787 or to the real companion (8791+), and it kills only the engine it started.

Then it plays Adrian's app over the WebSocket (shared/contracts/events.ts) and the presenter keys over /stage:

  take 1  the whole run of show: Demo chip -> Before you start -> Start -> nn1..nn3 pasted (zero weights) + saved ->
          nn4 Run it for me -> the stuck run -> Not yet "Loss is stuck at 0.49" -> Hint 1 of 2 -> random weights +
          Check my work -> 0.8187 -> 0.0009 -> nn5 -> nn6 Run it for me -> [-1.0, 0.0, 1.0] -> the completion card
  take 2  right after take 1: a fresh take; the presenter's next / back / restart; next through to the end; End
  take 3  after End: fresh; a deploy's POST /end + reconnect never brings a Demo back
  take 4  Demo again, mid-lesson
  take 5  "Just teach me" for the same goal from that running Demo: the real lesson, fresh, really graded; a deploy's
          POST /end + reconnect continues it at its step (claude/stable-nosave); End
  take 6  "Just teach me" again after End: step 1, clean nn.py, no resume card

Rows are "demo" (a DEMO.md step: must pass), "brief" (an item from the test-7 brief that a headless run can see:
reported, never fails the gate) or "info".
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
GOAL = "teach me to build a neural network from scratch"
LESSON_ID = "lesson-nn-from-scratch"
STARTER = ROOT / "demo" / "nn-start.py"
RUNS_FILE = ROOT / "demo" / "cache" / "stage" / "nn-runs.json"
DEFAULT_PORT = 8899
LIVE_PORT = 8787
BAD_PROXY = "http://127.0.0.1:9"  # the discard port: any proxied request fails at once, for free
PAID_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY",
             "TIGER_DATABASE_URL", "OPENAI_API_KEY", "YOUTUBE_API_KEY")
KEY_NAMES = ("anthropic", "gemini", "elevenlabs", "tigerUrl")
DWELL_S = 2.5  # stage.DWELL_S: a save in a step's first seconds doesn't count
SECTIONS = ("# The network", "# Backprop", "# Training", "# Test it")
_W_RANDOM = {"W1": "np.random.randn(1, 4)", "W2": "np.random.randn(4, 4)", "W3": "np.random.randn(4, 1) * 0.1"}
_W_ZEROS = {"W1": "np.zeros((1, 4))", "W2": "np.zeros((4, 4))", "W3": "np.zeros((4, 1))"}
_W_LINE = re.compile(r"^(?P<ind>\s*)(?P<name>W[123])\s*=\s*.+$", re.M)


class Fail(Exception):
    pass


# --------------------------------------------------------------------------------------------- report rows

@dataclass
class Row:
    id: str
    take: str
    ref: str  # where the expectation comes from: "DEMO §2 row 6", "brief 5", ...
    what: str
    tier: str = "demo"  # demo: must pass | brief: test-7 brief item, reported | info
    ok: bool | None = None
    secs: float = 0.0
    timings: dict[str, float] = field(default_factory=dict)
    fails: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    slack: float = 1.0  # timing limits x this (pytest: a loaded machine runs the suite next to it)

    def check(self, cond: Any, msg: str) -> bool:
        if not cond:
            self.fails.append(msg)
        return bool(cond)

    def time(self, name: str, secs: float | None, limit: float | None = None) -> None:
        if secs is None:
            return
        self.timings[name] = round(secs, 2)
        if limit is not None and secs > limit * self.slack:
            self.fails.append(f"{name} took {secs:.2f}s (limit {limit * self.slack:.1f}s)")

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "take", "ref", "what", "tier", "ok", "secs", "timings", "fails",
                                              "notes")}


# --------------------------------------------------------------------------------------------- fake companion

class FakeCompanion:
    """The VS Code companion extension's HTTP API (vscode-ext/extension.js), for ONE window that has the lesson folder
    open with nn.py in front. Reads come from the disk; every action is recorded and answered ok, nothing happens."""

    def __init__(self) -> None:
        self.folder: str | None = None
        self.calls: list[dict] = []
        self.lock = threading.Lock()
        self.focused_at = time.time() * 1000
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _send(self, code: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                u = urlparse(self.path)
                if u.path in ("/", "/health"):
                    return self._send(200, {"ok": True, "name": "miyagi-companion", "version": "rehearsal",
                                            "port": outer.port})
                if u.path == "/state":
                    return self._send(200, outer.state())
                if u.path == "/text":
                    want = (parse_qs(u.query).get("file") or [None])[0] or outer.nn_path()
                    try:
                        text = Path(want).read_text(encoding="utf-8") if want else None
                    except OSError:
                        text = None
                    if text is None:
                        return self._send(404, {"ok": False, "error": "not_found"})
                    return self._send(200, {"ok": True, "file": want, "text": text, "dirty": False,
                                            "version": int(time.time() * 1000), "languageId": "python",
                                            "lineCount": text.count("\n") + 1})
                return self._send(404, {"ok": False, "error": "no_route"})

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("content-length") or 0)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    body = {}
                with outer.lock:
                    outer.calls.append({"t": time.monotonic(), "route": urlparse(self.path).path, "body": body})
                return self._send(200, {"ok": True})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, name="fake-companion", daemon=True)

    def nn_path(self) -> str | None:
        return str(Path(self.folder) / "nn.py") if self.folder else None

    def state(self) -> dict:
        nn = self.nn_path()
        return {"ok": True, "app": "vscode", "extension": "rehearsal", "pid": os.getpid(), "port": self.port,
                "folders": [self.folder] if self.folder else [], "file": nn, "relPath": "nn.py" if nn else None,
                "dirty": False, "languageId": "python" if nn else None, "cursor": {"line": 1, "column": 1},
                "visibleRanges": [{"startLine": 1, "endLine": 40}], "dirtyFiles": [],
                "openFiles": [{"file": nn, "active": True}] if nn else [], "terminalOpen": False, "terminals": [],
                "lastCommand": None, "windowFocused": False, "lastFocusedAt": self.focused_at, "highlight": None}

    def since(self, t: float) -> list[dict]:
        with self.lock:
            return [c for c in self.calls if c["t"] >= t]

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()


# --------------------------------------------------------------------------------------------- the private engine

def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def engine_env(port: int, base: Path, companion_port: int, extra: dict[str, str] | None = None) -> dict[str, str]:
    """The private engine's environment: nothing of this Mac's real state, keys or editor is reachable from it."""
    drop = ("ORCH_", "TUT_", "MIYAGI_", "LESSON_", "COACH_", "ENGINE_", "DEMO", "VIRTUAL_ENV")
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    home = base / "home"
    for d in (home, base / "lessons", base / "state", base / "spool", base / "tts"):
        d.mkdir(parents=True, exist_ok=True)
    (base / "empty.env").write_text("# rehearsal: no keys\n", encoding="utf-8")
    env.update({
        "HOME": str(home),
        "MIYAGI_LESSONS_DIR": str(base / "lessons"), "MIYAGI_LESSONS": str(base / "lessons"),
        "MIYAGI_STATE_DIR": str(base / "state"),
        "TUT_ENV": str(base / "empty.env"),  # .env would otherwise put the paid keys back (dotenv never overrides "")
        "TUT_SPOOL_DIR": str(base / "spool"), "COACH_TTS_DIR": str(base / "tts"),
        "LESSON_GEMINI_USAGE_FILE": str(base / "state" / "gemini_usage.json"),
        "ENGINE_PORT": str(port), "ENGINE_HOST": "127.0.0.1",
        "ORCH_SCREEN": "0",  # no screen reader, no AX tree
        "ORCH_OPEN_WORKSPACE": "1",  # as scripts/miyagi-engine.sh; rehearsal_engine records the opens instead
        "ORCH_AUTOSTART": "0",
        "ORCH_AUTO_RESUME": "1",  # T5.3 rehearses a deploy restart mid-lesson (opt-in since Nov 21; app launches start fresh)
        "MIYAGI_ARRANGE": "0", "MIYAGI_EDITOR": "vscode", "MIYAGI_CURATED": "1",
        "MIYAGI_VSCODE_PORTS": str(companion_port),  # the fake companion only, never VS Code's real 8791+
        "DEMO": "0",
        "REHEARSAL_SIDE_EFFECTS": str(base / "side-effects.jsonl"),
        "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "https_proxy": BAD_PROXY, "http_proxy": BAD_PROXY, "all_proxy": BAD_PROXY,
        "HTTPS_PROXY": BAD_PROXY, "HTTP_PROXY": BAD_PROXY, "ALL_PROXY": BAD_PROXY,
        "NO_PROXY": "localhost,127.0.0.1,::1", "no_proxy": "localhost,127.0.0.1,::1",
    })
    for k in PAID_KEYS:
        env[k] = ""
    env.update(extra or {})
    return env


class PrivateEngine:
    def __init__(self, port: int, env: dict[str, str], log_path: Path, python: str | None = None):
        if port == LIVE_PORT:
            raise SystemExit("never :8787 (Michael's live engine)")
        self.port, self.env, self.log_path = port, env, log_path
        self.python = python or sys.executable
        self.proc: subprocess.Popen | None = None
        self._log = None

    async def start(self, timeout: float = 45.0) -> float:
        import httpx

        if not port_free(self.port):
            raise RuntimeError(f"port {self.port} is busy: pick another (--port), never {LIVE_PORT}")
        self._log = open(self.log_path, "w", encoding="utf-8")  # noqa: SIM115
        t0 = time.monotonic()
        self.proc = subprocess.Popen([self.python, "-m", "server.tests.rehearsal_engine", "--host", "127.0.0.1",
                                      "--port", str(self.port)], cwd=ROOT, env=self.env, stdout=self._log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
        async with httpx.AsyncClient(trust_env=False) as c:
            while time.monotonic() - t0 < timeout:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"engine exited ({self.proc.returncode}); see {self.log_path}")
                with contextlib.suppress(httpx.HTTPError):
                    if (await c.get(f"http://127.0.0.1:{self.port}/health", timeout=1)).status_code == 200:
                        return time.monotonic() - t0
                await asyncio.sleep(0.2)
        raise TimeoutError(f"engine not up after {timeout:.0f}s; see {self.log_path}")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                if hasattr(os, "killpg"):
                    os.killpg(self.proc.pid, signal.SIGTERM)
                else:  # Windows: no process groups, no SIGTERM; terminate() is TerminateProcess
                    self.proc.terminate()
            try:
                self.proc.wait(8)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    if hasattr(os, "killpg"):
                        os.killpg(self.proc.pid, signal.SIGKILL)
                    else:
                        self.proc.kill()
                self.proc.wait(4)
        if self._log:
            with contextlib.suppress(Exception):
                self._log.close()


# --------------------------------------------------------------------------------------------- the app

@dataclass
class Ev:
    t: float
    type: str
    p: dict
    i: int


def is_completion(p: dict) -> bool:
    """lesson_end.card: the lesson-complete card (its one button is End lesson)."""
    return "end_lesson" in (p.get("actions") or []) and p.get("kind") != "resume"


def _text(p: dict) -> str:
    return " ".join(str(p.get(k) or "") for k in ("title", "body", "guidingQuestion", "caption", "message"))


class App:
    """Plays Adrian's app over the WebSocket: config.keys on connect, every engine event recorded with its time,
    card.shown for each card it would show."""

    def __init__(self, port: int):
        self.url = f"ws://127.0.0.1:{port}/"
        self.events: list[Ev] = []
        self.ws = None
        self._reader: asyncio.Task | None = None
        self._cond = asyncio.Condition()
        self.sent: list[tuple[float, str, dict]] = []

    async def connect(self) -> int:
        import websockets

        self.ws = await websockets.connect(self.url, max_size=None, open_timeout=5, proxy=None)
        mark = len(self.events)
        self._reader = asyncio.create_task(self._read(self.ws))
        await self.send("config.keys", {k: "" for k in KEY_NAMES})
        return mark

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
        self.ws, self._reader = None, None

    async def _read(self, ws) -> None:
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                ev = Ev(time.monotonic(), str(msg.get("type")), msg.get("payload") or {}, len(self.events))
                self.events.append(ev)
                if ev.type in ("card", "offtrack"):  # the app reports what it put on screen (E14)
                    asyncio.create_task(self._shown(ev))
                async with self._cond:
                    self._cond.notify_all()
        except Exception:  # noqa: BLE001 - closed
            pass

    async def _shown(self, ev: Ev) -> None:
        p = {"title": str(ev.p.get("title") or ""), "kind": str(ev.p.get("kind") or ev.type)}
        if ev.p.get("stepId"):
            p["stepId"] = ev.p["stepId"]
        with contextlib.suppress(Exception):
            await self.send("card.shown", p)

    async def send(self, type_: str, payload: dict | None = None) -> float:
        t = time.monotonic()
        self.sent.append((t, type_, payload or {}))
        await self.ws.send(json.dumps({"type": type_, "payload": payload or {}}))
        return t

    def mark(self) -> int:
        return len(self.events)

    def since(self, mark: int, type_: str | None = None) -> list[Ev]:
        return [e for e in self.events[mark:] if type_ is None or e.type == type_]

    def find(self, mark: int, type_: str, pred=None) -> Ev | None:
        for e in self.events[mark:]:
            if e.type == type_ and (pred is None or pred(e.p)):
                return e
        return None

    async def wait(self, type_: str, pred=None, since: int = 0, timeout: float = 5.0, what: str = "") -> Ev:
        end = time.monotonic() + timeout
        while True:
            hit = self.find(since, type_, pred)
            if hit is not None:
                return hit
            left = end - time.monotonic()
            if left <= 0:
                raise Fail(f"no {what or type_} within {timeout:.1f}s")
            async with self._cond:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._cond.wait(), left)


# --------------------------------------------------------------------------------------------- nn.py edits

def starter() -> str:
    return STARTER.read_text(encoding="utf-8")


def paste_under(text: str, section: str, code: str) -> str:
    """Paste `code` on the line under the section comment (what Copy + paste under `# Backprop` gives)."""
    lines = text.split("\n")
    i = next((k for k, ln in enumerate(lines) if ln.strip() == section), None)
    if i is None:
        return text.rstrip("\n") + "\n\n" + code.rstrip("\n") + "\n"
    return "\n".join(lines[:i + 1] + code.rstrip("\n").split("\n") + lines[i + 1:])


def set_weights(text: str, how: dict[str, str]) -> str:
    return _W_LINE.sub(lambda m: f"{m['ind']}{m['name']} = {how[m['name']]}", text)


def _loss_lines(output: str) -> list[float]:
    return [float(m.group(1)) for m in re.finditer(r"loss\s+([0-9.eE+-]+)", output or "")]


# --------------------------------------------------------------------------------------------- the rehearsal

class Rehearsal:
    def __init__(self, port: int, base: Path, companion: FakeCompanion, verbose: bool = False, slack: float = 1.0):
        self.port, self.base, self.comp, self.verbose, self.slack = port, base, companion, verbose, slack
        self.http = f"http://127.0.0.1:{port}"
        self.app = App(port)
        self.rows: list[Row] = []
        self.take = ""
        self.workdir: Path | None = None
        self.step_t: dict[str, float] = {}  # when each step last started (stage's dwell counts from there)
        self._client = None
        self.effects_path = base / "side-effects.jsonl"

    # -- plumbing
    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"  [{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    async def get(self, path: str) -> dict:
        r = await self._client.get(self.http + path, timeout=5)
        return r.json()

    async def post(self, path: str, body: dict | None = None) -> dict:
        r = await self._client.post(self.http + path, json=body if body is not None else {}, timeout=10)
        try:
            return r.json()
        except ValueError:
            return {"status": r.status_code}

    def effects(self, since_wall: float = 0.0) -> list[dict]:
        try:
            lines = self.effects_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for ln in lines:
            with contextlib.suppress(ValueError):
                e = json.loads(ln)
                if e.get("t", 0) >= since_wall:
                    out.append(e)
        return out

    @contextlib.asynccontextmanager
    async def row(self, id_: str, ref: str, what: str, tier: str = "demo"):
        r = Row(id_, self.take, ref, what, tier, slack=self.slack)
        self.rows.append(r)
        t0 = time.monotonic()
        self.log(f"{id_} {what}")
        try:
            yield r
        except Fail as e:
            r.fails.append(str(e))
        except Exception as e:  # noqa: BLE001 - one broken row must not stop the rehearsal
            r.fails.append(f"{type(e).__name__}: {e}")
        finally:
            r.secs = round(time.monotonic() - t0, 2)
            r.ok = not r.fails
            self.log(f"   -> {'PASS' if r.ok else 'FAIL'} {r.timings} {r.fails}")

    def nn(self) -> Path:
        if self.workdir is None:
            raise Fail("no lesson folder known yet")
        return self.workdir / "nn.py"

    def read_nn(self) -> str:
        try:
            return self.nn().read_text(encoding="utf-8")
        except OSError:
            return ""

    async def save(self, text: str) -> float:
        """Paste + ⌘S: the file on disk (the engine's watcher) and the companion's save event (POST /vscode/event)."""
        p = self.nn()
        await self.post("/vscode/event", {"type": "dirty", "ts": int(time.time() * 1000), "port": self.comp.port,
                                          "pid": os.getpid(), "folders": [str(self.workdir)], "file": str(p),
                                          "dirty": True, "languageId": "python"})
        p.write_text(text, encoding="utf-8")
        t = time.monotonic()
        await self.post("/vscode/event", {"type": "save", "ts": int(time.time() * 1000), "port": self.comp.port,
                                          "pid": os.getpid(), "folders": [str(self.workdir)], "file": str(p),
                                          "windowFocused": True, "languageId": "python"})
        return t

    async def dwell(self, sid: str) -> None:
        """A presenter takes a few seconds to paste: never inside the step's first DWELL_S seconds."""
        t0 = self.step_t.get(sid)
        if t0 is not None:
            left = (t0 + DWELL_S + 0.4) - time.monotonic()
            if left > 0:
                await asyncio.sleep(left)

    def _track_steps(self, mark: int) -> None:
        for e in self.app.since(mark, "step.started"):
            self.step_t[e.p.get("stepId")] = e.t

    def step_code(self, sid: str) -> str:
        ev = next((e for e in reversed(self.app.events) if e.type == "step.started" and e.p.get("stepId") == sid),
                  None)
        if ev is None or not (ev.p.get("code") or "").strip():
            raise Fail(f"step.started {sid} carried no code to copy")
        return ev.p["code"]

    # -- shared expectations
    async def learn(self, r: Row, mode: str, fresh_expected: bool = True) -> tuple[int, Ev]:
        """learn -> lesson.ready -> step.started nn1, and the take is fresh: step 1, clean nn.py, nothing resumed."""
        m = self.app.mark()
        t = await self.app.send("learn", {"query": GOAL, "mode": mode})
        ready = await self.app.wait("lesson.ready", since=m, timeout=6, what="lesson.ready")
        r.time("learn -> lesson.ready", ready.t - t, 3.0)
        lesson = ready.p.get("lesson") or {}
        r.check(lesson.get("id") == LESSON_ID, f"lesson id {lesson.get('id')!r}")
        r.check(len(ready.p.get("steps") or []) == 6, f"{len(ready.p.get('steps') or [])} steps (want 6)")
        first = await self.app.wait("step.started", since=ready.i, timeout=3, what="step.started")
        r.check(first.p.get("stepId") == "nn1", f"first step.started is {first.p.get('stepId')}, want nn1")
        st = await self.get("/state")
        self.workdir = Path(st.get("workdir") or "")
        self.comp.folder = str(self.workdir)
        self._track_steps(m)
        await asyncio.sleep(0.8)  # anything a resume / skip-ahead would send comes right after
        if fresh_expected:
            self.expect_fresh(r, m)
        return m, ready

    def expect_fresh(self, r: Row, mark: int) -> None:
        ev = self.app.since(mark)
        r.check(self.read_nn() == starter(), "nn.py isn't the clean starter (just the four section comments)")
        resume = [e for e in ev if e.type == "card" and (e.p.get("kind") == "resume" or
                                                         "continue where" in _text(e.p).lower())]
        r.check(not resume, f"a resume card: {[_text(e.p) for e in resume]}")
        already = [e for e in ev if (e.type == "step.passed" and e.p.get("already")) or
                   (e.type == "card" and "already did" in _text(e.p).lower())]
        r.check(not already, f"'You already did…': {[e.p for e in already]}")
        passed = [e.p.get("stepId") for e in ev if e.type == "step.passed"]
        r.check(not passed, f"steps passed on their own at the start: {passed}")
        later = [e.p.get("stepId") for e in ev if e.type == "step.started" and e.p.get("stepId") != "nn1"]
        r.check(not later, f"a later step started: {later}")
        r.check(not [e for e in ev if e.type == "error"], "an error event")

    async def start_lesson(self, r: Row) -> float:
        wall, m = time.time(), self.app.mark()
        t = await self.app.send("action", {"kind": "start"})
        await asyncio.sleep(0.6)
        st = await self.get("/state")
        r.check(st.get("phase") == "active", f"phase {st.get('phase')!r} after Start (want active)")
        self.step_t["nn1"] = t  # the held step really starts now (session._begin)
        opens = [e for e in self.effects(wall) if e["what"] == "workspace.open" and e.get("would_open")]
        r.check(opens, "Start didn't open the lesson's VS Code window")
        if opens:
            r.check(str(opens[-1].get("file") or "").endswith("nn.py"), f"VS Code opened on {opens[-1].get('file')}")
        r.check(not [e for e in self.app.since(m) if e.type == "error"], "an error event")
        return t

    def rows_of(self, sid: str) -> set[str]:
        """The drawer's rows for the step's latest start (every checkId sent for it since its step.started)."""
        start = next((e.i for e in reversed(self.app.events) if e.type == "step.started" and e.p.get("stepId") == sid),
                     0)
        return {e.p.get("checkId") for e in self.app.since(start, "check.updated") if e.p.get("stepId") == sid}

    def greens(self, r: Row, sid: str, mark: int, before: int, one_by_one: bool = True) -> list[Ev]:
        """Every row of the step went green (pass) before `before`; one by one for a Demo (DEMO §2 row 3)."""
        events = [e for e in self.app.since(mark, "check.updated") if e.p.get("stepId") == sid and e.i < before]
        greens = [e for e in events if e.p.get("status") == "pass"]
        want = self.rows_of(sid)
        got = {e.p.get("checkId") for e in greens}
        r.check(want and want <= got, f"{sid} rows not all green: {sorted(want - got)} "
                f"({[(e.p.get('checkId'), e.p.get('status')) for e in events]})")
        r.check(not [e for e in events if e.p.get("status") == "fail"], f"{sid}: a red row on the way")
        if one_by_one:
            gaps = [b.t - a.t for a, b in zip(greens, greens[1:])]
            r.check(all(g >= 0.08 for g in gaps), f"{sid} rows not one by one (gaps {[round(g, 2) for g in gaps]})")
        return greens

    async def save_pass(self, r: Row, sid: str, nxt: str | None, text: str, one_by_one: bool = True,
                        limits=(2.0, 3.5, 4.5)) -> None:
        """⌘S on a typing step: every row goes green one by one, the step passes, the next one starts."""
        await self.dwell(sid)
        m = self.app.mark()
        t = await self.save(text)
        passed = await self.app.wait("step.passed", lambda p: p.get("stepId") == sid, since=m, timeout=8,
                                     what=f"step.passed {sid}")
        greens = self.greens(r, sid, m, passed.i, one_by_one)
        if greens:
            r.time("save -> first green", greens[0].t - t, limits[0])
        r.time("save -> step.passed", passed.t - t, limits[1])
        r.check(passed.p.get("nextStepId") == nxt, f"nextStepId {passed.p.get('nextStepId')!r} (want {nxt!r})")
        r.check(not passed.p.get("already") and not passed.p.get("skipped"), f"step.passed {passed.p}")
        if nxt:
            started = await self.app.wait("step.started", lambda p: p.get("stepId") == nxt, since=passed.i,
                                          timeout=4, what=f"step.started {nxt}")
            r.time(f"save -> {nxt} started", started.t - t, limits[2])
            self._track_steps(m)

    def run_metrics(self, mark: int) -> list[tuple[Any, float]]:
        """The live curve of the learner's own runs: (epoch, loss), not the lesson's reference curve (runId tutorial)."""
        return [(e.p.get("step"), e.p.get("value")) for e in self.app.since(mark, "metric")
                if e.p.get("runId") != "tutorial"]

    @staticmethod
    def previews(r: Row, diagrams: list[Ev]) -> None:
        """DEMO §2 rows 2-5: before the learner's first run the panel shows previews (data.preview, no epoch / loss)."""
        r.check(diagrams, "no panel pictures before the first run")
        for e in diagrams:
            d = e.p.get("data") or {}
            stats = [f for f in d.get("frames") or [] if f.get("loss") is not None or f.get("epoch") is not None]
            r.check(bool(e.p.get("preview") or d.get("preview")), f"{e.p.get('stepId')} {d.get('mode')}: not a preview")
            r.check(not stats, f"{e.p.get('stepId')} {d.get('mode')}: {len(stats)} frames carry epoch/loss (e.g. epoch "
                    f"{stats[-1].get('epoch') if stats else ''} loss {stats[-1].get('loss') if stats else ''})")

    def diagram_for(self, sid: str, mark: int) -> list[Ev]:
        return [e for e in self.app.since(mark, "diagram") if e.p.get("stepId") == sid]

    async def panel(self, r: Row, sid: str, what: str) -> None:
        """The drawer's right-hand panel got the step's network picture when the step started."""
        start = next((e.i for e in reversed(self.app.events) if e.type == "step.started" and e.p.get("stepId") == sid),
                     None)
        if not r.check(start is not None, f"{sid} never started"):
            return
        try:
            d = await self.app.wait("diagram", lambda p: p.get("stepId") == sid, since=start, timeout=2.0)
            r.check(d.p.get("kind") == "network", f"{sid} panel kind {d.p.get('kind')!r}")
        except Fail:
            r.check(False, f"no network diagram for {sid} ({what})")

    # ----------------------------------------------------------------------------------------- take 1
    async def take1(self) -> None:
        self.take = "1"
        app, start = self.app, self.app.mark()
        async with self.row("T1.1", "DEMO §2 row 1", "Demo chip: learn -> Before you start sheet") as r:
            m, ready = await self.learn(r, "demo")
            lesson = ready.p.get("lesson") or {}
            flow = " ".join(f"{b.get('label', '')} {b.get('detail', '')}" for b in lesson.get("flow") or []).lower()
            for word in ("input", "hidden", "output", "backprop", "gradient"):
                r.check(word in flow, f"'How it works' has no {word!r} box: {flow!r}")
            pre = " ".join(p.get("title", "") for p in lesson.get("prerequisites") or []).lower()
            for word in ("numpy", "matri", "derivative"):
                r.check(word in pre, f"'What to know first' has no {word!r}: {pre!r}")
            st = await self.get("/state")
            r.check(st.get("phase") == "ready", f"phase {st.get('phase')!r} (want ready: held under the sheet)")
            sg = await self.get("/stage")
            r.check(sg.get("on") and sg.get("step") == "nn1", f"/stage {sg}")
        async with self.row("T1.2", "DEMO §2 row 2", "Start the lesson -> VS Code on nn.py, step 1 of 6 + code + network") as r:
            m = app.mark()
            await self.start_lesson(r)
            code = self.step_code("nn1")
            r.check("W1 = np.random.randn(1, 4)" in code, "nn1's code has no W1 = np.random.randn(1, 4)")
            dia = self.diagram_for("nn1", 0)
            r.check(dia and dia[-1].p.get("kind") == "network", "no network diagram for nn1 in the panel")
            # a save in the step's first seconds never counts (DEMO §4: "ignored in the step's first 2.5 s")
            t = await self.save(self.read_nn().replace("# The network", "# The network\n", 1))
            await asyncio.sleep(1.4)
            early = [e for e in app.since(m) if e.type in ("check.updated", "step.passed") and e.t >= t]
            r.check(not early, f"a save {DWELL_S}s into the step counted: {[(e.type, e.p) for e in early]}")
            r.check(self.read_nn().startswith(starter().split("\n")[0]), "nn.py lost its header")
        async with self.row("T1.3", "DEMO §2 row 3", "nn1: paste, zero weights, ⌘S -> rows green one by one -> step 2") as r:
            text = set_weights(paste_under(starter(), SECTIONS[0], self.step_code("nn1")), _W_ZEROS)
            r.check("np.zeros((4, 1))" in text and "randn" not in text, "zeros didn't go in")
            await self.save_pass(r, "nn1", "nn2", text)
        async with self.row("T1.3b", "DEMO §3 row 1", "a second ⌘S right after a pass never skips a step") as r:
            m = app.mark()
            t = await self.save(self.read_nn())  # the presenter's reflex ⌘S, nn2 just started
            await asyncio.sleep(1.5)
            moved = [(e.type, e.p.get("stepId")) for e in app.since(m) if e.type in ("step.passed", "step.started")]
            r.check(not moved, f"the second ⌘S moved the lesson: {moved}")
            r.time("watched", time.monotonic() - t)
        async with self.row("T1.4", "DEMO §2 row 4", "nn2 Backprop: paste, ⌘S -> green, next step (error flows back)") as r:
            await self.panel(r, "nn2", "the error flowing back")
            await self.save_pass(r, "nn2", "nn3", paste_under(self.read_nn(), SECTIONS[1], self.step_code("nn2")))
        async with self.row("T1.5", "DEMO §2 row 5", "nn3 training loop: paste, ⌘S -> green, Train it starts") as r:
            m = app.mark()
            await self.panel(r, "nn3", "the training to come")
            await self.save_pass(r, "nn3", "nn4", paste_under(self.read_nn(), SECTIONS[2], self.step_code("nn3")))
            await asyncio.sleep(0.8)
            st4 = app.find(m, "step.started", lambda p: p.get("stepId") == "nn4")
            r.check(st4 is not None and st4.p.get("kind") == "run", f"nn4 kind {st4 and st4.p.get('kind')!r}")
            runbtn = [e for e in app.since(m, "card") if "run_command" in (e.p.get("actions") or [])]
            r.check(runbtn, "nothing offers Run it for me (action run_command) on nn4")
            r.note("headless: no screen, so the Run ▷ / terminal box never goes up and the Run it card always does "
                   "(brief item 2 needs a desktop run)")
        first_run: int | None = None
        async with self.row("T1.6", "DEMO §2 row 6", "nn4 Run it for me -> stuck run (0.4900 every line) -> Not yet · Loss is stuck at 0.49") as r:
            m = app.mark()
            t = await app.send("action", {"kind": "run_command"})
            ran = await app.wait("card", lambda p: str(p.get("title", "")).startswith("Ran "), since=m, timeout=5,
                                 what="the run card")
            r.time("press -> run card", ran.t - t, 2.5)
            first_run = ran.i
            out = str(ran.p.get("output") or "")
            losses = _loss_lines(out)
            r.check(losses and all(abs(v - 0.49) < 1e-9 for v in losses), f"run card losses {losses}")
            r.check(ran.p.get("title") == "Ran nn.py", f"run card title {ran.p.get('title')!r} (DEMO: Ran nn.py)")
            off = await app.wait("offtrack", since=m, timeout=6, what="the Not yet card")
            r.time("run card -> Not yet", off.t - ran.t, 3.0)
            r.check(off.p.get("title") == "Loss is stuck at 0.49", f"Not yet title {off.p.get('title')!r}")
            r.check(off.p.get("stepId") == "nn4", f"Not yet stepId {off.p.get('stepId')}")
            r.check("hint" in (off.p.get("actions") or []), f"no Hint on the Not yet card: {off.p.get('actions')}")
            metr = [v for _, v in self.run_metrics(m)]
            r.check(metr and all(abs(v - 0.49) < 1e-9 for v in metr), f"live curve {metr}")
            stuck = [e for e in app.since(m, "diagram") if (e.p.get("data") or {}).get("mode") == "stuck"
                     or "same" in str(e.p.get("caption", "")).lower()]
            r.check(stuck, "the panel never showed the identical hidden neurons (loss stuck)")
            if stuck:
                d = stuck[-1].p.get("data") or {}
                r.check(not d.get("preview"), "the stuck panel is marked preview (it is their run)")
                last = [f.get("loss") for f in d.get("frames") or [] if f.get("loss") is not None][-1:]
                r.check(last and abs(last[0] - 0.49) < 1e-6, f"the stuck panel's loss {last} (want 0.4900)")
            fail = [e for e in app.since(m, "check.updated") if e.p.get("status") == "fail"]
            r.check(fail and "0.4900" in str(fail[-1].p.get("detail")), f"loss row: {[e.p for e in fail]}")
            r.check(len([e for e in app.since(m, "card") if str(e.p.get("title", "")).startswith("Ran ")]) == 1,
                    "one press, more than one run card")
            r.check(not app.find(m, "step.passed"), "the stuck run passed the step")
            self.stuck_card, self.stuck_mark, self.stuck_row = off.p, m, (fail[-1].p if fail else {})
        async with self.row("T1.6a", "DEMO §2 rows 2-5", "panel pictures before the first run: previews, no epoch / loss") as r:
            cut = first_run if first_run is not None else len(app.events)
            self.previews(r, [e for e in app.since(start, "diagram") if e.i < cut])
        async with self.row("T1.6b", "brief 5", "Not yet: the loss row and curve show yours vs expected, citation fits",
                            tier="brief") as r:
            p = getattr(self, "stuck_card", None) or {}
            detail = str((getattr(self, "stuck_row", None) or {}).get("detail") or "")
            r.check("0.01" in detail, f"loss row detail {detail!r} (want the target, loss below 0.01)")
            ref = [e for e in app.since(getattr(self, "stuck_mark", 0), "metric") if e.p.get("runId") == "tutorial"]
            r.check(ref, "no expected curve (metric runId tutorial) for the Not yet's loss chart")
            label = str((p.get("citation") or {}).get("label") or "")
            r.check(len(label) <= 40, f"citation label is {len(label)} chars: {label!r}")
        async with self.row("T1.7", "DEMO §2 row 7", "Hint -> Hint 1 of 2 'Look at how W1, W2 and W3 start…'") as r:
            m, tc = app.mark(), time.monotonic()
            t = await app.send("action", {"kind": "hint"})
            hint = await app.wait("card", lambda p: p.get("kind") == "hint", since=m, timeout=4, what="the hint card")
            r.time("press -> hint", hint.t - t, 1.0)
            r.check(hint.p.get("title") == "Hint 1 of 2", f"hint title {hint.p.get('title')!r}")
            r.check(str(hint.p.get("body", "")).startswith("Look at how W1, W2 and W3 start"),
                    f"hint body {hint.p.get('body')!r}")
            await asyncio.sleep(1.0)
            calls = [f"{c['route']} {json.dumps(c['body'])[:120]}" for c in self.comp.since(tc)]
            spots = [e.p for e in app.since(m, "spotlight")]
            r.note(f"after Hint: companion {calls or 'none'}; spotlight {spots or 'none'} (brief 4: a desktop run "
                   f"must show the box on the W1/W2/W3 lines)")
        async with self.row("T1.8", "DEMO §2 row 8", "random weights + ⌘S + Check my work -> 0.8187 -> 0.0009, green") as r:
            text = set_weights(self.read_nn(), _W_RANDOM)
            r.check(all(v in text for v in _W_RANDOM.values()), "random weights didn't go in")
            m = app.mark()
            await self.save(text)
            await asyncio.sleep(1.2)
            r.check(not app.find(m, "step.passed"), "a save passed the run step")
            t = await app.send("action", {"kind": "check_step"})
            ran = await app.wait("card", lambda p: str(p.get("title", "")).startswith("Ran "), since=m, timeout=5,
                                 what="the run card")
            r.time("Check -> run card", ran.t - t, 2.5)
            passed = await app.wait("step.passed", lambda p: p.get("stepId") == "nn4", since=m, timeout=6,
                                    what="step.passed nn4")
            r.time("Check -> step.passed", passed.t - t, 4.5)
            metr = self.run_metrics(m)
            r.check(metr and abs(metr[0][1] - 0.8187) < 1e-4, f"first loss {metr[:1]} (want 0.8187)")
            r.check(metr and abs(metr[-1][1] - 0.0009) < 1e-4 and metr[-1][0] == 18000,
                    f"last loss {metr[-1:]} (want 0.0009 at epoch 18000)")
            row = [e for e in app.since(m, "check.updated") if e.p.get("stepId") == "nn4"]
            r.check(row and row[-1].p.get("status") == "pass" and "0.0009" in str(row[-1].p.get("detail")),
                    f"loss row {[e.p for e in row]}")
            r.check(not app.find(m, "offtrack"), "a second Not yet")
            r.check(passed.p.get("nextStepId") == "nn5", f"nextStepId {passed.p.get('nextStepId')}")
            await app.wait("step.started", lambda p: p.get("stepId") == "nn5", since=passed.i, timeout=3,
                           what="step.started nn5")
            self._track_steps(m)
            trained = [e for e in app.since(m, "diagram") if e.p.get("stepId") == "nn4"]
            r.check(trained, "the panel didn't show the network training")
            if trained:
                d = trained[-1].p.get("data") or {}
                r.check(not d.get("preview") and d.get("mode") == "train",
                        f"the panel after the run: mode {d.get('mode')!r} preview {d.get('preview')!r} (want their run)")
        async with self.row("T1.9", "DEMO §2 row 9", "nn5 Test it: paste, ⌘S -> green, step 6") as r:
            m = app.mark()
            await self.save_pass(r, "nn5", "nn6", paste_under(self.read_nn(), SECTIONS[3], self.step_code("nn5")))
            await asyncio.sleep(0.6)
            r.check([e for e in app.since(m, "card") if "run_command" in (e.p.get("actions") or [])],
                    "nothing offers Run it for me on nn6")
        async with self.row("T1.10", "DEMO §2 row 10", "nn6 Run it for me -> [-1.0, 0.0, 1.0] + W1..b3 -> completion card") as r:
            m = app.mark()
            t = await app.send("action", {"kind": "run_command"})
            await asyncio.sleep(0.3)  # DEMO §4: a second press while the run is going is ignored (one press, one run)
            await app.send("action", {"kind": "run_command"})
            ran = await app.wait("card", lambda p: str(p.get("title", "")).startswith("Ran "), since=m, timeout=5,
                                 what="the run card")
            r.time("press -> run card", ran.t - t, 2.5)
            out = str(ran.p.get("output") or "")
            r.check(ran.p.get("title") == "Ran nn.py", f"run card title {ran.p.get('title')!r} (DEMO: Ran nn.py)")
            r.check("ran without errors" in str(ran.p.get("body", "")).lower(), f"run card body {ran.p.get('body')!r}")
            r.check("[-1.0, 0.0, 1.0]" in out, f"no [-1.0, 0.0, 1.0] in {out!r}")
            r.check(all(re.search(rf"^{w}\b", out, re.M) for w in ("W1", "b1", "W2", "b2", "W3", "b3")),
                    f"not every weight W1..b3 in the output: {out!r}")
            passed = await app.wait("step.passed", lambda p: p.get("stepId") == "nn6", since=m, timeout=6,
                                    what="step.passed nn6")
            r.time("press -> step.passed", passed.t - t, 4.5)
            r.check(not passed.p.get("nextStepId"), f"nn6 has a next step {passed.p.get('nextStepId')}")
            answering = [e for e in app.since(m, "diagram") if e.p.get("stepId") == "nn6"]
            r.check(answering, "the panel didn't show the network answering")
            end = await app.wait("card", is_completion, since=passed.i, timeout=6, what="the completion card")
            r.time("last pass -> completion card", end.t - passed.t, 4.0)
            title = str(end.p.get("title") or "")
            r.check(not re.match(r"you built a neural net", title, re.I), f"completion title {title!r} (brief 6)")
            r.check("lesson complete" not in _text(end.p).lower(), f"completion card says Lesson complete: {title!r}")
            r.note(f"completion card: {title!r} / {str(end.p.get('body') or '')[:100]!r}")
            st = await self.get("/state")
            r.check(st.get("phase") == "done", f"phase {st.get('phase')!r} (want done)")
            runs = [e for e in app.since(m, "card") if str(e.p.get("title", "")).startswith("Ran ")]
            r.check(len(runs) == 1, f"a double press ran {len(runs)} times")
            extra = [e.p.get("title") for e in app.since(m, "card") if e.p.get("kind") == "answer"
                     and not str(e.p.get("title", "")).startswith("Ran ")]
            r.check(not extra, f"the second press got a card of its own: {extra}")
            sg = await self.get("/stage")
            r.check(sg.get("runs") == {"nn4": 2, "nn6": 1}, f"/stage runs {sg.get('runs')} (want nn4 2, nn6 1)")
        await self.global_copy_rows("T1", start)

    async def global_copy_rows(self, prefix: str, mark: int) -> None:
        app = self.app
        async with self.row(f"{prefix}.copy", "brief 6 + UX rules", "no 'Lesson complete', no 'You built…', no Cursor, no error") as r:
            texts = [(e.type, _text(e.p)) for e in app.since(mark) if e.type in ("card", "offtrack", "error",
                                                                                     "spotlight", "diagram")]
            r.check(not [t for t in texts if "lesson complete" in t[1].lower()], "something says 'Lesson complete'")
            r.check(not [t for t in texts if re.search(r"\byou built a neural net", t[1], re.I)],
                    "something says 'You built a neural net…'")
            r.check(not [t for t in texts if re.search(r"\bcursor\b", t[1], re.I)], "a card mentions Cursor")
            errs = [e.p for e in app.since(mark, "error")]
            r.check(not errs, f"error events: {errs}")
        async with self.row(f"{prefix}.dash", "brief UX rules", "no em dash in any card / Not yet copy", tier="brief") as r:
            dashes = sorted({_text(e.p)[:80] for e in app.since(mark) if e.type in ("card", "offtrack")
                             and "—" in _text(e.p)})
            r.check(not dashes, f"em dashes in: {dashes}")

    # ----------------------------------------------------------------------------------------- take 2
    async def take2(self) -> None:
        self.take = "2"
        app, start = self.app, self.app.mark()
        async with self.row("T2.1", "brief: repeatable takes", "take 2 right after take 1 (no End): fresh at step 1, clean nn.py") as r:
            await self.learn(r, "demo")
            sg = await self.get("/stage")
            r.check(sg.get("on") and sg.get("step") == "nn1" and not sg.get("runs"), f"/stage {sg}")
            kept = list((self.base / "lessons" / ".miyagi-state" / "attempts").rglob("nn-*.py"))
            r.check(kept, "take 1's nn.py wasn't kept in .miyagi-state/attempts")
            first = [e for e in app.since(start, "diagram") if e.p.get("stepId") == "nn1"]
            self.previews(r, first[:1])  # a second take previews again, never take 1's trained run
        async with self.row("T2.2", "DEMO §2 rows 2-3", "Start, nn1 pasted + ⌘S -> step 2") as r:
            await self.start_lesson(r)
            await self.save_pass(r, "nn1", "nn2", set_weights(paste_under(starter(), SECTIONS[0],
                                                                          self.step_code("nn1")), _W_ZEROS))
        async with self.row("T2.3", "DEMO §1 ⌃⌥⌘→", "POST /stage/next passes the step") as r:
            m = app.mark()
            t = time.monotonic()
            res = await self.post("/stage/next")
            r.check(res.get("ok") is True, f"/stage/next -> {res}")
            passed = await app.wait("step.passed", lambda p: p.get("stepId") == "nn2", since=m, timeout=4,
                                    what="step.passed nn2")
            r.time("next -> step.passed", passed.t - t, 1.5)
            self.greens(r, "nn2", m, passed.i)
            await app.wait("step.started", lambda p: p.get("stepId") == "nn3", since=passed.i, timeout=3,
                           what="step.started nn3")
            self._track_steps(m)
        async with self.row("T2.4", "DEMO §1 ⌃⌥⌘←", "POST /stage/back goes back one step") as r:
            m = app.mark()
            t = time.monotonic()
            res = await self.post("/stage/back")
            r.check(res.get("ok") is True, f"/stage/back -> {res}")
            back = await app.wait("step.started", since=m, timeout=3, what="step.started")
            r.time("back -> step.started", back.t - t, 1.0)
            r.check(back.p.get("stepId") == "nn2", f"back went to {back.p.get('stepId')} (want nn2)")
            sg = await self.get("/stage")
            r.check(sg.get("step") == "nn2", f"/stage {sg}")
            self._track_steps(m)
        async with self.row("T2.5", "DEMO §1 ⌃⌥⌘R", "POST /stage/restart: step 1, nn.py back to the four section comments") as r:
            r.check(self.read_nn() != starter(), "nn.py was already clean before restart (nothing to test)")
            m = app.mark()
            t = time.monotonic()
            res = await self.post("/stage/restart")
            r.check(res.get("ok") is True, f"/stage/restart -> {res}")
            first = await app.wait("step.started", since=m, timeout=5, what="step.started")
            r.time("restart -> step 1", first.t - t, 3.0)
            r.check(first.p.get("stepId") == "nn1", f"restart started {first.p.get('stepId')}")
            await asyncio.sleep(0.8)
            self.expect_fresh(r, m)
            body = [ln for ln in self.read_nn().splitlines() if ln.strip() and not ln.startswith("import")]
            r.check(all(ln.startswith("#") for ln in body), f"nn.py has more than comments: {body}")
            sg = await self.get("/stage")
            r.check(sg.get("on") and sg.get("step") == "nn1" and not sg.get("runs"), f"/stage {sg}")
            self._track_steps(m)
        async with self.row("T2.6", "DEMO §3 short on time", "⌃⌥⌘→ through all six steps: Train it on the run that learns, no Not yet") as r:
            m = app.mark()
            st = await self.get("/state")
            if st.get("phase") == "ready":  # "Click Start the lesson if the sheet comes back"
                await app.send("action", {"kind": "start"})
                await asyncio.sleep(0.3)
            for sid in ("nn1", "nn2", "nn3", "nn4", "nn5", "nn6"):
                mm = app.mark()
                if sid == "nn4":  # zero weights in nn.py, Run it for me, then ⌃⌥⌘→ while it runs: that run learns
                    await self.save(set_weights(paste_under(self.read_nn(), SECTIONS[0], self.step_code("nn1")),
                                                _W_ZEROS))
                    await asyncio.sleep(0.6)
                    await app.send("action", {"kind": "run_command"})
                    await asyncio.sleep(0.3)
                res = await self.post("/stage/next")
                r.check(res.get("ok") is True, f"/stage/next on {sid} -> {res}")
                await app.wait("step.passed", lambda p, s=sid: p.get("stepId") == s, since=mm, timeout=5,
                               what=f"step.passed {sid}")
                if sid != "nn6":
                    nxt = f"nn{int(sid[2:]) + 1}"
                    await app.wait("step.started", lambda p, s=nxt: p.get("stepId") == s, since=mm,
                                   timeout=3, what=f"step.started {nxt}")
            r.check(not app.find(m, "offtrack"), "a Not yet on the presenter's next")
            good = [v for _, v in self.run_metrics(m)]
            r.check(good and abs(good[-1] - 0.0009) < 1e-4, f"Train it's run {good[-1:]} (want 0.0009)")
            r.check(not [v for v in good if abs(v - 0.49) < 1e-9], "the run under ⌃⌥⌘→ was the stuck one (0.4900)")
            runs = [e for e in app.since(m, "card") if str(e.p.get("title", "")).startswith("Ran ")]
            r.check(len(runs) <= 1, f"Run it for me + ⌃⌥⌘→ ran {len(runs)} times")
            end = await app.wait("card", is_completion, since=m, timeout=6, what="the completion card")
            r.check("lesson complete" not in _text(end.p).lower(), f"completion: {end.p.get('title')!r}")
        async with self.row("T2.7", "DEMO §1 reset", "End -> lesson ended, /stage off (presenter keys released)") as r:
            m = app.mark()
            await app.send("end_lesson", {})
            ended = await app.wait("lesson.ended", since=m, timeout=4, what="lesson.ended")
            r.check(ended.p.get("reason") in ("completed", "stopped"), f"reason {ended.p.get('reason')!r}")
            await asyncio.sleep(0.4)
            sg = await self.get("/stage")
            r.check(not sg.get("on"), f"/stage still on after End: {sg}")
        await self.global_copy_rows("T2", start)

    # ----------------------------------------------------------------------------------------- takes 3, 4
    async def take3(self) -> None:
        self.take = "3"
        app, start = self.app, self.app.mark()
        async with self.row("T3.1", "brief: repeatable takes", "a Demo after End: fresh at step 1, clean nn.py") as r:
            await self.learn(r, "demo")
            await self.start_lesson(r)
            await self.save_pass(r, "nn1", "nn2", paste_under(starter(), SECTIONS[0], self.step_code("nn1")))
        async with self.row("T3.2", "stable-nosave + a2ff530", "a deploy's POST /end + reconnect never brings a Demo back") as r:
            res = await self.post("/end")
            r.check(res.get("ok") and res.get("kept") is False, f"POST /end -> {res} (a Demo is never kept)")
            await app.close()
            await asyncio.sleep(0.5)
            m = await app.connect()
            await asyncio.sleep(1.5)
            ev = app.since(m)
            r.check(not [e for e in ev if e.type == "lesson.ready"], "the Demo came back on reconnect")
            r.check(not [e for e in ev if e.type == "card" and e.p.get("kind") == "resume"],
                    "a resume card for a Demo")
            st = await self.get("/state")
            r.check(st.get("phase") == "idle" and not st.get("lesson"), f"after reconnect: phase {st.get('phase')}")
        self.take = "4"
        async with self.row("T4.1", "brief: repeatable takes", "a Demo after the deploy: fresh at step 1; nn1 -> step 2") as r:
            await self.learn(r, "demo")
            await self.start_lesson(r)
            await self.save_pass(r, "nn1", "nn2", paste_under(starter(), SECTIONS[0], self.step_code("nn1")))
        await self.global_copy_rows("T3", start)

    # ----------------------------------------------------------------------------------------- takes 5, 6
    async def take5(self) -> None:
        self.take = "5"
        app, start = self.app, self.app.mark()
        async with self.row("T5.1", "DEMO §3 another topic", "Just teach me, same goal, from the running Demo: the real lesson, fresh") as r:
            m, ready = await self.learn(r, "lesson")
            r.check(not (ready.p.get("lesson") or {}).get("stage"), "lesson.ready is still a Demo lesson")
            sg = await self.get("/stage")
            r.check(not sg.get("on"), f"/stage on for Just teach me: {sg}")
            ended = app.find(m, "lesson.ended")
            r.check(ended is not None and ended.i < ready.i, "the Demo wasn't ended first")
        async with self.row("T5.2", "Just teach me", "Start, nn1's code + ⌘S -> really graded and passed") as r:
            await self.start_lesson(r)
            await self.save_pass(r, "nn1", "nn2", paste_under(starter(), SECTIONS[0], self.step_code("nn1")),
                                 one_by_one=False, limits=(2.0, 3.0, 4.0))  # really graded: all rows at once
        async with self.row("T5.3", "stable-nosave", "a deploy's POST /end + reconnect: Just teach me continues at step 2") as r:
            before = self.read_nn()
            res = await self.post("/end")
            r.check(res.get("ok") and res.get("kept") is True, f"POST /end -> {res} (a real lesson is kept)")
            await app.close()
            await asyncio.sleep(0.5)
            m = await app.connect()
            back = await app.wait("step.started", since=m, timeout=5, what="the lesson back")
            r.check(back.p.get("stepId") == "nn2", f"resumed at {back.p.get('stepId')} (want nn2)")
            ready = app.find(m, "lesson.ready")
            r.check(ready is not None and not (ready.p.get("lesson") or {}).get("stage"), "it came back as a Demo")
            r.check(self.read_nn() == before, "nn.py changed across the deploy")
            sg = await self.get("/stage")
            r.check(not sg.get("on"), f"/stage on: {sg}")
        async with self.row("T5.4", "DEMO §1 reset", "End mid-lesson -> lesson ended (stopped)") as r:
            m = app.mark()
            await app.send("end_lesson", {})
            ended = await app.wait("lesson.ended", since=m, timeout=4, what="lesson.ended")
            r.check(ended.p.get("reason") == "stopped", f"reason {ended.p.get('reason')!r}")
        self.take = "6"
        async with self.row("T6.1", "stable-nosave", "Just teach me again after End: step 1, clean nn.py, no resume card") as r:
            m, ready = await self.learn(r, "lesson")
            r.check(not (ready.p.get("lesson") or {}).get("stage"), "a Demo lesson")
            await app.send("end_lesson", {})
            await app.wait("lesson.ended", since=m, timeout=4, what="lesson.ended")
        await self.global_copy_rows("T5", start)

    # ----------------------------------------------------------------------------------------- run
    async def run(self) -> None:
        import httpx

        async with httpx.AsyncClient(trust_env=False) as c:
            self._client = c
            m = await self.app.connect()
            async with self.row("T0", "DEMO §1", "app connects: no lesson, no resume card", tier="demo") as r:
                await asyncio.sleep(0.6)
                ev = self.app.since(m)
                r.check(not [e for e in ev if e.type in ("lesson.ready", "step.started")], "a lesson on connect")
                r.check(not [e for e in ev if e.type == "card" and e.p.get("kind") == "resume"], "a resume card")
                h = await self.get("/health")
                r.check(h.get("ok"), f"/health {h}")
            try:
                for take in (self.take1, self.take2, self.take3, self.take5):
                    await take()
            finally:
                async with self.row("FX", "isolation", "side effects the private engine blocked or recorded", tier="info") as r:
                    eff = self.effects()
                    kinds: dict[str, int] = {}
                    for e in eff:
                        key = e["what"] + (f" {e.get('program')}" if e.get("program") else "")
                        kinds[key] = kinds.get(key, 0) + 1
                    r.note(f"{kinds}")
                    r.note(f"companion calls: {sorted({c['route'] for c in self.comp.calls})}")
                await self.app.close()


# --------------------------------------------------------------------------------------------- entry points

def engine_log_problems(path: Path, limit: int = 30) -> list[str]:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    return [ln[:240] for ln in lines if re.search(r"Traceback|\bERROR\b|exception", ln)][:limit]


async def rehearse(port: int | None = None, base: Path | None = None, verbose: bool = False,
                   extra_env: dict[str, str] | None = None, python: str | None = None, slack: float = 1.0) -> dict:
    """One full rehearsal on a private engine. -> {"ok", "rows": [...], "engine_log", ...}
    slack: every timing limit times this (1.0: the run of show's own beats; pytest uses 1.5)."""
    port = port or DEFAULT_PORT
    base = Path(base or tempfile.mkdtemp(prefix="miyagi-demo-rehearsal-"))
    base.mkdir(parents=True, exist_ok=True)
    comp = FakeCompanion()
    comp.start()
    env = engine_env(port, base, comp.port, extra_env)
    eng = PrivateEngine(port, env, base / "engine.log", python=python)
    t0 = time.monotonic()
    reh = Rehearsal(port, base, comp, verbose=verbose, slack=slack)
    head = ""
    with contextlib.suppress(Exception):
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              timeout=5).stdout.strip()
    try:
        up = await eng.start()
        reh.log(f"engine up in {up:.1f}s on :{port} (HOME {env['HOME']})")
        await reh.run()
    finally:
        eng.stop()
        comp.stop()
        with contextlib.suppress(OSError), open(base / "events.jsonl", "w", encoding="utf-8") as f:
            for e in reh.app.events:  # everything the engine sent, for a failed row's post-mortem
                f.write(json.dumps({"t": round(e.t - t0, 3), "type": e.type, "payload": e.p}) + "\n")
    demo_rows = [r for r in reh.rows if r.tier == "demo"]
    return {"ok": all(r.ok for r in demo_rows) and bool(demo_rows), "head": head, "port": port, "base": str(base),
            "secs": round(time.monotonic() - t0, 1), "engine_log": str(base / "engine.log"),
            "engine_log_problems": engine_log_problems(base / "engine.log"),
            "rows": [r.to_dict() for r in reh.rows]}


def table(report: dict, color: bool = False) -> str:
    G, R, Y, D, X = ("\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m") if color else ("",) * 5
    out = [f"Demo rehearsal on {report.get('head') or '?'} · :{report['port']} · {report['secs']}s · "
           f"{'PASS' if report['ok'] else 'FAIL'}", ""]
    out.append(f"{'row':7} {'tier':5} {'result':6} {'secs':>5}  {'DEMO.md / brief':22} what")
    for r in report["rows"]:
        res = "PASS" if r["ok"] else ("WARN" if r["tier"] != "demo" else "FAIL")
        c = G if r["ok"] else (Y if r["tier"] != "demo" else R)
        out.append(f"{r['id']:7} {r['tier']:5} {c}{res:6}{X} {r['secs']:5.1f}  {r['ref'][:22]:22} {r['what']}")
        if r["timings"]:
            out.append(f"{'':21}{D}{'  '.join(f'{k} {v}s' for k, v in r['timings'].items())}{X}")
        for f in r["fails"]:
            out.append(f"{'':21}{c}x {f}{X}")
        for n in r["notes"]:
            out.append(f"{'':21}{D}- {n}{X}")
    if report.get("engine_log_problems"):
        out += ["", f"engine log problems ({report['engine_log']}):"] + [f"  {ln}" for ln in
                                                                        report["engine_log_problems"][:12]]
    return "\n".join(out)


def deps_missing() -> str | None:
    """Why the rehearsal can't run here (None: it can)."""
    for mod in ("websockets", "httpx", "uvicorn", "fastapi"):
        try:
            __import__(mod)
        except ImportError:
            return f"{mod} is not installed"
    if not STARTER.exists() or not RUNS_FILE.exists():
        return "demo/nn-start.py or demo/cache/stage/nn-runs.json is missing"
    return None
