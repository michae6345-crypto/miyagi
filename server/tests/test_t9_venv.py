"""Desktop test 9 (Nov 15, "Watch a video", V6): step 1 of the cached Kie Codes TensorFlow lesson
(demo/cache/lessons/5c0ea8a49f419487.json, copied here as fixtures/t9_lesson_5c0ea8a49f419487.json) said
`python3 -m venv venv && source venv/bin/activate && pip3 install jupyter tensorflow numpy matplotlib && jupyter notebook`.
Miyagi had already made the lesson's .venv (Python 3.12: on Michael's Mac bare `python3` is Homebrew 3.15, which has no
TensorFlow wheels, so that command fails with "No matching distribution found for tensorflow") and its setup card
installs those packages into it. The demo replays that cache with no rebuild, so the fix applies on every lesson load.
No model is called.

Run from the repo root:  python -m pytest server/tests/test_t9_venv.py -q"""

from __future__ import annotations

import asyncio
import copy
import json
import re
from pathlib import Path

import pytest

from server.lesson import gemini
from server.lesson.venv_steps import rewrite_command, use_lesson_venv

LESSON = json.loads((Path(__file__).parent / "fixtures" / "t9_lesson_5c0ea8a49f419487.json").read_text())
PAID_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "BRIGHTDATA_API_KEY", "ELEVENLABS_API_KEY",
             "TIGER_DATABASE_URL")
LIBS = {"tensorflow", "numpy", "matplotlib", "jupyter"}
NEW_VENV = re.compile(r"-m\s+venv|virtualenv")


@pytest.fixture(autouse=True)
def _free(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path_factory.mktemp("miyagi-state")))
    for k in PAID_KEYS:  # an accidental live call fails at once, for free
        monkeypatch.setenv(k, "")


def lesson() -> dict:
    return copy.deepcopy(LESSON)


def test_cached_lesson_step1_uses_the_lessons_venv():
    g = lesson()
    assert NEW_VENV.search(g["steps"][0]["run_command"])  # the cache as test 9 replayed it
    assert use_lesson_venv(g) == ["s1"]
    s1 = g["steps"][0]
    assert s1["run_command"] == "source .venv/bin/activate && jupyter notebook"
    assert s1["title"] == "Activate .venv and start Jupyter"
    text = " ".join([s1["instructions"], *s1["hints"], *s1["common_mistakes"], *(t["match"] + t["caption"] for t in s1["targets"])])
    assert not NEW_VENV.search(text) and "pip3 install" not in text and "pip install" not in text, text
    assert "source .venv/bin/activate && jupyter notebook" in s1["instructions"]
    assert "setup card" in s1["instructions"] and "—" not in s1["instructions"]
    # checks: pip's own output can never show any more; the venv file check looks in .venv
    labels = [c["label"] for c in s1["checks"]]
    assert "Packages installed via pip" not in labels and "Jupyter server running" in labels
    # t10: the venv file check goes: Miyagi made .venv, so it passed s1 ("confirmed by your files") with no action
    assert s1["precision_checks"] == []
    assert s1["targets"] == [{"app": "Terminal", "match": "jupyter notebook", "caption": "Run this in the VS Code terminal"}]
    # the notebook steps are untouched
    assert [st for st in g["steps"][1:]] == lesson()["steps"][1:]
    # idempotent: a second load changes nothing
    again = copy.deepcopy(g)
    assert use_lesson_venv(again) == [] and again == g


@pytest.mark.parametrize("cmd, want", [
    ("python3 -m venv venv && source venv/bin/activate && pip3 install jupyter tensorflow numpy matplotlib && jupyter notebook",
     "source .venv/bin/activate && jupyter notebook"),
    ("python3.15 -m venv env; . env/bin/activate; python3 -m pip install -U numpy tensorflow==2.15.0 && env/bin/python train.py",
     "source .venv/bin/activate && .venv/bin/python train.py"),
    ("pip3 install numpy seaborn", "pip install seaborn"),
    ("python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt",
     "source .venv/bin/activate && pip install -r requirements.txt"),
    ("pip install tensorflow", ""),
])
def test_venv_and_install_forms(cmd, want):
    new, _ = rewrite_command(cmd, LIBS)
    assert new == want
    assert not NEW_VENV.search(new)


def test_nothing_to_change_or_nothing_known():
    assert rewrite_command("python3 train.py --epochs 5", LIBS) is None
    assert rewrite_command("source .venv/bin/activate && jupyter notebook", LIBS) is None
    g = {"lesson": {"libraries": {}}, "steps": [{"id": "s1", "run_command": "python3 -m venv venv", "instructions": "x"}]}
    assert use_lesson_venv(g) == [] and g["steps"][0]["run_command"] == "python3 -m venv venv"  # no .venv may be made
    g = {"lesson": {"libraries": {"numpy": ""}}, "steps": [{"id": "s2", "run_command": "Run the cell (Shift+Enter)"}]}
    assert use_lesson_venv(g) == [] and g["steps"][0]["run_command"] == "Run the cell (Shift+Enter)"


def test_lesson_load_sends_the_venv_step(tmp_path, monkeypatch):
    """The session applies it when the cached lesson loads: step.started for s1 and the session's graph."""
    from server.orchestrator.tests.test_session import Rig

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    rig = Rig(tmp_path)

    async def go():
        await rig.s.load_graph(lesson())
        await rig.settle()

    asyncio.run(go())
    started = rig.of("step.started")[0]
    assert started["stepId"] == "s1"
    sent = " ".join(str(started.get(k) or "") for k in ("title", "instructions", "details", "code"))
    assert not NEW_VENV.search(sent) and "pip3 install" not in sent, sent
    # t10 (server/lesson/notebook_steps.py): no browser Jupyter server either; the notebook opens in VS Code on .venv
    assert "Select the .venv kernel in mnist.ipynb" in sent and "jupyter notebook" not in sent, sent
    pending = {p["label"] for p in rig.of("check.updated") if p["stepId"] == "s1"}  # no screen here: the file checks
    assert pending == {"Jupyter server running", "No terminal errors"}  # t10: no vacuous .venv file check
    s1 = rig.s.graph["steps"][0]
    assert "run_command" not in s1
    assert [c["label"] for c in s1["checks"]] == ["Notebook kernel is .venv", "No kernel or terminal errors"]


def test_adapt_prompt_says_the_lessons_venv_is_ready():
    assert ".venv" in gemini.ADAPT_SYSTEM and "Never tell the learner to create another venv" in gemini.ADAPT_SYSTEM
