"""Offline tests: Gemini is faked, so these run in CI without a key."""

import asyncio
import json
import re
from pathlib import Path

import pytest

from server.lesson import claude  # noqa: E402

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

    async def watch_video(url, goal, fps=None, **kw):
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
    monkeypatch.setenv("LESSON_ENGINE", "gemini")  # tests never reach a real API; Claude tests opt in

    async def offline(*a, **k):
        raise RuntimeError("offline test: no real Claude/transcript calls")

    from server.lesson import claude as _claude, transcript as _transcript
    monkeypatch.setattr(_claude, "watch_transcript", offline)
    monkeypatch.setattr(_claude, "adapt_checks", adapt_checks)  # the adapt pass is Claude's
    monkeypatch.setattr(_transcript, "fetch_video_info", offline)

    async def meta(vid):
        calls["meta"] = calls.get("meta", 0) + 1
        return {"video_id": vid, "title": "Fake tutorial", "description": "Code: https://github.com/x/y", "length_s": 600, "chapters": []}

    monkeypatch.setattr(_transcript, "fetch_metadata", meta)
    from server.lesson import links as _links

    async def no_net_resolve(client, url):  # tests never touch the network
        return "dead" not in url

    monkeypatch.setattr(_links, "_resolves", no_net_resolve)
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

    monkeypatch.setattr(claude, "adapt_checks", boom)
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
    monkeypatch.setattr(claude, "adapt_checks", lambda *a, **k: _async(_good_adapt()))
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


# ---- Claude (transcript) path -------------------------------------------------
from server.lesson import claude, transcript  # noqa: E402

INFO = {"video_id": "AXXnSzmpyoI", "title": "PINNs", "description": "", "length_s": 1460, "chapters": [],
        "transcript": [{"t": 902.0, "text": "now let's code the PINN"}], "sources": {"transcript": "youtube-transcript-api"}, "errors": []}


def _claude_fakes(monkeypatch, calls):
    async def fetch(vid):
        calls.append("transcript")
        return INFO

    async def watch_transcript(info, goal):
        calls.append("claude-watch")
        claude.last_model = "claude-opus-5-5"
        return json.loads(json.dumps(DRAFT))

    async def claude_adapt(goal, steps, summary, feedback=None):
        calls.append("claude-adapt")
        claude.last_model = "claude-opus-5-5"
        return _good_adapt()

    monkeypatch.setattr(transcript, "fetch_video_info", fetch)
    monkeypatch.setattr(claude, "watch_transcript", watch_transcript)
    monkeypatch.setattr(claude, "adapt_checks", claude_adapt)


def test_claude_takes_over_when_gemini_fails(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "auto")
    async def gemini_down(*a, **k):
        raise RuntimeError("Gemini call failed on ['gemini-4-hydrogen']: 429 RESOURCE_EXHAUSTED PerDay")

    monkeypatch.setattr(gemini, "watch_video", gemini_down)
    monkeypatch.setattr(gemini, "adapt_checks", gemini_down)
    calls = []
    _claude_fakes(monkeypatch, calls)
    g = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, refresh=True, detail=True))
    assert calls == ["transcript", "claude-watch", "claude-adapt"]
    assert g["build"]["model"] == {"video": "claude-opus-5-5 (transcript via youtube-transcript-api)", "adapt": "claude-opus-5-5"}
    assert g["build"]["adapted"] is True and schema_errors(g) == []
    assert fake["detail"] == 0  # clip pass needs a model that sees the video


def test_engine_env_forces_claude(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "claude")
    calls = []
    _claude_fakes(monkeypatch, calls)
    asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, refresh=True))
    assert fake["watch"] == 0 and calls[:2] == ["transcript", "claude-watch"]


def test_both_engines_failing_raises_with_both_errors(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "auto")
    async def gemini_down(*a, **k):
        raise RuntimeError("gemini quota")

    async def no_transcript(vid):
        raise RuntimeError("no transcript for AXXnSzmpyoI")

    monkeypatch.setattr(gemini, "watch_video", gemini_down)
    monkeypatch.setattr(transcript, "fetch_video_info", no_transcript)
    with pytest.raises(RuntimeError) as ei:
        asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, refresh=True))
    assert "gemini quota" in str(ei.value) and "no transcript" in str(ei.value)


