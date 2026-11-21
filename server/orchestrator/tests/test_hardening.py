"""ROADMAP 5.3, engine hardening (offline): loopback bind, the per-launch token on writes and the WebSocket, dev routes
off in release builds, the token file for the companion / `tut run`, and the companion link token."""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server import engine_token
from server.orchestrator import main
from server.workspace import vscode_ext

LOCAL = ("127.0.0.1", 50000)  # a loopback client (TestClient's default "testclient" is not an address)
BASE = "http://127.0.0.1"
TOKEN = "per-launch-token-abc123"


@pytest.fixture
def engine(monkeypatch, tmp_path):
    """main.app with no lifespan (no screen reader, no watcher) and the session's writes stubbed."""
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv(main.DEBUG_ENV, raising=False)
    monkeypatch.delenv("DEMO", raising=False)
    main.engine.recorder.enabled = False
    return main


def test_dev_routes_are_404_unless_asked_for(engine, monkeypatch):
    c = TestClient(engine.app, base_url=BASE, client=LOCAL)
    for method, path in (("POST", "/debug/pass"), ("POST", "/debug/goto/3"), ("POST", "/debug/lesson"),
                         ("GET", "/demo/runs"), ("POST", "/demo/replay"), ("GET", "/events"),
                         ("GET", "/events?since=0")):
        r = c.request(method, path)
        assert r.status_code == 404, (method, path, r.status_code)
    assert c.get("/health").status_code == 200  # everything else is unchanged
    monkeypatch.setenv(main.DEBUG_ENV, "1")
    assert c.get("/demo/runs").status_code == 200
    assert c.get("/events").status_code == 200
    monkeypatch.delenv(main.DEBUG_ENV)
    monkeypatch.setenv("DEMO", "1")  # a DEMO engine (never the app's: localEngine.ts refuses DEMO=1)
    assert c.get("/demo/runs").status_code == 200


def test_no_token_configured_keeps_loopback_open(engine, monkeypatch):
    """An engine started by hand (no MIYAGI_ENGINE_TOKEN): curl -X POST localhost:8787/end and old companions work."""
    monkeypatch.setattr(main, "ENGINE_TOKEN", None)
    c = TestClient(engine.app, base_url=BASE, client=LOCAL)
    assert c.post("/end").status_code == 200
    assert c.post("/vscode/event", json={"type": "focus", "focused": True}).status_code == 200


def test_token_required_on_every_write_from_this_mac_too(engine, monkeypatch):
    monkeypatch.setattr(main, "ENGINE_TOKEN", TOKEN)
    c = TestClient(engine.app, base_url=BASE, client=LOCAL)
    writes = [("/ingest", [{"kind": "run_started", "run_id": "x"}]), ("/vscode/event", {"type": "focus"}),
              ("/end", None), ("/stage/next", None)]
    for path, body in writes:
        r = c.post(path, json=body) if body is not None else c.post(path)
        assert r.status_code == 403 and r.json()["error"] == main.REFUSED_TOKEN, path
        r = c.post(path, json=body, headers={"X-Miyagi-Token": "wrong"}) if body is not None else \
            c.post(path, headers={"X-Miyagi-Token": "wrong"})
        assert r.status_code == 403, path
    ok = c.post("/ingest", json=[{"kind": "run_started", "run_id": "x"}], headers={"X-Miyagi-Token": TOKEN})
    assert ok.status_code == 200 and ok.json()["accepted"] == 1
    assert c.post("/end", headers={"X-Miyagi-Token": TOKEN}).status_code == 200
    # reads from this Mac need none (the app polls /health; /library and /progress feed Home)
    for path in ("/health", "/state", "/library"):
        assert c.get(path).status_code == 200, path
    # another machine needs it on reads too
    lan = TestClient(engine.app, base_url=BASE, client=("192.168.1.20", 50000))
    assert lan.get("/health").status_code == 403
    assert lan.get("/health", headers={"X-Miyagi-Token": TOKEN}).status_code == 200


