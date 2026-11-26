"""Run-step pointing after desktop test 7 (run_pointing.py), offline: a fake screen (regions), a fake AX tree and a fake
VS Code companion. Run from the repo root:  python -m pytest server/orchestrator/tests/test_run_pointing.py -q"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from types import SimpleNamespace as NS

import pytest

from server.orchestrator import curated, run_pointing, stage
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.test_session import Rig, _lesson_rig, _run_lesson
from server.orchestrator.tests.test_stage import RANDOM, ZEROS

WIN = {"x": 0.0, "y": 0.0, "w": 1200.0, "h": 900.0}
RUN_BTN = {"x": 1150.0, "y": 60.0, "w": 22.0, "h": 22.0}  # VS Code's editor-title ▷ (~22 pt: the loupe)
TERMINAL = {"x": 260.0, "y": 640.0, "w": 900.0, "h": 220.0}


def run(coro):
    return asyncio.run(coro)


def _code_window(title: str = "nn.py — lesson"):
    return NS(app="Code", windows=[NS(app="Code", title=title, rect=dict(WIN))])


class ButtonLater(FakeScreen):
    """A fake screen whose Run ▷ lookups find nothing until `.button_on` (VS Code still filling its AX tree)."""

    def __init__(self) -> None:
        super().__init__()
        self.regions = {"terminal": dict(TERMINAL)}
        self.button_on = False
        self.looks = 0

    def region(self, name: str, app: str | None = None) -> dict | None:
        if name == "run_button":
            self.looks += 1
            return dict(RUN_BTN) if self.button_on else None
        return super().region(name, app)


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(run_pointing, "RETRY_S", (0.01, 0.01, 0.01, 0.01))
    monkeypatch.setattr(run_pointing, "SLOW_S", 0.01)
    monkeypatch.setattr(run_pointing, "REVEAL_WAIT_S", 0.0)
    for name in ("GRADE_S", "ROW_S", "RUN_S", "STUCK_S"):
        monkeypatch.setattr(stage, name, 0.0)
    monkeypatch.delenv("MIYAGI_STAGE", raising=False)
    monkeypatch.delenv("MIYAGI_STAGE_STUCK", raising=False)


async def wait_for(cond, s: float = 2.0) -> bool:
    end = time.monotonic() + s
    while time.monotonic() < end:
        if cond():
            return True
        await asyncio.sleep(0.01)
    return cond()


def boxes(rig) -> list[dict]:
    return [p for p in rig.of("spotlight") if p.get("rect")]


# ------------------------------------------------------------------------------- (2) Run it for me in a Demo lesson

def _demo_rig(tmp_path, monkeypatch, screen: FakeScreen | None = None, **kw) -> tuple[Rig, FakeScreen]:
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    screen = screen or FakeScreen()
    if not getattr(screen, "regions", None):
        screen.regions = {"terminal": dict(TERMINAL), "run_button": dict(RUN_BTN)}
    rig = Rig(tmp_path, screen=screen, **kw)
    return rig, screen


async def _demo_at(rig: Rig, idx: int, text: str = ZEROS) -> None:
    await rig.s.learn("anything", mode="demo")
    await rig.settle()
    p = rig.workdir / "nn.py"
    p.write_text(p.read_text(encoding="utf-8") + text, encoding="utf-8")
    rig.s.last_obs = _code_window(f"nn.py — {rig.workdir.name}")
    await rig.s.goto_step(idx)
    await rig.settle()


def test_demo_run_steps_offer_run_it_for_me_beside_the_box(tmp_path, monkeypatch, fast):
    """t7: the ▷ / terminal box was up, so the run step's card (Run it for me) never went out; DEMO.md presses it on
    Train it and on See what it learned."""
    rig, _ = _demo_rig(tmp_path, monkeypatch)

    async def go():
        await _demo_at(rig, 3)
        for idx, sid in ((3, "nn4"), (5, "nn6")):
            if sid == "nn6":
                await rig.s.goto_step(idx)
                await rig.settle()
            assert rig.s.step["id"] == sid
            assert await wait_for(lambda: bool(boxes(rig)) and boxes(rig)[-1]["caption"].startswith("Click ▷"))
            cards = [c for c in rig.of("card") if c.get("stepId") == sid and c.get("actions") == ["run_command"]]
            assert cards and cards[-1]["title"] == "Run it", rig.of("card")
            assert not cards[-1].get("targets")  # one box: the card points at nothing itself
        assert boxes(rig)[-1].get("zoom") is True  # the box is still the ▷ (+ loupe): the card didn't take it

    run(go())


def test_normal_lesson_run_step_keeps_just_the_box(tmp_path, monkeypatch, fast):
    """Outside a Demo the run step's box is the answer (Michael loves the ▷ box); the card stays for when no box can go
    up, and Run it for me is on Check's "Not yet" card from the first one."""
    async def build(goal, workdir, on_update=None, **kw):
        return _run_lesson()

    rig, screen, _ = _lesson_rig(tmp_path, monkeypatch, build)
    screen.regions = {"terminal": dict(TERMINAL), "run_button": dict(RUN_BTN)}
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    rig.s.check_wait_s = 0

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s.last_obs = _code_window(f"calc.py — {tmp_path.name}")
        await rig.s.goto_step(1)
        await rig.settle()
        assert await wait_for(lambda: bool(boxes(rig)) and boxes(rig)[-1]["caption"] == "Click ▷ to run calc.py")
        assert not [c for c in rig.of("card") if c.get("title") == "Run it"]
        rig.clock.t += 30
        await rig.s.action("check_step")  # not run yet: "Not yet", with Run it for me on it
        await rig.settle()

    run(go())
    notyet = [c for c in rig.of("card") if c.get("title") == "Not yet"]
    assert notyet and notyet[-1]["actions"][0] == "run_command" and "hint" in notyet[-1]["actions"]


