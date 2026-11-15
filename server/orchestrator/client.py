"""Tiny CLI test client for the engine.

  python -m server.orchestrator.client                     # connect and print events
  python -m server.orchestrator.client end                 # end the current lesson (= curl -X POST localhost:8787/end)
  python -m server.orchestrator.client --learn "how to use git rebase"
  python -m server.orchestrator.client --autopilot --learn "pinn"   # DEMO tool: needs a DEMO=1 engine (canned PINN lesson)

--autopilot plays a fake learner against the REAL state machine: it reports video
positions like the player would, writes the canned PINN solution into the engine's
workdir step by step, and POSTs simulated `tut run` training runs to /ingest
(a β=30 plateau first, then apply_fix + a β-curriculum run). It only ever writes
`pinn_convection.py`, and refuses to overwrite one it did not create.
Point the engine at a scratch folder:  TUT_WORKDIR=/tmp/tut-work python -m server.orchestrator.main

Interactive commands on stdin while connected:
  learn <query> | url <youtube url> | build [id ...] | hint | explain | ask <q> | diagram [kind]
  show_me | back | apply_fix | voice | pass | goto <i> | lesson | runs | replay [name] | state | quit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
import time
from pathlib import Path

import httpx
import websockets

MARKER = "# tut-autopilot"

C = {"dim": "\033[2m", "g": "\033[32m", "y": "\033[33m", "r": "\033[31m", "b": "\033[34m", "c": "\033[36m", "x": "\033[0m"}
if not sys.stdout.isatty():
    C = {k: "" for k in C}


def fmt(msg: dict) -> str:
    t, p = msg.get("type"), msg.get("payload", {})
    ts = time.strftime("%H:%M:%S")
    col = C["x"]
    if t == "search.result":
        body = f"{p.get('id')} [{p.get('kind')}] {p.get('title')} ({p.get('score')})"
    elif t == "lesson.ready":
        body = f"{p['lesson']['title']} · {len(p['steps'])} steps"
        col = C["b"]
    elif t == "lesson.building":
        body = f"{p.get('message')} {int(100 * p.get('progress', 0))}%"
    elif t == "step.started":
        body = f"#{p.get('index')} {p.get('stepId')} · {p.get('title')}"
        col = C["b"]
    elif t == "check.updated":
        st = p.get("status")
        col = {"pass": C["g"], "fail": C["r"]}.get(st, C["dim"])
        body = f"{p.get('stepId')}/{p.get('checkId')} {st:7} {p.get('label')}" + (f" · {p['detail']}" if p.get("detail") else "")
    elif t == "step.passed":
        body = f"{p.get('stepId')} → {p.get('nextStepId')}"
        col = C["g"]
    elif t == "offtrack":
        body = f"{p.get('title')} — {p.get('body')}"
        col = C["y"]
    elif t == "metric":
        return ""
    else:
        body = json.dumps(p, ensure_ascii=False)
        if len(body) > 160:
            body = body[:157] + "..."
    return f"{C['dim']}{ts}{C['x']} {col}{t:16}{C['x']} {body}"


# ------------------------------------------------------------------ canned PINN solution

SOLUTION = {
    "s1": f"{MARKER}\n\"\"\"PINN for the 1D convection equation.\"\"\"\n",
    "s2": """import torch
import torch.nn as nn


class PINN(nn.Module):
    def __init__(self, width=50, depth=4):
        super().__init__()
        layers = [nn.Linear(2, width), nn.Tanh()]
        for _ in range(depth - 1):
            layers += [nn.Linear(width, width), nn.Tanh()]
        layers += [nn.Linear(width, 1)]
        self.net = nn.Sequential(*layers)

    def forward(self, x, t):
        return self.net(torch.cat([x, t], dim=1))
""",
    "s3": """

def sample_points(n=1000):
    x = (torch.rand(n, 1) * 2 * torch.pi).requires_grad_(True)
    t = torch.rand(n, 1).requires_grad_(True)
    return x, t
""",
    "s4": """

def pde_residual(model, x, t, beta):
    u = model(x, t)
    u_t = torch.autograd.grad(u, t, torch.ones_like(u), create_graph=True)[0]
    u_x = torch.autograd.grad(u, x, torch.ones_like(u), create_graph=True)[0]
    return u_t + beta * u_x
""",
    "s5": """

def train(model, steps=4000):
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    beta = 1
    for epoch in range(steps):
        x, t = sample_points()
        loss = pde_residual(model, x, t, beta).pow(2).mean()
        opt.zero_grad(); loss.backward(); opt.step()
