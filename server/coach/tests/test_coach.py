"""Coach tests. No network: fixtures (COACH_REPLAY_DIR) or monkeypatched transports."""

from __future__ import annotations

import asyncio
import json
import re
from types import SimpleNamespace

import pytest

from server import coach
from server.coach import common, llm, web
from server.coach.case_convection import CODE, FAILED_CHECKS, LESSON, METRICS, STEP
from server.coach.diagnose import LAST
from server.coach.metrics import series_flags, summarize
from server.coach.playbook import BY_ID, CITATIONS, match

EVENT_ACTIONS = {"explain", "show_me", "apply_fix", "hint"}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "COACH_REPLAY_DIR", "COACH_RECORD_DIR", "BRIGHTDATA_API_KEY",
              "BRIGHTDATA_SERP_ZONE", "BRIGHTDATA_UNLOCKER_ZONE", "DEMO", "TUT_ENV", "COACH_OFFLINE_FALLBACK"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "_load_env", lambda: None)
    monkeypatch.setattr(llm, "_local_keys", {})
    LAST.clear()
    from server.coach.diagnose import reset_memo

    reset_memo()
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
    assert set(p) <= {"stepId", "severity", "title", "body", "diff", "citation", "actions", "guidingQuestion", "offline", "notStarted"}
    assert p["severity"] in ("warn", "fail")
    assert 0 < len(p["title"].split()) <= 8
    assert 0 < len(p["body"].split()) <= 42  # ~30 by contract; the action sentence is never cut
    assert set(p["actions"]) <= EVENT_ACTIONS
    if "diff" in p:
        assert (p["diff"]["expected"] or p["diff"].get("command")) and isinstance(p["diff"]["yours"], str)
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
    assert card["diff"]["yours"].endswith("train(model)") and "for " in card["diff"]["expected"] and "30" in card["diff"]["expected"]
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
    assert "diff" not in card  # the playbook carries no demo-specific code; only Opus writes diffs


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
    assert card["_meta"]["route"] == "template" and card["notStarted"] is True and card["body"] == "Define residual()."


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
    assert t.by == "haiku" and t.route in ("opus", "playbook")  # recorded Haiku call; never "template" for a crash


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


def test_apply_fix_never_writes(tmp_path, replay):
    f = tmp_path / "pinn_convection.py"
    f.write_text(CODE)
    card = run(coach.diagnose(STEP, FAILED_CHECKS, METRICS, CODE))
    patch = coach.apply_fix(card["diff"], f.read_text())
    assert f.read_text() == CODE  # untouched
    assert patch["requires_confirmation"] is True and patch["error"] is None
    assert "-train(model)" in patch["unified_diff"] and "+for " in patch["unified_diff"]
    compile(patch["new_text"], "pinn_convection.py", "exec")
    assert "\ntrain(model)\n" not in patch["new_text"]


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


# ---------- hero lesson: 1D diffusion PINN, three real learner mistakes ----------------------

from server.coach import case_diffusion as d

DIFFUSION_CASES = {
    "missing_bc": (d.MISSING_BC_FAILED, d.MISSING_BC_METRICS, d.MISSING_BC_CODE, "", "warn", "doi.org/10.1016/j.jcp.2018.10.045", "lossBC"),
    "high_lr": (d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE, "", "warn", "arxiv.org/abs/1506.01186", "lr=1e-3"),
    "no_grad": (d.NO_GRAD_FAILED, None, d.NO_GRAD_CODE, d.NO_GRAD_ERROR, "fail", "pytorch.org/docs/stable/generated/torch.autograd.grad", "requires_grad_"),
}


@pytest.mark.parametrize("name", sorted(DIFFUSION_CASES))
def test_diffusion_mistakes_get_specific_cited_fixes(name, replay):
    """Recorded live Opus cards; each diff must turn the learner's code back into the correct code."""
    failed, metrics, code, err, severity, cite, fix_token = DIFFUSION_CASES[name]
    common.set_lesson(d.LESSON)
    card = run(coach.diagnose(d.STEP, failed, metrics, code, error_text=err))
    assert_offtrack(card)
    assert card["_meta"]["source"] == "replay" and card["severity"] == severity
    assert cite in card["citation"]["url"]
    assert fix_token in card["diff"]["expected"]
    patch = coach.apply_fix(card["diff"], code)
    assert patch["error"] is None and patch["new_text"] == d.code()


def test_low_loss_but_wrong_solution_is_flagged():
    _, flags = summarize(d.MISSING_BC_METRICS, goals={"rel_l2": "down", "loss": "down"})
    assert "low_loss_wrong_solution" in flags and "plateau" in flags
    assert match(d.MISSING_BC_CODE, flags)[0].id == "pinn_missing_ic_bc"
    # the same signals on correct code don't get the "term missing" bonus
    assert match(d.code(), flags)[1] < match(d.MISSING_BC_CODE, flags)[1]


def test_diffusion_explain_and_ladder(replay):
    common.set_lesson(d.LESSON)
    run(coach.diagnose(d.STEP, d.MISSING_BC_FAILED, d.MISSING_BC_METRICS, d.MISSING_BC_CODE))
    card = run(coach.explain(d.STEP, None, {"metrics_summary": d.MISSING_BC_METRICS}))
    assert card["kind"] == "explain" and "videoJump" in card
    ladder = [coach.hint(d.STEP, i) for i in range(4)]
    assert ladder[0]["body"].endswith("?") and "doi.org" in ladder[2]["citation"]["url"]
    assert "lossBC" in ladder[3]["diff"]["expected"]


def test_no_grad_error_without_api_in_demo_mode_is_curated(monkeypatch):
    monkeypatch.setenv("DEMO", "1")
    common.set_lesson(d.LESSON)
    card = run(coach.diagnose(d.STEP, d.NO_GRAD_FAILED, None, d.NO_GRAD_CODE, error_text=d.NO_GRAD_ERROR))
    assert card["_meta"]["playbook_id"] == "pinn_inputs_no_grad" and "pytorch.org" in card["citation"]["url"]


def test_hero_hint_ladder_follows_the_diagnosis(replay):
    """E4 run: level 0 must ask about THE diagnosed issue, not a generic step hint."""
    common.set_lesson(d.LESSON)
    card = run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE))
    assert "noisy" in summarize(d.HIGH_LR_METRICS, goals={"loss": "down"})[1]
    q = card["guidingQuestion"]
    assert q.endswith("?") and ("Adam" in q or "step" in q) and "1e-3" not in q  # leads, doesn't tell
    for last in (None, coach.public(card)):  # from LAST, or the public card the orchestrator kept
        ladder = [coach.hint(d.STEP, i, last) for i in range(4)]
        assert ladder[0]["body"] == q
        assert ladder[1]["videoJump"]["t"] == d.STEP["video"]["start"]  # no IC/BC clip for an LR issue
        assert "1506.01186" in ladder[2]["citation"]["url"]
        assert "lr=1e-3" in ladder[3]["diff"]["expected"]