# ------------------------------------------------------------------------------- (3) the Run ▷ AX race

def _run_rig(tmp_path, monkeypatch, with_inputs: bool = False):
    async def build(goal, workdir, on_update=None, **kw):
        return _run_lesson()

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    from server.orchestrator.workspace import Workspace

    screen = ButtonLater()
    rig = Rig(tmp_path, screen=screen, with_inputs=with_inputs)
    rig.s.workspace = Workspace(enabled=False, runner=lambda argv: True)
    rig.s.m.build_text_lesson = build
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    return rig, screen


def test_terminal_box_becomes_the_run_button_once_vs_code_fills_its_ax_tree(tmp_path, monkeypatch, fast, caplog):
    """t7 03:56:31: the lookup that switched VS Code's AX tree on missed the ▷ 2 ms later, the terminal box went up
    and stayed. Now it is looked up again shortly and the terminal box becomes the ▷ box (+ zoom)."""
    rig, screen = _run_rig(tmp_path, monkeypatch)
    caplog.set_level(logging.INFO, logger="orchestrator.session")

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s.last_obs = _code_window(f"calc.py — {tmp_path.name}")
        await rig.s.goto_step(1)
        assert await wait_for(lambda: bool(boxes(rig)))
        first = dict(boxes(rig)[-1])
        assert await wait_for(lambda: screen.looks >= 3)  # looked again while it was missing
        screen.button_on = True
        assert await wait_for(lambda: boxes(rig)[-1]["caption"] == "Click ▷ to run calc.py")
        return first

    first = run(go())
    assert first["caption"] == "Run it here" and first["rect"] == TERMINAL  # the fallback, at once
    last = boxes(rig)[-1]
    assert last.get("zoom") is True and last["rect"]["w"] == 28.0  # Adrian's loupe on the ~22 pt ▷
    assert "no Python extension" not in caplog.text  # a tree still filling in is not a missing extension


