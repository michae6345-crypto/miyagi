#!/usr/bin/env python3
"""Lesson lifecycle checks against a LIVE engine (default :8790, started/reused like scripts/stage.py).

  .venv/bin/python scripts/stage_lifecycle.py end          # end a lesson 3 ways (+ mid-build), assert a clean idle
  .venv/bin/python scripts/stage_lifecycle.py resume       # resume card after reconnect / engine restart (S7)

Lessons come from the builders' caches (any topic already built in this checkout), so each start takes
seconds. Every case prints its event sequence and PASS/FAIL per assertion; a JSON summary is appended to
demo/runs/stage-lifecycle.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage  # noqa: E402  (scripts/stage.py: Engine, colors, RUNS)

import httpx  # noqa: E402
import websockets  # noqa: E402

C = stage.C
LESSON_A = ("react useEffect cleanup", "https://www.youtube.com/watch?v=ZipmUa9N7Os")
LESSON_B = ("git rebase interactive", "https://www.youtube.com/watch?v=42392W7SgnE")
# after a lesson ends, none of these may arrive (they'd mean a leftover task is still talking)
LEFTOVER = {"diagram", "card", "offtrack", "check.updated", "step.started", "step.passed", "video.seek", "video.play", "speak"}


class Client:
    """One app-like WebSocket client that records every event with a timestamp."""

    def __init__(self, engine: stage.Engine, name: str = "app"):
        self.engine, self.name = engine, name
        self.events: list[tuple[float, str, dict]] = []
        self.t0 = time.monotonic()
        self.ws = None
        self._task: asyncio.Task | None = None
        self._preflight_answered = False
        self.preflights: list = []

    async def __aenter__(self):
        self.ws = await websockets.connect(self.engine.ws, max_size=8 * 2**20, ping_interval=None)
        self._task = asyncio.create_task(self._read())
        return self

    async def __aexit__(self, *exc):
        if self._task:
            self._task.cancel()
        await self.ws.close()

    auto_build = True  # answer S8's preflight card with action build (once per pick), like a learner pressing "Build"

    async def _read(self):
        try:
            async for raw in self.ws:
                m = json.loads(raw)
                ev = (time.monotonic() - self.t0, m.get("type"), m.get("payload", {}))
                self.events.append(ev)
                if (self.auto_build and ev[1] == "card" and ev[2].get("kind") == "preflight"
                        and not self._preflight_answered):
                    self._preflight_answered = True
                    self.preflights.append(ev)
                    await self.send("action", {"kind": "build"})
        except websockets.ConnectionClosed:
            pass

    async def send(self, type_: str, payload: dict | None = None):
        if type_ in ("learn_url", "build_lesson", "learn"):
            self._preflight_answered = False
        await self.ws.send(json.dumps({"type": type_, "payload": payload or {}}))

    def mark(self) -> int:
        return len(self.events)

    def since(self, i: int) -> list[tuple[float, str, dict]]:
        return self.events[i:]

    async def wait_for(self, pred, since: int = 0, timeout: float = 60.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for ev in self.events[since:]:
                if pred(ev):
                    return ev
            await asyncio.sleep(0.05)
        return None


def seq(events, limit: int = 40) -> str:
    out = []
    for t, ty, p in events:
        if ty in ("lesson.building", "search.result", "metric", "screen.seen"):
            continue  # noisy; counted separately
        brief = ""
        if ty == "lesson.ended":
            brief = f" reason={p.get('reason')!r} lessonId={p.get('lessonId')}"
        elif ty == "status":
            brief = f" {p.get('state')}"
        elif ty == "step.started":
            brief = f" #{p.get('index')} {p.get('stepId')} {p.get('title', '')[:30]!r}"
        elif ty == "lesson.ready":
            brief = f" {p['lesson'].get('title', '')[:35]!r}"
        elif ty in ("card", "diagram"):
            brief = f" {p.get('kind')} {str(p.get('title') or p.get('caption') or '')[:40]!r}"
        elif ty == "spotlight":
            brief = " clear" if p.get("clear") else f" {p.get('caption', '')[:30]!r}"
        elif ty == "error":
            brief = f" {p.get('message', '')[:80]!r}"
        out.append(f"{t:6.2f}s {ty}{brief}")
    return "\n      ".join(out[:limit]) + (f"\n      … {len(out) - limit} more" if len(out) > limit else "")


class Case:
    def __init__(self, name: str):
        self.name, self.checks, self.sequence = name, [], ""

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        self.checks.append((label, bool(ok), detail))
        col = C["g"] if ok else C["r"]
        print(f"    {col}{'PASS' if ok else 'FAIL'}{C['x']} {label}" + (f" {C['dim']}({detail}){C['x']}" if detail else ""))
        return ok

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


async def start_lesson(c: Client, topic=LESSON_A, *, timeout: float = 120) -> dict | None:
    """learn (finder cache) -> learn_url (lesson cache) -> lesson.ready + step.started."""
    query, url = topic
    i = c.mark()
    await c.send("learn", {"query": query})
    if not await c.wait_for(lambda e: e[1] == "search.done", i, 90):
        return None
    i = c.mark()
    await c.send("learn_url", {"url": url})
    ready = await c.wait_for(lambda e: e[1] in ("lesson.ready", "error"), i, timeout)
    if not ready or ready[1] != "lesson.ready":
        return None
    await c.wait_for(lambda e: e[1] == "step.started", i, 10)
    return ready[2]


async def assert_ended(case: Case, c: Client, engine: stage.Engine, i: int, *, reason: str, quiet_s: float = 6.0,
                       expect_follow: set[str] | None = None, kept: bool = False) -> None:
    """kept: the bar's End (reason "stopped") keeps the save, so /state reads awaiting_resume and a new app is
    offered the resume card (only its Continue restores it; a rebuild starts over)."""
    ended = await c.wait_for(lambda e: e[1] == "lesson.ended", i, 10)
    case.check("lesson.ended arrives", ended is not None, f"reason={ended[2].get('reason')!r}" if ended else "none in 10 s")
    if ended:
        case.check(f"reason is {reason!r}", ended[2].get("reason") == reason, repr(ended[2].get("reason")))
    t_end = ended[0] if ended else 0.0
    idle = await c.wait_for(lambda e: e[1] == "status" and e[2].get("state") == "idle" and e[0] >= t_end, i, 5)
    case.check("status idle after lesson.ended", idle is not None)
    evs = c.since(i)
    case.check("spotlight cleared", any(ty == "spotlight" and p.get("clear") for _, ty, p in evs))
    case.check("video paused", any(ty == "video.pause" for _, ty, _ in evs))
    await asyncio.sleep(quiet_s)  # anything still running would talk now
    after = [(t, ty, p) for t, ty, p in c.since(i) if t > t_end and ty in LEFTOVER - (expect_follow or set())]
    case.check(f"no leftover events for {quiet_s:.0f} s (diagram/card/offtrack/check/step/video)", not after,
               ", ".join(f"{ty}@{t:.1f}s" for t, ty, _ in after[:5]))
    st = engine.state()
    case.check("/state: " + ("awaiting_resume (save kept)" if kept else "phase idle, no lesson") + ", no step",
               st.get("phase") == ("awaiting_resume" if kept else "idle") and bool(st.get("lesson")) == kept
               and st.get("stepId") is None,
               f"phase={st.get('phase')} lesson={bool(st.get('lesson'))} step={st.get('stepId')}")
    async with Client(engine, "probe") as probe:  # what a freshly connecting app would be told
        await asyncio.sleep(1.0)
        types = [ty for _, ty, _ in probe.events]
        cards = [p.get("kind") for _, ty, p in probe.events if ty == "card"]
        case.check("new client's snapshot has no lesson/step/offtrack/diagram, and "
                   + ("only the resume card" if kept else "no card"),
                   not ({"lesson.ready", "step.started", "offtrack", "diagram"} & set(types))
                   and cards == (["resume"] if kept else []),
                   f"snapshot: {types}")


async def run_end(engine: stage.Engine) -> list[Case]:
    cases: list[Case] = []

    async def ended_then_fresh(case: Case, c: Client, topic=LESSON_A):
        i = c.mark()
        ready = await start_lesson(c, topic)
        case.check("fresh lesson after: lesson.ready + step 1 started", ready is not None and any(
            ty == "step.started" for _, ty, _ in c.since(i)), ready["lesson"]["title"] if ready else "no lesson.ready")
        if ready:
            st = engine.state()
            case.check("fresh lesson starts at step index 0 with pending checks",
                       st.get("stepIndex") == 0 and all(v.get("status") != "pass" for v in (st.get("checks") or {}).values()),
                       f"stepIndex={st.get('stepIndex')} checks={[v.get('status') for v in (st.get('checks') or {}).values()]}")

    async with Client(engine) as c:
        # ---- 1: end_lesson over WS, with a hint card + a diagram request in flight
        case = Case("end_lesson over WS (diagram in flight)")
        print(f"\n{C['bold']}{case.name}{C['x']}")
        case.check("lesson starts", await start_lesson(c) is not None)
        i0 = c.mark()
        await c.send("action", {"kind": "hint"})
        await c.wait_for(lambda e: e[1] == "card", i0, 20)
        i = c.mark()
        await c.send("action", {"kind": "diagram"})
        await asyncio.sleep(0.3)
        await c.send("end_lesson", {})
        await assert_ended(case, c, engine, i, reason="stopped", kept=True)  # the bar's End: save kept
        await ended_then_fresh(case, c)  # the same lesson again starts over (only Continue restores a kept save)
        case.sequence = seq(c.since(i0))
        print(f"      {C['dim']}{case.sequence}{C['x']}")
        cases.append(case)

        # ---- 2: POST /end (lesson from case 1's fresh start), with an explain request in flight
        case = Case("curl -X POST /end (explain in flight)")
        print(f"\n{C['bold']}{case.name}{C['x']}")
        i = c.mark()
        await c.send("action", {"kind": "explain"})
        await asyncio.sleep(0.3)
        r = httpx.post(f"{engine.http}/end", timeout=10).json()
        case.check("POST /end answers ok + the ended lesson id", r.get("ok") and r.get("ended"), json.dumps(r))
        await assert_ended(case, c, engine, i, reason="POST /end")
        r2 = httpx.post(f"{engine.http}/end", timeout=10).json()
        case.check("POST /end again with nothing running is harmless", r2.get("ok") and not r2.get("ended"), json.dumps(r2))
        await ended_then_fresh(case, c)
        case.sequence = seq(c.since(i))
        print(f"      {C['dim']}{case.sequence}{C['x']}")
        cases.append(case)

        # ---- 3: a new learn ends the running lesson
        case = Case("new learn while a lesson runs")
        print(f"\n{C['bold']}{case.name}{C['x']}")
        i = c.mark()
        await c.send("action", {"kind": "hint"})
        await asyncio.sleep(0.3)
        await c.send("learn", {"query": LESSON_B[0]})
        # results for the new search are expected, the old lesson's events are not
        await assert_ended(case, c, engine, i, reason="new lesson", quiet_s=3.0)
        done = await c.wait_for(lambda e: e[1] == "search.done", i, 60)
        case.check("the new search completes", done is not None, f"total={done[2].get('total')}" if done else "")
        j = c.mark()
        await c.send("learn_url", {"url": LESSON_B[1]})
        ready = await c.wait_for(lambda e: e[1] in ("lesson.ready", "error"), j, 120)
        case.check("fresh lesson after: the new topic's lesson.ready",
                   ready is not None and ready[1] == "lesson.ready", ready[2]["lesson"]["title"] if ready and ready[1] == "lesson.ready" else str(ready))
        case.sequence = seq(c.since(i))
        print(f"      {C['dim']}{case.sequence}{C['x']}")
        cases.append(case)

        # ---- 4 (extra): end_lesson while a lesson is being built
        case = Case("end_lesson mid-build (extra)")
        print(f"\n{C['bold']}{case.name}{C['x']}")
        i = c.mark()
        await c.send("learn", {"query": "css flexbox tutorial"})
        done = await c.wait_for(lambda e: e[1] == "search.done", i, 90)
        rows = [p for _, ty, p in c.since(i) if ty == "search.result" and p.get("kind") == "video"]
        if not rows:
            case.check("search returned a video to build", False)
        else:
            j = c.mark()
            await c.send("build_lesson", {"resultIds": [rows[0]["id"]]})
            await c.wait_for(lambda e: e[1] == "lesson.building", j, 15)
            await asyncio.sleep(3)
            k = c.mark()
            await c.send("end_lesson", {})
            ended = await c.wait_for(lambda e: e[1] == "lesson.ended", k, 10)
            case.check("lesson.ended arrives while building", ended is not None)
            await asyncio.sleep(8)
            late = [ty for t, ty, p in c.since(k) if ty in ("lesson.ready", "step.started", "error")
                    or (ty == "lesson.building" and not p.get("failed"))]
            case.check("build is cancelled: no lesson.ready / progress / error afterwards", not late, ", ".join(late[:6]))
            st = engine.state()
            case.check("/state idle", st.get("phase") == "idle" and not st.get("lesson"), f"phase={st.get('phase')}")
            case.sequence = seq(c.since(j))
            print(f"      {C['dim']}{case.sequence}{C['x']}")
        cases.append(case)
    return cases


async def _lesson_at_step2(engine: stage.Engine, *, video_offset: float = 7.0) -> dict:
    """Start a lesson, advance to the 2nd step, report a video position inside it, disconnect.
    -> {stepId, video_t, lessonId}"""
    async with Client(engine) as c:
        if await start_lesson(c) is None:
            return {}
        i = c.mark()
        httpx.post(f"{engine.http}/debug/pass", timeout=10)  # advance a step
        st = await c.wait_for(lambda e: e[1] == "step.started", i, 10)
        if not st:
            return {}
        seg = st[2].get("video") or {}
        t = float(seg.get("start", 0)) + video_offset
        await c.send("video.state", {"t": t, "playing": True})
        await asyncio.sleep(1.0)
        lesson = (engine.state().get("lesson") or {}).get("id")
        return {"stepId": st[2]["stepId"], "video_t": t, "lessonId": lesson, "title": st[2].get("title")}


async def _expect_resume(case: Case, engine: stage.Engine, before: dict) -> None:
    async with Client(engine, "returning-app") as c:
        await asyncio.sleep(2.0)
        types = [ty for _, ty, _ in c.events]
        card = next((p for _, ty, p in c.events if ty == "card" and p.get("kind") == "resume"), None)
        case.check("reconnect shows the resume card", card is not None,
                   f"{card.get('title')!r} · {card.get('body')!r} · actions {card.get('actions')}" if card else f"snapshot: {types}")
        case.check("…and does not auto-continue (no step.started / video.play / video.seek in the snapshot)",
                   not ({"step.started", "video.play", "video.seek"} & set(types)), f"snapshot: {types}")
        case.check("video paused while asking", "video.pause" in types)
        i = c.mark()
        await c.send("action", {"kind": "resume"})
        st = await c.wait_for(lambda e: e[1] == "step.started", i, 10)
        seek = await c.wait_for(lambda e: e[1] == "video.seek", i, 10)
        case.check("resume -> same step", st is not None and st[2].get("stepId") == before.get("stepId"),
                   f"{st[2].get('stepId') if st else None} (was {before.get('stepId')})")
        case.check(f"resume -> video seeks to the reported position ({before.get('video_t', 0):.0f} s)",
                   seek is not None and abs(seek[2].get("t", -99) - before.get("video_t", 0)) < 1.5,
                   f"video.seek {seek[2] if seek else None}")
        stat = await c.wait_for(lambda e: e[1] == "status" and e[2].get("state") in ("watching", "offtrack"), i, 5)
        case.check("status back to watching/offtrack", stat is not None)
        resumed = c.since(i)
        j = c.mark()
        await c.send("action", {"kind": "end_lesson"})  # the card's "Start a new lesson" button
        # E11: the save is kept (stopped) until another lesson is built, like the bar's End
        await assert_ended(case, c, engine, j, reason="end_lesson", quiet_s=3, kept=True)
        case.sequence = ("snapshot: " + seq([e for e in c.events[:i]]) + "\n      after resume: " + seq(resumed)
                         + "\n      after end_lesson: " + seq(c.since(j)))
        print(f"      {C['dim']}{case.sequence}{C['x']}")


async def run_resume(engine: stage.Engine, restart) -> list[Case]:
    cases: list[Case] = []
    away = float(os.environ.get("ORCH_RESUME_AFTER_S", "10")) + 2

    case = Case(f"reconnect after {away:.0f} s away -> resume card -> resume -> end_lesson")
    print(f"\n{C['bold']}{case.name}{C['x']}")
    before = await _lesson_at_step2(engine)
    case.check("lesson started and advanced to step 2", bool(before), json.dumps(before))
    await asyncio.sleep(away)
    await _expect_resume(case, engine, before)
    cases.append(case)

    case = Case("quick reconnect (2 s blip) -> just continues, no card")
    print(f"\n{C['bold']}{case.name}{C['x']}")
    before = await _lesson_at_step2(engine)
    case.check("lesson started and advanced to step 2", bool(before), json.dumps(before))
    await asyncio.sleep(2)
    async with Client(engine, "blip") as c:
        await asyncio.sleep(1.5)
        types = [ty for _, ty, _ in c.events]
        st = next((p for _, ty, p in c.events if ty == "step.started"), None)
        case.check("no resume card", not any(ty == "card" and p.get("kind") == "resume" for _, ty, p in c.events), f"{types}")
        case.check("snapshot continues the same step", st is not None and st.get("stepId") == before.get("stepId"),
                   f"{types}")
        case.sequence = seq(c.events)
        print(f"      {C['dim']}{case.sequence}{C['x']}")
        httpx.post(f"{engine.http}/end", timeout=10)
    cases.append(case)

    case = Case("engine restart while away -> resume card")
    print(f"\n{C['bold']}{case.name}{C['x']}")
    before = await _lesson_at_step2(engine)
    case.check("lesson started and advanced to step 2", bool(before), json.dumps(before))
    restart()
    await asyncio.sleep(away)
    st = engine.state()
    case.check("after restart the engine still has the lesson", bool(st.get("lesson")),
               f"phase={st.get('phase')} lesson={(st.get('lesson') or {}).get('id')} step={st.get('stepId')}")
    if st.get("lesson"):
        await _expect_resume(case, engine, before)
    else:
        async with Client(engine, "after-restart") as c:
            await asyncio.sleep(1.5)
            case.check("reconnect after restart shows the resume card",
                       any(ty == "card" and p.get("kind") == "resume" for _, ty, p in c.events),
                       f"snapshot: {[ty for _, ty, _ in c.events]}")
            case.sequence = seq(c.events)
            print(f"      {C['dim']}{case.sequence}{C['x']}")
    cases.append(case)
    return cases


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["end", "resume"])
    ap.add_argument("--port", type=int, default=8790)
    args = ap.parse_args()
    engine = stage.Engine(args.port)
    engine.ensure(screen=False, open_ws=False, workdir=None)
    if args.what == "end":
        cases = asyncio.run(run_end(engine))
    else:
        def restart() -> None:
            engine.stop()
            engine.ensure(screen=False, open_ws=False, workdir=None)
        cases = asyncio.run(run_resume(engine, restart=restart))
    print()
    for cs in cases:
        print(f"{C['g'] if cs.passed else C['r']}{'PASS' if cs.passed else 'FAIL'}{C['x']} {cs.name}")
    stage.RUNS.mkdir(parents=True, exist_ok=True)
    with (stage.RUNS / "stage-lifecycle.jsonl").open("a") as f:
        for cs in cases:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "what": args.what, "case": cs.name,
                                "passed": cs.passed, "checks": cs.checks, "sequence": cs.sequence}) + "\n")


if __name__ == "__main__":
    main()
