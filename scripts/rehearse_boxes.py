"""Where do the "Just teach me" boxes land? Rendered VS Code frames through the real ScreenReader. ZERO API calls.

  .venv/bin/python scripts/rehearse_boxes.py                       # both starters, the cached calculator lesson
  .venv/bin/python scripts/rehearse_boxes.py --starter seeded      # only the live run's starter
  .venv/bin/python scripts/rehearse_boxes.py --steps 4 --hold 6

Reuses S1's harness (scripts/stage_lessonmode.py, branch claude/stage-runner-89c172): its offline env (DEMO=1, keys
blanked, HTTP(S) through a dead proxy), its VS Code renderer and fixture plumbing. The real orchestrator Engine runs in
this process with the real ScreenReader OCR-ing the rendered PNGs (Apple Vision, on device). The editor is never opened.

What it adds to S1's checks:
  boxes   every spotlight rect, classified against the frame it was placed on: the code row it covers (and that row's
          text), an EMPTY row, below the last line, the tab/breadcrumb rows, or the terminal panel. Each typing step's
          box is compared with the row where the step's target text really is.
  away    app switching on one typing step: (1) another app in front -> the box clears; (2) VS Code back -> a box
          again; (3) the step finishes while VS Code is in the background -> no box over the other app, and back in
          VS Code the NEW step is boxed (not the old rect); (4) a browser showing the step's own code text -> no box
          inside the browser.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSON = ROOT / "demo" / "cache" / "lessons" / "text-43e26ca1d86c37ed.json"
STARTER = '"""A simple Python calculator."""\n\n# Step 1: Start building your calculator here'  # Michael's live run
S1_REF = "claude/stage-runner-89c172"


def load_harness():
    """S1's stage_lessonmode.py: this checkout's copy if present, else straight from S1's branch (git show)."""
    local = ROOT / "scripts" / "stage_lessonmode.py"
    path = local
    if not local.exists():
        src = subprocess.run(["git", "-C", str(ROOT), "show", f"{S1_REF}:scripts/stage_lessonmode.py"],
                             capture_output=True, text=True, check=True).stdout
        path = ROOT / "demo" / "runs" / "boxes" / "_stage_lessonmode.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(src)
    spec = importlib.util.spec_from_file_location("stage_lessonmode", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ROOT, mod.RUNS = ROOT, ROOT / "demo" / "runs"  # its paths, wherever the file came from
    mod.FIXDIR, mod.SCRATCH = mod.RUNS / "boxes" / "fixtures", mod.RUNS / "boxes" / "work"
    return mod


def render_browser(H, name: str, lines: list[str]) -> dict:
    """Safari in front, showing a tutorial page that contains the step's own code text."""
    from PIL import Image, ImageDraw, ImageFont

    H.FIXDIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (H.W * H.S, H.H * H.S), (250, 250, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, H.W * H.S, 80 * H.S], fill=(230, 230, 230))
    d.text((40 * H.S, 30 * H.S), "https://realpython.com/python-calculator", font=ImageFont.truetype(H.UI, 14 * H.S),
           fill=(40, 40, 40))
    mono = ImageFont.truetype(H.MENLO, 14 * H.S)
    for i, ln in enumerate(lines):
        d.text((300 * H.S, (200 + i * 24) * H.S), ln, font=mono, fill=(30, 30, 30))
    png = H.FIXDIR / f"{name}.png"
    img.save(png, optimize=True)
    (H.FIXDIR / f"{name}.json").write_text(json.dumps({
        "screen": {"x": 0, "y": 0, "w": H.W, "h": H.H}, "scale": float(H.S), "app": "Safari",
        "windows": [{"app": "Safari", "title": "Build a Python calculator", "rect": {"x": 0, "y": 0, "w": H.W, "h": H.H}}]}))
    return {"png": str(png), "browser": True}


def classify(rect: dict, fx: dict) -> str:
    """What a box covers on the frame it was placed on."""
    if fx.get("browser") or "truth" not in fx:
        return "over another app"
    cy = rect["y"] + rect["h"] / 2
    if cy < fx["top"]:
        return "tab/breadcrumb row"
    if fx.get("panel_y") and cy >= fx["panel_y"]:
        return "terminal panel"
    for n, row in fx["truth"].items():
        if abs(cy - (row["y"] + row["h"] / 2)) <= row["h"] / 2:
            return f"line {n}: {row['text']!r}" if row["text"].strip() else f"line {n}: EMPTY"
    return "below the last line (EMPTY)"


def target_row(step: dict, fx: dict) -> int | None:
    tgt = next((t.get("match") for t in step.get("targets") or [] if t.get("match")
                and (t.get("app") or "").lower() not in ("terminal", "iterm", "iterm2", "warp")), None)
    if not tgt or "truth" not in fx:
        return None
    return next((int(n) for n, v in fx["truth"].items() if tgt.strip() in v["text"]), None)


