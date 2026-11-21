"""Rehearse the stage demo end to end against a real engine, over the WebSocket (no UI).

  .venv/bin/python scripts/rehearse.py                       # spawn an engine on :8797, rehearse once
  .venv/bin/python scripts/rehearse.py --runs 3              # three takes, one fresh engine + temp pinn-lab each
  .venv/bin/python scripts/rehearse.py --offline             # network dead for external APIs (keys + proxy + Tiger)
  .venv/bin/python scripts/rehearse.py --offline --demo      # same, with DEMO=1 (cached/canned data)
  .venv/bin/python scripts/rehearse.py --prefill DIR         # only write the stage's pre-filled pinn_diffusion.py into DIR

The take follows docs/devpost/DEMO.md:
  pre-fill sections 1-7 of a TEMP COPY of demo/pinn-lab (lr = 0.3) -> learn <stage query> -> pick the Toscano row
  -> lesson.ready -> /debug/goto/7 (s8 "Train the network and log loss") -> `tut run python pinn_diffusion.py`
  -> amber + offtrack card -> Do it for me (apply_fix) -> preview card -> confirm -> `tut run` again -> green -> video resumes.
Every beat is timed; the JSON report goes to --out (default: the scratch folder).

It never touches demo/pinn-lab itself, never talks to another engine's port, and kills only the engine it spawned.
Cost: a live take makes ~11 Anthropic calls and a few docs-page web requests (no Gemini: the lesson is cached); --offline takes
cost nothing (bogus keys behind a dead proxy).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "demo" / "pinn-lab"
STAGE_QUERY = "learn physics informed machine learning with PINNs in PyTorch"
HERO_VIDEO = "AXXnSzmpyoI"
HERO_LESSON = "lesson-aebc6b8f"
TRAIN_STEP_INDEX = 7  # s8 "Train the network and log loss" (DEMO.md: curl -X POST .../debug/goto/7)
DEFAULT_PORT = 8797  # never 8787 (Michael's live engine); 8790/8794 are other sessions' stage engines
BAD_PROXY = "http://127.0.0.1:9"  # discard port: every proxied request fails at once

# --------------------------------------------------------------------------- the learner's code

# Sections 1-7 of pinn-lab/pinn_diffusion.py, written the way Toscano's video does them (same names as the
# lesson's checks: FCN, lossBC / lossPDE / loss, PINN, Adam, report). Section 8 stays a TODO on purpose:
# a plot would write results.png into the folder, which changes E2's cache fingerprint (file names) and
# turns the cached lesson into a live Gemini build.
SECTIONS = {
    "1. Libraries and setup": """\
import numpy as np
import torch
import torch.autograd as autograd
import torch.nn as nn
try:
    from pyDOE import lhs  # Latin hypercube sampling
except ImportError:  # pyDOE >= 0.4 is the `pydoe` module
    from pydoe import lhs

torch.set_default_dtype(torch.float)
torch.manual_seed(1234)
np.random.seed(1234)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
""",
    "2. Tuning parameters and the exact solution": """\
steps = {steps}
lr = {lr}
layers = np.array([2, 32, 32, 1])
x_min, x_max, t_min, t_max = -1, 1, 0, 1
total_points_x, total_points_t = 200, 100
Nu, Nf = 100, 10000


def f_real(x, t):
    return torch.exp(-t) * torch.sin(np.pi * x)


x = torch.linspace(x_min, x_max, total_points_x).view(-1, 1)
t = torch.linspace(t_min, t_max, total_points_t).view(-1, 1)
X, T = torch.meshgrid(x.squeeze(1), t.squeeze(1), indexing="ij")
y_real = f_real(X, T)
""",
    "3. Test data: flatten the grid into (x, t) pairs": """\
x_test = torch.hstack((X.transpose(1, 0).flatten()[:, None], T.transpose(1, 0).flatten()[:, None]))
y_test = y_real.transpose(1, 0).flatten()[:, None]
lb, ub = x_test[0], x_test[-1]
""",
    "4. Training data: initial and boundary conditions": """\
left_X = torch.hstack((X[:, 0][:, None], T[:, 0][:, None]))  # t = 0
left_Y = torch.sin(np.pi * left_X[:, 0]).unsqueeze(1)
bottom_X = torch.hstack((X[0, :][:, None], T[0, :][:, None]))  # x = -1
bottom_Y = torch.zeros(bottom_X.shape[0], 1)
top_X = torch.hstack((X[-1, :][:, None], T[-1, :][:, None]))  # x = 1
top_Y = torch.zeros(top_X.shape[0], 1)
X_train = torch.vstack([left_X, bottom_X, top_X])
Y_train = torch.vstack([left_Y, bottom_Y, top_Y])
idx = np.random.choice(X_train.shape[0], Nu, replace=False)
X_train_Nu, Y_train_Nu = X_train[idx, :], Y_train[idx, :]
""",
    "5. Collocation points": """\
X_train_Nf = lb + (ub - lb) * torch.from_numpy(lhs(2, Nf)).float()
X_train_Nf = torch.vstack((X_train_Nf, X_train_Nu))
X_train_Nu, Y_train_Nu, X_train_Nf = X_train_Nu.to(device), Y_train_Nu.to(device), X_train_Nf.to(device)
X_test, Y_test = x_test.to(device), y_test.to(device)
""",
    "6. The PINN": """\