def test_ladder_video_matches_the_issue(replay):
    common.set_lesson(d.LESSON)
    run(coach.diagnose(d.STEP, d.MISSING_BC_FAILED, d.MISSING_BC_METRICS, d.MISSING_BC_CODE))
    jump = coach.hint(d.STEP, 1)["videoJump"]
    assert jump["t"] == 902.0  # "coding the PINN: boundary loss and PDE residual loss"


def test_playbook_card_carries_its_guiding_question():
    card = coach.playbook_card(d.STEP, BY_ID["lr_too_high"], d.HIGH_LR_CODE)
    assert card["guidingQuestion"].startswith("What happens to Adam")
    assert coach.hint(d.STEP, 0, coach.public(card))["body"] == card["guidingQuestion"]


# ---------- screen understanding: set-of-mark payload, streaming targets, cancel, warm -------------

from server.coach import actions
from server.coach.screen import ScreenContext, parse_targets_prefix
from server.coach.tests.screen_case import box_id_containing, make_screen


def test_screen_payload_shapes():
    s = make_screen()
    assert s.overview().size[0] == 1280 and s.crop().size == (400, 400)
    content = s.claude_content()
    assert [b["type"] for b in content] == ["text", "image", "image"]  # instructions before images
    assert content[1]["source"]["media_type"] == "image/jpeg"
    assert "Cursor at (990, 585) over [" in s.text() and "(Terminal)" in s.cursor_line()
    assert [b.id for b in s.boxes] == list(range(1, len(s.boxes) + 1))
    lr = box_id_containing(s, "lr=0.3")
    got = s.resolve_targets([{"box_id": lr, "label": "learning rate"}, {"box_id": 999, "label": "x"}, {"box_id": lr, "label": "dup"}])
    assert len(got) == 1 and got[0]["rect"]["y"] > 0 and got[0]["text"].startswith("optimizer")


def test_from_e6_observation():
    obs = {"scale": 2.0, "screen": {"x": 0, "y": 0, "w": 100, "h": 50}, "app": "Code",
           "blocks": [{"text": "def loss(self):", "rect": {"x": 10, "y": 10, "w": 60, "h": 12}, "app": "Code"}, {"text": " ", "rect": [0, 0, 1, 1]}]}
    from PIL import Image

    s = ScreenContext.from_observation(obs, Image.new("RGB", (200, 100)), (20, 15), file="pinn.py", line=33)
    assert len(s.boxes) == 1 and s.boxes[0].id == 1
    assert s.cursor_line() == 'Cursor at (20, 15) over [1] "def loss(self):" (Code), line 33 of pinn.py'


def test_targets_parse_from_partial_json():
    assert parse_targets_prefix('{"targets": [{"box_id": 4, "la') is None
    assert parse_targets_prefix('{"targets": [{"box_id": 4, "label": "lr"}], "playbook_') == [{"box_id": 4, "label": "lr"}]
    assert parse_targets_prefix('{"title": "x"') is None


class _FakeStream:
    def __init__(self, chunks, final_text, delay=0.0, log=None):
        self.chunks, self.final_text, self.delay, self.log = chunks, final_text, delay, log if log is not None else []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.log.append("closed")

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        snap = ""
        for c in self.chunks:
            await asyncio.sleep(self.delay)
            snap += c
            self.log.append(f"chunk:{len(snap)}")
            yield SimpleNamespace(type="text", text=c, snapshot=snap)

    async def get_final_message(self):
        return SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5", content=[SimpleNamespace(type="text", text=self.final_text)],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0))


def _fake_streaming_client(monkeypatch, stream):
    seen = {}

    class Msgs:
        def stream(self, **kw):
            seen.update(kw)
            return stream

    fake = SimpleNamespace(beta=SimpleNamespace(messages=Msgs()))
    fake.with_options = lambda **_: fake
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    return seen


def test_screen_diagnose_streams_targets_first(monkeypatch):
    s = make_screen()
    lr = box_id_containing(s, "lr=0.3")
    body = {"targets": [{"box_id": lr, "label": "learning rate"}], "playbook_id": "lr_too_high", "severity": "warn",
            "title": "Adam learning rate too high", "body": "Each step overshoots. Lower the learning rate to 1e-3.",
            "citation_id": "smith2017_clr", "diff_expected": "optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)",
            "diff_yours": "optimizer = torch.optim.Adam(model.parameters(), lr=0.3)", "diff_file": "pinn_diffusion.py",
            "diff_line": 38, "actions": ["apply_fix"], "guiding_question": "What happens to Adam's steps?"}
    text = json.dumps(body)
    cut = text.index('"playbook_id"')
    log = []
    stream = _FakeStream([text[:20], text[20:cut], text[cut:]], text, log=log)
    seen = _fake_streaming_client(monkeypatch, stream)
    fired = []
    common.set_lesson(d.LESSON)
    card = run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE, screen=s,
                              on_targets=lambda t: fired.append((len(log), t))))
    assert fired and fired[0][1][0]["boxId"] == lr and fired[0][0] == 2  # after chunk 2 of 3, before the prose
    assert card["targets"] == fired[0][1]
    props = list(seen["output_config"]["format"]["schema"]["properties"])
    assert props[0] == "targets"  # target first in the output
    user = seen["messages"][0]["content"]
    assert [b["type"] for b in user] == ["text", "text", "image", "image"]


def test_cancel_closes_the_stream(monkeypatch):
    log = []
    stream = _FakeStream(['{"targets": [', "]"] + ["x"] * 50, "{}", delay=0.05, log=log)
    _fake_streaming_client(monkeypatch, stream)
    common.set_lesson(d.LESSON)

    async def go():
        task = coach.inflight.start("diagnose", coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE, screen=make_screen()))
        await asyncio.sleep(0.2)
        assert coach.inflight.running() == ["diagnose"]
        assert coach.cancel() == 1
        with pytest.raises(asyncio.CancelledError):
            await task

    run(go())
    assert log[-1] == "closed" and len(log) < 20  # stopped early, HTTP stream closed


def test_warm_sends_the_same_prefix(monkeypatch):
    calls = []

    class Msgs:
        async def create(self, **kw):
            calls.append(kw)
            return SimpleNamespace(usage=SimpleNamespace(cache_creation_input_tokens=4000, cache_read_input_tokens=0))

    async def retrieve(model):
        return None

    fake = SimpleNamespace(beta=SimpleNamespace(messages=Msgs()), messages=Msgs(), models=SimpleNamespace(retrieve=retrieve))
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    common.set_lesson(d.LESSON)
    out = run(coach.warm())
    assert out["cache"] == [4000, 4000] and len(calls) == 2
    assert all(c["max_tokens"] == 1 and c["betas"] == [llm.FALLBACK_BETA] and c["thinking"] == {"type": "adaptive"} for c in calls)
    assert next(iter(calls[1]["output_config"]["format"]["schema"]["properties"])) == "targets"


# ---------- "Do it for me" --------------------------------------------------------------------------

