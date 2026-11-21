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


def _queued_fence(ws) -> list[dict]:
    """Everything up to the engine's answer to a malformed queued command. Queued commands run one at a time in
    order, so all a command before it sent is in the list. (Never fence on an instant read such as progress.get: those
    run as side tasks beside each other and can answer out of order.)"""
    ws.send_json({"type": "fence.test", "payload": {}})
    return _until(ws, "error")


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
            assert [m["type"] for m in _until(ws, "library")] == ["library"]
            after = _until(ws, "card")  # the same handler sends it right after `library`
            assert [m["type"] for m in after] == ["card"]
            card = after[0]["payload"]
            assert card["kind"] == "resume" and "step 3 of" in card["body"], card
            # once per connection: the app asks for its library on every launcher / library open, and a second
            # ask answers `library` with no card after it (the queued fence: everything the reads sent is in)
            ws.send_json({"type": "library.list", "payload": {}})
            assert [m["type"] for m in _until(ws, "library")] == ["library"]
            assert [m["type"] for m in _queued_fence(ws)] == ["error"]
            assert quiet_env.starts == 0

            ws.send_json({"type": "action", "payload": {"kind": "resume"}})  # Continue
            got = _until(ws, "step.started")
            types = [m["type"] for m in got]
            assert "lesson.ready" in types
            got += _until(ws, "video.seek")  # start_step seeks after step.started
            got += _queued_fence(ws)  # everything the Continue sent (it ran before the fence in the queue)
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
    main, eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            assert ws.receive_json()["type"] == "engine.hello"
            assert ws.receive_json()["type"] == "status"
            ws.send_json({"type": "library.list", "payload": {}})
            assert [m["type"] for m in _until(ws, "library")] == ["library"]
            assert eng.resumer.pending_offer() is None  # the handler sends a card only for an offer
            ws.send_json({"type": "library.list", "payload": {}})  # a second ask: nothing came between the two
            assert [m["type"] for m in _until(ws, "library")] == ["library"]
            assert [m["type"] for m in _queued_fence(ws)] == ["error"]


def test_a_closed_offer_is_never_sent_again_in_this_engine_run(quiet_env, monkeypatch):
    from fastapi.testclient import TestClient

    _save_unended_video_lesson(monkeypatch)
    main, eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            _until(ws, "status")
            ws.send_json({"type": "library.list", "payload": {}})
            _until(ws, "library")
            card = _until(ws, "card")[-1]["payload"]
            assert card["kind"] == "resume"
            ws.send_json({"type": "card.closed", "payload": {"title": card["title"], "kind": "resume", "by": "user"}})
            _queued_fence(ws)
        with client.websocket_connect("/") as ws:  # a new connection (the app relaunched): still closed
            _until(ws, "status")
            ws.send_json({"type": "library.list", "payload": {}})
            assert [m["type"] for m in _until(ws, "library")] == ["library"]
            assert [m["type"] for m in _queued_fence(ws)] == ["error"]
    assert eng.resumer.pending_offer() is not None  # the save itself stays: the library's Continue row


def test_a_new_connection_gets_the_unanswered_offer_once(quiet_env, monkeypatch):
    from fastapi.testclient import TestClient

    _save_unended_video_lesson(monkeypatch)
    main, eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client:
        for _ in range(2):  # neither answered nor closed (e.g. the app quit with it up): each app run sees it once
            with client.websocket_connect("/") as ws:
                _until(ws, "status")
                got: list[dict] = []
                for _n in range(2):
                    ws.send_json({"type": "library.list", "payload": {}})
                    got += _until(ws, "library")
                got += _queued_fence(ws)
                assert [m["payload"]["kind"] for m in got if m["type"] == "card"] == ["resume"]
    assert eng._offered_to == set()  # each closed socket is forgotten


def test_answering_the_offer_with_start_new_stops_it(quiet_env, monkeypatch):
    from fastapi.testclient import TestClient

    _save_unended_video_lesson(monkeypatch)
    main, eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            _until(ws, "status")
            ws.send_json({"type": "library.list", "payload": {}})
            _until(ws, "card")
            ws.send_json({"type": "action", "payload": {"kind": "end_lesson"}})  # "Start a new lesson"
            _queued_fence(ws)
        with client.websocket_connect("/") as ws:
            _until(ws, "status")
            ws.send_json({"type": "library.list", "payload": {}})
            _until(ws, "library")
            assert not [m for m in _queued_fence(ws) if m["type"] == "card"]


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