def test_demo_train_it_as_in_t7_card_and_late_run_button(tmp_path, monkeypatch, fast):
    """t7's exact nn4 start: the ▷ missed on the first look. Now: Run it for me on the card, the terminal box at once,
    then the ▷ box (+ zoom) once VS Code's tree has it."""
    screen = ButtonLater()
    rig, _ = _demo_rig(tmp_path, monkeypatch, screen=screen)

    async def go():
        await _demo_at(rig, 3)
        assert await wait_for(lambda: bool(boxes(rig)))
        first = dict(boxes(rig)[-1])
        screen.button_on = True
        assert await wait_for(lambda: boxes(rig)[-1]["caption"] == "Click ▷ to run nn.py")
        return first

    first = run(go())
    assert first["caption"] == "Run it here"
    assert [c for c in rig.of("card") if c.get("stepId") == "nn4" and c.get("actions") == ["run_command"]]
    assert boxes(rig)[-1].get("zoom") is True


def test_no_upgrade_once_the_learner_types_in_vs_code(tmp_path, monkeypatch, fast):
    rig, screen = _run_rig(tmp_path, monkeypatch, with_inputs=True)

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s.last_obs = _code_window(f"calc.py — {tmp_path.name}")
        await rig.s.goto_step(1)
        assert await wait_for(lambda: bool(boxes(rig)) and boxes(rig)[-1]["caption"] == "Run it here")
        rig.clock.t += 1
        rig.inputs.key()  # they started typing `python calc.py` at the terminal box
        screen.button_on = True
        await asyncio.sleep(0.2)

    run(go())
    assert boxes(rig)[-1]["caption"] == "Run it here"
    assert not [b for b in boxes(rig) if b["caption"].startswith("Click ▷")]


def test_no_python_extension_is_logged_only_after_the_retries(tmp_path, monkeypatch, fast, caplog):
    rig, screen = _run_rig(tmp_path, monkeypatch)
    monkeypatch.setattr(run_pointing, "UPGRADE_FOR_S", 0.3)
    caplog.set_level(logging.INFO, logger="orchestrator.session")

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s.last_obs = _code_window(f"calc.py — {tmp_path.name}")
        await rig.s.goto_step(1)
        assert await wait_for(lambda: "no Python extension" in caplog.text)
        return screen.looks

    looks = run(go())
    assert looks >= len(run_pointing.RETRY_S) + 1
    assert boxes(rig)[-1]["caption"] == "Run it here"  # the terminal box stays


def test_ax_lookup_that_misses_while_the_tree_fills_in_says_settling(monkeypatch):
    """A fake AX tree: the lookup that switches the tree on, then an empty tree, then the filled-in one."""
    ax = pytest.importorskip("server.screen.ax")

    class El(dict):
        __hash__ = object.__hash__

    def button():
        return El(AXRole="AXButton", AXDescription="Run Python File", rect=(1150.0, 60.0, 22.0, 22.0))

    def tree(n_groups: int, with_button: bool) -> El:
        kids = [El(AXRole="AXGroup", AXChildren=[El(AXRole="AXGroup") for _ in range(3)]) for _ in range(n_groups)]
        if with_button:
            kids.append(El(AXRole="AXGroup", AXChildren=[button()]))
        return El(AXRole="AXWindow", AXChildren=kids)

    state = {"win": None}
    monkeypatch.setattr(ax, "_code_app", lambda folder=None: (4242, state["win"]))
    monkeypatch.setattr(ax, "attr", lambda el, name: el.get(name) if isinstance(el, dict) else None)
    monkeypatch.setattr(ax, "rect_of", lambda el: ax.Rect(*el["rect"]) if isinstance(el, dict) and "rect" in el
                        else None)
    ax._run_cache.clear()
    monkeypatch.setitem(ax._enabled_pids, 4242, time.time())  # just switched on
    ax._ready_pids.discard(4242)
    assert ax.find_run_button() is None and ax.last_miss() == "settling"  # (pid, None): the tree is being switched on
    ax._ready_pids.add(4242)
    state["win"] = tree(1, False)
    assert ax.find_run_button() is None and ax.last_miss() == "settling"  # ready, but filled in moments ago
    monkeypatch.setitem(ax._enabled_pids, 4242, time.time() - 60)
    assert ax.find_run_button() is None and ax.last_miss() == "settling"  # a tree this empty isn't filled in yet
    state["win"] = tree(20, False)
    assert ax.find_run_button() is None and ax.last_miss() == "absent"  # a real window without the ▷
    state["win"] = tree(20, True)
    found = ax.find_run_button()
    assert found is not None and found.rect.w == 22.0 and ax.last_miss() is None
    ax._run_cache.clear()
    ax._ready_pids.discard(4242)


