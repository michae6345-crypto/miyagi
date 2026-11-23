"""The LLM cost lane, offline (every client is a fake): the model table, prompt-cache breakpoints on the stable
prefix of each main call site, cache tokens recorded and priced, and the build-cost estimator."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import logging
from types import SimpleNamespace

import pytest

from server import config as server_config
from server import models, prompt_cache
from server.lesson import build_cost_estimate as est
from server.lesson import claude, cost

EPH = {"type": "ephemeral"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(cost, "_session", cost._fresh())
    monkeypatch.setattr(cost, "_handlers", [])
    monkeypatch.delenv("MIYAGI_PRICES_JSON", raising=False)
    cost._counter.set(None)
    names = {n for r in models.ROUTES.values() for n in r.env} | {"MIYAGI_ALLOW_OPUS", "LESSON_ALLOW_OPUS", "LESSON_CLAUDE_MODEL"}
    for n in names:
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(server_config, "mode", lambda provider: "direct")  # not the cloud
    yield


# ------------------------------------------------------------------------------------- (a) the routing table

def test_every_purpose_is_haiku_or_sonnet_by_default():
    assert models.ROUTES
    for purpose in models.ROUTES:
        assert models.model_for(purpose) in (models.HAIKU, models.SONNET), purpose
        assert "opus" not in models.model_for(purpose)
    assert models.model_for("coach.something_new") == models.HAIKU  # an unlisted coach purpose is the cheap model


def test_the_table_routes_small_calls_to_haiku_and_reasoning_to_sonnet():
    sonnet = {"lesson.segment", "lesson.escalate", "coach.diagnose", "coach.explain_selection", "screen.coach", "diagrams",
              "workspace.scaffold",
              "coach.fast_ask"}  # streamed circle to ask (Nov 22): Sonnet, thinking off, low effort; Haiku for simple asks
    for purpose in models.ROUTES:
        want = models.SONNET if purpose in sonnet else models.HAIKU
        assert models.model_for(purpose) == want, purpose


def test_call_sites_take_their_model_from_the_table():
    import importlib

    from server.coach import llm, scene, selection

    diagrams = importlib.import_module("server.diagrams.build")
    from server.finder import claude as finder
    from server.screen import describe, target
    from server.workspace import scaffold

    assert claude.model("segment") == models.model_for("lesson.segment")
    for role in ("detail", "adapt", "judge", "escalate"):
        assert claude.model(role) == models.model_for(f"lesson.{role}")
    assert llm.model_for("diagnose") == models.SONNET and llm.model_for("hint") == models.HAIKU
    assert selection.model() == models.SONNET and scene.MODEL == models.HAIKU
    assert describe.COACH_MODEL == models.SONNET and describe.QUICK_MODEL == models.HAIKU
    assert target.MODEL == models.HAIKU and diagrams.MODEL == models.SONNET
    assert finder.model() == models.HAIKU and scaffold.model() == models.SONNET


@pytest.mark.parametrize("purpose,env", [
    ("lesson.detail", "LESSON_CLAUDE_MODEL_DETAIL"), ("lesson.segment", "LESSON_CLAUDE_MODEL"),
    ("coach.hint", "COACH_MODEL_HINT"), ("coach.diagnose", "COACH_MODEL_DIAGNOSE"), ("diagrams", "DIAGRAMS_MODEL"),
    ("workspace.scaffold", "WORKSPACE_CLAUDE_MODEL"), ("workspace.requirements", "WORKSPACE_REQ_MODEL"),
    ("finder", "FINDER_CLAUDE_MODEL"), ("screen.coach", "TUT_SCREEN_COACH_MODEL"), ("screen.quick", "TUT_SCREEN_QUICK_MODEL"),
    ("screen.target", "MIYAGI_VISION_MODEL"), ("coach.scene", "MIYAGI_SCENE_MODEL"), ("preflight", "PREFLIGHT_MODEL"),
])
def test_env_overrides_win_and_an_opus_override_falls_back_to_sonnet(monkeypatch, purpose, env):
    monkeypatch.setenv(env, "claude-haiku-5-5" if models.default_for(purpose) == models.SONNET else "claude-sonnet-5-5")
    assert models.model_for(purpose) == ("claude-haiku-5-5" if models.default_for(purpose) == models.SONNET else "claude-sonnet-5-5")
    monkeypatch.setenv(env, "claude-opus-5-5")
    assert models.model_for(purpose) == models.SONNET  # MIYAGI_ALLOW_OPUS is not set


def test_lesson_and_coach_env_overrides_through_their_own_helpers(monkeypatch):
    from server.coach import llm

    monkeypatch.setenv("LESSON_CLAUDE_MODEL_DETAIL", "claude-sonnet-5-5")
    assert claude.model("detail") == "claude-sonnet-5-5"
    monkeypatch.setenv("LESSON_CLAUDE_MODEL", "claude-opus-5-5")
    assert claude.model("detail") == models.SONNET and claude.model("segment") == models.SONNET
    monkeypatch.setenv("COACH_MODEL_EXPLAIN", "claude-sonnet-5-5")
    assert llm.model_for("explain") == "claude-sonnet-5-5"
    monkeypatch.setenv("COACH_MODEL_EXPLAIN", "claude-opus-5-5")
    assert llm.model_for("explain") == models.SONNET


# ------------------------------------------------------------------------------------- (b) cache breakpoints

class _Resp(SimpleNamespace):
    pass


def _usage(inp=100, out=20, cr=0, cw=0):
    return SimpleNamespace(input_tokens=inp, output_tokens=out, cache_read_input_tokens=cr, cache_creation_input_tokens=cw)


def _msg(text, model="claude-haiku-5-5", usage=None):
    return _Resp(model=model, usage=usage or _usage(), stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get_final_message(self):
        return self.msg


class _Api:
    """messages / beta.messages of a fake Anthropic client: records every request, answers with `reply(kw)`."""

    def __init__(self, reply, seen):
        self.reply, self.seen = reply, seen

    def stream(self, **kw):
        self.seen.append(kw)
        return _Stream(self.reply(kw))

    async def create(self, **kw):
        self.seen.append(kw)
        return self.reply(kw)


def _fake_client(reply):
    seen: list[dict] = []
    api = _Api(reply, seen)
    return SimpleNamespace(messages=api, beta=SimpleNamespace(messages=api), with_options=lambda **k: SimpleNamespace(
        messages=api, beta=SimpleNamespace(messages=api))), seen


def _breakpoints_ok(kw):
    n = prompt_cache.count_breakpoints(kw)
    assert 1 <= n <= prompt_cache.MAX_BREAKPOINTS, n


INFO = {
    "video_id": "abc123def45", "title": "Learn pandas", "description": "A pandas tutorial", "length_s": 600,
    "chapters": [{"t": 0, "title": "Intro"}, {"t": 120, "title": "Load the CSV"}],
    "transcript": [{"t": 5.0, "text": "hi everyone"}, {"t": 70.0, "text": "now we import pandas as pd"},
                   {"t": 130.0, "text": "and read the csv with read_csv"}, {"t": 200.0, "text": "then we print the head"}],
}


def _lesson_reply(kw):
    if "format" in (kw.get("output_config") or {}):  # the segment call (structured output)
        return _msg(json.dumps({"title": "Pandas basics", "libraries": [], "steps": [
            {"start": "0:05", "end": "1:00", "title": "Import pandas", "instructions": "Import pandas as pd."},
            {"start": "1:10", "end": "2:10", "title": "Read the CSV", "instructions": "Use read_csv."}]}), "claude-sonnet-5-5")
    return _msg(json.dumps({"checks": [{"type": "screen_contains", "app": "Code", "pattern": "pandas", "label": "x"}],
                            "hints": ["h"]}))


def _run_build(monkeypatch, goal, info=INFO):
    fake, seen = _fake_client(_lesson_reply)
    monkeypatch.setattr(claude, "client", lambda: fake)
    asyncio.run(claude.watch_transcript(copy.deepcopy(info), goal))
    return seen


def test_lesson_build_caches_the_transcript_and_the_per_step_prefix(monkeypatch):
    monkeypatch.setenv("LESSON_PROMPT_CACHE_USER", "1")
    seen = _run_build(monkeypatch, "learn pandas")
    seg, details = seen[0], seen[1:]
    assert len(details) == 2
    for kw in seen:
        _breakpoints_ok(kw)
        assert all("cache_control" in b for b in kw["system"])
    seg_blocks = seg["messages"][0]["content"]
    assert "cache_control" in seg_blocks[0] and "Transcript" in seg_blocks[0]["text"]  # the transcript is the cached part
    assert "learn pandas" in seg_blocks[1]["text"] and "cache_control" not in seg_blocks[1]  # the goal comes after it
    for kw in details:
        head, body = kw["messages"][0]["content"]
        assert "cache_control" in head and "cache_control" not in body
        assert "Learner's goal: learn pandas" in head["text"]
    # the two per-step calls of one build share their whole cached prefix; only the step text differs
    assert prompt_cache.prefix_through_breakpoint(details[0]) == prompt_cache.prefix_through_breakpoint(details[1])
    assert details[0]["messages"][0]["content"][1]["text"] != details[1]["messages"][0]["content"][1]["text"]


def test_segment_prefix_is_identical_for_two_goals_on_the_same_video(monkeypatch):
    monkeypatch.setenv("LESSON_PROMPT_CACHE_USER", "1")
    a = _run_build(monkeypatch, "learn pandas")[0]
    b = _run_build(monkeypatch, "get a job as a data analyst")[0]
    assert prompt_cache.prefix_through_breakpoint(a) == prompt_cache.prefix_through_breakpoint(b)
    assert a["messages"][0]["content"][1]["text"] != b["messages"][0]["content"][1]["text"]  # the goal is after it
    assert "id=" in a["messages"][0]["content"][0]["text"]  # the fences carry a content hash, not a random nonce


def test_the_cached_prefix_does_not_depend_on_the_system_schema_split(monkeypatch):
    """The detail calls share block 1 (the system prompt) with the segment call's system block."""
    monkeypatch.setenv("LESSON_PROMPT_CACHE_USER", "1")
    seen = _run_build(monkeypatch, "g")
    assert seen[0]["system"][0] == seen[1]["system"][0]


