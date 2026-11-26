"""The lesson window's layout (server/workspace/layout.py) and its single writer in editor.py (Nov 25, MacBook Neo
test): VS Code fits the overlay's display beside the panel, a full-screen or learner-moved window is left alone, and a
burst of follow-ups is one layout, so nothing moves back and forth. The golden cases in shared/layout-cases.json are
checked here and by the app (app/test/screenLayout.test.ts)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.workspace import editor as E
from server.workspace import layout as L

CASES = json.loads((Path(__file__).resolve().parents[3] / "shared" / "layout-cases.json").read_text())["cases"]


def scr(c: dict) -> L.Screen:
    return L.Screen(frame=L.Rect(*c["frame"]), visible=L.Rect(*c["visible"]), safe_top=c["safe_top"])


def by(name: str) -> dict:
    return next(c for c in CASES if c["name"].startswith(name))


# ------------------------------------------------------------------------------------------------ the policy (pure)

@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden_cases(case):
    s = scr(case)
    assert list(L.target(s, "lesson").tuple()) == case["expect"]["lesson"]["editor"]
    assert list(L.panel_rect(s).tuple()) == case["expect"]["lesson"]["panel"]
    assert list(L.target(s, "video").tuple()) == case["expect"]["video"]["editor"]
    # the engine's VS Code and the app's column agree on where VS Code ends
    assert L.video_editor_w(s.visible.w) == case["expect"]["video"]["column_editor_w"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_every_layout_fits_the_screen_and_clears_the_panel(case):
    s, vis = scr(case), scr(case).visible
    lesson, panel = L.target(s, "lesson"), L.panel_rect(s)
    assert vis.x <= lesson.x and lesson.right <= vis.right and vis.y <= lesson.y and lesson.bottom <= vis.bottom
    assert lesson.right + L.PANEL_GAP <= panel.x  # the panel never covers VS Code
    assert lesson.w >= L.MIN_W and lesson.h >= L.MIN_H
    video = L.target(s, "video")
    vplayer, vpanel = (L.Rect(*case["expect"]["video"][k]) for k in ("player", "panel"))
    assert video.right <= vplayer.x and video.right <= vpanel.x  # player and steps drawer in the right column
    assert vplayer.right <= vis.right and vpanel.right <= vis.right and vpanel.bottom <= vis.bottom
    assert video.w >= 0.55 * vis.w or vis.w - video.w == L.VIDEO_MIN_COLUMN


def test_small_mac_without_notch_keeps_the_island_row_and_goes_down_to_the_dock():
    s = scr(by("13-inch 1440x900, no notch, Dock bottom"))
    x, y, w, h = L.target(s, "lesson").tuple()
    assert (x, y) == (0, 25 + L.PILL_CLEARANCE)  # under the menu bar and the island below it
    assert y + h == 25 + 805  # down to the Dock: no 112 pt for the retired bottom bar
    assert w == 1440 - 392  # 360 panel + 16 inset + 16 gap


def test_notch_mac_starts_right_under_the_menu_bar_and_under_the_notch_when_it_auto_hides():
    s = scr(by("14-inch 1512x982, notch, Dock bottom"))
    assert L.target(s, "lesson").y == 38  # the island lives in the notch band: no extra row
    hidden = L.Screen(frame=s.frame, visible=L.Rect(0, 0, 1512, 982), safe_top=32)  # menu bar set to auto-hide
    assert L.target(hidden, "lesson").y == 32  # never under the notch


def test_no_notch_with_the_menu_bar_hidden_still_clears_the_island():
    """#287 review: an auto-hidden menu bar on a Mac without a notch: the app still hangs the island from a 24 pt band
    (#282 belowTop: 24 + the 34 pt pill = 58), so VS Code starts below that, not at 0 + 44."""
    s = scr(by("13-inch 1440x900, no notch, menu bar hidden"))
    assert s.visible.y == 0
    top = L.target(s, "lesson").y
    assert top == L.MENU_BAND + L.PILL_CLEARANCE and top >= 24 + 34
    assert L.target(s, "video").y == top


def test_dock_left_moves_the_editor_right_of_it():
    s = scr(by("13-inch 1440x900, no notch, Dock left"))
    assert L.target(s, "lesson").x == 64 and L.target(s, "video").x == 64


def test_wide_external_display_puts_player_and_drawer_side_by_side():
    c = by("external 2560x1440")
    assert c["expect"]["video"]["stacked"] is False
    assert by("13-inch 1440x900, no notch, Dock bottom")["expect"]["video"]["stacked"] is True


def test_full_screen_is_left_alone():
    s = scr(by("14-inch"))
    p = L.plan(s, editor=L.EditorState(frame=L.Rect(0, 0, 1512, 982), fullscreen=True))
    assert p.action == "leave" and "full screen" in p.reason and p.bounds is None


def test_a_window_the_learner_moved_is_theirs():
    s = scr(by("14-inch"))
    p = L.plan(s, editor=L.EditorState(frame=L.Rect(300, 200, 700, 500), owned=False))
    assert p.action == "leave" and "learner" in p.reason


def test_already_there_is_nothing_to_do():
    s = scr(by("14-inch"))
    want = L.target(s, "lesson")
    p = L.plan(s, editor=L.EditorState(frame=L.Rect(want.x + 2, want.y, want.w - 3, want.h + 1), owned=True))
    assert p.action == "leave" and p.reason == "already there"


def test_first_layout_moves_a_window_from_an_external_display_to_the_overlays_display():
    s = scr(by("13-inch 1440x900, no notch, Dock bottom"))
    on_external = L.Rect(1600, 100, 1200, 800)  # VS Code remembered a frame on the display to the right
    p = L.plan(s, editor=L.EditorState(frame=on_external))
    assert p.action == "set" and p.bounds == L.target(s, "lesson") and p.reason == "first layout"


def test_the_reported_docked_panel_sets_the_edge_but_a_dragged_panel_is_not_chased():
    s = scr(by("13-inch 1440x900, no notch, Dock bottom"))
    docked = L.Rect(1440 - 16 - 400, 52, 400, 600)  # a wider docked panel
    assert L.target(s, "lesson", docked).right == docked.x - L.PANEL_GAP
    dragged = L.Rect(200, 300, 360, 400)  # #281: the learner dragged the panel over the middle
    assert L.target(s, "lesson", dragged) == L.target(s, "lesson")
    assert L.plan(s, panel=dragged).panel == L.panel_rect(s)


def test_v1_reserve_when_the_app_is_older():
    s = scr(by("13-inch 1440x900, no notch, Dock bottom"))
    assert L.target(s, "lesson", reserve=L.PANEL_RESERVE_V1).right == 1440 - 436


def test_rounding_matches_javascript():
    assert L.half_up(0.5) == 1.0 and L.half_up(1036.8) == 1037.0 and L.video_editor_w(1512) == 907.0


# ----------------------------------------------------------------------------------- the single writer (editor.py)

class AXW:
    """One lesson window with a real frame: reads what was set, the learner can move it."""

    def __init__(self, frame=(100, 120, 900, 600), fullscreen=False):
        self.frames = {"lesson": tuple(frame)}
        self.fs = fullscreen
        self.log: list = []

    def folder_window(self, pid, folder):
        return "lesson"

    def focused_window(self, pid):
        return "lesson"

    def is_fullscreen(self, w):
        return self.fs

    def frame(self, w):
        return self.frames.get(w)

    def set_frame(self, w, x, y, wd, h):
        self.log.append(("frame", w, x, y, wd, h))
        self.frames[w] = (x, y, wd, h)
        return True

    def other_lesson_windows(self, pid, folder):
        return []

    def raise_window(self, w):
        self.log.append(("raise", w))

    def enter_fullscreen(self, w):
        self.log.append(("enter_fs", w))
        return True

    def exit_fullscreen(self, w):
        self.log.append(("exit_fs", w))
        return True


VSC = {"id": "vscode", "label": "Visual Studio Code", "app": "Visual Studio Code", "bundle": "com.microsoft.VSCode"}
NEO = scr(by("13-inch 1440x900, no notch, Dock bottom"))


@pytest.fixture
def rig(monkeypatch, tmp_path):
    monkeypatch.setattr(E, "_arranged", [])
    monkeypatch.setattr(E, "_released", [])
    monkeypatch.setattr(E, "_opening", 0)
    monkeypatch.setattr(E, "_pending_fit", None)
    monkeypatch.setattr(E, "_later", lambda s, fn: fn())  # the settled re-read runs at once
    monkeypatch.setattr(E, "_panel_rect", None)
    monkeypatch.setattr(E, "_app_v2", True)
    monkeypatch.setattr(E, "NATIVE_FULLSCREEN", False)
    monkeypatch.setattr(E, "find_pid", lambda name, bundle=None: 222)
    monkeypatch.setattr(E, "ax_trusted", lambda: True)
    monkeypatch.setattr(E, "lesson_screen", lambda: NEO)
    folder = tmp_path / "lesson"
    folder.mkdir()
    return str(folder)


def frames(ax):
    return [e for e in ax.log if e[0] == "frame"]


def test_open_lays_the_window_out_once_beside_the_panel(rig):
    ax, rep = AXW(), {}
    E.make_fullscreen(VSC, rep, folder=rig, ax=ax, sleep=lambda s: None)
    want = L.target(NEO, "lesson")
    assert frames(ax) == [("frame", "lesson", *want.tuple())] and rep["fullscreen"] == "done (maximized)"
    # the panel reports where the app drew it (the same dock): nothing moves
    E.note_panel(True, L.panel_rect(NEO).__dict__)
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0) == "ok"
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0) == "ok"  # a run step: still nothing
    assert len(frames(ax)) == 1


