#!/usr/bin/env python3
"""The Demo lesson as a mock-engine scenario: the backup that needs no Python engine on the demo Mac.

Walks the real engine's Demo lesson (server/orchestrator/stage.py, no API calls, no network) step by step, records
every event it sends with its real timing, and writes them as a scenario for the app's mock engine
(app/mock/engine.ts): the same lesson, cards, check rows, runs and network diagrams, driven by the same buttons.

    python3 scripts/make_demo_scenario.py [--out app/mock/scenarios/nndemo.json]

In the app: Electron with DEMO=1 SCENARIO=nndemo (or `npm run mock -- nndemo` and the app as usual), launcher →
anything → Demo. Then Check my work on each typing step, Run it for me on the run steps (the first Train it run is
the stuck one; Run it for me again learns). Hint / Explain / Diagram / Show me answer from the lesson's own cards.
The mock can't see saves: each step moves on with Check my work (or Skip).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "BRIGHTDATA_API_KEY", "ELEVENLABS_API_KEY")
SKIP = {"speak", "screen.seen", "config.status"}  # audio lives on the engine


async def walk() -> dict:
    work = Path(tempfile.mkdtemp(prefix="nndemo-"))
    os.environ.update({"TUT_WORKDIR": str(work), "MIYAGI_STATE_DIR": tempfile.mkdtemp(prefix="nndemo-state-")})
    for k in KEYS:
        os.environ[k] = ""
    os.environ.pop("DEMO", None)

    from server.orchestrator import stage
    from server.orchestrator.modules import Modules
    from server.orchestrator.session import LessonSession
    from shared.contracts.events import engine_message

    log: list[tuple[float, str, dict]] = []

    async def emit(type_: str, payload: dict | None = None) -> None:
        msg = engine_message(type_, payload or {})  # contract-checked, like the hub
        log.append((time.monotonic(), msg["type"], msg["payload"]))

    s = LessonSession(emit, Modules(demo=False, force_stubs="all"), metric_eval_s=0, result_stagger_s=0,
                      build_tick_s=0.01, seen_interval_s=0)
    s.ready_hold_s = 0.4
    segments: dict[str, list[dict]] = {}

    async def until(cond, timeout: float = 15.0) -> None:
        end = time.monotonic() + timeout
        while not cond() and time.monotonic() < end:
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.8)  # the diagrams / status that follow a pass
        await s.drain()

    async def record(name: str, act, cond) -> None:
        await asyncio.sleep(stage.AGAIN_S + 0.3)  # a person's pace: a press right after a run counts as that run
        t0, n = time.monotonic(), len(log)
        await act()
        await until(cond)
        assert cond(), f"{name}: the engine didn't get there"
        items, last = [], t0
        for t, type_, payload in log[n:]:
            if type_ in SKIP:
                continue
            items.append({"wait": max(0, round((t - last) * 1000)), "type": type_, "payload": payload})
            last = t
        segments[name] = items
        print(f"{name}: {len(items)} events ({', '.join(sorted({i['type'] for i in items}))})")

    step = lambda: (s.step or {}).get("id")  # noqa: E731
    types_since = lambda n: [x[1] for x in log[n:]]  # noqa: E731

    await record("stepnn1", lambda: s.learn("build a neural network", mode="demo"), lambda: step() == "nn1")
    nn = work / "nn.py"
    for k in (1, 2, 3):
        if k == 1:  # the presenter's zeros shortcut, so the first Train it run is the stuck one
            nn.write_text(nn.read_text() + "\nW1 = np.zeros((2, 4))\nW2 = np.zeros((4, 1))\n")
        await record(f"stepnn{k + 1}", lambda: s.action("check_step"), lambda k=k: step() == f"nn{k + 1}")
    n = len(log)
    await record("stepnn4stuck", lambda: s.action("run_command"), lambda: "offtrack" in types_since(n))
    await record("stepnn5", lambda: s.action("run_command"), lambda: step() == "nn5")
    await record("stepnn6", lambda: s.action("check_step"), lambda: step() == "nn6")
    n = len(log)
    await record("stepnn6done", lambda: s.action("run_command"), lambda: "step.passed" in types_since(n))
    assert stage.on(s)
    return segments


def cached(kind: str, name: str, sid: str) -> list[dict]:
    from server.orchestrator import config

    p = config.DEMO_CACHE / kind / f"{name}.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    d["stepId"] = sid
    return [{"wait": 250, "type": "status", "payload": {"state": "thinking"}},
            {"wait": 450, "type": "diagram" if kind == "diagrams" else "card", "payload": d}]


def scenario(segments: dict) -> dict:
    on = {"learn:demo": "stepnn1"}
    nxt = {"stepnn1": "stepnn2", "stepnn2": "stepnn3", "stepnn3": "stepnn4", "stepnn4": "stepnn4stuck",
           "stepnn4stuck": "stepnn5", "stepnn5": "stepnn6", "stepnn6": "stepnn6done"}
    for cur, seg in nxt.items():
        on[f"action:check_step@{cur}"] = seg
        on[f"action:skip_step@{cur}"] = seg
    for cur in ("stepnn4", "stepnn4stuck", "stepnn6"):
        on[f"action:run_command@{cur}"] = nxt[cur]
        on[f"action:apply_fix@{cur}"] = nxt[cur]
    sid = {"stepnn1": "nn1", "stepnn2": "nn2", "stepnn3": "nn3", "stepnn4": "nn4", "stepnn4stuck": "nn4",
           "stepnn5": "nn5", "stepnn6": "nn6", "stepnn6done": "nn6"}
    for cur, s in sid.items():
        stuck = cur == "stepnn4stuck"
        extra = {"hint": cached("cards", f"{s}-stuck-hint0" if stuck else f"{s}-hint0", s),
                 "explain": cached("cards", f"{s}-stuck-explain" if stuck else f"{s}-explain", s),
                 "show_me": cached("cards", f"{s}-answer", s),
                 "diagram": cached("diagrams", f"{s}-gradients" if stuck else f"{s}-network", s)}
        for kind, items in extra.items():
            if items:
                name = f"nn-{kind}-{cur}"
                segments[name] = items + [{"wait": 100, "type": "status",
                                           "payload": {"state": "offtrack" if stuck else "watching"}}]
                on[f"action:{kind}@{cur}"] = name
    return {"name": "nndemo", "on": on, "segments": segments}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "app" / "mock" / "scenarios" / "nndemo.json"))
    out = Path(ap.parse_args().out)
    segments = asyncio.run(walk())
    sc = scenario(segments)
    text = json.dumps(sc, indent=1, ensure_ascii=False)
    work = json.dumps(str(Path(os.environ["TUT_WORKDIR"])))[1:-1]  # as it is written inside the JSON text
    text = text.replace(work, "~/miyagi/lessons/a-neural-net-from-scratch")
    out.write_text(text + "\n", encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
