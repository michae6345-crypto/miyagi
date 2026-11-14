import math
import random

import pytest

from server.checks import RunContext, evaluate_check, evaluate_step, step_passed


def status(check, ctx):
    return evaluate_check(check, ctx)["status"]


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def wd(tmp_path):
    (tmp_path / "pinn_convection.py").write_text(
        "import torch\n\ndef pde_residual(u_t, u_x, beta):\n    return u_t + beta * u_x\n"
    )
    return tmp_path


def flat_pinn_loss(n_steps=4000, every=50, seed=0):
    """β=30 convection PINN: loss plateaus around 0.25 with minibatch noise."""
    rng = random.Random(seed)
    pts = []
    for s in range(0, n_steps + 1, every):
        base = 0.2504 - 0.0014 * (s / n_steps)  # ~0.6% drift over the whole run
        pts.append((s, base * (1 + rng.gauss(0, 0.03))))
    return pts


def dropping_pinn_loss(n_steps=4000, every=50, seed=1):
    """After the β curriculum: loss decays ~exponentially from 0.25 toward 1e-3."""
    rng = random.Random(seed)
    return [(s, (0.25 * math.exp(-s / 800) + 1e-3) * (1 + rng.gauss(0, 0.05))) for s in range(0, n_steps + 1, every)]


# ---------------------------------------------------------------- file_exists
def test_file_exists(wd):
    ctx = RunContext(workdir=str(wd))
    assert status({"id": "a", "type": "file_exists", "label": "x", "file": "pinn_convection.py"}, ctx) == "pass"
    r = evaluate_check({"id": "b", "type": "file_exists", "label": "x", "file": "nope.py"}, ctx)
    assert r["status"] == "fail" and "nope.py" in r["detail"]
    assert r["checkId"] == "b" and r["label"] == "x"


# ---------------------------------------------------------------- file_contains
def test_file_contains_pass_fail_missing(wd):
    ctx = RunContext(workdir=str(wd))
    c = {"id": "c1", "type": "file_contains", "label": "residual", "file": "pinn_convection.py",
         "pattern": r"u_t\s*\+\s*\w*\s*\*\s*u_x"}
    r = evaluate_check(c, ctx)
    assert r["status"] == "pass" and r["detail"].endswith(":4")
    (wd / "pinn_convection.py").write_text("def pde_residual(u_t, u_x):\n    return u_t\n")
    assert status(c, ctx) == "fail"
    assert status({**c, "file": "missing.py"}, ctx) == "fail"


def test_file_contains_bad_regex_is_fail_not_crash(wd):
    r = evaluate_check({"id": "c", "type": "file_contains", "label": "x", "file": "pinn_convection.py",
                        "pattern": "u_t(("}, RunContext(workdir=str(wd)))
    assert r["status"] == "fail" and "invalid pattern" in r["detail"]


# ---------------------------------------------------------------- command_exit_ok
def test_command_exit_ok():
    c = {"id": "c2", "type": "command_exit_ok", "label": "runs", "command": "python pinn_convection.py --epochs 1"}
    assert status(c, RunContext()) == "pending"
    assert status(c, RunContext(command="python pinn_convection.py", running=True)) == "pending"
    assert status(c, RunContext(command="python pinn_convection.py --epochs 1", exit_code=0)) == "pass"
    # flags may differ; the script must match
    assert status(c, RunContext(command="python3 -u pinn_convection.py --epochs 5", exit_code=0)) == "pass"
    assert status(c, RunContext(command="python pinn_convection.py", exit_code=1)) == "fail"
    # a different script doesn't count
    assert status(c, RunContext(command="python other.py", exit_code=0)) == "pending"


# ---------------------------------------------------------------- output_contains
def test_output_contains():
    c = {"id": "o", "type": "output_contains", "label": "prints shape", "pattern": r"torch\.Size\(\[\d+, 1\]\)"}
    assert status(c, RunContext()) == "pending"
    assert status(c, RunContext(command="x", running=True, output_tail=["epoch 1"])) == "pending"
    assert status(c, RunContext(command="x", exit_code=0, output_tail=["u: torch.Size([256, 1])"])) == "pass"
    assert status(c, RunContext(command="x", exit_code=0, output_tail="nothing here")) == "fail"