def test_open_leaves_native_full_screen_alone(rig):
    ax, rep = AXW(fullscreen=True), {}
    E.make_fullscreen(VSC, rep, folder=rig, ax=ax, sleep=lambda s: None)
    assert frames(ax) == [] and ("exit_fs", "lesson") not in ax.log and rep["fullscreen"].startswith("done (already")
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0) == "full screen (left as it is)"


def test_after_the_learner_resizes_it_miyagi_never_lays_it_out_again(rig):
    ax, rep = AXW(), {}
    E.make_fullscreen(VSC, rep, folder=rig, ax=ax, sleep=lambda s: None)
    ax.frames["lesson"] = (0, 69, 1300, 700)  # the learner widened it under the panel: their choice
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0) == "the learner's layout (left as it is)"
    E.note_panel(True, {"x": 1000, "y": 52, "w": 400, "h": 600})  # the panel moves (a display change)
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0) == "the learner's layout (left as it is)"
    ax.frames["lesson"] = tuple(L.target(NEO, "lesson").tuple())  # even dragged back exactly: still theirs
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0) == "the learner's layout (left as it is)"
    assert len(frames(ax)) == 1


def test_a_window_still_where_miyagi_put_it_follows_the_docked_panel(rig):
    ax, rep = AXW(), {}
    E.make_fullscreen(VSC, rep, folder=rig, ax=ax, sleep=lambda s: None)
    E.note_panel(True, {"x": 1440 - 16 - 420, "y": 52, "w": 420, "h": 600})  # a wider docked panel
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0) == "followed"
    assert frames(ax)[-1][2] + frames(ax)[-1][4] == 1440 - 16 - 420 - L.PANEL_GAP


