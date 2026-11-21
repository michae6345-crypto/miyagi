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
    monkeypatch.setenv("LESSON_LAZY_PARTS", "0")  # eager by default in tests; lazy tests opt in
    monkeypatch.setenv("LESSON_GEMINI_USAGE_FILE", str(tmp_path / "gemini_usage.json"))  # never ~/miyagi
    monkeypatch.setenv("LESSON_GEMINI_DAILY_CAP", "1000")

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
    from server.lesson import progressive as _prog

    async def fake_goal_match(goal, meta):
        return {"score": 0.9, "note": "fake"}

    monkeypatch.setattr(_prog, "goal_match", fake_goal_match)
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
    exp = json.loads((FIX / "toscano_pinn_part1.expected.json").read_text(encoding="utf-8"))
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
    (a / "main.py").write_text("print(1)", encoding="utf-8")
    k1 = builder.cache_key(URL, "goal", str(a))
    (a / "main.py").write_text("print(2)  # learner edit", encoding="utf-8")
    assert builder.cache_key(URL, "goal", str(a)) == k1
    (a / "util.py").write_text("", encoding="utf-8")
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


# ---- long videos: progressive build -------------------------------------------------
from server.lesson import progressive  # noqa: E402


def test_plan_windows_groups_chapters_and_splits_long_ones():
    ch = [{"t": 0, "title": "intro"}, {"t": 120, "title": "data"}, {"t": 420, "title": "baseline"},
          {"t": 900, "title": "attention"}, {"t": 2700, "title": "transformer"}, {"t": 3300, "title": "outro"}]
    w = progressive.plan_windows(3500, ch)
    assert w[0][0] == 0 and w[0][1] <= progressive.FIRST_HARD_MAX_S  # small first part (a too-short one takes 1 more chapter)
    assert all(b > a for a, b, _ in w) and w[-1][1] == 3500
    assert all(w[k][1] == w[k + 1][0] for k in range(len(w) - 1))  # contiguous, no gaps
    assert all(b - a <= progressive.WINDOW_MAX_S + 1 for a, b, _ in w[1:])  # the 30-min chapter got split
    nochap = progressive.plan_windows(7000, [])
    assert nochap[0][1] == 480 and nochap[-1][1] == 7000


def test_progressive_build_emits_part_one_then_appends_in_order(fake, monkeypatch, tmp_path):
    monkeypatch.setenv("LESSON_ENGINE", "gemini")
    chapters = [{"t": 0, "title": "setup"}, {"t": 400, "title": "part two"}, {"t": 1200, "title": "part three"}, {"t": 2000, "title": "part four"}]

    async def meta(vid):
        return {"video_id": vid, "title": "Long tutorial", "description": "", "length_s": 2600, "chapters": chapters}

    monkeypatch.setattr(transcript, "fetch_metadata", meta)
    delays = {0: 0.0, 400: 0.3, 1200: 0.05, 2000: 0.1}  # part 3 finishes before part 2

    async def clip(url, goal, fps=None, context="", start=None, end=None, media_low=False):
        await asyncio.sleep(delays[int(start)])
        if int(start) == 2000:
            raise RuntimeError("Gemini call failed: 503 UNAVAILABLE")
        rel = int(start) == 1200  # this one answers with clip-relative times
        a = 10 if rel else start + 10
        return {"title": "t", "libraries": [], "steps": [
            {"start": a, "end": a + 100, "title": f"Step at {int(start)} A", "instructions": "do", "checks": [], "hints": []},
            {"start": a + 100, "end": a + 200, "title": f"Step at {int(start)} B", "instructions": "do", "checks": [], "hints": []}]}

    monkeypatch.setattr(gemini, "watch_video", clip)

    async def adapt(goal, steps, summary, feedback=None):
        return {"steps": [{"index": s["index"], "checks": [{"type": "screen_contains", "label": "x", "app": "Code",
                                                            "pattern": f"step_{s['index']}_marker"}], "targets": []} for s in steps]}

    monkeypatch.setattr(claude, "adapt_checks", adapt)
    updates = []
    g = asyncio.run(builder.build_lesson(URL, "learn it", WORKDIR, refresh=True,
                                         on_update=lambda graph, complete: updates.append((complete, [s["title"] for s in graph["steps"]]))))
    assert updates[0] == (False, ["Step at 0 A", "Step at 0 B"])  # part 1 alone, first
    titles = [s["title"] for s in g["steps"]]
    assert titles == ["Step at 0 A", "Step at 0 B", "Step at 400 A", "Step at 400 B", "Step at 1200 A", "Step at 1200 B"]
    for seen_complete, seen in updates:  # ids are stable: every update extends the previous one
        assert titles[:len(seen)] == seen
    assert updates[-1][0] is True and g["lesson"]["complete"] is True
    assert [s["id"] for s in g["steps"]] == [f"s{i}" for i in range(1, 7)] and g["steps"][4]["checks"][0]["id"] == "s5c1"
    assert g["steps"][4]["video"]["start"] == 1210  # clip-relative 10 s shifted to absolute
    assert g["lesson"]["parts"]["failed"] == 1 and any("part 4" in w for w in g["build"]["warnings"])
    assert g["lesson"]["goalMatch"]["score"] == 0.9 and schema_errors(g) == []
    assert not list(builder.CACHE_DIR.glob("*.json"))  # a part failed: not cached