def test_do_it_for_me_from_the_diagnosis(replay):
    common.set_lesson(d.LESSON)
    run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE))
    p = run(coach.do_it_for_me(d.STEP, "pinn_diffusion.py", d.HIGH_LR_CODE))
    assert p["requires_confirmation"] and p["_meta"]["via"] == "diagnosis"
    assert "1e-3" in p["summary"] and p["new_text"] == d.code()
    assert p["unified_diff"].startswith("--- a/pinn_diffusion.py") and "+optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)" in p["unified_diff"]


def test_do_it_for_me_retries_until_it_compiles(monkeypatch):
    answers = iter([
        {"summary": "Fix it", "yours": "return self.lossPDE(x_PDE)", "expected": "return self.lossBC(x_BC, y_BC) +", "line": 34},
        {"summary": "Add the boundary loss to the total", "yours": "return self.lossPDE(x_PDE)", "expected": "return self.lossBC(x_BC, y_BC) + self.lossPDE(x_PDE)", "line": 34},
    ])
    users = []

    async def call(**kw):
        users.append(kw["user_text"])
        return llm.CallResult(data=next(answers), model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    common.set_lesson(d.LESSON)
    p = run(coach.do_it_for_me(d.STEP, "pinn_diffusion.py", d.MISSING_BC_CODE, last_offtrack={}))
    assert p["_meta"]["via"] == "opus#2" and p["new_text"] == d.code()
    assert "PREVIOUS ATTEMPT FAILED: patched file would not compile" in users[1]


def test_do_it_for_me_gives_up_without_a_safe_patch(monkeypatch):
    async def call(**kw):
        return llm.CallResult(data={"summary": "x", "yours": "nope", "expected": "y", "line": 1}, model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    with pytest.raises(coach.CoachUnavailable, match="no safe patch"):
        run(coach.do_it_for_me(d.STEP, "pinn_diffusion.py", d.MISSING_BC_CODE, last_offtrack={}))


# ---------- "where is X" -------------------------------------------------------------------------------

def test_locate_exact_text_needs_no_model(monkeypatch):
    async def boom(**kw):
        raise AssertionError("no model call")

    monkeypatch.setattr(llm, "structured_call", boom)
    s = make_screen()
    t = run(coach.locate("optimizer.zero_grad()", s))
    assert t[0]["text"] == "optimizer.zero_grad()"


def test_locate_uses_haiku_for_descriptions(replay):
    """Recorded live Haiku call over the set-of-mark screen."""
    s = make_screen()
    t = run(coach.locate("the learning rate", s))
    assert t[0]["boxId"] == box_id_containing(s, "lr=0.3")


def test_locate_request_shape(monkeypatch):
    seen = {}

    async def call(**kw):
        seen.update(kw)
        return llm.CallResult(data={"box_ids": [999, 3]}, model=kw["model"])

    monkeypatch.setattr(llm, "structured_call", call)
    t = run(coach.locate("the learning rate", make_screen()))
    assert seen["model"] == "claude-haiku-5-5" and [b["type"] for b in seen["user_content"]] == ["text", "text", "image", "image"]
    assert [x["boxId"] for x in t] == [3]  # unknown id dropped


def test_locate_without_key_raises():
    with pytest.raises(coach.CoachUnavailable, match="locate failed"):
        run(coach.locate("the learning rate", make_screen()))


def test_inflight_replaces_previous_task():
    async def go():
        a = actions.inflight.start("k", asyncio.sleep(10))
        b = actions.inflight.start("k", asyncio.sleep(10))
        await asyncio.sleep(0)
        assert a.cancelled() or a.cancelling()
        assert actions.inflight.cancel() == 1 and actions.inflight.running() == []
        await asyncio.gather(a, b, return_exceptions=True)

    run(go())


def test_recorded_screen_diagnosis_points_at_the_lr_line(replay):
    """Recorded live Opus call with the set-of-mark screen: first target is the optimizer line."""
    s = make_screen()
    common.set_lesson(d.LESSON)
    fired = []
    card = run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE, screen=s, on_targets=fired.append))
    assert card["targets"][0]["boxId"] == box_id_containing(s, "lr=0.3") and fired == [card["targets"]]
    assert all(len(t["label"].split()) <= 3 for t in card["targets"])


# ---------- E4 integration: cursor, terminal commands, level-2-first ladder, action sentence -------------

def test_cursor_reaches_the_prompt(monkeypatch):
    seen = {}

    async def call(**kw):
        seen[kw["purpose"]] = kw["user_text"]
        if kw["purpose"] == "explain":
            return llm.CallResult(data={"title": "t", "body": "b", "explanation_index": -1, "citation_id": "none"}, model="o")
        return llm.CallResult(data={"playbook_id": "lr_too_high", "severity": "warn", "title": "t", "body": "b.", "citation_id": "none",
                                    "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0, "diff_command": "",
                                    "actions": [], "guiding_question": "q?"}, model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    common.set_lesson(d.LESSON)
    cur = {"x": 120.4, "y": 609.0, "under": {"text": "optimizer = torch.optim.Adam(model.parameters(), lr=0.3)", "app": "Code", "rect": {}}}
    run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE, cursor=cur))
    run(coach.explain(d.STEP, "why?", {"cursor": cur}))
    for purpose in ("diagnose", "explain"):
        assert 'LEARNER CURSOR: at (120, 609) over "optimizer = torch.optim.Adam(model.parameters(), lr=0.3)" (Code)' in seen[purpose]


def test_terminal_fix_travels_as_diff_command(monkeypatch):
    async def call(**kw):
        if kw["purpose"] == "triage":
            return llm.CallResult(data={"route": "opus", "playbook_id": "none", "reason": ""}, model="h")
        return llm.CallResult(data={"playbook_id": "none", "severity": "fail", "title": "pandas is not installed",
                                    "body": "The script imports pandas but this venv lacks it. Install it with pip install pandas.",
                                    "citation_id": "none", "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0,
                                    "diff_command": "pip install pandas", "actions": ["apply_fix"], "guiding_question": "Which venv is active?"}, model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    step = {"id": "p1", "title": "Run it", "instructions": "Run clean.py.", "checks": [{"id": "x", "type": "command_exit_ok", "label": "runs"}]}
    card = run(coach.diagnose(step, [{"checkId": "x", "status": "fail"}], None, "import pandas as pd", error_text="ModuleNotFoundError: No module named 'pandas'"))
    assert_offtrack(card)
    assert card["diff"] == {"expected": "", "yours": "", "command": "pip install pandas"} and "apply_fix" in card["actions"]


def test_level0_after_e4_strips_the_diff(replay):
    """E4 shows the first offtrack as level 2 without diff/apply_fix; level 0 must still be about the issue."""
    common.set_lesson(d.LESSON)
    card = coach.public(run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE)))
    shown = {k: v for k, v in card.items() if k != "diff"} | {"actions": [a for a in card["actions"] if a != "apply_fix"]}
    LAST.clear()  # orchestrator process restarted: only its stored card is left
    assert coach.hint(d.STEP, 0, shown)["body"] == card["guidingQuestion"]
    assert "1e-3" in card["body"]  # the fix is stated in words for the diff-less level-2 card