class FCN(nn.Module):
    def __init__(self, layers):
        super().__init__()
        self.activation = nn.Tanh()
        self.loss_function = nn.MSELoss(reduction="mean")
        self.linears = nn.ModuleList([nn.Linear(layers[i], layers[i + 1]) for i in range(len(layers) - 1)])
        for lin in self.linears:
            nn.init.xavier_normal_(lin.weight.data, gain=1.0)
            nn.init.zeros_(lin.bias.data)

    def forward(self, x):
        a = x.float()
        for lin in self.linears[:-1]:
            a = self.activation(lin(a))
        return self.linears[-1](a)

    def lossBC(self, x_BC, y_BC):
        return self.loss_function(self.forward(x_BC), y_BC)

    def lossPDE(self, x_PDE):
        g = x_PDE.clone()
        g.requires_grad = True
        f = self.forward(g)
        f_x_t = autograd.grad(f, g, torch.ones([g.shape[0], 1]).to(device), retain_graph=True, create_graph=True)[0]
        f_xx_tt = autograd.grad(f_x_t, g, torch.ones(g.shape).to(device), create_graph=True)[0]
        f_t = f_x_t[:, [1]]
        f_xx = f_xx_tt[:, [0]]
        f = f_t - f_xx + torch.exp(-g[:, 1:]) * (torch.sin(np.pi * g[:, 0:1]) - np.pi**2 * torch.sin(np.pi * g[:, 0:1]))
        return self.loss_function(f, torch.zeros_like(f))

    def loss(self, x_BC, y_BC, x_PDE):
        return self.lossBC(x_BC, y_BC) + self.lossPDE(x_PDE)
""",
    "7. Train": """\
PINN = FCN(layers).to(device)
optimizer = torch.optim.Adam(PINN.parameters(), lr=lr, amsgrad=False)
for i in range(steps):
    loss = PINN.loss(X_train_Nu, Y_train_Nu, X_train_Nf)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    if i % 100 == 0 or i == steps - 1:
        with torch.no_grad():
            test_loss = PINN.lossBC(X_test, Y_test)
        report(i, loss.item(), test_loss.item())
""",
}

LR_LINE = re.compile(r"^lr = .*$", re.MULTILINE)


def prefill(starter_text: str, steps: int, lr: str) -> str:
    """The starter with sections 1-7 filled in (each section's TODO comment lines replaced)."""
    out = starter_text
    for title, code in SECTIONS.items():
        code = code.replace("{steps}", str(steps)).replace("{lr}", lr)
        pat = re.compile(r"(# " + re.escape(title) + r"\n# =+\n)((?:# .*\n|#\s*\n)+)")
        out, n = pat.subn(lambda m, c=code: m.group(1) + c, out, count=1)
        if n != 1:
            raise RuntimeError(f"starter section not found: {title!r} (did demo/pinn-lab change?)")
    return out


def starter_files() -> dict[str, str]:
    """demo/pinn-lab as committed (git HEAD), not the working folder: on stage day that folder holds the presenter's
    pre-filled file and a .venv. Falls back to the files on disk outside a git checkout."""
    rel = STARTER.relative_to(ROOT).as_posix()
    try:
        names = subprocess.run(["git", "ls-files", rel], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        out = {n[len(rel) + 1:]: subprocess.run(["git", "show", f"HEAD:{n}"], cwd=ROOT, capture_output=True, text=True,
                                                check=True).stdout for n in names}
        if "pinn_diffusion.py" in out:
            return out
    except (OSError, subprocess.CalledProcessError):
        pass
    return {p.name: p.read_text() for p in STARTER.iterdir() if p.is_file() and not p.name.startswith(".")}


def make_workdir(base: Path, steps: int, lr: str) -> Path:
    """base/pinn-lab: the committed demo/pinn-lab files (same folder NAME and file names, so E2's cache key matches),
    with sections 1-7 pre-filled."""
    wd = base / "pinn-lab"
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True)
    for name, text in starter_files().items():
        (wd / name).parent.mkdir(parents=True, exist_ok=True)
        (wd / name).write_text(text)
    f = wd / "pinn_diffusion.py"
    f.write_text(prefill(f.read_text(), steps, lr))
    return wd


# --------------------------------------------------------------------------- engine


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def offline_env() -> dict[str, str]:
    """External APIs unreachable: bogus keys, every HTTP(S) client through a dead proxy (localhost exempt),
    Tiger's DSN on a black-holed address (what the venue Wi-Fi does to its port)."""
    return {
        "ANTHROPIC_API_KEY": "sk-ant-offline-rehearsal",
        "GEMINI_API_KEY": "offline-rehearsal",
        "GOOGLE_API_KEY": "offline-rehearsal",
        "ELEVENLABS_API_KEY": "offline-rehearsal",
        "HTTPS_PROXY": BAD_PROXY, "HTTP_PROXY": BAD_PROXY, "ALL_PROXY": BAD_PROXY,
        "https_proxy": BAD_PROXY, "http_proxy": BAD_PROXY, "all_proxy": BAD_PROXY,
        "NO_PROXY": "localhost,127.0.0.1,::1", "no_proxy": "localhost,127.0.0.1,::1",
        "TIGER_DATABASE_URL": "postgres://tsdbadmin:offline@10.255.255.1:34567/tsdb?sslmode=require&connect_timeout=3",
    }


def engine_env(port: int, workdir: Path, *, demo: bool, offline: bool, extra: dict[str, str]) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "ENGINE_PORT": str(port),
        "ORCH_HERO_WORKDIR": str(workdir),  # S2: the hero lesson's folder = our temp copy
        "ORCH_SCREEN": "0",  # no screen reader: precision checks (files + tut run) grade the step
        "ORCH_OPEN_WORKSPACE": "0",  # never open VS Code from a rehearsal
        "ORCH_AUTOSTART": "0",  # the launcher flow: learn -> pick -> build
        "DEMO": "1" if demo else "0",
        "MIYAGI_STATE_DIR": str(workdir.parent / "state"),
        "PYTHONUNBUFFERED": "1",
    })
    env.pop("TUT_WORKDIR", None)  # it would override the hero folder
    if demo:  # like scripts/miyagi-offline.sh: two cached lessons are the hero video; pin the stage one
        env["ORCH_LESSON"] = str(ROOT / "demo" / "cache" / "lessons" / "aebc6b8fba02dac5.json")
    if offline:
        env.update(offline_env())
    env.update(extra)
    return env


