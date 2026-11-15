#!/usr/bin/env python3
"""Actions QA: do Explain / Show me / Hint / Diagram / Back visibly answer, on real lessons, with and
without code on screen?

  .venv/bin/python scripts/stage_actions.py --screen fixture     # OCR fixture: VS Code + Terminal with code
  .venv/bin/python scripts/stage_actions.py --screen real        # the real screen (whatever is on it)

For each lesson, at step 1 and step 2, it sends explain, show_me, hint x3, diagram, back (one at a time) and records
every event for 8 s. Verdict per action:
  - visible within 1 s: status thinking, a spotlight with a rect, video.seek, or the card/diagram itself
  - result within 6 s: a card (explain, hint), a diagram (diagram); show_me / back: a video.seek
    (show_me also spotlights the step target when it is on screen)
  - every spotlight rect is non-empty and on the main display; at most one card per action; the 3 hints differ
  - no `error` event
Then end_lesson, and nothing may arrive for 8 s afterwards. Records go to demo/runs/stage-actions.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage  # noqa: E402
from stage_lifecycle import Client, start_lesson  # noqa: E402

import httpx  # noqa: E402

C = stage.C
ROOT = stage.ROOT
FIXTURE = "server/screen/fixtures/vscode_terminal_flat.png"
LESSONS = [
    ("PINN hero", ("train a physics-informed neural network in PyTorch", "https://www.youtube.com/watch?v=AXXnSzmpyoI")),
    ("React useEffect", ("react useEffect cleanup", "https://www.youtube.com/watch?v=V8FvyuObouc")),
    ("notebook (linear regression)", ("linear regression in numpy", "https://www.youtube.com/watch?v=Jj7WD71qQWE")),
    # its targets (`class PINN(nn.Module):`, `def pde_residual(`) are the code in the OCR fixture: tests spotlight rects
    ("PINN convection (targets on the fixture)", ("train a PINN on the convection equation",
                                                  "https://www.youtube.com/watch?v=unBU1PwCnvQ")),
]
ACTIONS = ["explain", "show_me", "hint", "hint", "hint", "diagram", "back"]
WINDOW_S = 8.0


def display_size() -> tuple[float, float]:
    try:
        import Quartz

        b = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        return float(b.size.width), float(b.size.height)
    except Exception:  # noqa: BLE001
        return 1728.0, 1117.0


W, H = display_size()


def rect_ok(r: dict | None) -> tuple[bool, str]:
    if not isinstance(r, dict):
        return False, "no rect"
    x, y, w, h = (float(r.get(k, -1)) for k in ("x", "y", "w", "h"))
    if w <= 0 or h <= 0:
        return False, f"empty rect {r}"
    if x < 0 or y < 0 or x + w > W + 1 or y + h > H + 1:
        return False, f"off-screen rect {r} (display {W:.0f}x{H:.0f})"
    return True, f"{x:.0f},{y:.0f} {w:.0f}x{h:.0f}"


def judge(action: str, evs: list, prev_hints: list[str]) -> dict:
    """evs: [(t_rel, type, payload)] relative to the send."""
    first = next(((t, ty, p) for t, ty, p in evs
                  if (ty == "status" and p.get("state") == "thinking") or ty in ("video.seek", "card", "diagram")
                  or (ty == "spotlight" and p.get("rect"))), None)
    cards = [(t, p) for t, ty, p in evs if ty == "card"]
    diagrams = [(t, p) for t, ty, p in evs if ty == "diagram"]
    seeks = [(t, p) for t, ty, p in evs if ty == "video.seek"]
    spots = [(t, p) for t, ty, p in evs if ty == "spotlight" and p.get("rect")]
    errors = [p.get("message") for _, ty, p in evs if ty == "error"]
    problems = []
    visible = first is not None and first[0] <= 1.0
    if not visible:
        problems.append("nothing visible within 1 s" + (f" (first at {first[0]:.1f} s: {first[1]})" if first else ""))
    result = None
    if action in ("explain", "hint"):
        result = cards[0] if cards else None
        if not result or result[0] > 6.0:
            problems.append("no card within 6 s" + (f" (card at {cards[0][0]:.1f} s)" if cards else ""))
        if len(cards) > 1:
            problems.append(f"{len(cards)} cards for one {action}")
        if action == "hint" and cards:
            body = (cards[0][1].get("title", "") + "|" + cards[0][1].get("body", "")).strip()
            if body in prev_hints:
                problems.append("same hint as an earlier level")
            prev_hints.append(body)
    elif action == "diagram":
        result = diagrams[0] if diagrams else None
        if not result or result[0] > 6.0:
            problems.append("no diagram within 6 s" + (f" (diagram at {diagrams[0][0]:.1f} s)" if diagrams else ""))
        if len(diagrams) > 1:
            problems.append(f"{len(diagrams)} diagrams for one request")
    elif action in ("show_me", "back"):
        result = seeks[0] if seeks else None
        if not result or result[0] > 1.0:
            problems.append("no video.seek within 1 s")
    for _, p in spots:
        ok, why = rect_ok(p.get("rect"))
        if not ok:
            problems.append(f"spotlight {why}")
    if errors:
        problems.append(f"error: {errors[0][:120]}")
    what = ""
    if result:
        p = result[1]
        what = (f"{p.get('kind')} {p.get('title') or p.get('caption') or ''}" if action != "show_me" and action != "back"
                else f"seek t={p.get('t')}")
    return {"action": action, "pass": not problems, "first": f"{first[1]}@{first[0]:.2f}s" if first else None,
            "result": f"{what[:70]}@{result[0]:.1f}s" if result else None,
            "spotlight": [rect_ok(p.get("rect"))[1] for _, p in spots] or None,
            "problems": problems, "events": [f"{t:.2f} {ty}" for t, ty, _ in evs if ty not in ("metric", "screen.seen")]}


async def qa_lesson(engine: stage.Engine, name: str, topic, screen: str) -> list[dict]:
    rows = []
    async with Client(engine, "qa") as c:
        print(f"\n{C['bold']}=== {name} ({screen} screen){C['x']}")
        ready = await start_lesson(c, topic, timeout=240)
        if not ready:
            errs = [p.get("message") for _, ty, p in c.events if ty == "error"]
            print(f"  {C['r']}lesson didn't start: {errs[-1:] }{C['x']}")
            return [{"lesson": name, "screen": screen, "step": None, "action": "start", "pass": False,
                     "problems": [f"lesson didn't start: {errs[-1:]}"]}]
        st0 = engine.state()
        print(f"  lesson {ready['lesson']['title']!r} · screen={st0.get('screen')} · precision={st0.get('precisionMode')} "
              f"· workdir {st0.get('workdir')}")
        for step_i in (0, 1):
            if step_i:
                i = c.mark()
                httpx.post(f"{engine.http}/debug/goto/{step_i}", timeout=10)
                await c.wait_for(lambda e: e[1] == "step.started", i, 10)
            st = engine.state()
            step = st.get("step") or {}
            seg = step.get("video") or {}
            # the player reports a position inside the clip, so the wall-clock segment timer doesn't fire mid-test
            await c.send("video.state", {"t": float(seg.get("start", 0)) + 1, "playing": True})
            await asyncio.sleep(3.0)  # let the step settle (prefetches, first evaluation)
            targets = [t.get("match") for t in step.get("targets") or []]
            print(f"  {C['b']}step {step_i + 1}: {step.get('id')} {step.get('title')!r}{C['x']} targets {targets}")
            hints: list[str] = []
            for action in ACTIONS:
                i = c.mark()
                t_send = time.monotonic() - c.t0
                await c.send("action", {"kind": action})
                await asyncio.sleep(WINDOW_S)
                evs = [(t - t_send, ty, p) for t, ty, p in c.since(i)]
                r = judge(action, evs, hints)
                r.update({"lesson": name, "screen": screen, "step": step_i + 1, "stepId": step.get("id")})
                rows.append(r)
                col = C["g"] if r["pass"] else C["r"]
                print(f"    {col}{'PASS' if r['pass'] else 'FAIL'}{C['x']} {action:8} first {r['first']} · result {r['result']}"
                      + (f" · spot {r['spotlight']}" if r["spotlight"] else "")
                      + (f" · {C['y']}{'; '.join(r['problems'])}{C['x']}" if r["problems"] else ""))
        # end_lesson: nothing may follow
        i = c.mark()
        await c.send("end_lesson", {})
        ended = await c.wait_for(lambda e: e[1] == "lesson.ended", i, 10)
        await asyncio.sleep(WINDOW_S)
        late = [ty for t, ty, p in c.since(i) if ended and t > ended[0] and (
            ty in ("card", "diagram", "video.seek", "step.started", "offtrack")
            or (ty == "spotlight" and p.get("rect")) or (ty == "status" and p.get("state") != "idle"))]
        ok = bool(ended) and not late
        rows.append({"lesson": name, "screen": screen, "step": "end", "action": "end_lesson", "pass": ok,
                     "problems": ([] if ended else ["no lesson.ended"]) + ([f"after lesson.ended: {late}"] if late else []),
                     "first": "lesson.ended" if ended else None, "result": None, "spotlight": None})
        print(f"    {C['g'] if ok else C['r']}{'PASS' if ok else 'FAIL'}{C['x']} end_lesson" + (f" · late {late}" if late else ""))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--screen", choices=["fixture", "real"], required=True)
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--only", action="append", default=[], help="lesson names to run (default: all 3)")
    args = ap.parse_args()
    engine = stage.Engine(args.port)
    env = [f"TUT_SCREEN_FIXTURE={ROOT / FIXTURE}"] if args.screen == "fixture" else ["TUT_SCREEN_FIXTURE="]
    engine.ensure(screen=True, open_ws=False, workdir=None, fresh=True, extra_env=env)
    rows = []
    for name, topic in LESSONS:
        if args.only and name not in args.only:
            continue
        rows += asyncio.run(qa_lesson(engine, name, topic, args.screen))
    with (stage.RUNS / "stage-actions.jsonl").open("a") as f:
        for r in rows:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **r}, ensure_ascii=False) + "\n")
    n = sum(1 for r in rows if r["pass"])
    print(f"\n{n}/{len(rows)} PASS ({args.screen} screen)")


if __name__ == "__main__":
    main()