def test_level0_for_an_old_card_without_a_question():
    old = {"stepId": "d6", "title": "Learning rate 0.3 is far too high", "body": "…", "citation": {"label": "x", "url": "https://example.org"}}
    q = coach.hint(d.STEP, 0, old)["body"]
    assert q.startswith("Learning rate 0.3 is far too high:") and q.endswith("?")


# ---------- voice (ElevenLabs track) ------------------------------------------------------------------

import httpx

from server.coach import voice


@pytest.fixture
def tts(monkeypatch, tmp_path):
    """Fake ElevenLabs: records requests, streams a fake mp3 in two chunks."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, headers={"content-type": "audio/mpeg"}, content=b"ID3fake-mp3-bytes" * 64)

    monkeypatch.setenv("COACH_TTS_DIR", str(tmp_path))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice123")
    monkeypatch.setattr(voice, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(voice, "_client", None)
    voice._logged.clear()
    return calls


def test_voice_lines_are_short_and_readable():
    assert voice.line_for("step.started", {"index": 6, "title": "Train the PINN"}) == "Step 6: Train the PINN."
    assert voice.line_for("offtrack", {"title": "Adam learning rate 0.3 is too high", "body": "long..."}) == "Adam learning rate 0.3 is too high."
    assert voice.line_for("step.passed", {}) == "Nice, step passed."
    assert voice.line_for("metric", {"value": 1}) is None
    assert voice.spoken("Set lr to 1e-3 at β=30") == "Set learning rate to 0.001 at beta=30."


def test_speak_streams_caches_and_serves(tts):
    s = run(voice.speak_event("offtrack", {"title": "Adam learning rate 0.3 is too high"}))
    assert s["text"] == "Adam learning rate 0.3 is too high." and re.fullmatch(r"/tts/[0-9a-f]{20}\.mp3", s["audioUrl"])
    req = tts[0]
    assert req.method == "POST" and req.url.path == "/v1/text-to-speech/voice123/stream"
    assert req.url.params["output_format"] == "mp3_44100_128" and req.headers["xi-api-key"] == "el-test-key"
    assert json.loads(req.content) == {"text": "Adam learning rate 0.3 is too high.", "model_id": "eleven_flash_v2_5"}
    assert voice.last_timing["first_byte_s"] >= 0 and voice.last_timing["bytes"] > 0
    # cached: same line again makes no request
    assert run(voice.speak_event("offtrack", {"title": "Adam learning rate 0.3 is too high"})) == s and len(tts) == 1
    # served by the router; bad names are 404
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(voice.router)
    c = TestClient(app)
    r = c.get(s["audioUrl"])
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content.startswith(b"ID3")
    assert c.get("/tts/..%2F..%2Fetc%2Fpasswd").status_code == 404 and c.get("/tts/abc.mp3").status_code == 404


def test_concurrent_identical_lines_make_one_request(tts):
    async def go():
        return await asyncio.gather(*(voice.speak("Nice, step passed.") for _ in range(5)))

    out = run(go())
    assert len(tts) == 1 and len({o["audioUrl"] for o in out}) == 1


def test_voice_failures_never_raise(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("COACH_TTS_DIR", str(tmp_path))
    monkeypatch.setattr(voice, "_client", None)
    voice._logged.clear()
    # no key
    assert run(voice.speak("Hello there")) is None
    # HTTP error and network error
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "v")
    for handler in (lambda r: httpx.Response(401, json={"detail": "bad key"}), lambda r: (_ for _ in ()).throw(httpx.ConnectError("down"))):
        monkeypatch.setattr(voice, "_transport", httpx.MockTransport(handler))
        monkeypatch.setattr(voice, "_client", None)
        assert run(voice.speak("Hello again")) is None
    assert not list(tmp_path.glob("*.mp3")) and not list(tmp_path.glob("*.part"))
    msgs = [r.getMessage() for r in caplog.records if r.name == "coach.voice"]
    assert any("HTTP 401" in m for m in msgs) and any("ConnectError" in m for m in msgs)
    assert not any("el-" in m or "k)" in m for m in msgs)  # never logs the key


def test_prefetch_step_titles(tts):
    titles = [s["title"] for s in d.LESSON["steps"]] + ["Write the residual"]
    assert run(voice.prefetch(titles)) == len(titles)


# ---------- demo rehearsal (S11): latency of metric-only failures, offline stage fallback ----------------

def test_metric_only_failure_never_waits_on_the_web(monkeypatch, replay):
    calls = []

    async def gather(*a, **kw):
        calls.append(a)
        return []

    monkeypatch.setattr(web, "gather", gather)
    common.set_lesson(d.LESSON)
    run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE))
    assert calls == []  # hero: no error text → no Bright Data round trips before Opus
    run(coach.diagnose(d.STEP, d.NO_GRAD_FAILED, None, d.NO_GRAD_CODE, error_text=d.NO_GRAD_ERROR))
    assert len(calls) == 1  # an error message is still looked up in the docs


def _client_raising(monkeypatch, exc):
    import anthropic

    class Msgs:
        async def create(self, **kw):
            raise exc(anthropic)

    fake = SimpleNamespace(beta=SimpleNamespace(messages=Msgs()), messages=Msgs())
    fake.with_options = lambda **_: fake
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")


def _conn_error(anthropic):
    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


def test_offline_fallback_is_opt_in(monkeypatch):
    _client_raising(monkeypatch, _conn_error)
    common.set_lesson(d.LESSON)
    with pytest.raises(coach.CoachUnavailable, match="connection error"):
        run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE))
    monkeypatch.setenv("COACH_OFFLINE_FALLBACK", "1")
    card = run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE))
    assert_offtrack(card)
    pub = coach.public(card)
    assert pub["offline"] is True and card["_meta"]["route"] == "playbook" and card["_meta"]["playbook_id"] == "lr_too_high"
    assert "connection error" in card["_meta"]["fallback_reason"] and card["_meta"]["confidence"] >= 0.6
    assert coach.hint(d.STEP, 0, pub)["body"].startswith("What happens to Adam")


def test_offline_fallback_never_covers_other_failures(monkeypatch):
    monkeypatch.setenv("COACH_OFFLINE_FALLBACK", "1")
    common.set_lesson(d.LESSON)
    # an API error (not a network outage) still raises
    _client_raising(monkeypatch, lambda a: a.InternalServerError("boom", response=httpx.Response(500, request=httpx.Request("POST", "https://x")), body=None))
    with pytest.raises(coach.CoachUnavailable):
        run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE))
    # a network outage without a confident match on the learner's code still raises
    _client_raising(monkeypatch, _conn_error)
    with pytest.raises(coach.CoachUnavailable):
        run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, None, "print('hello')"))


# ---------- Explain / Show me / Hint point at the screen (Michael, live) ------------------------------

from server.coach.tests.screen_case import step_without_targets, terminal_only


def test_show_me_exact_match_is_instant_and_whole_word(monkeypatch):
    async def boom(**kw):
        raise AssertionError("exact match must not call a model")

    monkeypatch.setattr(llm, "structured_call", boom)
    s = make_screen()
    r = run(coach.show_me(d.STEP, s))  # step target `def loss` → `def loss(...)`, not `def lossPDE`
    assert r["targets"][0]["text"].startswith("def loss(self") and r["caption"] == "total loss" and r["where"] is None
    LAST["d6"] = {"title": "Adam learning rate 0.3 is too high", "diff": {"yours": "optimizer = torch.optim.Adam(model.parameters(), lr=0.3)"}}
    r = run(coach.show_me(d.STEP, s))  # after a diagnosis: the line to change
    assert "lr=0.3" in r["targets"][0]["text"]


def test_point_uses_haiku_without_thinking(replay):
    """Recorded live Haiku calls: finds the lr line; with the editor closed, says where to go."""
    s = make_screen()
    bare = step_without_targets(d.STEP)
    p = run(coach.point(bare, s, about="the learning rate setting"))
    assert p["via"] == "haiku" and "lr=0.3" in p["targets"][0]["text"] and p["where"] is None
    p = run(coach.point(bare, terminal_only(s), about="the learning rate setting in the code"))
    assert p["targets"] == [] and "pinn_diffusion.py" in p["where"]


def test_point_request_shape_and_fallbacks(monkeypatch):
    seen = {}

    async def call(**kw):
        seen.update(kw)
        return llm.CallResult(data={"box_ids": [999], "where": ""}, model=kw["model"])

    monkeypatch.setattr(llm, "structured_call", call)
    p = run(coach.point(step_without_targets(d.STEP), make_screen(), about="something"))
    assert seen["model"] == "claude-haiku-5-5" and seen["thinking"] == {"type": "disabled"} and "user_content" not in seen
    assert p["targets"] == [] and p["where"] == "Open the code for this step"  # unknown id → no fake target
    assert run(coach.point(d.STEP, None, about="x"))["where"] == "Open pinn_diffusion.py in your editor"

    async def down(**kw):
        raise llm.CoachLLMError("x", "connection")

    monkeypatch.setattr(llm, "structured_call", down)
    p = run(coach.point(step_without_targets(d.STEP), make_screen(), about="something"))
    assert p["via"] == "fallback" and p["targets"] == [] and p["where"]


def test_hint_points_or_says_where_first():
    card = {"title": "Adam learning rate 0.3 is too high", "guidingQuestion": "What happens to Adam's steps when lr is large?",
            "diff": {"yours": "optimizer = torch.optim.Adam(model.parameters(), lr=0.3)", "expected": "x", "file": "pinn_diffusion.py"}}
    s = make_screen()
    h = coach.hint(d.STEP, 0, card, screen=s)
    assert h["body"] == card["guidingQuestion"] and "lr=0.3" in h["targets"][0]["text"]
    h = coach.hint(d.STEP, 0, card, screen=terminal_only(s))  # `$ python pinn_diffusion.py` is not the code
    assert h["title"] == "Open your code first" and h["body"].startswith("Open pinn_diffusion.py in your editor. Then: What happens")
    assert h["where"] == "Open pinn_diffusion.py in your editor" and "targets" not in h
    h = coach.hint(step_without_targets(d.STEP) | {"checks": [{"id": "r", "type": "command_exit_ok", "command": "python train.py"}]}, 1, {}, screen=terminal_only(s))
    assert h["where"] == "Switch to your terminal and run `python train.py`"


def test_explain_points_before_the_text_arrives(monkeypatch):
    order = []

    async def call(**kw):
        if kw["purpose"] == "point":
            await asyncio.sleep(0.05)
            order.append("point")
            return llm.CallResult(data={"box_ids": [box_id_containing(make_screen(), "lr=0.3")], "where": ""}, model="h")
        await asyncio.sleep(0.3)
        order.append("explain")
        assert "user_content" not in kw  # Opus gets text only; pointing is Haiku's job
        return llm.CallResult(data={"title": "Big steps overshoot", "body": "b", "explanation_index": -1, "citation_id": "none"}, model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    common.set_lesson(d.LESSON)
    fired = []
    card = run(coach.explain(step_without_targets(d.STEP), "why does lr matter?", {"screen": make_screen(), "on_targets": lambda t: fired.append(list(order))}))
    assert fired == [["point"]]  # targets reached the app before the Opus text
    assert "lr=0.3" in card["targets"][0]["text"] and card["_meta"]["point_via"] == "haiku"


# ---------- S9 QA on React / pandas / git mistakes ------------------------------------------------------

from server.coach.diagnose import (
    COACH_SYSTEM,
    _unsafe_git_continue,
    notebook_code,
    screen_errors,
)
from server.coach.screen import Box


def _git_screen() -> ScreenContext:
    from PIL import Image

    texts = ["pick a1b2c3 Add login", "$ git rebase --continue", "index.js: needs merge",
             "error: You must edit all merge conflicts and then mark them as resolved using git add"]
    boxes = [Box(0, t, 900, 450 + 16 * i, 400, 13, app="Terminal") for i, t in enumerate(texts)]
    return ScreenContext(image=Image.new("RGB", (100, 100)), cursor=(950, 470), boxes=boxes, scale=1.0, app="Terminal").numbered()


def test_screen_errors_are_error_text_and_never_template(monkeypatch):
    seen = {}

    async def call(**kw):
        seen.setdefault(kw["purpose"], kw["user_text"])
        if kw["purpose"] == "triage":
            return llm.CallResult(data={"route": "template", "playbook_id": "none", "reason": "no error output"}, model="h")
        return llm.CallResult(data={"playbook_id": "none", "severity": "fail", "title": "Conflict markers still in index.js",
                                    "body": "Git stops because index.js still has conflict markers. Remove them, then git add index.js.",
                                    "citation_id": "none", "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0,
                                    "diff_command": "", "actions": [], "guiding_question": "q?"}, model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    step = {"id": "g2", "title": "Resolve the conflict", "instructions": "Fix the conflict and continue.",
            "checks": [{"id": "f", "type": "file_contains", "label": "no markers", "file": "index.js", "pattern": "^(?!<<<<<<<)"}]}
    s = _git_screen()
    assert "needs merge" in screen_errors(s) and "You must edit all merge conflicts" in screen_errors(s)
    card = run(coach.diagnose(step, [{"checkId": "f", "label": "no markers", "status": "fail"}], None, "", screen=s))
    assert card["_meta"]["route"] == "opus"  # Haiku said template; an error is on screen → overridden
    assert "needs merge" in seen["triage"] and "needs merge" in seen["diagnose"]


def test_prompt_trusts_screen_and_guards_git():
    assert "Trust what is on screen" in COACH_SYSTEM and "conflict markers" in COACH_SYSTEM
    conflict = "<<<<<<< HEAD\nconst a = 1;\n=======\nconst a = 2;\n>>>>>>> topic\n"
    assert _unsafe_git_continue("git add index.js && git rebase --continue", conflict, "", "")
    assert not _unsafe_git_continue("git add index.js && git rebase --continue", conflict, "<<<<<<< HEAD", "const a = 2;")
    assert not _unsafe_git_continue("pip install pandas", conflict, "", "")


def test_apply_fix_tolerates_ocr_anchors():
    src = "a = 1\n<<<<<<< HEAD\nb = 2\n=======\nb = 3\n>>>>>>> topic\nc = 4\n"
    r = coach.apply_fix({"file": "x.py", "yours": "2 <<<<<<< HEAD\n3 b = 2\n4 =======\n5 b = 3\n6 >>>>>>> topic", "expected": "b = 3"}, src)
    assert r["error"] is None and r["new_text"] == "a = 1\nb = 3\nc = 4\n"
    r = coach.apply_fix({"file": "y.py", "yours": "x  =  foo( 1,2 )", "expected": "x = foo(1, 3)"}, "x = foo(1, 2)\n")
    assert r["error"] is None and r["new_text"] == "x = foo(1, 3)\n"


def test_apply_fix_rejects_no_op():
    r = coach.apply_fix({"file": "x.py", "yours": "a = 1", "expected": "a = 1"}, "a = 1\n")
    assert r["new_text"] is None and r["error"] == "the patch changes nothing"


def test_notebook_excerpt_and_cell_patch():
    nb = {"cells": [{"cell_type": "markdown", "source": ["# Sales\n"]},
                    {"cell_type": "code", "source": ["import pandas as pd\n", "%matplotlib inline\n", "for k, v in counts.iteritems():\n", "    print(k, v)"],
                     "outputs": [{"text": "\x1b[31m" * 500}], "execution_count": 3, "metadata": {}}],
          "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    raw = json.dumps(nb)
    ex = notebook_code(raw)
    assert ex.startswith("# %% [cell 1]\nimport pandas as pd") and "\x1b" not in ex and "outputs" not in ex
    r = coach.apply_fix({"file": "clean.ipynb", "yours": "for k, v in counts.iteritems():", "expected": "for k, v in counts.items():"}, raw)
    assert r["error"] is None
    out = json.loads(r["new_text"])
    assert out["cells"][1]["source"][2] == "for k, v in counts.items():\n" and out["cells"][1]["source"][3] == "    print(k, v)"
    assert out["cells"][1]["outputs"] == nb["cells"][1]["outputs"] and "[cell 1]" in r["unified_diff"]


def test_do_it_for_me_command_fix_and_missing_edit(monkeypatch):
    card = {"title": "pandas missing", "body": "The venv lacks pandas. Install it.", "diff": {"expected": "", "yours": "", "command": "pip install pandas"}}
    r = run(coach.do_it_for_me(d.STEP, "clean.py", "import pandas\n", card))
    assert r["command"] == "pip install pandas" and r["new_text"] is None and r["unified_diff"] == ""

    todo = "pick a1 Add login\npick b2 Cleanup\n"
    card = {"title": "Squash the cleanup", "body": "The cleanup must fold into the previous commit. Change Cleanup's command to `squash`.",
            "diff": {"yours": "pick a1 Add login", "expected": "pick a1 Add login", "file": "git-rebase-todo"}}
    users = []

    async def call(**kw):
        users.append(kw["user_text"])
        return llm.CallResult(data={"summary": "Squash Cleanup into Add login", "yours": "pick b2 Cleanup", "expected": "squash b2 Cleanup",
                                    "line": 2, "command": ""}, model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    r = run(coach.do_it_for_me(d.STEP, "git-rebase-todo", todo, card))
    assert r["_meta"]["via"] == "opus#1" and r["new_text"] == "pick a1 Add login\nsquash b2 Cleanup\n"
    assert "PREVIOUS ATTEMPT FAILED" in users[0]  # the diagnosis diff was a no-op that missed `squash`


# ---------- cost policy: Opus only for the diagnosis card ------------------------------------------------

def test_models_by_purpose(monkeypatch):
    assert llm.model_for("diagnose") == "claude-opus-5-5"
    for purpose in ("triage", "point", "locate", "explain", "do_it_for_me", "fix_outdated"):
        assert llm.model_for(purpose) == "claude-haiku-5-5"
    monkeypatch.setenv("COACH_MODEL_EXPLAIN", "claude-opus-5-5")
    assert llm.model_for("explain") == "claude-opus-5-5"


def test_live_paths_use_the_policy(monkeypatch, fake_web):
    used = {}

    async def call(**kw):
        used[kw["purpose"]] = (kw["model"], all("cache_control" in b for b in kw["system"]))
        data = {
            "triage": {"route": "opus", "playbook_id": "none", "reason": ""},
            "diagnose": {"playbook_id": "none", "severity": "fail", "title": "t", "body": "b. Do x.", "citation_id": "none", "diff_expected": "",
                         "diff_yours": "", "diff_file": "", "diff_line": 0, "diff_command": "", "actions": [], "guiding_question": "q?"},
            "explain": {"title": "t", "body": "b", "explanation_index": -1, "citation_id": "none"},
            "point": {"box_ids": [], "where": "x"},
            "locate": {"box_ids": []},
            "do_it_for_me": {"summary": "s", "yours": "a = 1", "expected": "a = 2", "line": 1, "command": ""},
            "fix_outdated": {"found": False, "title": "", "body": "", "yours": "", "expected": "", "source_index": 0},
        }[kw["purpose"]]
        return llm.CallResult(data=data, model=kw["model"])

    monkeypatch.setattr(llm, "structured_call", call)
    common.set_lesson(g.REACT_LESSON)
    run(coach.diagnose(g.REACT_STEP, g.REACT_FAILED, None, g.REACT_CODE, error_text=g.REACT_ERROR))
    run(coach.explain(g.REACT_STEP, "why?", {"screen": make_screen()}))
    run(coach.locate("nothing like this", make_screen()))
    run(coach.do_it_for_me(g.REACT_STEP, "a.py", "a = 1\n", last_offtrack={}))
    run(coach.fix_outdated(g.PANDAS_ERROR, g.PANDAS_LIBS))
    assert {p: m for p, (m, _) in used.items()} == {
        "triage": "claude-haiku-5-5", "diagnose": "claude-opus-5-5", "explain": "claude-haiku-5-5", "point": "claude-haiku-5-5",
        "locate": "claude-haiku-5-5", "do_it_for_me": "claude-haiku-5-5", "fix_outdated": "claude-haiku-5-5"}
    assert all(cached for _, cached in used.values())  # every system prompt is marked for prompt caching


def test_record_fixtures_refuses_without_opt_in(monkeypatch):
    import runpy

    monkeypatch.delenv("COACH_ALLOW_LIVE", raising=False)
    monkeypatch.setenv("COACH_RECORD_DIR", "")  # the module sets it on import; monkeypatch restores it afterwards
    with pytest.raises(SystemExit, match="COACH_ALLOW_LIVE=1"):
        runpy.run_module("server.coach.tests.record_fixtures", run_name="__main__")


# ---------- S9 re-run on d219e52 ---------------------------------------------------------------------------

TODO = "pick 1a2b3c4 Add login endpoint\npick 7a428b4 Add logout\npick 9f8e7d6 Cleanup\nsquash 1194326 Add README\n\n# Rebase 0123..1194326 onto 0123 (4 commands)\n"


def test_g1_rewritten_todo_replaces_the_whole_span():
    """Model rewrote 4 todo lines but anchored on 1: widen to the 4, don't insert 3 duplicate picks."""
    diff = {"file": ".git/rebase-merge/git-rebase-todo", "yours": "squash 1194326 Add README",
            "expected": "pick 1a2b3c4 Add login endpoint\npick 7a428b4 Add logout\nsquash 9f8e7d6 Cleanup\npick 1194326 Add README"}
    r = coach.apply_fix(diff, TODO)
    assert r["error"] is None
    body = [ln for ln in r["new_text"].splitlines() if ln and not ln.startswith("#")]
    assert body == diff["expected"].splitlines()


