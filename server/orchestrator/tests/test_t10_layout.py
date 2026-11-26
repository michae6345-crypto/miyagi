"""Test 10 judge review: (1) the lesson's VS Code window starts below Miyagi's step pill and settings gear (they sat
on its title bar, y 40-75 pt on a 1728x1117 display), in the video lesson's left layout and the full-screen one; (2) an
off-track box is placed from a fresh screen read (a repeat warning's box went to y=861 from an older read, then jumped
454 pt to where the line was), and none goes out for a line that isn't on screen; (3) Build -> VS Code: no "Miyagi is
in front" grace right after the learner's own Build click, and a lesson built before opens VS Code alongside the setup
check (it took 4.7 s)."""

from __future__ import annotations

import asyncio
import time

from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.test_session import Rig, run
from server.workspace import editor as E
from server.workspace.tests.test_editor import CURSOR, FakeAX, screen

# ---------------------------------------------------------------------------------------------- (1) window rect

VISIBLE = (0, 38, 1728, 1079)  # a 1728x1117 display's visible frame (menu bar 38 pt)
PILL_BOTTOM = 75  # the step pill / gear: y 40-75 pt


def test_pill_clearance_is_on_by_default_and_named():
    assert E.PILL_CLEARANCE >= 44 - 0.5
    x, y, w, h = E.below_pill(VISIBLE)
    assert (x, w) == (0, 1728) and y >= PILL_BOTTOM and y == 38 + E.PILL_CLEARANCE
    assert y + h == 38 + 1079  # the bottom stays where it was: only the top moves down


def test_left_layout_starts_below_the_pill_and_ends_above_the_bar(monkeypatch):
    monkeypatch.setattr(E, "find_pid", lambda name, bundle=None: 222)
    monkeypatch.setattr(E, "lesson_screen", lambda: screen())  # no notch: the island sits below the menu bar
    ax, rep = FakeAX(fullscreen_prev=False, fullscreen_editor=False), {}
    E.arrange(CURSOR, None, rep, ax=ax, sleep=lambda s: None)
    _, _, x, y, w, h = ax.log[-1]
    assert (x, w) == (0, 1037) and y == 38 + E.PILL_CLEARANCE > PILL_BOTTOM
    assert y + h == 38 + 1079 - E.BAR_CLEARANCE  # down to the Dock (the bottom bar was retired Nov 21: 0)
    assert rep["frame"] == [0, round(y), 1037, round(h)]


def test_full_screen_layout_starts_below_the_pill(monkeypatch):
    monkeypatch.setattr(E, "find_pid", lambda name, bundle=None: 222)
    monkeypatch.setattr(E, "NATIVE_FULLSCREEN", False)
    monkeypatch.setattr(E, "lesson_screen", lambda: screen())
    ax, rep = FakeAX(fullscreen_editor=False), {}
    E.make_fullscreen(CURSOR, rep, ax=ax, sleep=lambda s: None)
    frames = [e for e in ax.log if e[0] == "frame"]
    assert frames and rep["fullscreen"] == "done (maximized)"
    _, _, x, y, w, h = frames[0]
    assert x == 0 and y == 38 + E.PILL_CLEARANCE > PILL_BOTTOM and w == 1728 - E.drawer_reserve()
    assert y + h == 38 + 1079 - E.BAR_CLEARANCE


def test_pill_clearance_env_override(monkeypatch):
    monkeypatch.setattr(E, "PILL_CLEARANCE", 0.0)  # MIYAGI_PILL_CLEARANCE=0: right under the menu bar
    assert E.below_pill(VISIBLE) == VISIBLE
    monkeypatch.setattr(E, "PILL_CLEARANCE", 5000.0)  # never under half the height
    assert E.below_pill(VISIBLE)[3] >= 1079 * 0.5 - 1


def test_pill_clearance_reads_the_env(monkeypatch):
    import importlib

    monkeypatch.setenv("MIYAGI_PILL_CLEARANCE", "60")
    try:
        assert importlib.reload(E).PILL_CLEARANCE == 60.0
    finally:
        monkeypatch.delenv("MIYAGI_PILL_CLEARANCE")
        importlib.reload(E)


# ---------------------------------------------------------------------------------------------- (2) fresh box

LINE = "model.compile(optimizer='adam',"


class LaggingScreen(FakeScreen):
    """latest() is an older read until fresh() reads the screen again (the reader's _fresh_obs)."""

    def __init__(self, old: list[str], now: list[str]) -> None:
        super().__init__()
        self.text = {"Code": old}
        self.now = now
        self.reads: list[float] = []

    def fresh(self, max_age: float = 1.0):
        self.reads.append(max_age)
        self.text = {"Code": self.now}
        return self.text


def _rows(at: int) -> list[str]:
    return [f"# filler {i}" for i in range(at)] + [LINE, "    loss='sparse_categorical_crossentropy')"]