def test_strict_schema_closes_every_object():
    from server.lesson.schema import VIDEO_DRAFT_SCHEMA

    s = claude.strict_schema(VIDEO_DRAFT_SCHEMA)
    objs = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "object":
                objs.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(s)
    assert objs and all(o["additionalProperties"] is False for o in objs)
    assert "additionalProperties" not in VIDEO_DRAFT_SCHEMA  # original untouched


def test_parse_chapters():
    desc = "Learn git!\n00:00 Intro\n00:21 Configuring Git with 'git config'\n1:49 git init\n1:02:03 Outro\nnot a chapter 5:00"
    ch = transcript.parse_chapters(desc)
    assert [c["t"] for c in ch] == [0, 21, 109, 3723] and ch[1]["title"] == "Configuring Git with 'git config'"
    assert transcript.parse_chapters("0:30 a\n1:00 b\n2:00 c") == []  # YouTube needs a 0:00 start


def test_cache_hit_ignores_goal_wording_for_same_video_and_workdir(fake):
    g = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR))
    assert g["build"]["workdir_fp"]
    watched = fake["watch"]
    g2 = asyncio.run(builder.build_lesson(URL, "how do physics informed nets work?", WORKDIR))
    assert fake["watch"] == watched and g2["steps"] == g["steps"]


def test_extract_json_tolerates_fences_and_prose():
    assert claude.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert claude.extract_json('Here you go: {"steps": []} done') == {"steps": []}
    with pytest.raises(ValueError):
        claude.extract_json("no json here")


def test_precision_backup_never_looser_than_screen_check():
    g = {"steps": [{"id": "s8", "checks": [
        {"id": "s8c4", "type": "metric_threshold", "label": "loss < 1e-2 by 2000", "metric": "loss", "op": "<", "value": 0.01, "by_step": 2000, "metric_pattern": "x"}],
        "precision_checks": [
            {"id": "s8p1", "type": "metric_threshold", "label": "loss low", "metric": "loss", "op": "<=", "value": 0.05},
            {"id": "s8p2", "type": "metric_threshold", "label": "test", "metric": "test_loss", "op": "<", "value": 0.5},
            {"id": "s8p3", "type": "metric_threshold", "label": "tight", "metric": "loss", "op": "<", "value": 0.001, "by_step": 1000}]}]}
    builder.align_precision_metrics(g)
    p1, p2, p3 = g["steps"][0]["precision_checks"]
    assert (p1["op"], p1["value"], p1["by_step"]) == ("<", 0.01, 2000)  # tightened to the screen check
    assert p2["value"] == 0.5 and "by_step" not in p2  # other metric untouched
    assert (p3["value"], p3["by_step"]) == (0.001, 1000)  # already stricter: kept


def test_slow_gemini_hands_over_to_claude_within_the_cap(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "auto")
    monkeypatch.setenv("LESSON_GEMINI_TIMEOUT", "0.2")

    async def slow_gemini(url, goal, fps=None, **kw):
        await asyncio.sleep(5)

    monkeypatch.setattr(gemini, "watch_video", slow_gemini)
    calls = []
    _claude_fakes(monkeypatch, calls)
    import time as _t
    t0 = _t.time()
    g = asyncio.run(builder.build_lesson(URL, "anything", WORKDIR, refresh=True))
    assert _t.time() - t0 < 2
    assert g["build"]["model"]["video"].startswith("claude-opus-5-5 (transcript")
    assert calls[:2] == ["transcript", "claude-watch"]


def test_adapt_pass_is_claude_even_when_gemini_watched(fake, monkeypatch):
    def gemini_adapt_must_not_run(*a, **k):
        raise AssertionError("Gemini must only watch videos")

    monkeypatch.setattr(gemini, "adapt_checks", gemini_adapt_must_not_run)
    claude.last_model = "claude-opus-5-5"
    g = asyncio.run(builder.build_lesson(URL, "anything", WORKDIR, refresh=True))
    assert g["build"]["adapted"] is True and g["build"]["model"]["adapt"] == "claude-opus-5-5"


# ---- S3 eval fixes -------------------------------------------------------------