def test_judge_role_caches_its_system(monkeypatch):
    fake, seen = _fake_client(lambda kw: _msg('{"score": 0.5, "note": "n"}'))
    monkeypatch.setattr(claude, "client", lambda: fake)
    asyncio.run(claude._generate_json("You judge.", "p", {"type": "object", "properties": {}}, role="judge", escalate=False))
    assert seen[0]["system"] == [{"type": "text", "text": "You judge.", "cache_control": EPH}]
    assert seen[0]["model"] == models.model_for("lesson.judge")


def test_the_user_prefix_is_not_cached_by_default(monkeypatch):
    monkeypatch.delenv("LESSON_PROMPT_CACHE_USER", raising=False)
    seg = _run_build(monkeypatch, "g")[0]
    assert isinstance(seg["messages"][0]["content"], str) and "Transcript" in seg["messages"][0]["content"]


def test_coach_request_carries_cache_control_on_the_stable_system_and_the_prefix_is_stable():
    from server.coach import common, llm

    lesson = {"lesson": {"title": "T"}, "steps": [{"title": "s1", "instructions": "do it"}]}
    client, _ = _fake_client(lambda kw: _msg("{}"))
    sysb = common.system_blocks("INSTRUCTIONS " * 200, lesson)
    _, k1 = llm._request(client, "claude-sonnet-5-5", sysb, "I am stuck on line 3", {"type": "object"}, "low", 500)
    _, k2 = llm._request(client, "claude-sonnet-5-5", common.system_blocks("INSTRUCTIONS " * 200, lesson), "different question",
                         {"type": "object"}, "low", 500)
    _breakpoints_ok(k1)
    assert all("cache_control" in b for b in k1["system"])
    assert prompt_cache.prefix_through_breakpoint(k1) == prompt_cache.prefix_through_breakpoint(k2)
    assert k1["messages"] != k2["messages"]
    # a call that passed a bare system block still gets its breakpoint
    _, k3 = llm._request(client, "claude-haiku-5-5", [{"type": "text", "text": "SYS"}], "q", {"type": "object"}, "low", 100)
    assert k3["system"][-1]["cache_control"] == EPH


