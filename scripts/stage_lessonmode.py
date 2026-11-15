#!/usr/bin/env python3
"""Offline acceptance check for "Just teach me" (lesson mode) lessons. ZERO API calls.

  .venv/bin/python scripts/stage_lessonmode.py [--lesson text-XXXX.json] [--hold 22] [--only open|closed]

How it runs:
  * The real orchestrator Engine runs IN THIS PROCESS (no port), DEMO=1, finder/lesson/diagrams stubbed. The coach
    is real but has no key, and every API key is blanked and HTTP(S) goes to a dead proxy, so any network call
    fails instead of costing money.
  * The screen is the real ScreenReader on rendered VS Code screenshots (OCR'd locally by Apple Vision). For each
    step this renders the editor BEFORE the step (holds it --hold s), then AFTER it (the step's code typed, or the
    command's output in the terminal), so the engine sees the learner work. Two scenarios:
      open    the integrated terminal panel is open; the file is saved after every typing step
      closed  the terminal panel is closed; the file is NOT saved before the first run step (tests (d))
  * The editor is never really opened: the Workspace runner is replaced by a recorder (tests (e)), and S2's
    Accessibility snapshot is stubbed out so nothing reads the real editor on this Mac.

Asserts, per step:
  (a) one spotlight per step; re-sent only if the target moved > 12 px; at most one per 2 s
  (b) run step: the spotlight is on the terminal panel (open), or something says "Open the terminal: ⌃`" (closed);
      typing step: the spotlight is on the target code line; never on the tab/breadcrumb rows
  (c) no offtrack / auto-card in the first 20 s of a step; never two cards within 8 s
  (d) a run step never starts while its file is empty (on disk)
  (e) the editor is opened once per lesson, never `-n` twice, never Cursor
  (f) step instructions: one sentence, <= 10 words, no absolute paths, no mkdir
plus: the "I can't see your screen" card comes within 1 s of show_me when capture is down.
Writes demo/runs/stage-lessonmode.jsonl and prints PASS/FAIL per item.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "demo" / "runs"
FIXDIR = RUNS / "stage-fixtures"
SCRATCH = RUNS / "stage-lessonmode-work"

# ---------------------------------------------------------------- offline env (BEFORE importing the engine)
OFFLINE_ENV = {
    "DEMO": "1", "ORCH_STUBS": "diagrams,finder,lesson", "ORCH_AUTOSTART": "0", "ORCH_SCREEN": "1", "TUT_AX": "0",
    "ORCH_OPEN_WORKSPACE": "1", "ORCH_RECORD": "0", "ORCH_DIAGRAM_PREFETCH": "0",
    "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "", "BRIGHTDATA_API_KEY": "", "ELEVENLABS_API_KEY": "",
    "TIGER_DATABASE_URL": "", "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9",
    "ALL_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
}

RUN_APPS = {"terminal", "iterm", "iterm2", "warp"}
TERMINAL_HINT = re.compile(r"open the terminal", re.I)
SHELL_CMD = re.compile(r"^\s*(python3?|node|npm|npx|pip3?|git|cargo|go|deno|bun|yarn|pnpm|ruby|java|bash|sh|\./)\b")
CTRL_BACKTICK = re.compile(r"⌃\s*`|ctrl\s*\+?\s*`", re.I)


# ---------------------------------------------------------------- fixture renderer (after E6's make_editor_fixtures)
W, H, S = 1728, 1117, 2
MENLO = "/System/Library/Fonts/Menlo.ttc"
UI = "/System/Library/Fonts/SFNS.ttf"
GEO = {"act_w": 48, "side_w": 252, "tabs_h": 35, "crumbs_h": 22, "status_h": 22, "panel_y": 800, "line_h": 18.0,
       "font": 12.0}


def render_other_app(name: str, app: str = "Safari", title: str = "Google") -> dict:
    """A plain browser window in front (VS Code not frontmost)."""
    from PIL import Image, ImageDraw, ImageFont

    FIXDIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (W * S, H * S), (250, 250, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W * S, 80 * S], fill=(230, 230, 230))
    d.text((40 * S, 30 * S), "https://www.google.com", font=ImageFont.truetype(UI, 14 * S), fill=(40, 40, 40))
    d.text((600 * S, 400 * S), "Search the web", font=ImageFont.truetype(UI, 28 * S), fill=(60, 60, 60))
    png = FIXDIR / f"{name}.png"
    img.save(png, optimize=True)
    (FIXDIR / f"{name}.json").write_text(json.dumps({
        "screen": {"x": 0, "y": 0, "w": W, "h": H}, "scale": float(S), "app": app,
        "windows": [{"app": app, "title": title, "rect": {"x": 0, "y": 0, "w": W, "h": H}}]}))
    return {"png": str(png)}


def render(name: str, folder: str, file: str, src: str, *, panel: bool, term: list[str], dirty: bool = False,
           title_folder: str | None = None) -> dict:
    """VS Code full screen (Dark+): explorer, one tab, breadcrumb, gutter + code, optional terminal panel.
    Writes <name>.png + sidecar <name>.json; returns geometry + per-line truth rows (screen points)."""
    from PIL import Image, ImageDraw, ImageFont

    FIXDIR.mkdir(parents=True, exist_ok=True)
    g = GEO
    img = Image.new("RGB", (W * S, H * S), (30, 30, 30))
    d = ImageDraw.Draw(img)
    P = lambda v: round(v * S)  # noqa: E731
    mono = ImageFont.truetype(MENLO, P(g["font"]))
    ui = ImageFont.truetype(UI, P(12))
    ui_small = ImageFont.truetype(UI, P(11))
    ex = g["act_w"] + g["side_w"]
    top = g["tabs_h"] + g["crumbs_h"]
    status_y = H - g["status_h"]
    panel_y = g["panel_y"] if panel else status_y
    gutter_right = ex + 6 + 5 * g["font"] * 0.6 + 8
    code_x = gutter_right + 26
    text_right = W - 124
    d.rectangle([0, 0, P(g["act_w"]), P(H)], fill=(51, 51, 51))
    d.rectangle([P(g["act_w"]), 0, P(ex), P(H)], fill=(37, 37, 38))
    d.text((P(g["act_w"] + 20), P(12)), "EXPLORER", font=ui_small, fill=(150, 150, 150))
    d.text((P(g["act_w"] + 12), P(40)), folder.upper()[:28], font=ui_small, fill=(204, 204, 204))
    d.text((P(g["act_w"] + 28), P(64)), file, font=ui, fill=(204, 204, 204))
    d.rectangle([P(ex), 0, P(W), P(g["tabs_h"])], fill=(45, 45, 45))
    tab = f"{file}  ●" if dirty else file
    shown_folder = title_folder or folder
    tw = 40 + len(tab) * 7.2
    d.rectangle([P(ex), 0, P(ex + tw), P(g["tabs_h"])], fill=(30, 30, 30))
    d.text((P(ex + 14), P(10)), tab, font=ui, fill=(204, 204, 204))
    d.text((P(ex + 14), P(g["tabs_h"] + 4)), f"{shown_folder}  ›  {file}", font=ui_small, fill=(150, 150, 150))
    lines = src.split("\n") if src else [""]
    truth = {}
    rows = int((panel_y - top) // g["line_h"])
    for k in range(min(rows, len(lines))):
        n = k + 1
        y = top + k * g["line_h"]
        ty = y + (g["line_h"] - g["font"] * 1.17) / 2
        num = str(n)
        d.text((P(gutter_right - d.textlength(num, font=mono) / S), P(ty)), num, font=mono, fill=(133, 133, 133))
        d.text((P(code_x), P(ty)), lines[k], font=mono, fill=(212, 212, 212))
        truth[n] = {"y": y, "h": g["line_h"], "text": lines[k]}
    if panel:
        d.rectangle([P(ex), P(panel_y), P(W), P(status_y)], fill=(30, 30, 30))
        d.line([P(ex), P(panel_y), P(W), P(panel_y)], fill=(70, 70, 70), width=2)
        d.text((P(ex + 14), P(panel_y + 8)), "PROBLEMS    OUTPUT    DEBUG CONSOLE    TERMINAL    PORTS",
               font=ui_small, fill=(204, 204, 204))
        for i, t in enumerate(term[:12]):
            d.text((P(ex + 14), P(panel_y + 36 + i * 17)), t, font=ImageFont.truetype(MENLO, P(12)), fill=(212, 212, 212))
    d.rectangle([0, P(status_y), P(W), P(H)], fill=(0, 122, 204))
    d.text((P(W - 520), P(status_y + 4)), "Ln 1, Col 1    Spaces: 4    UTF-8    LF    Python",
           font=ui_small, fill=(255, 255, 255))
    png = FIXDIR / f"{name}.png"
    img.save(png, optimize=True)
    (FIXDIR / f"{name}.json").write_text(json.dumps({
        "screen": {"x": 0, "y": 0, "w": W, "h": H}, "scale": float(S), "app": "Code",
        "windows": [{"app": "Code", "title": f"{'● ' if dirty else ''}{file} — {shown_folder}",
                     "rect": {"x": 0, "y": 0, "w": W, "h": H}}]}))
    return {"png": str(png), "top": top, "panel_y": panel_y if panel else None, "editor_x": ex,
            "gutter_right": gutter_right, "truth": truth}


# ---------------------------------------------------------------- lesson model
def step_kind(step: dict) -> str:
    """run = the learner runs a command (file "(terminal)", or the first target is a terminal); else type."""
    if (step.get("file") or "").strip() == "(terminal)":
        return "run"
    first = next(iter(step.get("targets") or []), {})
    if (first.get("app") or "").lower() in RUN_APPS:
        return "run"
    code = (step.get("code") or "").strip().splitlines()
    if len(code) == 1 and SHELL_CMD.match(code[0]):  # E2 sometimes files a command under the code file
        return "run"
    return "type"


def code_file(lesson: dict, upto: int) -> str:
    """The code file a step works on: its own file, else the last typing step's file before it."""
    steps = lesson["steps"]
    for st in reversed(steps[: upto + 1]):
        f = (st.get("file") or "").strip()
        if f and f != "(terminal)":
            return f
    for t in steps[upto].get("targets") or []:
        if (t.get("file") or "") not in ("", "(terminal)"):
            return t["file"]
    return "main.py"