async def run(H, starter_kind: str, n_steps: int, hold: float) -> dict:
    lesson = json.loads(LESSON.read_text())
    work = H.SCRATCH / starter_kind
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    os.environ.update(H.OFFLINE_ENV)
    os.environ["TUT_WORKDIR"] = str(work)
    os.environ["TUT_SPOOL_DIR"] = str(H.RUNS / "boxes" / "tiger-spool")  # never the shared ~/.miyagi spool (uploads later)
    folder, file = work.name, H.code_file(lesson, 0)
    starter = STARTER if starter_kind == "seeded" else ""
    (work / file).write_text(starter + "\n" if starter else "")
    fx0 = H.render(f"{starter_kind}-start", folder, file, starter, panel=True, term=["% "])
    os.environ["TUT_SCREEN_FIXTURE"] = fx0["png"]

    for m in [m for m in list(sys.modules) if m.startswith("server.orchestrator")]:
        del sys.modules[m]
    main = importlib.import_module("server.orchestrator.main")
    try:
        from server.workspace import editor as s2_editor

        s2_editor._ax_editor_snapshot = lambda: None  # never read the real editor on this Mac
    except Exception:  # noqa: BLE001
        pass
    engine = main.engine
    engine.workspace.run = lambda argv: True  # never open VS Code
    t0 = time.monotonic()
    events: list[dict] = []
    cur = {"fx": fx0, "frame": f"{starter_kind}-start"}
    orig = engine.hub.emit

    async def emit(type_: str, payload: dict | None = None) -> None:
        payload = payload or {}
        events.append({"t": round(time.monotonic() - t0, 2), "type": type_, "payload": payload,
                       "frame": cur["frame"], "fx": cur["fx"]})
        await orig(type_, payload)

    engine.hub.emit = emit
    await engine.start()
    reader = getattr(engine.screen, "reader", None)
    graph = json.loads(json.dumps(lesson))
    graph["lesson"]["workdir"] = str(work)
    await engine.session.load_graph(graph)

    async def show(name: str, fx: dict) -> None:
        cur.update(fx=fx, frame=name)
        if reader is not None:
            reader.fixture = fx["png"]
            try:
                reader.poke("fixture", force=True)
            except TypeError:
                reader.poke("fixture")

    def editor(name: str, src: list[str], term: list[str]) -> dict:
        return H.render(name, folder, file, "\n".join(src), panel=True, term=term)

    src = starter.split("\n") if starter else []
    term = ["% "]
    steps_out = []
    steps = lesson["steps"][: n_steps or len(lesson["steps"])]
    for i, st in enumerate(steps):
        for _ in range(100):
            if engine.session.step is not None and engine.session.step["id"] == st["id"]:
                break
            await asyncio.sleep(0.1)
        if engine.session.step is None or engine.session.step["id"] != st["id"]:
            await engine.session.goto_step(i)
        kind = H.step_kind(st)
        n0 = len(events)
        before = editor(f"{starter_kind}-{st['id']}-before", src, term)
        await show(f"{starter_kind}-{st['id']}-before", before)
        await asyncio.sleep(hold)
        boxes = [e for e in events[n0:] if e["type"] == "spotlight" and e["payload"].get("rect")]
        want = target_row(st, before)
        steps_out.append({"step": st["id"], "title": st["title"], "kind": kind,
                          "target": next((t.get("match") for t in st.get("targets") or [] if t.get("match")), None),
                          "target_row": want, "file_lines": len(src),
                          "boxes": [{"at": b["t"], "covers": classify(b["payload"]["rect"], b["fx"]),
                                     "caption": b["payload"].get("caption")} for b in boxes]})
        if kind == "type":
            src = src + H.typed_code(st)
            (work / file).write_text("\n".join(src) + "\n")
        else:
            cmd = (st.get("code") or "python calculator.py").strip().splitlines()[0]
            term = term + [f"% {cmd}", "5", "% "]
        await show(f"{starter_kind}-{st['id']}-after", editor(f"{starter_kind}-{st['id']}-after", src, term))
        for _ in range(80):
            if engine.session.step is None or engine.session.step["id"] != st["id"]:
                break
            await asyncio.sleep(0.1)
        else:
            if i + 1 < len(steps):
                await engine.session.action("skip_step")

    away = await probe_away(H, engine, lesson, show, editor, work, file, starter, events) if starter_kind == "seeded" else {}
    await engine.session.end_lesson("rehearse_boxes")
    await asyncio.sleep(0.3)
    await engine.stop()
    if reader is not None:
        try:
            reader.stop()
        except Exception:  # noqa: BLE001
            pass
    return {"starter": starter_kind, "steps": steps_out, "away": away}


