#!/usr/bin/env python3
"""LIVE tier of the "Just teach me" acceptance check: fresh text-lesson builds on the real Claude key, then the
first steps driven on rendered VS Code screens. Gemini is off; Michael's screen and :8787 are never touched.

  .venv/bin/python scripts/stage_lessonmode_live.py                      # the 2 default topics = one round
  .venv/bin/python scripts/stage_lessonmode_live.py --topic "make a snake game in python" --budget 1.0

Per topic (each in its own process; the round's spend is carried over and capped by --budget, default $1):
  * the real Engine in-process (also served on 127.0.0.1:8790), LESSON_ENGINE=claude, GEMINI/GOOGLE keys blanked,
    finder/diagrams stubbed, Bright Data / ElevenLabs / Tiger off; the editor never opens (recorded); S2's
    Accessibility snapshot stubbed; the screen is the real ScreenReader on rendered fixtures (local Vision OCR)
  * `learn {mode: "lesson"}` -> times to the first step and the full lesson, build stages, lesson.builtBy
  * E2's rules on the built steps (textlesson.py: step 1 types code, runs after their code, one short sentence,
    no abs paths / setup commands, run steps "Run your X in the terminal." with a file check, typing steps
    checked for their code, schema-valid)
  * steps 1-3 driven like the offline tier (before 22 s / after), judged with the same items (a)-(j)
  * every Anthropic call's usage (SDK hook): tokens by model and by caller module, $ estimate; stops over budget
Prices ($/MTok, claude-api reference 2026-11-03): Opus 5.5 4/20 (cache read 0.20), Sonnet 5.5 2/10 (0.10),
Haiku 5.5 0.10/0.50; cache writes 1.25x input; fast mode 2x; web search assumed $10 per 1,000.
Writes demo/runs/stage-lessonmode-live.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_lessonmode as L  # noqa: E402

ROOT, RUNS = L.ROOT, L.RUNS
TOPICS = ["build a to-do list app in python", "make a number guessing game in python"]
PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20), "claude-sonnet-5-5": (2.0, 10.0, 0.10), "claude-haiku-5-5": (0.10, 0.50, 0.01)}
WEB_SEARCH_USD = 10.0 / 1000
STEPS_DRIVEN = 3


# ---------------------------------------------------------------- usage hook
class Usage:
    def __init__(self, budget: float):
        self.budget, self.calls, self.over, self._seen = budget, [], False, set()

    @staticmethod
    def price(model: str) -> tuple[float, float, float]:
        for k, v in PRICES.items():
            if model.startswith(k):
                return v
        return PRICES["claude-opus-5-5"]  # unknown: price it like the most expensive model in use

    @staticmethod
    def caller() -> str:
        srv = str(ROOT / "server")
        frames = [f for f in traceback.extract_stack() if f.filename.startswith(srv)]
        return os.path.relpath(frames[-1].filename, ROOT) if frames else "?"

    def add(self, msg) -> None:
        if msg is None or id(msg) in self._seen:
            return
        u = getattr(msg, "usage", None)
        if u is None:
            return
        self._seen.add(id(msg))
        model = str(getattr(msg, "model", "") or "")
        i, o = int(getattr(u, "input_tokens", 0) or 0), int(getattr(u, "output_tokens", 0) or 0)
        cw, cr = int(getattr(u, "cache_creation_input_tokens", 0) or 0), int(getattr(u, "cache_read_input_tokens", 0) or 0)
        stu = getattr(u, "server_tool_use", None)
        ws = int(getattr(stu, "web_search_requests", 0) or 0) if stu is not None else 0
        wf = int(getattr(stu, "web_fetch_requests", 0) or 0) if stu is not None else 0
        fast = getattr(u, "speed", None) == "fast"
        p = self.price(model)
        usd = (2 if fast else 1) * (i * p[0] + o * p[1] + cr * p[2] + cw * p[0] * 1.25) / 1e6 + ws * WEB_SEARCH_USD
        self.calls.append({"model": model, "in": i, "out": o, "cache_write": cw, "cache_read": cr, "web_search": ws,
                           "web_fetch": wf, "fast": fast, "usd": round(usd, 5), "caller": self.caller()})
        if self.total() > self.budget:
            self.over = True

    def total(self) -> float:
        return round(sum(c["usd"] for c in self.calls), 4)

    def summary(self) -> dict:
        by_model, by_caller = {}, {}
        for c in self.calls:
            m = by_model.setdefault(c["model"], {"calls": 0, "in": 0, "out": 0, "cache_write": 0, "cache_read": 0, "usd": 0.0})
            for k in ("in", "out", "cache_write", "cache_read"):
                m[k] += c[k]
            m["calls"] += 1
            m["usd"] = round(m["usd"] + c["usd"], 4)
            b = by_caller.setdefault(c["caller"], {"calls": 0, "usd": 0.0})
            b["calls"] += 1
            b["usd"] = round(b["usd"] + c["usd"], 4)
        return {"usd": self.total(), "calls": len(self.calls), "web_searches": sum(c["web_search"] for c in self.calls),
                "by_model": by_model, "by_caller": by_caller}


def install_usage_hook(usage: Usage) -> None:
    from anthropic.lib.streaming._beta_messages import BetaAsyncMessageStream, BetaMessageStream
    from anthropic.lib.streaming._messages import AsyncMessageStream, MessageStream
    from anthropic.resources.beta.messages.messages import AsyncMessages as BAM
    from anthropic.resources.beta.messages.messages import Messages as BM
    from anthropic.resources.messages.messages import AsyncMessages, Messages

    for cls in (Messages, BM):
        for name in ("create", "parse"):
            orig = getattr(cls, name, None)
            if orig is None:
                continue

            @functools.wraps(orig)
            def w(self, *a, __o=orig, **k):
                r = __o(self, *a, **k)
                if not k.get("stream"):
                    usage.add(r)
                return r
            setattr(cls, name, w)
    for cls in (AsyncMessages, BAM):
        for name in ("create", "parse"):
            orig = getattr(cls, name, None)
            if orig is None:
                continue

            @functools.wraps(orig)
            async def aw(self, *a, __o=orig, **k):
                r = await __o(self, *a, **k)
                if not k.get("stream"):
                    usage.add(r)
                return r
            setattr(cls, name, aw)
    for cls in (MessageStream, BetaMessageStream):
        orig = cls.get_final_message

        @functools.wraps(orig)
        def g(self, __o=orig):
            m = __o(self)
            usage.add(m)
            return m
        cls.get_final_message = g
    for cls in (AsyncMessageStream, BetaAsyncMessageStream):
        orig = cls.get_final_message

        @functools.wraps(orig)
        async def ag(self, __o=orig):
            m = await __o(self)
            usage.add(m)
            return m
        cls.get_final_message = ag


# ---------------------------------------------------------------- E2's rules for text lessons
ABS = re.compile(r"(?<![\w.])(/Users/|/home/|/tmp/|/private/|[A-Z]:\\)")
SETUP = re.compile(r"^\s*(mkdir|touch|cd|md|New-Item)\b", re.I | re.M)
RAN_FILE = re.compile(r"\b([\w./-]+\.(?:py|js|mjs|ts|rs|go|rb|java|sh))\b")


def e2_rules(graph: dict) -> list[str]:
    out = []
    lesson, steps = graph.get("lesson") or {}, graph.get("steps") or []
    try:
        from server.lesson.schema import schema_errors

        out += [f"schema: {e}" for e in schema_errors(graph)][:5]
    except Exception as e:  # noqa: BLE001
        out.append(f"schema check unavailable: {e}")
    if lesson.get("mode") != "lesson":
        out.append(f"lesson.mode is {lesson.get('mode')!r}, not 'lesson'")
    if not steps:
        return out + ["no steps"]
    if L.step_kind(steps[0]) == "run":
        out.append("step 1 is a run step (must type code into a file)")
    for k, st in enumerate(steps):
        sid, ins, code = st.get("id"), st.get("instructions") or "", st.get("code") or ""
        if st.get("video"):
            out.append(f"{sid}: has a video segment")
        words = ins.split()
        if len([s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", ins.strip()) if s]) > 1:
            out.append(f"{sid}: instructions are more than one sentence: {ins!r}")
        if len(words) > 10:
            out.append(f"{sid}: instructions have {len(words)} words (> 10): {ins!r}")
        if "(" in ins and ")" in ins:
            out.append(f"{sid}: instructions have a parenthetical: {ins!r}")
        if ABS.search(ins) or ABS.search(code):
            out.append(f"{sid}: absolute path in instructions/code")
        if SETUP.search(code) or re.search(r"\b(mkdir|touch)\b", ins):
            out.append(f"{sid}: folder-setup command in the step")
        if L.step_kind(st) == "run":
            if not re.match(r"^Run your .+ in the terminal\.$", ins):
                out.append(f"{sid}: run step wording {ins!r} (E2: 'Run your X in the terminal.')")
            if not any(c.get("type") == "file_contains" for c in st.get("precision_checks") or []):
                out.append(f"{sid}: run step without a file_contains check for the code it runs")
            m = RAN_FILE.search(code + " " + (st.get("file") or ""))
            f = m.group(1) if m else ""
            if f and not any((o.get("file") or "") == f and (o.get("code") or "").strip() and L.step_kind(o) == "type"
                             for o in steps[:k]):
                out.append(f"{sid}: runs {f} before any step writes it")
        else:
            pats = [c.get("pattern") for c in (st.get("checks") or []) + (st.get("precision_checks") or []) if c.get("pattern")]
            ok = False
            for p in pats:
                try:
                    ok = ok or bool(re.search(p, code))
                except re.error:
                    out.append(f"{sid}: invalid regex {p!r}")
            if code.strip() and not ok:
                out.append(f"{sid}: no check matches the code to type")
            if any((c.get("app") or "") in ("Terminal", "iTerm2") for c in st.get("checks") or []):
                out.append(f"{sid}: typing step has a Terminal check")
    return out


# ---------------------------------------------------------------- one topic
async def run_topic(topic: str, hold: float, budget: float, spent: float, port: int) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40]
    workdir = L.SCRATCH / f"live-{slug}"
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True)
    fx0 = L.render(f"live-{slug}-start", workdir.name, "main.py", "", panel=True, term=["% "])
    for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        os.environ.pop(k, None)
    os.environ.update({
        "DEMO": "0", "ORCH_STUBS": "finder,diagrams", "LESSON_ENGINE": "claude", "GEMINI_API_KEY": "",
        "GOOGLE_API_KEY": "", "BRIGHTDATA_API_KEY": "", "ELEVENLABS_API_KEY": "", "TIGER_DATABASE_URL": "",
        "ORCH_SCREEN": "1", "TUT_AX": "0", "ORCH_OPEN_WORKSPACE": "1", "ORCH_RECORD": "0",
        "ORCH_DIAGRAM_PREFETCH": "0", "ORCH_AUTOSTART": "0", "TUT_WORKDIR": str(workdir), "TUT_SCREEN_FIXTURE": fx0["png"],
    })
    usage = Usage(max(0.0, budget - spent))
    install_usage_hook(usage)
    main = __import__("server.orchestrator.main", fromlist=["engine"])
    try:
        from server.workspace import editor as s2_editor

        s2_editor._ax_editor_snapshot = lambda: None
    except Exception:  # noqa: BLE001
        pass
    engine = main.engine
    rec = L.Recorder(workdir)
    engine.workspace.run = lambda argv: (rec.argv.append([str(a) for a in argv]) or True)
    orig_emit = engine.hub.emit
    cur = {"step": None}

    async def emit(type_: str, payload: dict | None = None) -> None:
        payload = payload or {}
        ev = {"t": rec.now(), "type": type_, "payload": payload}
        g = engine.session.graph or {"steps": []}
        if type_ == "step.started":
            idx = next((i for i, s in enumerate(g["steps"]) if s["id"] == payload.get("stepId")), 0)
            f = workdir / L.code_file(g, idx) if g["steps"] else None
            ev["file_bytes"] = f.stat().st_size if f is not None and f.is_file() else None
            ev["file"] = f.name if f is not None else None
            cur["step"] = payload.get("stepId")
        ev["step"] = cur["step"]
        rec.events.append(ev)
        await orig_emit(type_, payload)

    engine.hub.emit = emit
    await engine.start()
    server_task = None
    try:  # also serve it on :8790, so the hub can look at it (lifespan off: started above)
        import uvicorn

        cfg = uvicorn.Config(main.app, host="127.0.0.1", port=port, lifespan="off", log_level="warning")
        server_task = asyncio.create_task(uvicorn.Server(cfg).serve())
    except Exception:  # noqa: BLE001
        pass
    reader = getattr(engine.screen, "reader", None)
    res: dict = {"topic": topic, "workdir": str(workdir)}
    print(f"  engine up · modules {engine.modules.describe()} · serving 127.0.0.1:{port}", flush=True)

    # ---- build
    t0 = rec.now()
    build = asyncio.create_task(engine.dispatch({"type": "learn", "payload": {"query": topic, "mode": "lesson"}}))
    first = full = None
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline and not usage.over:
        if first is None and any(e["type"] == "step.started" for e in rec.events):
            first = next(e for e in rec.events if e["type"] == "step.started")["t"] - t0
        if build.done() and (first is not None or any(e["type"] == "error" for e in rec.events)):
            full = rec.now() - t0
            break
        await asyncio.sleep(0.25)
    if not build.done():
        res["build_timeout_or_budget"] = "budget" if usage.over else "timeout"
    errors = [e["payload"].get("message") for e in rec.events if e["type"] == "error"]
    stages, last = [], None
    for e in rec.events:
        if e["type"] == "lesson.building":
            m = re.sub(r"\s*·\s*\d+:\d\d$", "", e["payload"].get("message", ""))
            if m != last:
                stages.append((round(e["t"] - t0, 1), m))
                last = m
    graph = json.loads(json.dumps(engine.session.graph or {}))
    lesson = graph.get("lesson") or {}
    res.update({"first_step_s": round(first, 1) if first is not None else None, "full_lesson_s": round(full, 1) if full else None,
                "stages": stages, "errors": errors, "title": lesson.get("title"), "builtBy": lesson.get("builtBy"),
                "n_steps": len(graph.get("steps") or []), "build_usd": usage.total(),
                "steps": [{"id": s.get("id"), "file": s.get("file"), "instructions": s.get("instructions"),
                           "code": (s.get("code") or "")[:200]} for s in graph.get("steps") or []]})
    res["e2_rules"] = e2_rules(graph) if graph.get("steps") else ["no lesson built"]
    print(f"  build: first step {res['first_step_s']} s · full {res['full_lesson_s']} s · {res['n_steps']} steps · "
          f"builtBy {res['builtBy']} · ${usage.total():.3f} · errors {errors[:2]}", flush=True)

    # ---- drive steps 1-3 on rendered screens (terminal open, saved after each typing step)
    geo, forced = {}, []
    if graph.get("steps") and not usage.over:
        folder = workdir.name
        src: list[str] = []
        term = ["% "]

        async def show(name: str, lines: list[str], term_lines: list[str], file: str) -> dict:
            fx = L.render(name, folder, file, "\n".join(lines), panel=True, term=term_lines)
            if reader is not None:
                reader.fixture = fx["png"]
                try:
                    reader.poke("fixture", force=True)
                except TypeError:
                    reader.poke("fixture")
            return fx

        steps = graph["steps"]
        for i, st in enumerate(steps[:STEPS_DRIVEN]):
            if usage.over:
                break
            for _ in range(100):
                if engine.session.step is not None and engine.session.step["id"] == st["id"]:
                    break
                await asyncio.sleep(0.1)
            if engine.session.step is None or engine.session.step["id"] != st["id"]:
                await engine.session.goto_step(i)
                forced.append(f"{st['id']} (start)")
            kind, file = L.step_kind(st), L.code_file(graph, i)
            before = await show(f"live-{slug}-{st['id']}-before", src, term, file)
            geo[st["id"]] = {"kind": kind, "before": before, "src": list(src)}
            print(f"  {st['id']} [{kind}] {st.get('title')!r} · holding {hold:.0f} s · ${usage.total():.3f}", flush=True)
            await asyncio.sleep(hold)
            if kind == "type":
                src = src + L.typed_code(st)
                (workdir / file).write_text("\n".join(src) + "\n")
            else:
                cmd = (st.get("code") or "python main.py").strip().splitlines()[0]
                term = term + [f"% {cmd}", "% "]
            await show(f"live-{slug}-{st['id']}-after", src, term, file)
            moved = False
            for _ in range(120):
                if engine.session.step is None or engine.session.step["id"] != st["id"]:
                    moved = True
                    break
                await asyncio.sleep(0.1)
            if not moved and i + 1 < min(len(steps), STEPS_DRIVEN):
                forced.append(st["id"])
                rec.events.append({"t": rec.now(), "type": "_skip", "payload": {}, "step": st["id"]})
                await engine.session.action("skip_step")  # what a learner presses to move on
    try:
        await engine.session.end_lesson("stage_lessonmode_live")
    except Exception:  # noqa: BLE001
        pass
    await asyncio.sleep(0.5)
    if not build.done():
        build.cancel()
    await engine.stop()
    if server_task:
        server_task.cancel()
    driven = {"scenario": "open", "lesson": graph or {"steps": []}, "events": rec.events, "argv": rec.argv, "geo": geo,
              "forced": forced, "screen_down": {}, "extras": {}}
    j = L.judge(driven) if graph.get("steps") else {"items": {}, "rows": []}
    ids = {s["id"] for s in (graph.get("steps") or [])[:STEPS_DRIVEN]}
    rows = [r for r in j["rows"] if r["step"] in ids]
    items = {k: [x for x in v if x.split(":")[0] in ids or k == "e"] for k, v in j["items"].items()}
    res.update({"items": items, "rows": rows, "forced": forced, "argv": rec.argv, "usage": usage.summary(),
                "over_budget": usage.over})
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topic", action="append", default=[])
    ap.add_argument("--hold", type=float, default=22.0)
    ap.add_argument("--budget", type=float, default=1.0, help="stop the round once the estimate passes this ($)")
    ap.add_argument("--spent", type=float, default=0.0, help=argparse.SUPPRESS)
    ap.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--port", type=int, default=8790)
    args = ap.parse_args()
    topics = args.topic or TOPICS
    head = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%h"], capture_output=True, text=True).stdout.strip()
    live = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "origin/integration/live"],
                          capture_output=True, text=True).stdout.strip()
    out_path = RUNS / "stage-lessonmode-live.jsonl"
    if args.child:
        res = asyncio.run(run_topic(topics[0], args.hold, args.budget, args.spent, args.port))
        res.update({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "code": head, "live": live})
        RUNS.mkdir(parents=True, exist_ok=True)
        with out_path.open("a") as f:
            f.write(json.dumps(res, ensure_ascii=False, default=str) + "\n")
        return
    print(f"LIVE round · code {head} (origin/integration/live {live}) · budget ${args.budget:.2f}", flush=True)
    spent, results = 0.0, []
    for t in topics:
        if spent >= args.budget:
            print(f"STOP: round spend ${spent:.3f} reached the ${args.budget:.2f} budget; skipping {t!r}")
            break
        print(f"\n=== {t}  (round so far ${spent:.3f})", flush=True)
        n0 = sum(1 for _ in out_path.open()) if out_path.exists() else 0
        subprocess.run([sys.executable, __file__, "--child", "--topic", t, "--hold", str(args.hold), "--budget",
                        str(args.budget), "--spent", str(spent), "--port", str(args.port)], check=False)
        lines = out_path.read_text().splitlines() if out_path.exists() else []
        if len(lines) <= n0:
            print("  (no result: the run crashed; see above)")
            continue
        r = json.loads(lines[-1])
        results.append(r)
        spent = round(spent + r["usage"]["usd"], 4)
        u = r["usage"]
        print(f"  RESULT {t!r}: build {'OK' if r['n_steps'] else 'FAILED'} · first step {r['first_step_s']} s · full "
              f"{r['full_lesson_s']} s · {r['n_steps']} steps · builtBy {r['builtBy']} · ${u['usd']:.3f} "
              f"({u['calls']} calls, {u['web_searches']} web searches)")
        print(f"    by model: {json.dumps(u['by_model'])}")
        print(f"    by caller: {json.dumps(u['by_caller'])}")
        print(f"    E2 rules: {'PASS' if not r['e2_rules'] else 'FAIL'} {r['e2_rules'][:6]}")
        for k, v in sorted(r["items"].items()):
            print(f"    ({k}) {'PASS' if not v else 'FAIL'} {v[:4] if v else ''}")
        for row in r["rows"]:
            print(f"    {row['step']} [{row['kind']}] spots={row['spots']} cards={row['cards']} instr={row['instructions']!r}")
        if r.get("over_budget"):
            print("  STOP: over budget during this topic")
            spent = max(spent, args.budget)
    print(f"\nROUND TOTAL ≈ ${spent:.3f} for {len(results)} build(s)")


if __name__ == "__main__":
    main()
