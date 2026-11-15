"""Desktop test 8 (Nov 15, 05:50-05:54, live "Just teach me" neural-net lesson), engine items, offline:
stale Hint / Not yet cards (advice_clear), the lesson's VS Code view settings + nn5's output order, row boxes as wide as
their text (box_fit) + one caption per changed line, the tight box on the gutter's row, the step-start jump through
the companion (no `code` CLI), and no terminal opened ahead of the ▷.
Run from the repo root:  python -m pytest server/orchestrator/tests/test_t8_engine.py -q"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from server.orchestrator import advice_clear, box_fit, curated, stage, stale_advice
from server.orchestrator import workspace as wsmod
from server.orchestrator.tests.test_run_pointing import (
    FakeExt,
    _demo_at,
    _demo_rig,
    _rows_after_reveal,
    boxes,
    fast,  # noqa: F401 - fixture
    wait_for,
)
from server.orchestrator.tests.test_stage import RANDOM, ZEROS
from server.workspace import core

ROOT = Path(__file__).resolve().parents[3]


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------------------- (1) the stale Hint card

def _clears(rig, mark: int | None = None) -> list[dict]:
    ev = rig.since(mark) if mark is not None else rig.events
    return [e["payload"] for e in ev if e["type"] == "card" and e["payload"].get("dismissAfterMs") == 1]


def test_hint_on_the_stuck_run_goes_once_the_weights_are_random(tmp_path, monkeypatch, fast):  # noqa: F811
    """t8 05:53:09-05:53:37: "Hint 1 of 2: Look at how W1, W2 and W3 start…" stayed up ~15 s after the fix. Now the
    next frame after the weights start random sends that card again with dismissAfterMs 1 (the app closes it)."""
    rig, _ = _demo_rig(tmp_path, monkeypatch)
    ext = FakeExt()
    rig.s._vscode_ext = lambda: ext
    _rows_after_reveal(monkeypatch, ext)

    async def go():
        await _demo_at(rig, 3)
        await rig.s.action("run_command")  # the planned stuck run
        await rig.settle()
        await rig.s.action("hint")
        await rig.settle()
        hint = [c for c in rig.of("card") if c.get("title") == "Hint 1 of 2"]
        assert hint and rig.s._advice_up is not None and rig.s._advice_up["culprit"] == "stuck"
        m = rig.mark()
        await advice_clear.follow(rig.s, force=True)  # still zeros: the card stays
        assert not _clears(rig, m)
        p = rig.workdir / "nn.py"
        p.write_text(p.read_text().replace(ZEROS, RANDOM))
        await rig.s.on_file_change([str(p)])
        await rig.settle()
        await rig.s.on_screen(rig.s.last_obs)  # the next frame
        await rig.settle()
        got = _clears(rig, m)
        assert got and got[-1]["title"] == "Hint 1 of 2" and got[-1]["body"] == hint[-1]["body"]
        assert got[-1]["stepId"] == "nn4" and rig.s._advice_up is None
        n = len(_clears(rig))
        await rig.s.on_screen(rig.s.last_obs)  # once only
        await advice_clear.follow(rig.s, force=True)
        await rig.settle()
        assert len(_clears(rig)) == n

    run(go())


def test_a_newer_card_or_the_learners_close_is_never_cleared(tmp_path, monkeypatch, fast):  # noqa: F811
    """The clear re-sends the card: it must never bring back a card another card replaced or the learner closed."""
    rig, _ = _demo_rig(tmp_path, monkeypatch)
    ext = FakeExt()
    rig.s._vscode_ext = lambda: ext
    _rows_after_reveal(monkeypatch, ext)

    async def go():
        await _demo_at(rig, 3)
        await rig.s.action("run_command")
        await rig.settle()
        await rig.s.action("hint")
        await rig.settle()
        assert rig.s._advice_up is not None
        await rig.s.card_seen(False, "nn4", "Hint 1 of 2", "hint", by="user")  # ✕
        assert rig.s._advice_up is None
        await rig.s.action("hint")  # Hint 2 of 2
        await rig.settle()
        assert rig.s._advice_up is not None
        await rig.s._emit_card({"stepId": "nn4", "kind": "explain", "title": "Why zeros", "body": "…"})
        assert rig.s._advice_up is None  # the Explain card took the slot
        m = rig.mark()
        p = rig.workdir / "nn.py"
        p.write_text(p.read_text().replace(ZEROS, RANDOM))
        await rig.s.on_file_change([str(p)])
        await rig.s.on_screen(rig.s.last_obs)
        await rig.settle()
        assert not _clears(rig, m)

    run(go())


class _S:
    """The bits of LessonSession advice_clear uses."""

    def __init__(self, step: dict, cmd: str | None = None) -> None:
        self.step, self.step_gen, self.passed = step, 1, False
        self.last_offtrack = None
        self._advice_up = None
        self._card_in_use = None
        self.sent: list[tuple[str, dict]] = []
        self._cmd = cmd

    def _run_command(self, step):
        return self._cmd

    def _step_lines(self, step):
        return None, []

    async def emit(self, type_, payload):
        self.sent.append((type_, payload))


OFF = {"stepId": "nn2", "severity": "fail", "title": "Wrong sign in d_h2 tanh slope",
       "body": "In VS Code, change + to - on line 25 of nn.py.",
       "diff": {"file": "nn.py", "yours": "    d_h2 = d_out @ W3.T * (1 + h2 ** 2)",
                "expected": "    d_h2 = d_out @ W3.T * (1 - h2 ** 2)"}, "actions": ["explain", "hint"]}


def test_not_yet_offtrack_card_goes_when_stale_advice_forgets_it():
    """t8 05:53:22: stale_advice dropped "All weights start at zero" (gone) and nothing told the app. The off-track card
    (the app's "Not yet") resting on that diagnosis is cleared: a step card with its words, dismissAfterMs 1."""
    s = _S({"id": "nn2"})
    s.last_offtrack = OFF
    advice_clear.sent_offtrack(s, s.step, OFF, OFF)
    run(advice_clear.forgotten(s, {**OFF, "title": "Something else"}))
    assert not s.sent
    run(advice_clear.forgotten(s, OFF))
    assert s.sent == [("card", {"stepId": "nn2", "kind": "step", "title": OFF["title"], "body": OFF["body"],
                                "dismissAfterMs": 1})]


def test_hint_resting_on_a_diagnosis_goes_when_its_line_is_fixed(monkeypatch):
    """card_copy's "Look at line 25" hint rests on the off-track; its line gone from VS Code's text -> cleared."""
    s = _S({"id": "nn2"})
    s.last_offtrack = OFF
    hint = {"stepId": "nn2", "kind": "hint", "title": "Look at line 25", "body": "Look at the sign in (1 + h2 ** 2).",
            "level": 0}
    advice_clear.sent(s, hint)
    assert s._advice_up["off"]["title"] == OFF["title"]
    states = iter(["", "unsaved"])

    async def state(sess, step, card, anew=False):
        return next(states)

    monkeypatch.setattr(stale_advice, "state", state)
    run(advice_clear.follow(s, force=True))
    assert not s.sent
    s._card_in_use = ("Look at line 25", 0.0, 1)
    run(advice_clear.follow(s, force=True))
    assert s.sent == [("card", {**hint, "dismissAfterMs": 1})] and s._card_in_use is None
    # a plain card (no Hint / Not yet) is never tracked
    advice_clear.sent(s, {"stepId": "nn2", "kind": "answer", "title": "About tanh", "body": "…"})
    assert s._advice_up is None


def test_nothing_to_go_stale_nothing_tracked():
    s = _S({"id": "nn1"})
    advice_clear.sent(s, {"stepId": "nn1", "kind": "hint", "title": "Hint 1 of 2", "body": "Start with X."})
    assert s._advice_up is None


# ------------------------------------------------------------------------------- (2) VS Code view + nn5's output

def test_lesson_settings_turn_off_sticky_scroll_minimap_and_the_startup_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "VSCODE_A11Y", "off")
    monkeypatch.setattr(core, "_voiceover_on", lambda: False)
    (tmp_path / "nn.py").write_text("import numpy as np\n")
    core._write_vscode_settings(tmp_path)
    got = json.loads((tmp_path / ".vscode" / "settings.json").read_text())
    assert got["terminal.integrated.stickyScroll.enabled"] is False
    assert got["editor.minimap.enabled"] is False
    assert got["editor.wordWrap"] == "on"  # the boxes come from the gutter (a number per file line)
    assert got["terminal.integrated.enablePersistentSessions"] is False
    assert got["terminal.integrated.hideOnStartup"] == "whenEmpty"


