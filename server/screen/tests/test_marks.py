"""Set-of-marks candidates (server.screen.marks) on recorded OCR fixtures. Offline, no API calls."""
import itertools
import json
import sys
from pathlib import Path

import pytest

from server.screen import marks
from server.screen.types import ScreenObservation

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def _obs(name):
    return ScreenObservation.from_dict(json.loads((FIX / f"{name}.ocr.json").read_text()))


def _texts(cands):
    return [c.text for c in cands]


def test_regions_have_fixed_ids():
    cs = marks.candidates(_obs("vscode_fullscreen_scrolled"))
    regs = {c.text: c.id for c in cs if c.kind == "region"}
    assert regs == {"terminal": 1, "editor": 2, "explorer": 3}            # no menu bar / run icon here
    cs2 = marks.candidates(_obs("vscode_window_calc_clean"))
    assert {c.text: c.id for c in cs2 if c.kind == "region"} == {"editor": 2, "explorer": 3, "terminal_menu": 4}


def test_code_rows_carry_file_lines_and_full_width_rects():
    cs = marks.candidates(_obs("vscode_fullscreen_scrolled"))
    rows = [c for c in cs if c.kind in ("code", "blank")]
    assert [c.id for c in rows] == list(range(10, 10 + len(rows)))        # editor rows first, from id 10
    assert [c.line for c in rows] == list(range(rows[0].line, rows[0].line + len(rows)))   # every line, blanks too
    code = [c for c in rows if c.kind == "code"]
    assert all(c.text == "" for c in rows if c.kind == "blank")
    pde = next(c for c in code if c.text.startswith("def pde_residual"))
    assert pde.line == 48 and pde.rect.w > 1000 and pde.region == "editor"
    assert not any(c.text.isdigit() for c in cs)                          # no gutter numbers


def test_excludes_hover_breadcrumb_and_tab_bar():
    cs = marks.candidates(_obs("vscode_window_calc_hover"))
    t = " | ".join(_texts(cs))
    assert "(function)" not in t and "Any" not in t and "Add two numbers" not in t    # hover
    assert "›" not in t and "src > calc" not in t                                     # breadcrumb
    assert "test_calculator.py" in _texts(cs)                                         # explorer item stays...
    tab_row = [c for c in cs if c.kind != "region" and 75 < c.rect.cy < 100 and c.rect.x > 290]
    assert tab_row == []                                                               # ...the tab bar doesn't
    assert "python-calculator-e430dc" not in _texts(cs)                               # command center (title bar)
    under = [c for c in cs if c.kind == "code" and c.occluded]
    assert under and all(5 <= c.line <= 10 for c in under)
    assert "partly under a tooltip" in marks.listing(under)


def test_terminal_and_explorer_lines_are_tagged_with_their_region():
    cs = marks.candidates(_obs("vscode_fullscreen_scrolled"))
    assert any(c.region == "terminal" and c.text.startswith("epoch 100") for c in cs)
    assert any(c.region == "explorer" and c.text == "train.py" for c in cs)


def test_ids_are_stable_whatever_the_intent():
    obs = _obs("vscode_window_calc_clean")
    plain = marks.candidates(obs)
    ranked = marks.candidates(obs, intent="def add")
    assert [(c.id, c.text) for c in plain] == [(c.id, c.text) for c in ranked]
    best = max((c for c in ranked if c.kind != "region"), key=lambda c: c.score)
    assert best.text == "def add(a, b):" and best.line == 4
    assert next(c for c in ranked if c.text == "terminal_menu").score == 0
    assert next(c for c in marks.candidates(obs, intent="open the terminal menu") if c.id == 4).score == 100


def test_max_lines_keeps_the_most_relevant_in_id_order():
    obs = _obs("vscode_fullscreen_scrolled")
    cs = marks.candidates(obs, intent="def pde_residual", max_lines=5)
    lines = [c for c in cs if c.kind != "region"]
    assert len(lines) == 5 and [c.id for c in lines] == sorted(c.id for c in lines)
    assert any(c.text.startswith("def pde_residual") for c in lines)


