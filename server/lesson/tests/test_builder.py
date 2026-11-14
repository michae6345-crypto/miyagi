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
    a["steps"][2]["checks"][0].pop("metric_pattern")  # screen metric check that can't read the terminal...
    a["steps"][2]["checks"][0]["metric"] = "val_acc"  # ...on a metric the workdir never prints (so it can't be auto-filled)
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
    g = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, detail=True))
    assert schema_errors(g) == [] and g["build"]["adapted"] is True
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
    assert any(w.startswith("no metric check") for w in g["build"]["warnings"])
    assert "s3: no screen checks (every step needs at least one screen_* or metric_* check)" in g["build"]["warnings"]
    assert fake["detail"] == 0  # clip pass is opt-in


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


def test_adapt_failure_falls_back_to_draft_and_says_so(fake, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("429 RESOURCE_EXHAUSTED per day")

    monkeypatch.setattr(gemini, "adapt_checks", boom)
    draft = json.loads(json.dumps(DRAFT))
    draft["steps"][0]["checks"] = [{"type": "screen_contains", "label": "residual", "app": "Code", "pattern": r"f_t\s*-\s*f_xx"},
                                   {"type": "file_contains", "label": "residual", "file": "pinn_diffusion.py", "pattern": "f_t"}]
    monkeypatch.setattr(gemini, "watch_video", lambda *a, **k: _async(draft))
    g = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, refresh=True))
    assert g["build"]["adapted"] is False and g["build"]["warnings"][0].startswith("adapt pass failed")
    assert not (builder.CACHE_DIR / f"{builder.cache_key(URL, 'train a PINN', WORKDIR)}.json").exists()  # not cached
    pinn = g["steps"][1]
    assert [c["type"] for c in pinn["checks"]] == ["screen_contains"] and [c["type"] for c in pinn["precision_checks"]] == ["file_contains"]

    # readapt reuses the cached video draft: no new watch call
    monkeypatch.setattr(gemini, "adapt_checks", lambda *a, **k: _async(_good_adapt()))
    watched = fake["watch"]
    g2 = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, readapt=True))
    assert g2["build"]["adapted"] is True and fake["watch"] == watched


async def _async(v):
    return json.loads(json.dumps(v))


def test_classify_quota_errors():
    assert gemini._classify(RuntimeError("429 RESOURCE_EXHAUSTED ... GenerateRequestsPerDayPerProjectPerModel-FreeTier")) == ("daily", 0.0)
    kind, wait = gemini._classify(RuntimeError("429 RESOURCE_EXHAUSTED per minute. Please retry in 20.04s."))
    assert kind == "rate" and 20 < wait < 22
    assert gemini._classify(RuntimeError("503 UNAVAILABLE high demand"))[0] == "busy"
    assert gemini._classify(RuntimeError("404 NOT_FOUND no longer available to new users"))[0] == "gone"
    assert gemini._classify(RuntimeError("403 PERMISSION_DENIED"))[0] == "auth"


def test_precision_metric_check_is_promoted_with_protocol_pattern():
    g = {"steps": [{"id": "s8", "checks": [{"id": "s8c1", "type": "screen_absent", "label": "x", "app": "Terminal", "pattern": "Traceback"}],
                    "precision_checks": [{"id": "s8p1", "type": "metric_threshold", "label": "loss", "metric": "loss", "op": "<", "value": 0.01}]}]}
    builder.complete_metric_checks(g, {"loss", "test_loss"})
    c = g["steps"][0]["checks"][1]
    assert c["id"] == "s8c2" and c["type"] == "metric_threshold"
    m = re.search(c["metric_pattern"], '::metric:: {"step": 1200, "name": "loss", "value": 0.0031}')
    assert m and m["step"] == "1200" and float(m["value"]) == 0.0031
    assert not re.search(c["metric_pattern"], '::metric:: {"step": 1200, "name": "test_loss", "value": 0.4}')
    # OCR mangles quotes/braces: still parses
    assert re.search(c["metric_pattern"], "::metric:: (step: 40, name: loss, value: 1.5e-3)")


def test_literal_code_pasted_as_regex_is_escaped():
    assert builder.looks_like_literal("lhs(2, Nf)")
    for ok in (r"lhs\(2,\s*Nf\)", "(bottom|top)_X", "Traceback|Error", "import torch", "useState"):
        assert not builder.looks_like_literal(ok), ok
    p = builder.literal_pattern("lhs(2, Nf)")
    assert re.search(p, "torch.from_numpy(lhs(2, Nf))") and re.search(p, "lhs(2,Nf)")


def test_community_signals_attach_to_the_right_step(monkeypatch):
    import sys
    import types as pytypes

    mod = pytypes.ModuleType("server.finder.web")

    async def community_signals(url):
        return [{"t": "16:40", "text": "create_graph=True is required or the 2nd derivative is None", "source": "YouTube comments"},
                {"timestamp": 5, "text": "ignored: before any step"}, {"t": 970}]

    mod.community_signals = community_signals
    monkeypatch.setitem(sys.modules, "server.finder.web", mod)
    g = {"steps": [{"id": "s1", "video": {"start": 902, "end": 1096}, "common_mistakes": []}]}
    assert asyncio.run(builder.add_community_mistakes(g, URL)) == 1
    assert g["steps"][0]["common_mistakes"] == ["create_graph=True is required or the 2nd derivative is None (at 16:40, YouTube comments)"]


def test_cache_key_tracks_workdir_layout_not_contents(tmp_path):
    a = tmp_path / "proj"
    a.mkdir()
    (a / "main.py").write_text("print(1)")
    k1 = builder.cache_key(URL, "goal", str(a))
    (a / "main.py").write_text("print(2)  # learner edit")
    assert builder.cache_key(URL, "goal", str(a)) == k1
    (a / "util.py").write_text("")
    assert builder.cache_key(URL, "goal", str(a)) != k1


def test_detail_failures_become_warnings(fake, monkeypatch):
    async def flaky(url, start, end, title, fps=2.0):
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(gemini, "step_detail", flaky)
    g = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, refresh=True, detail=True))
    assert sum(w.startswith(("s1: clip", "s2: clip", "s3: clip")) for w in g["build"]["warnings"]) == 3