def test_human_error_says_what_to_do():
    msg = builder.human_error("no engine could build the lesson:\ngemini: 429 RESOURCE_EXHAUSTED quota\nclaude: no transcript: timedtext 429", {"length_s": 6980})
    first = msg.splitlines()[0]
    assert first.startswith("Couldn't read this video (1:56:20 long): Gemini's quota is used up and YouTube is blocking transcripts")
    assert "no engine could build the lesson" in msg and "taking too long" not in msg


def test_local_and_backticked_urls_are_left_alone(fake):
    from server.lesson import links
    steps = [{"id": "s1", "instructions": "Run `uvicorn main:app --reload` and open http://127.0.0.1:8000/docs in your browser.",
              "hints": ["Try http://localhost:8000/items?item=apple"]},
             {"id": "s2", "instructions": "From a second terminal, run `curl -X POST 'https://dead.example/items?item=apple'` to add an item."}]
    assert links.urls_in_steps(steps) == set()
    s = [{"id": "s3", "instructions": "Clone https://github.com/x/dead-repo and run `git clone https://github.com/x/dead-repo`."}]
    links.strip_bad_urls(s, {"https://github.com/x/dead-repo"})
    assert s[0]["instructions"] == "Clone and run `git clone https://github.com/x/dead-repo`."


def test_vague_setup_catches_initialize_but_accepts_code():
    from server.lesson.schema import vague_setup
    st = {"instructions": "Initialize a git repo with a main branch and a feature branch whose commits change index.js."}
    assert vague_setup(st)
    assert not vague_setup(dict(st, code="git init\ngit checkout -b feature/login"))


def test_error_text_follows_the_lessons_stack_without_run_command():
    g = {"lesson": {"libraries": {"react": "18.x", "vite": "5.x"}}, "steps": [{"id": "s3", "precision_checks": [], "targets": [],
         "code": "export default function Header() {}",
         "checks": [{"id": "s3c1", "type": "screen_absent", "label": "x", "app": "Terminal", "pattern": "Traceback|Error:|ERR!"}]}]}
    assert "Traceback" not in builder.normalize_checks(g, set())["steps"][0]["checks"][0]["pattern"]


def test_talk_only_parts_are_skipped_not_failed(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "gemini")

    async def meta(vid):
        return {"video_id": vid, "title": "Long", "description": "", "length_s": 2400,
                "chapters": [{"t": 0, "title": "intro"}, {"t": 300, "title": "code"}, {"t": 1200, "title": "outro"}]}

    monkeypatch.setattr(transcript, "fetch_metadata", meta)

    async def clip(url, goal, fps=None, context="", start=None, end=None, media_low=False):
        if int(start) != 300:
            return {"title": "t", "libraries": [], "steps": []}  # intro / outro: nothing hands-on
        return {"title": "t", "libraries": [], "steps": [{"start": 310, "end": 600, "title": "Write code", "instructions": "do", "checks": [], "hints": []}]}

    monkeypatch.setattr(gemini, "watch_video", clip)

    async def adapt(goal, steps, summary, feedback=None):
        return {"steps": [{"index": s["index"], "checks": [{"type": "screen_contains", "label": "x", "app": "Code", "pattern": "write_code_here"}], "targets": []} for s in steps]}

    monkeypatch.setattr(claude, "adapt_checks", adapt)
    updates = []
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True, on_update=lambda gr, c: updates.append((c, len(gr["steps"])))))
    p = g["lesson"]["parts"]
    assert (p["done"], p["skipped"], p["failed"]) == (1, 3, 0)  # the 20-min outro chapter splits into 2 parts and [s["title"] for s in g["steps"]] == ["Write code"]
    assert updates[0] == (False, 1)  # never shows an empty lesson
    assert list(builder.CACHE_DIR.glob("*.json"))  # skipped parts don't block caching