def test_reader_keeps_a_settling_miss_only_for_a_moment(monkeypatch):
    ax = pytest.importorskip("server.screen.ax")
    from server.screen import reader as rd

    clock = {"t": 1000.0}
    monkeypatch.setattr(rd, "time", NS(time=lambda: clock["t"]))
    monkeypatch.setattr(rd.sys, "platform", "darwin")
    monkeypatch.setattr(ax, "trusted", lambda prompt=False: True)
    answers = [(None, "settling"), (None, "absent"), (ax.Rect(1150.0, 60.0, 22.0, 22.0), None)]
    calls = []

    def find(folder=None):
        rect, why = answers[len(calls)]
        calls.append(folder)
        ax._misses.pop("run_button", None) if why is None else ax._misses.__setitem__("run_button", why)
        return NS(rect=rect) if rect is not None else None

    monkeypatch.setattr(ax, "find_run_button", find)
    me = NS(use_ax=True, _run_btn=(0.0, None, 0.0), _lesson_folder="/tmp/lesson",
            AX_SETTLING_KEEP_S=rd.ScreenReader.AX_SETTLING_KEEP_S)
    me._ax_keep = lambda key, rect, absent_s: rd.ScreenReader._ax_keep(me, key, rect, absent_s)
    look = lambda: rd.ScreenReader._ax_run_button(me)  # noqa: E731
    assert look() is None and len(calls) == 1  # settling: kept 0.25 s
    clock["t"] += 0.3
    assert look() is None and len(calls) == 2  # looked again at once; this miss is a real one: kept 6 s
    clock["t"] += 3.0
    assert look() is None and len(calls) == 2
    clock["t"] += 3.5
    assert look() is not None and len(calls) == 3
    ax._misses.pop("run_button", None)


def test_t11_run_button_found_after_vscode_was_quit_and_reopened(monkeypatch, tmp_path):
    """t11 (Nov 15, 08:42, nn4 of the Just teach me lesson): the engine started at 08:35:53 with VS Code (pid 62432) in
    front; VS Code was quit and reopened at 08:40:33 (pid 3452). NSWorkspace.frontmostApplication never updates in the
    engine (no AppKit run loop), so every Run ▷ lookup asked the dead 62432: no window, "VS Code's Run ▷ isn't found
    (yet)", and the step boxed the terminal panel ("Run it here") instead of the ▷ with its zoom. A dead VS Code is
    passed over: the running one's window is walked and its ▷ found."""
    import subprocess
    import sys

    ax = pytest.importorskip("server.screen.ax")
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    dead, live = p.pid, os.getpid()  # the VS Code quit at 08:40 / the one running now

    class El(dict):
        __hash__ = object.__hash__

    def app(pid):
        return NS(processIdentifier=lambda: pid, bundleIdentifier=lambda: "com.microsoft.VSCode")

    nn = tmp_path / "nn.py"
    button = El(AXRole="AXButton", AXDescription="Run Python File", rect=(1176.0, 124.0, 28.0, 28.0))
    kids = [El(AXRole="AXGroup", AXChildren=[El(AXRole="AXGroup") for _ in range(3)]) for _ in range(20)]
    win = El(AXRole="AXWindow", AXDocument=f"file://{nn}", AXChildren=kids + [El(AXRole="AXGroup", AXChildren=[button])])
    apps = {dead: El(), live: El(AXWindows=[win], AXFocusedWindow=win)}  # a dead app answers no AX reads
    stale = app(dead)
    monkeypatch.setattr(ax, "NSWorkspace", NS(sharedWorkspace=lambda: NS(frontmostApplication=lambda: stale)))
    monkeypatch.setattr(ax, "NSRunningApplication", NS(runningApplicationsWithBundleIdentifier_=lambda b: (
        [stale, app(live)] if b == "com.microsoft.VSCode" else [])))
    monkeypatch.setattr(ax, "AX", NS(AXUIElementCreateApplication=lambda pid: apps.get(pid, El()),
                                     AXUIElementSetMessagingTimeout=lambda el, t: None))
    monkeypatch.setattr(ax, "enable_electron_ax", lambda app_el, pid: True)
    monkeypatch.setattr(ax, "attr", lambda el, name: el.get(name) if isinstance(el, dict) else None)
    monkeypatch.setattr(ax, "rect_of", lambda el: ax.Rect(*el["rect"]) if isinstance(el, dict) and "rect" in el
                        else None)
    ax._run_cache.clear()
    try:
        assert ax._code_app(str(tmp_path)) == (live, win)  # never the stale front app's dead pid
        found = ax.find_run_button(str(tmp_path))
        assert found is not None and found.rect.x == 1176.0 and ax.last_miss() is None
        apps.pop(live)  # VS Code not running at all: no app, nothing walked
        monkeypatch.setattr(ax, "NSRunningApplication", NS(runningApplicationsWithBundleIdentifier_=lambda b: (
            [stale] if b == "com.microsoft.VSCode" else [])))
        assert ax._code_app(str(tmp_path)) == (None, None)
    finally:
        ax._run_cache.clear()
        ax._misses.pop("run_button", None)