def _st(start, end, title, **kw):
    return {"start": start, "end": end, "title": title, "instructions": title, "checks": kw.pop("checks", []), "hints": [], **kw}


def test_micro_steps_merge_and_explanations_rehome():
    draft = {"steps": [
        _st("0:10", "1:00", "Init repo", explanations=[{"topic": "staging", "t": "1:40"}]),
        _st("1:00", "1:12", "Check status", checks=[{"type": "screen_contains", "label": "status", "app": "Terminal", "pattern": "On branch"}]),
        _st("1:12", "3:00", "Stage and commit", explanations=[{"topic": "init", "t": "0:30"}]),
        _st("3:00", "5:00", "Create a branch"),
        _st("5:00", "7:00", "Merge it"),
    ]}
    d = builder.normalize_draft(draft)
    titles = [s["title"] for s in d["steps"]]
    assert titles == ["Init repo", "Stage and commit", "Create a branch", "Merge it"]  # 12 s step folded into its predecessor
    assert d["steps"][0]["end"] == 72 and d["steps"][0]["checks"][0]["pattern"] == "On branch"
    assert [e["topic"] for e in d["steps"][0]["explanations"]] == ["init"]  # t=0:30 belongs to step 1
    assert [e["topic"] for e in d["steps"][1]["explanations"]] == ["staging"]  # t=1:40 belongs to step 2


def test_terminal_check_that_matches_the_typed_command_is_rejected():
    from server.lesson.schema import echoes_command

    step = {"id": "s3", "title": "Query items", "run_command": "curl 'localhost:8000/items?limit=5'",
            "checks": [{"id": "s3c1", "type": "screen_contains", "label": "limit", "app": "Terminal", "pattern": r"items\?limit=\d+"}]}
    probs = lint({"steps": [step]})
    assert any("matches the command the learner types" in p for p in probs)
    assert any("no check on its output" in p for p in probs)
    assert echoes_command(step["checks"][0], step["run_command"])
    step["checks"].append({"id": "s3c2", "type": "screen_contains", "label": "json", "app": "Terminal", "pattern": r'"items":\s*\['})
    assert not any("no check on its output" in p for p in lint({"steps": [step]}))


def test_browser_checks_are_not_tied_to_one_browser():
    g = {"steps": [{"id": "s1", "checks": [{"id": "s1c1", "type": "screen_contains", "label": "x", "app": "Google Chrome", "pattern": "Hello"},
                                          {"id": "s1c2", "type": "screen_contains", "label": "y", "app": "Code", "pattern": "App"}],
                    "precision_checks": [], "targets": [{"app": "Safari", "match": "Hello", "caption": "page"}]}]}
    builder.normalize_checks(g, set())
    s = g["steps"][0]
    assert "app" not in s["checks"][0] and s["checks"][1]["app"] == "Code" and "app" not in s["targets"][0]


def test_empty_workdir_prompt_asks_for_a_setup_step(tmp_path):
    assert "step 1 must create anything the tutorial assumes" in scan(str(tmp_path / "nope")).summary_for_prompt()


# ---- S3 re-run fixes -------------------------------------------------------------

def test_output_check_matching_the_steps_own_code_is_rejected():
    step = {"id": "s5", "title": "Filter by country", "code": "df[df['Country'] == 'France']",
            "instructions": "Filter with `df['Country']`.", "targets": [],
            "checks": [{"id": "s5c1", "type": "screen_contains", "label": "table shown", "pattern": "Country|Customer"}]}
    assert any("matches the step's own code" in p for p in lint({"steps": [step]}))
    step["checks"][0]["app"] = "Terminal"  # scoped to where the output appears: fine
    assert not any("own code" in p for p in lint({"steps": [step]}))


def test_notebook_steps_count_code_scoped_output_checks():
    step = {"id": "s2", "title": "Inspect the data", "run_command": "Run each notebook cell (Shift+Enter)", "code": "df.info()",
            "targets": [], "checks": [{"id": "s2c1", "type": "screen_contains", "label": "info shown", "app": "Code",
                                      "pattern": r"RangeIndex:\s*\d+\s+entries"}]}
    assert lint({"steps": [step]}) == []
    shell = dict(step, run_command="python inspect.py")  # a real shell step needs output outside the editor
    assert any("no check on its output" in p for p in lint({"steps": [shell]}))


