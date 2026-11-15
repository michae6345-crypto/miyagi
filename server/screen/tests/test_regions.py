"""locate_region: terminal / editor / explorer rects on recorded Vision OCR (offline, any OS).

Fixtures: three rendered full-screen editors (ground truth in `.truth.json`: editor x=300, rows from
y=57, panel at y=800, status bar at y=1095) and a real windowed VS Code screenshot with Explorer,
a Chat side panel and a separate Terminal.app window (`vscode_terminal_flat.ocr.json`).
"""
import json
import sys
from pathlib import Path

import pytest

from server.screen import match as M
from server.screen import regions as R
from server.screen.types import Rect, ScreenObservation

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def _obs(name):
    return ScreenObservation.from_dict(json.loads((FIX / f"{name}.ocr.json").read_text()))


def near(a, b, tol=6):
    return abs(a - b) <= tol


# ---------------------------------------------------------------------- full-screen VS Code

@pytest.mark.parametrize("name", ["vscode_fullscreen_top", "vscode_fullscreen_scrolled"])
def test_terminal_panel_from_its_tab_header(name):
    reg = R.find_region(_obs(name), "terminal")
    assert reg is not None and reg.source == "panel_header" and reg.app == "Code"
    r = reg.rect
    assert near(r.x, 300) and near(r.y, 800) and near(r.x2, 1728) and near(r.y2, 1095)


@pytest.mark.parametrize("name", ["vscode_fullscreen_top", "vscode_fullscreen_scrolled"])
def test_editor_is_below_tabs_and_breadcrumb_and_above_the_panel(name):
    r = R.find_region(_obs(name), "editor").rect
    assert near(r.x, 300) and near(r.y, 57) and near(r.y2, 800) and near(r.x2, 1728)
    assert r.y > 52.7                    # below the breadcrumb row (its text ends at y=52.7)


def test_explorer_side_bar():
    r = R.find_region(_obs("vscode_fullscreen_top"), "explorer").rect
    assert near(r.x, 48, 8) and near(r.x2, 300) and near(r.y2, 1095)


def test_terminal_from_the_prompt_when_the_header_is_unreadable():
    obs = _obs("vscode_fullscreen_top")
    obs.blocks = [b for b in obs.blocks if not any(t in b.text for t in ("PROBLEMS", "TERMINAL"))]
    reg = R.find_region(obs, "terminal")
    assert reg is not None and reg.source == "prompt"
    assert near(reg.rect.y, 830) and near(reg.rect.x, 300) and near(reg.rect.y2, 1095)
    # ... and the editor still stops at the terminal
    assert R.find_region(obs, "editor").rect.y2 < reg.rect.y


def test_no_panel_no_side_bar_means_none():
    obs = _obs("cursor_fullscreen_bigfont")      # Cursor, panel closed, side bar hidden
    assert R.find_region(obs, "terminal") is None
    assert R.find_region(obs, "explorer") is None
    r = R.find_region(obs, "editor").rect
    assert near(r.x, 48) and near(r.y2, 1095)


def test_code_with_percent_signs_is_not_a_prompt():
    obs = _obs("vscode_fullscreen_top")
    obs.blocks = [b for b in obs.blocks if b.rect.y < 795]   # panel gone; code has `%` in f-strings
    assert R.find_region(obs, "terminal") is None


# ---------------------------------------------------------------------- real windowed VS Code

def test_real_window_explorer_editor_and_chat_panel():
    obs = _obs("vscode_terminal_flat")
    ex = R.find_region(obs, "explorer").rect
    ed = R.find_region(obs, "editor").rect
    assert near(ex.x, 44, 8) and near(ex.x2, 281) and ex.y < 100
    assert near(ed.x, 282) and 640 < ed.x2 < 668       # stops at the Chat side panel (x~666)
    assert near(ed.y, 147) and near(ed.y2, 1012)        # status bar at the window bottom (1034)
    assert R.find_region(obs, "terminal") is None       # integrated terminal not open


def test_terminal_app_window_on_request():
    obs = _obs("vscode_terminal_flat")
    reg = R.find_region(obs, "terminal", app="Terminal")
    assert reg.app == "Terminal" and reg.rect == Rect(980, 408, 740, 692)


