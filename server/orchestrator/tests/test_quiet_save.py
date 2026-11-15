"""quiet_save.intercept (no ⌘S chores, Nov 15): a card that asks for ⌘S is answered by a quiet save through the
companion; only its save request goes, never the instruction it came with. Run from the repo root:
    python -m pytest server/orchestrator/tests/test_quiet_save.py -q
"""
from __future__ import annotations

import asyncio
import types

import pytest

from server.orchestrator import quiet_save


def _session(tmp_path, saves: bool | None = True):
    """A lesson session as intercept sees it: step nn4 in nn.py; the companion saves (True), finds nothing unsaved
    (False) or isn't there (None: the file stays dirty)."""
    (tmp_path / "nn.py").write_text("W1 = np.zeros((1, 4))\n", encoding="utf-8")
    spawned: list = []

    async def save_step_file(step):
        return bool(saves)

    async def evaluate(trigger):
        return None

    def spawn(coro, **kw):
        spawned.append(coro)
        coro.close()

    s = types.SimpleNamespace(
        step={"id": "nn4", "file": "nn.py"}, lesson_mode=True, workdir=str(tmp_path),
        _untitled_editor=lambda: None, _save_step_file=save_step_file, _dirty_step_file=lambda step: saves is None,
        _step_file=lambda step: "nn.py", _spawn=spawn, evaluate=evaluate)
    return s, spawned


def _run(coro):
    return asyncio.run(coro)


def test_delete_card_keeps_its_instruction_after_the_quiet_save(tmp_path):
    """stale_advice's Do it for me over unsaved edits: "In nn.py, delete line 1 (...), then save with ⌘S." The save
    is done quietly; the card still says what to delete (it used to be dropped whole: Do it for me showed nothing)."""
    s, spawned = _session(tmp_path)
    card = {"stepId": "nn4", "kind": "answer", "title": "Delete line 1",
            "body": "In nn.py, delete line 1 (W1 = np.zeros((1, 4))), then save with ⌘S.", "actions": ["show_me"]}
    out = _run(quiet_save.intercept(s, card))
    assert out is not None and out["title"] == "Delete line 1"
    assert out["body"] == "In nn.py, delete line 1 (W1 = np.zeros((1, 4)))."
    assert out["actions"] == ["show_me"] and "⌘S" not in out["body"]
    assert spawned  # graded on the saved file at once


@pytest.mark.parametrize("card,want", [
    ({"title": "Save nn.py", "body": "Save nn.py (⌘S) so I can check it."}, None),  # the save answers it
    ({"title": "Save so I can check", "body": "Save with ⌘S so I can check it."}, None),
    ({"title": "Save nn.py first", "body": "Press ⌘S, then Do it for me again."},
     {"title": "Saved nn.py", "body": "Press Do it for me again."}),
    ({"title": "You fixed it", "body": "Save nn.py (⌘S)."}, {"title": "You fixed it", "body": "Checking it now."}),
    ({"title": "Not yet", "body": "You fixed it. Save nn.py (⌘S). The loss still needs random weights."},
     {"title": "Not yet", "body": "You fixed it. The loss still needs random weights."}),
    ({"title": "Save nn.py", "body": "Save nn.py in VS Code (⌘S), then run it again."}, None),  # nothing else asked
])
def test_save_requests_go_and_everything_else_stays(tmp_path, card, want):
    s, _ = _session(tmp_path)
    out = _run(quiet_save.intercept(s, {"stepId": "nn4", "kind": "answer", **card}))
    if want is None:
        assert out is None
    else:
        assert out is not None and {k: out[k] for k in want} == want


def test_without_the_companion_the_card_asks_for_the_save(tmp_path):
    """The extension can't save (not installed / refused): the one case a ⌘S card is right; it goes out unchanged."""
    s, spawned = _session(tmp_path, saves=None)
    card = {"stepId": "nn4", "kind": "answer", "title": "Delete line 1",
            "body": "In nn.py, delete line 1 (W1 = np.zeros((1, 4))), then save with ⌘S."}
    assert _run(quiet_save.intercept(s, card)) == card and not spawned


def test_a_run_steps_pending_autosave_never_lands_on_the_next_step(tmp_path, monkeypatch):
    """A run step's unsaved fix is saved after ~1 s of quiet (a terminal run reads the disk). When that step is over
    first (Check passed it, Skip), the save it had pending is dropped, never done on the next step's half-typed code."""
    s, _ = _session(tmp_path)
    text = {"v": "W1 = np.zeros((1, 4))\n"}
    saved: list = []

    async def refresh(paths, workdir):
        return None

    async def save_step_file(step):
        saved.append(step["id"])
        return True

    async def evaluate(trigger):
        return None

    s.__dict__.update(
        passed=False, phase="active", awaiting_resume=False, awaiting_start=False, step_gen=1,
        _buffers=types.SimpleNamespace(refresh=refresh, text=lambda p: text["v"]), _save_step_file=save_step_file,
        _run_command=lambda step: "python3 nn.py" if step["id"] == "nn4" else "", _dirty_step_file=lambda step: True,
        evaluate=evaluate)
    clock = {"t": 100.0}
    monkeypatch.setattr(quiet_save.time, "monotonic", lambda: clock["t"])

    async def go():
        await quiet_save.poll(s)  # the first look: the buffer's signature
        text["v"] = "W1 = np.random.randn(1, 4)\n"  # the fix, typed (unsaved)
        await quiet_save.poll(s)
        assert s._quiet_save["run_save_due"] is not None
        s.step, s.step_gen = {"id": "nn5", "file": "nn.py"}, 2  # Check passed nn4: nn5 started
        clock["t"] += 5
        await quiet_save.poll(s)
        assert saved == [] and s._quiet_save["run_save_due"] is None
        # the same on the run step itself: saved once still for a second
        s.step, s.step_gen = {"id": "nn4", "file": "nn.py"}, 3
        text["v"] = "W1 = np.random.randn(1, 4) * 0.5\n"
        await quiet_save.poll(s)
        clock["t"] += 1.5
        await quiet_save.poll(s)
        assert saved == ["nn4"]

    _run(go())


def test_save_clause_only_goes_when_something_else_is_asked():
    w = quiet_save._without_save
    assert w("In nn.py, delete lines 3-5 (W1 = 0), then save with ⌘S.") == "In nn.py, delete lines 3-5 (W1 = 0)."
    assert w("Change + to - on line 23, and then save nn.py (⌘S).") == "Change + to - on line 23."
    assert w("Save with ⌘S so I can check it.") == "Save with ⌘S so I can check it."  # the whole sentence is the ask
    assert w("Press ⌘S, then Do it for me again.") == "Press ⌘S, then Do it for me again."