""",
}


def curve(kind: str, n_steps: int = 5000, every: int = 100) -> list[tuple[int, float]]:
    rnd = random.Random(7)
    pts = []
    for s in range(0, n_steps + 1, every):
        if kind == "plateau":
            v = 0.3 + 0.7 * math.exp(-s / 120) + rnd.uniform(-0.01, 0.01)
        else:  # converging
            v = max(2e-4, 1.0 * math.exp(-s / 520)) * (1 + rnd.uniform(-0.05, 0.05))
        pts.append((s, round(v, 6)))
    return pts


class Autopilot:
    def __init__(self, http: str, send, speed: float):
        self.http = http
        self.send = send
        self.speed = speed
        self.workdir: Path | None = None
        self.hero_phase = 0
        self.running = False
        self.done = asyncio.Event()

    async def state(self) -> dict:
        async with httpx.AsyncClient() as c:
            return (await c.get(f"{self.http}/state")).json()

    async def post(self, events) -> None:
        async with httpx.AsyncClient() as c:
            await c.post(f"{self.http}/ingest", json=events)

    def file(self) -> Path:
        assert self.workdir is not None
        return self.workdir / "pinn_convection.py"

    def write(self, text: str, append: bool = True) -> None:
        p = self.file()
        if p.exists() and MARKER not in p.read_text():
            raise SystemExit(f"refusing to touch {p}: not created by the autopilot (start the engine with TUT_WORKDIR=<scratch dir>)")
        p.parent.mkdir(parents=True, exist_ok=True)
        if append and p.exists():
            p.write_text(p.read_text() + text)
        else:
            p.write_text(text)

    async def run(self, run_id: str, kind: str, exit_code: int = 0, beta: int = 1) -> None:
        self.running = True
        await self.post({"kind": "run_started", "run_id": run_id, "command": f"python pinn_convection.py --beta {beta}",
                         "cwd": str(self.workdir)})
        pts = curve(kind)
        for i in range(0, len(pts), 5):
            batch = [{"step": s, "name": "loss", "value": v} for s, v in pts[i:i + 5]]
            await self.post({"kind": "metric", "run_id": run_id, "metrics": batch})
            await asyncio.sleep(0.08 / self.speed)
        await self.post({"kind": "output", "run_id": run_id, "lines": [f"done, final loss {pts[-1][1]}"]})
        await self.post({"kind": "run_ended", "run_id": run_id, "exit_code": exit_code})
        self.running = False

    async def on_event(self, msg: dict) -> None:
        t, p = msg["type"], msg["payload"]
        if t == "search.done":
            await self.send("build_lesson", {"resultIds": ["r1"]})
        elif t == "lesson.ready":
            st = await self.state()
            self.workdir = Path(st["workdir"])
            print(f"{C['c']}autopilot: workdir {self.workdir}{C['x']}")
        elif t == "step.started":
            asyncio.create_task(self.do_step(p))
        elif t == "offtrack" and p.get("stepId") == "s6" and self.hero_phase == 1:
            self.hero_phase = 2
            asyncio.create_task(self.hero_fix())
        elif t == "step.passed" and not p.get("nextStepId"):
            print(f"{C['g']}autopilot: lesson complete{C['x']}")
            self.done.set()

    async def do_step(self, p: dict) -> None:
        sid, video = p["stepId"], p.get("video")
        await asyncio.sleep(0.6 / self.speed)
        if video:  # the player reaches the end of the segment
            await self.send("video.state", {"t": video["end"], "playing": True})
        await asyncio.sleep(0.8 / self.speed)
        if sid in ("s1", "s2", "s3", "s4", "s5") and sid in SOLUTION:
            self.write(SOLUTION[sid], append=sid != "s1")
        if sid == "s5":
            await asyncio.sleep(0.6 / self.speed)
            await self.run("run-beta1", "converge", beta=1)
        elif sid == "s6":
            text = self.file().read_text().replace("    beta = 1\n", "    beta = 30\n")
            self.write(text, append=False)
            self.hero_phase = 1
            await asyncio.sleep(0.6 / self.speed)
            await self.run("run-beta30", "plateau", beta=30)
        elif sid not in SOLUTION:
            await asyncio.sleep(1.0 / self.speed)
            async with httpx.AsyncClient() as c:  # unknown lesson: just force it
                await c.post(f"{self.http}/debug/pass")

    async def hero_fix(self) -> None:
        while self.running:
            await asyncio.sleep(0.1)
        await asyncio.sleep(1.2 / self.speed)
        await self.send("action", {"kind": "diagram"})
        await asyncio.sleep(0.8 / self.speed)
        await self.send("action", {"kind": "apply_fix"})
        await asyncio.sleep(1.0 / self.speed)
        await self.run("run-curriculum", "converge", beta=30)


async def main_async(args) -> None:
    http = args.url.replace("ws://", "http://").replace("wss://", "https://").rstrip("/")
    async with websockets.connect(args.url, max_size=None) as ws:
        async def send(type_: str, payload: dict) -> None:
            await ws.send(json.dumps({"type": type_, "payload": payload}))
            print(f"{C['dim']}{time.strftime('%H:%M:%S')}{C['x']} {C['c']}<- {type_:13}{C['x']} {json.dumps(payload)}")

        pilot = Autopilot(http, send, args.speed) if args.autopilot else None

        async def reader() -> None:
            async for raw in ws:
                msg = json.loads(raw)
                if args.json:
                    print(json.dumps(msg))
                else:
                    line = fmt(msg)
                    if line:
                        print(line, flush=True)
                if pilot:
                    await pilot.on_event(msg)

        async def stdin_loop() -> None:
            loop = asyncio.get_running_loop()
            while True:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    return
                await handle_line(line.strip(), send, http)

        tasks = [asyncio.create_task(reader())]
        if sys.stdin.isatty() and not args.autopilot:
            tasks.append(asyncio.create_task(stdin_loop()))
        if args.autopilot:
            if not args.learn:
                raise SystemExit("--autopilot needs --learn <query> (and a DEMO=1 engine: it plays the canned PINN lesson)")
            await send("learn", {"query": args.learn})
            done = asyncio.create_task(pilot.done.wait())
            await asyncio.wait([done, tasks[0]], return_when=asyncio.FIRST_COMPLETED, timeout=args.timeout)
            await asyncio.sleep(0.5)
            for t in tasks:
                t.cancel()
            if not pilot.done.is_set():
                raise SystemExit("autopilot did not finish the lesson")
            return
        if args.learn:
            await send("learn", {"query": args.learn})
        if args.lesson_url:
            await send("learn_url", {"url": args.lesson_url})
        await asyncio.gather(*tasks)


async def handle_line(line: str, send, http: str) -> None:
    if not line:
        return
    cmd, _, rest = line.partition(" ")
    actions = {"hint", "explain", "show_me", "back", "apply_fix", "diagram"}
    if cmd == "learn":
        await send("learn", {"query": rest})
    elif cmd == "url":
        await send("learn_url", {"url": rest})
    elif cmd == "build":
        await send("build_lesson", {"resultIds": rest.split() or ["r1"]})
    elif cmd in actions:
        await send("action", {"kind": cmd, **({"text": rest} if rest else {})})
    elif cmd == "ask":
        await send("action", {"kind": "ask", "text": rest})
    elif cmd == "voice":
        await send("action", {"kind": "voice_toggle"})
    elif cmd in ("pass", "goto", "state", "lesson", "replay", "runs"):
        async with httpx.AsyncClient() as c:
            if cmd == "pass":
                r = await c.post(f"{http}/debug/pass")
            elif cmd == "goto":
                r = await c.post(f"{http}/debug/goto/{int(rest or 0)}")
            elif cmd == "lesson":
                r = await c.post(f"{http}/debug/lesson")
            elif cmd == "replay":
                r = await c.post(f"{http}/demo/replay", json={"name": rest} if rest else {})
            elif cmd == "runs":
                r = await c.get(f"{http}/demo/runs")
            else:
                r = await c.get(f"{http}/state")
            print(json.dumps(r.json(), indent=2)[:3000])
    elif cmd in ("quit", "exit"):
        raise SystemExit(0)
    else:
        print("commands: learn <q> | url <u> | build [ids] | hint | explain | ask <q> | diagram [kind] | "
              "show_me | back | apply_fix | voice | pass | goto <i> | lesson | runs | replay [name] | state | quit")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", choices=["end"], help="one-shot: `end` ends the current lesson")
    ap.add_argument("--url", default="ws://localhost:8787", help="engine WebSocket URL")
    ap.add_argument("--learn", help="send a learn query on connect")
    ap.add_argument("--lesson-url", help="send learn_url on connect")
    ap.add_argument("--autopilot", action="store_true", help="drive the full happy path + hero loop")
    ap.add_argument("--speed", type=float, default=1.0, help="autopilot speed multiplier")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--json", action="store_true", help="print raw JSON messages")
    args = ap.parse_args()
    if args.command == "end":
        http = args.url.replace("ws://", "http://").replace("wss://", "https://").rstrip("/")
        r = httpx.post(f"{http}/end", timeout=10)
        print(json.dumps(r.json()))
        return
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