def test_failed_background_part_is_retried_as_two_halves(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "gemini")

    async def meta(vid):
        return {"video_id": vid, "title": "Long", "description": "", "length_s": 2000,
                "chapters": [{"t": 0, "title": "a"}, {"t": 300, "title": "b"}, {"t": 1100, "title": "c"}]}

    monkeypatch.setattr(transcript, "fetch_metadata", meta)

    async def clip(url, goal, fps=None, context="", start=None, end=None, media_low=False):
        if int(start) == 300 and int(end) == 1100:
            raise RuntimeError("Gemini call failed: no answer")  # the whole 300-1100 part stalls
        return {"title": "t", "libraries": [], "steps": [{"start": start + 5, "end": start + 60, "title": f"Step {int(start)}", "instructions": "do",
                                                         "checks": [], "hints": []}]}

    monkeypatch.setattr(gemini, "watch_video", clip)

    async def adapt(goal, steps, summary, feedback=None):
        return {"steps": [{"index": s["index"], "checks": [{"type": "screen_contains", "label": "x", "app": "Code", "pattern": "some_marker_x"}], "targets": []} for s in steps]}

    monkeypatch.setattr(claude, "adapt_checks", adapt)
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert [s["title"] for s in g["steps"]] == ["Step 0", "Step 300", "Step 700", "Step 1100"]  # halves 300-700, 700-1100
    assert g["lesson"]["parts"]["failed"] == 0


def test_preflight_meta_and_first_hands_on(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "gemini")
    fetched = []

    async def meta(vid):
        fetched.append(vid)
        return {"video_id": vid, "title": "x", "description": "", "length_s": 1, "chapters": []}

    monkeypatch.setattr(transcript, "fetch_metadata", meta)
    watched = []

    async def clip(url, goal, fps=None, context="", start=None, end=None, media_low=False):
        watched.append((int(start), int(end)))
        return {"title": "t", "libraries": [], "steps": [{"start": start + 5, "end": start + 60, "title": f"S{int(start)}", "instructions": "do", "checks": [], "hints": []}]}

    monkeypatch.setattr(gemini, "watch_video", clip)

    async def adapt(goal, steps, summary, feedback=None):
        return {"steps": [{"index": s["index"], "checks": [{"type": "screen_contains", "label": "x", "app": "Code", "pattern": "marker_text"}], "targets": []} for s in steps]}

    monkeypatch.setattr(claude, "adapt_checks", adapt)
    vm = {"title": "Long one", "description": "d", "duration_s": 2400, "firstHandsOn": "7:52",
          "chapters": [{"start": 0, "title": "intro"}, {"start": 472, "title": "data"}, {"start": 1300, "title": "model"}]}
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True, video_meta=vm))
    assert watched and min(a for a, _ in watched) == 472  # the 0:00-7:52 intro was never watched
    p = g["lesson"]["parts"]["list"]
    assert p[0]["status"] == "skipped" and p[0]["end"] == 472 and g["steps"][0]["video"]["start"] >= 472
    assert "Long one" == g["lesson"]["title"]


def test_localhost_at_sentence_end_is_left_alone():
    from server.lesson import links
    assert links._checkable("open http://127.0.0.1:8000.") == set()
    assert links._checkable("see https://example.com/real.") == {"https://example.com/real"}


def test_parts_merge_short_steps_down_to_one():
    d = {"steps": [_st(0, 30, "Import pandas"), _st(30, 70, "Load the CSV"), _st(70, 400, "Group and sort")]}
    out = builder.normalize_draft(d, min_step_s=45, min_steps=1)
    assert [s["title"] for s in out["steps"]] == ["Load the CSV", "Group and sort"]  # 30 s + 40 s folded into one 70 s step
    assert out["steps"][0]["instructions"] == "Import pandas Load the CSV"


def test_mid_length_video_falls_back_to_parts_when_one_pass_fails(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "auto")
    monkeypatch.setenv("LESSON_GEMINI_TIMEOUT", "0.3")
    monkeypatch.setenv("LESSON_GEMINI_MAX_TIMEOUT", "0.3")

    async def meta(vid):
        return {"video_id": vid, "title": "Rust CLI", "description": "", "length_s": 779, "chapters": []}

    monkeypatch.setattr(transcript, "fetch_metadata", meta)

    async def gemini_watch(url, goal, fps=None, context="", start=None, end=None, media_low=False):
        if start is None:
            await asyncio.sleep(5)  # the whole 13-min video: too slow
        return {"title": "t", "libraries": [], "steps": [{"start": start + 5, "end": start + 120, "title": f"Part at {int(start)}",
                                                         "instructions": "do", "checks": [], "hints": []}]}

    monkeypatch.setattr(gemini, "watch_video", gemini_watch)  # Claude path stays offline (fails: no transcript)

    async def adapt(goal, steps, summary, feedback=None):
        return {"steps": [{"index": s["index"], "checks": [{"type": "screen_contains", "label": "x", "app": "Code", "pattern": "fn\\s+main\\("}], "targets": []} for s in steps]}

    monkeypatch.setattr(claude, "adapt_checks", adapt)
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert g["build"]["progressive"] is True and g["lesson"]["parts"]["done"] >= 1 and g["steps"][0]["title"] == "Part at 0"


