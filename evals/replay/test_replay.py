"""The scripted-learner replay eval, offline: every cached case replays as its case file expects, every case's learner
script satisfies its own expected checks (dry run), and the harness can fail.

    python -m pytest evals/replay -q -p no:cacheprovider
"""

from __future__ import annotations

import ast
import copy
import re
import sys
import tempfile
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


def _case_sensitive_tmp() -> bool:
    """Does the temp folder the replay writes lessons into tell `a` from `A`? (Linux yes, macOS and Windows no.)"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a").touch()
        return not (Path(d) / "A").exists()


# Cases whose expected grades hold only where file names ignore case, as on macOS and Windows: on a case-sensitive
# filesystem (Linux CI) they grade differently. Fix the lesson or the case, then drop it here.
CASE_INSENSITIVE_ONLY = {
    "git-basics": "the cached lesson's s8 precision check reads gitgoing/index.html while the learner edits "
                  "GitGoing/index.html: it passes only where file names ignore case",
}


def _replay_param(case: dict):
    why = CASE_INSENSITIVE_ONLY.get(case["id"])
    marks = [pytest.mark.xfail(_case_sensitive_tmp(), reason=why, strict=True)] if why else []
    return pytest.param(case, id=case["id"], marks=marks)


@pytest.mark.parametrize("case", [_replay_param(c) for c in CACHED])
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


def _step(result, sid):
    return next(s for s in result["steps"] if s["step"] == sid)


def test_status_is_the_first_passing_gate():
    """The session moves on at the first green gate. git s9's precision row (command_exit_ok, which keeps only `git`)
    goes green on `git checkout main`, before the pull and git show that its screen checks wait for."""
    result = harness.run_case(next(c for c in CASES if c["id"] == "git-basics"))
    s9 = _step(result, "s9")
    assert s9["first_status"] == "pass-precision" and s9["status"] == "pass-precision"
    assert s9["first_pass_after_action"] == 1 and s9["correct_actions"] == 3
    assert s9["early_precision"] and s9["best_status"] == "pass"
    s7 = _step(result, "s7")  # a step whose screen checks open the gate
    assert s7["first_status"] == "pass" and not s7["early_precision"]


def test_early_precision_needs_a_finding():
    """A correct learner moved on by precision before the step's work is done is a problem until the case records it."""
    case = copy.deepcopy(next(c for c in CASES if c["id"] == "git-basics"))
    s9 = next(st for st in case["outline"] if st["step"] == "s9")
    del s9["finding"]
    assert any("git-basics/s9" in p and "via precision after action 1 of 3" in p for p in harness.problems(harness.run_case(case)))
    s9["expect"] = "pass"
    assert any("git-basics/s9: pass-precision (expected pass)" in p for p in harness.problems(harness.run_case(case)))


def test_caught_by_names_the_row_that_fires():
    """sql step 2: the Traceback row (x1) catches the bad insert; x0 (`customers: 3`) only fails because the mistake
    never prints the count, so naming it as the catcher is a problem when it isn't failing for the mistake."""
    case = next(c for c in CASES if c["id"] == "sql-sqlite-joins")
    m = next(a for a in case["outline"][1]["actions"] if a.get("do") == "mistake")
    assert m["caught_by_spec_rows"] == ["x1"]
    result = harness.run_case(case, dry=True)
    assert result["steps"][1]["mistakes"][0]["caught_by"] == {"x1": "fail"}
    wrong = copy.deepcopy(case)
    for a in wrong["outline"][2]["actions"]:  # the wrong-key join: x2 doesn't exist, x0 does fail
        if a.get("do") == "mistake":
            a["caught_by_spec_rows"] = ["x0", "x2"]
    assert any("did not fail: x2 missing" in p for p in harness.problems(harness.run_case(wrong, dry=True)))


def test_caught_by_row_that_passes_is_reported():
    """react s2: the leftover useState is caught by s2c3 (screen_absent useState), not by s2c1, which passes."""
    case = copy.deepcopy(next(c for c in CASES if c["id"] == "react-components"))
    s2 = next(st for st in case["outline"] if st["step"] == "s2")
    m = next(a for a in s2["actions"] if a.get("do") == "mistake")
    assert m["caught_by"] == ["s2c3"]
    m["caught_by"] = ["s2c1", "s2c3"]
    assert any("did not fail: s2c1 pass" in p for p in harness.problems(harness.run_case(case)))


def test_video_tutorial_accepts_video_query():
    case = copy.deepcopy(next(c for c in CASES if c["id"] == "sql-sqlite-joins"))
    case["tutorial"]["kind"] = "video"
    case["tutorial"].pop("video_id", None)
    assert case["tutorial"].get("video_query")
    assert harness.validate_case(case) == []
    del case["tutorial"]["video_query"]
    assert "a video tutorial needs video_id or video_query" in harness.validate_case(case)


def test_terminal_echoes_input_answers():
    out = harness._echo_input("First number: Operator (+, -, *, /): Second number: Result: 4.0\n", "8\n/\n2\n")
    assert out.splitlines() == ["First number: 8", "Operator (+, -, *, /): /", "Second number: 2", "Result: 4.0"]


def test_real_runs_are_limited_to_python_scripts(tmp_path):
    world = harness.World(root=tmp_path)
    with pytest.raises(harness.CaseError):
        harness.apply(world, {"do": "run", "cmd": "rm -rf /", "real": True})
    with pytest.raises(harness.CaseError):
        harness.apply(world, {"do": "write", "file": "../outside.txt", "text": "x"})
    for script in ("/tmp/x.py", "~/x.py"):  # the script itself must be inside the lesson folder, not only the cwd
        with pytest.raises(harness.CaseError):
            harness._real_run(f"python3 {script}", "", tmp_path)


def test_real_runs_get_an_allowlisted_env(tmp_path, monkeypatch):
    for name in ("SOME_API_KEY", "DB_PASSWORD", "SUPABASE_URL", "AWS_REGION", "DATABASE_URL"):
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("LC_ALL", "C")
    (tmp_path / "env.py").write_text("import os\nprint(sorted(os.environ))\n", encoding="utf-8")
    lines, code = harness._real_run("python3 env.py", "", tmp_path)
    assert code == 0
    names = set(ast.literal_eval(lines[0]))
    assert names <= {"PATH", "HOME", "LANG", "TMPDIR", "LC_ALL", "LC_CTYPE", "__CF_USER_TEXT_ENCODING", "PYTHONHASHSEED"}
    assert "LC_ALL" in names and "DB_PASSWORD" not in names