def test_a_burst_of_follow_ups_is_one_layout(rig, monkeypatch):
    """panel.state while the panel springs, then a run step: only the last request of the burst acts."""
    ax = AXW(frame=(0, 69, 1300, 700))  # never laid out by Miyagi, reaching under the panel
    results = []

    def nested_sleep(_s):  # a second request lands while the first one waits out the burst
        if not results:
            results.append(E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0))

    first = E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0.5, sleep=nested_sleep)
    assert results == ["narrowed"] and first.startswith("coalesced") and len(frames(ax)) == 1


def test_follow_ups_wait_for_the_opens_own_layout_then_run_once(rig, monkeypatch):
    """#287 review: a follow-up skipped while the open's layout runs isn't lost: it runs once when that layout ends."""
    monkeypatch.setattr(E, "_opening", 1)
    ax = AXW(frame=(0, 69, 1300, 700))
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0).startswith("skipped: the open")
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0).startswith("skipped: the open")  # one pending
    assert frames(ax) == []
    E._opening_layout(-1, ax)  # the open's layout ends (make_fullscreen / arrange's finally)
    assert len(frames(ax)) == 1 and E._pending_fit is None
    E._opening_layout(-1, ax)
    assert len(frames(ax)) == 1  # nothing pending any more


def test_the_open_runs_a_follow_up_that_came_while_it_waited_for_the_window(rig, monkeypatch):
    ax = AXW()
    seen = []

    def sleep(_s):  # the open waits for the window; panel.state arrives meanwhile
        if not seen:
            seen.append(E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0))

    real = ax.folder_window
    calls = {"n": 0}

    def late_window(pid, folder):
        calls["n"] += 1
        return real(pid, folder) if calls["n"] > 1 else None

    ax.folder_window = late_window
    E.make_fullscreen(VSC, {}, folder=rig, ax=ax, sleep=sleep)
    assert seen[0].startswith("skipped: the open")
    assert len(frames(ax)) == 1  # the open's layout; the held follow-up then found it already there