def typed_code(step: dict) -> list[str]:
    out = []
    for ln in (step.get("code") or "").split("\n"):
        s = ln.strip()
        if s.startswith("# (") or s.lower().startswith("# at the bottom") or s.lower().startswith("# place"):
            continue
        out.append(ln)
    while out and not out[-1].strip():
        out.pop()
    return out


# ---------------------------------------------------------------- the run
class Recorder:
    def __init__(self, workdir: Path):
        self.t0 = time.monotonic()
        self.events: list[dict] = []
        self.argv: list[list[str]] = []
        self.workdir = workdir

    def now(self) -> float:
        return round(time.monotonic() - self.t0, 2)


async def run_scenario(lesson_path: Path, scenario: str, hold: float) -> dict:
    lesson = json.loads(lesson_path.read_text())
    workdir = SCRATCH / scenario
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True)
    os.environ.update(OFFLINE_ENV)
    os.environ["TUT_WORKDIR"] = str(workdir)
    folder = workdir.name
    first_file = code_file(lesson, 0)
    starter = "# Write your code below" if any("# Write your code below" in (t.get("match") or "")
                                              for s in lesson["steps"] for t in s.get("targets") or []) else ""
    fx0 = render(f"{scenario}-start", folder, first_file, starter, panel=scenario == "open", term=["% "])
    os.environ["TUT_SCREEN_FIXTURE"] = fx0["png"]

    sys.path.insert(0, str(ROOT))
    import importlib

    for m in [m for m in list(sys.modules) if m.startswith("server.orchestrator")]:
        del sys.modules[m]
    main = importlib.import_module("server.orchestrator.main")
    try:
        from server.workspace import editor as s2_editor

        s2_editor._ax_editor_snapshot = lambda: None  # never read the real editor on this Mac
    except Exception:  # noqa: BLE001
        pass
    engine = main.engine
    # S2's wrong_folder() reads the REAL VS Code windows on this Mac: off, so E4's window-title fallback reads the fixture
    engine.session._s2_wrong_folder_fn = lambda: None
    rec = Recorder(workdir)
    disk = {"save": scenario == "open"}

    def fake_run(argv: list[str]) -> bool:
        rec.argv.append([str(a) for a in argv])
        return True

    engine.workspace.run = fake_run
    orig_emit = engine.hub.emit
    cur = {"step": None}

    async def emit(type_: str, payload: dict | None = None) -> None:
        payload = payload or {}
        ev = {"t": rec.now(), "type": type_, "payload": payload}
        if type_ == "step.started":
            idx = next((i for i, s in enumerate(lesson["steps"]) if s["id"] == payload.get("stepId")), None)
            f = workdir / code_file(lesson, idx or 0)
            ev["file_bytes"] = f.stat().st_size if f.is_file() else None
            ev["file"] = f.name
            cur["step"] = payload.get("stepId")
        ev["step"] = cur["step"]
        rec.events.append(ev)
        await orig_emit(type_, payload)

    engine.hub.emit = emit
    await engine.start()
    reader = getattr(engine.screen, "reader", None)
    print(f"  engine up · modules {engine.modules.describe()} · screen {engine.session.screen_active()} · workdir {workdir}")
    if starter and disk["save"]:
        (workdir / first_file).write_text(starter + "\n")

    graph = json.loads(json.dumps(lesson))
    graph["lesson"]["workdir"] = str(workdir)
    await engine.session.load_graph(graph)

    src_lines = [starter] if starter else []
    term = ["% "]
    geo_by_step: dict[str, dict] = {}
    forced: list[str] = []

    async def show(name: str, src: list[str], term_lines: list[str], file: str, *, fx: dict | None = None, **kw) -> dict:
        fx = fx or render(name, folder, file, "\n".join(src), panel=scenario == "open", term=term_lines, **kw)
        if reader is not None:
            reader.fixture = fx["png"]
            try:
                reader.poke("fixture", force=True)
            except TypeError:
                reader.poke("fixture")
        return fx

    for i, st in enumerate(lesson["steps"]):
        # wait for the engine to start this step
        for _ in range(100):
            if engine.session.step is not None and engine.session.step["id"] == st["id"]:
                break
            await asyncio.sleep(0.1)
        if engine.session.step is None or engine.session.step["id"] != st["id"]:
            await engine.session.goto_step(i)
            forced.append(f"{st['id']} (start)")
        kind = step_kind(st)
        file = code_file(lesson, i)
        before = await show(f"{scenario}-{st['id']}-before", src_lines, term, file)
        geo_by_step[st["id"]] = {"kind": kind, "before": before, "src": list(src_lines)}
        print(f"  {st['id']} [{kind}] {st['title']!r} · holding {hold:.0f} s")
        await asyncio.sleep(hold)
        # the learner does the step
        if kind == "type":
            src_lines = src_lines + typed_code(st)
            if disk["save"]:
                (workdir / file).write_text("\n".join(src_lines) + "\n")
        else:
            cmd = (st.get("code") or "python main.py").strip().splitlines()[0]
            out = [ln for st2 in lesson["steps"][:i] for ln in typed_code(st2) if ln.strip().startswith("print(")]
            term = term + [f"% {cmd}"] + [re.sub(r'^print\((["\'])(.*)\1\)$', r"\2", o.strip()) for o in out[:3]] + ["% "]
            if scenario == "closed" and not disk["save"]:  # from now on the learner saves
                disk["save"] = True
                (workdir / file).write_text("\n".join(src_lines) + "\n")
        await show(f"{scenario}-{st['id']}-after", src_lines, term, file)
        if scenario == "closed" and i == 0 and kind == "type":
            pass  # (d): calculator.py stays empty on disk until the first run step is done
        moved = False
        for _ in range(120):
            if engine.session.step is None or engine.session.step["id"] != st["id"]:
                moved = True
                break
            await asyncio.sleep(0.1)
        if not moved and i + 1 < len(lesson["steps"]):
            forced.append(st["id"])
            rec.events.append({"t": rec.now(), "type": "_skip", "payload": {}, "step": st["id"]})
            await engine.session.action("skip_step")  # what a learner presses to move on

    extras = await run_extras(engine, lesson, rec, show, render, workdir, folder, starter) if scenario == "open" else {}

    # screen-down: show_me must answer at once
    down = {}
    if reader is not None:
        reader.fixture = str(FIXDIR / "does-not-exist.png")
        try:
            reader.poke("fixture", force=True)
        except TypeError:
            reader.poke("fixture")
        await asyncio.sleep(7)
        n = len(rec.events)
        t_send = rec.now()
        await engine.session.action("show_me")
        await asyncio.sleep(3)
        card = next((e for e in rec.events[n:] if e["type"] == "card" and "see your screen" in json.dumps(e["payload"])), None)
        down = {"reason": engine.session.screen_down_reason(), "card_after_s": round(card["t"] - t_send, 2) if card else None}
    await engine.session.end_lesson("stage_lessonmode")
    await asyncio.sleep(0.5)
    await engine.stop()
    if reader is not None:
        try:
            reader.stop()
        except Exception:  # noqa: BLE001
            pass
    return {"scenario": scenario, "lesson": lesson, "events": rec.events, "argv": rec.argv, "geo": geo_by_step,
            "forced": forced, "screen_down": down, "extras": extras}