# The engine reads this Mac's REAL keyboard/mouse idle time (server/orchestrator/inputs.py): it never speaks within
# 2 s of a keystroke, and keys/clicks in the last 3 s block the idle trigger. Anyone typing on this Mac while a take
# runs delays the coach card by however long they keep typing. --hands-off (default) starts the engine with that
# reader off, i.e. a presenter whose hands stay off the keyboard while the run finishes; --real-inputs keeps it.
HANDS_OFF_BOOT = (
    "import sys, server.orchestrator.inputs as m\n"
    "m.Inputs.__init__ = lambda self: setattr(self, 'q', None)\n"
    "from server.orchestrator.main import run\n"
    "sys.argv = ['server.orchestrator.main'] + sys.argv[1:]\n"
    "run()\n"
)


class Engine:
    def __init__(self, port: int, env: dict[str, str], log_path: Path, hands_off: bool = True):
        self.port, self.env, self.log_path, self.hands_off = port, env, log_path, hands_off
        self.proc: subprocess.Popen | None = None

    async def start(self, timeout: float = 60.0) -> float:
        if not port_free(self.port):
            raise SystemExit(f"port {self.port} is busy; pick another with --port (never 8787)")
        py = ROOT / ".venv" / "bin" / "python"
        self.log = open(self.log_path, "w")  # noqa: SIM115
        t0 = time.monotonic()
        boot = ["-c", HANDS_OFF_BOOT] if self.hands_off else ["-m", "server.orchestrator.main"]
        self.proc = subprocess.Popen([str(py if py.exists() else sys.executable), *boot,
                                      "--host", "127.0.0.1", "--port", str(self.port)],
                                     cwd=ROOT, env=self.env, stdout=self.log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        async with httpx.AsyncClient() as c:
            while time.monotonic() - t0 < timeout:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"engine exited ({self.proc.returncode}); see {self.log_path}")
                with contextlib.suppress(httpx.HTTPError):
                    if (await c.get(f"http://127.0.0.1:{self.port}/health", timeout=1)).status_code == 200:
                        return time.monotonic() - t0
                await asyncio.sleep(0.2)
        raise TimeoutError(f"engine not up after {timeout}s; see {self.log_path}")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(8)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.proc.pid, signal.SIGKILL)
        with contextlib.suppress(Exception):
            self.log.close()


# --------------------------------------------------------------------------- the take