def test_locate_line_rows_stop_at_the_chat_panel_too():
    from server.screen import lines as L
    r = L.locate_line(_obs("vscode_terminal_flat"), "pinn_convection.py", 19).rect
    assert r.x2 < 660


def test_aliases_and_unknown_names():
    obs = _obs("vscode_fullscreen_top")
    assert R.find_region(obs, "panel").rect == R.find_region(obs, "terminal").rect
    assert R.find_region(obs, "Side-Bar").rect == R.find_region(obs, "explorer").rect
    assert R.find_region(obs, "run_button") is None     # icon only: AX
    with pytest.raises(ValueError):
        R.find_region(obs, "minimap")


# ---------------------------------------------------------------------- breadcrumb is not a target

def test_breadcrumb_text_is_never_located():
    top = _obs("vscode_fullscreen_top")
    for needle in ("pinn_convection.py › pde_residual", "pde_residual", "pinn_demo"):
        hit = M.locate_match(top, needle)       # may hit the tab / explorer / docstring, never the crumb row
        in_crumb = hit is not None and near(hit.rect.cy, 46, 8) and hit.rect.x > 300   # crumb: x 311-547
        assert not in_crumb, (needle, hit.rect)
    hit = M.locate_match(top, "pinn_convection.py", app="Code")
    assert hit is not None and not near(hit.rect.cy, 46, 10)   # the tab or the explorer entry, not y~46
    scrolled = _obs("vscode_fullscreen_scrolled")       # here it's also code on line 48
    assert M.locate_match(scrolled, "pde_residual").rect.y > 100


@pytest.mark.parametrize("text,crumb", [
    ("pinn_demo › pinn_convection.py › pde_residual", True),
    ("pinn_convection.py > pde_residual", True),
    ("src > models > net", True),
    ("if loss > best > 0: break", False),
    ("return u_t + beta * u_x", False),
    ("x > 3", False),
])
def test_is_breadcrumb(text, crumb):
    assert M.is_breadcrumb(text) is crumb


# ---------------------------------------------------------------------- stability

def test_snap_to_4pt_grid():
    assert R.snap(Rect(299.4, 800.3, 1428.6, 294.7)) == Rect(300, 800, 1428, 296)


def test_small_moves_keep_the_last_rect_big_moves_update():
    st = R.RegionStabilizer()
    a = st.update("t", Rect(299.4, 800.3, 1428.6, 294.7), frame=1)
    assert st.update("t", Rect(303.1, 806.9, 1425.0, 290.0), frame=2) == a     # every edge < 12 pt
    b = st.update("t", Rect(299.4, 640.0, 1428.6, 455.0), frame=3)              # panel dragged up
    assert b != a and b.y == 640


def test_one_missed_frame_is_bridged_two_are_not():
    st = R.RegionStabilizer()
    a = st.update("t", Rect(300, 800, 1428, 295), frame=1)
    assert st.update("t", None, frame=2) == a
    assert st.update("t", None, frame=2) == a           # same frame again: not another miss
    assert st.update("t", None, frame=3) is None
    assert st.update("t", Rect(300, 800, 1428, 295), frame=4) == a


def test_regions_are_stable_across_recorded_frames():
    """The two VS Code frames differ (scrolled), yet the terminal/editor rects come out identical."""
    st = R.RegionStabilizer()
    for name in ("terminal", "editor", "explorer"):
        r1 = st.update(name, R.find_region(_obs("vscode_fullscreen_top"), name).rect, frame=1)
        r2 = st.update(name, R.find_region(_obs("vscode_fullscreen_scrolled"), name).rect, frame=2)
        assert r1 == r2 and all(v % 4 == 0 for v in (r1.x, r1.y, r1.x2, r1.y2))


# ---------------------------------------------------------------------- reader API (macOS: fixture PNG)

mac = pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision is macOS-only")


@mac
def test_reader_locate_region_on_a_fixture():
    from server.screen.reader import ScreenReader
    r = ScreenReader(fixture=str(FIX / "vscode_fullscreen_top.png"), use_ax=False, use_events=False)
    t = r.locate_region("terminal")
    assert t is not None and near(t.y, 800) and t.x % 4 == 0
    assert r.locate_region("terminal") == t
    regs = r.locate_regions()
    assert regs["terminal"] == t.to_dict() and regs["editor"] and regs["explorer"] and regs["run_button"] is None
