"""ROADMAP 1.8, check correctness: false passes and false fails seen in desktop QA tests 3 to 12 (Nov 15,
miyagi-qa-1115/<tN>/checkpoints.log + engine logs), one offline regression test per case that had none.
No model call, no network, no screen: pure checks plus a lesson-mode session on stubs.

Fixed here (failed on origin/integration/live before this change):
  T11-CP4  false pass  s2 "No import or load errors · not showing in VS Code" 0.4 s into the step, before the
                       learner's notebook existed (engine-t11.log 08:28:57).
  T5-CP12  false pass  "Ran python3 main.py · ran in the terminal" on a run the venv activation's ^C cancelled
                       (screen fallback: VS Code's shell integration reported nothing). A KeyboardInterrupt run read
                       as "the run printed an error" (a false fail row for a run the learner stopped).

Fixed earlier, regression test added here (none existed):
  T3-CP16  false pass  run step "No Python error shown" passed 2 ms in, "Terminal is not on screen".
  T5-CP10  false pass  Do it for me left a later `def sigmoid_slope` (s*(1+s)) overriding the right one; step passed.
  T5-CP12  false pass  VS Code route: an exit-130 / KeyboardInterrupt run never passes (terminal_run.verdict).
  T5-CP13  false pass  s7 "Ran python3 main.py" passed on s5's run still in the terminal panel.
  T12-CP4  false fail  "Kernel picker not set to .venv" while VS Code showed '.venv (3.12.16) (Python 3.12.16)'.

Already covered elsewhere (see the PR body for the full list): T3-CP12 syntax error (orchestrator/tests/
test_check_verdicts.py), T6-CP7 tanh sign (test_t8_engine.py), T9 V1-V3 (test_t9_checks.py), T10 CP3/7/12/13/14/15
(test_t10_checks.py), T11 kernel / live terminal (test_t11_notebook.py).

Run from the repo root:  python -m pytest server/tests/test_check_correctness.py -q"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from server.checks.evaluator import RunContext, evaluate_gate, evaluate_step, terminal_runs
from server.orchestrator import terminal_run

ROOT = Path(__file__).resolve().parents[2]
VIDEO = json.loads((ROOT / "demo" / "cache" / "lessons" / "5c0ea8a49f419487.json").read_text())
PAID_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY", "TIGER_DATABASE_URL")
PROMPT = "tripi@mac nn % "


@pytest.fixture(autouse=True)
def _free(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path_factory.mktemp("miyagi-state")))
    for k in PAID_KEYS:  # an accidental live call fails at once, for free
        monkeypatch.setenv(k, "")


def video_step(sid: str) -> dict:
    return copy.deepcopy(next(s for s in VIDEO["steps"] if s["id"] == sid))


def by_id(results: list[dict]) -> dict[str, dict]:
    return {r["checkId"]: r for r in results}


# ------------------------------------------------------------------ T11-CP4: no notebook yet, no "no errors" pass
README = {"Code": ["README.md", "# Code your first Neural Network with TensorFlow"]}
S2_TYPED = {"Code": ["Untitled.ipynb", "import tensorflow as tf",
                     "(train_images, train_labels), (test_images, test_labels) = tf.keras.datasets.mnist.load_data()",
                     "train_images = train_images.astype('float32') / 255"]}


@pytest.mark.parametrize("sid,absent", [("s2", ("s2c4", "s2c5")), ("s4", ("s4c5",)), ("s6", ("s6c5",))])
def test_t11_cp4_no_errors_row_waits_while_the_notebook_does_not_exist(tmp_path, sid, absent):
    """VS Code shows README.md, the lesson folder holds no notebook: the cell can't have run, so "No import or load
    errors" has nothing to grade. Was: pass "not showing in VS Code" at step start."""
    res = by_id(evaluate_step(video_step(sid), RunContext(workdir=str(tmp_path), screen=README)))
    for cid in absent:
        assert res[cid]["status"] == "pending" and res[cid]["detail"] == "checked when the cell runs", res[cid]
    assert not evaluate_gate(video_step(sid), RunContext(workdir=str(tmp_path), screen=README))["passed"]


def test_t11_cp4_a_browser_notebook_is_still_graded_once_its_code_is_on_screen(tmp_path):
    """No notebook on disk (Colab / a browser Jupyter): once every code row sees the step's code, the error rows
    read the screen again, so such a step can still pass; a visible error still fails it."""
    res = by_id(evaluate_step(video_step("s2"), RunContext(workdir=str(tmp_path), screen=S2_TYPED)))
    assert all(res[c]["status"] == "pass" for c in ("s2c1", "s2c2", "s2c3")), res
    assert res["s2c4"]["status"] == "pass" and res["s2c5"]["status"] == "pass", res
    broken = {"Code": S2_TYPED["Code"] + ["AttributeError: module has no attribute 'load_dat'"]}
    assert by_id(evaluate_step(video_step("s2"), RunContext(workdir=str(tmp_path), screen=broken)))["s2c4"][
        "status"] == "fail"