# ------------------------------------------------------------------------------- (4) the culprit lines

class FakeExt:
    """The VS Code companion: /open reveals a line (preserveFocus) and VS Code scrolls there."""

    def __init__(self) -> None:
        self.opened: list[tuple] = []

    def open_file(self, file, line=None, *, column=None, folder=None, preserve_focus=False, port=None):
        self.opened.append((os.path.basename(str(file)), line, preserve_focus))
        return {"ok": True}


def _rows_after_reveal(monkeypatch, ext: FakeExt, top: float = 200.0, pitch: float = 18.0) -> list[int]:
    """Line rects as VS Code's gutter gives them: none until the companion scrolled there (the lines were off
    screen), then one row per line."""
    asked: list[int] = []

    def where(s, path, line):
        asked.append(line)
        if not ext.opened:
            return {"rect": None, "reason": "not_visible", "direction": "down"}
        first = ext.opened[-1][1] - 3
        return {"rect": {"x": 330.0, "y": top + (line - first) * pitch, "w": 700.0, "h": pitch}}

    monkeypatch.setattr(run_pointing, "_line_location", where)
    return asked


def _line_of(rig: Rig, text: str) -> int:
    return next(i for i, ln in enumerate((rig.workdir / "nn.py").read_text(encoding="utf-8").splitlines(), 1) if ln.startswith(text))