class Take:
    """One rehearsal: a WebSocket client that plays the app (video position reports included)."""

    def __init__(self, port: int, workdir: Path, *, fix: str, verbose: bool, timeout: float, pick_after: float = 0.0):
        self.port, self.workdir, self.fix, self.verbose, self.timeout = port, workdir, fix, verbose, timeout
        self.pick_after = pick_after
        self.http = f"http://127.0.0.1:{port}"
        self.events: list[tuple[float, str, dict]] = []
        self.cursor = 0
        self.t0 = time.monotonic()
        self.beats: list[dict] = []
        self.notes: list[str] = []
        self.ws = None
        self.video = {"t": 0.0, "playing": False, "at": time.monotonic()}
        self.stalls: list[tuple[float, float]] = []  # (at, seconds) the engine took > 0.5 s to answer /health

    # -- plumbing
    async def probe(self) -> None:
        """GET /health every 0.25 s: a slow answer means the engine's event loop was blocked (tut's
        run_started POST gives up after 1.0 s, and every WS message waits too)."""
        async with httpx.AsyncClient() as c:
            while True:
                t = time.monotonic()
                with contextlib.suppress(httpx.HTTPError):
                    await c.get(f"{self.http}/health", timeout=10)
                dt = time.monotonic() - t
                if dt > 0.5:
                    self.stalls.append((round(t - self.t0, 1), round(dt, 2)))
                    if self.verbose:
                        self.log(f"engine stalled {dt:.2f}s")
                await asyncio.sleep(0.25)

    def now(self) -> float:
        return time.monotonic() - self.t0

    def log(self, msg: str) -> None:
        print(f"  {self.now():6.1f}s  {msg}", flush=True)

    async def reader(self) -> None:
        async for raw in self.ws:
            msg = json.loads(raw)
            t, p = msg.get("type"), msg.get("payload") or {}
            self.events.append((self.now(), t, p))
            if t == "video.seek":
                self.video = {"t": float(p.get("t", 0)), "playing": bool(p.get("play")), "at": time.monotonic()}
            elif t == "video.play":
                self.video = {**self.video, "t": self.video_t(), "playing": True, "at": time.monotonic()}
            elif t == "video.pause":
                self.video = {**self.video, "t": self.video_t(), "playing": False, "at": time.monotonic()}
            if self.verbose and t not in ("metric", "lesson.building", "video.state"):
                body = json.dumps(p, ensure_ascii=False)
                print(f"  {self.now():6.1f}s  <- {t:15} {body[:150]}", flush=True)

    def video_t(self) -> float:
        v = self.video
        return v["t"] + (time.monotonic() - v["at"] if v["playing"] else 0.0)

    async def player(self) -> None:
        """Report the playhead once a second, like the app's player."""
        while True:
            await asyncio.sleep(1.0)
            with contextlib.suppress(Exception):
                await self.send("video.state", {"t": round(self.video_t(), 2), "playing": self.video["playing"]})

    async def send(self, type_: str, payload: dict) -> None:
        await self.ws.send(json.dumps({"type": type_, "payload": payload}))

    async def expect(self, pred, what: str, timeout: float | None = None, since: int | None = None):
        """Wait for the first event (from `since`, default the cursor) matching pred(type, payload)."""
        deadline = time.monotonic() + (timeout or self.timeout)
        i = self.cursor if since is None else since
        while True:
            while i < len(self.events):
                t_ev, typ, p = self.events[i]
                i += 1
                if pred(typ, p):
                    self.cursor = i
                    return t_ev, p
            if time.monotonic() > deadline:
                raise TimeoutError(f"timed out waiting for {what}")
            await asyncio.sleep(0.05)

    def beat(self, name: str, start: float, end: float, ok: bool, detail: str = "") -> None:
        self.beats.append({"beat": name, "start_s": round(start, 2), "end_s": round(end, 2),
                           "took_s": round(end - start, 2), "ok": ok, "detail": detail})
        mark = "OK  " if ok else "FAIL"
        self.log(f"[{mark}] {name}: {end - start:.2f}s  {detail}")

    async def tut_run(self, argv: list[str] | None = None, timeout: float = 600.0) -> tuple[float, float, int, str]:
        """`tut run <argv>` in the workdir (default: the hero's `python pinn_diffusion.py`), the engine's /ingest as
        the sink. stdin is /dev/null, so a script that waits for input() ends instead of hanging the take."""
        env = dict(os.environ, TUT_INGEST_URL=f"{self.http}/ingest", PYTHONUNBUFFERED="1",
                   **{k: v for k, v in self.run_env.items()})
        tut = ROOT / ".venv" / "bin" / "tut"
        argv = argv or [str(ROOT / ".venv" / "bin" / "python"), "pinn_diffusion.py"]
        t_start = self.now()
        proc = await asyncio.create_subprocess_exec(str(tut), "run", "-v", *argv, cwd=self.workdir, env=env,
                                                    stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            out, _ = await proc.communicate()
        text = out.decode(errors="replace")
        return t_start, self.now(), proc.returncode or 0, text

    # -- the demo
    async def run(self, run_env: dict[str, str]) -> dict:
        self.run_env = run_env
        async with websockets.connect(f"ws://127.0.0.1:{self.port}/", max_size=2**24) as ws:
            self.ws = ws
            rd = asyncio.create_task(self.reader())
            pl = asyncio.create_task(self.player())
            pr = asyncio.create_task(self.probe())
            try:
                await self._script()
            except Exception as e:  # noqa: BLE001 - a failed beat is a result, not a crash
                self.notes.append(f"ABORTED: {type(e).__name__}: {e}")
                self.log(f"ABORTED: {e}")
            finally:
                rd.cancel()
                pl.cancel()
                pr.cancel()
        if self.stalls:
            self.notes.append("engine stalls (at s, for s): " + ", ".join(f"{a}+{d}" for a, d in self.stalls))
        return {"beats": self.beats, "notes": self.notes, "total_s": round(self.now(), 2), "stalls": self.stalls,
                "events": [(round(t, 2), typ, p) for t, typ, p in self.events if typ not in ("metric", "video.state")]}

    async def _script(self) -> None:
        await asyncio.sleep(0.3)  # the connect snapshot
        self.cursor = len(self.events)

        # 1. search
        t = self.now()
        await self.send("learn", {"query": STAGE_QUERY})
        t1, first = await self.expect(lambda ty, p: ty in ("search.result", "error"), "first search.result")
        if "message" in first and "id" not in first:
            self.beat("search: first row", t, t1, False, first["message"])
            raise RuntimeError("search failed")
        rows_from = self.cursor - 1
        t2, _ = await self.expect(lambda ty, p: ty == "search.done", "search.done")
        rows = [p for _, ty, p in self.events[rows_from:self.cursor] if ty == "search.result"]
        hero = next((r for r in rows if HERO_VIDEO in (r.get("url") or "")), None)
        rank = rows.index(hero) + 1 if hero else None
        self.beat("search: first row", t, t1, True, f"{first.get('title', '')[:60]!r}")
        self.beat("search: done", t, t2, rank == 1, f"{len(rows)} rows, Toscano at #{rank}")
        if hero is None:
            raise RuntimeError("Toscano video not in the results")

        # 2. pick -> (S8 preflight card -> Build) -> lesson.ready. DEMO=1 / no preflight module: builds at once.
        if self.pick_after:  # the presenter talks over the rows; the engine prefetches preflight meanwhile
            await asyncio.sleep(self.pick_after)
        t = self.now()
        await self.send("build_lesson", {"resultIds": [hero["id"]]})
        t1, ev = await self.expect(lambda ty, p: ty == "lesson.ready" or (ty == "lesson.building" and p.get("failed"))
                                   or (ty == "card" and p.get("kind") == "preflight"), "preflight card or lesson.ready",
                                   timeout=max(self.timeout, 120))
        if ev.get("kind") == "preflight":
            pf = ev.get("preflight") or {}
            self.beat("pick: preflight card", t, t1, "build" in (ev.get("actions") or []),
                      f"{ev.get('title', '')!r} · actions {ev.get('actions')}")
            self.notes.append(f"preflight card: {ev.get('title', '')!r}: {(ev.get('body') or '')[:160]!r}"
                              + (f" · warning {ev['warning']!r}" if ev.get("warning") else "")
                              + (f" · partial={pf.get('partial')}" if "partial" in pf else ""))
            await asyncio.sleep(0.3)  # the presenter reads the card, then presses Build
            t = self.now()
            await self.send("action", {"kind": "build"})
            t1, ready = await self.expect(lambda ty, p: ty == "lesson.ready" or (ty == "lesson.building" and p.get("failed")),
                                          "lesson.ready", timeout=max(self.timeout, 120))
        else:
            ready = ev
        if "lesson" not in ready:
            self.beat("build: lesson.ready", t, t1, False, ready.get("message", ""))
            raise RuntimeError("build failed")
        lid = ready["lesson"]["id"]
        async with httpx.AsyncClient() as c:
            st = (await c.get(f"{self.http}/state")).json()
        wd_ok = Path(st.get("workdir", "")).resolve() == self.workdir.resolve()
        self.beat("build: lesson.ready", t, t1, lid == HERO_LESSON and wd_ok,
                  f"{lid} · {len(ready['steps'])} steps · workdir {'= temp copy' if wd_ok else st.get('workdir')}")
        if not wd_ok:
            raise RuntimeError(f"engine watches {st.get('workdir')}, not the temp copy")
        building = [p.get("message", "") for _, ty, p in self.events if ty == "lesson.building"]
        if building:
            self.notes.append("build stages: " + " | ".join(dict.fromkeys(m.split(" · ")[0] for m in building)))

        # 3. jump to the training step (DEMO.md: curl -X POST .../debug/goto/7)
        t = self.now()
        async with httpx.AsyncClient() as c:
            await c.post(f"{self.http}/debug/goto/{TRAIN_STEP_INDEX}")
        t1, started = await self.expect(lambda ty, p: ty == "step.started" and p.get("index") == 8 or
                                        (ty == "step.started" and p.get("stepId") == "s8"), "step.started s8")
        self.beat("goto training step", t, t1, started.get("stepId") == "s8", started.get("title", ""))
        await asyncio.sleep(0.5)

        # 4. run at lr = 0.3 -> amber + coach card
        t_run, t_end, code, out = await self.tut_run()
        losses = re.findall(r"step (\d+) \| loss ([0-9.eE+-]+)", out)
        last = losses[-1] if losses else ("?", "?")
        self.beat("run 1 (lr = 0.3)", t_run, t_end, code == 0, f"exit {code}, {len(losses)} reports, last loss {last[1]} @ {last[0]}")
        self._tut_notes(out, "run 1")
        since = next(i for i, (te, _, _) in enumerate(self.events) if te >= t_run)
        t_amber, amber = await self.expect(lambda ty, p: ty == "check.updated" and p.get("status") == "fail",
                                           "a failing check", since=since)
        rel = f"{t_amber - t_end:+.1f}s vs run end"
        self.beat("amber (from run start)", t_run, t_amber, True,
                  f"{amber.get('label')} · {amber.get('detail', '')}"[:100] + f" ({rel})")
        t_card, card = await self.expect(lambda ty, p: ty == "offtrack", "offtrack card", since=since)
        thinking = next((te for te, ty, p in self.events[since:] if ty == "status" and p.get("state") == "thinking"
                         and te >= t_amber), t_amber)
        text = f"{card.get('title', '')} {card.get('body', '')}"
        right = bool(re.search(r"learning rate|\blr\b", text, re.IGNORECASE)) and "1e-3" in text.replace("0.001", "1e-3")
        self.beat("coach card (from amber)", t_amber, t_card, right,
                  f"L{card.get('level')} {card.get('title', '')!r} · actions {card.get('actions')} · "
                  f"model {t_card - thinking:.1f}s · {t_card - t_end:+.1f}s vs run end")
        self.notes.append(f"card body: {card.get('body', '')[:300]}")

        # 5. fix
        if self.fix == "manual":
            t = self.now()
            f = self.workdir / "pinn_diffusion.py"
            f.write_text(LR_LINE.sub("lr = 1e-3", f.read_text(), count=1))
            self.beat("fix by hand (lr = 1e-3, save)", t, self.now(), True)
        else:
            card_level, card_actions = card.get("level"), card.get("actions") or []
            if "apply_fix" not in card_actions and self.fix == "ladder":
                # the app shows "Do it for me" only on the level-3 card: same failure saved again >= LADDER_MIN_S later
                t = self.now()
                wait = float(self.run_env.get("ORCH_LADDER_MIN_S", os.environ.get("ORCH_LADDER_MIN_S", "20")))
                await asyncio.sleep(max(0.0, wait - (self.now() - t_card)) + 0.5)
                f = self.workdir / "pinn_diffusion.py"
                f.write_text(f.read_text())  # ⌘S with no change: the same failure on a save
                t3, card3 = await self.expect(lambda ty, p: ty == "offtrack" and "apply_fix" in (p.get("actions") or []),
                                              "level-3 card with Do it for me")
                self.beat("escalate to Do it for me (re-save)", t, t3, True, f"L{card3.get('level')} actions {card3.get('actions')}")
            elif "apply_fix" not in card_actions:
                self.notes.append(f"first card is level {card_level} without apply_fix: the app shows no 'Do it for me' "
                                  "button on it; sent apply_fix anyway (--fix direct)")
            t = self.now()
            await self.send("action", {"kind": "apply_fix"})
            t1, prev = await self.expect(lambda ty, p: ty in ("card", "error"), "apply_fix preview card")
            is_preview = "confirm" in (prev.get("actions") or [])
            self.beat("Do it for me -> preview", t, t1, is_preview,
                      f"{prev.get('title', prev.get('message', ''))!r}: {prev.get('body', '')[:80]!r}")
            if is_preview:
                self.notes.append("preview diff: " + (prev.get("diff") or "").replace("\n", " ⏎ ")[:300])
                t = self.now()
                await self.send("action", {"kind": "confirm"})
                t1, applied = await self.expect(lambda ty, p: ty in ("card", "error"), "Fix applied card")
                self.beat("confirm -> fix applied", t, t1, applied.get("title") == "Fix applied", applied.get("title", ""))
            elif prev.get("title") == "Fix applied":  # no preview step (propose_fix path): written directly
                self.notes.append("apply_fix wrote the file with NO preview/confirm (stub/propose_fix path)")
            else:
                f = self.workdir / "pinn_diffusion.py"
                f.write_text(LR_LINE.sub("lr = 1e-3", f.read_text(), count=1))
                self.notes.append("Do it for me gave no patch: fixed by hand instead (lr = 1e-3, save)")
        lr_now = LR_LINE.search((self.workdir / "pinn_diffusion.py").read_text())
        self.notes.append(f"after the fix: {lr_now.group(0) if lr_now else 'lr line not found'}")
        await asyncio.sleep(0.5)

        # 6. run again -> green -> video resumes
        t_run2 = self.now()
        run2 = asyncio.create_task(self.tut_run())
        since = next((i for i, (te, _, _) in enumerate(self.events) if te >= t_run2), len(self.events))
        t_pass, passed = await self.expect(lambda ty, p: ty == "step.passed" and p.get("stepId") == "s8", "step.passed s8",
                                           since=since, timeout=max(self.timeout, 120))
        self.beat("run 2 (lr = 1e-3) -> green", t_run2, t_pass, True, f"next {passed.get('nextStepId')}")
        t_vid, vid = await self.expect(lambda ty, p: ty in ("video.play", "video.seek") and (p.get("play", True)),
                                       "video resumes")
        self.beat("video resumes", t_pass, t_vid, True, json.dumps(vid))
        _, _, code2, out2 = await run2
        losses = re.findall(r"step (\d+) \| loss ([0-9.eE+-]+)", out2)
        under = next((s for s, v in losses if float(v) < 1e-2), None)
        self.notes.append(f"run 2: exit {code2}, first loss < 1e-2 at step {under}, run took {self.now() - t_run2:.1f}s "
                          f"(green came {t_pass - t_run2:.1f}s in)")
        self._tut_notes(out2, "run 2")

    def _tut_notes(self, out: str, label: str) -> None:
        for line in out.splitlines():
            if line.startswith(("[tut]", "tut:")) or "Tiger" in line or "spool" in line:
                self.notes.append(f"{label} tut: {line.strip()[:200]}")


# --------------------------------------------------------------------------- "Just teach me" (no video)

TEACH_QUERY = "build a calculator in python"
TEACH_LESSON = ROOT / "demo" / "cache" / "lessons" / "text-43e26ca1d86c37ed.json"  # Michael's live calculator run
# The starter S2's Claude scaffold wrote for that run (~/miyagi/lessons/python-calculator-e430dc). Offline (or under the
# cost freeze) the scaffold call fails and the folder gets a README only, so the steps' "# Step 1: …" anchor is missing.
TEACH_STARTER = {"calculator.py": '"""A simple Python calculator."""\n\n# Step 1: Start building your calculator here\n'}


def teach_folder(lessons_root: Path, goal: str = TEACH_QUERY) -> Path:
    """The folder the engine's "Just teach me" build will use (S2's name for the seed lesson in _build_text)."""
    import hashlib

    from server.workspace.paths import folder_name

    seed = {"lesson": {"id": "text-" + hashlib.sha1(goal.strip().lower().encode()).hexdigest()[:10], "title": goal,
                       "goal": goal, "mode": "lesson"}, "steps": [], "sources": []}
    return lessons_root / folder_name(seed)


def _engine_run_command(step: dict) -> str:
    """The engine's own rule (LessonSession._run_command): a "run it" step boxes the terminal, anything else boxes
    a line in the editor."""
    from server.orchestrator.session import LessonSession

    return LessonSession._run_command(LessonSession, step)


def _literal_line(text: str, match: str) -> int | None:
    for i, ln in enumerate(text.splitlines(), start=1):
        if match in ln:
            return i
    return None


def box_report(step: dict, workdir: Path) -> dict:
    """Where the engine would box this step, from the files as they are now (no screen needed): the run/type
    decision, the target's line by the engine's target_location (regex) vs where the anchor literally is."""
    from server.orchestrator.workspace import target_location

    run_cmd = _engine_run_command(step)
    t = next((x for x in step.get("targets") or [] if x.get("match")), {})
    rep = {"kind": "run (terminal box)" if run_cmd else "type (editor line box)", "run_command": run_cmd,
           "target": t.get("match"), "target_app": t.get("app"), "caption": t.get("caption")}
    f = workdir / (t.get("file") or step.get("file") or "")
    if t.get("file") and f.is_file():
        text = f.read_text(errors="replace")
        loc = target_location(workdir, step)
        rep["engine_line"] = loc[1] if loc else None
        rep["literal_line"] = _literal_line(text, t["match"])
        rep["file_lines"] = len(text.splitlines())
    return rep


def _type_into(text: str, code: str) -> str:
    """The learner types the step's code: a function that already exists is rewritten in place, `if __name__`
    stays last, and once main() exists the old top-level test print goes (as the steps ask)."""
    lines = text.rstrip("\n").splitlines()
    for m in re.finditer(r"^def (\w+)\(", code, re.MULTILINE):  # rewrite: drop the old def block
        name, out, skip = m.group(1), [], False
        for ln in lines:
            if re.match(rf"def {name}\(", ln):
                skip = True
                continue
            if skip and (ln.startswith((" ", "\t")) or not ln.strip()):
                continue
            skip = False
            out.append(ln)
        lines = out
    if "def main(" in code or "def main(" in "\n".join(lines):
        lines = [ln for ln in lines if not re.fullmatch(r"print\(add\(2, ?3\)\)", ln.strip())]
    tail = []
    if "__main__" not in code and any("__main__" in ln for ln in lines):
        k = next(i for i, ln in enumerate(lines) if "__main__" in ln)
        lines, tail = lines[:k], lines[k:]
    return "\n".join(lines + ["", code.rstrip("\n"), ""] + tail).strip("\n") + "\n"


def _stdin_for(step: dict) -> str | None:
    """`printf '8\n2\n/\n' | python calculator.py` in a precision check -> the answers to pipe in."""
    for c in step.get("precision_checks") or []:
        m = re.search(r"printf\s+(['\"])(.*?)\1\s*\|", c.get("command") or "")
        if m:
            return m.group(2)
    return None


class TeachTake(Take):
    """The "Just teach me" path: learn {mode: lesson} -> lesson.ready (no video) -> each step: type -> Check
    (action check_step) -> next; a run step: `tut run`. Records instructions, cards, spotlights, and where the
    engine would box each step."""

    def __init__(self, *a, max_steps: int = 0, **kw):
        super().__init__(*a, **kw)
        self.max_steps = max_steps
        self.steps_out: list[dict] = []

    async def run(self, run_env: dict[str, str]) -> dict:
        res = await super().run(run_env)
        res["teach_steps"] = self.steps_out
        return res

    async def _check(self, sid: str, wait: float = 8.0) -> tuple[str, dict, float]:
        t = self.now()
        await self.send("action", {"kind": "check_step"})
        try:
            t1, ev = await self.expect(lambda ty, p: (ty == "step.passed" and p.get("stepId") == sid)
                                       or (ty == "card" and p.get("stepId") == sid), f"Check on {sid}", timeout=wait)
        except TimeoutError:
            return "no answer", {}, self.now() - t
        matched_type = self.events[self.cursor - 1][1]  # expect() leaves the cursor just past the match
        return ("passed" if matched_type == "step.passed" else "card"), ev, t1 - t

    async def _script(self) -> None:
        await asyncio.sleep(0.3)
        self.cursor = len(self.events)
        t = self.now()
        await self.send("learn", {"query": TEACH_QUERY, "mode": "lesson"})
        t1, ready = await self.expect(lambda ty, p: ty == "lesson.ready" or (ty == "lesson.building" and p.get("failed")),
                                      "lesson.ready", timeout=max(self.timeout, 120))
        if "lesson" not in ready:
            self.beat("Just teach me → lesson.ready", t, t1, False, ready.get("message", ""))
            raise RuntimeError("text lesson build failed")
        async with httpx.AsyncClient() as c:
            st = (await c.get(f"{self.http}/state")).json()
        self.workdir = Path(st["workdir"])
        video = any(ty.startswith("video.") for _, ty, _ in self.events)
        self.beat("Just teach me → lesson.ready", t, t1, ready["lesson"]["id"].startswith("lesson-") and not video,
                  f"{ready['lesson']['id']} {ready['lesson'].get('title')!r} · {len(ready['steps'])} steps · "
                  f"{'VIDEO EVENTS SENT' if video else 'no video'} · folder {self.workdir.name}")
        building = [p.get("message", "") for _, ty, p in self.events if ty == "lesson.building"]
        self.notes.append("build stages: " + " | ".join(dict.fromkeys(building)))
        starter = {p.name: p.read_text(errors="replace")[:300] for p in sorted(self.workdir.iterdir()) if p.is_file()}
        self.notes.append(f"starter files: {json.dumps(starter)[:400]}")
        lesson = json.loads(TEACH_LESSON.read_text())
        by_id = {s["id"]: s for s in lesson["steps"]}
        n = len(ready["steps"]) if not self.max_steps else min(self.max_steps, len(ready["steps"]))
        for k in range(n):
            sid = ready["steps"][k]["id"]
            step = by_id.get(sid, {})
            since = self.cursor
            t0 = self.now()
            try:
                _, started = await self.expect(lambda ty, p, sid=sid: ty == "step.started" and p.get("stepId") == sid,
                                                f"step.started {sid}", timeout=20, since=max(0, since - 40))
            except TimeoutError:
                self.beat(f"{sid} starts", t0, self.now(), False, "never started")
                break
            await asyncio.sleep(1.0)  # the step-start spotlight / setup card land
            rec = {"step": sid, "title": step.get("title"), "instructions": started.get("instructions"),
                   "details": (started.get("details") or "")[:200], "box": box_report(step, self.workdir),
                   "spotlights": [p for _, ty, p in self.events[since:] if ty == "spotlight"],
                   "cards_at_start": [{k2: p.get(k2) for k2 in ("kind", "title", "body")} for _, ty, p in self.events[since:]
                                      if ty == "card"]}
            run_cmd = rec["box"]["run_command"]
            f = self.workdir / (step.get("file") or "calculator.py")
            passed, how = False, []
            if not run_cmd and (step.get("code") or "").strip():  # type step
                tt = self.now()
                f.write_text(_type_into(f.read_text() if f.exists() else "", step["code"]))
                await asyncio.sleep(1.0)
                how.append("typed")
                verdict, ev, _ = await self._check(sid)
                how.append(f"Check → {verdict}" + (f" {ev.get('title')!r}: {ev.get('body')!r}" if verdict == "card" else ""))
                passed = verdict == "passed"
                self.beat(f"{sid} type → Check", tt, self.now(), passed, how[-1][:150])
            if not passed:  # a run (the run step itself, or a type step whose checks also want a run)
                stdin = _stdin_for(step)
                script = (run_cmd or step.get("run_command") or f"python {f.name}").replace("python ", "python3 ", 1)
                argv = ["bash", "-c", f"printf '{stdin}' | {script}"] if stdin else script.split()
                tr, _, code, out = await self.tut_run(argv, timeout=30)
                how.append(f"tut run {' '.join(argv)[:60]!r} → exit {code}, out {out.splitlines()[:1]!r}")
                try:
                    await self.expect(lambda ty, p, sid=sid: ty == "step.passed" and p.get("stepId") == sid, f"{sid} passes",
                                      timeout=4, since=since)
                    passed = True
                except TimeoutError:
                    verdict, ev, _ = await self._check(sid)
                    how.append(f"Check → {verdict}" + (f" {ev.get('title')!r}: {ev.get('body')!r}" if verdict == "card" else ""))
                    passed = verdict == "passed"
                self.beat(f"{sid} run{' step' if run_cmd else ''} → green", tr, self.now(), passed, how[-1][:150])
            if not passed:
                await self.send("action", {"kind": "skip_step"})
                how.append("skipped")
            rec.update(passed=passed, how=how, seconds=round(self.now() - t0, 2))
            self.steps_out.append(rec)
            self.cursor = len(self.events)


# --------------------------------------------------------------------------- main


async def rehearse_once(i: int, args, scratch: Path) -> dict:
    base = scratch / f"take-{i}-{int(time.time())}"
    base.mkdir(parents=True)
    teach = args.path == "teach"
    wd = (base / "lessons") if teach else make_workdir(base, args.steps, "0.3")
    extra = dict(kv.split("=", 1) for kv in args.env)
    env = engine_env(args.port, wd, demo=args.demo, offline=args.offline, extra=extra)
    if teach:  # S2 makes the lesson folder under the take, and DEMO=1 serves the newest cached "lesson"-mode lesson
        wd.mkdir()
        env.update({"MIYAGI_LESSONS_DIR": str(wd), "MIYAGI_LESSONS": str(wd)})
        env.pop("ORCH_LESSON", None)
        if TEACH_LESSON.exists():
            os.utime(TEACH_LESSON)
        if args.teach_starter:  # S2 never replaces existing files: the stage folder starts like Michael's live run
            folder = teach_folder(wd)
            folder.mkdir(parents=True)
            for name, text in TEACH_STARTER.items():
                (folder / name).write_text(text)
    if not args.real_spool:  # Tiger still spools (that's what we test), but into the take's folder: a rehearsal
        env["TUT_SPOOL_DIR"] = str(base / "tiger-spool")  # must never upload into the team's real Tiger stats
    run_env = {k: env[k] for k in ("TIGER_DATABASE_URL", "TUT_SPOOL_DIR") if k in env}
    if args.offline:
        run_env.update({k: v for k, v in offline_env().items() if "PROXY" in k.upper()})
    if "ORCH_LADDER_MIN_S" in extra:
        run_env["ORCH_LADDER_MIN_S"] = extra["ORCH_LADDER_MIN_S"]
    eng = Engine(args.port, env, base / "engine.log", hands_off=not args.real_inputs)
    mode = (("DEMO=1 " if args.demo else "LIVE ") + ("offline" if args.offline else "online")
            + ("" if args.real_inputs else " · hands-off"))
    print(f"\n=== take {i} · {mode} · workdir {wd}")
    up = await eng.start()
    print(f"  engine up in {up:.1f}s on :{args.port} (log {base / 'engine.log'})")
    try:
        async with httpx.AsyncClient() as c:
            health = (await c.get(f"http://127.0.0.1:{args.port}/health")).json()
        if teach:
            take = TeachTake(args.port, wd, fix=args.fix, verbose=args.verbose, timeout=args.timeout, max_steps=args.teach_steps)
        else:
            take = Take(args.port, wd, fix=args.fix, verbose=args.verbose, timeout=args.timeout, pick_after=args.pick_after)
        res = await take.run(run_env)
    finally:
        eng.stop()
    res.update({"take": i, "mode": mode, "fix": args.fix, "steps": args.steps, "engine_up_s": round(up, 1),
                "modules": health.get("modules"), "workdir": str(wd), "engine_log": str(base / "engine.log")})
    log_text = (base / "engine.log").read_text(errors="replace")
    res["engine_log_errors"] = [ln[:240] for ln in log_text.splitlines()
                                if re.search(r"ERROR|Traceback|failed|spool|offline|playbook|coach meta", ln)][:40]
    ok = all(b["ok"] for b in res["beats"]) and not any(n.startswith("ABORTED") for n in res["notes"])
    res["ok"] = ok
    print(f"  take {i}: {'PASS' if ok else 'FAIL'} in {res['total_s']:.1f}s")
    for n in res["notes"]:
        print(f"    · {n}")
    for st in res.get("teach_steps", []):
        b = st["box"]
        print(f"    {st['step']} {st['title']!r}: {b['kind']}; box target {b.get('target')!r} → engine line "
              f"{b.get('engine_line')} / literal line {b.get('literal_line')} of {b.get('file_lines')}; "
              f"{'PASS' if st['passed'] else 'SKIPPED'} in {st['seconds']}s")
        print(f"       instructions: {st['instructions']!r}")
        print(f"       caption: {b.get('caption')!r}")
        print(f"       how: {st['how']}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--demo", action="store_true", help="DEMO=1 engine (demo/cache + canned stubs)")
    ap.add_argument("--offline", action="store_true", help="external APIs unreachable (bad keys, dead proxy, Tiger black-holed)")
    ap.add_argument("--path", choices=["hero", "teach"], default="hero",
                    help="hero: the PINN video lesson; teach: \"Just teach me\" (no video, cached text lesson, DEMO=1)")
    ap.add_argument("--teach-steps", type=int, default=0, help="with --path teach: stop after N steps (0 = all)")
    ap.add_argument("--no-teach-starter", dest="teach_starter", action="store_false",
                    help="with --path teach: don't pre-seed the lesson folder with the live run's calculator.py starter")
    ap.add_argument("--real-spool", action="store_true",
                    help="spool Tiger data to ~/.miyagi/tiger-spool (uploaded to the real Tiger later); default: the take's folder")
    ap.add_argument("--real-inputs", action="store_true",
                    help="let the engine read this Mac's real keyboard/mouse idle time (typing delays the coach)")
    ap.add_argument("--fix", choices=["ladder", "direct", "manual"], default="direct",
                    help="direct: send apply_fix after the first card; ladder: re-save until the app would show "
                         "'Do it for me' (level 3); manual: edit lr by hand")
    ap.add_argument("--steps", type=int, default=2500, help="training iterations in the pre-filled code")
    ap.add_argument("--timeout", type=float, default=90.0, help="per-beat timeout (s)")
    ap.add_argument("--pick-after", type=float, default=0.0, metavar="S",
                    help="wait S seconds after search.done before picking (the presenter's narration)")
    ap.add_argument("--env", action="append", default=[], metavar="K=V", help="extra engine env (repeatable)")
    ap.add_argument("--out", type=Path, help="JSON report path")
    ap.add_argument("--prefill", type=Path, metavar="DIR",
                    help="only write the stage's pre-filled pinn_diffusion.py (lr = 0.3) into DIR and exit")
    ap.add_argument("--lr", default="0.3", help="with --prefill: the learning rate to write")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.prefill:
        f = args.prefill / "pinn_diffusion.py"
        f.write_text(prefill(starter_files()["pinn_diffusion.py"], args.steps, args.lr))
        print(f"wrote {f} (sections 1-7, steps = {args.steps}, lr = {args.lr})")
        return 0
    if args.port == 8787:
        print("refusing :8787 (Michael's live engine); use another --port")
        return 2

    scratch = Path(os.environ.get("REHEARSE_DIR") or tempfile.mkdtemp(prefix="miyagi-rehearsal-"))
    results = []
    for i in range(1, args.runs + 1):
        results.append(asyncio.run(rehearse_once(i, args, scratch)))
    out = args.out or scratch / f"rehearsal-{int(time.time())}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"\nreport: {out}")
    names = list(dict.fromkeys(b["beat"] for r in results for b in r["beats"]))
    print("\n| take | " + " | ".join(names) + " | total |")
    for r in results:
        by = {b["beat"]: b for b in r["beats"]}
        cells = [f"{by[n]['took_s']:.1f}{'' if by[n]['ok'] else ' ✗'}" if n in by else "—" for n in names]
        print(f"| {r['take']} | " + " | ".join(cells) + f" | {r['total_s']:.0f} |")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