def test_long_failure_suggests_a_shorter_video():
    msg = builder.human_error("gemini: no answer within 110s | claude: no transcript", {"length_s": 779})
    assert "Try a shorter video from the same search." in msg.splitlines()[0]


def test_a_too_short_part_one_takes_one_more_chapter():
    ch = [{"t": 0, "title": "intro"}, {"t": 472, "title": "reading data"}, {"t": 568, "title": "tokenization"},
          {"t": 867, "title": "data loader"}, {"t": 1331, "title": "bigram"}]
    w = progressive.plan_windows(6980, ch, 472)  # Karpathy: hands-on starts at 7:52
    assert (w[0][1], w[1][0], w[1][1]) == (472, 472, 867)  # part 1 = 7:52-14:27, not a 96 s 7:52-9:28


# ---- speed: prebuild + quick start ---------------------------------------------------
from server.lesson import prebuild  # noqa: E402


def _slow_gemini(fake, delay):
    async def watch(url, goal, fps=None, **kw):
        fake["watch"] += 1
        await asyncio.sleep(delay)
        return json.loads(json.dumps(DRAFT))
    return watch


def test_build_attaches_to_a_running_prebuild(fake, monkeypatch):
    monkeypatch.setenv("ORCH_PREBUILD", "1")
    monkeypatch.setattr(gemini, "watch_video", _slow_gemini(fake, 0.3))
    monkeypatch.setattr(prebuild, "_jobs", {})

    async def scenario():
        assert prebuild.prebuild(URL, "learn", WORKDIR) is True
        await asyncio.sleep(0.1)  # the learner clicks Build while it's still watching
        stages = []
        g = await builder.build_lesson(URL, "learn", WORKDIR, refresh=True, on_progress=lambda s, m: stages.append(s))
        return g, stages

    g, stages = asyncio.run(scenario())
    assert fake["watch"] == 1 and len(g["steps"]) == 3  # one video pass, shared
    assert "watching" in stages  # replayed from the prebuild


def test_prebuild_cap_and_cancel_on_lesson_start(fake, monkeypatch):
    monkeypatch.setenv("ORCH_PREBUILD", "1")
    monkeypatch.setattr(gemini, "watch_video", _slow_gemini(fake, 0.5))
    monkeypatch.setattr(prebuild, "_jobs", {})

    async def scenario():
        a = prebuild.prebuild("https://youtu.be/aaaaaaaaaaa", "x", WORKDIR)
        b = prebuild.prebuild("https://youtu.be/bbbbbbbbbbb", "x", WORKDIR)
        c = prebuild.prebuild("https://youtu.be/ccccccccccc", "x", WORKDIR)  # over the cap of 2
        await asyncio.sleep(0.05)
        n = prebuild.cancel(except_vid="aaaaaaaaaaa")
        await asyncio.sleep(0.05)
        return a, b, c, n, prebuild._jobs["bbbbbbbbbbb"].task.cancelled()

    assert asyncio.run(scenario()) == (True, True, False, 1, True)


def test_quick_start_sends_a_provisional_step_then_the_real_lesson(fake, monkeypatch):
    monkeypatch.setattr(builder, "QUICK_START_S", 0.1)
    monkeypatch.setattr(gemini, "watch_video", _slow_gemini(fake, 0.4))
    vm = {"title": "React basics", "duration_s": 1200, "chapters": [{"start": 0, "title": "Introduction"},
          {"start": 101, "title": "Installation"}, {"start": 168, "title": "New project"}]}
    updates = []
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True, video_meta=vm,
                                         on_update=lambda gr, c: updates.append((c, gr["lesson"].get("provisional"), gr["steps"][0]))))
    first, last = updates[0], updates[-1]
    assert first[0] is False and first[1] is True and first[2]["title"] == "New project"  # skips intro AND install chapters
    assert first[2]["video"] == {"sourceId": "src1", "start": 168.0, "end": 468.0} and first[2]["id"] == "s1"
    assert last[0] is True and not last[1] and last[2]["id"] == "s1" and g["lesson"]["complete"] is True