def test_screen_describe_prefix_is_stable_across_questions(monkeypatch):
    from server.screen import describe

    client, seen = _fake_client(lambda kw: _msg("answer", "claude-sonnet-5-5"))
    d = describe.Describer(min_interval=0)
    monkeypatch.setattr(d, "_get_client", lambda: client)
    for q, img in (("what is this?", b"jpeg1"), ("why red?", b"jpeg2")):
        asyncio.run(d._ask("claude-sonnet-5-5", describe.SYSTEM, img, q, effort="low", max_tokens=50, timeout=5))
    assert seen[0]["system"][0]["cache_control"] == EPH
    assert prompt_cache.prefix_through_breakpoint(seen[0]) == prompt_cache.prefix_through_breakpoint(seen[1])


def test_scaffold_caches_system_and_the_lesson_prompt(monkeypatch):
    from server.workspace import scaffold

    reply = json.dumps({"files": [], "git": {"init": False, "default_branch": "", "ops": []}, "open_file": "", "setup": [],
                        "kind": "code", "stack": "python", "notes": ""})
    seen: list[dict] = []

    def create(**kw):  # the scaffold's client is the sync one
        seen.append(kw)
        return _msg(reply, "claude-sonnet-5-5")

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    first = [{"role": "user", "content": "LESSON JSON " * 50}]
    for msgs in (first, [*first, {"role": "assistant", "content": "{}"}, {"role": "user", "content": "fix the leaks"}]):
        with contextlib.suppress(Exception):  # the canned reply need not validate; the requests are what is checked
            scaffold._ask(client, msgs)
    assert len(seen) == 2
    for kw in seen:
        _breakpoints_ok(kw)
        assert kw["system"][0]["cache_control"] == EPH
    assert prompt_cache.prefix_through_breakpoint(seen[0]) == prompt_cache.prefix_through_breakpoint(seen[1])
    assert seen[1]["model"] == models.model_for("workspace.scaffold")


