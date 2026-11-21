"""Nov 21 (launch-quiet): a freshly booted engine does nothing visible until the app asks for a lesson.

Michael, on every launch of the installed app: "Right when it opens, it just opens up everything" (the steps drawer,
the lesson player, VS Code, a video with sound, prompts to control the screen). Launch = starting from new: the app's
sign-in first. So on connect: engine.hello (never restored) and status idle only: no lesson.ready, step.started,
video.*, spotlight or resume / step / setup / preflight card; no VS Code; the screen reader never started. The saved
lesson stays on disk (its lastActiveAt untouched) and is offered once the app asks for its library; Continue restores
it paused. Offline: stub modules, a recording workspace, a fake screen reader; never the real engine or windows."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from server import sessions
from server.orchestrator import stubs
from server.orchestrator import workspace as wsmod
from server.orchestrator.modules import Modules
from server.orchestrator.session import LessonSession

QUIET_CARDS = ("resume", "step", "setup", "preflight")


class FakeReader:
    """server.screen's reader, never started for real."""

    def __init__(self) -> None:
        self.interval = 2.0
        self.status = "ok"
        self.last_error = None
        self.starts = 0
        self.front_cbs: list = []
        self.ax_reader = None
        self.events = None
        self._thread = None

    def start(self):
        self.starts += 1
        return self

    def stop(self) -> None:
        pass

    def subscribe(self, cb):
        return lambda: None

    def on_frontmost_change(self, cb, interval: float = 0.25):
        self.front_cbs.append(cb)
        return lambda: None

    def latest(self):
        return None

    def set_overlay_bounds(self, rects) -> None:
        pass


class RecWorkspace(wsmod.Workspace):
    """Records every VS Code open; opens nothing."""

    def __init__(self) -> None:
        super().__init__(enabled=True, runner=lambda argv: True)
        self.opens: list[dict] = []

    def open(self, workdir, force=False, full=False, explicit=False, **k):
        self.opens.append({"workdir": workdir, "full": full, "explicit": explicit})
        self.opened = workdir

    def goto_target(self, *a, **k):
        return None


@pytest.fixture
def quiet_env(tmp_path, monkeypatch):
    import server.screen as screen_pkg

    reader = FakeReader()
    monkeypatch.setattr(screen_pkg, "get_reader", lambda: reader)  # ScreenBridge imports server.screen by name
    monkeypatch.delenv("ORCH_AUTO_RESUME", raising=False)
    monkeypatch.delenv("ORCH_SCREEN_EAGER", raising=False)
    monkeypatch.delenv("ORCH_AUTOSTART", raising=False)
    monkeypatch.delenv("ORCH_SCREEN", raising=False)
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.setenv("MIYAGI_SYSTEM_STATUS", "0")  # no network / health probes from a test
    monkeypatch.setenv("MIYAGI_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "work"))
    (tmp_path / "work").mkdir()
    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: None)  # no setup check (no model call)
    return reader


def _engine(monkeypatch):
    """A new engine process on the same disk: stub modules (any build fails the test), a recording workspace."""
    from server.orchestrator import main

    eng = main.Engine()
    eng.recorder.enabled = False
    ws = RecWorkspace()
    eng.workspace = eng.session.workspace = ws
    eng.session.m = eng.modules = Modules(demo=False, force_stubs="all")
    calls: list[str] = []
    for name in ("build_lesson", "build_text_lesson", "extend_lesson"):
        async def boom(*_a, _n=name, **_k):
            calls.append(_n)
            raise AssertionError(_n)
        setattr(eng.session.m, name, boom)
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "host_allowed", lambda _h: True)  # TestClient's Host is "testserver"
    return main, eng, ws, calls


def _save_unended_video_lesson(monkeypatch) -> tuple[dict, float]:
    """The last app run: a video lesson at step 3, 20 s into its clip, never ended; that engine then stops."""
    _, eng, _, _ = _engine(monkeypatch)
    eng.session.workspace = None  # nothing opens in the old run either

    async def go() -> dict:
        await eng.session.load_graph(stubs.load_fixture_lesson())
        await eng.session.drain()
        await eng.session.goto_step(2)
        await eng.session.drain()
        seg = eng.session._segment(eng.session.step)
        await eng.session.video_state(seg["start"] + 20, False)
        await eng.stop()  # the app quit: the engine stops (and saves the exact place)
        return seg

    seg = asyncio.run(go())
    saved = sessions.load()
    assert saved is not None and saved["stepIndex"] == 2 and not saved.get("stopped")
    assert saved["videoT"] == seg["start"] + 20
    return seg, float(saved["lastActiveAt"])


