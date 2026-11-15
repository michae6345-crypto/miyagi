"""Desktop test 9 (Nov 15, "Watch a video": Kie Codes' "Code your first Neural Network with TensorFlow", cached lesson
demo/cache/lessons/5c0ea8a49f419487.json, copied here as fixtures/t9_lesson_5c0ea8a49f419487.json).

V4  The coach said "Notebook is mnist.ipynb, not Untitled.ipynb · Rename mnist.ipynb to Untitled.ipynb" and boxed the
    Explorer item ("Rename to Untitled.ipynb") while the only failing check was the screen check `mnist\\.load_data\\(\\)`.
    Untitled.ipynb was the video's Jupyter default. No model is called: llm.structured_call is a stub that returns
    test 9's own reply.

Run from the repo root:  python -m pytest server/tests/test_t9_coach.py -q"""

from __future__ import annotations

import asyncio
import copy
import importlib
import json
from pathlib import Path

import pytest

from server.coach import common, llm

dg = importlib.import_module("server.coach.diagnose")  # the package re-exports the function under the same name

LESSON = json.loads((Path(__file__).parent / "fixtures" / "t9_lesson_5c0ea8a49f419487.json").read_text())
PAID_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "BRIGHTDATA_API_KEY", "ELEVENLABS_API_KEY")


@pytest.fixture(autouse=True)
def _free(monkeypatch):
    for k in PAID_KEYS:  # an accidental live call fails at once, for free
        monkeypatch.setenv(k, "")
    for k in ("COACH_REPLAY_DIR", "COACH_RECORD_DIR"):
        monkeypatch.delenv(k, raising=False)
    yield
    common.set_lesson(None)


def lesson() -> dict:
    return copy.deepcopy(LESSON)


# test 9's diagnose reply (engine-t9.log 06:16:02), the triage that sent it there
T9_CARD = {
    "playbook_id": "none", "severity": "fail", "title": "Notebook is mnist.ipynb, not Untitled.ipynb",
    "body": "The check looks for `Untitled.ipynb`, but your notebook is saved as `mnist.ipynb`, so the file lookup fails. "
            "Rename `mnist.ipynb` to `Untitled.ipynb` in the Explorer, or confirm the step accepts your filename.",
    "citation_id": "none", "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0, "diff_command": "",
    "guiding_question": "", "actions": ["show_me"],
}


def stub_calls(monkeypatch, card: dict) -> list[str]:
    calls: list[str] = []

    async def fake(*, purpose: str, user_text: str = "", **_: object) -> llm.CallResult:
        calls.append(purpose)
        if purpose == "triage":
            return llm.CallResult(data={"route": "opus", "playbook_id": "none", "reason": "code visible, check fails"}, model="stub")
        return llm.CallResult(data=copy.deepcopy(card), model="stub")

    monkeypatch.setattr(llm, "structured_call", fake)
    return calls


S2_FAILED = [{"checkId": "s2c2", "label": "mnist load_data called", "status": "fail", "detail": "not showing yet"}]
S2_CODE = ("import tensorflow as tf\nfrom tensorflow.keras import layers, models\n\n(train_images, train_labels), "
           "(test_images, test_labels) = tf.keras.datasets.mnist.\nload_data()\n")


def test_rename_to_the_videos_notebook_name_is_never_the_diagnosis(monkeypatch):
    g = lesson()
    common.set_lesson(g)
    step = g["steps"][1]
    calls = stub_calls(monkeypatch, T9_CARD)
    failed = [{**next(c for c in step["checks"] if c["id"] == "s2c2"), **S2_FAILED[0]}]
    card = asyncio.run(dg.diagnose(step, failed, None, S2_CODE, lesson=g))
    assert "diagnose" in calls  # the model did answer (and named Untitled.ipynb)...
    text = f"{card['title']} {card['body']} {card.get('why', '')}"
    assert "Untitled" not in text and "Rename" not in text and "rename" not in text, text  # ...and that card is gone
    # the card is about the failing screen check instead
    assert card["title"] == "`mnist.load_data()` not on screen yet"
    assert "mnist.load_data()" in card["body"] and "Scroll VS Code" in card["body"]
    assert card["_meta"]["route"] == "guard" and "Untitled.ipynb" in card["_meta"]["dropped"]["title"]
    assert "targets" not in card or card["targets"] == []
    assert "—" not in card["title"] + card["body"]


def test_rename_boxes_are_dropped_streamed_and_final():
    g = lesson()
    common.set_lesson(g)
    step = g["steps"][1]
    req = dg.required_names(step, S2_FAILED)
    assert req == set()  # the step's own failing check names no file; the precision check's Untitled.ipynb never counts
    targets = [{"label": "Rename to Untitled.ipynb", "text": "mnist.ipynb", "rect": [80, 178, 75, 15]},
               {"label": "Load MNIST here", "text": "load_data()", "rect": [400, 300, 120, 18]}]
    assert dg.keep_targets(targets, req) == [targets[1]]
    for ask in ("Rename mnist.ipynb to Untitled.ipynb.", "Save it as `Untitled.ipynb`", "Move it into venv/",
                "Name the notebook Untitled.ipynb"):
        assert dg.asks_incidental_rename(ask, req), ask
    for fine in ("Run the cell with Shift+Enter.", "Call model.fit to train.", "Save the file, then run it.",
                 "Move the import to line 1."):
        assert not dg.asks_incidental_rename(fine, req), fine


def test_a_name_a_failing_check_needs_may_still_be_asked_for(monkeypatch):
    """calc.py vs calculator.py: the step's own file_exists check names calculator.py, so the rename stays."""
    step = {"id": "s1", "title": "Create calculator.py", "video": {"sourceId": "src1", "start": 0, "end": 30},
            "checks": [{"id": "s1c1", "type": "file_exists", "label": "calculator.py created", "file": "calculator.py"}]}
    common.set_lesson({"lesson": {"title": "Calc"}, "sources": [], "steps": [step]})
    card = {**T9_CARD, "title": "File is calc.py, not calculator.py", "body": "The check looks for calculator.py. Rename calc.py to calculator.py."}
    stub_calls(monkeypatch, card)
    failed = [{**step["checks"][0], "checkId": "s1c1", "status": "fail"}]
    out = asyncio.run(dg.diagnose(step, failed, None, "print('hi')\n", error_text="Traceback (most recent call last):\nNameError: x"))
    assert out["_meta"]["route"] == "opus" and "Rename calc.py to calculator.py" in out["body"]


def test_the_coach_prompt_says_incidental_names_are_not_requirements():
    assert "Untitled.ipynb" in dg.COACH_SYSTEM and "Never ask them to rename" in dg.COACH_SYSTEM
