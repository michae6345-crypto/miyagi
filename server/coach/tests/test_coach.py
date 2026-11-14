"""Coach tests. No network: fixtures (COACH_REPLAY_DIR) or monkeypatched transports."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from server import coach
from server.coach import common, llm, web
from server.coach.demo_case import CODE, FAILED_CHECKS, LESSON, METRICS, STEP
from server.coach.diagnose import LAST
from server.coach.metrics import series_flags, summarize
from server.coach.playbook import BY_ID, CITATIONS, match

EVENT_ACTIONS = {"explain", "show_me", "apply_fix", "hint"}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "COACH_REPLAY_DIR", "COACH_RECORD_DIR", "BRIGHTDATA_API_KEY",
              "BRIGHTDATA_SERP_ZONE", "BRIGHTDATA_UNLOCKER_ZONE", "DEMO", "TUT_ENV"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "_load_env", lambda: None)
    monkeypatch.setattr(llm, "_local_keys", {})
    LAST.clear()
    common.set_lesson(LESSON)
    yield
    common.set_lesson(None)


@pytest.fixture
def replay(monkeypatch):
    monkeypatch.setenv("COACH_REPLAY_DIR", str(llm.FIXTURES_DIR))


def run(coro):
    return asyncio.run(coro)


def assert_offtrack(card: dict) -> None:
    """Shape of EngineEvents['offtrack'] in shared/contracts/events.ts."""
    p = coach.public(card)
    assert set(p) <= {"stepId", "severity", "title", "body", "diff", "citation", "actions"}
    assert p["severity"] in ("warn", "fail")
    assert 0 < len(p["title"].split()) <= 8
    assert 0 < len(p["body"].split()) <= 34
    assert set(p["actions"]) <= EVENT_ACTIONS
    if "diff" in p:
        assert p["diff"]["expected"] and isinstance(p["diff"]["yours"], str)
    if "citation" in p:
        assert set(p["citation"]) == {"label", "url"}
    json.dumps(p)  # serializable


# ---------- diagnose ----------------------------------------------------------

def test_diagnose_pinn_flat_loss_card(replay):
    card = run(coach.diagnose(STEP, FAILED_CHECKS, METRICS, CODE))
    assert_offtrack(card)
    assert card["severity"] == "warn"  # amber: it runs, it just doesn't learn
    assert "β" in card["title"] or "beta" in card["title"].lower()
    assert card["citation"]["url"] == "https://arxiv.org/abs/2109.01050"
    assert card["diff"]["file"] == "pinn_convection.py" and card["diff"]["line"] in (39, 40)
    assert card["diff"]["yours"].endswith("train(model)") and "for beta in" in card["diff"]["expected"]
    assert "apply_fix" in card["actions"]
    assert card["_meta"]["source"] == "replay" and card["_meta"]["model"] == "claude-opus-5-5"
    assert card["_meta"]["route"] == "opus" and card["_meta"]["triage"]["by"] == "rules"


def test_diagnose_without_api_raises_outside_demo():
    """No-fake rule: no key → CoachUnavailable, never a canned card."""
    with pytest.raises(coach.CoachUnavailable, match="no ANTHROPIC_API_KEY"):
        run(coach.diagnose(STEP, FAILED_CHECKS, METRICS, CODE))


def test_diagnose_without_api_in_demo_mode_uses_playbook_card(monkeypatch):
    monkeypatch.setenv("DEMO", "1")
    card = run(coach.diagnose(STEP, FAILED_CHECKS, METRICS, CODE))
    assert_offtrack(card)
    assert card["_meta"]["route"] == "playbook"
    assert card["_meta"]["playbook_id"] == "pinn_convection_large_beta"
    assert "no ANTHROPIC_API_KEY" in card["_meta"]["fallback_reason"]
    assert card["diff"]["yours"] == "train(model)" and card["diff"]["line"] == 40


def _fake_call(data: dict):
    async def call(**kw):
        return llm.CallResult(data=data, model=kw["model"], source="fake")
    return call


def test_hallucinated_citation_is_dropped_and_text_clamped(monkeypatch):
    monkeypatch.setattr(llm, "structured_call", _fake_call({
        "playbook_id": "none", "severity": "warn",
        "title": "A very long title that keeps going well past eight words",
        "body": " ".join(["word"] * 60),
        "citation_id": "smith2099_made_up", "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0,
        "actions": ["apply_fix", "explain"],
    }))
    card = run(coach.diagnose(STEP, FAILED_CHECKS, METRICS, CODE))
    assert_offtrack(card)
    assert "citation" not in card
    assert "apply_fix" not in card["actions"]  # no diff → no apply button


def test_lesson_source_citation_allowed(monkeypatch):
    monkeypatch.setattr(llm, "structured_call", _fake_call({
        "playbook_id": "pinn_convection_large_beta", "severity": "warn", "title": "t", "body": "b",
        "citation_id": "source:paper", "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0, "actions": [],
    }))
    card = run(coach.diagnose(STEP, FAILED_CHECKS, METRICS, CODE))
    assert card["citation"]["url"] == "https://arxiv.org/abs/2109.01050"


def test_opus_request_shape(monkeypatch):
    """Exact SDK call: Opus 5.5, adaptive thinking, effort, structured output, cached system, fallbacks."""
    seen = {}

    class FakeBeta:
        async def create(self, **kw):
            seen.update(kw)
            text = json.loads(next(llm.FIXTURES_DIR.glob("diagnose-*.json")).read_text())["response"]["text"]
            return SimpleNamespace(
                stop_reason="end_turn", model=kw["model"],
                content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=text)],
                usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=3000, cache_creation_input_tokens=0),
            )

    fake = SimpleNamespace(beta=SimpleNamespace(messages=FakeBeta()))
    fake.with_options = lambda **_: fake
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    card = run(coach.diagnose(STEP, FAILED_CHECKS, METRICS, CODE))
    assert seen["model"] == "claude-opus-5-5"
    assert seen["thinking"] == {"type": "adaptive"}
    assert seen["output_config"]["effort"] == "low"
    assert seen["output_config"]["format"]["type"] == "json_schema"
    assert seen["fallbacks"] == "default" and seen["betas"] == [llm.FALLBACK_BETA]
    assert all(b["cache_control"] == {"type": "ephemeral"} for b in seen["system"])
    assert "krishnapriyan2021" in seen["system"][0]["text"]  # playbook in the cached prefix
    assert '"pinn-convection"' in seen["system"][1]["text"]  # lesson context in the cached prefix
    assert card["_meta"]["usage"]["cache_read_input_tokens"] == 3000


def test_refusal_raises_outside_demo(monkeypatch):
    class FakeBeta:
        async def create(self, **kw):
            return SimpleNamespace(stop_reason="refusal", model=kw["model"], content=[], usage=None)

    fake = SimpleNamespace(beta=SimpleNamespace(messages=FakeBeta()))
    fake.with_options = lambda **_: fake
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    with pytest.raises(coach.CoachUnavailable, match="refusal"):
        run(coach.diagnose(STEP, FAILED_CHECKS, METRICS, CODE))
    monkeypatch.setenv("DEMO", "1")
    assert run(coach.diagnose(STEP, FAILED_CHECKS, METRICS, CODE))["_meta"]["route"] == "playbook"


def test_lesson_context_is_byte_stable():
    a = common.lesson_context_text(LESSON)
    b = common.lesson_context_text(json.loads(json.dumps(LESSON)))
    assert a == b


# ---------- triage ------------------------------------------------------------

def _no_llm(monkeypatch):
    async def boom(**kw):
        raise AssertionError("LLM must not be called")
    monkeypatch.setattr(llm, "structured_call", boom)


def test_triage_not_attempted_is_template_without_llm(monkeypatch):
    _no_llm(monkeypatch)
    step = {"id": "s1", "title": "Write the residual", "instructions": "Define residual().", "hints": ["Start from u_t + β·u_x."],
            "checks": [{"id": "c1", "type": "file_contains", "label": "residual defined", "file": "pinn.py", "pattern": "def residual"}]}
    card = run(coach.diagnose(step, [{"checkId": "c1", "label": "residual defined", "status": "fail"}], None, ""))
    assert_offtrack(card)
    assert card["_meta"]["route"] == "template" and card["body"] == "Start from u_t + β·u_x."


def test_triage_cuda_error_is_instant_playbook(monkeypatch):
    _no_llm(monkeypatch)
    step = {"id": "s2", "title": "Run training", "instructions": "Run it.",
            "checks": [{"id": "c2", "type": "command_exit_ok", "label": "script runs", "command": "python pinn.py"}]}
    err = "Traceback...\nAssertionError: Torch not compiled with CUDA enabled"
    card = run(coach.diagnose(step, [{"checkId": "c2", "label": "script runs", "status": "fail"}], None, 'model.to("cuda")', error_text=err))
    assert_offtrack(card)
    assert card["_meta"]["playbook_id"] == "cuda_on_mac" and card["severity"] == "fail"
    assert "pytorch.org" in card["citation"]["url"]


def test_triage_ambiguous_uses_haiku(replay):
    """Recorded live Haiku call: an MPS error no regex rule matches."""
    step = {"id": "s3", "title": "Run training", "instructions": "Run the training script once.",
            "checks": [{"id": "c3", "type": "command_exit_ok", "label": "script runs", "command": "python pinn.py"}]}
    err = "Traceback (most recent call last):\n  File \"pinn.py\", line 41, in <module>\n    loss = residual(model, x, t)\nRuntimeError: Placeholder storage has not been allocated on MPS device!"
    code = 'device = "mps"\nmodel = PINN().to(device)\nx = torch.rand(1000, 1)\nt = torch.rand(1000, 1)'
    t = run(coach.triage(step, [{"checkId": "c3", "label": "script runs", "status": "fail"}], set(), code, err))
    assert t.by == "haiku" and t.route == "playbook" and t.playbook_id == "cuda_on_mac"


def test_triage_haiku_failure_defaults_to_opus():
    step = {"id": "s3", "checks": [{"id": "c3", "type": "output_contains", "label": "x"}]}
    t = run(coach.triage(step, [{"checkId": "c3"}], set(), "", "weird"))
    assert t.route == "opus" and t.by == "fallback"


# ---------- metrics + playbook --------------------------------------------------

def test_metrics_flags():
    assert "plateau" in summarize(METRICS)[1]
    assert "diverging" in series_flags([(i, v) for i, v in enumerate([1.0, 0.9, 1.5, 3.0, 9.0, 40.0])])
    assert {"nan", "diverging"} <= series_flags([(0, 1.0), (1, float("nan"))])
    assert "imbalance" in summarize({"loss/residual": [(i, 1.0 / 10**i) for i in range(5)], "loss/ic": [(i, 1.0) for i in range(5)]})[1]


@pytest.mark.parametrize(
    "code,flags,err,expected",
    [
        (CODE, {"plateau"}, "", "pinn_convection_large_beta"),
        ("loss.backward()\nopt.step()", {"diverging"}, "", "missing_zero_grad"),
        ("opt = Adam(p, lr=0.5)\nopt.zero_grad()\nloss.backward()\nopt.step()", {"diverging", "nan"}, "loss nan", "lr_too_high"),
        ("", set(), "RuntimeError: One of the differentiated Tensors does not require grad", "pinn_inputs_no_grad"),
    ],
)
def test_playbook_match(code, flags, err, expected):
    assert match(code, flags, err)[0].id == expected


def test_playbook_citations_resolve():
    for m in BY_ID.values():
        assert m.citation_id in CITATIONS and m.card_title and m.card_body
        assert len(m.card_title.split()) <= 8 and len(m.card_body.split()) <= 34


# ---------- explain -------------------------------------------------------------

def test_explain_with_video_jump(replay):
    run(coach.diagnose(STEP, FAILED_CHECKS, METRICS, CODE))
    card = run(coach.explain(STEP, None, {"metrics_summary": METRICS}))
    assert card["kind"] == "explain" and card["stepId"] == "s5"
    assert card["videoJump"] == {"t": 548.0, "label": "Explained at 9:08"}


def test_explain_offline_uses_keyword_jump(monkeypatch):
    with pytest.raises(coach.CoachUnavailable):
        run(coach.explain(STEP, "why does large beta make training hard?", {}))
    monkeypatch.setenv("DEMO", "1")
    card = run(coach.explain(STEP, "why does large beta make training hard?", {}))
    assert card["kind"] == "answer" and card["videoJump"]["t"] == 548.0


# ---------- hints + apply_fix ---------------------------------------------------

def test_hint_ladder(replay):
    run(coach.diagnose(STEP, FAILED_CHECKS, METRICS, CODE))
    levels = [coach.hint(STEP, i) for i in range(5)]
    assert [h["levelName"] for h in levels] == ["question", "video", "paper", "diff", "diff"]
    assert levels[0]["body"].endswith("?")
    assert levels[1]["videoJump"]["t"] == 548.0
    assert levels[2]["citation"]["url"].endswith("2109.01050")
    assert levels[3]["diff"]["yours"].endswith("train(model)") and levels[3]["actions"] == ["apply_fix"]


def test_apply_fix_never_writes(tmp_path):
    f = tmp_path / "pinn_convection.py"
    f.write_text(CODE)
    card = coach.playbook_card(STEP, BY_ID["pinn_convection_large_beta"], CODE)
    patch = coach.apply_fix(card["diff"], f.read_text())
    assert f.read_text() == CODE  # untouched
    assert patch["requires_confirmation"] is True
    assert "-train(model)" in patch["unified_diff"] and "+for beta in" in patch["unified_diff"]
    assert patch["new_text"].count("train(model, epochs=1000)") == 1 and "\ntrain(model)\n" not in patch["new_text"]


# ---------- fix_outdated ----------------------------------------------------------

def test_fix_outdated_known_offline():
    r = run(coach.fix_outdated("AttributeError: module 'numpy' has no attribute 'float'", {"numpy": "1.21"}))
    assert r["citation"]["url"].startswith("https://numpy.org/") and r["diff"]["yours"] == "np.float"


def test_fix_outdated_without_brightdata_raises():
    with pytest.raises(coach.OutdatedFixUnavailable, match="not configured") as e:
        run(coach.fix_outdated("TypeError: foo() got an unexpected keyword argument 'bar'", ["torch"]))
    assert e.value.reason


def test_fix_outdated_no_pages_raises(fake_web):
    with pytest.raises(coach.OutdatedFixUnavailable, match="no docs"):
        run(coach.fix_outdated("Error: obscure failure in zzz-tool", ["zzz-tool"]))


def test_byok_keys_win_over_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert llm.get_key("anthropic") == "from-env"
    coach.set_keys({"anthropic": "from-app", "brightdata": "postgres://..."})  # placeholder ignored
    assert llm.get_key("anthropic") == "from-app" and llm.get_key("brightdata") is None
    assert llm.get_client().api_key == "from-app"
    coach.set_keys({"anthropic": ""})
    assert llm.get_key("anthropic") == "from-env" and llm.get_client().api_key == "from-env"


E4_SRC = '''import torch

def train(model, steps=4000):
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    beta = 30
    for epoch in range(steps):
        x, t = sample_points()
        loss = pde_residual(model, x, t, beta).pow(2).mean()
        opt.zero_grad(); loss.backward(); opt.step()
    return model
'''


def test_apply_fix_renests_block_and_dedents_expected():
    """E4 integration repro: expected carries its own indent; the loop body must move under the new header."""
    d = {"file": "pinn.py", "line": 5, "yours": "    beta = 30\n    for epoch in range(steps):",
         "expected": "    for beta in [1, 5, 10, 20, 30]:\n        for epoch in range(steps // 5):"}
    r = coach.apply_fix(d, E4_SRC)
    assert r["error"] is None
    assert (
        "    for beta in [1, 5, 10, 20, 30]:\n"
        "        for epoch in range(steps // 5):\n"
        "            x, t = sample_points()\n"
    ) in r["new_text"]
    assert "\n    return model\n" in r["new_text"]  # code after the block keeps its level
    compile(r["new_text"], "pinn.py", "exec")


def test_apply_fix_refuses_uncompilable_or_unanchored():
    r = coach.apply_fix({"file": "pinn.py", "yours": "beta = 30", "expected": "for beta in [1, 5]:"}, E4_SRC)
    assert r["new_text"] is None and "compile" in r["error"] and r["unified_diff"]
    r = coach.apply_fix({"file": "pinn.py", "yours": "beta = 99", "expected": "beta = 1"}, E4_SRC)
    assert r["new_text"] is None and "not found" in r["error"]
    r = coach.apply_fix({"file": "pinn.py", "yours": "", "expected": "beta = 1"}, E4_SRC)
    assert r["new_text"] is None


# ---------- GENERALITY RULE: non-ML cases, web-grounded ----------------------------------

from server.coach.tests import generic_cases as g


@pytest.fixture
def fake_web(monkeypatch):
    """Stand-in for Bright Data (SERP + Unlocker) with short excerpts of the real pages."""
    g.fake_fetch_log().clear()
    monkeypatch.setattr(web, "fetch", g.fake_fetch)
    monkeypatch.setattr(web, "configured", lambda: True)
    return g.fake_fetch_log()


@pytest.mark.parametrize(
    "error,code,libs,command,expected",
    [
        ("AttributeError: module 'numpy' has no attribute 'float'", "", None, "", ("numpy", "numpy.float")),
        (g.PANDAS_ERROR, g.PANDAS_CODE, g.PANDAS_LIBS, "", ("pandas", "Series.iteritems")),
        (g.REACT_ERROR, g.REACT_CODE, {"react": "18"}, "npm run lint", ("react", "useEffect")),
        ("Warning: ReactDOM.render is no longer supported in React 18.", "", None, "", ("react-dom", "ReactDOM.render")),
        ("Error: Cannot find module 'express'", "", None, "node server.js", ("express", "express")),
        ("npm ERR! code ERESOLVE", "", None, "npm install", ("npm", "")),
    ],
)
def test_detect_library_from_any_error(error, code, libs, command, expected):
    assert web.detect(error, code, libs, command) == expected


def test_react_hooks_error_is_grounded_in_official_docs(fake_web, replay):
    """Recorded live run: Haiku triage → Opus, grounded in react.dev fetched via the web layer."""
    common.set_lesson(g.REACT_LESSON)
    card = run(coach.diagnose(g.REACT_STEP, g.REACT_FAILED, None, g.REACT_CODE, error_text=g.REACT_ERROR))
    assert_offtrack(card)
    assert card["severity"] == "fail" and card["_meta"]["route"] == "opus" and card["_meta"]["triage"]["by"] == "haiku"
    assert card["citation"]["url"] == "https://react.dev/reference/rules/rules-of-hooks"
    assert "useEffect" in card["title"] + card["body"]
    serp = [u for k, u in fake_web if k == "serp"]
    assert any("site%3Areact.dev" in u for u in serp) and any("site%3Astackoverflow.com" in u for u in serp)
    assert ("unlock", "https://react.dev/reference/rules/rules-of-hooks") in fake_web
    assert not any("example-blog.com" in u for _, u in fake_web)  # non-official SERP hit filtered out
    patch = coach.apply_fix(card["diff"], g.REACT_CODE)
    assert patch["error"] is None and "if (enabled) {" not in patch["new_text"]
    assert "useEffect(() => {\n    if (!enabled) return;" in patch["new_text"]


def test_deprecated_pandas_api_fix_from_web(fake_web, replay):
    """Recorded live run: pandas 2.0 removed Series.iteritems; fix cites the official release notes."""
    fix = run(coach.fix_outdated(g.PANDAS_ERROR, g.PANDAS_LIBS, code=g.PANDAS_CODE))
    assert fix["_meta"]["via"] == "web" and fix["_meta"]["library"] == "pandas"
    assert fix["citation"]["url"] == "https://pandas.pydata.org/docs/whatsnew/v2.0.0.html"
    assert fix["diff"]["yours"].strip().endswith("counts.iteritems():") and ".items()" in fix["diff"]["expected"]
    assert any("site%3Apandas.pydata.org" in u for k, u in fake_web if k == "serp")
    patch = coach.apply_fix({**fix["diff"], "file": "clean.py"}, g.PANDAS_CODE)
    assert patch["error"] is None and "counts.items()" in patch["new_text"]


def test_web_citations_are_whitelisted(fake_web, monkeypatch):
    """The model can cite web:N only for sources actually fetched for this call."""
    seen = {}

    async def call(**kw):
        seen["user"] = kw["user_text"]
        if kw["purpose"] == "triage":
            return llm.CallResult(data={"route": "opus", "playbook_id": "none", "reason": ""}, model="h")
        return llm.CallResult(data={
            "playbook_id": "none", "severity": "fail", "title": "Hook inside a condition", "body": "Move it out.",
            "citation_id": "web:7", "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0, "actions": [],
        }, model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    common.set_lesson(g.REACT_LESSON)
    card = run(coach.diagnose(g.REACT_STEP, g.REACT_FAILED, None, g.REACT_CODE, error_text=g.REACT_ERROR))
    assert "citation" not in card  # web:7 does not exist
    assert "[web:0] (docs) Rules of Hooks" in seen["user"]


def test_web_unavailable_degrades_quietly(monkeypatch):
    monkeypatch.setattr(web, "_bd_config", lambda: None)
    assert run(web.gather("react", "useEffect", "hook error")) == []


def test_metric_direction_from_checks():
    acc_rising = [(i, v) for i, v in enumerate([0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95])]
    acc_stuck = [(i, v) for i, v in enumerate([0.1, 0.5, 0.61, 0.62, 0.62, 0.62, 0.62])]
    assert summarize({"accuracy": acc_rising}, goals={"accuracy": "up"})[1] == set()
    assert "plateau" in summarize({"accuracy": acc_stuck}, goals={"accuracy": "up"})[1]
    assert "diverging" not in summarize({"tests_passed": acc_rising})[1]  # "pass" → higher is better
