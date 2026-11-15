"""server.workspace.vscode_ext: the engine's client for the VS Code companion extension (vscode-ext/).

Offline only: fake extension windows are local HTTP servers; the end-to-end test runs the real extension.js under
node with a stubbed `vscode` module. No VS Code, no network, no API calls."""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from server.workspace import vscode_ext as vx

REPO = Path(__file__).resolve().parents[3]


class FakeWindow:
    """One VS Code window's extension: answers /state and records POSTs."""

    def __init__(self, state: dict, delay: float = 0.0, reply: dict | None = None, status: int = 200):
        self.state, self.delay, self.reply, self.status = state, delay, reply, status
        self.requests: list[tuple[str, str, dict | None, dict]] = []
        win = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                win.requests.append(("GET", self.path, None, dict(self.headers)))
                time.sleep(win.delay)
                if self.path == "/state":
                    return self._send(200, {**win.state, "port": win.port, "app": "vscode", "ok": True})
                if self.path.startswith("/text"):
                    return self._send(200, {"ok": True, "text": "unsaved", "dirty": True, "path": self.path})
                return self._send(404, {"ok": False, "error": "no_route"})

            def do_POST(self):
                n = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                win.requests.append(("POST", self.path, body, dict(self.headers)))
                time.sleep(win.delay)
                return self._send(win.status, win.reply or {"ok": True, "route": self.path})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def posts(self, path=None):
        return [(p, b) for m, p, b, _ in self.requests if m == "POST" and (path is None or p == path)]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def make_windows(monkeypatch):
    made: list[FakeWindow] = []

    def make(*states, **kw):
        wins = [FakeWindow(s, **kw) for s in states]
        made.extend(wins)
        # a closed port first: real scans hit ports with nothing listening
        monkeypatch.setenv("MIYAGI_VSCODE_PORTS", ",".join([str(free_port())] + [str(w.port) for w in made]))
        return wins

    yield make
    for w in made:
        w.close()


@pytest.fixture(autouse=True)
def _events():
    vx.reset_events()
    yield
    vx.reset_events()


def test_ports_env(monkeypatch):
    monkeypatch.delenv("MIYAGI_VSCODE_PORTS", raising=False)
    assert vx.ports() == list(range(8791, 8800))
    monkeypatch.setenv("MIYAGI_VSCODE_PORTS", "9001-9003, 9010,bad,9001")
    assert vx.ports() == [9001, 9002, 9003, 9010]


def test_none_when_extension_not_running(monkeypatch):
    monkeypatch.setenv("MIYAGI_VSCODE_PORTS", ",".join(str(free_port()) for _ in range(3)))
    t0 = time.monotonic()
    assert vx.windows() == []
    assert vx.available() is False
    assert vx.state() is None
    assert vx.open_file("/tmp/x.py", 3) is None
    assert vx.highlight("/tmp/x.py", 1) is None
    assert vx.run_in_terminal("ls") is None
    assert vx.apply("/tmp/x.py", "x") is None
    assert vx.buffer_text() is None
    assert vx.clear_highlight() is None
    assert vx.last_command() is None
    assert vx.active_editor() is None
    assert time.monotonic() - t0 < 1.0  # refused connections fail fast


def test_hung_window_times_out_within_300ms(make_windows):
    make_windows({"windowFocused": True, "folders": []}, delay=1.5)
    t0 = time.monotonic()
    assert vx.state() is None
    assert time.monotonic() - t0 < 0.45


def test_picks_focused_then_last_focused_window(make_windows):
    a, b, c = make_windows(
        {"windowFocused": False, "lastFocusedAt": 100, "folders": ["/lessons/old"]},
        {"windowFocused": True, "lastFocusedAt": 50, "folders": ["/lessons/new"]},
        {"windowFocused": False, "lastFocusedAt": 300, "folders": ["/elsewhere"]},
    )
    assert [w["port"] for w in vx.windows()] == [b.port, c.port, a.port]
    assert vx.state()["port"] == b.port
    b.state["windowFocused"] = False
    assert vx.state()["port"] == c.port