def test_generic_patterns_are_too_weak():
    from server.lesson.schema import is_weak

    for weak in (r"\*\s*\S+", r"\|\s*/", r"\bmain\b", r"\S+\s+0\.1\.0"):
        assert is_weak({"type": "screen_contains", "pattern": weak}), weak
    for ok in ("Successfully rebased", r"RangeIndex:\s*\d+\s+entries", r"(?P<value>\d+)\s+passed", r"Local:\s+http://localhost:\d+", "Traceback|Error:|ERR!"):
        assert not is_weak({"type": "screen_contains", "pattern": ok}), ok
    assert not is_weak({"type": "screen_absent", "pattern": "x"})  # absence checks may be broad


def test_race_takes_claude_after_a_short_grace(fake, monkeypatch):
    import time as _t

    monkeypatch.setenv("LESSON_ENGINE", "auto")
    monkeypatch.setenv("LESSON_GEMINI_GRACE", "0.2")

    async def slow_gemini(url, goal, fps=None, **kw):
        await asyncio.sleep(5)

    monkeypatch.setattr(gemini, "watch_video", slow_gemini)
    calls = []
    _claude_fakes(monkeypatch, calls)
    t0 = _t.time()
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert _t.time() - t0 < 1.5 and g["build"]["model"]["video"].startswith("claude")


def test_race_prefers_gemini_when_it_answers_in_time(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "auto")
    calls = []
    _claude_fakes(monkeypatch, calls)

    async def slow_claude_watch(info, goal):
        await asyncio.sleep(0.3)
        return json.loads(json.dumps(DRAFT))

    monkeypatch.setattr(claude, "watch_transcript", slow_claude_watch)
    gemini.last_model = "gemini-4-hydrogen"
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert g["build"]["model"]["video"].startswith("gemini-4-hydrogen")


def test_progress_callback_reports_stable_stages(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "auto")

    async def gemini_down(*a, **k):
        raise RuntimeError("Gemini call failed: 429 RESOURCE_EXHAUSTED PerDay")

    monkeypatch.setattr(gemini, "watch_video", gemini_down)
    calls = []
    _claude_fakes(monkeypatch, calls)
    seen = []
    asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True, on_progress=lambda s, m: seen.append((s, m))))
    stages = [s for s, _ in seen]
    assert set(stages) <= set(builder.STAGES)
    assert ("engine_switch", "quota") in seen and ("steps_ready", "claude") in seen
    assert stages[-1] == "done" and "adapting" in stages and "reading_transcript" in stages and "writing_steps" in stages
    seen.clear()
    asyncio.run(builder.build_lesson(URL, "other words", WORKDIR, on_progress=lambda s, m: seen.append((s, m))))
    assert [s for s, _ in seen] == ["cache_hit", "done"]


# ---- S3 third-run fixes ----------------------------------------------------------

def test_standard_output_patterns_pass_their_own_lint():
    from server.lesson.schema import STANDARD_OUTPUTS, is_weak

    for _detect, app, label, pattern in STANDARD_OUTPUTS:
        assert not is_weak({"type": "screen_contains", "pattern": pattern}), (label, pattern)


def test_repair_adds_a_standard_output_check_to_a_run_step():
    from server.lesson.workdir import WorkdirInfo

    g = {"steps": [
        {"id": "s7", "title": "Start the dev server", "run_command": "npm run dev",
         "checks": [{"id": "s7c1", "type": "screen_absent", "label": "no errors", "app": "Terminal", "pattern": "ERR!|Error"}],
         "precision_checks": [], "targets": []},
        {"id": "s5", "title": "Filter rows", "run_command": "Run the notebook cell", "code": "df[df['Country'] == 'France']",
         "checks": [{"id": "s5c1", "type": "screen_contains", "label": "filtered", "app": "Code", "pattern": "Country|Quantity"}],
         "precision_checks": [], "targets": []},
    ]}
    out = builder.repair(g, WorkdirInfo(root="/x", exists=False))
    s7, s5 = out["steps"]
    assert s7["checks"][-1]["pattern"] == r"Local:\s+http://localhost:\d+" and s7["checks"][-1]["id"] == "s7c2"
    assert s5["checks"][-1]["app"] == "Code" and "rows" in s5["checks"][-1]["pattern"]  # notebook: rendered in the editor
    assert not any("no check on its output" in p for p in lint(out))


