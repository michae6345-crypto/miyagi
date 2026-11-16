"""The presenter keys, hammered on a PRIVATE engine (server/tests/demo_rehearsal.py's): ~30 s.

    python -m pytest server/tests/test_presenter_keys.py -q

Adrian's app binds ⌃⌥⌘→ / ⌃⌥⌘← / ⌃⌥⌘R to POST /stage/next | back | restart while GET /stage says a Demo lesson is on
(app/src/main/features/presenter.ts: it re-asks on every lesson.ready and lets the keys go on lesson.ended; it ignores
the reply). This presses them many times in a row, the way a nervous presenter does, and checks /state and /stage
after every press:

  - no Demo lesson: every key answers ok false, nothing happens
  - next moves exactly one step (also from the "Before you start" sheet, also a double press, also on a run step,
    which gets its recorded run that learns: no "Not yet"); back moves exactly one step back and nothing passes on
    its own; back on step 1 stays there
  - restart: a fresh take (step 1, nn.py back to the clean starter, no runs), twice in a row, as a double press, and
    after the lesson is complete; a Demo started again after End is fresh too and its keys work
  - next through to the end: the completion card; next after that does nothing
  - the lesson folder is in the test's temp folder (never ~/miyagi/lessons), nothing touched the screen (no AX or
    Quartz event), no error event, no Traceback / ERROR in the engine log

Skips like test_demo_rehearsal (missing dependency, MIYAGI_SKIP_REHEARSAL); marker demo_rehearsal.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from server.tests import demo_rehearsal as dr

pytestmark = pytest.mark.demo_rehearsal
STEPS = ("nn1", "nn2", "nn3", "nn4", "nn5", "nn6")
SETTLE_S = 1.2  # > a fast pass (0.2 s + 0.1 s a row) + the advance delay (0.4 s): a second move would have shown


class Keys:
    def __init__(self, port: int, base: Path, client, app: dr.App):
        self.http, self.base, self.c, self.app = f"http://127.0.0.1:{port}", base, client, app
        self.workdir: Path | None = None

    async def get(self, path: str) -> dict:
        return (await self.c.get(self.http + path, timeout=5)).json()

    async def post(self, path: str) -> dict:
        return (await self.c.post(self.http + path, timeout=15)).json()

    async def where(self) -> tuple[str | None, str | None, dict]:
        """(/state's phase, its stepId, /stage), checking /state and /stage agree on the step."""
        st, sg = await self.get("/state"), await self.get("/stage")
        assert st.get("stepId") == sg.get("step"), f"/state on {st.get('stepId')} but /stage on {sg}"
        return st.get("phase"), st.get("stepId"), sg

    def moves(self, mark: int) -> list[tuple[str, str]]:
        return [(e.type, e.p.get("stepId")) for e in self.app.since(mark) if e.type in ("step.started", "step.passed")]

    def errors(self, mark: int) -> list[dict]:
        return [e.p for e in self.app.since(mark, "error")]

    async def press(self, cmd: str, frm: str, to: str, double: bool = False) -> None:
        """One key press (two at once: double) that must take the lesson from step `frm` to step `to`, exactly once."""
        _, step, _ = await self.where()
        assert step == frm, f"before {cmd}: on {step}, want {frm}"
        m = self.app.mark()
        replies = await asyncio.gather(*[self.post(f"/stage/{cmd}") for _ in range(2 if double else 1)])
        assert replies[0].get("ok") is True, f"{cmd} on {frm} -> {replies}"
        await self.app.wait("step.started", lambda p: p.get("stepId") == to, since=m, timeout=6,
                            what=f"{cmd} {frm} -> {to}")
        await asyncio.sleep(SETTLE_S)
        phase, step, sg = await self.where()
        assert step == to and sg.get("on"), f"after {cmd} on {frm}: {step} {sg} (want {to})"
        assert phase == "active", f"after {cmd} on {frm}: phase {phase}"
        moves = self.moves(m)
        if cmd == "next":
            assert moves == [("step.passed", frm), ("step.started", to)], f"next {frm}{' x2' if double else ''}: {moves}"
            passed = self.app.find(m, "step.passed")
            assert passed.p.get("nextStepId") == to and not passed.p.get("skipped") and not passed.p.get("already"), \
                passed.p
            assert not self.app.find(m, "offtrack"), f"a Not yet on next {frm}"
        else:
            assert moves == [("step.started", to)], f"{cmd} {frm}: {moves} (nothing may pass on its own)"
        assert not self.errors(m), self.errors(m)

    async def fresh_take(self, m: int, why: str) -> None:
        """A restart / Demo start: lesson.ready -> step 1, nn.py the clean starter, no runs, nothing passed."""
        await self.app.wait("lesson.ready", since=m, timeout=8, what=f"lesson.ready ({why})")
        await self.app.wait("step.started", lambda p: p.get("stepId") == "nn1", since=m, timeout=4,
                            what=f"step 1 ({why})")
        await asyncio.sleep(0.8)
        phase, step, sg = await self.where()
        assert step == "nn1" and sg.get("on") and not sg.get("runs"), f"{why}: {step} {sg}"
        assert phase == "ready", f"{why}: phase {phase} (the Before you start sheet)"
        wd = Path((await self.get("/state")).get("workdir") or "").resolve()
        assert wd.is_relative_to((self.base / "lessons").resolve()), f"{why}: lesson folder {wd} isn't in the temp dir"
        assert (wd / "nn.py").read_text(encoding="utf-8") == dr.starter(), f"{why}: nn.py isn't the clean starter"
        moves = self.moves(m)
        assert not [mv for mv in moves if mv[0] == "step.passed"], f"{why}: {moves}"
        assert [mv for mv in moves if mv[0] == "step.started"] == [("step.started", "nn1")], f"{why}: {moves}"
        assert not self.errors(m), self.errors(m)
        self.workdir = wd

    async def all_off(self, why: str) -> None:
        for cmd in ("next", "back", "restart"):
            r = await self.post(f"/stage/{cmd}")
            assert r.get("ok") is False and "no Demo lesson" in str(r.get("error")), f"{why}: {cmd} -> {r}"
        assert not (await self.get("/stage")).get("on")


async def presenter(port: int, base: Path) -> None:
    import httpx

    comp = dr.FakeCompanion()
    comp.start()
    eng = dr.PrivateEngine(port, dr.engine_env(port, base, comp.port), base / "engine.log")
    app = dr.App(port)
    t_wall = time.time()
    try:
        await eng.start()
        async with httpx.AsyncClient(trust_env=False) as c:
            k = Keys(port, base, c, app)
            await app.connect()
            start = app.mark()

            # no lesson: the keys do nothing
            await k.all_off("no lesson")
            assert (await k.post("/stage/bogus")).get("ok") is False

            # take 1: Demo chip; ⌃⌥⌘→ from the Before you start sheet starts the lesson and passes step 1
            m = app.mark()
            await app.send("learn", {"query": dr.GOAL, "mode": "demo"})
            await k.fresh_take(m, "Demo start")
            comp.folder = str(k.workdir)
            await k.press("next", "nn1", "nn2")
            await k.press("next", "nn2", "nn3")
            await k.press("next", "nn3", "nn4")
            await k.press("next", "nn4", "nn5", double=True)  # the run step, pressed twice: one run that learns
            losses = [e.p.get("value") for e in app.since(m, "metric") if e.p.get("runId") != "tutorial"]
            assert losses and abs(losses[-1] - 0.0009) < 1e-4, f"nn4's run under next: {losses[-3:]}"
            assert (await k.get("/stage")).get("runs") == {"nn4": 1}, "next on the run step counts one run"
            await k.press("next", "nn5", "nn6", double=True)
            for frm, to in zip(reversed(STEPS), reversed(STEPS[:-1])):  # back x5: nn6 -> nn1, one step each
                await k.press("back", frm, to)
            m = app.mark()  # back on step 1: stays there, says so
            assert (await k.post("/stage/back")).get("ok") is True
            await app.wait("card", lambda p: "first step" in str(p.get("title", "")).lower(), since=m, timeout=3,
                           what="'This is the first step'")
            await asyncio.sleep(0.5)
            assert not k.moves(m) and (await k.where())[1] == "nn1", k.moves(m)

            # ⌃⌥⌘R: fresh takes, one after another, then two presses at once
            for i in range(2):
                (k.workdir / "nn.py").write_text(dr.paste_under(dr.starter(), dr.SECTIONS[0], "W1 = 0\n"),
                                                 encoding="utf-8")
                m = app.mark()
                assert (await k.post("/stage/restart")).get("ok") is True
                await k.fresh_take(m, f"restart {i + 1}")
            m = app.mark()
            replies = await asyncio.gather(k.post("/stage/restart"), k.post("/stage/restart"))
            assert any(r.get("ok") for r in replies), replies  # the second may land while the first has no lesson
            await k.fresh_take(m, "double restart")
            assert len(app.since(m, "lesson.ready")) == 1, "a double ⌃⌥⌘R started two takes"

            # Start the lesson, then ⌃⌥⌘→ to the end: the completion card; ⌃⌥⌘→ after it does nothing
            m = app.mark()
            await app.send("action", {"kind": "start"})
            await asyncio.sleep(0.5)
            assert (await k.where())[0] == "active"
            for frm, to in zip(STEPS, STEPS[1:]):
                await k.press("next", frm, to)
            m6 = app.mark()
            assert (await k.post("/stage/next")).get("ok") is True
            await app.wait("step.passed", lambda p: p.get("stepId") == "nn6", since=m6, timeout=6, what="nn6 passed")
            await app.wait("card", dr.is_completion, since=m6, timeout=8, what="the completion card")
            assert not app.find(m, "offtrack"), "a Not yet on the presenter's next"
            assert (await k.post("/stage/next")).get("ok") is False
            await asyncio.sleep(0.5)
            assert (await k.where())[:2] == ("done", "nn6")

            # ⌃⌥⌘R after the lesson is complete: take 2
            m = app.mark()
            assert (await k.post("/stage/restart")).get("ok") is True
            await k.fresh_take(m, "restart after the end")

            # End: the keys let go; a Demo again after End is fresh and its keys work
            m = app.mark()
            await app.send("end_lesson", {})
            await app.wait("lesson.ended", since=m, timeout=4, what="lesson.ended")
            await asyncio.sleep(0.4)
            await k.all_off("after End")
            m = app.mark()
            await app.send("learn", {"query": dr.GOAL, "mode": "demo"})
            await k.fresh_take(m, "Demo after End")
            await k.press("next", "nn1", "nn2")
            await k.press("back", "nn2", "nn1")
            m = app.mark()
            await app.send("end_lesson", {})
            await app.wait("lesson.ended", since=m, timeout=4, what="lesson.ended")

            assert not k.errors(start), k.errors(start)
            await app.close()
    finally:
        eng.stop()
        comp.stop()
    assert not dr.engine_log_problems(base / "engine.log"), dr.engine_log_problems(base / "engine.log")
    screen = [e for e in dr.Rehearsal(port, base, comp).effects(t_wall) if e["what"] in ("ax", "quartz")]
    assert not screen, f"the keys touched the screen: {screen[:5]}"


@pytest.mark.skipif(bool(os.environ.get("MIYAGI_SKIP_REHEARSAL")), reason="MIYAGI_SKIP_REHEARSAL is set")
def test_presenter_keys_next_back_restart_many_times(tmp_path):
    if why := dr.deps_missing():
        pytest.skip(f"presenter keys: {why}")
    asyncio.run(presenter(dr.free_port(), tmp_path / "keys"))