def _offtrack(tmp_path, screen: LaggingScreen, full: dict) -> tuple[Rig, list[dict]]:
    rig = Rig(tmp_path, screen=screen)

    async def go():
        await rig.start_lesson()
        await rig.settle()
        m = rig.mark()
        await rig.s._offtrack_spot(rig.s.step, full)
        await rig.settle()
        return [e["payload"] for e in rig.since(m) if e["type"] == "spotlight" and e["payload"].get("rect")]

    return rig, run(go())


def test_offtrack_box_is_placed_from_a_fresh_read_not_the_coachs(tmp_path):
    """Test 10 step 6: the coach's target (its own, older read) said y=861; the screen now shows the line elsewhere."""
    screen = LaggingScreen(old=_rows(38), now=_rows(15))
    full = {"title": "Run training cell, then add next", "body": "...",
            "targets": [{"rect": [321.5, 861.0, 190.9, 12.6], "text": LINE, "label": "Run training cell"}]}
    rig, spots = _offtrack(tmp_path, screen, full)
    assert screen.reads and screen.reads[0] <= 1.0  # a read at most ~1 s old before the box went out
    assert spots, "the line is on screen: it is boxed"
    assert spots[0]["rect"]["y"] == 100.0 + 20 * 15  # where the fresh read has it, never y=861
    assert all(s["rect"]["y"] != 861.0 for s in spots)


def test_offtrack_box_never_goes_out_for_a_line_that_is_not_on_screen(tmp_path):
    screen = LaggingScreen(old=_rows(38), now=["# the plot cell", "plt.show()"])
    full = {"title": "Run training cell, then add next", "body": "...",
            "targets": [{"rect": [321.5, 861.0, 190.9, 12.6], "text": LINE, "label": "Run training cell"}]}
    _, spots = _offtrack(tmp_path, screen, full)
    assert not [s for s in spots if s.get("matched") == LINE or s["rect"]["y"] == 861.0]


# ---------------------------------------------------------------------------------------------- (3) Build -> VS Code

def _open_rig(tmp_path, monkeypatch, req_s: float = 0.0):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import workspace as wsmod

    def req(graph, folder):
        time.sleep(req_s)
        asked.append({"requirements_done": True})
        return None

    monkeypatch.setattr(wsmod, "requirements", req)
    asked: list[dict] = []

    class Rec(wsmod.Workspace):
        def open(self, workdir, force=False, full=False, explicit=False, **k):
            asked.append({"full": full, "explicit": explicit, **k})
            return super().open(workdir, force, full, explicit, **k)

    (tmp_path / "pinn_convection.py").write_text("import torch\n", encoding="utf-8")
    rig = Rig(tmp_path)
    rig.s.workspace = Rec(enabled=True, runner=lambda argv: True)
    return rig, asked, wsmod


def test_open_right_after_the_build_click_skips_the_miyagi_grace(tmp_path, monkeypatch):
    rig, asked, wsmod = _open_rig(tmp_path, monkeypatch)
    rig.s._build_t0 = rig.s.clock()  # the learner just clicked Build
    since = {"key": 30.0, "click": 0.1}  # the Build click, no keystroke

    class Inputs:
        def seconds_since_key(self):
            return since["key"]

        def seconds_since_input(self):
            return min(since.values())

    rig.s.inputs = Inputs()

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.settle()

    run(go())
    auto = [a for a in asked if "explicit" in a and not a["explicit"]]
    assert auto and auto[0]["miyagi_wait_s"] == 0.0
    busy = auto[0]["busy"]  # the typing guard rides along, keys only (the Build click itself isn't typing)
    assert busy() is False
    since["key"] = 0.1  # a keystroke
    assert busy() is True


def test_open_long_after_the_build_click_keeps_the_grace(tmp_path, monkeypatch):
    rig, asked, wsmod = _open_rig(tmp_path, monkeypatch)
    rig.s._build_t0 = rig.s.clock() - 60

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.settle()

    run(go())
    auto = [a for a in asked if "explicit" in a and not a["explicit"]]
    assert auto and auto[0]["miyagi_wait_s"] == wsmod.VIDEO_MIYAGI_WAIT_S


def test_lesson_built_before_opens_vscode_alongside_the_setup_check(tmp_path, monkeypatch):
    rig, asked, _ = _open_rig(tmp_path, monkeypatch, req_s=0.4)
    rig.s._build_t0 = rig.s.clock()
    rig.s._build_cached = True  # E2's lesson cache answered the Build

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.settle()

    run(go())
    order = ["open" if "explicit" in a else "req" for a in asked]
    assert order[:2] == ["open", "req"], asked  # VS Code did not wait for the setup check
    assert order.count("open") == 1  # one open, not a second after the check


def test_fresh_build_still_waits_for_the_setup_check(tmp_path, monkeypatch):
    rig, asked, _ = _open_rig(tmp_path, monkeypatch, req_s=0.2)

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.settle()

    run(go())
    order = ["open" if "explicit" in a else "req" for a in asked]
    assert order[:2] == ["req", "open"], asked