def test_no_word_wrap_while_the_boxes_use_the_accessibility_caret_row(tmp_path, monkeypatch):
    """The AX caret row counts one screen row per file line: a wrapped line above a box would put it a row off."""
    monkeypatch.setattr(core, "VSCODE_A11Y", "auto")
    core._write_vscode_settings(tmp_path)
    got = json.loads((tmp_path / ".vscode" / "settings.json").read_text())
    assert "editor.wordWrap" not in got and got["terminal.integrated.stickyScroll.enabled"] is False


def test_an_existing_folder_gets_the_new_keys_and_its_own_values_win(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "VSCODE_A11Y", "off")
    monkeypatch.setattr(core, "_voiceover_on", lambda: False)
    p = tmp_path / ".vscode" / "settings.json"
    p.parent.mkdir()
    p.write_text(json.dumps({"editor.minimap.enabled": True, "editor.fontSize": 17}))
    core._write_vscode_settings(tmp_path)
    got = json.loads(p.read_text())
    assert got["editor.minimap.enabled"] is True and got["editor.fontSize"] == 17
    assert got["terminal.integrated.stickyScroll.enabled"] is False and got["editor.wordWrap"] == "on"


def _lesson() -> dict:
    return json.loads(curated.LESSON_FILE.read_text(encoding="utf-8"))