def test_rebase_todo_must_keep_every_commit_once():
    r = coach.apply_fix({"file": "git-rebase-todo", "yours": "pick 7a428b4 Add logout", "expected": "pick 1a2b3c4 Add login endpoint"}, TODO)
    assert r["new_text"] is None and "lose or repeat a commit" in r["error"]


def test_patch_that_would_duplicate_a_neighbour_is_rejected():
    src = "a = 1\nb = 2\nc = 3\nd = 4\n"
    # expected repeats the lines above as context: the span widens over them, nothing is duplicated
    r = coach.apply_fix({"file": "x.py", "yours": "x = 9", "expected": "a = 1\nb = 2\nx = 10"}, "a = 1\nb = 2\nx = 9\n")
    assert r["new_text"] == "a = 1\nb = 2\nx = 10\n"
    # a same-size replacement equal to the two lines above would repeat them → rejected
    r = coach.apply_fix({"file": "x.py", "yours": "x = 9\ny = 8", "expected": "a = 1\nb = 2"}, "a = 1\nb = 2\nx = 9\ny = 8\n")
    assert r["new_text"] is None and "duplicate" in r["error"]
    # a single repeated line next to the span is normal code, not a duplicate
    r = coach.apply_fix({"file": "x.py", "yours": "c = 3", "expected": "b = 2\nc = 30"}, src)
    assert r["error"] is None


