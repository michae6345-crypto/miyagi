"""vscode_window(), frontmost app, the menu-bar Terminal item, hover tooltips and split code words.

Fixtures: two rendered WINDOWED VS Code screens (make_window_fixtures.py), with the macOS menu bar,
the command center showing "python-calculator-e430dc", a dirty or clean tab, Dark+ token colours and
(in one) a Pylance hover over `def add(a, b):`. Recorded OCR, offline, no API calls.
"""
import json
import sys
import time
from pathlib import Path

import pytest
from rapidfuzz import fuzz

from server.screen import lines as L
from server.screen import match as M
from server.screen import regions as R
from server.screen.types import Block, Rect, ScreenObservation, Window
from server.screen.vscode import parse_title, vscode_window

FIX = Path(__file__).resolve().parent.parent / "fixtures"
HOVER, CLEAN = "vscode_window_calc_hover", "vscode_window_calc_clean"


def _obs(name):
    return ScreenObservation.from_dict(json.loads((FIX / f"{name}.ocr.json").read_text(encoding="utf-8")))


def _truth(name):
    return json.loads((FIX / f"{name}.truth.json").read_text(encoding="utf-8"))


def near(a, b, tol=4):
    return abs(a - b) <= tol


# ---------------------------------------------------------------------- vscode_window

def test_window_folder_file_path_dirty():
    w = vscode_window(_obs(HOVER))
    assert (w.folder, w.file, w.path, w.symbol, w.dirty) == (
        "python-calculator-e430dc", "calculator.py", "src/calculator.py", "add", True)
    assert w.sources["folder"] == "title+command_center" and w.sources["dirty"] == "title"
    assert vscode_window(_obs(CLEAN)).dirty is False


def test_window_without_a_title_uses_command_center_and_breadcrumb():
    obs = _obs(CLEAN)
    title = obs.windows[0].title
    obs.windows = [Window("Code", "", obs.windows[0].rect)]
    obs.blocks = [Block(b.text, b.rect, b.confidence, b.app, "" if b.window == title else b.window, b.role)
                  for b in obs.blocks]
    w = vscode_window(obs)
    assert w.folder == "python-calculator-e430dc" and w.sources["folder"] == "command_center"
    assert w.file == "calculator.py" and w.sources["file"] == "breadcrumb"   # spelled as on the tab
    assert w.path.startswith("src/") and w.dirty is None


@pytest.mark.parametrize("name,expect", [
    ("vscode_fullscreen_top", ("pinn_demo", "pinn_convection.py", False)),
    ("cursor_fullscreen_bigfont", ("pinn_demo", "pinn_convection.py", True)),
    ("vscode_terminal_flat", ("pinn_demo", "pinn_convection.py", False)),
])
def test_window_on_other_fixtures(name, expect):
    w = vscode_window(_obs(name))
    assert (w.folder, w.file, w.dirty) == expect


def test_no_vscode_window():
    obs = _obs(CLEAN)
    obs.windows = [Window("Safari", "Apple", Rect(0, 33, 800, 600))]
    assert vscode_window(obs) is None


@pytest.mark.parametrize("title,expect", [
    ("● calculator.py — python-calculator-e430dc", ("calculator.py", "python-calculator-e430dc", True)),
    ("calculator.py — python-calculator-e430dc — Visual Studio Code",
     ("calculator.py", "python-calculator-e430dc", False)),
    ("python-calculator-e430dc", (None, "python-calculator-e430dc", False)),
    ("app.py - demo [SSH: box] - Visual Studio Code", ("app.py", "demo", False)),
    ("", (None, None, False)),
])
def test_parse_title(title, expect):
    assert parse_title(title) == expect


# ---------------------------------------------------------------------- hover tooltips

