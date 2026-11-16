"""A video / generated lesson's VS Code opens within a short grace of lesson.ready, even with Miyagi's player in front
(Michael, Nov 15 7:19: `auto-open ... deferred` held VS Code 30 s, until he left Miyagi). Typing still holds it."""

from __future__ import annotations

import asyncio
import time

from server.orchestrator.tests.test_session import Rig, run
from server.workspace import editor as E
from server.workspace.tests.test_editor import CODE, MIYAGI, fresh, kw, opener  # noqa: F401 - fresh is a fixture


def test_miyagi_in_front_holds_only_the_grace_not_until_focus_leaves(tmp_path, fresh):  # noqa: F811
    calls, run_ = opener(tmp_path)
    t0 = time.monotonic()
    rep = E.open_lesson_editor(tmp_path, lesson_id="V", runner=run_, focus=lambda: MIYAGI, busy=lambda: False,
                               background=False, miyagi_wait_s=0.05, wait_s=5, sleep=lambda s: time.sleep(0.01), **kw())
    assert rep["opened"] and len([c for c in calls if c[0] == "/usr/local/bin/code"]) == 1  # Miyagi never left
    assert time.monotonic() - t0 < 2


def test_typing_still_holds_the_open(tmp_path, fresh):  # noqa: F811
    calls, run_ = opener(tmp_path)
    rep = E.open_lesson_editor(tmp_path, lesson_id="V", runner=run_, focus=lambda: MIYAGI, busy=lambda: True,
                               background=False, miyagi_wait_s=0.0, wait_s=0.05, sleep=lambda s: time.sleep(0.01), **kw())
    assert rep.get("gave_up") and calls == []  # typing in the launcher / ask box: never stolen mid-keystroke


def test_workspace_open_passes_the_grace_through(tmp_path, monkeypatch):
    from server.orchestrator import workspace as wsmod

    seen = []

    class Ed:
        @staticmethod
        def open_lesson_editor(folder, file=None, **k):
            seen.append(k)
            return {"opened": True}

    class WS:
        editor = Ed

        @staticmethod
        def open_file_for(p):
            return None

    monkeypatch.setattr(wsmod, "_s2", lambda: WS)
    monkeypatch.setattr(wsmod, "python_terminal_settings", lambda wd: None)
    ws = wsmod.Workspace(enabled=True)  # the real runner: holds go through
    ws.open(str(tmp_path), True, miyagi_wait_s=1.5)
    ws.open(str(tmp_path), True, True)  # "Just teach me": its own grace, full screen
    ws.open(str(tmp_path), True)  # no grace asked: until the learner leaves Miyagi (unchanged)
    assert [(k["miyagi_wait_s"], k["fullscreen"]) for k in seen] == [
        (1.5, False), (wsmod.LESSON_MIYAGI_WAIT_S, True), (None, False)]


def test_video_lesson_auto_open_asks_for_the_short_grace(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import workspace as wsmod

    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: None)
    asked = []

    class Rec(wsmod.Workspace):
        def open(self, workdir, force=False, full=False, explicit=False, **k):
            asked.append({"full": full, "explicit": explicit, **k})
            return super().open(workdir, force, full, explicit, **k)

    (tmp_path / "pinn_convection.py").write_text("import torch\n")
    rig = Rig(tmp_path)
    rig.s.workspace = Rec(enabled=True, runner=lambda argv: True)

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.settle()

    run(go())
    auto = [a for a in asked if not a["explicit"]]
    assert auto and auto[0]["miyagi_wait_s"] == wsmod.VIDEO_MIYAGI_WAIT_S <= 3 and auto[0]["full"] is False
    assert callable(auto[0]["busy"])  # the typing guard still rides along