def test_g3_repeated_closing_lines_are_not_duplicates():
    """S9 false positive: the login route right above ends with the same `res.json(...)` / `});`."""
    src = "app.post('/login', (req, res) => {\n  res.json({ ok: true });\n});\n<<<<<<< HEAD\n=======\napp.post('/logout', (req, res) => {\n  res.json({ ok: true });\n});\n>>>>>>> topic\n"
    r = coach.apply_fix({"file": "index.js", "yours": "<<<<<<< HEAD\n=======\napp.post('/logout', (req, res) => {\n  res.json({ ok: true });\n});\n>>>>>>> topic",
                         "expected": "app.post('/logout', (req, res) => {\n  res.json({ ok: true });\n});"}, src)
    assert r["error"] is None and "<<<<<<<" not in r["new_text"] and r["new_text"].count("app.post('/logout'") == 1


def test_g3_fuzzy_ocr_anchor_maps_onto_real_lines():
    src = "const app = express();\n<<<<<<< HEAD\napp.post('/logout', (req, res) => {\n  res.json({ ok: true });\n=======\napp.post('/logout', (req, res) => {\n  res.json({ ok: false });\n>>>>>>> topic\n});\n"
    ocr = "10 <<<<< HEAD\n11\n12 app.post('/logout', (req, res) = {\n13 res. json({ ok: true });\n14 =======\n15 app.post('/logout', (req, res) => {\n16 res.json({ ok: false });\n17 >>>>>>> topic"
    r = coach.apply_fix({"file": "index.js", "yours": ocr, "expected": "app.post('/logout', (req, res) => {\n  res.json({ ok: true });"}, src)
    assert r["error"] is None and "<<<<<<<" not in r["new_text"] and ">>>>>>>" not in r["new_text"]
    assert r["new_text"].count("app.post('/logout'") == 1