def test_routes_to_the_window_that_has_the_file(make_windows, tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir(), new.mkdir()
    w_old, w_new = make_windows({"windowFocused": True, "folders": [str(old)]},
                                {"windowFocused": False, "folders": [str(new)]})
    r = vx.open_file(new / "calculator.py", 12)
    assert r == {"ok": True, "route": "/open"}
    assert w_new.posts("/open") == [("/open", {"file": str(new / "calculator.py"), "line": 12, "preserveFocus": False})]
    assert w_old.posts() == []
    # relative file + folder: resolved against the folder, routed there
    vx.highlight("calculator.py", 3, 5, folder=new)
    assert w_new.posts("/highlight")[-1][1] == {"file": str(new / "calculator.py"), "startLine": 3, "endLine": 5,
                                                "focus": False}
    # a file in no window's folder: the focused window (never a new one)
    vx.open_file("/somewhere/else.py")
    assert w_old.posts("/open")[-1][1]["file"] == "/somewhere/else.py"
    # state(folder=...) picks by folder, including a lesson folder inside an opened parent
    assert vx.state(folder=new)["port"] == w_new.port
    assert vx.state(folder=old / "sub")["port"] == w_old.port


def test_action_payloads(make_windows, tmp_path):
    (w,) = make_windows({"windowFocused": True, "folders": [str(tmp_path)]})
    f = tmp_path / "calculator.py"
    vx.run_in_terminal("python calculator.py", cwd=tmp_path)
    vx.show_terminal()
    vx.hide_terminal()
    vx.apply(f, "x = 1\n", save=False)
    vx.replace_line(f, "return a - b", "return a + b")
    vx.diff(f, "y\n", title="fix")
    vx.clear_highlight()
    posts = w.posts()
    assert posts == [
        ("/terminal/run", {"cmd": "python calculator.py", "preserveFocus": False, "cwd": str(tmp_path)}),
        ("/terminal", {"show": True, "preserveFocus": False}),
        ("/terminal", {"show": False}),
        ("/apply", {"file": str(f), "save": False, "reveal": True, "newText": "x = 1\n"}),
        ("/apply", {"file": str(f), "save": True, "reveal": True,
                    "edits": [{"find": "return a - b", "replace": "return a + b"}]}),
        ("/diff", {"file": str(f), "newText": "y\n", "title": "fix"}),
        ("/highlight", {"clear": True}),
    ]
    # the engine never looks like a browser to the extension's guard
    for _, _, _, headers in w.requests:
        assert "Origin" not in headers and "Sec-Fetch-Site" not in headers
        assert headers["Host"] == f"127.0.0.1:{w.port}"
    with pytest.raises(ValueError):
        vx.apply(f)
    txt = vx.buffer_text(f)
    assert txt["text"] == "unsaved" and "calculator.py" in txt["path"]


def test_error_answers_are_returned_not_none(make_windows):
    make_windows({"windowFocused": True, "folders": []}, reply={"ok": False, "error": "not_found"}, status=404)
    assert vx.open_file("/nope.py") == {"ok": False, "error": "not_found"}


def test_active_editor_matches_active_py_shape(make_windows, tmp_path, monkeypatch):
    lessons = tmp_path / "lessons"
    lesson = lessons / "python-calculator-e430dc"
    lesson.mkdir(parents=True)
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(lessons))
    make_windows({"windowFocused": True, "folders": [str(lesson)], "file": str(lesson / "calculator.py"),
                  "dirty": True, "cursor": {"line": 3, "column": 1}, "languageId": "python"})
    a = vx.active_editor()
    assert a["folder"] == str(lesson) and a["folder_name"] == lesson.name
    assert a["file"] == "calculator.py" and a["path"] == str(lesson / "calculator.py")
    assert a["dirty"] is True and a["miyagi_lesson"] is True and a["source"] == "extension"
    assert a["cursor"] == {"line": 3, "column": 1}
    from server.workspace import active as A

    assert A.wrong_folder(lesson, active=a) is None  # plugs into S2's detector as `active=`


def test_record_event_and_subscribers():
    seen = []
    unsub = vx.subscribe(seen.append)
    vx.record_event({"type": "save", "file": "/x/calculator.py"})
    vx.record_event({"type": "command_end", "command": {"exitCode": 1}})
    assert [e["type"] for e in seen] == ["save", "command_end"]
    assert vx.last_event("save")["file"] == "/x/calculator.py"
    assert vx.last_event()["type"] == "command_end"
    assert [e["seq"] for e in vx.recent_events(since=1)] == [2]
    unsub()
    vx.record_event({"type": "focus"})
    assert len(seen) == 2


