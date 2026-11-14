"""Engine hub: FastAPI app on :8787.

  WS   /                 events.ts protocol ({type, payload} JSON both ways)
  POST /ingest           `tut run` events (one object, a list, or {"events": [...]})
  GET  /state            session state (debugging, the CLI client's simulator)
  GET  /events?since=N   recent engine events (debugging)
  POST /debug/pass       force-pass the active step
  POST /debug/goto/{i}   jump to step i
  POST /debug/lesson     load the canned/demo lesson without searching

Run:  python -m server.orchestrator.main      (or uvicorn server.orchestrator.main:app --port 8787)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Any

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect

from shared.contracts.events import parse_app_message

from . import config, recorder
from .hub import Hub
from .modules import Modules
from .screen_bridge import ScreenBridge
from .session import LessonSession
from .watcher import Watcher

log = logging.getLogger("orchestrator")


class Engine:
    def __init__(self) -> None:
        self.hub = Hub()
        self.modules = Modules()
        self.screen = ScreenBridge()
        self.session = LessonSession(self.hub.emit, self.modules, screen=self.screen)
        self.watcher = Watcher(self.session.on_file_change, interval=config.WATCH_INTERVAL_S)
        self.session.on_workdir = self.watcher.set_root
        self.recorder = recorder.Recorder()
        self._ticker: asyncio.Task | None = None
        self._replays: set[asyncio.Task] = set()

    async def ingest(self, ev: dict) -> None:
        self.recorder.record(ev)
        await self.session.ingest(ev)

    async def start(self) -> None:
        self.watcher.set_root(self.session.workdir)
        self.watcher.start()
        if not self.screen.start(self.session.on_screen):
            self.session.screen = None  # precision mode only (files + tut run)
        self._ticker = asyncio.create_task(self._tick_loop())
        log.info("engine up: demo=%s modules=%s workdir=%s", self.modules.demo, self.modules.describe(),
                 self.session.workdir)

    async def stop(self) -> None:
        await self.watcher.stop()
        self.screen.stop()
        if self._ticker:
            self._ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ticker

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                await self.session.tick()
            except Exception:
                log.exception("tick failed")

    async def dispatch(self, raw: dict) -> None:
        msg = parse_app_message(raw)
        p = msg.payload
        s = self.session
        if msg.type == "learn":
            await s.learn(p.query)
        elif msg.type == "learn_url":
            await s.learn_url(p.url)
        elif msg.type == "build_lesson":
            await s.build_lesson(p.resultIds)
        elif msg.type == "action":
            await s.action(p.kind, p.text)
        elif msg.type == "video.state":
            await s.video_state(p.t, p.playing)
        elif msg.type == "overlay.bounds":
            s.overlay_bounds([r.model_dump() for r in p.rects])
        elif msg.type == "config.keys":
            await self.hub.emit("config.status", apply_keys(p.model_dump()))


# config.keys name -> env var the modules read. Keys stay in this process's memory; never logged.
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "brightdata": "BRIGHTDATA_API_KEY",
           "elevenlabs": "ELEVENLABS_API_KEY", "tigerUrl": "TIGER_DATABASE_URL"}
_ENV_AT_START = {name: os.environ.get(var, "") for name, var in KEY_ENV.items()}


def _usable(v: str | None) -> bool:
    return bool(v) and "..." not in v


def apply_keys(keys: dict) -> dict:
    """Use the app's keys over .env (bring-your-own-key); answer with presence only."""
    status = {}
    for name, var in KEY_ENV.items():
        v = (keys.get(name) or "").strip()
        if _usable(v):
            os.environ[var] = v
            status[name] = "ok"
        elif _usable(_ENV_AT_START[name]):
            os.environ[var] = _ENV_AT_START[name]
            status[name] = "env"
        else:
            status[name] = "missing"
    return status


def _redact(raw: dict) -> dict:
    return {"type": raw.get("type"), "payload": "<redacted>"} if raw.get("type") == "config.keys" else raw


engine = Engine()


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    await engine.start()
    yield
    await engine.stop()


app = FastAPI(title="sandhacks-tutor engine", lifespan=lifespan)


@app.websocket("/")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    for type_, payload in engine.session.snapshot():
        await engine.hub.send_to(ws, type_, payload)
    engine.hub.clients.add(ws)
    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def worker() -> None:
        # commands run in order, off the receive loop, so video.state keeps flowing
        while True:
            raw = await queue.get()
            try:
                await engine.dispatch(raw)
            except Exception as e:
                log.exception("command failed: %s", _redact(raw))
                with contextlib.suppress(Exception):
                    await engine.hub.send_to(ws, "error", {"message": f"{raw.get('type')}: {e}"})

    task = asyncio.create_task(worker())
    try:
        while True:
            raw = await ws.receive_json()
            if not isinstance(raw, dict):
                continue
            if raw.get("type") in ("video.state", "overlay.bounds"):  # frequent + instant: skip the queue
                try:
                    await engine.dispatch(raw)
                except Exception:
                    log.exception("bad video.state: %s", raw)
            else:
                await queue.put(raw)
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        log.exception("websocket error")
    finally:
        engine.hub.clients.discard(ws)
        task.cancel()


@app.post("/ingest")
async def ingest(body: Any = Body(...)) -> dict:
    if isinstance(body, dict) and isinstance(body.get("events"), list):
        events = body["events"]
    elif isinstance(body, list):
        events = body
    else:
        events = [body]
    n = 0
    for ev in events:
        if isinstance(ev, dict):
            await engine.ingest(ev)
            n += 1
    st = engine.session.step
    lesson = (engine.session.graph or {}).get("lesson", {})
    # E3's `tut run` tags its Tiger run with these
    return {"ok": True, "accepted": n, "lesson_id": lesson.get("id"), "step_id": st["id"] if st else None}


@app.get("/state")
async def state() -> dict:
    return engine.session.state()


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "clients": len(engine.hub.clients), "demo": engine.modules.demo,
            "modules": engine.modules.describe()}


@app.get("/events")
async def events(since: int = 0) -> dict:
    items = list(engine.hub.history)
    return {"total": len(items), "events": items[since:]}


@app.post("/debug/pass")
async def debug_pass() -> dict:
    await engine.session.force_pass()
    return {"ok": True}


@app.post("/debug/goto/{idx}")
async def debug_goto(idx: int) -> dict:
    await engine.session.goto_step(idx)
    return {"ok": True}


@app.post("/debug/lesson")
async def debug_lesson() -> dict:
    graph = await engine.modules.build_lesson("", "", str(config.default_workdir()))
    await engine.session.load_graph(graph)
    return {"ok": True, "lesson": graph.get("lesson")}


@app.get("/demo/runs")
async def demo_runs() -> dict:
    return {"runs": [str(p.relative_to(config.REPO_ROOT)) for p in recorder.list_recordings()]}


@app.post("/demo/replay")
async def demo_replay(body: dict | None = Body(None)) -> dict:
    """Replay a recorded `tut run` (default: newest) into the active step. Body: {"name"?, "speed"?}"""
    body = body or {}
    path = recorder.find_recording(body.get("name"))
    if path is None:
        return {"ok": False, "error": "no recording found in demo/cache/runs or demo/runs"}
    speed = float(body.get("speed") or recorder.default_speed())
    task = asyncio.create_task(recorder.replay(path, engine.session.ingest, speed=speed))
    engine._replays.add(task)
    task.add_done_callback(engine._replays.discard)
    return {"ok": True, "replaying": path.name, "speed": speed}


def run() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=config.port(), log_level="info")


if __name__ == "__main__":
    run()