def test_nn5_prints_the_weights_first_and_its_answers_last():
    """The terminal shows its last rows: "[-1.0, 0.0, 1.0]" is the last line nn.py prints (t8: under the drawer)."""
    steps = {s["id"]: s for s in _lesson()["steps"]}
    code = steps["nn5"]["code"].splitlines()
    assert code[-1] == "print((np.round(out, 1) + 0.0).ravel().tolist())"
    assert code[0].startswith("for name, w in ((\"W1\", W1)")
    assert "(np.round(w, 3) + 0.0).tolist()" in code[1]
    for c in steps["nn5"]["checks"] + steps["nn5"]["precision_checks"]:
        assert re.search(c["pattern"], steps["nn5"]["code"]), c["id"]
    good = json.loads(stage.RUNS_FILE.read_text(encoding="utf-8"))["nn6"]["good"]
    assert good[-1] == "[-1.0, 0.0, 1.0]" and re.search(steps["nn6"]["checks"][0]["pattern"], good[-1])
    assert not [ln for ln in good if re.search(r"-0\.0(?!\d)", ln)]
    assert [ln.split()[0] for ln in good if re.match(r"[Wb]\d ", ln)] == ["W1", "b1", "W2", "b2", "W3", "b3"]
    parsed = curated.parse_output(good)
    assert parsed["losses"][-1][1] == 0.0009 and parsed["final"] and len(parsed["final"]["b"]) == 3


# ------------------------------------------------------------------------------- (3) row boxes as wide as their text

def test_fit_narrows_a_full_width_row_to_its_text_and_an_empty_row_to_a_fixed_width():
    row = {"x": 357.7, "y": 423.7, "w": 920.3, "h": 31.2}
    assert box_fit.fit(row, 852.0, "    d_h2 = d_out @ W3.T * (1 - h2 ** 2)")["w"] == pytest.approx(852.0 - 357.7 + 12)
    assert box_fit.fit(row, None, "")["w"] == box_fit.EMPTY_W  # "Type it here" on an empty row
    assert box_fit.fit(row, None, "x = 1") == row  # text not read: unchanged
    assert box_fit.fit(row, 1400.0, "x" * 200)["w"] == 920.3  # never wider than the row
    assert box_fit.fit(row, 380.0, "y = 1")["w"] == box_fit.MIN_W
    assert box_fit.fit({**row, "w": 300.0}, None, "")["w"] == 300.0