def test_demo_hint_on_the_stuck_run_boxes_w1_to_w3_not_the_run_button(tmp_path, monkeypatch, fast):
    """t7: "Not yet · Loss is stuck at 0.49", Hint 1 "Look at how W1, W2 and W3 start…", and the box was the ▷.
    Now the box is on the W1..W3 lines, scrolled there by the companion (preserving focus) before it is measured; once
    they start random the ▷ is back, and it goes with the rerun."""
    rig, _ = _demo_rig(tmp_path, monkeypatch)
    ext = FakeExt()
    rig.s._vscode_ext = lambda: ext
    _rows_after_reveal(monkeypatch, ext)

    async def go():
        await _demo_at(rig, 3)
        await rig.s.action("run_command")  # the planned stuck run
        await rig.settle()
        assert rig.of("offtrack") and curated._stuck_here(rig.s, rig.s.step)
        m = rig.mark()
        await rig.s.action("hint")
        await rig.settle()
        ev = rig.since(m)
        spots = [e["payload"] for e in ev if e["type"] == "spotlight" and e["payload"].get("rect")]
        cards = [e["payload"] for e in ev if e["type"] == "card"]
        w1, w3 = _line_of(rig, "W1 ="), _line_of(rig, "W3 =")
        assert ext.opened == [("nn.py", (w1 + w3) // 2, True)]  # scrolled there first, the focus left alone
        assert spots and spots[-1]["caption"] == "Look at how W1, W2 and W3 start"
        r = spots[-1]["rect"]
        assert r["y"] == 200.0 + 3 * 18.0 - ((w1 + w3) // 2 - w1) * 18.0 and r["h"] == (w3 - w1 + 1) * 18.0
        assert not [s for s in spots if s["caption"].startswith("Click ▷")]
        assert cards and cards[-1]["title"] == "Hint 1 of 2"
        # Show me says the same place
        await rig.s.action("show_me")
        await rig.settle()
        assert boxes(rig)[-1]["caption"] == "Look at how W1, W2 and W3 start"
        # they start them random and save: a rerun is next, so the ▷ is back (not under a keystroke)
        p = rig.workdir / "nn.py"
        p.write_text(p.read_text(encoding="utf-8").replace(ZEROS, RANDOM), encoding="utf-8")
        await rig.s.on_file_change([str(p)])
        await rig.settle()
        await rig.s._run_box_done()  # the next frame
        await rig.settle()
        assert boxes(rig)[-1]["caption"] == "Click ▷ to run nn.py" and boxes(rig)[-1].get("zoom")
        # Hint now points at the ▷ too (the code changed; the stuck run is old)
        assert run_pointing.culprit(rig.s, rig.s.step) is None
        # the rerun starts: that ▷ box has done its job
        await rig.s.ingest({"kind": "run_started", "run_id": "again", "command": "python3 nn.py"})
        await rig.s._run_box_done()
        await rig.settle()
        assert rig.of("spotlight")[-1] == {"clear": True}

    run(go())


def test_no_box_rather_than_the_run_button_when_the_culprit_isnt_on_screen(tmp_path, monkeypatch, fast):
    rig, _ = _demo_rig(tmp_path, monkeypatch)
    monkeypatch.setattr(run_pointing, "_line_location", lambda s, path, line: {})  # no gutter / AX row anywhere

    async def go():
        await _demo_at(rig, 3)
        await rig.s.action("run_command")
        await rig.settle()
        n = len(boxes(rig))
        await rig.s.action("hint")
        await rig.settle()
        assert len(boxes(rig)) == n  # no box (never "Click ▷", which says "run it again")
        assert rig.of("card")[-1]["title"] == "Hint 1 of 2"  # the hint itself still answers

    run(go())


def _nn_lesson_rig(tmp_path, monkeypatch):
    async def build(goal, workdir, on_update=None, **kw):
        return _run_lesson()

    rig, screen, _ = _lesson_rig(tmp_path, monkeypatch, build)
    screen.regions = {"terminal": dict(TERMINAL), "run_button": dict(RUN_BTN)}
    return rig, screen


CALC = "def add(a, b):\n    return a + b\n\nprint(total(1, 2))\n\ndef total(a, b):\n    return add(a, b)\n"
NAME_ERROR = ["Traceback (most recent call last):", '  File "{f}", line 4, in <module>', "    print(total(1, 2))",
              "          ^^^^^", "NameError: name 'total' is not defined"]


def test_show_me_after_a_name_error_boxes_the_line_that_raised_it(tmp_path, monkeypatch, fast):
    """t6: forward() called before its def: the run's NameError line is the culprit, not the ▷."""
    rig, _ = _nn_lesson_rig(tmp_path, monkeypatch)
    calc = tmp_path / "calc.py"
    calc.write_text(CALC, encoding="utf-8")
    old = time.time() - 30
    os.utime(calc, (old, old))
    ext = FakeExt()
    rig.s._vscode_ext = lambda: ext
    _rows_after_reveal(monkeypatch, ext)

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s.last_obs = _code_window(f"calc.py — {tmp_path.name}")
        await rig.s.goto_step(1)
        await rig.settle()
        await rig.s.ingest({"kind": "run_started", "run_id": "r1", "command": "python calc.py"})
        await rig.s.ingest({"kind": "output", "run_id": "r1", "lines": [ln.format(f=calc) for ln in NAME_ERROR]})
        await rig.s.ingest({"kind": "run_ended", "run_id": "r1", "exit_code": 1})
        await rig.settle()
        rig.s.last_offtrack = None  # whatever the stub coach said: the traceback alone decides here
        assert run_pointing.culprit(rig.s, rig.s.step)["first"] == 4
        await rig.s.action("show_me")
        await rig.settle()
        assert ext.opened and ext.opened[-1] == ("calc.py", 4, True)
        assert boxes(rig)[-1]["caption"] == "total is used before it's defined"
        # they move the call below the def and save: the file changed since that run, a rerun is next
        calc.write_text(CALC.replace("print(total(1, 2))\n\n", "") + "\nprint(total(1, 2))\n", encoding="utf-8")
        later = time.time() + 5  # saved a few seconds after that run began
        os.utime(calc, (later, later))
        assert run_pointing.culprit(rig.s, rig.s.step) is None
        rig.clock.t += 20
        await rig.s.action("show_me")
        await rig.settle()
        assert boxes(rig)[-1]["caption"] == "Click ▷ to run calc.py"

    run(go())


def test_a_diagnosed_line_is_the_culprit_while_it_is_still_in_the_file(tmp_path, monkeypatch, fast):
    """t6 CP10: "Wrong sign in tanh slope: change + to - on line 23 of nn.py"."""
    rig, _ = _nn_lesson_rig(tmp_path, monkeypatch)
    calc = tmp_path / "calc.py"
    calc.write_text("def slope(h):\n    return 1 + h ** 2\n", encoding="utf-8")

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        await rig.s.goto_step(1)
        await rig.settle()
        await rig.s.ingest({"kind": "run_started", "run_id": "r1", "command": "python calc.py"})
        await rig.s.ingest({"kind": "run_ended", "run_id": "r1", "exit_code": 0})
        await rig.settle()
        sid = rig.s.step["id"]
        rig.s.check_state = {"c": {"label": "loss", "status": "fail"}}
        rig.s.last_offtrack = {"stepId": sid, "title": "Wrong sign in tanh slope",
                               "diff": {"yours": "return 1 + h ** 2", "expected": "return 1 - h ** 2"}}
        c = run_pointing.culprit(rig.s, rig.s.step)
        assert (c["first"], c["last"], c["caption"]) == (2, 2, "Change to: return 1 - h ** 2")
        rig.s.last_offtrack = {"stepId": sid, "title": "Wrong sign in tanh slope",
                               "body": "Change + to - on line 2 of calc.py."}
        c = run_pointing.culprit(rig.s, rig.s.step)
        assert (c["first"], c["caption"]) == (2, "Wrong sign in tanh slope")
        rig.s.last_offtrack = {"stepId": sid, "title": "Wrong sign",
                               "diff": {"yours": "return 1 + h ** 2", "expected": "return 1 - h ** 2"}}
        calc.write_text("def slope(h):\n    return 1 - h ** 2\n", encoding="utf-8")  # fixed: the ▷ is next
        assert run_pointing.culprit(rig.s, rig.s.step) is None

    run(go())


def test_stuck_culprit_is_the_weights_that_start_the_same():
    lines = ["import numpy as np", "W1 = np.zeros((1, 4))", "b1 = np.zeros((1, 4))", "W2 = np.random.randn(4, 4)",
             "b2 = np.zeros((1, 4))", "W3 = np.ones((4, 1))", "for e in range(9):", "    W1 -= 0.1 * dW1"]
    c = run_pointing._stuck_lines(lines)
    assert (c["first"], c["last"], c["caption"]) == (2, 6, "Look at how W1 and W3 start")
    assert run_pointing._stuck_lines([ln.replace("zeros", "random.randn").replace("ones", "random.randn")
                                      for ln in lines if ln.startswith("W")]) is None