async def run_extras(engine, lesson, rec, show, render_fn, workdir: Path, folder: str, starter: str) -> dict:
    """New round-2 behaviours, on a typing step that isn't done yet (only the starter line is on screen, so the
    coach gate opens): (g) the box clears when VS Code isn't frontmost and comes back; (h) an unsaved file
    (● in the title) gets "Save with ⌘S" and no off-track; (i) the file open from another lesson's folder gets
    one calm card with open_editor and no off-track."""
    out: dict = {}
    idx = next((i for i, st in enumerate(lesson["steps"]) if step_kind(st) == "type" and i > 0), 0)
    st = lesson["steps"][idx]
    file = code_file(lesson, idx)
    base = [starter] if starter else []
    (workdir / file).write_text("\n".join(base) + "\n")

    async def phase(name: str, secs: float, **show_kw) -> list[dict]:
        n = len(rec.events)
        t = rec.now()
        await show(name, base, ["% "], file, **show_kw)
        await asyncio.sleep(secs)
        return [{**e, "dt": round(e["t"] - t, 2)} for e in rec.events[n:]]

    await engine.session.goto_step(idx)
    await asyncio.sleep(1.0)
    ev0 = await phase("x-editor", 6)
    out["step"] = st["id"]
    out["box_before"] = [e["payload"].get("rect") for e in ev0 if e["type"] == "spotlight" and e["payload"].get("rect")]
    ev1 = await phase("x-away", 5, fx=render_other_app("x-away"))
    clr = next((e for e in ev1 if e["type"] == "spotlight" and e["payload"].get("clear")), None)
    out["g_clear_after_s"] = clr["dt"] if clr else None
    ev2 = await phase("x-back", 6)
    back = next((e for e in ev2 if e["type"] == "spotlight" and e["payload"].get("rect")), None)
    out["g_rebox_after_s"] = back["dt"] if back else None
    ev3 = await phase("x-dirty", 14, dirty=True)
    save = next((e for e in ev3 if e["type"] == "card" and "⌘S" in json.dumps(e["payload"], ensure_ascii=False)), None)
    out["h_save_card_after_s"] = save["dt"] if save else None
    out["h_save_card"] = (save or {}).get("payload", {}).get("title")
    out["h_offtrack"] = [e["payload"].get("title") for e in ev3 if e["type"] == "offtrack"]
    ev4 = await phase("x-otherfolder", 14, title_folder="some-other-lesson")
    wf = next((e for e in ev4 if e["type"] == "card" and "open_editor" in (e["payload"].get("actions") or [])), None)
    out["i_card_after_s"] = wf["dt"] if wf else None
    out["i_card"] = (wf or {}).get("payload", {}).get("title")
    out["i_offtrack"] = [e["payload"].get("title") for e in ev4 if e["type"] == "offtrack"]
    out["i_cards"] = [e["payload"].get("title") for e in ev4 if e["type"] == "card"]
    return out