def test_progress_box_is_as_wide_as_its_line_and_a_changed_line_says_change(tmp_path, monkeypatch, fast):  # noqa: F811
    """t8 nn2: "Finish this function" boxed the line with the wrong sign (the function was complete) and ran to the
    drawer's edge. The row box ends after the line's text; a line that differs says "Change this line"."""
    rig, _ = _demo_rig(tmp_path, monkeypatch)
    rig.s.screen.reader = object()  # _progress_spot measures rows only with the real reader

    async def go():
        await _demo_at(rig, 1, text="")
        step = rig.s.step
        p = rig.workdir / "nn.py"
        p.write_text(p.read_text() + "\n" + step["code"].replace("(1 - h2 ** 2)", "(1 + h2 ** 2)") + "\n")
        prog = rig.s._code_progress(step)
        assert prog and prog["kind"] == "change"
        line = p.read_text().splitlines()[prog["line"] - 1]
        monkeypatch.setattr(wsmod, "line_location", lambda path, n: {
            "rect": {"x": 357.7, "y": 423.7, "w": 920.3, "h": 31.2}, "text_x2": 357.7 + 11.9 * len(line)})
        spot = await rig.s._progress_spot(step, prog)
        assert spot["caption"] == "Change this line"
        assert spot["rect"]["w"] == pytest.approx(11.9 * len(line) + box_fit.PAD)
        nxt = {**prog, "kind": "next", "line": len(p.read_text().splitlines()) + 1}
        monkeypatch.setattr(wsmod, "line_location", lambda path, n: {
            "rect": {"x": 357.7, "y": 600.0, "w": 920.3, "h": 31.2}})
        spot = await rig.s._progress_spot(step, nxt)
        assert spot["caption"] == "Finish this function" and spot["rect"]["w"] == box_fit.EMPTY_W

    run(go())


def test_one_line_keeps_one_caption(tmp_path, monkeypatch, fast):  # noqa: F811
    """t8 05:51:20-05:51:31: the same line got "Finish this function", "Change + to - here", "Change this line"."""
    rig, _ = _demo_rig(tmp_path, monkeypatch)

    async def go():
        await _demo_at(rig, 1, text="")
        s = rig.s
        s.spot_rect, s._spot_caption = {"x": 357.7, "y": 423.7, "w": 500.0, "h": 31.2}, "Change this line"
        same = {"rect": {"x": 414.4, "y": 428.9, "w": 432.1, "h": 28.3}, "caption": "Change + to - here"}
        assert s._keep_row_caption(same)["caption"] == "Change this line"
        below = {"rect": {"x": 414.4, "y": 460.0, "w": 432.1, "h": 28.3}, "caption": "Change + to - here"}
        assert s._keep_row_caption(below)["caption"] == "Change + to - here"
        other = {"rect": dict(same["rect"]), "caption": "Look here"}
        assert s._keep_row_caption(other)["caption"] == "Look here"

    run(go())


def test_culprit_box_ends_after_the_longest_weights_line(tmp_path, monkeypatch, fast):  # noqa: F811
    """t8 05:53:09: the W1..W3 box ran to the drawer's edge and its caption read "Look at how W1,"."""
    from server.orchestrator import run_pointing

    rig, _ = _demo_rig(tmp_path, monkeypatch)
    ext = FakeExt()
    rig.s._vscode_ext = lambda: ext

    def where(s, path, line):
        if not ext.opened:
            return {"rect": None, "reason": "not_visible", "direction": "down"}
        first = ext.opened[-1][1] - 3
        return {"rect": {"x": 330.0, "y": 200.0 + (line - first) * 18.0, "w": 900.0, "h": 18.0},
                "text_x2": 330.0 + 10.0 * (20 + line % 3)}

    monkeypatch.setattr(run_pointing, "_line_location", where)

    async def go():
        await _demo_at(rig, 3)
        await rig.s.action("run_command")
        await rig.settle()
        await rig.s.action("hint")
        await rig.settle()
        spot = boxes(rig)[-1]
        assert spot["caption"] == "Look at how W1, W2 and W3 start"
        assert spot["rect"]["w"] == pytest.approx(10.0 * 22 + box_fit.PAD)

    run(go())


# ------------------------------------------------------------------------------- (5) the jump without the `code` CLI