def test_no_provisional_step_when_real_steps_are_fast(fake, monkeypatch):
    monkeypatch.setattr(builder, "QUICK_START_S", 0.3)
    updates = []
    asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True, on_update=lambda gr, c: updates.append(c)))
    assert updates == []  # short video, no provisional: the return value is the lesson, as before


# ---- Gemini billing: circuit breaker -------------------------------------------------

def test_billing_error_is_fatal_and_trips_the_breaker(monkeypatch):
    import time as _t

    monkeypatch.setattr(gemini, "_down_until", 0.0)
    assert gemini._classify(RuntimeError("402 RESOURCE_EXHAUSTED. Your prepayment credits are depleted."))[0] == "billing"
    calls = {"n": 0}

    class FakeModels:
        async def generate_content(self, **kw):
            calls["n"] += 1
            raise RuntimeError("402 Payment Required: Your prepayment credits are depleted")

    class FakeClient:
        class aio:
            models = FakeModels()

    monkeypatch.setattr(gemini, "client", lambda: FakeClient())
    t = _t.time()
    with pytest.raises(RuntimeError, match="402 Payment Required"):
        asyncio.run(gemini._generate_json("gemini-4-hydrogen", [], {}, system="s"))
    assert calls["n"] == 1 and _t.time() - t < 1  # no fallback models, no retries, no waiting
    assert gemini.is_down() and "credits" in gemini.is_down()
    with pytest.raises(RuntimeError, match="Gemini unavailable"):
        asyncio.run(gemini._generate_json("gemini-3.8-flash", [], {}, system="s"))
    assert calls["n"] == 1  # breaker open: not even tried
    monkeypatch.setattr(gemini, "_down_until", 0.0)


def test_billing_error_message_names_the_real_cause():
    err = ("no engine could build the lesson:\ngemini: Gemini unavailable: billing: 402 Payment Required (Gemini credits are used up)\n"
           "claude: no transcript for x: timedtext: Client error '429 Too Many Requests'")
    first = builder.human_error(err, {"length_s": 1227}).splitlines()[0]
    assert first == ("Couldn't read this video (20:27 long): Gemini credits are used up (top up at ai.studio/projects) and "
                     "YouTube is blocking transcripts on this network. Try a saved lesson, or switch to your phone hotspot.")
    assert "in time" not in first


def test_with_gemini_down_the_build_goes_straight_to_claude(fake, monkeypatch):
    import time as _t

    monkeypatch.setenv("LESSON_ENGINE", "auto")
    monkeypatch.setattr(gemini, "_down_until", _t.time() + 60)
    monkeypatch.setattr(gemini, "_down_reason", "billing: 402 Payment Required (Gemini credits are used up)")

    async def gemini_watch_uses_breaker(url, goal, **kw):  # the real watch_video -> _generate_json -> breaker
        return await gemini._generate_json("gemini-4-hydrogen", [], {}, system="s")

    monkeypatch.setattr(gemini, "watch_video", gemini_watch_uses_breaker)
    calls = []
    _claude_fakes(monkeypatch, calls)
    t = _t.time()
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert _t.time() - t < 2 and g["lesson"]["builtBy"] == "claude"
    monkeypatch.setattr(gemini, "_down_until", 0.0)


def test_prebuild_is_opt_in(monkeypatch):
    monkeypatch.delenv("ORCH_PREBUILD", raising=False)
    monkeypatch.setattr(prebuild, "_jobs", {})
    assert prebuild.prebuild(URL, "x", WORKDIR) is False and prebuild._jobs == {}


def test_cheap_models_first_and_opus_only_on_a_failed_check(monkeypatch):
    for k in ("LESSON_CLAUDE_MODEL", "LESSON_ALLOW_OPUS", "LESSON_CLAUDE_MODEL_ESCALATE"):
        monkeypatch.delenv(k, raising=False)
    assert (claude.model("segment"), claude.model("detail"), claude.model("adapt")) == ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-haiku-5-5")
    used = []

    async def on(mid, system, prompt, schema, *, effort, structured):
        used.append(mid)
        return {"steps": []} if "haiku" in mid else {"steps": [{"start": "0:10", "end": "1:00"}, {"start": "1:00", "end": "2:00"}]}

    monkeypatch.setattr(claude, "_generate_json_on", on)
    ok = lambda o: None if len(o["steps"]) >= 2 else "too few steps"  # noqa: E731
    out = asyncio.run(claude._generate_json("s", "p", {}, role="detail", check=ok))
    assert used == ["claude-haiku-5-5", "claude-sonnet-5-5"] and len(out["steps"]) == 2  # Haiku -> Sonnet, never Opus
    used.clear()
    asyncio.run(claude._generate_json("s", "p", {}, role="detail", check=lambda o: None))
    assert used == ["claude-haiku-5-5"]  # passed its check: no escalation
    monkeypatch.setenv("LESSON_ALLOW_OPUS", "1")
    used.clear()
    async def on2(mid, system, prompt, schema, *, effort, structured):
        used.append(mid)
        return {"steps": []} if "opus" not in mid else {"steps": [1, 2]}
    monkeypatch.setattr(claude, "_generate_json_on", on2)
    asyncio.run(claude._generate_json("s", "p", {}, role="segment", check=ok))
    assert used == ["claude-sonnet-5-5", "claude-opus-5-5"]  # Opus only with the explicit opt-in