# ---------------------------------------------------------------- assertions
def judge(res: dict) -> dict:
    lesson, events, geo = res["lesson"], res["events"], res["geo"]
    scen = res["scenario"]
    items = {k: [] for k in "abcdefj"}
    rows = []
    starts = [e for e in events if e["type"] == "step.started"]
    for si, se in enumerate(starts):
        sid = se["payload"]["stepId"]
        st = next(s for s in lesson["steps"] if s["id"] == sid)
        g = geo.get(sid) or {}
        kind = g.get("kind", step_kind(st))
        t0 = se["t"]
        t1 = starts[si + 1]["t"] if si + 1 < len(starts) else events[-1]["t"]
        evs = [e for e in events if t0 <= e["t"] < t1 and e is not se]
        spots = [e for e in evs if e["type"] == "spotlight" and e["payload"].get("rect")]
        cards = [e for e in evs if e["type"] in ("card", "offtrack")
                 and (e["payload"].get("kind") not in ("setup", "preflight", "resume"))
                 and not re.search(r"is still empty", e["payload"].get("title") or "")]  # answer to the learner's Skip
        row = {"step": sid, "kind": kind, "spots": len(spots), "cards": [(round(e["t"] - t0, 1), e["type"],
               e["payload"].get("kind"), (e["payload"].get("title") or "")[:40]) for e in cards]}
        row["after_skip"] = any(e["type"] == "_skip" for e in events if t0 - 1.0 <= e["t"] <= t0)
        # (a)
        prob_a = []
        if not spots and t1 - t0 >= 6.0:  # a step that was up for less than 6 s (redirected / skipped) isn't judged
            prob_a.append("no spotlight")
        for a, b in zip(spots, spots[1:]):
            ra, rb = a["payload"]["rect"], b["payload"]["rect"]
            move = max(abs(ra["x"] - rb["x"]), abs(ra["y"] - rb["y"]), abs(ra["w"] - rb["w"]), abs(ra["h"] - rb["h"]))
            if move <= 12:
                prob_a.append(f"re-sent at +{b['t'] - t0:.1f}s though it moved {move:.0f}px")
            if b["t"] - a["t"] < 2.0:
                prob_a.append(f"two spotlights {b['t'] - a['t']:.1f}s apart")
        items["a"] += [f"{sid}: {p}" for p in prob_a]
        # (b)
        prob_b = []
        before = g.get("before") or {}
        top = before.get("top", 57)
        for sp in spots:
            r = sp["payload"]["rect"]
            cy = r["y"] + r["h"] / 2
            if cy < top:
                prob_b.append(f"boxes the tab/breadcrumb row ({r})")
        if kind == "run":
            if scen == "open":
                py = before.get("panel_y") or 800
                if spots and not any(sp["payload"]["rect"]["y"] + sp["payload"]["rect"]["h"] / 2 >= py for sp in spots):
                    prob_b.append(f"run step not boxing the terminal panel (rects {[sp['payload']['rect'] for sp in spots]})")
            else:
                texts = " ".join(json.dumps(e["payload"], ensure_ascii=False) for e in evs + [se])
                if not (TERMINAL_HINT.search(texts) and CTRL_BACKTICK.search(texts)):
                    prob_b.append("terminal closed, but nothing says \"Open the terminal: ⌃`\"")
        else:
            tgt = next((t.get("match") for t in st.get("targets") or [] if t.get("match")
                        and (t.get("app") or "").lower() not in RUN_APPS), None)
            truth = before.get("truth") or {}
            ln = next((int(n) for n, v in truth.items() if tgt and tgt.strip() and tgt.strip() in v["text"]), None)
            if spots and ln is not None:
                ok_rows = [truth.get(str(k)) or truth.get(k) for k in range(ln, ln + 3)]
                ok_rows = [r for r in ok_rows if r]
                hit = any(any(abs((sp["payload"]["rect"]["y"] + sp["payload"]["rect"]["h"] / 2) - (r["y"] + r["h"] / 2)) <= r["h"]
                              for r in ok_rows) for sp in spots)
                if not hit:
                    prob_b.append(f"typing step box not on target line {ln} {tgt!r} (rects {[sp['payload']['rect'] for sp in spots]})")
            elif spots and ln is None:
                row["note_b"] = f"target {tgt!r} not on the before-screen; box not judged"
        items["b"] += [f"{sid}: {p}" for p in prob_b]
        # (c)
        prob_c = [f"{c[1]} {c[2] or ''} {c[3]!r} at +{c[0]}s" for c in row["cards"] if c[0] < 20.0]
        for a, b in zip(cards, cards[1:]):
            if b["t"] - a["t"] < 8.0:
                prob_c.append(f"two cards {b['t'] - a['t']:.1f}s apart")
        items["c"] += [f"{sid}: {p}" for p in prob_c]
        # (d)
        if kind == "run" and not se.get("file_bytes"):
            items["d"].append(f"{sid}: run step started while {se.get('file')} is {'empty' if se.get('file_bytes') == 0 else 'missing'}")
        # (j) the first help card of the step offers "Do it for me" (apply_fix)
        help_cards = [e for e in cards if e["type"] == "offtrack" or (
            e["payload"].get("kind") == "hint" and not re.match(r"(Looks done|I can't see|Save |That's another|Wrong folder|.* is still empty)",
                                                                e["payload"].get("title") or ""))]
        want = {"apply_fix", "run_command"} if kind == "run" else {"apply_fix"}  # Do it for me / Run it for me
        if help_cards and not want & set(help_cards[0]["payload"].get("actions") or []):
            items.setdefault("j", []).append(f"{sid}: first help card {help_cards[0]['payload'].get('title')!r} "
                                             f"has actions {help_cards[0]['payload'].get('actions')}")
        row["first_help_card"] = (help_cards[0]["payload"].get("title"), help_cards[0]["payload"].get("actions")) if help_cards else None
        # (f)
        ins = se["payload"].get("instructions") or ""
        words = ins.split()
        sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", ins.strip()) if s]
        prob_f = []
        if len(sentences) > 1:
            prob_f.append(f"{len(sentences)} sentences")
        if len(words) > 10:
            prob_f.append(f"{len(words)} words")
        if re.search(r"(^|[\s\"'`(])/(Users|home|tmp|var|private|opt)/", ins):
            prob_f.append("absolute path")
        if re.search(r"\bmkdir\b", ins):
            prob_f.append("mkdir")
        if prob_f:
            items["f"].append(f"{sid}: {', '.join(prob_f)}: {ins!r}")
        row.update({"instructions": ins, "problems": {"a": prob_a, "b": prob_b, "c": prob_c, "f": prob_f}})
        rows.append(row)
    # (e)
    argv = res["argv"]
    wd = str(SCRATCH)
    opens = [a for a in argv if not any(x in ("-g", "--goto") for x in a) and any(x.startswith(wd) for x in a[1:])]
    activations = [a for a in argv if a[:2] == ["open", "-a"] and not any(x.startswith(wd) for x in a[2:])]
    gotos = [a for a in argv if "-g" in a or "--goto" in a]
    n_flag = sum(1 for a in argv if "-n" in a or "--new-window" in a)
    if len(opens) != 1:
        items["e"].append(f"editor opened {len(opens)}x: {opens}")
    if n_flag > 1:
        items["e"].append(f"`-n` used {n_flag}x")
    if any(re.search(r"cursor", " ".join(a), re.I) for a in argv):
        items["e"].append("Cursor in a command: " + str([a for a in argv if re.search(r'cursor', ' '.join(a), re.I)]))
    x = res.get("extras") or {}
    if x:
        items["g"] = [] if (x.get("g_clear_after_s") is not None and x["g_clear_after_s"] <= 2.0) else [
            f"{x.get('step')}: no spotlight clear within 2 s of another app in front (got {x.get('g_clear_after_s')})"]
        if x.get("g_rebox_after_s") is None:
            items["g"].append(f"{x.get('step')}: no new box after VS Code came back")
        items["h"] = ([] if x.get("h_save_card_after_s") is not None else [f"{x.get('step')}: no ⌘S card for an unsaved file"]) + (
            [f"off-track while unsaved: {x['h_offtrack']}"] if x.get("h_offtrack") else [])
        items["i"] = ([] if x.get("i_card_after_s") is not None else [f"{x.get('step')}: no open_editor card for another lesson's folder "
                                                                      f"(cards {x.get('i_cards')})"]) + (
            [f"off-track in the wrong folder: {x['i_offtrack']}"] if x.get("i_offtrack") else [])
    return {"items": items, "rows": rows, "opens": opens, "activations": activations, "gotos": len(gotos), "argv": argv}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lesson", help="a cached text lesson (default: newest demo/cache/lessons/text-*.json, "
                    "else the run-live worktree's)")
    ap.add_argument("--hold", type=float, default=22.0, help="seconds the before-screen is held per step")
    ap.add_argument("--only", choices=["open", "closed"])
    args = ap.parse_args()
    if args.lesson:
        lp = Path(args.lesson)
    else:
        cands = sorted((ROOT / "demo/cache/lessons").glob("text-*.json"), key=lambda p: p.stat().st_mtime)
        cands = cands or sorted((ROOT.parent / "run-live/demo/cache/lessons").glob("text-*.json"),
                                key=lambda p: p.stat().st_mtime)
        if not cands:
            sys.exit("no text-*.json lesson found")
        lp = cands[-1]
    head = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%h %s"], capture_output=True, text=True).stdout.strip()
    live = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "origin/integration/live"],
                          capture_output=True, text=True).stdout.strip()
    if args.only:
        print(f"lesson {lp.name} · code {head} (origin/integration/live {live})", flush=True)
    if not args.only:  # each scenario in its own process (the screen reader is a process-wide singleton)
        for scen in ("open", "closed"):
            subprocess.run([sys.executable, __file__, "--lesson", str(lp), "--hold", str(args.hold), "--only", scen],
                           check=False)
        return
    out = []
    for scen in [args.only]:
        print(f"\n=== scenario: terminal {scen}")
        res = asyncio.run(run_scenario(lp, scen, args.hold))
        j = judge(res)
        for r in j["rows"]:
            bad = {k: v for k, v in r["problems"].items() if v}
            print(f"  {r['step']} [{r['kind']}] spots={r['spots']} cards={r['cards']} instr={r['instructions']!r}"
                  + (f"\n      {bad}" if bad else "") + (f"\n      note: {r['note_b']}" if r.get("note_b") else ""))
        print(f"  editor commands: opens={j['opens']} activations(open -a, no folder)={len(j['activations'])} gotos(-g)={j['gotos']}")
        print(f"  forced step changes (engine didn't advance by itself): {res['forced']}")
        print(f"  screen down: {res['screen_down']}")
        if res.get("extras"):
            print(f"  extras: {res['extras']}")
        verdict = {k: ("PASS" if not v else "FAIL") for k, v in j["items"].items()}
        sd = res["screen_down"].get("card_after_s")
        verdict["screen-down card ≤ 1 s"] = "PASS" if sd is not None and sd <= 1.0 else f"FAIL ({sd})"
        for k, v in verdict.items():
            print(f"  ({k}) {v}" + ("" if v == "PASS" or k not in j["items"] else "\n      " + "\n      ".join(j["items"][k][:8])))
        out.append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "code": head, "live": live, "lesson": lp.name,
                    "scenario": scen, "verdict": verdict, "items": j["items"], "rows": j["rows"], "argv": j["argv"],
                    "forced": res["forced"], "screen_down": res["screen_down"]})
    RUNS.mkdir(parents=True, exist_ok=True)
    with (RUNS / "stage-lessonmode.jsonl").open("a") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