def test_adapt_retries_only_failing_steps_and_stops_without_progress(fake):
    good = _good_adapt()
    bad_step2 = json.loads(json.dumps(good))
    bad_step2["steps"][1]["checks"][0]["pattern"] = r"(f_xx"  # step 2 broken
    only2 = {"steps": [bad_step2["steps"][1]]}  # model returns the same broken step again
    fake["responses"].extend([bad_step2, only2, only2])
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert len(fake["adapt"]) == 2  # round 2 made no progress -> stopped, no 3rd round
    assert all(p.startswith("s2") for p in fake["adapt"][1])  # only step 2's problems were re-sent
    assert g["build"]["adapted"] is True and schema_errors(g) == []


def test_it_runs_checks_use_the_stacks_own_error_text():
    def g(cmd):
        return {"lesson": {"libraries": {}}, "steps": [{"id": "s1", "run_command": cmd, "precision_checks": [], "targets": [],
                "checks": [{"id": "s1c1", "type": "screen_absent", "label": "no errors", "app": "Terminal", "pattern": "Traceback|Error:|ERR!"}]}]}
    pats = {cmd: builder.normalize_checks(g(cmd), set())["steps"][0]["checks"][0]["pattern"]
            for cmd in ("npm run dev", "cargo run", "git rebase main", "python app.py")}
    assert "ERR!" in pats["npm run dev"] and "Traceback" not in pats["npm run dev"]
    assert pats["cargo run"].startswith(r"error\[E") and pats["git rebase main"].startswith("fatal:")
    assert pats["python app.py"] == "Traceback|Error:|ERR!"  # python keeps it


def test_adapt_runs_in_parallel_batches(fake, monkeypatch):
    sizes = []

    async def adapt(goal, steps, summary, feedback=None):
        sizes.append(len(steps))
        await asyncio.sleep(0.2)
        return {"steps": [{"index": s["index"], "checks": [{"type": "screen_contains", "label": "x", "app": "Code", "pattern": "function\\s+App"}],
                           "targets": []} for s in steps]}

    monkeypatch.setattr(claude, "adapt_checks", adapt)
    monkeypatch.setattr(builder, "ADAPT_BATCH", 1)
    import time as _t
    t0 = _t.time()
    asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert sizes[:3] == [1, 1, 1] and _t.time() - t0 < 0.55  # three 0.2 s calls ran concurrently


# ---- S3 Gemini-path fixes ---------------------------------------------------------

def test_auto_waits_for_gemini_even_when_claude_is_ready_first(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "auto")
    calls = []
    _claude_fakes(monkeypatch, calls)  # Claude answers instantly
    seen = {}

    async def gemini_slower(url, goal, fps=None, context=""):
        seen["context"] = context
        await asyncio.sleep(0.4)
        return json.loads(json.dumps(DRAFT))

    monkeypatch.setattr(gemini, "watch_video", gemini_slower)
    gemini.last_model = "gemini-4-hydrogen"
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert g["build"]["model"]["video"].startswith("gemini-4-hydrogen")
    assert "https://github.com/x/y" in seen["context"] and "Fake tutorial" in seen["context"]  # description reaches Gemini


def test_vague_setup_step_and_repeated_checks_are_linted():
    chk = {"id": "c", "type": "screen_contains", "label": "x", "app": "Code", "pattern": r"useState\("}
    steps = [{"id": "s1", "title": "Get the starter", "instructions": "Clone the example repository from the tutorial.", "checks": [dict(chk, id="s1c1")]},
             {"id": "s2", "title": "Add state", "instructions": "Add a counter.", "checks": [dict(chk, id="s2c1")]}]
    probs = lint({"steps": steps})
    assert any(p.startswith("s1: setup step") for p in probs) and any(p.startswith("s2: its checks repeat") for p in probs)
    steps[0]["instructions"] = "Run `git clone https://github.com/x/y` and cd into it."
    steps[1]["checks"].append({"id": "s2c2", "type": "screen_contains", "label": "list", "app": "Code", "pattern": r"items\.map\("})
    assert lint({"steps": steps}) == []


