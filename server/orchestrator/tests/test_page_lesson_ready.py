"""Any link (ANY-LINK.md): a lesson built from a page goes out in lesson.ready with lesson.origin and each step's pageRef,
through the strict (contract-validating) hub. Offline: the page lesson is built with the deterministic fake model."""

from __future__ import annotations

import asyncio

from server.lesson.pagelesson import build_page_lesson
from server.lesson.tests.test_pagelesson import LESSONS, fake, greet_page  # noqa: F401 (fixture)
from server.orchestrator.tests.test_session import Rig


def test_lesson_ready_carries_origin_and_page_refs(fake, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    fake["lesson"] = LESSONS["greet-cli"]
    g = asyncio.run(build_page_lesson(greet_page(), str(tmp_path / "work")))
    rig = Rig(tmp_path)

    async def go():
        await rig.s.load_graph(g)
        await rig.settle()

    asyncio.run(go())
    ready = rig.of("lesson.ready")[-1]
    les = ready["lesson"]
    assert les["mode"] == "lesson" and les["origin"]["kind"] == "github"
    assert les["origin"]["site"] == "github.com/example/greet-cli" and les["origin"]["author"] == "Example Org"
    assert les["sources"][0]["kind"] == "repo" and les["sources"][0]["meta"] == "github.com/example/greet-cli"
    refs = [s.get("pageRef") for s in ready["steps"]]
    assert refs[0] == {"url": "https://github.com/Example/Greet-CLI.git#your-first-greeting", "heading": "Your first greeting"}
    assert all(r and r["url"].startswith("https://github.com/") for r in refs)
    assert all("video" not in s for s in ready["steps"])