def test_token_usage_is_recorded_per_model():
    from server.lesson import cost
    c = cost.start()
    cost.add_tokens("claude-haiku-5-5", 1200, 300)
    cost.add_tokens("claude-haiku-5-5", 800, 200)
    t = c["tokens"]["claude-haiku-5-5"]
    assert {k: t[k] for k in ("input", "output", "calls")} == {"input": 2000, "output": 500, "calls": 2}
    assert t["usd"] > 0 and c["cost_usd"] == t["usd"]  # dollars per model (server/lesson/cost.py PRICES)


# ---- spend guard + lazy parts -----------------------------------------------------------
from server.lesson import budget  # noqa: E402

_REAL_WATCH = gemini.watch_video


def test_daily_budget_persists_and_blocks_gemini(tmp_path, monkeypatch):
    monkeypatch.setenv("LESSON_GEMINI_USAGE_FILE", str(tmp_path / "u.json"))
    monkeypatch.setenv("LESSON_GEMINI_DAILY_CAP", "2")
    monkeypatch.setattr(gemini, "_down_until", 0.0)
    assert budget.remaining() == 2 and budget.try_take("a") and budget.try_take("b") and not budget.try_take("c")
    assert json.loads((tmp_path / "u.json").read_text(encoding="utf-8"))["video_calls"] == 2  # survives a restart
    with pytest.raises(RuntimeError, match="Gemini budget is used up"):  # the real watch_video checks it first
        asyncio.run(gemini.watch_video(URL, "x"))
    (tmp_path / "u.json").write_text(json.dumps({"date": "2000-01-01", "video_calls": 99}), encoding="utf-8")
    assert budget.remaining() == 2  # a new day resets it


def test_budget_exhausted_build_goes_to_claude_and_says_so(fake, monkeypatch, tmp_path):
    monkeypatch.setenv("LESSON_ENGINE", "auto")
    monkeypatch.setenv("LESSON_GEMINI_DAILY_CAP", "0")
    monkeypatch.setattr(gemini, "watch_video", _REAL_WATCH)  # the real one: it checks the budget first
    calls = []
    _claude_fakes(monkeypatch, calls)
    seen = []
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True, on_progress=lambda s, m: seen.append((s, m))))
    assert g["lesson"]["builtBy"] == "claude" and ("engine_switch", "budget") in seen


def test_long_video_builds_part_one_then_extends_on_demand(fake, monkeypatch):
    from server.lesson import progressive
    monkeypatch.setenv("LESSON_LAZY_PARTS", "1")
    chapters = [{"t": 0, "title": "setup"}, {"t": 400, "title": "two"}, {"t": 1200, "title": "three"}, {"t": 2000, "title": "four"}]

    async def meta(vid):
        return {"video_id": vid, "title": "Long", "description": "", "length_s": 2600, "chapters": chapters}

    monkeypatch.setattr(transcript, "fetch_metadata", meta)
    watched = []

    async def clip(url, goal, fps=None, context="", start=None, end=None, media_low=False):
        watched.append(int(start))
        return {"title": "t", "libraries": [], "steps": [{"start": start + 10, "end": start + 200, "title": f"Step {int(start)}", "instructions": "do", "checks": [], "hints": []}]}

    monkeypatch.setattr(gemini, "watch_video", clip)

    async def adapt(goal, steps, summary, feedback=None):
        return {"steps": [{"index": s["index"], "checks": [{"type": "screen_contains", "label": "x", "app": "Code", "pattern": "marker_text"}], "targets": []} for s in steps]}

    monkeypatch.setattr(claude, "adapt_checks", adapt)
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert watched == [0] and [s["title"] for s in g["steps"]] == ["Step 0"] and g["lesson"]["complete"] is False
    assert [p["status"] for p in g["lesson"]["parts"]["list"]] == ["done", "pending", "pending", "pending"]
    assert progressive.needs_more(g, current_step_index=1)  # learner is on the last built step
    ups = []
    g2 = asyncio.run(progressive.extend(g, on_update=lambda gr, c: ups.append(c)))
    assert watched == [0, 400] and [s["id"] for s in g2["steps"]] == ["s1", "s2"] and g2["steps"][1]["checks"][0]["id"] == "s2c1"
    assert ups == [False] and g["steps"] != g2["steps"]  # input untouched, new graph returned
    g3 = asyncio.run(progressive.extend(g2, parts=5))
    assert g3["lesson"]["complete"] is True and len(g3["steps"]) == 4 and not progressive.needs_more(g3, 4)