def _until(ws, type_: str, limit: int = 200) -> list[dict]:
    got: list[dict] = []
    while not got or got[-1]["type"] != type_:
        got.append(ws.receive_json())
        assert len(got) < limit, [m["type"] for m in got]
    return got


def _visible(msgs: list[dict]) -> list[dict]:
    return [m for m in msgs if m["type"] in ("lesson.ready", "step.started", "spotlight", "lesson.building")
            or m["type"].startswith("video.")
            or m["type"] == "card" and (m["payload"] or {}).get("kind") in QUIET_CARDS]


def test_fresh_engine_connect_is_quiet(quiet_env, monkeypatch):
    from fastapi.testclient import TestClient

    _, last_active = _save_unended_video_lesson(monkeypatch)
    time.sleep(0.01)  # any re-save now would carry a later lastActiveAt
    current = sessions.state_dir() / "current.json"
    before = current.read_bytes()
    main, eng, ws_rec, calls = _engine(monkeypatch)
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "engine.hello" and "restored" not in hello["payload"]
            ws.send_json({"type": "progress.get", "payload": {}})  # a fence: everything before it is the connect burst
            burst = _until(ws, "progress")[:-1]
            assert burst == [{"type": "status", "payload": {"state": "idle"}}], [m["type"] for m in burst]
            assert not _visible(burst)
        assert client.get("/state").json()["phase"] != "active"
    assert eng.session.graph is None and calls == []
    assert ws_rec.opens == []  # VS Code never opened
    assert quiet_env.starts == 0 and quiet_env.front_cbs == []  # no capture, taps, AX reader or front-app poller
    assert eng.screen.reader is quiet_env and eng.session.screen is eng.screen  # the bridge is real, just idle
    assert current.read_bytes() == before  # kept, not rewritten
    assert sessions.load()["lastActiveAt"] == last_active


def test_saved_lesson_is_offered_after_library_list_and_continue_restores_it_paused(quiet_env, monkeypatch):
    from fastapi.testclient import TestClient

    seg, last_active = _save_unended_video_lesson(monkeypatch)
    main, eng, _, calls = _engine(monkeypatch)
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            assert ws.receive_json()["type"] == "engine.hello"
            assert ws.receive_json() == {"type": "status", "payload": {"state": "idle"}}
            ws.send_json({"type": "library.list", "payload": {}})
            lib = ws.receive_json()
            assert lib["type"] == "library"
            ws.send_json({"type": "progress.get", "payload": {}})  # fence: exactly one card came with the library
            after = _until(ws, "progress")[:-1]
            cards = [m for m in after if m["type"] == "card"]
            assert len(cards) == 1 and cards[0]["payload"]["kind"] == "resume", after
            assert "step 3 of" in cards[0]["payload"]["body"]
            assert not [m for m in after if m["type"] != "card"]
            assert quiet_env.starts == 0

            ws.send_json({"type": "action", "payload": {"kind": "resume"}})  # Continue
            got = _until(ws, "step.started")
            types = [m["type"] for m in got]
            assert "lesson.ready" in types
            ws.send_json({"type": "progress.get", "payload": {}})
            got += _until(ws, "progress")
            seeks = [m["payload"] for m in got if m["type"] == "video.seek"]
            assert seeks and seeks[-1] == {"t": seg["start"] + 20, "play": False}  # waits paused at its place
            assert not [m for m in got if m["type"] == "video.play"]
            assert [m["payload"]["index"] for m in got if m["type"] == "step.started"] == [2]
    assert calls == []
    saved = sessions.load()
    assert saved["stepIndex"] == 2 and saved["lastActiveAt"] == last_active  # the restore never stamps "now"


def test_library_list_offers_nothing_for_a_stopped_save(quiet_env, monkeypatch):
    from fastapi.testclient import TestClient

    _save_unended_video_lesson(monkeypatch)
    sessions.save({**sessions.load(), "stopped": True})  # the learner pressed End last time
    main, _, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            ws.receive_json()
            ws.receive_json()
            ws.send_json({"type": "library.list", "payload": {}})
            ws.send_json({"type": "progress.get", "payload": {}})
            got = _until(ws, "progress")
            assert [m["type"] for m in got if m["type"] in ("library", "card")] == ["library"]