def test_automatic_jump_reveals_through_the_companion_not_the_cli():
    calls, reveals = [], []
    ws = wsmod.Workspace(enabled=True, runner=lambda argv: calls.append(argv) or True)
    ws.reveal = lambda path, line: reveals.append((Path(path).name, line)) or True
    ws.front = lambda: False  # VS Code isn't the active app: no jump at all (as the CLI's gate)
    ws.goto("/tmp/lesson/nn.py", 46)
    assert reveals == [] and calls == []
    ws.front = lambda: True
    ws.goto("/tmp/lesson/nn.py", 46)
    assert reveals == [("nn.py", 46)] and calls == []
    ws.reveal = lambda path, line: False  # no lesson window answers: the CLI, as before
    ws.goto("/tmp/lesson/nn.py", 46)
    assert len(calls) == 1 and calls[0][-1].endswith("nn.py:46")
    ws.reveal = lambda path, line: reveals.append(line) or True
    ws.goto("/tmp/lesson/nn.py", 9, explicit=True)  # Do it for me: VS Code comes forward (the CLI)
    assert len(calls) == 2 and reveals == [("nn.py", 46)]


def test_tests_never_reach_a_real_vs_code():
    ws = wsmod.Workspace(enabled=True, runner=lambda argv: True)
    assert ws.reveal is None and ws.run != ws._spawn  # an injected runner: no companion reveal at all
    assert wsmod.Workspace(enabled=True).run == wsmod.Workspace._spawn  # (the real one does reveal)


def test_reveal_line_uses_only_the_window_that_holds_the_file(monkeypatch, tmp_path):
    from server.workspace import vscode_ext as vx

    opened = []
    wins = [{"port": 8791, "folders": ["/other/project"]}, {"port": 8792, "folders": [str(tmp_path)]}]
    monkeypatch.setattr(vx, "windows", lambda timeout=0.3: list(wins))
    monkeypatch.setattr(vx, "open_file", lambda f, line=None, **kw: opened.append((Path(f).name, line, kw)) or
                        {"ok": True})
    assert wsmod.reveal_line(tmp_path / "nn.py", 31) is True
    assert opened == [("nn.py", 31, {"preserve_focus": True, "port": 8792})]
    wins.pop()
    assert wsmod.reveal_line(tmp_path / "nn.py", 31) is False and len(opened) == 1  # another project: never


# ------------------------------------------------------------------------------- (6) no terminal ahead of the ▷

def test_no_terminal_opened_ahead_of_the_run_button(tmp_path, monkeypatch, fast):  # noqa: F811
    """t8: a zsh terminal plus the ▷'s own "Python" one. A run step whose command the ▷ runs gets no terminal opened
    for it (Hint / Show me's box answer included); any other command still does."""
    rig, _ = _demo_rig(tmp_path, monkeypatch)
    opened = []

    async def ensure(step):
        opened.append(step["id"])
        return False

    async def go():
        await _demo_at(rig, 3, text=RANDOM)
        rig.s._ensure_terminal = ensure
        assert rig.s._ptr_runs_it(rig.s.step)
        await rig.s._show_where(rig.s.step)
        assert opened == []
        step = {**rig.s.step, "code": "python3 nn.py --epochs 5"}
        monkeypatch.setattr(rig.s, "_run_command", lambda st: st.get("code") if st is step else "python3 nn.py")
        assert not rig.s._ptr_runs_it(step)

    run(go())


# ------------------------------------------------------------------------------- (4) the tight box on the gutter's row

def _fixture(name: str):
    from server.screen.types import ScreenObservation

    fix = ROOT / "server" / "screen" / "fixtures"
    obs = ScreenObservation.from_dict(json.loads((fix / f"{name}.ocr.json").read_text()))
    return obs, json.loads((fix / f"{name}.truth.json").read_text())


def _src() -> list[str]:
    return (ROOT / "server" / "screen" / "fixtures" / "editor_src" / "pinn_convection.py.txt").read_text().splitlines()