# ---------------------------------------------------------------- metric_threshold
def test_metric_threshold():
    c = {"id": "c3", "type": "metric_threshold", "label": "loss < 1e-2", "metric": "loss", "op": "<",
         "value": 0.01, "by_step": 4000}
    assert status(c, RunContext(running=True, command="x")) == "pending"
    ctx = RunContext(running=True, command="x", metrics={"loss": [(100, 0.2), (200, 0.1)]})
    assert status(c, ctx) == "pending"  # not there yet, by_step not reached
    ctx.metrics["loss"] += [(s, 0.005) for s in range(300, 800, 100)]
    assert status(c, ctx) == "pass"
    # flat run reached by_step without hitting the threshold → fail
    flat = RunContext(running=True, command="x", metrics={"loss": flat_pinn_loss()})
    r = evaluate_check(c, flat)
    assert r["status"] == "fail" and "by step 4000" in r["detail"]
    # a single lucky minibatch does not pass (median smoothing)
    noisy = RunContext(running=True, command="x", metrics={"loss": [(s, 0.2) for s in range(0, 500, 100)] + [(500, 0.001)]})
    assert status(c, noisy) == "pending"


def test_metric_threshold_greater_and_run_end():
    c = {"id": "acc", "type": "metric_threshold", "label": "acc", "metric": "acc", "op": ">=", "value": 0.9}
    assert status(c, RunContext(exit_code=0, metrics={"acc": [(1, 0.5), (2, 0.95), (3, 0.96)]})) == "pass"
    assert status(c, RunContext(exit_code=0, metrics={"acc": [(1, 0.5), (2, 0.6)]})) == "fail"
    assert status(c, RunContext(exit_code=0)) == "fail"  # run ended, never logged acc


# ---------------------------------------------------------------- metric_trend
TREND = {"id": "c4", "type": "metric_trend", "label": "loss still dropping", "metric": "loss",
         "trend": "not_flat", "window": 1500}


def test_flat_pinn_loss_fails_not_flat():
    r = evaluate_check(TREND, RunContext(running=True, command="x", metrics={"loss": flat_pinn_loss()}))
    assert r["status"] == "fail", r
    assert "plateau" in r["detail"]


def test_dropping_pinn_loss_passes_not_flat():
    r = evaluate_check(TREND, RunContext(running=True, command="x", metrics={"loss": dropping_pinn_loss()}))
    assert r["status"] == "pass", r


def test_flat_curve_with_spikes_still_fails():
    pts = flat_pinn_loss(seed=3)
    pts[-3] = (pts[-3][0], 0.02)  # one lucky minibatch near the end
    pts[5] = (pts[5][0], 3.0)     # one blow-up early in the window
    assert status(TREND, RunContext(running=True, command="x", metrics={"loss": pts})) == "fail"


def test_trend_pending_until_window_covered():
    short = [(s, 0.25) for s in range(0, 300, 50)]
    assert status(TREND, RunContext(running=True, command="x", metrics={"loss": short})) == "pending"
    assert status(TREND, RunContext(exit_code=0, metrics={"loss": short})) == "fail"


def test_trend_decreasing():
    c = {**TREND, "trend": "decreasing"}
    assert status(c, RunContext(running=True, command="x", metrics={"loss": dropping_pinn_loss()})) == "pass"
    assert status(c, RunContext(running=True, command="x", metrics={"loss": flat_pinn_loss()})) == "fail"
    rising = [(s, 0.1 + s / 1000) for s in range(0, 2000, 50)]
    assert status(c, RunContext(running=True, command="x", metrics={"loss": rising})) == "fail"


def test_trend_ignores_nan_and_handles_negative_values():
    pts = [(s, -1.0 - s / 500) for s in range(0, 2000, 50)] + [(2000, float("nan"))]
    assert status(TREND, RunContext(running=True, command="x", metrics={"loss": pts})) == "pass"


# ---------------------------------------------------------------- visual
def test_visual_uses_supplied_verdict():
    c = {"id": "v", "type": "visual", "label": "plot shows wave", "prompt": "Is there a sine wave?"}
    assert status(c, RunContext()) == "pending"
    assert status(c, RunContext(visual={"v": {"pass": True, "detail": "yes"}})) == "pass"
    assert status(c, RunContext(visual={"v": {"pass": False}})) == "fail"


# ---------------------------------------------------------------- evaluate_step
def test_evaluate_step_all_and_filtered(wd):
    step = {"id": "s4", "checks": [
        {"id": "c1", "type": "file_contains", "label": "residual", "file": "pinn_convection.py", "pattern": r"beta \* u_x"},
        TREND,
        {"id": "z", "type": "bogus", "label": "?"},
    ]}
    ctx = RunContext(workdir=str(wd), running=True, command="x", metrics={"loss": dropping_pinn_loss()})
    res = evaluate_step(step, ctx)
    assert [r["status"] for r in res] == ["pass", "pass", "fail"]
    assert not step_passed(res)
    only_files = evaluate_step(step, ctx, types={"file_exists", "file_contains"})
    assert [r["checkId"] for r in only_files] == ["c1"]
    assert step_passed(only_files)
    assert not step_passed([])
