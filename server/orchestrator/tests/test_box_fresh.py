"""Desktop test 7 (Nov 15, Demo mode): the "Type it here" box after VS Code scrolls. Run from the repo root:
    python -m pytest server/orchestrator/tests/test_box_fresh.py -q

Test 7, steps nn2 and nn3: the box went up ~0.4 s after step.started from Accessibility line rects read while VS Code
was still scrolled where the last step left it; then the step start's jump (`code -g nn.py:<comment>` and the
companion's reveal both centre the line, even one already on screen) scrolled the editor 7 / 8 rows and the box stayed
at the old screen y (below the end of the file). FakeVSCode replays that: AX rows from the current scroll, the
companion's /state (visibleRanges, lineCount), and jumps / reveals that land `lag` seconds after they are asked for.
Nothing here touches the real editor: the companion's HTTP is cut off and every read is the fake's.
"""
from __future__ import annotations

import asyncio
import time
import types
from pathlib import Path

import pytest

from server.orchestrator import curated, stage, where_row
from server.orchestrator import workspace as wsmod
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.test_session import Rig
from server.workspace import vscode_ext

STARTER = curated.STARTER_FILE.read_text(encoding="utf-8")
STEPS = {s["id"]: s for s in (curated.lesson_for("x", force=True) or {}).get("steps", [])}


def _pasted(text: str, comment: str, code: str) -> str:
    """`code` pasted on the empty line under `comment` (the presenter's paste: the line's newline stays after it)."""
    lines = text.split("\n")
    i = lines.index(comment)
    return "\n".join(lines[:i + 1] + code.rstrip("\n").split("\n") + lines[i + 1:])


# nn.py as it was in test 7: nn1 pasted under `# The network` (29 lines, `# Backprop` on 22), then nn2 under
# `# Backprop` (34 lines, `# Training` on 30)
NN1_DONE = _pasted(STARTER, "# The network", STEPS["nn1"]["code"])
NN2_DONE = _pasted(NN1_DONE, "# Backprop", STEPS["nn2"]["code"])