@pytest.mark.parametrize("name", ["vscode_fullscreen_top", "vscode_fullscreen_scrolled", "cursor_fullscreen_bigfont"])
def test_a_text_match_box_gets_the_full_line_boxs_y_and_height(name):
    """t8 frames 05:51:58-05:52:09: the tight "Look here" box sat 3.4 pt below the full-line box of line 25 and cut
    through line 26's text. Snapped: the gutter row's y / height (the full-line box's), its own x / width."""
    from server.screen import lines as L
    from server.screen import match as M

    obs, truth = _fixture(name)
    src = _src()
    checked = 0
    for n in sorted(int(k) for k in truth["lines"]):
        text = src[n - 1].strip()
        if len(text) < 12 or sum(1 for ln in src if ln.strip() == text) > 1:
            continue
        res = M.locate_match(obs, re.escape(text), None)
        row = L.locate_line(obs, "pinn_demo/pinn_convection.py", n)
        if res is None or not row or res.rect.h > 1.6 * row.rect.h or abs(res.rect.cy - row.rect.cy) > row.rect.h:
            continue  # (the same text elsewhere on screen, or a match over two rows)
        snapped = L.snap_rows(obs, res.rect)
        assert snapped is not None, n
        assert (snapped.y, snapped.h) == (row.rect.y, row.rect.h), (n, snapped, row.rect)
        assert (snapped.x, snapped.w) == (res.rect.x, res.rect.w)
        assert row.text_x2 is not None and row.rect.x < row.text_x2 <= row.rect.x2 + 1
        checked += 1
    assert checked >= 5


def test_an_empty_row_has_no_text_end():
    from server.screen import lines as L

    obs, truth = _fixture("vscode_fullscreen_top")
    src = _src()
    blank = next(int(k) for k in sorted(truth["lines"], key=int) if not src[int(k) - 1].strip())
    loc = L.locate_line(obs, "pinn_demo/pinn_convection.py", blank)
    assert loc and loc.text_x2 is None and loc.to_dict()["text_x2"] is None


def test_locate_puts_a_text_match_on_its_editor_row(tmp_path, monkeypatch, fast):  # noqa: F811
    """session._locate (the tight "Look here" box, the off-track's text follow): the editor row's y / height."""
    rig, screen = _demo_rig(tmp_path, monkeypatch)
    screen.text = {"Code": ["    d_h2 = d_out @ W3.T * (1 + h2 ** 2)"]}
    asked = []

    def snap(rect, app=None):
        asked.append(dict(rect))
        return {**rect, "y": rect["y"] - 3.4, "h": rect["h"] - 0.7}

    screen.snap_rows = snap
    spot = rig.s._locate(re.escape("d_h2 = d_out @ W3.T * (1 + h2 ** 2)"), None, "Look here")
    assert asked and spot["rect"] == {**asked[0], "y": asked[0]["y"] - 3.4, "h": asked[0]["h"] - 0.7}
    assert spot["caption"] == "Look here"
    screen.snap_rows = lambda rect, app=None: None  # not on an editor's rows: the match's own box
    assert rig.s._locate(re.escape("d_h2 = d_out"), None, "Look here")["rect"] == asked[0]


def test_the_live_bridge_snaps_through_the_readers_latest_frame():
    from server.orchestrator.screen_bridge import ScreenBridge
    from server.screen import lines as L
    from server.screen import match as M
    from server.screen import reader as rd

    obs, truth = _fixture("vscode_fullscreen_top")
    n = next(int(k) for k in sorted(truth["lines"], key=int) if len(_src()[int(k) - 1].strip()) > 20
             and sum(1 for ln in _src() if ln.strip() == _src()[int(k) - 1].strip()) == 1)
    res = M.locate_match(obs, re.escape(_src()[n - 1].strip()), None)
    reader = NS(latest=lambda: obs)
    reader.snap_rows = lambda rect, app=None: rd.ScreenReader.snap_rows(reader, rect, app)
    bridge = NS(reader=reader, paused=False)
    got = ScreenBridge.snap_rows(bridge, res.rect.to_dict())
    row = L.locate_line(obs, "pinn_demo/pinn_convection.py", n).rect
    assert got["y"] == round(row.y, 1) and got["h"] == round(row.h, 1) and got["x"] == round(res.rect.x, 1)
    assert ScreenBridge.snap_rows(NS(reader=None, paused=False), res.rect.to_dict()) is None