def test_hover_is_tagged_and_kept_out_of_code_reading():
    obs = _obs(HOVER)
    assert obs.hovers()[0] == "(function) def add(" and "Add two numbers." in obs.hovers()
    assert "(function)" not in obs.text() and "a: Any" not in obs.text()
    assert all("Any" not in ln for ls in obs.lines_by_app().values() for ln in ls)
    assert M.locate_match(obs, "a: Any,") is None
    assert L.locate_line(obs, "calculator.py", 4).text == "def add(a, b):"


def test_rows_under_the_hover_are_flagged_not_garbled():
    obs = _obs(HOVER)
    t = _truth(HOVER)["hover"]
    for n in range(5, 11):
        loc = L.locate_line(obs, "calculator.py", n)
        assert loc.occluded, n
        assert "Any" not in (loc.text or "")           # was "def b: Any" for `def subtract(a, b):`
    assert not L.locate_line(obs, "calculator.py", 4).occluded
    assert not L.locate_line(obs, "calculator.py", 12).occluded
    assert t["y"] < L.locate_line(obs, "calculator.py", 6).rect.cy < t["y"] + t["h"]


def test_hover_seeds():
    blocks = [Block("(variable) loss: Tensor", Rect(400, 200, 160, 13), 1.0, "Code", "w"),
              Block('"np" is not defined Pylance(reportUndefinedVariable)', Rect(400, 400, 300, 13), 1.0, "Code", "w"),
              Block("x = np.zeros(3)", Rect(380, 420, 120, 13), 1.0, "Code", "w")]
    roles = [b.role for b in M.mark_hovers(blocks)]
    assert roles == ["hover", "hover", ""]
    assert M.mark_hovers(blocks[2:]) == blocks[2:]


# ---------------------------------------------------------------------- split coloured words

def test_split_def_name_is_one_block_for_the_coach():
    texts = [b.text for b in _obs(CLEAN).blocks]
    assert "def add(a, b):" in texts and "def" not in texts


def test_merge_split_words_rules():
    row = [Block("def", Rect(361.7, 180.7, 27.6, 12.6), 1.0, "Code", "w"),
           Block("add(a, b):", Rect(386.8, 180.5, 77.9, 15.4), 0.9, "Code", "w"),
           Block("12", Rect(322, 180.6, 17.6, 12.6), 1.0, "Code", "w"),               # gutter: never joined
           Block("# far comment", Rect(700, 180.6, 90, 12.6), 1.0, "Code", "w")]       # big gap: not joined
    out = M.merge_split_words(row)
    assert [b.text for b in out] == ["12", "def add(a, b):", "# far comment"]
    assert out[1].confidence == 0.9 and near(out[1].rect.x, 361.7, 0.1) and near(out[1].rect.x2, 464.7, 0.1)


def test_coloured_code_reads_close_to_the_source():
    obs, t = _obs(CLEAN), _truth(CLEAN)["lines"]
    for n, row in t.items():
        loc = L.locate_line(obs, "calculator.py", int(n))
        assert loc, n
        want = row["text"].strip()
        got = (loc.text or "").strip()
        assert (not want and not got) or fuzz.ratio(M.squash(want), M.squash(got)) >= 85, (n, got, want)


# ---------------------------------------------------------------------- row re-read

def test_broken_def_row_is_reread():
    from server.screen.reader import repair_code_rows
    blocks = [Block("def(a, b):", Rect(361.7, 180.5, 103.0, 15.4), 0.6, "Code", "w"),
              Block("return a + b", Rect(389.3, 200.8, 90.4, 12.7), 1.0, "Code", "w")]
    calls = []

    def fake_ocr(img, screen, scale, crop=None):
        calls.append(crop)
        return [Block("def add(a, b):", Rect(crop.x + 6, crop.y + 4, 103, 15), 0.95)], 5.0
    out = repair_code_rows(None, Rect(0, 0, 1728, 1117), 2.0, blocks, ocr=fake_ocr)
    assert [b.text for b in out] == ["def add(a, b):", "return a + b"] and out[0].app == "Code"
    assert calls and calls[0].contains_point(400, 188)