class FakeVSCode:
    """The lesson's VS Code window as Miyagi sees it. Row geometry from test 7's log: line rows 18 pt apart, the first
    visible row's top at y=122.8 (nn2's box for line 23 at top=1 went up at y=518.8), ROWS rows on screen."""

    X, W, Y0, H, ROWS = 412.9, 755.1, 122.8, 18.0, 28
    PORT = 8791

    def __init__(self, path: Path, top: int = 1, lag: float = 0.5) -> None:
        self.path, self.top, self.lag = Path(path), top, lag
        self.caret = 1
        self.buffer: str | None = None  # VS Code's text when it differs from the disk (not reloaded yet)
        self.jumps: list[tuple[str, int]] = []
        self.ax_stale_s = 0.0  # Accessibility answers with the scroll from this long ago

        self._history: list[tuple[float, int]] = [(0.0, top)]

    # -- the editor
    def text(self) -> str:
        return self.buffer if self.buffer is not None else self.path.read_text(encoding="utf-8")

    def line_count(self) -> int:
        return len(self.text().split("\n"))

    def scroll(self, top: int) -> None:
        self.top = max(1, min(int(top), self.line_count()))
        self._history.append((time.monotonic(), self.top))

    def centre(self, line: int) -> None:
        """VS Code's reveal (`code -g`, the companion's /open: InCenter): the line in the middle, also one on screen."""
        self.caret = line
        self.scroll(line - self.ROWS // 2)

    def row_y(self, line: int, top: int | None = None) -> float:
        return self.Y0 + (line - (self.top if top is None else top)) * self.H

    def reload(self) -> None:
        """VS Code reads the file from disk again (it was changed behind its back): a shorter file clamps the scroll."""
        self.buffer = None
        self.scroll(min(self.top, self.line_count()))

    loop: asyncio.AbstractEventLoop | None = None  # the test's loop (the companion is called from worker threads)

    def _later(self, fn, *args) -> None:
        self.loop.call_soon_threadsafe(self.loop.call_later, self.lag, fn, *args)

    # -- Accessibility (server.orchestrator.workspace.line_location): caret-anchored rows of the current scroll
    def line_location(self, path, line: int) -> dict:
        top = self.top
        if self.ax_stale_s:
            cut = time.monotonic() - self.ax_stale_s
            top = next((t for when, t in reversed(self._history) if when <= cut), self._history[0][1])
        if top <= line < top + self.ROWS:
            return {"rect": {"x": self.X, "y": self.row_y(line, top), "w": self.W, "h": self.H}, "source": "ax",
                    "reason": None, "line_height": self.H}
        return {"rect": None, "source": None, "reason": "not_visible", "direction": "up" if line < top else "down"}

    # -- `code -r -g nn.py:<line>` (Workspace.goto): lands `lag` s later
    def cli_goto(self, path, line: int, explicit: bool = False) -> None:
        self.jumps.append(("cli", int(line)))
        self._later(self.centre, int(line))

    # -- the companion extension (server.workspace.vscode_ext)
    def state(self) -> dict:
        return {"ok": True, "app": "vscode", "port": self.PORT, "folders": [str(self.path.parent)],
                "file": str(self.path), "dirty": False, "lineCount": self.line_count(),
                "cursor": {"line": self.caret, "column": 1},
                "visibleRanges": [{"startLine": self.top, "endLine": min(self.top + self.ROWS - 1, self.line_count())}],
                "openFiles": [{"file": str(self.path)}], "dirtyFiles": [], "windowFocused": True, "lastFocusedAt": 1}

    def windows(self, timeout: float = 0.3) -> list[dict]:
        return [self.state()]

    def open_file(self, file, line=None, *, column=None, folder=None, preserve_focus=False, port=None) -> dict:
        self.jumps.append(("open", int(line or 0)))
        if line:
            self._later(self.centre, int(line))
        return {"ok": True, "file": str(file), "line": line}

    def buffer_text(self, file=None, *, folder=None, port=None, timeout=0.3) -> dict:
        return {"ok": True, "file": str(self.path), "text": self.text(), "dirty": False, "lineCount": self.line_count()}


@pytest.fixture
def vs(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.delenv("MIYAGI_STAGE", raising=False)
    monkeypatch.delenv("MIYAGI_STAGE_STUCK", raising=False)
    for name in ("GRADE_S", "ROW_S", "RUN_S", "STUCK_S"):
        monkeypatch.setattr(stage, name, 0.0)
    fake = FakeVSCode(tmp_path / "nn.py")
    # never the real editor: no companion HTTP at all, no window raised; every read is the fake's
    monkeypatch.setattr(vscode_ext, "_http", lambda *a, **k: None)
    monkeypatch.setattr(vscode_ext, "windows", fake.windows)
    monkeypatch.setattr(vscode_ext, "open_file", fake.open_file)
    monkeypatch.setattr(vscode_ext, "buffer_text", fake.buffer_text)
    monkeypatch.setattr(where_row, "_raise_window", lambda *a, **k: None)
    monkeypatch.setattr(wsmod, "line_location", fake.line_location)
    return fake


def _rig(tmp_path: Path, fake: FakeVSCode) -> Rig:
    screen = FakeScreen()
    screen.reader = types.SimpleNamespace()  # "the real screen reader is running": AX rows, the companion
    rig = Rig(tmp_path, screen=screen)
    ws = wsmod.Workspace(enabled=False, runner=lambda argv: True)
    ws.goto = fake.cli_goto  # the step start's `code -g`
    rig.s.workspace = ws
    return rig


def run(coro):
    return asyncio.run(coro)


async def _settle(rig: Rig) -> None:
    for _ in range(4):
        await rig.settle()
        await asyncio.sleep(0)


async def _demo_at(rig: Rig, fake: FakeVSCode, text: str, step: str) -> None:
    """The Demo lesson, nn.py holding `text`, VS Code open on it; then the presenter's save passes steps up to `step`."""
    fake.loop = asyncio.get_running_loop()
    await rig.s.learn("anything", mode="demo")
    await _settle(rig)
    rig.s.editor_open = True
    fake.path.write_text(text, encoding="utf-8")
    while rig.s.step["id"] != step:
        rig.clock.t += 5  # past the step's first seconds (stage ignores a save in them)
        await rig.s.on_file_change([str(fake.path)])
        await _settle(rig)
    await asyncio.sleep(fake.lag + 0.05)  # the earlier steps' jumps have landed


def _boxes(rig: Rig, mark: int) -> list[dict]:
    return [e["payload"] for e in rig.since(mark) if e["type"] == "spotlight" and "rect" in e["payload"]]


async def _trace(rig: Rig, since: int, secs: float) -> list[tuple[float, float | None]]:
    """(monotonic time, y; None for a clear) of every spotlight sent since `since`, watched for `secs`."""
    out: list[tuple[float, float | None]] = []
    seen = since
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        await asyncio.sleep(0.01)
        ev = rig.events
        for e in ev[seen:]:
            if e["type"] == "spotlight":
                out.append((time.monotonic(), e["payload"]["rect"]["y"] if "rect" in e["payload"] else None))
        seen = len(ev)
    return out


def _last(trace: list) -> float | None:
    """The box's y at the end of the trace (None: no box)."""
    return trace[-1][1] if trace else None


def _landed(fake: FakeVSCode, top: int, after: float) -> float:
    """When the editor's scroll reached `top` (monotonic)."""
    return next(t for t, tp in fake._history if tp == top and t >= after)


async def _to_step(rig: Rig, fake: FakeVSCode, sid: str) -> int:
    """The presenter's save passes the step before `sid`. -> the event mark before it."""
    m = rig.mark()
    rig.clock.t += 5
    await rig.s.on_file_change([str(fake.path)])
    await _settle(rig)
    assert rig.s.step["id"] == sid
    return m


def _near(y: float | None, want: float) -> bool:
    return y is not None and abs(y - want) <= 2.0


# (step, file before the step's paste, where the editor was, its section comment's line, the row under it, where
#  `code -g <comment>` scrolls to): test 7's nn2 and nn3
T7 = [("nn2", NN1_DONE, 1, 22, 23, 8), ("nn3", NN2_DONE, 8, 30, 31, 16)]
PREV = {"nn2": "nn1", "nn3": "nn2"}


@pytest.mark.parametrize("lag", [0.5, 1.8], ids=["jump-0.5s", "jump-1.8s"])
@pytest.mark.parametrize("sid,text,top,comment,row,after", T7, ids=[t[0] for t in T7])
def test_t7_type_box_follows_the_step_start_jump(tmp_path, vs, sid, text, top, comment, row, after, lag):
    """The exact test-7 sequence: step.started -> the box from AX rows at the old scroll -> the step start's jump
    lands and VS Code centres the section comment -> the box is on the row under it within ~1 s of the scroll (t6's
    follow re-read the row 1.0 s and 3.5 s after the box went up: a jump landing 1.8 s in left it stale ~1.7 s). A
    jump that lands within the first second: the box goes up once, on the right row, never first on the old one."""
    rig = _rig(tmp_path, vs)
    vs.top, vs.lag = top, lag

    async def go():
        await _demo_at(rig, vs, text, PREV[sid])
        vs.scroll(top)
        t0 = time.monotonic()
        m = await _to_step(rig, vs, sid)
        assert ("cli", comment) in vs.jumps  # the step start's own jump to the section comment
        trace = await _trace(rig, m, lag + 1.5)
        want = vs.row_y(row, after)
        assert vs.top == after
        assert _near(_last(trace), want), f"{sid}: boxes {trace}, want y={want}"
        moved = next(t for t, y in trace if _near(y, want))
        assert moved - _landed(vs, after, t0) <= 1.0, f"{sid}: the box followed {moved - _landed(vs, after, t0):.2f} s late"
        if lag < 1.0:  # the jump landed while the first box waited for it: one box, on the right row
            assert [y for _, y in trace if y is not None] == [want], trace
        assert _boxes(rig, m)[-1]["caption"] == "Type it here"
        await asyncio.sleep(0.6)  # and it stays there
        assert _near(_boxes(rig, m)[-1]["rect"]["y"], want)

    run(go())


def test_t7_reveal_racing_the_box_and_slow_accessibility(tmp_path, vs):
    """nn2 starts with the editor scrolled away from its row (line 23 off screen, as the t6 persona's "VS Code opened
    scrolled to the bottom"): the step start's `code -g` (line 22) and the companion's reveal (start_hold, line 23)
    both land 0.4 s later, and Accessibility answers with the scroll from 0.1 s before. The box ends on line 23 as the
    editor finally shows it."""
    rig = _rig(tmp_path, vs)
    vs.lag = 0.4

    async def go():
        await _demo_at(rig, vs, NN1_DONE, "nn1")
        vs.scroll(26)  # line 23 is above the screen
        vs.ax_stale_s = 0.1
        m = await _to_step(rig, vs, "nn2")
        trace = await _trace(rig, m, 2.0)
        assert ("cli", 22) in vs.jumps
        assert vs.top in (8, 9)  # code -g centred line 22, the companion's reveal line 23
        assert _near(_last(trace), vs.row_y(23)), (trace, vs.row_y(23), vs.jumps)

    run(go())


def test_t7_box_on_the_new_row_when_the_line_count_changes(tmp_path, vs):
    """The file on disk changed before VS Code reloaded it (29 lines in the editor, 31 on disk: two lines pasted
    above `# Backprop`, now on line 24): the box goes on the disk's row (25) and stays on it through the reload and
    the jump. Then a paste above it with the box up (two more lines, no scroll): it moves to the new row (27) within
    ~1 s, re-planned from the file."""
    rig = _rig(tmp_path, vs)
    vs.lag = 0.5

    async def go():
        await _demo_at(rig, vs, NN1_DONE, "nn1")
        vs.scroll(1)
        vs.buffer = NN1_DONE  # what VS Code shows
        vs.path.write_text("\n\n" + NN1_DONE, encoding="utf-8")  # what the save wrote
        asyncio.get_running_loop().call_later(0.9, vs.reload)
        m = await _to_step(rig, vs, "nn2")
        trace = await _trace(rig, m, 1.8)
        assert vs.buffer is None and ("cli", 24) in vs.jumps and vs.top == 10
        assert _near(_last(trace), vs.row_y(25)), (trace, vs.row_y(25))
        m2 = rig.mark()
        t0 = time.monotonic()
        vs.path.write_text("\n\n" + vs.path.read_text(encoding="utf-8"), encoding="utf-8")  # a paste above it
        trace = await _trace(rig, m2, 1.0)
        assert _near(_last(trace), vs.row_y(27)), (trace, vs.row_y(27))
        assert trace[-1][0] - t0 <= 1.0

    run(go())


def test_t7_row_scrolled_off_screen_takes_the_box_down_until_it_is_back(tmp_path, vs):
    """The learner scrolls line 23 off screen: the box goes (never a box over whatever scrolled under it) and no jump
    pulls the editor back; scrolled back, the box returns on its row."""
    from server.orchestrator import box_follow

    rig = _rig(tmp_path, vs)
    vs.lag = 0.3

    async def go():
        await _demo_at(rig, vs, NN1_DONE, "nn1")
        vs.scroll(1)
        await _to_step(rig, vs, "nn2")
        await asyncio.sleep(1.0)
        assert rig.s.spot_rect is not None and _near(rig.s.spot_rect["y"], vs.row_y(23))
        jumps = list(vs.jumps)
        m = rig.mark()
        vs.scroll(26)  # the learner's scroll: line 23 above the screen
        trace = await _trace(rig, m, 0.8)
        assert trace and trace[-1][1] is None, trace  # the box went
        assert box_follow.hidden(rig.s, rig.s._insert_at)
        assert vs.jumps == jumps and vs.top == 26  # no jump back
        m = rig.mark()
        vs.scroll(12)
        trace = await _trace(rig, m, 0.8)
        assert _near(_last(trace), vs.row_y(23)), trace
        assert not box_follow.hidden(rig.s, rig.s._insert_at)

    run(go())


def test_t7_companion_visible_event_moves_the_box_at_once(tmp_path, vs, monkeypatch):
    """Companion 0.0.5's `visible` event (POST /vscode/event) re-places the box without waiting for the poll."""
    from server.orchestrator import box_follow

    rig = _rig(tmp_path, vs)
    vs.lag = 0.2

    async def go():
        await _demo_at(rig, vs, NN1_DONE, "nn1")
        vs.scroll(1)
        await _to_step(rig, vs, "nn2")
        await asyncio.sleep(1.2)
        monkeypatch.setattr(box_follow, "WATCH_FAST_S", 30.0)  # the poll sleeps from now on
        monkeypatch.setattr(box_follow, "WATCH_S", 30.0)
        await asyncio.sleep(0.6)  # (the watch's current sleep ends; its next one is 30 s)
        m = rig.mark()
        vs.scroll(5)
        box_follow.on_visible(rig.s, {"type": "visible", "folders": ["/somewhere/else"]})  # another window: nothing
        await asyncio.sleep(0.3)
        assert not _boxes(rig, m)
        box_follow.on_visible(rig.s, {"type": "visible", "folders": [str(tmp_path)], "visibleRanges": []})
        trace = await _trace(rig, m, 0.4)
        assert _near(_last(trace), vs.row_y(23)), trace

    run(go())


def test_t7_stale_ocr_frame_never_shifts_the_followed_box(tmp_path, vs):
    """_not_on_above (the box never on the section comment) reads OCR. A frame captured before a one-row scroll shows
    `# Backprop` exactly where line 23 is now: that frame must not push the box down a row."""
    import re

    rig = _rig(tmp_path, vs)
    vs.lag = 0.2
    frame = {"top": 1, "t": time.time()}
    lines = NN1_DONE.split("\n")

    def locate(match, app=None):
        for i, ln in enumerate(lines, start=1):
            if re.search(match, ln):
                return {"rect": {"x": vs.X, "y": vs.row_y(i, frame["top"]), "w": 200.0, "h": vs.H + 3},
                        "app": "Code", "matched": ln}
        return None

    rig.s.screen.locate = locate
    rig.s.screen.latest = lambda: types.SimpleNamespace(t=frame["t"], text={})

    async def go():
        await _demo_at(rig, vs, NN1_DONE, "nn1")
        vs.scroll(8)
        frame.update(top=8, t=time.time())
        await _to_step(rig, vs, "nn2")
        await asyncio.sleep(1.0)
        frame.update(top=vs.top, t=time.time())
        assert _near(rig.s.spot_rect["y"], vs.row_y(23))
        m = rig.mark()
        vs.scroll(vs.top + 1)  # one row: line 23 is where the stale frame has `# Backprop`
        trace = await _trace(rig, m, 0.8)
        assert _near(_last(trace), vs.row_y(23)), (trace, vs.row_y(23))

    run(go())


def test_t7_show_me_boxes_the_row_under_the_comment_and_shows_the_code(tmp_path, vs):
    """t6 persona: Show me boxed `# The network` itself with a clipped "Type below this l…", and its card said only
    "Type below line 4". Now: the row under the section comment, "Type it here", and the card names the line and
    shows the step's code under the comment."""
    rig = _rig(tmp_path, vs)
    vs.lag = 0.2

    async def go():
        await _demo_at(rig, vs, NN1_DONE, "nn1")
        vs.scroll(1)
        await _to_step(rig, vs, "nn2")
        await asyncio.sleep(0.8)
        m = rig.mark()
        await rig.s.action("show_me")
        await _settle(rig)
        for b in _boxes(rig, m):  # (the step's own box is that box already: not sent again)
            assert _near(b["rect"]["y"], vs.row_y(23)) and b["caption"] == "Type it here", b
        assert _near(rig.s.spot_rect["y"], vs.row_y(23)) and rig.s._spot_caption == "Type it here"
        card = [e["payload"] for e in rig.since(m) if e["type"] == "card"][-1]
        assert card["title"] == "Type on line 23", card
        assert "# Backprop" in card["body"]
        assert card["diff"].splitlines()[0] == " # Backprop"
        assert "+def backward(X, y, h1, h2, out):" in card["diff"].splitlines()

    run(go())


def test_t7_diagnosis_line_is_scrolled_into_view_and_boxed(tmp_path, vs):
    """t6 persona: "Wrong sign in tanh slope: change + to - on line 23" while VS Code showed lines 35-48 and nothing
    was boxed. The diagnosed line is found in nn.py by its text, revealed in the lesson's window (the companion, no
    focus change) and boxed on its row as the off-track's box."""
    rig = _rig(tmp_path, vs)
    vs.lag = 0.2
    wrong = "    d_h2 = d_out @ W3.T * (1 + h2 ** 2)"
    bad = NN2_DONE.replace("(1 - h2 ** 2)", "(1 + h2 ** 2)")
    n = bad.split("\n").index(wrong) + 1

    async def go():
        await _demo_at(rig, vs, bad, "nn2")
        vs.scroll(1)
        await _to_step(rig, vs, "nn3")
        await asyncio.sleep(0.8)
        vs.scroll(33)  # line n is far above the screen
        full = {"stepId": "nn3", "severity": "fail", "title": "Wrong sign in tanh slope",
                "body": "In VS Code, change + to - in d_h2 of nn.py.",
                "diff": {"yours": wrong, "expected": wrong.replace("+", "-")}}
        m = rig.mark()
        await rig.s._offtrack_spot(rig.s.step, full)
        assert ("open", n) in vs.jumps
        assert vs.top <= n < vs.top + vs.ROWS
        boxes = _boxes(rig, m)
        assert boxes and _near(boxes[-1]["rect"]["y"], vs.row_y(n)), (boxes, vs.row_y(n))
        assert boxes[-1]["caption"].startswith("Change"), boxes[-1]["caption"]
        assert rig.s._spot_owner[0] == "offtrack"

    run(go())
