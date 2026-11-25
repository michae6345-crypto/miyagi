"""server.workspace.blender_ext: the engine's client for the miyagi bridge Blender add-on.

Offline only: fake bridges are in-process HTTP servers on ephemeral ports. No Blender, no network, no API calls."""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from server.workspace import blender_ext as bx
from server.workspace import vscode_ext as vx

DUMP = {"dump": "dump_scene.py 1", "blender": "5.3.0", "file": "x.blend", "objects": [{"name": "Cube"}]}


class FakeBridge:
    """One Blender's bridge: answers /health, /state, /ops and /ui, and records each request's headers."""

    def __init__(self, file: str = "", dump: dict | None = None, status: int = 200, app: str = "blender"):
        self.file, self.dump, self.status, self.app = file, dict(DUMP) if dump is None else dump, status, app
        self.requests: list[tuple[str, dict]] = []
        bridge = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                bridge.requests.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
                path = self.path.split("?")[0]
                base = {"ok": True, "app": bridge.app, "port": bridge.port, "file": bridge.file}
                if path == "/health":
                    return self._send(200, {**base, "name": "miyagi_bridge", "version": "0.1.0", "blender": "5.3.0",
                                            "pid": 1})
                if bridge.status != 200:
                    return self._send(bridge.status, {"ok": False, "error": "busy"})
                if path == "/state":
                    return self._send(200, {**base, "dirty": False, "mode": "OBJECT", "active": "Cube",
                                            "selected": ["Cube"], "frame_current": 1, "dump": bridge.dump})
                if path == "/ops":
                    since = int(self.path.split("since=")[1]) if "since=" in self.path else 0
                    ops = [{"seq": i, "idname": "mesh.primitive_torus_add", "name": "Add Torus", "props": {},
                            "t": 0.0} for i in (1, 2, 3) if i > since]
                    return self._send(200, {"ok": True, "last_seq": 3, "ops": ops})
                if path == "/ui":
                    return self._send(200, {"ok": True, "pixel_size": 2.0, "ui_scale": 1.0, "origin": "bottom-left",
                                            "windows": []})
                if path == "/bad":
                    return self._send(200, b"not json")
                return self._send(404, {"ok": False, "error": "no_route"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def _no_token(monkeypatch, tmp_path):
    """No engine token unless a test sets one: an empty token folder and a fresh vscode_ext cache."""
    monkeypatch.setenv("MIYAGI_ENGINE_TOKEN_DIR", str(tmp_path / "tokens"))
    monkeypatch.setattr(vx, "_link_token", None)
    monkeypatch.setattr(vx, "_disk_token", (0.0, None))


@pytest.fixture
def make_bridges(monkeypatch):
    made: list[FakeBridge] = []

    def make(*specs):
        bridges = [FakeBridge(**s) for s in specs]
        made.extend(bridges)
        # a closed port first: real scans hit ports with nothing listening
        monkeypatch.setenv("MIYAGI_BLENDER_PORTS", ",".join([str(free_port())] + [str(b.port) for b in made]))
        return bridges

    yield make
    for b in made:
        b.close()


# ------------------------------------------------------------------ ports


def test_ports_parse(monkeypatch):
    monkeypatch.delenv("MIYAGI_BLENDER_PORTS", raising=False)
    assert bx.ports() == list(range(8801, 8810))
    monkeypatch.setenv("MIYAGI_BLENDER_PORTS", "8801,8802")
    assert bx.ports() == [8801, 8802]
    monkeypatch.setenv("MIYAGI_BLENDER_PORTS", "9000-9002, nope, 9001, 0")
    assert bx.ports() == [9000, 9001, 9002]


# ------------------------------------------------------------------ acceptance 1: nobody listening


def test_nothing_listening_returns_none_fast(monkeypatch):
    monkeypatch.setenv("MIYAGI_BLENDER_PORTS", str(free_port()))
    for call, empty in ((bx.health, None), (bx.state, None), (bx.live_state, None), (bx.recent_ops, None),
                        (bx.ui_rects, None), (bx.instances, [])):
        t0 = time.monotonic()
        assert call() == empty
        assert time.monotonic() - t0 < 0.5, call.__name__


# ------------------------------------------------------------------ acceptance 2: state / live_state


def test_health_and_instances_in_port_order(make_bridges, tmp_path):
    a, b = make_bridges({"file": str(tmp_path / "a.blend")}, {"file": str(tmp_path / "b.blend")})
    found = bx.instances()
    assert [h["port"] for h in found] == sorted([a.port, b.port], key=bx.ports().index)
    assert bx.health()["port"] == found[0]["port"]
    assert bx.health()["name"] == "miyagi_bridge"


def test_instances_skip_other_apps(make_bridges):
    make_bridges({"app": "vscode"})
    assert bx.instances() == []
    assert bx.health() is None


def test_live_state_returns_the_dump(make_bridges):
    make_bridges({})
    assert bx.live_state() == DUMP
    assert bx.state()["dump"] == DUMP
    assert bx.state()["selected"] == ["Cube"]


def test_live_state_none_on_wrong_tag(make_bridges):
    make_bridges({"dump": {"dump": "dump_scene.py 2", "objects": []}})
    assert bx.state() is not None
    assert bx.live_state() is None


def test_live_state_none_on_missing_dump(make_bridges):
    make_bridges({"dump": {}})
    assert bx.live_state() is None


def test_state_picks_the_instance_with_the_file(make_bridges, tmp_path):
    a_file, b_file = tmp_path / "a.blend", tmp_path / "b.blend"
    a_file.write_bytes(b"")
    b_file.write_bytes(b"")
    _a, b = make_bridges({"file": str(a_file), "dump": {**DUMP, "file": "a.blend"}},
                         {"file": str(b_file), "dump": {**DUMP, "file": "b.blend"}})
    st = bx.state(b_file)
    assert st["port"] == b.port
    assert bx.live_state(str(b_file))["file"] == "b.blend"
    assert bx.live_state(a_file)["file"] == "a.blend"
    assert bx.state(tmp_path / "c.blend") is None
    assert bx.live_state(tmp_path / "c.blend") is None


def test_state_matches_through_symlinks(make_bridges, tmp_path):
    real = tmp_path / "real.blend"
    real.write_bytes(b"")
    link = tmp_path / "link.blend"
    link.symlink_to(real)
    (b,) = make_bridges({"file": str(real)})
    assert bx.state(link)["port"] == b.port


def test_non_2xx_is_none(make_bridges):
    make_bridges({"status": 503})
    assert bx.health() is not None  # /health still answers
    assert bx.state() is None
    assert bx.live_state() is None
    assert bx.recent_ops() is None
    assert bx.ui_rects() is None


def test_bad_json_is_none(make_bridges):
    (b,) = make_bridges({})
    assert bx._call(b.port, "/bad") is None
    assert bx._call(b.port, "/nope") is None


# ------------------------------------------------------------------ ops / ui


def test_recent_ops_since(make_bridges):
    make_bridges({})
    assert [o["seq"] for o in bx.recent_ops()] == [1, 2, 3]
    assert [o["seq"] for o in bx.recent_ops(since=2)] == [3]
    assert bx.recent_ops(since=3) == []


def test_ui_rects(make_bridges):
    make_bridges({})
    ui = bx.ui_rects()
    assert ui["origin"] == "bottom-left" and ui["pixel_size"] == 2.0 and ui["windows"] == []


# ------------------------------------------------------------------ acceptance 3: token header


def test_sends_the_engine_token(make_bridges, monkeypatch):
    (b,) = make_bridges({})
    vx.set_link_token("tok-123")
    try:
        assert vx.link_token() == "tok-123"
        bx.state()
        bx.recent_ops()
        bx.ui_rects()
    finally:
        vx.set_link_token(None)
    assert b.requests
    assert all(h.get("x-miyagi-token") == "tok-123" for _, h in b.requests)


def test_no_token_header_without_a_token(make_bridges):
    (b,) = make_bridges({})
    assert vx.link_token() is None
    bx.state()
    bx.recent_ops()
    assert b.requests
    assert all("x-miyagi-token" not in h for _, h in b.requests)


# ------------------------------------------------------------------ acceptance 9: launch_argv


def test_launch_argv_with_blender():
    assert bx.launch_argv("/tmp/x.blend", blender="/B") == ["/B", "/tmp/x.blend", "--python", str(bx.BRIDGE_START)]


def test_launch_argv_is_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    argv = bx.launch_argv("x.blend", blender="/B")
    assert argv[1] == str(tmp_path / "x.blend")


def test_launch_argv_none_without_blender(monkeypatch):
    fake = types.ModuleType("server.workspace.blender")
    fake.find_blender = lambda: None
    monkeypatch.setitem(sys.modules, "server.workspace.blender", fake)
    assert bx.launch_argv("/tmp/x.blend") is None


def test_launch_argv_uses_the_finder(monkeypatch):
    fake = types.ModuleType("server.workspace.blender")
    fake.find_blender = lambda: "/Apps/Blender"
    monkeypatch.setitem(sys.modules, "server.workspace.blender", fake)
    assert bx.launch_argv("/tmp/x.blend")[0] == "/Apps/Blender"


def test_launch_argv_none_when_finder_breaks(monkeypatch):
    fake = types.ModuleType("server.workspace.blender")

    def boom():
        raise RuntimeError("no")

    fake.find_blender = boom
    monkeypatch.setitem(sys.modules, "server.workspace.blender", fake)
    assert bx.launch_argv("/tmp/x.blend") is None


def test_bridge_start_script_exists():
    assert bx.BRIDGE_START.is_file()
    assert bx.BRIDGE_START.name == "start_bridge.py"