def test_reread_that_is_still_broken_keeps_the_original():
    from server.screen.reader import repair_code_rows
    blocks = [Block("class(Base):", Rect(361.7, 180.5, 103.0, 15.4), 0.6, "Code", "w")]
    out = repair_code_rows(None, Rect(0, 0, 1728, 1117), 2.0, blocks,
                           ocr=lambda *a, **k: ([Block("class(Base):", Rect(360, 180, 100, 15), 0.6)], 1.0))
    assert out == blocks
    good = [Block("def add(a, b):", Rect(361.7, 180.5, 103.0, 15.4), 1.0, "Code", "w")]
    assert repair_code_rows(None, Rect(0, 0, 1728, 1117), 2.0, good, ocr=lambda *a, **k: pytest.fail("no")) == good


# ---------------------------------------------------------------------- menu bar Terminal item

@pytest.mark.parametrize("name", [HOVER, CLEAN])
def test_terminal_menu_item(name):
    reg = R.find_region(_obs(name), "terminal_menu")
    t = _truth(name)["menu"]["Terminal"]
    assert reg is not None and reg.source == "menu_bar_ocr"
    assert near(reg.rect.x, t["x"]) and near(reg.rect.x2, t["x"] + t["w"]) and reg.rect.y == 0
    assert 24 <= reg.rect.h <= 37
    run = R.find_region(_obs(name), "menu:Run")
    assert run.rect.x2 <= reg.rect.x + 4


def test_terminal_menu_none_when_hidden_or_another_app():
    assert R.find_region(_obs("vscode_fullscreen_top"), "terminal_menu") is None     # full screen: no menu bar
    obs = _obs(CLEAN)
    obs.windows = [Window("Safari", "Apple", Rect(0, 33, 800, 600))] + obs.windows
    assert R.find_region(obs, "terminal_menu") is None


def test_terminal_menu_inside_a_merged_block():
    obs = ScreenObservation(t=0, app="Code", windows=[Window("Code", "x.py — demo", Rect(0, 33, 1200, 900))],
                            blocks=[Block("Code File Edit Selection View Go Run Terminal Window Help",
                                          Rect(48, 10, 520, 15), 1.0)], screen=Rect(0, 0, 1728, 1117))
    reg = R.find_region(obs, "terminal_menu")
    text = "Code File Edit Selection View Go Run Terminal Window Help"
    cw = 520 / len(text)
    assert near(reg.rect.x + 8, 48 + text.index("Terminal") * cw, 1) and near(reg.rect.w - 16, 8 * cw, 1)


# ---------------------------------------------------------------------- frontmost

def _info(owner, layer=0, w=800, h=600, pid=1, wid=1, name=""):
    return {"kCGWindowOwnerName": owner, "kCGWindowLayer": layer, "kCGWindowAlpha": 1.0, "kCGWindowOwnerPID": pid,
            "kCGWindowNumber": wid, "kCGWindowName": name,
            "kCGWindowBounds": {"X": 0, "Y": 33, "Width": w, "Height": h}}


mac = pytest.mark.skipif(sys.platform != "darwin", reason="Quartz is macOS-only")


@mac
def test_pick_frontmost_skips_overlay_chrome_and_menu_extras():
    from server.screen.macos import pick_frontmost
    infos = [_info("Window Server", layer=25), _info("Electron"), _info("Miyagi"), _info("Control Center"),
             _info("Code", w=30, h=20), _info("Code", pid=7, wid=42, name="calculator.py — calc"), _info("Safari")]
    f = pick_frontmost(infos)
    assert (f["app"], f["pid"], f["window_id"], f["title"]) == ("Code", 7, 42, "calculator.py — calc")
    assert pick_frontmost([_info("Electron")]) is None