def test_scroll_events_never_push_a_run_out_of_the_history():
    """Audit (Nov 15): companion 0.0.5 posts `visible` on every scroll. They reach the subscribers (box_follow) and
    last_event, but stay out of the 200-event history, so a long scroll never evicts the command_end that Run it for
    me / the run row read back with recent_events()."""
    vx.reset_events()
    seen = []
    unsub = vx.subscribe(seen.append)
    end = vx.record_event({"type": "command_end", "command": {"exitCode": 0}})
    for i in range(500):
        vx.record_event({"type": "visible", "visibleRanges": [{"startLine": i, "endLine": i + 30}]})
    unsub()
    assert any(e["seq"] == end["seq"] for e in vx.recent_events(end["seq"] - 1))
    assert vx.last_event("visible")["visibleRanges"][0]["startLine"] == 499
    assert sum(1 for e in seen if e["type"] == "visible") == 500


def test_async_subscriber_runs_on_the_loop():
    got = []

    async def cb(ev):
        got.append(ev["type"])

    async def main():
        vx.subscribe(cb)
        vx.record_event({"type": "editor"})
        await asyncio.sleep(0)

    asyncio.run(main())
    assert got == ["editor"]


def test_engine_route_records_events():
    from fastapi.testclient import TestClient

    from server.orchestrator import main

    client = TestClient(main.app)  # no `with`: the lifespan (screen reader, watcher) doesn't start
    r = client.post("/vscode/event", json={"type": "save", "file": "/x/calculator.py", "port": 8791})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert vx.last_event("save")["port"] == 8791


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_end_to_end_against_the_real_extension(tmp_path, monkeypatch):
    """The real vscode-ext/extension.js (stubbed `vscode`) driven by this client: shapes match on both sides."""
    (tmp_path / "calculator.py").write_text('"""A simple Python calculator."""\n\n# Step 1\n')
    proc = subprocess.Popen(["node", str(REPO / "vscode-ext" / "test" / "serve-fake.js"), str(tmp_path)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        info = json.loads(proc.stdout.readline())
        monkeypatch.setenv("MIYAGI_VSCODE_PORTS", f"{free_port()},{info['port']}")
        folder = Path(info["dir"])
        st = vx.state()
        assert st["folders"] == [str(folder)] and st["file"] is None and st["windowFocused"] is True

        assert vx.open_file(folder / "calculator.py", 3)["line"] == 3
        st = vx.state(folder=folder)
        assert st["file"] == str(folder / "calculator.py") and st["cursor"] == {"line": 3, "column": 1}
        assert vx.active_editor()["path"] == str(folder / "calculator.py")

        assert vx.highlight(folder / "calculator.py", 1, 2) == {"ok": True, "file": str(folder / "calculator.py"),
                                                                 "startLine": 1, "endLine": 2}
        assert vx.state()["highlight"]["endLine"] == 2
        assert vx.clear_highlight() == {"ok": True, "cleared": 1}

        r = vx.apply(folder / "calculator.py", edits=[{"startLine": 3, "text": "def add(a, b):\n    return a - b"}])
        assert r["ok"] and r["saved"] is True
        assert vx.replace_line(folder / "calculator.py", "return a - b", "return a + b")["saved"] is True
        assert (folder / "calculator.py").read_text() == '"""A simple Python calculator."""\n\ndef add(a, b):\n    return a + b\n'
        assert vx.buffer_text(folder / "calculator.py")["dirty"] is False

        r = vx.run_in_terminal("python calculator.py", cwd=folder)
        assert r["ok"] and r["terminal"] == "Miyagi" and r["reportsExitCode"] is True
        deadline = time.monotonic() + 2
        while (cmd := vx.last_command()) is None or cmd["running"]:
            assert time.monotonic() < deadline, cmd
            time.sleep(0.02)
        assert cmd["commandLine"] == "python calculator.py" and cmd["exitCode"] == 0
        assert cmd["outputTail"] == ["ran: python calculator.py"]
        assert vx.state()["terminalOpen"] is True

        assert vx.diff(folder / "calculator.py", "x\n")["ok"] is True
        missing = vx.open_file(folder / "nope.py")
        assert missing == {"ok": False, "error": "not_found"}
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