def _connect_and_ask(client) -> None:
    with client.websocket_connect("/") as ws:
        _until(ws, "status")
        ws.send_json({"type": "action", "payload": {"kind": "start"}})  # a learner ask (no lesson yet: a no-op)
        _queued_fence(ws)  # it ran


def test_a_quick_reconnect_mid_build_keeps_the_learner_ask(quiet_env, monkeypatch):
    """A Wi-Fi / WS blip between the learner's ask and lesson.ready: VS Code still opens under "Before you start"."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ORCH_RESUME_AFTER_S", "30")
    main, eng, ws_rec, _ = _engine(monkeypatch)
    with TestClient(main.app) as client:
        _connect_and_ask(client)
        assert eng.session.learner_asked is True
        with client.websocket_connect("/") as ws:  # back 0 s later: the same app run
            _until(ws, "status")
            assert eng.session.learner_asked is True

            async def ready() -> None:
                await eng.session.load_graph(_sheet_lesson())
                await eng.session.drain()

            client.portal.call(ready)
            assert eng.session.awaiting_start  # the sheet is up (an app is connected)
            assert ws_rec.opens and ws_rec.opens[0]["full"] is True  # and VS Code opened under it, as after a learn


def test_a_new_app_run_asks_again(quiet_env, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ORCH_RESUME_AFTER_S", "0")  # every reconnect counts as the app having been away
    main, eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client:
        _connect_and_ask(client)
        assert eng.session.learner_asked is True
        with client.websocket_connect("/") as ws:
            _until(ws, "status")
            assert eng.session.learner_asked is False


def test_returning_app_never_gets_an_old_preflight_card(quiet_env, tmp_path):
    s, _, _ = _held_session(tmp_path, asked=True)
    s.pending_pick = {"url": "https://example.com/v", "row": {}, "card": {"kind": "preflight", "title": "Check"}}
    s.phase = "preflight"
    assert ("card", s.pending_pick["card"]) in s.snapshot()  # a quick reconnect: the card is still up
    assert s.snapshot(returning=True) == [("status", {"state": "idle"})]  # the app came back: never replayed
    assert json.dumps(s.snapshot()) and ("card", s.pending_pick["card"]) not in s.snapshot()  # and it stays unsent
    assert s.pending_pick is not None  # the pick is kept: that run's card can still press Build


def test_build_still_works_after_the_app_came_back_with_its_card_still_up(quiet_env, tmp_path):
    """Sleep / wake or a Wi-Fi drop (> ORCH_RESUME_AFTER_S): the same app run still shows its preflight card. Its
    Build must still build the picked video, not do nothing."""
    s, _, _ = _held_session(tmp_path, asked=True)
    built: list = []

    async def run_build(url, goal, video_meta=None, **_k):
        built.append(url)

    s._run_build = run_build
    s.pending_pick = {"url": "https://example.com/v", "row": {}, "card": {"kind": "preflight", "title": "Check"}}
    s.phase = "preflight"
    assert s.snapshot(returning=True) == [("status", {"state": "idle"})]

    async def go():
        await s.action("build")
        await asyncio.sleep(0.05)
        await s.drain()

    asyncio.run(go())
    assert built == ["https://example.com/v"] and s.pending_pick is None


def test_a_late_preflight_card_after_a_return_is_shown_again_on_a_quick_reconnect(quiet_env, tmp_path):
    s, _, _ = _held_session(tmp_path, asked=True)
    pick = {"url": "https://example.com/v", "row": {}, "card": {"kind": "preflight", "title": "Old"}}
    s.pending_pick, s.phase = pick, "preflight"
    s.snapshot(returning=True)
    s.m.preflight_card = lambda res: {"kind": "preflight", "title": "New"}

    async def go():
        await s._show_preflight(pick, {"items": []})

    asyncio.run(go())
    assert ("card", {"kind": "preflight", "title": "New"}) in s.snapshot()  # a card sent this run: shown again