# ---------------------------------------------------------------------------------------------- VS Code waits for Start
def _sheet_lesson() -> dict:
    g = stubs.text_lesson(stubs.load_fixture_lesson(), goal="teach me PINNs")
    g["lesson"]["build"] = {"summary": "A tiny PINN for the convection equation", "outcome": "It trains"}
    return g


def _held_session(tmp_path, asked: bool) -> tuple[LessonSession, RecWorkspace, list]:
    sent: list = []

    async def emit(t, p=None):
        sent.append((t, p))

    s = LessonSession(emit, Modules(demo=False, force_stubs="all"), idle_gate_s=5, advance_delay_s=0,
                      metric_eval_s=0, result_stagger_s=0, build_tick_s=0.01, seen_interval_s=0)
    s.ready_hold_s = 0
    s.has_clients = lambda: True  # an app is connected: it opens "Before you start"
    s.learner_asked = asked  # main.py: False until a learn / pick / library.start / Start / Continue on this connection
    ws = RecWorkspace()
    s.workspace = ws
    return s, ws, sent


def test_lesson_mode_vscode_waits_for_start_while_before_you_start_is_held(quiet_env, tmp_path):
    s, ws, _ = _held_session(tmp_path, asked=False)

    async def go():
        await s.load_graph(_sheet_lesson())
        await s.drain()
        assert s.lesson_mode and s.awaiting_start
        assert ws.opens == []  # nothing asked on this connection: no VS Code under the sheet

        # a key / click in an editor Miyagi did not open is not the lesson's start
        s._work_since = lambda kind: 0.0
        s._front_now = lambda: "Code"
        for _ in range(2):
            await s._maybe_begin()
        assert s.awaiting_start and ws.opens == []

        await s.action("start")  # "Start the lesson": now VS Code opens on the step's file
        await asyncio.sleep(0.05)
        await s.drain()
        assert not s.awaiting_start
        assert ws.opens and ws.opens[-1]["explicit"] is True

    asyncio.run(go())


def test_lesson_mode_vscode_opens_under_the_sheet_when_the_learner_asked(quiet_env, tmp_path):
    s, ws, _ = _held_session(tmp_path, asked=True)

    async def go():
        await s.load_graph(_sheet_lesson())
        await s.drain()
        assert s.awaiting_start and ws.opens and ws.opens[0]["full"] is True  # as before: a learn opens it

    asyncio.run(go())


def test_a_held_open_goes_when_another_control_begins_the_step(quiet_env, tmp_path):
    s, ws, _ = _held_session(tmp_path, asked=False)

    async def go():
        await s.load_graph(_sheet_lesson())
        await s.drain()
        assert ws.opens == []
        await s.action("hint")  # any step control begins the held step: its VS Code opens now
        await asyncio.sleep(0.05)
        await s.drain()
        assert not s.awaiting_start and ws.opens

    asyncio.run(go())


def test_engine_marks_learner_asks_per_connection(quiet_env, monkeypatch):
    _, eng, _, _ = _engine(monkeypatch)
    assert eng.session.learner_asked is False  # a fresh engine: nothing asked yet

    async def go():
        await eng.dispatch({"type": "action", "payload": {"kind": "pick_another"}})
        assert eng.session.learner_asked is False  # a control press is not a lesson ask
        await eng.dispatch({"type": "action", "payload": {"kind": "start"}})
        assert eng.session.learner_asked is True

    asyncio.run(go())


def test_returning_app_never_gets_an_old_preflight_card(quiet_env, tmp_path):
    s, _, _ = _held_session(tmp_path, asked=True)
    s.pending_pick = {"url": "https://example.com/v", "row": {}, "card": {"kind": "preflight", "title": "Check"}}
    s.phase = "preflight"
    assert ("card", s.pending_pick["card"]) in s.snapshot()  # a quick reconnect: the card is still up
    assert s.snapshot(returning=True) == [("status", {"state": "idle"})]  # the app relaunched: dropped
    assert s.pending_pick is None and s.phase == "idle"
    assert json.dumps(s.snapshot())  # and it stays gone
