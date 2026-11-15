"""Engine hub: FastAPI app on :8787.

  WS   /                 events.ts protocol ({type, payload} JSON both ways)
  POST /ingest           `tut run` events (one object, a list, or {"events": [...]})
  POST /end              end the current lesson (curl -X POST localhost:8787/end)
  GET  /state            session state (debugging, the CLI client's simulator)
  GET  /events?since=N   recent engine events (debugging)
  POST /debug/pass       force-pass the active step
  POST /debug/goto/{i}   jump to step i
  POST /debug/lesson     DEMO only: load the cached/canned lesson without searching
  GET  /stage            is a Demo lesson running (launcher → Demo, or MIYAGI_STAGE=1; stage.py)
  POST /stage/{cmd}      presenter, Demo lessons only: next | back | restart

Run:  python -m server.orchestrator.main      (or uvicorn server.orchestrator.main:app --port 8787)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from typing import Any

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect

from shared.contracts.events import parse_app_message

from server import config as server_config

from . import config, recorder, stage
from .hub import Hub, log_received
from .modules import Modules
from .screen_bridge import ScreenBridge
from .session import LessonSession
from .watcher import Watcher
from .inputs import Inputs
from .workspace import Workspace

log = logging.getLogger("orchestrator")


class Engine:
    def __init__(self) -> None:
        self.hub = Hub()
        self.modules = Modules()
        self.screen = ScreenBridge()
        self.workspace = Workspace()
        self.session = LessonSession(self._emit, self.modules, screen=self.screen, workspace=self.workspace,
                                     inputs=Inputs())
        self.watcher = Watcher(self.session.on_file_change, interval=config.WATCH_INTERVAL_S)
        self.session.on_workdir = self.watcher.set_root
        # E14: no off-track to an app that left (headless runs that never had an app still get them, e.g. /events)
        self.session.has_client = lambda: bool(self.hub.clients) or self.last_client_gone is None
        try:  # S7: progress saved to ~/miyagi/state; "Continue where you left off?" survives an engine restart
            from server.sessions import Resumer

            self.resumer = Resumer(self.session)
        except Exception as e:  # noqa: BLE001
            log.warning("saved-session resume unavailable: %s", e)
            self.resumer = None
        self.recorder = recorder.Recorder()
        self._ticker: asyncio.Task | None = None
        self._replays: set[asyncio.Task] = set()
        self.last_client_gone: float | None = None
        self.seen_lesson: str | None = None  # lesson id an app has already been shown

    def _lesson_id(self) -> str | None:
        return (self.session.graph or {}).get("lesson", {}).get("id")

    def mark_lesson_seen(self) -> None:
        if self._lesson_id():
            self.seen_lesson = self._lesson_id()

    def app_returning(self) -> bool:
        """The app reconnects after being away (>= ORCH_RESUME_AFTER_S with no client) to a lesson it had
        already shown: offer "Continue / Start new". A first connection (e.g. the demo's autostart) or a
        quick network blip just continues."""
        if self.hub.clients or self.last_client_gone is None or not self._lesson_id():
            return False
        away = time.monotonic() - self.last_client_gone
        return self.seen_lesson == self._lesson_id() and away >= float(os.environ.get("ORCH_RESUME_AFTER_S", "10"))

    async def _emit(self, type_: str, payload: dict | None = None) -> None:
        if type_ == "lesson.ready" and self.hub.clients:
            self.seen_lesson = ((payload or {}).get("lesson") or {}).get("id")
        if (note := getattr(self.screen, "note_ui", None)) is not None:
            note(type_, payload)  # the targeter never boxes Miyagi's own text (cards, captions) seen on screen
        await self.hub.emit(type_, payload)

    async def ingest(self, ev: dict) -> None:
        self.recorder.record(ev)
        await self.session.ingest(ev)

    async def start(self) -> None:
        self.watcher.set_root(self.session.workdir)
        self.watcher.start()
        if not self.screen.start(self.session.on_screen):
            self.session.screen = None  # precision mode only (files + tut run)
        else:  # E6: app switch / Space swipe within ~0.25 s -> clear (or re-place) the spotlight at once
            self.screen.watch_frontmost(self.session.on_frontmost)
        if config.env_flag("ORCH_AUTOSTART"):  # no launcher needed: the lesson is live from the start
            if self.modules.demo and (graph := self.modules._lesson_file()):
                await self.session.load_graph(graph)
            elif url := os.environ.get("ORCH_LESSON_URL"):  # real builder (E2's cache makes it instant)
                self._autostart = asyncio.create_task(self.session.learn_url(url, skip_preflight=True))
        self._ticker = asyncio.create_task(self._tick_loop())
        log.info("engine up: demo=%s modules=%s workdir=%s screen=%s precision=%s", self.modules.demo,
                 self.modules.describe(), self.session.workdir, self.session.screen_active(),
                 config.precision_setting())

    def save_progress(self) -> None:
        if self.resumer is not None and self.session.graph is not None and not self.session.awaiting_resume:
            try:
                self.resumer.save_now()
            except Exception:  # noqa: BLE001
                log.exception("saving lesson progress failed")

    async def stop(self) -> None:
        self.save_progress()
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
        log_received(msg.type, p)
        if msg.type == "learn":
            await s.learn(p.query, getattr(p, "mode", None))
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
        elif msg.type == "end_lesson":  # the bar's / launcher's End: stop for now, the saved progress stays resumable
            await s.end_lesson("stopped")  # (the resume card's "Start a new lesson" is action end_lesson: discards)
        elif msg.type == "config.keys":
            await self.hub.emit("config.status", apply_keys(p.model_dump()))
        elif msg.type in ("card.shown", "card.closed"):  # E14: what the learner really has on screen
            await s.card_seen(msg.type == "card.shown", p.stepId, p.title, p.kind, getattr(p, "by", None))


# config.keys -> server.config (get_key) + the env vars modules read. Memory only; never logged.
KEY_ENV = server_config.KEY_ENV
_ENV_AT_START = {name: os.environ.get(var, "") for name, var in KEY_ENV.items()}


def apply_keys(keys: dict) -> dict:
    """Use the app's keys over .env (bring-your-own-key); answer with presence only."""
    server_config.set_app_keys(keys)
    for name, var in KEY_ENV.items():
        app_key = server_config._app_keys.get(name)
        if app_key:
            os.environ[var] = app_key
        elif _ENV_AT_START[name]:
            os.environ[var] = _ENV_AT_START[name]
        else:
            os.environ.pop(var, None)
    return {name: server_config.key_source(name) for name in KEY_ENV}


def _redact(raw: dict) -> dict:
    return {"type": raw.get("type"), "payload": "<redacted>"} if raw.get("type") == "config.keys" else raw


def _searching(running: dict, session: Any) -> bool:
    """The worker is on a search (learn, not "Just teach me") that is still streaming rows."""
    cur, job = running.get("cmd") or {}, running.get("job")
    return job is not None and not job.done() and cur.get("type") == "learn" and session.phase == "searching"


def _brief(raw: dict) -> str:
    """'action hint' / 'learn': the type (+ an action's kind), never a payload (config.keys holds keys)."""
    p = raw.get("payload")
    kind = p.get("kind") if raw.get("type") == "action" and isinstance(p, dict) else None
    return f"{raw.get('type')} {kind}" if kind else str(raw.get("type"))


engine = Engine()


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    await engine.start()
    yield
    await engine.stop()


app = FastAPI(title="sandhacks-tutor engine", lifespan=lifespan)

try:  # E5 voice: GET /tts/<hash>.mp3 for `speak.audioUrl` (relative: the app prefixes ENGINE_HTTP)
    from server.coach import voice as _voice

    app.include_router(_voice.router)
except Exception as _e:  # noqa: BLE001
    log.warning("voice routes unavailable: %s", _e)

try:  # E3 Tiger stats: GET /stats (HTML, refreshes every 2 s) + /stats/data (JSON); read-only, never blocks long
    from server.checks.stats_web import router as _stats_router

    app.include_router(_stats_router)
except Exception as _e:  # noqa: BLE001
    log.warning("stats routes unavailable: %s", _e)


@app.websocket("/")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    for type_, payload in engine.session.snapshot(ask_resume=engine.app_returning()):
        await engine.hub.send_to(ws, type_, payload)
    engine.hub.join(ws)
    engine.mark_lesson_seen()
    queue: asyncio.Queue[dict] = asyncio.Queue()
    running: dict[str, dict] = {}  # the command the worker is on (a press queued behind it is logged on arrival)

    async def worker() -> None:
        # commands run in order, off the receive loop, so video.state keeps flowing
        while True:
            raw = await queue.get()
            running["cmd"] = raw
            job = running["job"] = asyncio.ensure_future(engine.dispatch(raw))  # cancellable: a new learn ends a search
            try:
                await job
            except asyncio.CancelledError:
                cur = asyncio.current_task()
                if cur is not None and cur.cancelling():
                    raise  # the app left: the worker (and its command) stop
                log.info("%s cancelled: a newer request replaced it", _brief(raw))
            except Exception as e:
                log.exception("command failed: %s", _redact(raw))
                with contextlib.suppress(Exception):
                    await engine.hub.send_to(ws, "error", {"message": f"{raw.get('type')}: {e}"})
            finally:
                running.pop("cmd", None)
                running.pop("job", None)

    task = asyncio.create_task(worker())
    why = "cancelled"  # how the socket ended (E14: the hub logs every close)
    try:
        while True:
            raw = await ws.receive_json()
            if not isinstance(raw, dict):
                continue
            if raw.get("type") in ("learn", "learn_url", "build_lesson") and engine.session.building():
                await engine.session.cancel_build()  # unblock the queue: the new request replaces the build
            elif raw.get("type") in ("learn", "learn_url", "build_lesson") and _searching(running, engine.session):
                running["job"].cancel()  # "Just teach me" / a pick / a new query while the search still runs: it
                # replaces the search (rows so far stay pickable) instead of waiting out its tail (live: 15 s)
            if raw.get("type") in ("video.state", "overlay.bounds", "end_lesson", "card.shown", "card.closed"):  # instant
                try:
                    await engine.dispatch(raw)
                except Exception:
                    log.exception("bad video.state: %s", raw)
            else:
                if (cur := running.get("cmd")) is not None:  # '<- …' is logged when it runs; this says it waited
                    log.info("<- %s queued behind %s (%d waiting)", _brief(raw), _brief(cur), queue.qsize())
                await queue.put(raw)
    except WebSocketDisconnect as e:
        why = f"closed, code {e.code}"
    except RuntimeError as e:
        why = f"closed ({e})"
    except Exception:
        log.exception("websocket error")
        why = "error"
    finally:
        engine.hub.drop(ws, why)
        if not engine.hub.clients:
            engine.last_client_gone = time.monotonic()
            engine.save_progress()  # the app left: keep the exact video position (autosave is throttled)
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


@app.post("/vscode/event")
async def vscode_event(body: dict = Body(...)) -> dict:
    """The VS Code companion (vscode-ext/) posts editor/save/dirty/focus/command_end events; see server.workspace.vscode_ext."""
    from server.workspace import vscode_ext

    item = vscode_ext.record_event(body)
    if body.get("type") == "command_end":  # a curated lesson's run: VS Code's exact output grades it (curated.py)
        from . import curated

        if curated.active(engine.session):
            engine.session._spawn(curated.on_command_end(engine.session, item))  # never holds up the extension
    if body.get("type") == "explain_selection":  # "Miyagi: Explain this" -> an Explain card in the overlay (selection.py)
        from .selection import explain_from_vscode

        return {"ok": True, "explaining": explain_from_vscode(engine.session, body)}
    return {"ok": True}


@app.post("/end")
async def end_lesson() -> dict:
    """End the current lesson from a terminal:  curl -X POST localhost:8787/end"""
    lesson = (engine.session.graph or {}).get("lesson", {}).get("id")
    await engine.session.end_lesson("POST /end")
    return {"ok": True, "ended": lesson}


@app.get("/state")
async def state() -> dict:
    st = engine.session.state()
    if engine.session.graph is None and engine.session.phase == "idle" and engine.resumer is not None:
        try:  # S7: a lesson saved before an engine restart, waiting for the learner's Continue / Start new
            from server.sessions import store

            saved = store.load()
            graph = store.load_graph(saved) if saved else None
            if graph is not None:
                st.update({"phase": "awaiting_resume", "lesson": graph.get("lesson"),
                           "saved": {k: saved.get(k) for k in ("stepIndex", "stepCount", "stepId", "videoT", "lastActiveAt")}})
        except Exception:  # noqa: BLE001
            log.exception("reading saved session failed")
    return st


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


@app.get("/stage")
async def stage_state() -> dict:
    """Is a Demo lesson running (the app binds the presenter keys while it is)?"""
    return stage.state(engine.session)


@app.post("/stage/{cmd}")
async def stage_cmd(cmd: str) -> dict:
    """Presenter, Demo lessons only: next (pass the step) | back (the step before) | restart (step 1, clean nn.py)."""
    fn = {"next": stage.next_step, "back": stage.back, "restart": stage.restart}.get(cmd)
    if fn is None:
        return {"ok": False, "error": f"unknown: {cmd} (next, back, restart)"}
    if not stage.on(engine.session):
        return {"ok": False, "error": "no Demo lesson is running"}
    if cmd == "restart":  # it ends the lesson it runs in: never inside this request
        task = asyncio.create_task(fn(engine.session))
        engine._replays.add(task)
        task.add_done_callback(engine._replays.discard)
        return {"ok": True}
    return {"ok": await fn(engine.session)}


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
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="sandhacks-tutor engine (WS + /ingest)")
    # ENGINE_HOST=0.0.0.0 / --host 0.0.0.0 lets Adrian's app reach this Mac over the LAN (ws://<mac>.local:8787)
    ap.add_argument("--host", default=os.environ.get("ENGINE_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=config.port())
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    run()