# ---- quick-start placeholder + setup steps (Michael's calculator lesson) -----------------

CALC_CHAPTERS = [{"t": 0, "title": "Introduction"}, {"t": 40, "title": "Guide to Installing Python & VS Code"},
                 {"t": 80, "title": "Creating the calculator file"}, {"t": 150, "title": "Adding operations"}]


def test_placeholder_skips_intro_and_setup_chapters_and_never_gates():
    g = builder.provisional_graph({"title": "Python calculator", "length_s": 520, "chapters": CALC_CHAPTERS}, "MPlIAlvqAjk",
                                  "https://www.youtube.com/watch?v=MPlIAlvqAjk", "build a calculator", "/tmp/w")
    s1 = g["steps"][0]
    assert s1["video"]["start"] == 80 and s1["title"] == "Creating the calculator file"
    assert s1["checks"] == [] and s1["provisional"] is True
    assert g["lesson"]["builtBy"] == "chapters" and g["lesson"]["provisional"] is True and schema_errors(g) == []
    g2 = builder.provisional_graph({"length_s": 520, "chapters": CALC_CHAPTERS, "first_hands_on": 150}, "MPlIAlvqAjk",
                                   "https://youtu.be/MPlIAlvqAjk", "x", "/tmp/w")
    assert g2["steps"][0]["video"]["start"] == 150  # preflight's first hands-on still wins


def test_pure_install_steps_are_tagged_setup_unless_the_goal_is_installing():
    def g(goal):
        return {"lesson": {"goal": goal}, "steps": [
            {"id": "s1", "title": "Install Python and VS Code", "instructions": "Download Python 3 and VS Code.", "checks": [], "precision_checks": [], "targets": []},
            {"id": "s2", "title": "Create the calculator file", "instructions": "Write add() in calc.py.", "code": "def add(a, b):\n    return a + b",
             "checks": [], "precision_checks": [], "targets": []},
            {"id": "s3", "title": "Set up the project", "instructions": "Create main.py with Python.", "code": "import sys", "checks": [], "precision_checks": [], "targets": []}]}

    out = builder.normalize_checks(g("build a calculator"), set())
    s1, s2, s3 = out["steps"]
    assert s1["setup"] is True and s1["requires"] == ["python", "vscode"]
    assert "setup" not in s2 and "setup" not in s3  # writing code is real work
    assert schema_errors({"lesson": {"id": "x", "title": "t", "goal": "g"}, "sources": [], "steps": [
        {k: v for k, v in s1.items() if k != "precision_checks"} | {"index": 1}]}) == []
    out2 = builder.normalize_checks(g("install Python on my Mac"), set())
    assert "setup" not in out2["steps"][0]


# ---- LESSON_ENGINE=claude-first (Michael: Gemini only when the transcript route can't do it) -----------

def test_claude_first_never_calls_gemini_when_the_transcript_works(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "claude-first")
    calls = []
    _claude_fakes(monkeypatch, calls)

    async def gemini_must_not_run(*a, **k):
        raise AssertionError("Gemini was called although the transcript path worked")

    monkeypatch.setattr(gemini, "watch_video", gemini_must_not_run)
    seen = []
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True, on_progress=lambda s, m: seen.append((s, m))))
    assert g["lesson"]["builtBy"] == "claude" and calls[:2] == ["transcript", "claude-watch"]
    assert ("steps_ready", "claude") in seen and not any(s == "watching" for s, _ in seen)


def test_claude_first_falls_back_to_gemini_without_a_transcript(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "claude-first")

    async def no_transcript(vid):
        raise RuntimeError("no transcript for x: timedtext: 429 Too Many Requests")

    monkeypatch.setattr(transcript, "fetch_video_info", no_transcript)
    gemini.last_model = "gemini-4-hydrogen"
    seen = []
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True, on_progress=lambda s, m: seen.append((s, m))))
    assert fake["watch"] == 1 and g["lesson"]["builtBy"] == "gemini"
    assert ("engine_switch", "no_transcript") in seen