@mac
def test_frontmost_change_callback_fires_within_half_a_second(monkeypatch):
    from server.screen import macos
    from server.screen.reader import ScreenReader
    seq = [{"app": "Code", "pid": 1, "title": "a", "window_id": 1, "rect": {}}]
    monkeypatch.setattr(macos, "frontmost_window", lambda: seq[-1])
    r = ScreenReader(use_ax=False, use_events=False)
    got = []
    unsub = r.on_frontmost_change(lambda new, old: got.append((time.time(), new and new["app"], old and old["app"])),
                                  interval=0.1)
    time.sleep(0.25)
    assert r.is_frontmost("VS Code") and not r.is_frontmost("Safari")
    t0 = time.time()
    seq.append({"app": "Safari", "pid": 2, "title": "", "window_id": 9, "rect": {}})   # swipe to another Space
    time.sleep(0.5)
    unsub()
    r._stop.set()
    assert got and got[0][1:] == ("Safari", "Code") and got[0][0] - t0 < 0.5
    assert r.is_frontmost("Safari")


@mac
def test_frontmost_live_is_cheap():
    from server.screen import macos
    macos.frontmost_window()
    t = time.perf_counter()
    for _ in range(20):
        macos.frontmost_window()
    assert (time.perf_counter() - t) / 20 < 0.02           # well under 20 ms a call (measured ~0.3 ms)


# ---------------------------------------------------------------------- Michael's notes.py misread:
# empty notes.py open with VS Code's inline chat over line 1; README.md only in the Explorer

NOTES = "vscode_window_notes_inline_chat"


def test_active_file_comes_from_tab_and_breadcrumb_never_the_explorer():
    w = vscode_window(_obs(NOTES))
    assert (w.folder, w.file, w.path, w.dirty) == ("help-me-build-a-notes-app-669032", "notes.py", "notes.py", False)
    assert w.sources["file"] == "tab+breadcrumb"


def test_stale_or_missing_title_does_not_change_the_answer():
    obs = _obs(NOTES)
    real = obs.windows[0].title
    for title in ("README.md — help-me-build-a-notes-app-669032", ""):
        o = _obs(NOTES)
        o.windows = [Window("Code", title, obs.windows[0].rect)]
        o.blocks = [Block(b.text, b.rect, b.confidence, b.app, title if b.window == real else b.window, b.role)
                    for b in o.blocks]
        w = vscode_window(o)
        assert w.file == "notes.py", title
        if title:
            assert w.sources["title_file"] == "README.md"


def test_explorer_rows_alone_never_name_the_file():
    obs = _obs(NOTES)
    obs.windows = [Window("Code", "", obs.windows[0].rect)]
    title = _obs(NOTES).windows[0].title
    obs.blocks = [Block(b.text, b.rect, b.confidence, b.app, "" if b.window == title else b.window, b.role)
                  for b in obs.blocks if b.rect.x < 280 or b.rect.y > 140]   # no tab row, no breadcrumb
    assert vscode_window(obs).file is None                                   # README.md / notes.py rows ignored


def test_inline_chat_is_a_widget_not_code():
    obs = _obs(NOTES)
    assert obs.widgets() == ["Generate code", "+ Auto | Balance"]
    assert "Generate code" not in obs.text() and "Balance" not in obs.text()
    assert M.locate_match(obs, "Generate code") is None
    assert L.locate_line(obs, "notes.py", 1).occluded
    from server.screen import marks
    t = marks.listing(marks.candidates(obs))
    assert "Generate code" not in t and "Auto" not in t and "README.md" in t


@pytest.mark.parametrize("text,widget", [
    ("Generate code", True), ("+ Auto | Balance", True), ("Ask Copilot", True), ("Accept", True),
    ("def generate_code():", False), ("# Auto-save the notes", False),
])
def test_widget_seeds(text, widget):
    b = Block(text, Rect(380, 140, 120, 13), 1.0, "Code", "w")
    assert (M.mark_widgets([b])[0].role == "widget") is widget


@mac
def test_observe_image_attaches_the_editor_info():
    from server.screen import observe_image
    obs = observe_image(str(FIX / f"{NOTES}.png"))
    assert obs.editor["file"] == "notes.py" and obs.editor["folder"] == "help-me-build-a-notes-app-669032"