async def probe_away(H, engine, lesson, show, editor, work: Path, file: str, starter: str, events: list) -> dict:
    """App switching on the first typing step after s1 (the box points at a real line)."""
    idx = next(i for i, st in enumerate(lesson["steps"]) if H.step_kind(st) == "type" and i > 0)
    st, nxt = lesson["steps"][idx], lesson["steps"][idx + 1]
    base = starter.split("\n") + H.typed_code(lesson["steps"][0])
    (work / file).write_text("\n".join(base) + "\n")
    out: dict = {"step": st["id"], "next": nxt["id"]}

    async def phase(name: str, secs: float, fx: dict) -> list[dict]:
        n = len(events)
        await show(name, fx)
        await asyncio.sleep(secs)
        return events[n:]

    def spots(evs):
        return [e for e in evs if e["type"] == "spotlight"]

    await engine.session.goto_step(idx)
    ev = await phase("a-editor", 6, editor("a-editor", base, ["% "]))
    out["1_box_in_editor"] = [classify(e["payload"]["rect"], e["fx"]) for e in spots(ev) if e["payload"].get("rect")]
    ev = await phase("a-away", 4, H.render_other_app("a-away"))
    out["1_clear_when_away"] = any(e["payload"].get("clear") for e in spots(ev))
    out["1_box_while_away"] = [classify(e["payload"]["rect"], e["fx"]) for e in spots(ev) if e["payload"].get("rect")]
    ev = await phase("a-back", 6, editor("a-back", base, ["% "]))
    out["2_box_after_back"] = [classify(e["payload"]["rect"], e["fx"]) for e in spots(ev) if e["payload"].get("rect")]
    # (3) away again, and the step gets done in the background (the file is saved with the step's code)
    await phase("b-away", 3, H.render_other_app("b-away"))
    done = base + H.typed_code(st)
    (work / file).write_text("\n".join(done) + "\n")
    n = len(events)
    await asyncio.sleep(1.0)
    await engine.session.action("check_step")
    await asyncio.sleep(4.0)
    ev = events[n:]
    out["3_step_passed_while_away"] = any(e["type"] == "step.passed" and e["payload"].get("stepId") == st["id"] for e in ev)
    out["3_now_on"] = engine.session.step["id"] if engine.session.step else None
    out["3_box_while_away"] = [classify(e["payload"]["rect"], e["fx"]) for e in spots(ev) if e["payload"].get("rect")]
    back_fx = editor("b-back", done, ["% "])
    ev = await phase("b-back", 7, back_fx)
    out["3_boxes_after_back"] = [{"covers": classify(e["payload"]["rect"], e["fx"]), "caption": e["payload"].get("caption")}
                                 for e in spots(ev) if e["payload"].get("rect")]
    cur_step = engine.session.step or {}
    out["3_new_step_target_row"] = target_row(cur_step, back_fx) if cur_step else None
    # (4) a browser page showing this step's own code
    code_lines = [ln for ln in H.typed_code(cur_step) if ln.strip()][:6] or ["def add(a, b):", "    return a + b"]
    ev = await phase("c-browser", 6, render_browser(H, "c-browser", code_lines + ["# Step 1: Start building your calculator here"]))
    out["4_box_in_browser"] = [classify(e["payload"]["rect"], e["fx"]) for e in spots(ev) if e["payload"].get("rect")]
    out["4_cleared"] = any(e["payload"].get("clear") for e in spots(ev))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--starter", choices=["empty", "seeded"], help="one starter only (default: both, one process each)")
    ap.add_argument("--steps", type=int, default=0, help="first N steps only (0 = all)")
    ap.add_argument("--hold", type=float, default=6.0, help="seconds each before-screen is held")
    ap.add_argument("--out", type=Path, default=ROOT / "demo" / "runs" / "boxes" / "boxes.jsonl")
    args = ap.parse_args()
    if not args.starter:  # the screen reader is a process-wide singleton: one process per starter
        for kind in ("empty", "seeded"):
            subprocess.run([sys.executable, __file__, "--starter", kind, "--steps", str(args.steps),
                            "--hold", str(args.hold), "--out", str(args.out)], check=False)
        return 0
    H = load_harness()
    res = asyncio.run(run(H, args.starter, args.steps, args.hold))
    print(f"\n=== starter: {args.starter}")
    for s in res["steps"]:
        print(f"  {s['step']} [{s['kind']}] {s['title']!r} target {s['target']!r} (row {s['target_row']}, file has "
              f"{s['file_lines']} lines)")
        for b in s["boxes"] or [{"covers": "NO BOX", "caption": None, "at": None}]:
            print(f"      box → {b['covers']}   caption {b['caption']!r}")
    if res["away"]:
        print("  app switching:", json.dumps(res["away"], ensure_ascii=False, indent=1))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **res}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
