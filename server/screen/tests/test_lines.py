"""locate_line / locate_anchor on recorded Vision OCR of full-screen VS Code and Cursor.

The fixtures (server/screen/fixtures/*_fullscreen_*) are rendered by make_editor_fixtures.py; each
has the recorded OCR (`.ocr.json`, so these tests run offline on any OS) and the ground truth of
where every file line was drawn (`.truth.json`). No network, no model calls.
"""
import json
import sys
from pathlib import Path

import pytest

from server.screen import lines as L
from server.screen.types import Rect, ScreenObservation

FIX = Path(__file__).resolve().parent.parent / "fixtures"
SRC = FIX / "editor_src" / "pinn_convection.py.txt"
NAMES = ["vscode_fullscreen_top", "vscode_fullscreen_scrolled", "cursor_fullscreen_bigfont"]
FILE = "pinn_demo/pinn_convection.py"


def _load(name):
    obs = ScreenObservation.from_dict(json.loads((FIX / f"{name}.ocr.json").read_text()))
    truth = json.loads((FIX / f"{name}.truth.json").read_text())
    return obs, truth


@pytest.fixture(scope="module", params=NAMES)
def case(request):
    return _load(request.param)


def test_visible_lines_match_what_was_drawn(case):
    obs, truth = case
    loc = L.locate_line(obs, FILE, truth["geometry"]["visible"][0])
    assert loc.visible_lines == tuple(truth["geometry"]["visible"])


def test_every_visible_line_gets_its_exact_row(case):
    obs, truth = case
    g = truth["geometry"]
    for n, t in truth["lines"].items():
        loc = L.locate_line(obs, FILE, int(n))
        assert loc, f"line {n} not found"
        r = loc.rect
        assert abs(r.y - t["y"]) <= 2 and abs(r.h - t["h"]) <= 1, (n, r, t)
        # full width of the text area: from just left of the code to the minimap
        assert g["text_left"] - 10 <= r.x <= g["text_left"] and abs(r.x2 - g["text_right"]) <= 2, (n, r)
        assert loc.source == "ocr" and loc.reason is None and loc.direction is None


def test_line_text_has_no_gutter_number():
    obs, _ = _load("cursor_fullscreen_bigfont")
    loc = L.locate_line(obs, FILE, 100)
    assert loc.text == "err = torch.linalg.norm(u - exact) / torch.linalg.norm(exact)"


def test_single_digit_lines_vision_missed_are_still_found():
    obs, truth = _load("vscode_fullscreen_top")
    numbered = {b.text for b in obs.blocks if b.text.strip().isdigit()}
    assert "1" not in numbered and "5" not in numbered   # Vision skips lone digits ...
    for n in (1, 5, 9):                                  # ... the row grid still covers them
        assert abs(L.locate_line(obs, FILE, n).rect.y - truth["lines"][str(n)]["y"]) <= 2


@pytest.mark.parametrize("name,line,direction", [
    ("vscode_fullscreen_top", 47, "down"),
    ("vscode_fullscreen_scrolled", 10, "up"),
    ("vscode_fullscreen_scrolled", 85, "down"),
    ("cursor_fullscreen_bigfont", 1, "up"),
])
def test_scrolled_off_line_says_where_to_scroll(name, line, direction):
    obs, truth = _load(name)
    loc = L.locate_line(obs, FILE, line)
    assert not loc and loc.rect is None
    assert loc.reason == "not_visible" and loc.direction == direction
    assert loc.visible_lines == tuple(truth["geometry"]["visible"])


def test_other_file_is_not_boxed():
    obs, _ = _load("vscode_fullscreen_scrolled")
    loc = L.locate_line(obs, "train.py", 48)
    assert not loc and loc.reason == "file_not_active" and loc.visible_lines == (44, 84)


@pytest.mark.parametrize("f", ["pinn_convection.py", "pinn_demo/pinn_convection.py",
                               "/Users/me/pinn_demo/pinn_convection.py", "./pinn_convection.py", None])
def test_file_spellings(f):
    obs, _ = _load("vscode_fullscreen_scrolled")
    assert L.locate_line(obs, f, 48)


def test_full_screen_editor_has_no_menu_bar_offset():
    obs, _ = _load("vscode_fullscreen_top")
    assert obs.windows[0].rect == Rect(0, 0, 1728, 1117)
    assert abs(L.locate_line(obs, FILE, 1).rect.y - 57) <= 2   # right under the breadcrumbs


def test_terminal_epoch_column_is_not_a_gutter():
    obs, _ = _load("vscode_fullscreen_scrolled")   # its panel shows epoch 100, 200, ... 1000
    panes = L.find_panes(obs)
    assert len(panes) == 1 and panes[0].rect.y2 < 800


# ---------------------------------------------------------------------- anchors

def test_anchor_on_screen():
    obs, truth = _load("vscode_fullscreen_scrolled")
    loc = L.locate_anchor(obs, "def pde_residual(")
    assert loc and loc.line == 48
    assert abs(loc.rect.y - truth["lines"]["48"]["y"]) <= 2
    assert loc.match_rect.x < 380 and loc.match_rect.x2 < 700 and loc.rect.contains(loc.match_rect)
    assert loc.text.startswith("def pde_residual(model, x, t")


def test_anchor_multi_line_uses_first_line():
    obs, _ = _load("vscode_fullscreen_top")
    assert L.locate_anchor(obs, "class MLP(nn.Module):\n    def __init__(self").line == 21