def test_t11_cp4_no_workdir_keeps_the_old_screen_rule():
    """Without a lesson folder nothing was looked for (ctx.notebook stays None): the screen decides as before."""
    res = by_id(evaluate_step(video_step("s2"), RunContext(screen=README)))
    assert res["s2c4"]["status"] == "pass"


# ------------------------------------------------------------------ T5-CP12: a ^C'd run is not a run
@pytest.mark.parametrize("rows", [
    [PROMPT + "python3 main.py", "^C", PROMPT + "source .venv/bin/activate", "(.venv) " + PROMPT],
    [PROMPT + "python3 main.py", PROMPT + "source .venv/bin/activate", "(.venv) " + PROMPT],
    # a folder path with a space: VS Code quotes it
    [PROMPT + "python3 main.py", PROMPT + 'source "/Users/a b/.venv/bin/activate"', "(.venv) " + PROMPT],
    [PROMPT + "python3 main.py", "^CTraceback (most recent call last):", "KeyboardInterrupt", PROMPT],
])
def test_t5_cp12_a_command_cancelled_by_ctrl_c_is_not_a_run(rows):
    """Run it for me typed `python3 main.py`; the venv activation sent ^C and ran `source .venv/bin/activate`.
    The terminal shows the command, then ^C (or straight away the activation): nothing ran."""
    assert terminal_runs("python3 main.py", rows, [r"Predictions"]) == (0, False, False)


def test_t5_cp12_a_keyboard_interrupt_is_not_read_as_a_crash():
    """The learner stopped a long run with ^C: Python printed a traceback ending in KeyboardInterrupt. Not a run
    that crashed (no "the run printed an error" fail row): it just didn't finish."""
    rows = [PROMPT + "python3 nn.py", "epoch 0 loss 0.81", "Traceback (most recent call last):",
            '  File "nn.py", line 30, in <module>', "KeyboardInterrupt", PROMPT]
    assert terminal_runs("python3 nn.py", rows) == (0, False, False)


def test_t5_cp12_real_runs_still_count():
    good = [PROMPT + "python3 main.py", "Predictions:", "[[0.47437206]", PROMPT]
    assert terminal_runs("python3 main.py", good, [r"Predictions"]) == (1, False, True)
    crash = [PROMPT + "python3 main.py", "Traceback (most recent call last):", "NameError: name 'W1' is not defined",
             PROMPT]
    assert terminal_runs("python3 main.py", crash) == (1, True, False)
    # a good run, then one cancelled by ^C: one run counts; its output isn't claimed for the newer line
    both = good[:-1] + [PROMPT + "python3 main.py", "^C", PROMPT]
    assert terminal_runs("python3 main.py", both, [r"Predictions"])[0] == 1
    # ...nor its "Traceback … KeyboardInterrupt" read as the good run crashing
    stopped = good[:-1] + [PROMPT + "python3 main.py", "Traceback (most recent call last):", "KeyboardInterrupt", PROMPT]
    assert terminal_runs("python3 main.py", stopped, [r"Predictions"]) == (1, False, False)
    # another program's ^C (a script, or a REPL) after the good run never cancels it nor reads as its crash; the
    # good run's output isn't claimed as shown once a later program ran (the same rule as `stopped`)
    other = good[:-1] + [PROMPT + "python3 other.py", "Traceback (most recent call last):", "KeyboardInterrupt", PROMPT]
    assert terminal_runs("python3 main.py", other, [r"Predictions"]) == (1, False, False)
    repl = good[:-1] + [PROMPT + "python3", ">>> ", "KeyboardInterrupt", PROMPT]
    assert terminal_runs("python3 main.py", repl, [r"Predictions"]) == (1, False, False)
    # ...and a new real run after them counts as one more (session._need_run's `n > base`)
    rerun = repl[:-1] + [PROMPT + "python3 main.py", "Predictions:", "[[0.47437206]", PROMPT]
    assert terminal_runs("python3 main.py", rerun, [r"Predictions"]) == (2, False, True)
    # a KeyboardInterrupt the program printed and then kept going past is not the end of the run
    caught = [PROMPT + "python3 main.py", "KeyboardInterrupt", "Predictions:", "[0.5]", "done", PROMPT]
    assert terminal_runs("python3 main.py", caught, [r"Predictions"]) == (1, False, True)


