"""One case through the REAL orchestrator: our own engine (LIVE mode, real checks + coach), the cached
React lesson, the case screen replayed through `TUT_SCREEN_FIXTURE` (the reader re-reads the PNG every
capture, so overwriting it is a screen change), and a scripted learner over the WebSocket.

Learner script (React R3, step s1: useEffect used but not imported -> "Failed to compile"):
  t0  connect; lesson.ready + step.started(s1)          (autostart: real builder, cache hit)
      video.state at the segment end                    -> the clip is over
      save Timer.js (no change)                         -> evaluate("file"): fails, gate opens
      idle >= ORCH_IDLE_GATE_S                          -> level-2 offtrack (concept, no diff)   [timed]
      save again after ORCH_LADDER_MIN_S                -> repeat breakpoint -> level-3 offtrack (diff)
      action apply_fix -> "Apply this fix?" preview -> action confirm -> file written
      overwrite the screen PNG with the post-fix screen (CRA "Compiled successfully!")
                                                        -> step.passed
usage:  .venv/bin/python -m evals.coach.run_engine --layout root|nested [--port 8796]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import websockets

from . import cases as C

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
URL = "https://www.youtube.com/watch?v=ZipmUa9N7Os"


def seed_cache(graph: dict, workdir: Path) -> Path:
    """Put the snapshot lesson where the builder's cache lookup finds it for this workdir (LIVE path)."""
    sys.path.insert(0, str(REPO))
    from server.lesson.builder import CACHE_DIR, cache_key

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / f"{cache_key(URL, '', str(workdir))}.json"
    p.write_text(json.dumps(graph))
    return p


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", choices=["root", "nested"], default="root",
                    help="root: TUT_WORKDIR is the CRA app; nested: the lesson folder holding demo-app/ (what s1 creates)")
    ap.add_argument("--port", type=int, default=8796)
    ap.add_argument("--out", default=str(HERE / "results"))
    args = ap.parse_args()

    case = C.BY_ID["R3"]
    work = Path(tempfile.mkdtemp(prefix="engine-eval-"))
    built = C.build(case, work / "lesson")  # -> <work>/lesson/demo-app/...
    workdir = built.workdir if args.layout == "root" else built.workdir.parent
    timer = built.workdir / built.file
    fixture = work / "screen.png"
    built.screen.save(fixture)
    cache_file = seed_cache(case.graph(), workdir)

    env = {**os.environ, "DEMO": "0", "ENGINE_PORT": str(args.port), "TUT_WORKDIR": str(workdir),
           "TUT_SCREEN_FIXTURE": str(fixture), "ORCH_SCREEN": "1", "ORCH_AUTOSTART": "1", "ORCH_LESSON_URL": URL,
           "ORCH_RECORD": "0", "ORCH_SCREEN_INTERVAL_S": "0.5"}
    log_path = Path(args.out) / f"engine-{args.layout}.log"
    Path(args.out).mkdir(parents=True, exist_ok=True)
    logf = open(log_path, "w")
    proc = subprocess.Popen([sys.executable, "-m", "server.orchestrator.main", "--port", str(args.port), "--host", "127.0.0.1"],
                            cwd=REPO, env=env, stdout=logf, stderr=subprocess.STDOUT)
    events: list[dict] = []
    t0 = time.perf_counter()
    marks: dict[str, float] = {}
    rel = lambda: round(time.perf_counter() - t0, 2)  # noqa: E731

    def note(k: str) -> None:
        marks.setdefault(k, rel())
        print(f"[{rel():7.2f}s] {k}", flush=True)

    try:
        ws = None
        for _ in range(80):
            try:
                ws = await websockets.connect(f"ws://127.0.0.1:{args.port}/", max_size=None)
                break
            except OSError:
                await asyncio.sleep(0.25)
        assert ws is not None, "engine did not start"
        note("connected")

        async def send(type_: str, payload: dict) -> None:
            await ws.send(json.dumps({"type": type_, "payload": payload}))

        async def wait_for(pred, timeout: float, label: str) -> dict | None:
            end = time.perf_counter() + timeout
            while time.perf_counter() < end:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(0.05, end - time.perf_counter()))
                except asyncio.TimeoutError:
                    break
                ev = json.loads(raw)
                ev["_t"] = rel()
                events.append(ev)
                p = ev.get("payload") or {}
                if ev["type"] in ("offtrack", "card", "error", "step.passed", "step.started", "lesson.ready", "spotlight", "status"):
                    brief = {k: p.get(k) for k in ("stepId", "title", "body", "level", "message", "state", "kind", "rect", "caption") if p.get(k) is not None}
                    if ev["type"] == "offtrack" and p.get("diff"):
                        brief["diff"] = p["diff"]
                    print(f"[{ev['_t']:7.2f}s]   <- {ev['type']} {json.dumps(brief)[:300]}", flush=True)
                if pred(ev):
                    note(label)
                    return ev
            print(f"[{rel():7.2f}s] TIMEOUT waiting for {label}", flush=True)
            return None

        ready = await wait_for(lambda e: e["type"] == "step.started", 120, "step.started")
        if not ready:
            return
        seg_end = case.step_dict()["video"]["end"]
        await send("video.state", {"t": seg_end, "playing": True})
        await wait_for(lambda e: e["type"] == "video.pause" or (e["type"] == "spotlight"), 8, "segment end")

        # learner saves (same content: the bug is already in the file)
        timer.write_text(timer.read_text())
        t_save = rel()
        note("save #1")
        off2 = await wait_for(lambda e: e["type"] == "offtrack", 90, "offtrack level 2")
        if off2:
            marks["save_to_l2_s"] = round(off2["_t"] - t_save, 2)
        ladder = float(os.environ.get("ORCH_LADDER_MIN_S", "20"))
        await wait_for(lambda e: False, ladder + 1, "ladder wait")
        timer.write_text(timer.read_text())
        t_save2 = rel()
        note("save #2 (repeat)")
        off3 = await wait_for(lambda e: e["type"] == "offtrack" and (e["payload"].get("level") == 3), 90, "offtrack level 3")
        if off3:
            marks["save_to_l3_s"] = round(off3["_t"] - t_save2, 2)
        await send("action", {"kind": "apply_fix"})
        prev = await wait_for(lambda e: e["type"] in ("card", "error") and (e["payload"].get("title") in ("Apply this fix?", "Fix it by hand", "No automatic fix", "Command copied", "Run this command") or e["type"] == "error"), 90, "apply_fix response")
        applied = False
        if prev and prev["payload"].get("title") == "Apply this fix?":
            await send("action", {"kind": "confirm"})
            done = await wait_for(lambda e: e["type"] == "card" and e["payload"].get("title") in ("Fix applied", "Fix it by hand") or e["type"] == "error", 30, "fix applied")
            applied = bool(done and done["payload"].get("title") == "Fix applied")
        new_text = timer.read_text()
        print("---- Timer.js after:\n" + new_text, flush=True)
        if applied:  # the dev server recompiles: render what CRA + Chrome would now show
            after = C.after_screen(case, built, new_text, C.react_check(new_text, built.workdir, case.step))
            tmp = work / "after.png"
            after.save(tmp)
            shutil.copy(tmp, fixture)
            shutil.copy(tmp.with_suffix(".json"), fixture.with_suffix(".json"))
            note("screen now shows the recompiled app")
            await wait_for(lambda e: e["type"] == "step.passed", 30, "step.passed")
        else:
            await wait_for(lambda e: False, 3, "drain")
    finally:
        summary = {"layout": args.layout, "workdir": str(workdir), "marks": marks,
                   "file_after": timer.read_text() if timer.exists() else None,
                   "events": [{k: v for k, v in e.items()} for e in events]}
        (Path(args.out) / f"engine-{args.layout}.json").write_text(json.dumps(summary, indent=1, default=str))
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        logf.close()
        cache_file.unlink(missing_ok=True)
        print(json.dumps(marks), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
