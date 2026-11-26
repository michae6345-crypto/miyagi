"""setup.scan / setup.fix through the service (server/ambient/assist.py) and the engine's wiring (capabilities, dispatch
beside the lesson queue). The scan and the install are fakes here; test_project.py covers them on fixture projects."""

from __future__ import annotations

import asyncio

from server.ambient import assist as A
from server.orchestrator.tests.test_launch_contract import _engine, quiet_env  # noqa: F401 - fixture
from shared.contracts.events import AMBIENT_CAPABILITIES, validate_engine_payload

ROW = {"tool": "pandas", "label": "pandas", "kind": "python_package", "why": "requirements.txt lists it", "needed": True,
       "installed": False, "ok": False, "install": {"method": "pip", "command": "pip install pandas"},
       "from": "requirements.txt:3", "setupKind": "package", "actions": ["install", "skip"]}


class FakeScan:
    def __init__(self):
        self.calls = []

    def __call__(self, path, *, req_id=None, quick=False):
        self.calls.append((path, quick))
        base = {**({"reqId": req_id} if req_id else {}), "root": "~/code/weather-app", "name": "weather-app",
                "_path": "/Users/x/code/weather-app", "files": ["requirements.txt"]}
        if quick:
            return {**base, "items": [], "ready": 0, "total": 0, "scanning": True}
        return {**base, "items": [ROW], "ready": 0, "total": 1, "next": "Install pandas into a new .venv in this folder."}


class Wire:
    def __init__(self):
        self.sent = []

    async def __call__(self, type_, payload):
        validate_engine_payload(type_, payload)
        assert not any(k.startswith("_") for k in payload)  # internal keys never go out
        self.sent.append((type_, payload))


def test_scan_sends_a_quick_answer_then_the_report_and_remembers_the_root():
    scan, wire = FakeScan(), Wire()
    a = A.Assist(scan=scan)
    asyncio.run(a.setup_scan(None, wire, {"reqId": "scan-1"}))
    assert [t for t, _ in wire.sent] == ["setup.report", "setup.report"]
    assert wire.sent[0][1]["scanning"] is True and wire.sent[1][1]["items"][0]["from"] == "requirements.txt:3"
    assert a.last_root == "/Users/x/code/weather-app" and scan.calls == [(None, True), (None, False)]


def test_scan_error_answers_once():
    wire = Wire()
    a = A.Assist(scan=lambda path, **kw: {"files": [], "items": [], "ready": 0, "total": 0, "error": "no_project"})
    asyncio.run(a.setup_scan(None, wire, {}))
    assert wire.sent == [("setup.report", {"files": [], "items": [], "ready": 0, "total": 0, "error": "no_project"})]


def test_fix_streams_progress_then_done_then_a_fresh_report():
    wire, calls = Wire(), []

    def fix(tool, root, *, on_line=None, confirmed=None):
        calls.append((tool, root, confirmed))
        on_line("$ pip install pandas")
        on_line("Successfully installed pandas-2.2.3")
        return {"ok": True, "tool": tool, "method": "pip", "version": "2.2.3"}

    a = A.Assist(scan=FakeScan(), fix=fix)
    a.last_root = "/Users/x/code/weather-app"
    asyncio.run(a.setup_fix("pandas", None, wire, {"reqId": "fix-1"}))
    kinds = [(t, p.get("line") or p.get("done")) for t, p in wire.sent]
    assert kinds == [("setup.progress", "Installing…"), ("setup.progress", "$ pip install pandas"),
                     ("setup.progress", "Successfully installed pandas-2.2.3"), ("setup.progress", True),
                     ("setup.report", None)]
    assert wire.sent[3][1] == {"tool": "pandas", "done": True, "ok": True, "version": "2.2.3"}
    assert wire.sent[4][1]["reqId"] == "fix-1" and calls == [("pandas", "/Users/x/code/weather-app", None)]


def test_off_list_package_installs_on_the_rows_second_press_only():
    wire, calls = Wire(), []

    def fix(tool, root, *, on_line=None, confirmed=None):
        calls.append(confirmed)
        if confirmed != "weirdpkg":
            return {"ok": False, "tool": tool, "needs_confirm": True, "package": "weirdpkg",
                    "error": "weirdpkg isn't on miyagi's list of common packages."}
        return {"ok": True, "tool": tool}

    a = A.Assist(scan=FakeScan(), fix=fix)
    asyncio.run(a.setup_fix("weirdpkg", "/p", wire, {}))
    asyncio.run(a.setup_fix("weirdpkg", "/p", wire, {}))
    assert calls == [None, "weirdpkg"]
    dones = [p for t, p in wire.sent if t == "setup.progress" and p.get("done")]
    assert [d["ok"] for d in dones] == [False, True]


def test_fix_without_a_scanned_project_or_twice_at_once():
    wire = Wire()
    a = A.Assist(scan=FakeScan(), fix=lambda *a, **k: {"ok": True})
    asyncio.run(a.setup_fix("pandas", None, wire, {}))
    assert wire.sent[-1][1]["error"] == "Check the project first, then press Install."
    a.installing.add("pandas")
    n = len(wire.sent)
    asyncio.run(a.setup_fix("pandas", "/p", wire, {}))
    assert len(wire.sent) == n  # the repeat press while it installs: ignored


def test_engine_lists_and_answers_the_commands(quiet_env, monkeypatch):
    _main, eng, _ws, calls = _engine(monkeypatch)
    assert eng.assist is not None
    caps = set(eng.capabilities())
    assert set(A.COMMANDS) <= caps and set(A.COMMANDS) <= set(AMBIENT_CAPABILITIES)
    eng.assist.scan = FakeScan()

    class WS:
        def __init__(self):
            self.sent = []

        async def send_json(self, msg):
            validate_engine_payload(msg["type"], msg["payload"])
            self.sent.append(msg)

    ws = WS()
    eng.hub.join(ws)
    asyncio.run(eng.dispatch({"type": "setup.scan", "payload": {"reqId": "s1"}}, ws=ws))
    reports = [m["payload"] for m in ws.sent if m["type"] == "setup.report"]
    assert len(reports) == 2 and reports[1]["reqId"] == "s1" and reports[1]["total"] == 1
    assert calls == []  # no lesson build
    assert set(A.COMMANDS) <= set(_main.ASSIST_INSTANT)  # answered beside the lesson queue