def test_vscode_settling_after_the_move_is_not_the_learner_moving_it(rig, monkeypatch):
    """#287 review: VS Code / macOS nudge the window a moment after the move (slow Mac, right after launch); that frame
    is re-read SETTLED_READ_S later and counts as Miyagi's, so the window isn't wrongly handed to the learner."""
    ax = AXW()
    want = L.target(NEO, "lesson")
    nudged = (want.x, want.y + 6, want.w, want.h - 6)  # a title-bar snap
    monkeypatch.setattr(E, "_later", lambda s, fn: (ax.frames.update(lesson=nudged), fn()))
    E.make_fullscreen(VSC, {}, folder=rig, ax=ax, sleep=lambda s: None)
    assert E._ownership(ax, "lesson") is True
    ax.frames["lesson"] = (200, 200, 900, 600)  # the learner really moves it
    assert E._ownership(ax, "lesson") is False


def test_never_laid_out_window_is_narrowed_once_then_owned(rig):
    ax = AXW(frame=(0, 69, 1300, 700))
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0) == "narrowed"
    assert frames(ax)[-1] == ("frame", "lesson", 0, 69, L.target(NEO, "lesson").right, 700)
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0) == "ok"


def test_maximized_window_is_left_for_good(rig):
    ax = AXW(frame=(0, 25, 1440, 805))
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0).startswith("maximized")
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0) == "the learner's layout (left as it is)"
    assert frames(ax) == []


def test_video_open_puts_vscode_left_of_the_player_column(rig):
    ax, rep = AXW(), {}
    E.arrange(VSC, {"pid": 111, "name": "Safari"}, rep, ax=ax, folder=rig, sleep=lambda s: None)
    want = L.target(NEO, "video")
    assert frames(ax)[0] == ("frame", "lesson", *want.tuple()) and want.right == 864
    assert not [e for e in ax.log if e[0] == "exit_fs"]  # nobody leaves full screen
    # a run step keeps the video layout (its mode is remembered), not the lesson panel's
    assert E.fit_beside_drawer(rig, ax=ax, editor=VSC, settle_s=0) == "ok" and len(frames(ax)) == 1


def test_lesson_end_restores_and_forgets_ownership(rig):
    ax, rep = AXW(frame=(10, 30, 1000, 700)), {}
    E.make_fullscreen(VSC, rep, folder=rig, ax=ax, sleep=lambda s: None)
    assert E.restore_frames(ax) == [(10, 30, 1000, 700)]
    assert E._arranged == [] and E._released == []
