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


def test_save_clause_only_goes_when_something_else_is_asked():
    w = quiet_save._without_save
    assert w("In nn.py, delete lines 3-5 (W1 = 0), then save with ⌘S.") == "In nn.py, delete lines 3-5 (W1 = 0)."
    assert w("Change + to - on line 23, and then save nn.py (⌘S).") == "Change + to - on line 23."
    assert w("Save with ⌘S so I can check it.") == "Save with ⌘S so I can check it."  # the whole sentence is the ask
    assert w("Press ⌘S, then Do it for me again.") == "Press ⌘S, then Do it for me again."