def test_diagrams_cache_the_drawing_rules_and_vary_only_the_step(monkeypatch):
    import importlib

    build = importlib.import_module("server.diagrams.build")

    def refuse(kw):
        r = _msg("{}", "claude-sonnet-5-5")
        r.stop_reason = "refusal"
        return r

    client, seen = _fake_client(refuse)
    for title in ("Load the CSV", "Plot it"):
        with pytest.raises(build.DiagramError):
            asyncio.run(build._call(client, {"id": title, "title": title, "instructions": "x"}, {"lesson": {"title": "L"}}))
    assert seen[0]["system"] == [{"type": "text", "text": build.SYSTEM, "cache_control": EPH}]
    assert prompt_cache.prefix_through_breakpoint(seen[0]) == prompt_cache.prefix_through_breakpoint(seen[1])
    assert seen[0]["messages"] != seen[1]["messages"] and seen[0]["model"] == models.model_for("diagrams")


# ------------------------------------------------------------------------------------- (c) cost accounting

def test_cache_write_and_read_tokens_are_recorded_and_priced(caplog):
    c = cost.start()
    with caplog.at_level(logging.INFO, logger="server.lesson.cost"):
        d = cost.record_usage("claude-sonnet-5-5", _usage(inp=1000, out=500, cr=20_000, cw=5_000), label="claude segment")
    expect = (1000 * 2.00 + 500 * 10.00 + 20_000 * 0.10 + 5_000 * 2.00 * cost.CACHE_WRITE_X) / 1e6
    assert d == pytest.approx(expect) and cost.CACHE_WRITE_X == 1.25
    t = c["tokens"]["claude-sonnet-5-5"]
    assert (t["input"], t["output"], t["cache_read"], t["cache_write"]) == (1000, 500, 20_000, 5_000)
    assert c["cache_hit_rate"] == pytest.approx(20_000 / 26_000, abs=1e-3)
    line = next(r.message for r in caplog.records if "claude segment call" in r.message)
    for part in ("model=claude-sonnet-5-5", "in=1000", "out=500", "cache_read=20000", "cache_write=5000"):
        assert part in line
    # reads save 0.9x input each; writes cost 0.25x extra
    assert c["cache_saved_usd"] == pytest.approx((20_000 * (2.00 - 0.10) - 5_000 * 2.00 * 0.25) / 1e6)
    assert cost.session()["cache_saved_usd"] == pytest.approx(c["cache_saved_usd"])