def test_notebook_cells_get_a_run_command():
    draft = {"title": "pandas", "files": ["analysis.ipynb"], "libraries": [{"name": "pandas", "version": "2.x"}],
             "steps": [{"index": 1, "start": 0, "end": 60, "title": "Load the data", "instructions": "Load it.", "code": "df = pd.read_csv('orders.csv')", "checks": []},
                       {"index": 2, "start": 60, "end": 120, "title": "Read along", "instructions": "Listen.", "checks": []}]}
    g = builder.assemble(draft, "x", {"steps": []})
    assert g["steps"][0]["run_command"] == builder.NOTEBOOK_RUN and "run_command" not in g["steps"][1]


def test_built_by_and_claude_first_switch(fake, monkeypatch):
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert g["lesson"]["builtBy"] == "gemini"
    monkeypatch.setenv("LESSON_ENGINE", "auto")
    monkeypatch.setenv("LESSON_PREFER", "claude")
    monkeypatch.setenv("LESSON_GEMINI_TIMEOUT", "30")

    async def slow_gemini(url, goal, fps=None, **kw):
        await asyncio.sleep(9)  # longer than the 8 s Claude-first grace... but the test must stay fast:

    monkeypatch.setenv("LESSON_GEMINI_GRACE", "0.2")  # explicit env still wins over the preset
    monkeypatch.setattr(gemini, "watch_video", slow_gemini)
    calls = []
    _claude_fakes(monkeypatch, calls)
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert g["lesson"]["builtBy"] == "claude"


def test_invented_links_go_back_to_adapt_then_get_stripped(fake):
    d = json.loads(json.dumps(DRAFT))
    d["steps"][1]["instructions"] = "Clone https://github.com/someone/dead-example-repo (or init a repo) and open it."
    d["steps"][1]["hints"] = ["See https://github.com/someone/dead-example-repo/issues", "Read the autograd docs"]
    d["steps"][0]["instructions"] = "Get the code from https://github.com/x/y as linked in the description."

    async def watch(url, goal, fps=None, **kw):
        fake["watch"] += 1
        return json.loads(json.dumps(d))

    import server.lesson.gemini as gm
    from unittest import mock
    with mock.patch.object(gm, "watch_video", watch):
        g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    fb = "\n".join(f for f in fake["adapt"][1] or []) if len(fake["adapt"]) > 1 else ""
    assert "dead-example-repo" in fb and "never mentions" in fb  # sent back to the adapt pass
    imp = next(s for s in g["steps"] if s["title"] == "Import the libraries")  # draft step 1 (sorted by time)
    pinn = next(s for s in g["steps"] if s["title"] == "Code the PINN")
    assert "dead-example-repo" not in imp["instructions"] and imp["hints"] == ["Read the autograd docs"]
    assert "https://github.com/x/y" in pinn["instructions"]  # in the description: kept
    assert any("removed a link" in w for w in g["build"]["warnings"])


def test_claude_429_is_retried_with_backoff(monkeypatch):
    n = {"calls": 0, "inflight": 0, "max": 0}

    async def flaky(mid, system, prompt, *, effort, schema):
        n["calls"] += 1
        n["inflight"] += 1
        n["max"] = max(n["max"], n["inflight"])
        await asyncio.sleep(0.01)
        n["inflight"] -= 1
        if n["calls"] <= 2:
            raise claude._RateLimited("Number of concurrent requests", 0.01)
        return "msg", "{}"

    monkeypatch.setattr(claude, "_call_once", flaky)
    assert asyncio.run(claude._call("m", "s", "p", effort="low", schema=None)) == ("msg", "{}") and n["calls"] == 3

    n.update(calls=10, inflight=0, max=0)  # now always succeeds: check the concurrency cap
    async def many():
        await asyncio.gather(*(claude._call("m", "s", "p", effort="low", schema=None) for _ in range(12)))
    asyncio.run(many())
    assert n["max"] <= claude.CONCURRENCY