def test_a_tokenless_companion_is_named_once_in_the_log(engine, monkeypatch, caplog):
    monkeypatch.setattr(main, "ENGINE_TOKEN", TOKEN)
    monkeypatch.setattr(main, "_warned_companion", False)
    c = TestClient(engine.app, base_url=BASE, client=LOCAL)
    with caplog.at_level("WARNING", logger=main.log.name):
        for _ in range(3):
            assert c.post("/vscode/event", json={"type": "save"}).status_code == 403
    lines = [r.getMessage() for r in caplog.records if "/vscode/event" in r.getMessage()]
    assert len(lines) == 1 and "older than 0.0.7" in lines[0]
    assert TOKEN not in caplog.text


def test_websocket_needs_the_token(engine, monkeypatch):
    monkeypatch.setattr(main, "ENGINE_TOKEN", TOKEN)
    with TestClient(engine.app, base_url=BASE, client=LOCAL) as c:
        with pytest.raises(WebSocketDisconnect), c.websocket_connect("ws://127.0.0.1/") as ws:
            ws.receive_json()
        with c.websocket_connect("ws://127.0.0.1/", headers={"X-Miyagi-Token": TOKEN}) as ws:
            assert ws.receive_json()["type"] == "engine.hello"


def _run_engine(monkeypatch, argv: list[str], env_host: str | None) -> dict:
    """main.run() with uvicorn.run stubbed: what it would bind, and the token file while it 'runs'."""
    import uvicorn

    seen: dict = {}

    def fake_run(app, host, port, log_level):
        seen.update(host=host, port=port, file=engine_token.read(port))

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["server.orchestrator.main", *argv])
    if env_host is None:
        monkeypatch.delenv("ENGINE_HOST", raising=False)
    else:
        monkeypatch.setenv("ENGINE_HOST", env_host)
    monkeypatch.setattr(main, "_bind_host", None)
    monkeypatch.setattr(vscode_ext, "_link_token", None)
    main.run()
    return seen


@pytest.mark.parametrize("env_host", [None, "", "  "])
def test_binds_loopback_by_default(monkeypatch, env_host):
    seen = _run_engine(monkeypatch, ["--port", "18787"], env_host)
    assert seen["host"] == "127.0.0.1"


def test_run_publishes_the_token_for_the_companion_and_removes_it(monkeypatch):
    monkeypatch.setattr(main, "ENGINE_TOKEN", None)
    seen = _run_engine(monkeypatch, ["--port", "18788"], None)
    assert seen["file"] and len(seen["file"]) >= 32  # a fresh random token while it ran
    assert vscode_ext.link_token() == seen["file"]  # the engine -> companion calls carry it
    assert engine_token.read(18788) is None  # removed on exit
    p = engine_token.token_dir() / "18788.json"
    assert not p.exists()

    monkeypatch.setattr(main, "ENGINE_TOKEN", TOKEN)  # the app's token is the one published
    seen = _run_engine(monkeypatch, ["--port", "18789"], None)
    assert seen["file"] == TOKEN


def test_token_file_is_private_and_ignored_once_its_engine_is_gone(tmp_path, monkeypatch):
    monkeypatch.setenv(engine_token.DIR_ENV, str(tmp_path / "tok"))
    p = engine_token.write("abc", 9001)
    assert p is not None and oct(p.stat().st_mode & 0o777) == "0o600"
    assert oct(p.parent.stat().st_mode & 0o777) == "0o700"
    assert engine_token.read(9001) == "abc" and engine_token.live_tokens() == ["abc"]
    p.write_text(json.dumps({"token": "stale", "pid": 2 ** 22 + 4321, "port": 9001}))  # a crashed engine's file
    assert engine_token.read(9001) is None and engine_token.live_tokens() == []
    p.write_text(json.dumps({"token": "abc", "pid": os.getpid(), "port": 9001}))
    engine_token.remove("someone-else", 9001)
    assert p.exists()  # not ours: kept
    engine_token.remove("abc", 9001)
    assert not p.exists()


def test_engine_calls_to_the_companion_carry_the_link_token(monkeypatch):
    got: list[str | None] = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            got.append(self.headers.get("X-Miyagi-Token"))
            body = json.dumps({"ok": True, "folders": [], "port": self.server.server_port}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # quiet
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("MIYAGI_VSCODE_PORTS", str(srv.server_port))
        monkeypatch.setattr(vscode_ext, "_link_token", "link-xyz")
        assert vscode_ext._call(srv.server_port, "GET", "/state") is not None
        assert got and got[-1] == "link-xyz"
    finally:
        srv.shutdown()
        srv.server_close()