def test_a_write_with_no_reads_costs_more_than_not_caching():
    assert cost.usd("claude-haiku-5-5", 0, 0, 0, 4000) == pytest.approx(cost.usd("claude-haiku-5-5", 4000) * 1.25)
    assert cost.cache_saved_usd("claude-haiku-5-5", 0, 4000) < 0


def test_build_cost_event_carries_the_cache_savings():
    got = []
    cost.register_event_handler(lambda n, p: got.append((n, p)))
    c = cost.start()
    cost.record_usage("claude-haiku-5-5", _usage(cr=3000))
    props = cost.finish_build(c, kind="video")
    assert props["cache_saved_usd"] > 0 and got[0][1]["cache_saved_usd"] == props["cache_saved_usd"]


# ------------------------------------------------------------------------------------- the estimator

def test_estimator_after_is_cheaper_wherever_a_prefix_is_read_again():
    rows = est.scenarios()
    for name in ("build + rebuild (same video, in TTL)", "build + rebuild (same video, in TTL) [transcript cache on]",
                 "coach session (after the build)"):
        assert rows[name]["after"] < rows[name]["before"], name
    cold = rows["cold build"]  # the default: only the system prompts are cached, so a cold build costs about the same
    assert cold["after"] <= cold["before"] * 1.03
    assert rows["cold build [transcript cache on]"]["after"] <= cold["before"] * 1.25  # it only pays the 1.25x writes
    assert "$" in est.report()


def test_estimator_uses_the_price_table_and_skips_prefixes_under_the_minimum():
    p = est.load()
    seg = p["segment"]
    before = est.stage_cost(p, seg, caching=False)
    assert before == pytest.approx(cost.usd(seg["before"], seg["system"] + seg["shared"] + seg["own"], seg["output"]))
    tiny = dict(p["judge"])  # 300 + 1200 tokens: under Haiku's minimum, so caching changes nothing
    assert est.stage_cost(p, tiny, caching=True) == pytest.approx(est.stage_cost(p, tiny, caching=False))


# ------------------------------------------------------------------------------- per-site prefix cache flags

def test_prefix_cache_is_off_for_every_lesson_site_by_default(monkeypatch):
    for k in ("LESSON_PROMPT_CACHE_USER", "MIYAGI_CACHE_PREFIX_LESSON_SEGMENT", "MIYAGI_CACHE_PREFIX_LESSON_DETAIL",
              "MIYAGI_CACHE_PREFIX_LESSON_TEXT_STEP"):
        monkeypatch.delenv(k, raising=False)
    assert set(models.PREFIX_CACHE) >= {"lesson.segment", "lesson.detail", "lesson.text_step"}
    assert not any(models.cache_prefix(s) for s in models.PREFIX_CACHE)
    assert models.cache_prefix("some.unknown_site") is False


def test_one_site_can_be_flipped_without_the_others(monkeypatch):
    monkeypatch.delenv("LESSON_PROMPT_CACHE_USER", raising=False)
    monkeypatch.setenv("MIYAGI_CACHE_PREFIX_LESSON_DETAIL", "1")
    assert models.cache_prefix("lesson.detail") and not models.cache_prefix("lesson.segment")
    seen = _run_build(monkeypatch, "g")
    seg, det = seen[0], seen[1]
    assert isinstance(seg["messages"][0]["content"], str)  # segment: plain string
    assert "cache_control" in det["messages"][0]["content"][0]  # detail: cached head


def test_the_site_flag_beats_the_older_lesson_switch(monkeypatch):
    monkeypatch.setenv("LESSON_PROMPT_CACHE_USER", "1")
    monkeypatch.setenv("MIYAGI_CACHE_PREFIX_LESSON_SEGMENT", "0")
    assert not models.cache_prefix("lesson.segment") and models.cache_prefix("lesson.detail")