def test_listing_and_by_id():
    cs = marks.candidates(_obs("vscode_window_calc_clean"))
    text = marks.listing(cs)
    assert text.splitlines()[0] == "2 [region] editor"
    assert "[code L4] def add(a, b):" in text
    c = marks.by_id(cs, "#4")
    assert c.text == "terminal_menu" and marks.by_id(cs, 999) is None and marks.by_id(cs, "x") is None
    assert json.loads(json.dumps([c.to_dict() for c in cs]))[0]["rect"]["w"] > 0


def test_given_region_rects_are_used_as_is():
    from server.screen.types import Rect
    obs = _obs("vscode_fullscreen_scrolled")
    cs = marks.candidates(obs, regions={"terminal": Rect(300, 800, 1428, 296), "editor": None})
    regs = {c.text: c.rect for c in cs if c.kind == "region"}
    assert regs == {"terminal": Rect(300, 800, 1428, 296)}


def test_package_function_on_an_observation():
    from server.screen import candidates
    assert candidates("def add", obs=_obs("vscode_window_calc_clean"))[0].text == "editor"


@pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision is macOS-only")
def test_reader_candidates_on_a_fixture():
    from server.screen.reader import ScreenReader
    r = ScreenReader(fixture=str(FIX / "vscode_fullscreen_top.png"), use_ax=False, use_events=False)
    cs = r.candidates("terminal")
    term = marks.by_id(cs, 1)
    assert term is not None and term.rect == r.locate_region("terminal")      # same stabilized rect
    assert term.score == 100 and any(c.kind == "code" and c.line == 9 for c in cs)


# ---------------------------------------------------------------------- Michael's real screen (scale 1,
# line numbers unreadable, Chat side bar, Miyagi overlay masked): fixture from the haiku-targeter

CALC = "vscode_lesson_calculator"


def test_real_screen_without_a_readable_gutter():
    from server.screen import regions as R
    obs = _obs(CALC)
    assert not any(b.text.strip().isdigit() for b in obs.blocks)          # Vision read no line numbers
    ed, ex = R.find_region(obs, "editor"), R.find_region(obs, "explorer")
    assert ed.source == "tabs" and 540 <= ed.rect.x <= 552 and 1505 <= ed.rect.x2 <= 1520   # stops at Chat
    assert 165 <= ed.rect.y <= 180                                          # below tab + breadcrumb
    assert ex.rect.x2 <= ed.rect.x                                          # explorer no longer covers the tab
    run = R.find_region(obs, "run_button")
    assert run.source == "tab_row_icon" and run.rect.contains_point(1412, 124)


def test_real_screen_candidates():
    cs = marks.candidates(_obs(CALC))
    t = marks.listing(cs)
    rows = [c for c in cs if c.kind in ("code", "blank")]
    assert [c.kind for c in rows] == ["code", "blank", "code", "blank"]      # lines 1-4 (2 and 4 empty)
    assert all(c.line is None for c in rows) and rows[2].text.startswith("# Step 1")
    assert all(abs((b.rect.cy - a.rect.cy) - 22.5) < 1.5 for a, b in itertools.pairwise(rows))
    assert {c.id: c.text for c in cs if c.kind == "region"} == {2: "editor", 3: "explorer", 5: "run_button"}
    assert "Chat" not in t and "Sessions" not in t and "Tip:" not in t          # side bar left out
    assert "D •" not in t and "calculator.py X" not in t                          # tab row left out
    explorer = [c for c in cs if c.region == "explorer"]
    assert [c.text for c in explorer][-2:] == ["calculator.py", "• README.md"]   # only real explorer items
    assert "11 [blank] (empty line)" in t and "13 [blank] (empty line)" in t


def test_blank_rows_are_never_ranked_by_text():
    cs = marks.candidates(_obs(CALC), intent="empty line")
    assert all(c.score == 0 for c in cs if c.kind == "blank")
