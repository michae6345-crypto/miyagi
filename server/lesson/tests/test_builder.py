"""Offline tests: Gemini is faked, so these run in CI without a key."""

import asyncio
import json
import re
from pathlib import Path

import pytest

from server.lesson import builder, gemini
from server.lesson.precision import report
from server.lesson.schema import lint, schema_errors
from server.lesson.workdir import scan

FIX = Path(__file__).resolve().parents[1] / "fixtures"
WORKDIR = str(FIX / "diffusion_workdir")
URL = "https://www.youtube.com/watch?v=AXXnSzmpyoI"

DRAFT = {
    "title": "PINNs in PyTorch",
    "libraries": [{"name": "torch", "version": "1.11"}, {"name": "pyDOE", "version": ""}],
    "steps": [
        {"start": "15:02", "end": "18:16", "title": "Code the PINN", "instructions": "Write FCN.", "checks": [], "hints": ["What does autograd.grad return?"],
         "explanations": [{"topic": "automatic differentiation", "t": "16:10"}], "code": "f_t - f_xx"},
        {"start": "2:23", "end": "3:10", "title": "Import the libraries", "instructions": "Import torch.", "checks": [], "hints": []},
        {"start": "18:16", "end": "23:34", "title": "Train the PINN", "instructions": "Train with Adam.", "checks": [], "hints": []},
    ],
}


MP = r"step\W+(?P<step>\d+)\W+name\W+loss\W+value\W+(?P<value>[0-9.eE+-]+)"


def _good_adapt():
    return {"steps": [
        {"index": 1, "checks": [{"type": "screen_contains", "label": "imports torch", "app": "Code", "pattern": r"import\s+torch"}],
         "precision_checks": [{"type": "file_contains", "label": "imports torch", "file": "pinn_diffusion.py", "pattern": r"import torch"}],
         "targets": [{"app": "Code", "file": "pinn_diffusion.py", "match": "import torch", "caption": "imports"}]},
        {"index": 2, "checks": [{"type": "screen_contains", "label": "residual", "app": "Code", "pattern": r"f_t\s*-\s*f_xx"},
                                {"type": "screen_absent", "label": "no traceback", "app": "Terminal", "pattern": "Traceback"}],
         "precision_checks": [{"type": "command_exit_ok", "label": "script runs", "command": "python pinn_diffusion.py --steps 1"}],
         "targets": [{"app": "Code", "match": "def lossPDE", "caption": "residual"}]},
        {"index": 3, "checks": [{"type": "metric_threshold", "label": "loss < 1e-2", "metric": "loss", "metric_pattern": MP, "op": "<", "value": 0.01, "by_step": 2000}],
         "precision_checks": [{"type": "metric_threshold", "label": "loss < 1e-2", "metric": "loss", "op": "<", "value": 0.01, "by_step": 2000}],
         "targets": []},
    ]}


def _bad_adapt():
    a = _good_adapt()
    a["steps"][1]["checks"][0]["pattern"] = r"f_t\s*-\s*(f_xx"  # does not compile
    a["steps"][2]["checks"][0].pop("metric_pattern")  # screen metric check that can't read the terminal
    a["steps"][2]["precision_checks"][0]["metric"] = "train_loss"  # not printed by the workdir
    a["steps"][0]["checks"].append({"type": "file_contains", "label": "wrong list", "file": "pinn_diffusion.py", "pattern": "x"})
    a["steps"][0]["checks"].append({"type": "visual", "label": "looks right", "prompt": "?"})
    return a


