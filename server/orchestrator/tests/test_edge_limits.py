"""Edge limits: over-long pasted text is clipped where the engine consumes it, and a build that hangs hits its
overall deadline and reports the existing build-failed path. Offline."""

from __future__ import annotations

import asyncio
import types

from server import textclip
from server.orchestrator.modules import Modules
from server.orchestrator.tests.test_session import Rig, rig, run  # noqa: F401 - rig is a fixture


def test_clip_text_short_and_none_unchanged():
    assert textclip.clip_text(None, 10) is None
    assert textclip.clip_text("hello", 10) == "hello"
    assert textclip.clip_text("x" * 10, 10) == "x" * 10


def test_clip_topic_cuts_at_a_word_boundary_and_logs(caplog):
    text = " ".join(["learn"] * 400)  # 2399 chars
    with caplog.at_level("WARNING", logger="server.textclip"):
        out = textclip.clip_topic(text)
    assert len(out) <= textclip.MAX_TOPIC_CHARS and out.split() == ["learn"] * len(out.split())
    assert not out.endswith(" ") and any("clipped topic" in r.message for r in caplog.records)
    assert textclip.clip_topic("y" * 900) == "y" * 500  # no spaces at all: a hard cut


def test_clip_ask_limit():
    assert len(textclip.clip_ask("a" * 9000)) == textclip.MAX_ASK_CHARS
    assert textclip.clip_ask("short") == "short" and textclip.clip_ask(None) is None


def test_search_uses_the_clipped_topic(rig):  # noqa: F811
    seen: list[str] = []

    async def search(q):
        seen.append(q)
        return
        yield  # an async generator

    mods = Modules(demo=False, force_stubs="")
    mods.real["finder"] = types.SimpleNamespace(search=search)
    r = Rig(rig.workdir, mods)
    essay = " ".join(f"word{i}" for i in range(5000))
    run(r.s.learn(essay))
    assert len(seen) == 1 and len(seen[0]) <= textclip.MAX_TOPIC_CHARS and essay.startswith(seen[0])
    assert r.s.query == seen[0]


def test_ask_text_is_clipped_before_the_engine_sees_it(rig, monkeypatch):  # noqa: F811
    import server.orchestrator.session as sess

    got: list[str | None] = []
    monkeypatch.setattr(sess.context_memory, "on_action", lambda s, kind, text: got.append(text))

    async def go():
        try:
            await rig.s.action("ask", "q" * 20000)
        except Exception:  # noqa: BLE001 - no lesson: only the clip matters here
            pass

    run(go())
    assert got and len(got[0]) == textclip.MAX_ASK_CHARS


def test_build_deadline_triggers_the_failure_path(rig, monkeypatch):  # noqa: F811
    monkeypatch.setenv("MIYAGI_BUILD_DEADLINE_S", "0.2")

    async def hang(goal, workdir, **kw):
        await asyncio.sleep(3600)

    mods = Modules(demo=False, force_stubs="")
    mods.real["lesson"] = types.SimpleNamespace(build_text_lesson=hang)
    r = Rig(rig.workdir, mods)

    async def go():
        await asyncio.wait_for(r.s.learn("teach me an obscure topic xyzzy", "lesson"), 10)
        await r.built()

    run(go())
    failed = [p for p in r.of("lesson.building") if p.get("failed")]
    assert failed, r.types()
    assert failed[-1]["failCode"] == "too_long" and "too long" in failed[-1]["message"]
    assert r.s.phase == "idle"