@pytest.mark.parametrize("code,lines,status", [
    (130, [], "pending"),                                                      # ^C: exit 130
    (1, ["Traceback (most recent call last):", "KeyboardInterrupt"], "pending"),
    (None, ["^C"], "pending"),
    (0, ["Predictions:"], "pass"),
    (1, ["Traceback (most recent call last):", "SyntaxError: invalid syntax"], "fail"),
    (None, [], "pending"),                                                     # no exit status, nothing shown
])
def test_t5_cp12_vscode_run_reports_never_pass_an_interrupted_run(code, lines, status):
    from server.checks.evaluator import run_output

    assert terminal_run.verdict(code, lines, [r"Predictions"], run_output)[0] == status


# ------------------------------------------------------------------ T3-CP16: run step "No Python error shown"
RUN_STEP = {"id": "s3", "title": "Run it", "kind": "run", "run_command": "python3 main.py",
            "targets": [{"app": "Code", "file": "(terminal)", "match": "python3 main.py"}],
            "checks": [{"id": "s3c3", "type": "screen_absent", "app": "Terminal", "label": "No Python error shown",
                        "pattern": r"Traceback|Error"}]}


def test_t3_cp16_no_error_row_waits_for_the_run_on_a_hidden_terminal():
    """01:21:33: s3c3 passed 2 ms after step.started, "Terminal is not on screen, so nothing to flag", then stayed
    green over the SyntaxError run. It waits for the run; the run's own output decides."""
    code_only = {"Code": ["main.py", "import random"]}
    res = by_id(evaluate_step(RUN_STEP, RunContext(screen=code_only, segment_done=True, editor="Code")))
    assert res["s3c3"]["status"] == "pending" and res["s3c3"]["detail"] == "checked when it runs", res
    crashed = RunContext(screen=code_only, editor="Code", command="python3 main.py", exit_code=1,
                         output_tail=['  File "main.py", line 6', "SyntaxError: invalid syntax"])
    assert by_id(evaluate_step(RUN_STEP, crashed))["s3c3"]["status"] == "fail"
    ok = RunContext(screen=code_only, editor="Code", command="python3 main.py", exit_code=0,
                    output_tail=["You rolled: 4"])
    assert by_id(evaluate_step(RUN_STEP, ok))["s3c3"]["status"] == "pass"


@pytest.mark.parametrize("code,tail", [(130, ["epoch 0 loss 0.81", "^C"]),
                                       (1, ["Traceback (most recent call last):", "KeyboardInterrupt"])])
def test_t5_cp12_a_stopped_run_is_not_a_python_error(code, tail):
    """A run the learner (or the venv activation) stopped with ^C prints "Traceback … KeyboardInterrupt": the "No
    Python error shown" row waits for a finished run instead of failing (the coach would explain a ^C)."""
    ctx = RunContext(screen={"Code": ["main.py"]}, editor="Code", command="python3 main.py", exit_code=code,
                     output_tail=tail)
    row = by_id(evaluate_step(RUN_STEP, ctx))["s3c3"]
    assert row["status"] == "pending" and row["detail"] == "it stopped before it finished: run it again", row


# ------------------------------------------------------------------ T5-CP10: a later copy of the step's def
SIGMOID_STEP = "def sigmoid(x):\n    return 1 / (1 + np.exp(-x))\n\n\ndef sigmoid_slope(s):\n    return s * (1 - s)\n"
T5_FILE = ("import numpy as np\n\n\ndef sigmoid(x):\n    return 1 / (1 + np.exp(-x))\n\n\n"
           "def sigmoid_slope(s):\n    return s * (1 - s)\n    return 1/(1+np.exp(x))\n\n\n"
           "W1 = np.random.randn(2, 3)\n\n\ndef sigmoid_slope(s):\n    return s*(1+s)\n")


def test_t5_cp10_a_later_def_overriding_the_steps_is_found():
    """02:18:22: the patch left a second `def sigmoid_slope(s): return s*(1+s)` at the end of main.py; every pattern
    of step 2 was still in the file, so it passed, and training was silently broken."""
    from server.orchestrator import py_blocks

    assert py_blocks.overridden(SIGMOID_STEP, T5_FILE) == [("sigmoid_slope", [8, 16])]
    fixed = T5_FILE.split("\n\n\ndef sigmoid_slope(s):\n    return s*(1+s)")[0] + "\n"
    assert py_blocks.overridden(SIGMOID_STEP, fixed) == []
    # the learner's own spacing of the same def is the same def: no false "defined twice"
    respaced = fixed + "\n\ndef sigmoid_slope(s):\n    return s*(1 - s)\n"
    assert py_blocks.overridden(SIGMOID_STEP, respaced) == []


