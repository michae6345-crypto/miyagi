"""Cursor lookup, PII redaction, AX text merge, AX line geometry, trigger debounce."""
import itertools
import sys
import time

import pytest

from server.screen.match import line_at_point, window_at_point
from server.screen.privacy import is_private_app, redact
from server.screen.types import Block, Rect, ScreenObservation, Window

CODE = Window("Code", "pinn_convection.py", Rect(0, 30, 860, 1000))


def obs_with(blocks, **kw):
    return ScreenObservation(t=0, app="Code", windows=[CODE], blocks=blocks, screen=Rect(0, 0, 1728, 1117), **kw)


def test_line_at_point_and_window():
    o = obs_with([Block("def pde_residual(model, x, t):", Rect(330, 470, 300, 15), 0.9, "Code", CODE.title),
                  Block("return u_t + beta * u_x", Rect(350, 500, 200, 15), 0.9, "Code", CODE.title)])
    assert line_at_point(o, 400, 477).text.startswith("def pde_residual")
    assert line_at_point(o, 400, 492.5) is None               # 7.5pt from both lines: beyond slop
    assert line_at_point(o, 345, 505).text.startswith("return")  # 5pt left of the box: within slop
    assert window_at_point(o, 10, 40).app == "Code" and window_at_point(o, 1500, 40) is None


def test_redact_pii_but_not_training_logs():
    assert redact("mail me: jane.doe@example.com") == "mail me: [email]"
    assert redact("ssn 123-45-6789") == "ssn [ssn]"
    assert redact("card 4111 1111 1111 1111 exp") == "card [card] exp"
    assert redact("call (424) 555-1234 now") == "call [phone] now"
    for safe in ["epoch  1600 | loss 2.5016e-01", "step 1234567890123 loss 0.1", "2026-11-14 12:51:03",
                 "layers=(2, 50, 50, 50, 50, 1)", "lr=1e-3 beta=30.0"]:
        assert redact(safe) == safe
    assert is_private_app("1Password") and not is_private_app("Code")


def test_ax_lines_merge_into_text_and_lines_by_app():
    o = obs_with([Block("visible line", Rect(330, 470, 100, 15), 0.9, "Code", CODE.title)],
                 ax_lines={"Code": ["visible line", "def offscreen_fn():"]})
    assert "def offscreen_fn" in o.text("Code")
    assert o.lines_by_app()["Code"] == ["visible line", "def offscreen_fn():"]  # deduped
    d = o.to_dict()
    assert "cursor" in d and "under_cursor" in d and d["trigger"] == "tick"


@pytest.mark.skipif(sys.platform != "darwin", reason="ax.py imports HIServices")
def test_editor_state_line_geometry():
    from server.screen.ax import EditorState
    ed = EditorState(text="a\nb\nc\nd", page_start_line=1, caret=4, selection_len=0, caret_line=3,
                     line_rect=Rect(330, 500, 500, 18), line_height=18)
    assert ed.rect_for_line(3) == Rect(330, 500, 500, 18)
    assert ed.rect_for_line(1).y == 464 and ed.rect_for_line(4).y == 518
    assert ed.line_at_y(470) == 1 and ed.line_at_y(509) == 3 and ed.line_at_y(520) == 4
    assert ed.line_text(3) == "c" and ed.line_text(9) is None
    off = EditorState("x", 1, 0, 0, 1, None, None)
    assert off.rect_for_line(1) is None and off.line_at_y(10) is None


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS capture")
def test_triggers_are_debounced(tmp_path):
    from server.screen.reader import ScreenReader
    fx = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "fixtures" / "vscode_terminal_flat.png")
    r = ScreenReader(fixture=fx, debounce=0.6, interval=30)
    seen = []
    # (when the capture STARTED, trigger): the debounce spaces capture starts; the first OCR is
    # slower (Vision warm-up), so completion times can be closer together than the debounce
    r.subscribe(lambda o: seen.append((time.time() - o.ocr_ms / 1000, o.trigger)))
    r.start()
    deadline = time.time() + 10   # let the start capture finish first (slow OCR under load)
    while not seen and time.time() < deadline:
        time.sleep(0.05)
    time.sleep(0.1)
    for _ in range(5):            # a burst of 5 clicks -> leading capture + one coalesced trailing capture
        r.poke("click", force=True)
        time.sleep(0.05)
    time.sleep(1.2)
    r.stop()
    triggers = [t for _, t in seen]
    assert triggers[0] == "start" and 1 <= triggers.count("click") <= 2
    assert all(b - a >= 0.55 for (a, _), (b, _) in itertools.pairwise(seen))