@pytest.fixture
def fake(monkeypatch, tmp_path):
    calls = {"watch": 0, "detail": 0, "adapt": []}

    async def watch_video(url, goal, fps=None):
        calls["watch"] += 1
        return json.loads(json.dumps(DRAFT))

    async def step_detail(url, start, end, title, fps=2.0):
        calls["detail"] += 1
        return {"code": "x" * 3, "printed_metrics": ["loss"]}

    responses = []

    async def adapt_checks(goal, steps, summary, feedback=None):
        calls["adapt"].append(feedback)
        return responses.pop(0) if responses else _good_adapt()

    monkeypatch.setattr(gemini, "watch_video", watch_video)
    monkeypatch.setattr(gemini, "step_detail", step_detail)
    monkeypatch.setattr(gemini, "adapt_checks", adapt_checks)
    monkeypatch.setattr(builder, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(builder, "RAW_DIR", tmp_path / "raw")
    calls["responses"] = responses
    return calls


def test_parse_ts():
    assert builder.parse_ts("7:42") == 462
    assert builder.parse_ts("1:02:03") == 3723
    assert builder.parse_ts("75s") == 75
    assert builder.parse_ts(12.5) == 12.5
    assert builder.parse_ts("soon") is None


def test_normalize_orders_and_unoverlaps():
    d = builder.normalize_draft(json.loads(json.dumps(DRAFT)))
    assert [s["title"] for s in d["steps"]] == ["Import the libraries", "Code the PINN", "Train the PINN"]
    assert [s["index"] for s in d["steps"]] == [1, 2, 3]
    for a, b in zip(d["steps"], d["steps"][1:]):
        assert a["end"] <= b["start"]
    assert d["steps"][1]["explanations"][0]["t"] == 970


def test_build_retries_with_feedback_then_caches(fake):
    fake["responses"].append(_bad_adapt())
    g = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR))
    assert schema_errors(g) == []
    assert lint(g, {"loss", "test_loss"}, {"pinn_diffusion.py"}) == []
    assert len(fake["adapt"]) == 2 and fake["adapt"][0] is None
    fb = "\n".join(fake["adapt"][1])
    assert "does not compile" in fb and "metric_pattern" in fb and "train_loss" in fb and "not allowed in `checks`" in fb
    assert "visual" not in fb  # visual is dropped silently
    assert g["sources"][0]["videoId"] == "AXXnSzmpyoI"
    assert g["lesson"]["libraries"]["torch"] == "1.11"
    s2 = g["steps"][1]
    assert s2["video"] == {"sourceId": "src1", "start": 902.0, "end": 1096.0}
    assert [c["id"] for c in s2["checks"]] == ["s2c1", "s2c2"] and s2["precision_checks"][0]["id"] == "s2p1"
    assert s2["targets"][0]["app"] == "Code"
    assert fake["detail"] == 3

    # second call: served from cache, no Gemini
    g2 = asyncio.run(builder.build_lesson(URL, "Train a  PINN", WORKDIR))
    assert g2["steps"] == g["steps"] and fake["watch"] == 1


def test_repair_drops_broken_checks_when_retries_run_out(fake):
    fake["responses"].extend([_bad_adapt()] * builder.ADAPT_ATTEMPTS)
    g = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, refresh=True))
    assert schema_errors(g) == []
    assert lint(g, {"loss", "test_loss"}, {"pinn_diffusion.py"}) == [s for s in g["build"]["warnings"]]
    s1, s2, s3 = g["steps"]
    assert [c["type"] for c in s1["checks"]] == ["screen_contains"]
    assert [c["id"] for c in s1["precision_checks"]] == ["s1p1", "s1p2"]  # misplaced file_contains moved, not dropped
    assert [(c["type"], c["id"]) for c in s2["checks"]] == [("screen_absent", "s2c1")]
    # step 3 lost its only screen check and has no target to fall back on -> reported, not hidden
    assert s3["checks"] == [] and s3["precision_checks"] == []
    assert g["build"]["warnings"] == ["s3: no screen checks (every step needs at least one screen_* or metric_* check)"]


def test_fallback_screen_check_from_target():
    step = {"id": "s4", "targets": [{"app": "Code", "match": "def lossPDE(self, x)", "caption": "PDE residual"}]}
    (c,) = builder.fallback_screen_checks(step)
    assert c["type"] == "screen_contains" and re.search(c["pattern"], "    def  lossPDE(self, x):")


def test_rejects_non_youtube():
    with pytest.raises(ValueError):
        asyncio.run(builder.build_lesson("https://example.com/post", "x", WORKDIR))


def test_workdir_scan_finds_metrics_and_flags():
    info = scan(WORKDIR)
    assert info.files == ["pinn_diffusion.py"]
    assert info.metrics == {"loss", "test_loss"}
    assert info.cli_flags["pinn_diffusion.py"] == ["--steps", "--lr"]


def test_fixture_is_valid_and_self_scores_perfectly():
    exp = json.loads((FIX / "toscano_pinn_part1.expected.json").read_text())
    assert schema_errors(exp) == []
    r = report(exp, exp, {"loss", "test_loss"}, {"pinn_diffusion.py"})
    assert r["steps"]["f1"] == 1.0 and r["checks"]["regex_accepts_solution"] == 1.0 and r["checks"]["lint_problems"] == 0
    assert r["checks"]["metric_pattern_parses_output"] == 1.0 and r["checks"]["screen_first_share"] == 1.0