def _big_notebook() -> str:
    noisy = [{"output_type": "stream", "name": "stdout", "text": ["\u001b[31m" + "x" * 80 + "\n"] * 60}]
    nb = {"cells": [{"cell_type": "markdown", "metadata": {}, "source": ["# Sales report\n"]},
                    {"cell_type": "code", "execution_count": 1, "metadata": {}, "outputs": [],
                     "source": ["import pandas as pd\n", "df = pd.read_csv('sales.csv')\n", "df.groupby('region', 'month').sum()"]},
                    {"cell_type": "code", "execution_count": 2, "metadata": {}, "outputs": noisy, "source": ["print(df.head())"]}],
          "metadata": {"kernelspec": {"name": "python3"}}, "nbformat": 4, "nbformat_minor": 5}
    return json.dumps(nb, indent=1, sort_keys=True)


def test_truncated_notebook_excerpt_still_reaches_the_model(monkeypatch):
    raw = _big_notebook()
    cut = raw[:6000]  # what the orchestrator sends
    with pytest.raises(json.JSONDecodeError):
        json.loads(cut)
    ex = notebook_code(cut)
    assert ex.startswith("# %% [cell 1]\nimport pandas as pd") and "groupby('region', 'month')" in ex and "\u001b" not in ex
    assert notebook_code(raw[:200]) == "# (notebook: no code cell source within the excerpt)"
    seen = {}

    async def call(**kw):
        seen.setdefault(kw["purpose"], kw["user_text"])
        if kw["purpose"] == "triage":
            return llm.CallResult(data={"route": "opus", "playbook_id": "none", "reason": ""}, model="h")
        return llm.CallResult(data={"playbook_id": "none", "severity": "fail", "title": "t", "body": "b. Do x.", "citation_id": "none",
                                    "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0, "diff_command": "", "actions": [],
                                    "guiding_question": "q?"}, model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    step = {"id": "p2", "title": "Group sales", "instructions": "Sum sales per region and month.", "checks": [{"id": "x", "type": "output_contains", "label": "table"}]}
    err = "ValueError: level name month is not the name of the index"
    run(coach.diagnose(step, [{"checkId": "x", "status": "fail"}], None, cut, error_text=err))
    assert "# %% [cell 1]" in seen["diagnose"] and '"outputs"' not in seen["diagnose"]
    assert f"THE ERROR MESSAGE (your cause must agree with exactly what it says, for the version that printed it):\n{err}" in seen["diagnose"]


def test_web_skips_self_explaining_errors_and_caps_at_1_5s(monkeypatch):
    calls = []

    async def gather(*a, **kw):
        calls.append(kw.get("timeout"))
        return []

    async def call(**kw):
        if kw["purpose"] == "triage":
            return llm.CallResult(data={"route": "opus", "playbook_id": "none", "reason": ""}, model="h")
        return llm.CallResult(data={"playbook_id": "none", "severity": "fail", "title": "t", "body": "b. Do x.", "citation_id": "none",
                                    "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0, "diff_command": "", "actions": [],
                                    "guiding_question": "q?"}, model="o")

    monkeypatch.setattr(web, "gather", gather)
    monkeypatch.setattr(llm, "structured_call", call)
    step = {"id": "r1", "title": "Render", "instructions": "Render the list.", "checks": [{"id": "x", "type": "command_exit_ok", "label": "build"}]}
    run(coach.diagnose(step, [{"checkId": "x", "status": "fail"}], None, "x", error_text="ReferenceError: users is not defined"))
    run(coach.diagnose(step, [{"checkId": "x", "status": "fail"}], None, "x", error_text="NameError: name 'df' is not defined"))
    assert calls == []
    run(coach.diagnose(step, [{"checkId": "x", "status": "fail"}], None, "x", error_text="TypeError: Cannot read properties of undefined (reading 'map')"))
    assert calls == [1.5]


def _conflict_file() -> str:
    filler = [f"const line{i} = {i};" for i in range(1, 10)]
    block = ["<<<<<<< HEAD", "=======", "app.post('/logout', (req, res) => {", "  res.json({ ok: true });", "});", "", ">>>>>>> topic"]
    return "\n".join(filler + block + ["app.listen(3000);"]) + "\n"


def test_g3_ocr_dropped_marker_row_uses_gutter_numbers():
    """S9 G3 re-check: Vision dropped the `=======` row; only its gutter "11" survived."""
    ocr = "10 <<<<< HEAD\n11\n12 app.post('/logout', (req, res) = {\n13 res. json({ ok: true });\n14 });\n16 >>>>>>> topic"
    expected = "app.post('/logout', (req, res) => {\n  res.json({ ok: true });\n});"
    r = coach.apply_fix({"file": "index.js", "yours": ocr, "expected": expected}, _conflict_file())
    assert r["error"] is None
    assert not re.search(r"^(<{7}|={7}|>{7})", r["new_text"], re.MULTILINE)
    assert r["new_text"].count("app.post('/logout'") == 1 and r["new_text"].rstrip().endswith("app.listen(3000);")


def test_fuzzy_walk_skips_dropped_marker_rows():
    ocr = "<<<<< HEAD\napp.post('/logout', (req, res) = {\nres. json({ ok: true });"  # no gutter numbers, `=======` dropped
    r = coach.apply_fix({"file": "index.js", "yours": ocr, "expected": "app.post('/logout', (req, res) => {\n  res.json({ ok: true });"}, _conflict_file())
    assert r["error"] is None and "<<<<<<<" not in r["new_text"] and "=======" not in r["new_text"]


def test_git_squash_order_playbook_entry():
    """Finishing G3: a squash moved above the commit whose code it edits → abort and reorder."""
    todo = "pick 1a2b3c4 Add login endpoint\nsquash 9f8e7d6 Cleanup\npick 8d7db63 Add logout endpoint\n"
    mode, conf = match(todo, set(), "CONFLICT (content): Merge conflict in index.js")
    assert mode.id == "git_squash_above_its_commit" and conf >= 0.3
    card = coach.playbook_card({"id": "g3"}, mode, todo, severity="fail")
    assert "git rebase --abort" in card["body"] and card["citation"]["url"] == "https://git-scm.com/docs/git-rebase"
    assert card["guidingQuestion"].endswith("?")
    assert "git_squash_above_its_commit" in COACH_SYSTEM and "never `git add` + `--continue`" in COACH_SYSTEM


def test_missing_term_bonus_needs_its_own_context():
    # a git todo list "lacks an IC/BC loss term", which says nothing: the PINN entry must not score on it
    _, conf = match("pick 1a2b3c4 Add login\n", set(), "")
    assert conf == 0.0


# ---------- S11 re-check: hero takes where lr=0.3 makes the loss sit flat; passing-run output tails -------

def _flat_hero_loss() -> dict:
    """S11's take: 18.18, 15.03, then flat at 17.32 for steps 200-2499 with a few blips."""
    vals = [18.18, 15.03] + [17.32] * 23
    for i, v in ((6, 17.39), (13, 17.73), (19, 17.39)):
        vals[i] = v
    return {"loss": [(i * 100, v) for i, v in enumerate(vals)]}


HERO_TAIL = "\n".join(f'step {s} | loss 17.3204\n::metric:: {{"step": {s}, "name": "test_loss", "value": 17.32}}' for s in range(2000, 2500, 100))


def test_flat_high_loss_with_high_lr_is_lr_too_high():
    flags = summarize(_flat_hero_loss(), goals={"loss": "down"})[1]
    assert "plateau" in flags
    mode, conf = match(d.HIGH_LR_CODE, flags, HERO_TAIL)
    assert mode.id == "lr_too_high" and conf >= 0.6  # the offline stage fallback threshold
    # without a β in the code the convection entry can't win; with a normal lr a plateau isn't "lr too high"
    mode, _ = match(d.code(), flags, "")
    assert mode is None or mode.id != "lr_too_high"
    assert all(m.id != "pinn_convection_large_beta" for m in [match(d.HIGH_LR_CODE, flags, "")[0]])


def test_offline_fallback_covers_the_flat_hero_take(monkeypatch):
    _client_raising(monkeypatch, _conn_error)
    monkeypatch.setenv("COACH_OFFLINE_FALLBACK", "1")
    common.set_lesson(d.LESSON)
    card = run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, _flat_hero_loss(), d.HIGH_LR_CODE, error_text=HERO_TAIL))
    assert card["offline"] is True and card["_meta"]["playbook_id"] == "lr_too_high" and card["severity"] == "warn"


def test_passing_run_tail_is_not_an_error(monkeypatch):
    calls, seen = [], {}

    async def gather(*a, **kw):
        calls.append(a)
        return []

    async def call(**kw):
        seen[kw["purpose"]] = kw["user_text"]
        return llm.CallResult(data={"playbook_id": "lr_too_high", "severity": "warn", "title": "t", "body": "b. Set lr to 1e-3.",
                                    "citation_id": "none", "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0,
                                    "diff_command": "", "actions": [], "guiding_question": "q?"}, model="o")

    monkeypatch.setattr(web, "gather", gather)
    monkeypatch.setattr(llm, "structured_call", call)
    common.set_lesson(d.LESSON)
    run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, _flat_hero_loss(), d.HIGH_LR_CODE, error_text=HERO_TAIL))
    assert calls == []  # no Bright Data round trips for metric lines
    assert "THE ERROR MESSAGE" not in seen["diagnose"] and "step 2400 | loss 17.3204" in seen["diagnose"]  # still shown as context
