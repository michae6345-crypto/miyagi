"""The scripted-learner replay eval, offline: every cached case replays as its case file expects, every case's learner
script satisfies its own expected checks (dry run), and the harness can fail.

    python -m pytest evals/replay -q -p no:cacheprovider
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from evals.replay import harness

CASES = harness.load_cases()
CACHED = [c for c in CASES if harness.is_cached(c)]
IDS = [c["id"] for c in CASES]


def test_fifteen_varied_cases():
    assert len(CASES) >= 15
    assert len(set(IDS)) == len(IDS)
    topics = {c["topic"] for c in CASES}
    assert len(topics) >= 10, topics
    nets = [c for c in CASES if c["topic"] in ("neural-nets", "deep-learning", "physics-ml")]
    assert len(nets) <= len(CASES) // 3, "not only neural nets"


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_case_is_well_formed(case):
    assert harness.validate_case(case) == []


@pytest.mark.parametrize("case", CACHED, ids=[c["id"] for c in CACHED])
def test_cached_case_maps_every_lesson_step(case):
    lesson = harness.load_lesson(case)
    lesson_ids = [s["id"] for s in lesson["steps"]]
    scripted = [st["step"] for st in case["outline"]]
    assert scripted == lesson_ids, "the learner script follows the lesson's steps in order"


@pytest.mark.parametrize("case", CACHED, ids=[c["id"] for c in CACHED])
def test_replay_cached_lesson(case):
    result = harness.run_case(case)
    assert result["mode"] == "replay"
    assert result["unscripted_steps"] == []
    assert harness.problems(result) == []
    assert all(s["outline_match"] for s in result["steps"])


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_learner_script_meets_its_expected_checks(case):
    """Dry run: the expected checks stand in for the lesson's. A correct learner passes every step; each mistake
    is caught (unless the case says the screen can't tell, caught_by_spec: false)."""
    result = harness.run_case(case, dry=True)
    assert result["mode"] == "dry"
    assert harness.problems(result) == []


def test_needs_build_list_is_in_the_readme():
    readme = (Path(harness.__file__).parent / "README.md").read_text(encoding="utf-8")
    listed = re.findall(r"^\| `([a-z0-9-]+)` \|", readme.split("## Needs one paid build", 1)[1], re.MULTILINE)
    assert sorted(listed) == sorted(c["id"] for c in harness.needs_build(CASES))


def test_a_wrong_lesson_check_fails_the_step(monkeypatch):
    """The harness can fail: the calculator's last check made to want Result: 5.0 turns s8 red."""
    case = next(c for c in CASES if c["id"] == "python-calculator")
    real = harness.load_lesson(case)
    broken = copy.deepcopy(real)
    s8 = next(s for s in broken["steps"] if s["id"] == "s8")
    s8["checks"][0]["pattern"] = r"Result:\s*5\.0"
    s8["precision_checks"] = []
    monkeypatch.setattr(harness, "load_lesson", lambda c: broken)
    result = harness.run_case(case)
    step = next(s for s in result["steps"] if s["step"] == "s8")
    assert step["status"] == "fail"
    assert any("s8" in p for p in harness.problems(result))


def test_mistake_that_passes_is_reported(monkeypatch):
    """A mistake the case expects caught but the lesson passes is a problem, not silence."""
    case = copy.deepcopy(next(c for c in CASES if c["id"] == "python-calculator"))
    s1 = case["outline"][0]
    s1["actions"][0]["caught"] = True
    result = harness.run_case(case)
    assert any("mistake NOT caught" in p for p in harness.problems(result))


def test_terminal_echoes_input_answers():
    out = harness._echo_input("First number: Operator (+, -, *, /): Second number: Result: 4.0\n", "8\n/\n2\n")
    assert out.splitlines() == ["First number: 8", "Operator (+, -, *, /): /", "Second number: 2", "Result: 4.0"]


def test_real_runs_are_limited_to_python_scripts(tmp_path):
    world = harness.World(root=tmp_path)
    with pytest.raises(harness.CaseError):
        harness.apply(world, {"do": "run", "cmd": "rm -rf /", "real": True})
    with pytest.raises(harness.CaseError):
        harness.apply(world, {"do": "write", "file": "../outside.txt", "text": "x"})
