"""Roadmap 3.3 / 3.4 / 3.8: dollars per model, per build and per session, the cost event hook, prompt
caching on lesson + screen calls, and no Opus / no Pro defaults. Fake clients only: nothing reaches an API."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from server.lesson import claude, cost, gemini


@pytest.fixture(autouse=True)
def _fresh_tallies(monkeypatch):
    monkeypatch.setattr(cost, "_session", cost._fresh())
    monkeypatch.setattr(cost, "_handlers", [])
    monkeypatch.delenv("MIYAGI_PRICES_JSON", raising=False)
    cost._counter.set(None)
    yield
    cost._counter.set(None)


def _events():
    got: list[tuple[str, dict]] = []
    cost.register_event_handler(lambda n, p: got.append((n, p)))
    return got


# ---- price table ----------------------------------------------------------------------------------

def test_price_table_rows_family_and_override(monkeypatch):
    assert cost.price("claude-sonnet-5-5") == (2.00, 10.00, 0.10)
    assert cost.price("claude-haiku-5-5") == (0.10, 0.50, 0.01)
    assert cost.price("claude-opus-5-5")[0] == 4.00
    assert cost.price("claude-haiku-5-5-20261001") == cost.price("claude-haiku-5-5")  # a dated id: its base row
    assert cost.price("gemini-3.7-flash") == cost.price("gemini-3.8-flash")  # fallback flashes: the flash family
    assert cost.price("gemini-3.1-flash-lite")[0] < cost.price("gemini-3.8-flash")[0]
    assert cost.price("something-new") == cost.DEFAULT_PRICE
    monkeypatch.setenv("MIYAGI_PRICES_JSON", '{"claude-haiku-5-5": [1, 2]}')
    assert cost.price("claude-haiku-5-5") == (1.0, 2.0, 0.1)
    monkeypatch.setenv("MIYAGI_PRICES_JSON", "not json")
    assert cost.price("claude-haiku-5-5") == (0.10, 0.50, 0.01)  # a bad override is ignored


def test_usd_counts_cache_reads_cheap_and_writes_at_a_premium():
    # 1M uncached in at $2 + 1M out at $10 + 1M cache reads at $0.10 + 1M cache writes at 1.25 x $2
    assert cost.usd("claude-sonnet-5-5", 1_000_000, 1_000_000, 1_000_000, 1_000_000) == pytest.approx(2 + 10 + 0.10 + 2.5)
    assert cost.usd("claude-haiku-5-5", 0, 0) == 0
    assert cost.hit_rate(100, 900, 0) == 0.9 and cost.hit_rate(0, 0, 0) is None


# ---- per build --------------------------------------------------------------------------------------

def test_token_usage_and_dollars_per_model_in_the_build_counter():
    c = cost.start()
    cost.add_tokens("claude-haiku-5-5", 1200, 300)
    cost.add_tokens("claude-haiku-5-5", 800, 200)
    t = c["tokens"]["claude-haiku-5-5"]
    assert (t["input"], t["output"], t["calls"]) == (2000, 500, 2)
    assert t["usd"] == pytest.approx(cost.usd("claude-haiku-5-5", 2000, 500))
    assert c["cost_usd"] == pytest.approx(t["usd"])
    assert "cache_read" not in t and "cache_hit_rate" not in c  # nothing reported cache fields


def test_record_usage_reads_anthropic_cache_fields_and_logs_the_hit_rate(caplog):
    c = cost.start()
    u = SimpleNamespace(input_tokens=100, output_tokens=50, cache_read_input_tokens=900, cache_creation_input_tokens=0)
    with caplog.at_level("INFO", logger="server.lesson.cost"):
        d = cost.record_usage("claude-sonnet-5-5", u, label="claude")
    assert d == pytest.approx(cost.usd("claude-sonnet-5-5", 100, 50, 900, 0))
    assert c["tokens"]["claude-sonnet-5-5"]["cache_read"] == 900 and c["cache_hit_rate"] == 0.9
    assert "hit=90%" in caplog.text
    cost.record_usage("claude-sonnet-5-5", {"input_tokens": 0, "output_tokens": 1, "cache_creation_input_tokens": 1000})
    assert c["tokens"]["claude-sonnet-5-5"]["cache_write"] == 1000 and c["cache_hit_rate"] == pytest.approx(900 / 2000)


def test_finish_build_emits_build_cost():
    got = _events()
    c = cost.start()
    cost.add_tokens("gemini-3.8-flash", 10_000, 1_000)
    props = cost.finish_build(c, kind="video", lesson_id="abc")
    assert got == [("build_cost", props)]
    assert props["cost_usd"] == pytest.approx(cost.usd("gemini-3.8-flash", 10_000, 1_000), abs=1e-6)
    assert props["lesson_id"] == "abc" and props["kind"] == "video"
    assert cost.finish_build(None) is None


# ---- event hook ----------------------------------------------------------------------------------------

def test_emit_event_is_a_noop_without_handlers_and_survives_a_bad_one():
    cost.emit_event("anything", {"a": 1})  # nothing registered: nothing happens, nothing raises
    got = []

    def bad(name, props):
        raise RuntimeError("telemetry down")
    cost.register_event_handler(bad)
    off = cost.register_event_handler(lambda n, p: got.append(n))
    cost.emit_event("x", {})
    assert got == ["x"]
    off()
    cost.emit_event("y", {})
    assert got == ["x"]


# ---- per session --------------------------------------------------------------------------------------

def test_session_tally_covers_builds_coach_and_screen_then_resets():
    got = _events()
    cost.start()
    cost.add_tokens("gemini-3.8-flash", 1000, 100)  # the build, before the lesson loads
    cost._counter.set(None)  # coach / screen calls run outside any build
    cost.session_start("lesson-1")
    cost.record_usage("claude-sonnet-5-5", {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 990},
                      source="coach")
    cost.record_usage("claude-haiku-5-5", {"input_tokens": 500, "output_tokens": 20}, source="screen")
    assert cost.session()["lesson_id"] == "lesson-1"
    props = cost.session_end("completed")
    assert got[-1] == ("session_cost", props)
    assert props["lesson_id"] == "lesson-1" and props["reason"] == "completed" and props["calls"] == 3
    assert set(props["by_source"]) == {"lesson", "coach", "screen"}
    assert props["cost_usd"] == pytest.approx(sum(props["by_model"].values()), abs=1e-6)
    assert props["cache_hit_rate"] == pytest.approx(990 / (1000 + 10 + 990 + 500))
    assert cost.session()["cost_usd"] == 0.0 and cost.session()["lesson_id"] is None  # a fresh tally


def test_orchestrator_hooks_start_and_end_the_session_tally():
    from server.orchestrator import session as sess

    got = _events()
    sess._session_cost_start({"lesson": {"id": "L9"}})
    cost.add_tokens("claude-haiku-5-5", 100, 10, source="coach")
    sess._session_cost_end("end_lesson")
    assert got and got[-1][0] == "session_cost" and got[-1][1]["lesson_id"] == "L9"


# ---- gemini ------------------------------------------------------------------------------------------

def test_gemini_usage_splits_implicit_cache_hits():
    c = cost.start()
    um = SimpleNamespace(prompt_token_count=10_000, cached_content_token_count=4_000, candidates_token_count=500,
                         thoughts_token_count=100)
    gemini.record_usage("gemini-3.8-flash", um)
    t = c["tokens"]["gemini-3.8-flash"]
    assert (t["input"], t["cache_read"], t["output"]) == (6_000, 4_000, 600) and c["cache_hit_rate"] == 0.4
    gemini.record_usage("gemini-3.8-flash", None)  # no usage metadata: a zero-token call, no crash


def test_gemini_fast_and_fallback_models_are_flash(monkeypatch):
    # The video pass DEFAULT_MODEL is Michael's call (see app/agents/eng-cost.md), so it is not pinned here.
    monkeypatch.delenv("LESSON_MODEL", raising=False)
    monkeypatch.delenv("LESSON_FAST_MODEL", raising=False)
    monkeypatch.delenv("LESSON_FALLBACK_MODELS", raising=False)
    monkeypatch.setenv("LESSON_NO_DOTENV", "1")
    assert gemini.model() == gemini.DEFAULT_MODEL
    assert "flash" in gemini.model(fast=True)
    assert all("flash" in m for m in gemini.fallback_models())
    assert cost.price(gemini.DEFAULT_MODEL) != cost.DEFAULT_PRICE  # whatever the default is, it has a price row


# ---- no Opus by default ------------------------------------------------------------------------------

def test_no_opus_defaults_anywhere(monkeypatch):
    for k in ("TUT_SCREEN_COACH_MODEL", "MIYAGI_ALLOW_OPUS", "LESSON_ALLOW_OPUS", "LESSON_CLAUDE_MODEL",
              "LESSON_CLAUDE_MODEL_ESCALATE"):
        monkeypatch.delenv(k, raising=False)
    from server.coach import llm
    from server.screen import describe

    assert "opus" not in describe.COACH_MODEL and "opus" not in describe.QUICK_MODEL
    for purpose in ("diagnose", "triage", "explain", "do_it_for_me", "locate", "hints"):
        monkeypatch.delenv(f"COACH_MODEL_{purpose.upper()}", raising=False)
        assert "opus" not in llm.model_for(purpose)
    assert all("opus" not in m for m in claude.ROLE_MODELS.values())
    assert "opus" not in claude.model() and "opus" not in claude.escalation_model()


# ---- prompt caching: lesson build --------------------------------------------------------------------

class _FakeStream:
    def __init__(self, msg):
        self.msg = msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get_final_message(self):
        return self.msg


class _FakeMessages:
    def __init__(self, msg, seen):
        self.msg, self.seen = msg, seen

    def stream(self, **kw):
        self.seen.append(kw)
        return _FakeStream(self.msg)


def _fake_anthropic(monkeypatch, text='{"ok": true}', usage=None):
    seen: list[dict] = []
    usage = usage or SimpleNamespace(input_tokens=40, output_tokens=10, cache_read_input_tokens=600,
                                     cache_creation_input_tokens=0)
    msg = SimpleNamespace(model="claude-haiku-5-5", usage=usage, stop_reason="end_turn",
                          content=[SimpleNamespace(type="text", text=text)])
    api = _FakeMessages(msg, seen)
    fake = SimpleNamespace(messages=api, beta=SimpleNamespace(messages=api))
    monkeypatch.setattr(claude, "client", lambda: fake)
    return seen


def test_lesson_claude_calls_cache_the_system_prompt_and_record_dollars(monkeypatch):
    seen = _fake_anthropic(monkeypatch)
    c = cost.start()
    asyncio.run(claude._call("claude-haiku-5-5", "You build lessons.", "the prompt", effort="low", schema=None))
    sysb = seen[0]["system"]
    assert sysb == [{"type": "text", "text": "You build lessons.", "cache_control": {"type": "ephemeral"}}]
    assert c["claude_calls"] == 1 and c["tokens"]["claude-haiku-5-5"]["cache_read"] == 600
    assert c["cost_usd"] > 0 and c["cache_hit_rate"] == pytest.approx(600 / 640)


def test_prompt_described_json_puts_the_schema_in_the_cached_system_block(monkeypatch):
    seen = _fake_anthropic(monkeypatch)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    out = asyncio.run(claude._generate_json_on("claude-haiku-5-5", "SYS", "step 3 slice", schema, effort="low",
                                               structured=False))
    assert out == {"ok": True}
    block = seen[0]["system"][0]
    assert block["text"].startswith("SYS") and '"required": ["ok"]' in block["text"] and "cache_control" in block
    assert seen[0]["messages"][0]["content"] == "step 3 slice"  # the varying part stays after the cached prefix


# ---- prompt caching: screen describe -----------------------------------------------------------------

def test_screen_describe_caches_its_system_prompt_and_records_dollars(monkeypatch):
    from server.screen import describe

    seen: list[dict] = []

    class _Msgs:
        async def create(self, **kw):
            seen.append(kw)
            return SimpleNamespace(model="claude-haiku-5-5", stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text="3")],
                                   usage=SimpleNamespace(input_tokens=1500, output_tokens=2,
                                                         cache_read_input_tokens=0, cache_creation_input_tokens=0))

    class _Client:
        messages = _Msgs()
        beta = SimpleNamespace(messages=_Msgs())

        def with_options(self, **kw):
            return self

    d = describe.Describer(min_interval=0)
    monkeypatch.setattr(d, "_get_client", lambda: _Client())
    out = asyncio.run(d._ask("claude-haiku-5-5", describe.WHERE_SYSTEM, b"jpeg", "where?", effort="low",
                             max_tokens=20, timeout=5))
    assert out == "3"
    assert seen[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    s = cost.session()
    assert s["by_source"]["screen"] == pytest.approx(cost.usd("claude-haiku-5-5", 1500, 2))


# ---- review round 1: every billed call counts, failed / cancelled builds, prebuild source, overrides ---------

def test_price_override_keys_are_case_insensitive(monkeypatch):
    monkeypatch.setenv("MIYAGI_PRICES_JSON", '{"Claude-Haiku-5-5": [1, 2, 0.5]}')
    assert cost.price("claude-haiku-5-5") == (1.0, 2.0, 0.5)
    assert cost.price("CLAUDE-HAIKU-5-5") == (1.0, 2.0, 0.5)
    monkeypatch.delenv("MIYAGI_PRICES_JSON")
    assert cost.price("claude-haiku-5-5") == (0.10, 0.50, 0.01)


def test_a_failed_build_emits_build_cost_and_its_spend_is_tagged():
    got = _events()
    c = cost.start()
    with pytest.raises(RuntimeError):
        with cost.build_scope(c, kind="video"):
            cost.add_tokens("gemini-3.8-flash", 10_000, 1_000)
            raise RuntimeError("build failed")
    (name, props), = got
    assert name == "build_cost" and props["outcome"] == "failed" and props["kind"] == "video"
    assert props["cost_usd"] == pytest.approx(cost.usd("gemini-3.8-flash", 10_000, 1_000), abs=1e-6)
    s = cost.session()
    assert s["by_source"].get("lesson", 0) == 0 and s["by_source"]["lesson_failed"] == pytest.approx(props["cost_usd"])
    assert s["cost_usd"] == pytest.approx(props["cost_usd"])  # it was paid: still in the session total


def test_a_build_with_no_calls_emits_nothing():
    got = _events()
    with cost.build_scope(cost.start(), kind="video") as scope:
        scope["lesson_id"] = "cached"
    assert got == []


def test_a_cancelled_prebuild_emits_build_cost_with_its_own_source(monkeypatch, tmp_path):
    from server.lesson import builder

    got = _events()

    async def impl(*a, **kw):
        cost.add_tokens("gemini-3.8-flash", 5_000, 500)  # the build counter's source tags it
        await asyncio.sleep(10)

    async def main():
        cost.start("prebuild")  # prebuild.Job.run does this before build_lesson(_prebuild=True)
        t = asyncio.ensure_future(builder.build_lesson("https://www.youtube.com/watch?v=abcdefghijk", "g",
                                                       str(tmp_path), _prebuild=True))
        await asyncio.sleep(0.05)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    monkeypatch.setattr(builder, "_build_lesson_impl", impl)
    asyncio.run(main())
    (name, props), = got
    assert props["kind"] == "prebuild" and props["outcome"] == "cancelled" and props["cost_usd"] > 0
    assert cost.session()["by_source"] == {"prebuild": 0.0, "prebuild_cancelled": props["cost_usd"]}


def test_a_video_build_emits_once_with_the_lesson_id(monkeypatch, tmp_path):
    from server.lesson import builder

    got = _events()

    async def impl(*a, **kw):
        cost.add_tokens("gemini-3.8-flash", 1_000, 100)
        return {"lesson": {"id": "L1"}, "steps": []}

    monkeypatch.setattr(builder, "_build_lesson_impl", impl)
    g = asyncio.run(builder.build_lesson("not-a-video", "g", str(tmp_path)))
    assert [n for n, _ in got] == ["build_cost"]
    assert got[0][1]["outcome"] == "ok" and got[0][1]["lesson_id"] == "L1"
    assert g["build"]["cost"]["cost_usd"] == got[0][1]["cost_usd"]
    assert cost.session()["by_source"] == {"lesson": got[0][1]["cost_usd"]}


def test_coach_structured_call_counts_a_refused_or_cut_off_call(monkeypatch):
    from server.coach import llm

    monkeypatch.setattr(llm, "offline_mode", lambda: False)
    monkeypatch.setattr(llm, "has_credentials", lambda: True)
    for stop in ("refusal", "max_tokens"):
        class _Api:
            async def create(self, **kw):
                return SimpleNamespace(stop_reason=stop, model="claude-haiku-5-5", content=[],
                                       usage=SimpleNamespace(input_tokens=1000, output_tokens=400,
                                                             cache_read_input_tokens=0, cache_creation_input_tokens=0))

        fake = SimpleNamespace(messages=_Api(), beta=SimpleNamespace(messages=_Api()))
        fake.with_options = lambda **_: fake
        monkeypatch.setattr(llm, "get_client", lambda: fake)
        with pytest.raises(llm.CoachLLMError):
            asyncio.run(llm.structured_call(purpose="explain", model="claude-haiku-5-5", system=[], user_text="q",
                                            schema={"type": "object"}))
    assert cost.session()["by_source"]["coach"] == pytest.approx(2 * cost.usd("claude-haiku-5-5", 1000, 400))


def test_scene_look_uses_the_shared_price_table_and_counts_in_the_session():
    from PIL import Image

    from server.coach import scene

    class _Msgs:
        async def create(self, **kw):
            return SimpleNamespace(model="claude-haiku-5-5", stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text="{}")],
                                   usage=SimpleNamespace(input_tokens=2300, output_tokens=100))

    assert not hasattr(scene, "PRICE_IN")  # one price table: server/lesson/cost.py
    sc = asyncio.run(scene.look(Image.new("RGB", (64, 64)), {"id": "s1", "title": "t"},
                                client=SimpleNamespace(messages=_Msgs())))
    assert sc.cost_usd == pytest.approx(cost.usd("claude-haiku-5-5", 2300, 100))
    assert cost.session()["by_source"]["coach"] == pytest.approx(sc.cost_usd)


def test_diagram_calls_count_in_the_session_even_when_refused():
    import importlib

    build = importlib.import_module("server.diagrams.build")  # the package exports a build() that shadows it
    resp = SimpleNamespace(model="claude-sonnet-5-5", stop_reason="refusal",
                           usage=SimpleNamespace(input_tokens=3000, output_tokens=200))
    build._record_cost(resp, "claude-sonnet-5-5")
    assert cost.session()["by_source"]["diagrams"] == pytest.approx(cost.usd("claude-sonnet-5-5", 3000, 200))


def test_finder_gemini_answers_count_in_the_session():
    from server.finder import gemini as fg

    um = SimpleNamespace(prompt_token_count=2000, candidates_token_count=100)
    fg._record_cost("gemini-3.8-flash", SimpleNamespace(usage_metadata=um))
    assert cost.session()["by_source"]["finder"] == pytest.approx(cost.usd("gemini-3.8-flash", 2000, 100))


def test_web_searches_are_billed_on_top_of_tokens():
    u = {"input_tokens": 1000, "output_tokens": 100, "server_tool_use": {"web_search_requests": 3}}
    d = cost.record_usage("claude-sonnet-5-5", u, source="finder")
    assert d == pytest.approx(cost.usd("claude-sonnet-5-5", 1000, 100) + 3 * cost.WEB_SEARCH_USD)
    u2 = SimpleNamespace(input_tokens=10, output_tokens=1, server_tool_use=SimpleNamespace(web_search_requests=None))
    assert cost.record_usage("claude-haiku-5-5", u2) == pytest.approx(cost.usd("claude-haiku-5-5", 10, 1))