def test_claude_first_long_video_uses_the_transcript_not_gemini_parts(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "claude-first")

    async def meta(vid):
        return {"video_id": vid, "title": "Long", "description": "", "length_s": 5000, "chapters": []}

    monkeypatch.setattr(transcript, "fetch_metadata", meta)
    calls = []
    _claude_fakes(monkeypatch, calls)
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert fake["watch"] == 0 and g["lesson"]["builtBy"] == "claude" and not g["build"].get("progressive")


def test_check_labels_are_complete_plain_phrases():
    fc = {"type": "file_contains", "file": "calculator.py", "pattern": r"def\s+add\(\s*a,\s*b\s*\)"}
    live = ["The add function is still in calculator.py and returns a + b",
            "add function is written in the calculator.py file right now", "te", ""]
    out = [builder.plain_label(x, fc) for x in live]
    for lbl in out:
        words = lbl.split()
        assert 1 <= len(words) <= 6, lbl
        assert words[-1].lower() not in ("in", "the", "to", "of", "and", "is"), lbl  # never cut mid-phrase
    assert out[0] == "add() is in calculator.py"
    assert builder.plain_label("Prints 5 for add(2, 3)", {"type": "screen_contains", "app": "Terminal", "pattern": r"\b5\b"}) == "Prints 5 for add(2, 3)"
    assert builder.plain_label("the add function is still written", fc) == "Add function written"
    assert builder.plain_label("It should not show any traceback or error at all in the terminal",
                               {"type": "screen_absent", "app": "Terminal", "pattern": "Traceback"}) == "No errors in the terminal"
    c = builder.clean_check({"type": "file_contains", "label": "The add function is still in", "file": "calculator.py",
                             "pattern": r"def\s+add\("}, "s2c1")
    assert c["label"] == "add() is in calculator.py"  # the live label was cut off: rewritten, not trimmed


# ---- cost guards ------------------------------------------------------------------------

def test_no_opus_without_explicit_opt_in(monkeypatch):
    for k in ("LESSON_CLAUDE_MODEL", "LESSON_CLAUDE_MODEL_ESCALATE", "LESSON_ALLOW_OPUS", "LESSON_CLAUDE_FAST"):
        monkeypatch.delenv(k, raising=False)
    assert claude.DEFAULT_MODEL == "claude-sonnet-5-5" and claude.model() == "claude-sonnet-5-5"
    assert claude.escalation_model() == "claude-sonnet-5-5" and claude.model("escalate") == "claude-sonnet-5-5"
    assert not claude._use_fast()
    monkeypatch.setenv("LESSON_CLAUDE_MODEL", "claude-opus-5-5")
    assert claude.model("segment") == "claude-sonnet-5-5"  # an Opus setting without the opt-in is downgraded
    monkeypatch.setenv("LESSON_ALLOW_OPUS", "1")
    assert claude.model("segment") == "claude-opus-5-5"
    monkeypatch.delenv("LESSON_CLAUDE_MODEL")
    assert claude.escalation_model() == "claude-opus-5-5"


def test_tests_cannot_reach_a_real_api():
    import anthropic
    import os as _os
    assert "ANTHROPIC_API_KEY" not in _os.environ and _os.environ.get("LESSON_NO_DOTENV") == "1"
    with pytest.raises(AssertionError):
        anthropic.AsyncAnthropic()
    with pytest.raises(AssertionError):
        claude.client()


def test_label_case_keeps_names_from_the_code_lowercase():
    """E25: 'Randint roll typed' on a lesson built after the 01:11 label fix."""
    c = {"type": "screen_contains", "app": "Code", "pattern": r"roll\s*=\s*random\.randint\(1,\s*6\)"}
    assert builder.label_case("randint roll typed", c) == "randint roll typed"  # an attribute the check looks for
    code = "import random\nroll = random.randint(1, 6)\nprint(roll)\n"
    assert builder.label_case("Randint roll typed", c, code) == "randint roll typed"
    assert builder.label_case("random import typed", {"type": "screen_contains", "pattern": r"import\s+random"}, code) == "random import typed"
    assert builder.label_case("print of roll typed", {"type": "screen_contains", "pattern": r"print\("}, code) == "Print of roll typed"  # a builtin reads as a word
    assert builder.label_case("numpy is imported", {"type": "screen_contains", "pattern": "import numpy"}, "import numpy as np") == "NumPy is imported"
    assert builder.label_case("`roll` gets `random.randint(1, 6)`", c, code) == "`roll` gets `random.randint(1, 6)`"
    st = {"code": code, "checks": [{"id": "a", "type": "screen_contains", "label": "Randint roll typed", "pattern": r"random\.randint\("}]}
    assert builder.tidy_labels(st)["checks"][0]["label"] == "randint roll typed"