def test_anchor_off_screen_resolves_with_file_text():
    obs, _ = _load("cursor_fullscreen_bigfont")
    assert L.locate_anchor(obs, "def pde_residual(").reason == "not_found"
    loc = L.locate_anchor(obs, "def pde_residual(", file=FILE, file_text=SRC.read_text())
    assert not loc and loc.line == 48 and loc.direction == "up" and loc.visible_lines == (70, 115)


def test_anchor_prefers_the_occurrence_that_is_in_the_file():
    obs, _ = _load("vscode_fullscreen_scrolled")
    loc = L.locate_anchor(obs, "torch.autograd.grad(u, x", file_text=SRC.read_text())
    assert loc.line == 52


# ---------------------------------------------------------------------- AX merge (pure)

class FakeEditor:
    """Duck-typed ax.EditorState: caret on `caret_line` at y=`y`."""

    def __init__(self, caret_line, y, h=18.0, text="", page_start_line=1):
        self.caret_line, self.text, self.page_start_line = caret_line, text, page_start_line
        self.line_rect, self.line_height = Rect(376, y, 2, h), h

    def rect_for_line(self, line):
        return Rect(self.line_rect.x, self.line_rect.y + (line - self.caret_line) * self.line_height, 2,
                    self.line_height)

    def line_text(self, line):
        lines = self.text.split("\n")
        i = line - self.page_start_line
        return lines[i] if 0 <= i < len(lines) else None


def test_ax_agreeing_keeps_ocr_width_and_takes_ax_y():
    obs, truth = _load("vscode_fullscreen_scrolled")
    ed = FakeEditor(48, truth["lines"]["48"]["y"] + 1, text=SRC.read_text())
    loc = L.merge_ax(L.locate_line(obs, FILE, 50), ed, "/u/pinn_demo/pinn_convection.py", FILE, 50)
    assert loc.source == "ax+ocr" and loc.rect.w > 1000
    assert loc.rect.y == truth["lines"]["50"]["y"] + 1
    assert loc.text == "    ones = torch.ones_like(u)"   # exact buffer text (indentation kept) via AX


def test_ax_disagreeing_keeps_ocr():
    obs, _ = _load("vscode_fullscreen_scrolled")
    before = L.locate_line(obs, FILE, 50)
    loc = L.merge_ax(L.locate_line(obs, FILE, 50), FakeEditor(48, 600), "/u/pinn_demo/pinn_convection.py", FILE, 50)
    assert loc.source == "ocr" and loc.rect == before.rect


def test_ax_other_document_is_ignored():
    obs, _ = _load("vscode_fullscreen_scrolled")
    loc = L.merge_ax(L.locate_line(obs, FILE, 50), FakeEditor(48, 128), "/u/pinn_demo/train.py", FILE, 50)
    assert loc.source == "ocr"


def test_ax_alone_when_ocr_sees_no_editor():
    obs = ScreenObservation(t=0, app="Code")
    loc = L.merge_ax(L.locate_line(obs, FILE, 50), FakeEditor(48, 128), "/u/pinn_demo/pinn_convection.py", FILE, 50)
    assert loc and loc.source == "ax" and loc.rect.y == 128 + 2 * 18


def test_ax_anchor_line_uses_page_offset():
    ed = FakeEditor(1, 0, text="a\nb\ndef target():\n", page_start_line=501)
    assert L.ax_anchor_line(ed, "def target(") == 503 and L.ax_anchor_line(ed, "nope") is None


def test_same_file():
    assert L.same_file("/a/pinn_demo/x.py", "pinn_demo/x.py") and L.same_file("x.py", "/a/b/x.py")
    assert L.same_file("file:///a/x.py", "/a/x.py") and not L.same_file("/a/x.py", "/a/y.py")
    assert not L.same_file("/a/other/x.py", "pinn_demo/x.py") and not L.same_file(None, "x.py")


def test_observation_round_trip():
    obs, _ = _load("vscode_fullscreen_top")
    again = ScreenObservation.from_dict(obs.to_dict())
    assert [b.to_dict() for b in again.blocks] == [b.to_dict() for b in obs.blocks]
    assert again.windows == obs.windows and again.screen == obs.screen


def test_to_dict_is_json():
    obs, _ = _load("vscode_fullscreen_scrolled")
    d = L.locate_line(obs, FILE, 48).to_dict()
    assert json.loads(json.dumps(d))["visible_lines"] == [44, 84]


# ---------------------------------------------------------------------- live Vision (macOS)

mac = pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision is macOS-only")


@mac
@pytest.mark.parametrize("name", NAMES)
def test_fresh_vision_ocr_agrees_with_the_recording(name):
    from server.screen import observe_image
    obs = observe_image(str(FIX / f"{name}.png"))
    _, truth = _load(name)
    loc = L.locate_line(obs, FILE, truth["geometry"]["visible"][0] + 3)
    assert loc.visible_lines == tuple(truth["geometry"]["visible"])
    assert abs(loc.rect.y - truth["lines"][str(loc.line)]["y"]) <= 2


@mac
def test_reader_api_on_a_fixture(tmp_path):
    from server.screen.reader import ScreenReader
    src = tmp_path / "pinn_convection.py"
    src.write_text(SRC.read_text())
    r = ScreenReader(fixture=str(FIX / "cursor_fullscreen_bigfont.png"), use_ax=False, use_events=False)
    assert r.locate_line(str(src), 100)
    off = r.locate_anchor("def pde_residual(", file=str(src))
    assert off.line == 48 and off.direction == "up"
    on = r.locate_anchor("def evaluate(", file=str(src))
    assert on and on.line == 93