# ------------------------------------------------------------------ T12-CP4: the kernel label VS Code really showed
@pytest.mark.parametrize("shown", [".venv (3.12.16) (Python 3.12.16)", ".venv (3.12.16)"])
def test_t12_cp4_kernel_label_with_both_versions_passes(shown):
    """08:56:32: 'Kernel picker not set to .venv' while VS Code's notebook toolbar read '.venv (3.12.16) (Python
    3.12.16)'. The kernel check passes on that label (no notebook on disk to read it from)."""
    from server.lesson.notebook_steps import KERNEL_LABEL, KERNEL_PATTERN

    step = {"id": "s1", "title": "Open mnist.ipynb with the .venv kernel", "targets": [],
            "checks": [{"id": "s1c2", "type": "screen_contains", "app": "Code", "label": KERNEL_LABEL,
                        "pattern": KERNEL_PATTERN}]}
    screen = {"Code": ["mnist.ipynb", "+ Code  + Markdown  Run All", shown]}
    assert by_id(evaluate_step(step, RunContext(screen=screen)))["s1c2"]["status"] == "pass"


# ------------------------------------------------------------------ T5-CP13 / T5-CP12 in the session (screen route)
def _run_rig(tmp_path, monkeypatch):
    from server.orchestrator.tests.test_check_verdicts import DICE, _rig

    rig, screen = _rig(tmp_path, monkeypatch)
    (tmp_path / "main.py").write_text(DICE)  # a run step over an empty main.py goes back to typing it
    monkeypatch.setattr(terminal_run, "shell_reports", lambda: False)  # no VS Code shell integration: the panel decides
    return rig, screen


def test_t5_cp13_an_earlier_steps_run_in_the_panel_never_passes_the_run_row(tmp_path, monkeypatch):
    """02:20:20: s7's "Ran python3 main.py" passed 'ran in the terminal' on s5's run still in the panel. The panel
    as the step began is its baseline: only a new run counts."""
    from server.orchestrator.tests.test_session import run

    rig, _ = _run_rig(tmp_path, monkeypatch)
    old = [PROMPT + "python3 main.py", "You rolled: 4", PROMPT]
    rows: list[str] = old

    async def go():
        await rig.s.learn("dice", mode="lesson")
        await rig.settle()
        await rig.s.goto_step(2)  # s3: run python3 main.py
        await rig.settle()
        rig.s._terminal_rows = lambda: rows
        step = rig.s.step
        out = []
        for dt in (0.0, 0.5, 5.0, 9.0):  # the step's first reads set the baseline, later reads of the same panel
            rig.clock.t = rig.s.step_t0 + dt
            res, _gate = rig.s._need_run(step, [], {"passed": True})
            out.append(res[-1])
        return step, out

    step, out = run(go())
    assert step["id"] == "s3"
    assert all(r["status"] == "pending" for r in out), out
    rows = old[:-1] + [PROMPT + "python3 main.py", "You rolled: 2", PROMPT]  # the learner runs it now
    rig.clock.t = rig.s.step_t0 + 12.0
    res, _ = rig.s._need_run(step, [], {"passed": True})
    assert res[-1]["status"] == "pass" and res[-1]["detail"] == "ran in the terminal", res[-1]


def test_t5_cp12_a_cancelled_run_never_passes_the_run_row(tmp_path, monkeypatch):
    """02:19:19: "Ran python3 main.py · ran in the terminal" after Run it for me's line was cancelled by the venv
    activation's ^C. Before the fix the panel's command row counted as a new run."""
    from server.orchestrator.tests.test_session import run

    rig, _ = _run_rig(tmp_path, monkeypatch)
    rows = [PROMPT]

    async def go():
        await rig.s.learn("dice", mode="lesson")
        await rig.settle()
        await rig.s.goto_step(2)
        await rig.settle()
        rig.s._terminal_rows = lambda: rows
        rig.clock.t = rig.s.step_t0
        rig.s._need_run(rig.s.step, [], {"passed": True})  # baseline: an empty prompt
        return rig.s.step

    step = run(go())
    for swallowed in ([PROMPT + "python3 main.py", "^C", PROMPT + "source .venv/bin/activate", "(.venv) " + PROMPT],
                      [PROMPT + "python3 main.py", PROMPT + "source .venv/bin/activate", "(.venv) " + PROMPT]):
        rows[:] = swallowed
        for dt in (5.0, 8.0):
            rig.clock.t = rig.s.step_t0 + dt
            res, gate = rig.s._need_run(step, [], {"passed": True})
            assert res[-1]["status"] != "pass" and not gate["passed"], (swallowed, res[-1])
