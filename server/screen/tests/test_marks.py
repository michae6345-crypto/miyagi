"""Set-of-marks candidates (server.screen.marks) on recorded OCR fixtures. Offline, no API calls."""
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
    assert regs == {"terminal": 1, "editor": 2, "explorer": 3}            # no menu bar in full screen
    cs2 = marks.candidates(_obs("vscode_window_calc_clean"))
    assert {c.text: c.id for c in cs2 if c.kind == "region"} == {"editor": 2, "explorer": 3, "terminal_menu": 4}


def test_code_rows_carry_file_lines_and_full_width_rects():
    cs = marks.candidates(_obs("vscode_fullscreen_scrolled"))
    code = [c for c in cs if c.kind == "code"]
    assert [c.id for c in code] == list(range(10, 10 + len(code)))        # code first, from id 10
    assert [c.line for c in code] == sorted(c.line for c in code)
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
