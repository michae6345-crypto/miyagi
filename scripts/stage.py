#!/usr/bin/env python3
"""Stage runner: drive the LIVE engine one pipeline stage at a time and print what each stage did.

  .venv/bin/python scripts/stage.py search "react useEffect cleanup"
  .venv/bin/python scripts/stage.py build 1 "react useEffect cleanup"        # result #1 of the last search
  .venv/bin/python scripts/stage.py build https://www.youtube.com/watch?v=... "goal"
  .venv/bin/python scripts/stage.py run                                       # watch the gate + coach while you work
  .venv/bin/python scripts/stage.py engine status|stop|log

It starts (or reuses) a LIVE engine on a spare port (default 8790): DEMO=0, ORCH_AUTOSTART=0,
ORCH_OPEN_WORKSPACE=0 (pass --open to open VS Code like the real script does). Everything goes over
the real WebSocket protocol (shared/contracts/events.ts); nothing here calls a module directly.

Each `search` / `build` appends a JSON summary to demo/runs/stage-results.jsonl (gitignored), which is
what docs/STAGES.md is written from. Engine log: demo/runs/stage-engine-<port>.log.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "demo" / "runs"
LESSON_CACHE = ROOT / "demo" / "cache" / "lessons"

try:
    import httpx
    import websockets
except ImportError:  # re-exec under the repo venv
    venv_py = ROOT / ".venv" / "bin" / "python"
    if venv_py.exists() and Path(sys.executable).resolve() != venv_py.resolve():
        os.execv(str(venv_py), [str(venv_py), __file__, *sys.argv[1:]])
    sys.exit("stage.py needs httpx + websockets: uv venv .venv && uv pip install -e 'server[dev]'")

C = {"dim": "\033[2m", "g": "\033[32m", "y": "\033[33m", "r": "\033[31m", "b": "\033[34m", "c": "\033[36m",
     "m": "\033[35m", "bold": "\033[1m", "x": "\033[0m"}
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    C = {k: "" for k in C}

# Things that belong to the PINN hero demo and should never show up in a lesson about something else.
LEAK_PATTERNS = [
    (r"\bpinns?\b", "PINN"),
    (r"physics[- ]informed", "physics-informed"),
    (r"convection", "convection"),
    (r"diffusion equation|heat equation|\bpdes?\b|burgers", "PDE"),
    (r"pinn[-_]lab|pinn_convection|demo/pinn", "pinn workdir/file"),
    (r"collocation", "collocation points"),
    (r"latin[- ]?hypercube|\blhs\b|pydoe", "Latin-hypercube sampling"),
    (r"exact_solution|def.{0,5}exact\b", "exact_solution (PDE reference)"),
    (r"boundary (?:condition|point|data)s?|initial condition|boundary_points", "IC/BC (PDE)"),
    (r"\bu_t\b|\bu_x\b|\bu_xx\b|\bf_t\b|\bf_xx\b", "PDE residual terms"),
    (r"β|\bbeta\s*=\s*30\b|beta\s*\*\s*u_x", "β (convection coefficient)"),
    (r"AXXnSzmpyoI|unBU1PwCnvQ|h5-7hu2QkMc|f9VZm6WrFIg", "hero video id"),
    (r"toscano", "Toscano (hero tutor)"),
]
SCREEN_TYPES = {"screen_contains", "screen_absent"}
METRIC_TYPES = {"metric_threshold", "metric_trend"}
FILE_TYPES = {"file_exists", "file_contains"}


def now() -> str:
    return time.strftime("%H:%M:%S")


def rel(t0: float) -> str:
    return f"+{time.monotonic() - t0:6.1f}s"


def log_result(rec: dict) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **rec}
    with (RUNS / "stage-results.jsonl").open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def leaks_in(text: str, *, topic: str = "") -> list[str]:
    """PINN-demo markers found in `text` that don't also appear in the learner's topic."""
    found = []
    for pat, label in LEAK_PATTERNS:
        if re.search(pat, topic, re.I):
            continue  # the learner asked for it
        m = re.search(pat, text, re.I)
        if m:
            found.append(f"{label} ({m.group(0)!r})")
    return found


# ---------------------------------------------------------------------------------------------- engine
class Engine:
    def __init__(self, port: int):
        self.port = port
        self.http = f"http://127.0.0.1:{port}"
        self.ws = f"ws://127.0.0.1:{port}"
        self.pidfile = RUNS / f"stage-engine-{port}.pid"
        self.logfile = RUNS / f"stage-engine-{port}.log"

    def health(self) -> dict | None:
        try:
            return httpx.get(f"{self.http}/health", timeout=2).json()
        except Exception:
            return None

    def state(self) -> dict:
        return httpx.get(f"{self.http}/state", timeout=5).json()

    def ensure(self, *, screen: bool, open_ws: bool, workdir: str | None, fresh: bool = False,
               extra_env: list[str] | None = None) -> dict:
        h = self.health()
        if h and fresh:
            self.stop()
            h = None
        if h:
            if h.get("demo"):
                sys.exit(f"engine on :{self.port} is in DEMO mode; stop it (stage.py engine stop) — this runner is LIVE only")
            print(f"{C['dim']}{now()} reusing LIVE engine on :{self.port} · modules {h.get('modules')}{C['x']}")
            return h
        RUNS.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "ENGINE_PORT": str(self.port), "ENGINE_HOST": "127.0.0.1", "DEMO": "0",
               "ORCH_AUTOSTART": "0", "ORCH_STUBS": "", "ORCH_SCREEN": "1" if screen else "0",
               "ORCH_OPEN_WORKSPACE": "1" if open_ws else "0", "PYTHONUNBUFFERED": "1",
               "MIYAGI_DEBUG_ROUTES": "1"}  # 5.3: /debug/pass, /debug/goto are dev routes
        if workdir:
            env["TUT_WORKDIR"] = str(Path(workdir).expanduser().resolve())
        for kv in extra_env or []:  # e.g. LESSON_MODEL=gemini-3.1-flash-lite (don't pass secrets: it's logged)
            k, _, v = kv.partition("=")
            env[k] = v
        py = ROOT / ".venv" / "bin" / "python"
        py = py if py.exists() else Path(sys.executable)
        out = self.logfile.open("a")
        out.write(f"\n===== stage.py starting engine {time.strftime('%Y-%m-%d %H:%M:%S')} (screen={screen}, "
                  f"TUT_WORKDIR={env.get('TUT_WORKDIR', '<unset>')}, extra env {extra_env or []})\n")
        out.flush()
        p = subprocess.Popen([str(py), str(ROOT / "scripts" / "stage_engine.py"), "--host", "127.0.0.1", "--port", str(self.port)],
                             cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        self.pidfile.write_text(str(p.pid))
        t0 = time.monotonic()
        while time.monotonic() - t0 < 40:
            if p.poll() is not None:
                sys.exit(f"engine exited with {p.returncode}; see {self.logfile}")
            h = self.health()
            if h:
                print(f"{C['dim']}{now()} started LIVE engine pid {p.pid} on :{self.port} in {time.monotonic() - t0:.1f}s · "
                      f"modules {h.get('modules')} · log {self.logfile.relative_to(ROOT)}{C['x']}")
                return h
            time.sleep(0.3)
        sys.exit(f"engine didn't answer /health in 40s; see {self.logfile}")

    def stop(self) -> None:
        pid = None
        if self.pidfile.exists():
            pid = int(self.pidfile.read_text().strip() or 0)
        if pid:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            for _ in range(30):
                if not self.health():
                    break
                time.sleep(0.2)
            self.pidfile.unlink(missing_ok=True)
            print(f"stopped engine pid {pid}")
        elif self.health():
            print(f"an engine answers on :{self.port} but wasn't started by stage.py; stop it yourself")
        else:
            print("no engine running")

    def log_since(self, offset: int) -> str:
        try:
            with self.logfile.open("rb") as f:
                f.seek(offset)
                return f.read().decode(errors="replace")
        except OSError:
            return ""

    def log_size(self) -> int:
        try:
            return self.logfile.stat().st_size
        except OSError:
            return 0


async def connect(engine: Engine):
    ws = await websockets.connect(engine.ws, max_size=8 * 2**20, ping_interval=None)
    return ws


async def recv(ws, timeout: float) -> dict | None:
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout)
    except asyncio.TimeoutError:
        return None
    except websockets.ConnectionClosed as e:
        return {"type": "error", "payload": {"message": f"engine closed the socket ({e}); engine died? see the engine log"}}
    return json.loads(raw)


# ---------------------------------------------------------------------------------------------- search
async def cmd_search(engine: Engine, query: str, timeout: float) -> dict:
    ws = await connect(engine)
    # drain the reconnect snapshot
    while await recv(ws, 0.3):
        pass
    t0 = time.monotonic()
    await ws.send(json.dumps({"type": "learn", "payload": {"query": query}}))
    print(f"{C['bold']}{now()} learn {query!r}{C['x']}")
    rows: list[dict] = []
    first = done_at = None
    errors: list[str] = []
    total = None
    while True:
        msg = await recv(ws, max(1.0, timeout - (time.monotonic() - t0)))
        if msg is None:
            errors.append(f"no search.done after {timeout:.0f}s")
            print(f"{C['r']}{rel(t0)} TIMEOUT: no search.done after {timeout:.0f}s{C['x']}")
            break
        t, p = msg.get("type"), msg.get("payload", {})
        if t == "search.result":
            first = first or time.monotonic() - t0
            rows.append({**p, "_t": round(time.monotonic() - t0, 2)})
            leak = leaks_in(json.dumps(p), topic=query)
            watched = "skim" if p.get("scored_by", "").endswith("skim") or p.get("skim") else "?"
            print(f"{C['dim']}{rel(t0)}{C['x']} {C['c']}#{len(rows):<2}{C['x']} [{p.get('kind'):8}] "
                  f"{C['bold']}{(p.get('title') or '')[:70]}{C['x']}\n"
                  f"           score {p.get('score'):>3} · source {p.get('source', '?')} · verified {p.get('verified', '?')}"
                  f" · watched {watched} · {p.get('meta', '')[:60]}\n"
                  f"           {C['dim']}{p.get('reason', '')}{C['x']}  {C['dim']}{p.get('url', '')}{C['x']}"
                  + (f"\n           {C['r']}LEAK? {', '.join(leak)}{C['x']}" if leak else "")
                  + (f"\n           {C['y']}warnings: {p.get('warnings')}{C['x']}" if p.get("warnings") else ""))
        elif t == "search.done":
            done_at = time.monotonic() - t0
            total = p.get("total")
            print(f"{C['g']}{rel(t0)} search.done total={total}{C['x']}")
            break
        elif t == "error":
            errors.append(p.get("message", ""))
            print(f"{C['r']}{rel(t0)} error: {p.get('message')}{C['x']}")
        elif t == "status":
            print(f"{C['dim']}{rel(t0)} status {p.get('state')}{C['x']}")
    await ws.close()
    ranked = sorted(rows, key=lambda r: -(r.get("score") or 0))
    print(f"\n{C['bold']}top 5 by score, as the app saw them{C['x']} (first result {first or 0:.1f}s, done {done_at or 0:.1f}s, "
          f"{len(rows)} rows, kinds {dict(_count(r.get('kind') for r in rows))})")
    for i, r in enumerate(ranked[:5], 1):
        print(f"  {i}. {r.get('score'):>3} [{r.get('kind')}] {r.get('title', '')[:80]}  ({r.get('source')}) {r.get('url')}")
    if rows and rows[0].get("kind") != "video":
        print(f"  {C['y']}note: the first streamed row is a {rows[0].get('kind')}; build_lesson with no resultIds builds "
              f"from the first streamed row ({rows[0].get('title', '')[:50]!r}), which isn't a YouTube video{C['x']}")
    # The finder's own final ranking (after the deep pass: Gemini skims the top videos). The engine
    # doesn't re-emit rows whose score changed, so read it from the finder's cache file.
    final, notes, timings = _finder_final(query, since=time.time() - (time.monotonic() - t0) - 2)
    if final:
        by_id = {r["id"]: r for r in rows}
        print(f"\n{C['bold']}finder's final ranking{C['x']} (rows[0] = what build_lesson should get) · timings {timings}")
        for i, r in enumerate(final[:5], 1):
            sent = by_id.get(r["id"])
            changed = sent is not None and (sent.get("score") != r.get("score") or sent.get("reason") != r.get("reason"))
            how = "watched (Gemini skim)" if r.get("kind") == "video" else "rescored"
            tag = f"{C['m']}{how}{C['x']}, app only saw {sent.get('score')}" if changed else ""
            print(f"  {i}. {r.get('score'):>5} [{r.get('kind')}] {r.get('title', '')[:70]}  {tag}\n"
                  f"        {C['dim']}{r.get('reason')}  {r.get('url')}{C['x']}")
        for n in notes:
            print(f"  {C['dim']}finder note: {n[:160]}{C['x']}")
    leaks = {r["id"]: leaks_in(json.dumps(r), topic=query) for r in rows}
    leaks = {k: v for k, v in leaks.items() if v}
    (RUNS / "stage-last-search.json").write_text(json.dumps({"query": query, "rows": rows, "final": final}, indent=1))
    rec = {"stage": "search", "query": query, "first_s": round(first or 0, 2), "done_s": round(done_at or 0, 2),
           "total": total, "n": len(rows), "errors": errors, "leaks": leaks, "finder_notes": notes,
           "finder_timings": timings,
           "final_top5": [{k: r.get(k) for k in ("id", "kind", "title", "score", "reason", "url")} for r in final[:5]],
           "rows": [{k: r.get(k) for k in ("id", "kind", "title", "score", "source", "verified", "reason", "url", "_t")}
                    for r in rows]}
    log_result(rec)
    return rec


def _finder_final(query: str, since: float) -> tuple[list[dict], list[str], dict]:
    """The newest demo/cache/search/*.json for this query (written by server.finder) -> (results, notes, timings).
    Empty if the finder didn't write one during this search (e.g. it answered from an older cache file)."""
    best = None
    for p in (ROOT / "demo" / "cache" / "search").glob("*.json"):
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if d.get("query") == query and (best is None or p.stat().st_mtime > best[0]):
            best = (p.stat().st_mtime, d)
    if not best:
        return [], [], {}
    d = best[1]
    notes = list(d.get("notes") or [])
    if best[0] < since:
        notes.insert(0, "served from an earlier finder cache file (not a live search)")
    return d.get("results") or [], notes, d.get("timings") or {}


def _count(items):
    out: dict = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out.items()


# ---------------------------------------------------------------------------------------------- build
def _full_graph(engine: Engine, lesson_id: str, n_steps: int) -> tuple[dict | None, str]:
    """The step graph the engine loaded. lesson.ready carries only summaries, so: the builder's cache file
    (lesson-<key8> -> demo/cache/lessons/<key8>*.json), else walk the steps via /debug/goto + /state."""
    key8 = lesson_id.removeprefix("lesson-")
    hits = sorted(LESSON_CACHE.glob(f"{key8}*.json")) if key8 else []
    if hits:
        try:
            return json.loads(hits[0].read_text()), f"cache file {hits[0].relative_to(ROOT)}"
        except (OSError, ValueError):
            pass
    st = engine.state()
    steps = []
    for i in range(n_steps):
        httpx.post(f"{engine.http}/debug/goto/{i}", timeout=10)
        s = engine.state().get("step")
        if s:
            steps.append(s)
    httpx.post(f"{engine.http}/debug/goto/0", timeout=10)
    return {"lesson": st.get("lesson") or {}, "steps": steps}, "walked /debug/goto (graph not cached by the builder)"


def outline(graph: dict, topic: str) -> dict:
    lesson = graph.get("lesson", {})
    steps = graph.get("steps", [])
    print(f"\n{C['bold']}{lesson.get('title')}{C['x']}  ({lesson.get('id')})")
    print(f"  goal: {lesson.get('goal')!r}")
    print(f"  workdir: {lesson.get('workdir')}   libraries: {lesson.get('libraries')}")
    for s in graph.get("sources", []):
        print(f"  source: {s.get('title')} {s.get('url')}")
    b = graph.get("build") or {}
    if b:
        print(f"  build: model {b.get('model')} · adapted {b.get('adapted')} · {b.get('seconds')}s · "
              f"workdir metrics {b.get('workdir_metrics')} · community {b.get('community_signals')}")
        for w in b.get("warnings") or []:
            print(f"  {C['y']}build warning: {str(w)[:200]}{C['x']}")
    types: dict[str, int] = {}
    issues: list[str] = []
    for i, s in enumerate(steps):
        v = s.get("video") or {}
        span = f"{_mmss(v.get('start'))}–{_mmss(v.get('end'))}" if v else "no video"
        print(f"\n  {C['b']}{s.get('id')}{C['x']} #{s.get('index', i)} {C['bold']}{s.get('title')}{C['x']}  [{span}]")
        print(f"     {C['dim']}{(s.get('instructions') or '')[:300]}{C['x']}")
        checks = s.get("checks") or []
        if not checks:
            issues.append(f"{s.get('id')}: no screen checks")
        for c in checks:
            types[c.get("type")] = types.get(c.get("type"), 0) + 1
            print(f"     ✓ {c.get('type'):16} {c.get('label')}  " + _check_detail(c))
            issues += [f"{s.get('id')}/{c.get('id')}: {x}" for x in _check_issues(c)]
        for c in s.get("precision_checks") or []:
            types["(p) " + str(c.get("type"))] = types.get("(p) " + str(c.get("type")), 0) + 1
            print(f"     {C['dim']}◇ {c.get('type'):16} {c.get('label')}  {_check_detail(c)}{C['x']}")
        for tg in s.get("targets") or []:
            print(f"     {C['dim']}→ target {tg.get('app')}:{tg.get('file', '')} match {tg.get('match')!r}{C['x']}")
    leak = leaks_in(json.dumps(graph, ensure_ascii=False), topic=topic)
    print(f"\n  check types: {types}")
    for x in issues:
        print(f"  {C['y']}check issue: {x}{C['x']}")
    if leak:
        print(f"  {C['r']}PINN LEAK: {', '.join(leak)}{C['x']}")
    return {"title": lesson.get("title"), "workdir": lesson.get("workdir"), "n_steps": len(steps), "check_types": types,
            "issues": issues, "leaks": leak, "build": b,
            "steps": [{"id": s.get("id"), "title": s.get("title"), "video": s.get("video"),
                       "checks": [{k: c.get(k) for k in ("type", "label", "pattern", "app", "metric", "metric_pattern",
                                                         "op", "value", "file")} for c in s.get("checks") or []],
                       "precision": [{k: c.get(k) for k in ("type", "label", "pattern", "file", "metric")}
                                     for c in s.get("precision_checks") or []]} for s in steps]}


def _mmss(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "?"
    return f"{int(v) // 60}:{int(v) % 60:02d}"


def _check_detail(c: dict) -> str:
    parts = []
    for k in ("app", "file", "pattern", "metric", "metric_pattern", "op", "value", "direction", "by_step", "command"):
        if c.get(k) not in (None, ""):
            parts.append(f"{k}={c[k]!r}" if k in ("pattern", "metric_pattern", "file", "command") else f"{k}={c[k]}")
    return C["dim"] + " ".join(parts)[:220] + C["x"]


def _check_issues(c: dict) -> list[str]:
    t = c.get("type")
    out = []
    if t in SCREEN_TYPES:
        pat = c.get("pattern") or ""
        if not pat:
            out.append("screen check without a pattern")
        elif len(re.sub(r"\\[sbwd]|[\\^$.*+?()\[\]{}|]", "", pat)) < 4:
            out.append(f"pattern {pat!r} is very generic (would match almost any screen)")
        else:
            try:
                re.compile(pat)
            except re.error as e:
                out.append(f"pattern {pat!r} is not a valid regex ({e})")
    elif t in METRIC_TYPES:
        if not c.get("metric_pattern"):
            out.append("metric check without metric_pattern (can't be read off the screen)")
        else:
            try:
                rx = re.compile(c["metric_pattern"])
                if rx.groups < 1:
                    out.append("metric_pattern has no capture group")
            except re.error as e:
                out.append(f"metric_pattern is not a valid regex ({e})")
    elif t == "visual":
        out.append("visual check (model judgement, not machine-checkable)")
    elif t not in FILE_TYPES | {"command_exit_ok", "output_contains"}:
        out.append(f"unknown check type {t!r}")
    return out


async def cmd_build(engine: Engine, target: str, goal: str, timeout: float) -> dict:
    url, rid, picked = None, None, None
    if re.fullmatch(r"\d+", target):
        last = json.loads((RUNS / "stage-last-search.json").read_text()) if (RUNS / "stage-last-search.json").exists() else None
        if not last:
            sys.exit("no previous search: run `stage.py search ...` first (same engine)")
        # numbered like "finder's final ranking" (rows[0] = the finder's best video); else by the streamed score
        rows = last.get("final") or sorted(last["rows"], key=lambda r: -(r.get("score") or 0))
        sent = {r["id"] for r in last["rows"]}
        i = int(target)
        if not 1 <= i <= len(rows):
            sys.exit(f"result #{i} out of range 1..{len(rows)} (numbered as in \"finder's final ranking\")")
        if rows[i - 1]["id"] not in sent:
            sys.exit(f"result #{i} ({rows[i - 1]['id']}) never reached the engine, so build_lesson can't name it")
        picked = rows[i - 1]
        rid = picked["id"]
        if last["query"] != goal:
            print(f"{C['y']}note: the engine builds with goal = the last `learn` query ({last['query']!r}), "
                  f"not {goal!r} (build_lesson carries no goal){C['x']}")
            goal = last["query"]
    else:
        url = target
        print(f"{C['y']}note: learn_url carries no goal; the engine uses its last `learn` query (or '') as the goal{C['x']}")
    ws = await connect(engine)
    while await recv(ws, 0.3):
        pass
    log_off = engine.log_size()
    t0 = time.monotonic()
    if rid:
        await ws.send(json.dumps({"type": "build_lesson", "payload": {"resultIds": [rid]}}))
        print(f"{C['bold']}{now()} build_lesson #{target} {picked.get('title')!r} {picked.get('url')}{C['x']}")
    else:
        await ws.send(json.dumps({"type": "learn_url", "payload": {"url": url}}))
        print(f"{C['bold']}{now()} learn_url {url}{C['x']}")
    ready = None
    errors: list[str] = []
    last_msg = ""
    last_print = -1
    stages: list[str] = []
    preflights: list[dict] = []
    answered = False
    while True:
        msg = await recv(ws, max(1.0, timeout - (time.monotonic() - t0)))
        if msg is None:
            if errors:  # an error came, but no lesson.building{failed} followed: the app may stay on "building"
                errors.append("no lesson.building{failed:true} after the error")
                print(f"{C['y']}{rel(t0)} note: no lesson.building{{failed}} followed the error{C['x']}")
                break
            errors.append(f"no lesson.ready after {timeout:.0f}s")
            print(f"{C['r']}{rel(t0)} TIMEOUT: no lesson.ready after {timeout:.0f}s{C['x']}")
            break
        t, p = msg.get("type"), msg.get("payload", {})
        if t == "lesson.building":
            # the engine ticks every second ("<stage> · m:ss"); print when the stage itself changes, plus every 15 s
            stage_txt = re.sub(r"\s*·\s*\d+:\d\d$", "", p.get("message", ""))
            el = int(time.monotonic() - t0)
            if stage_txt != last_msg or (el and el % 15 == 0 and el != last_print) or p.get("failed"):
                print(f"{C['dim']}{rel(t0)} building {int(100 * p.get('progress', 0)):3d}% {p.get('message')}"
                      + (f" {C['r']}[failed]" if p.get("failed") else "") + C["x"])
                last_print = el
                if stage_txt != last_msg:
                    stages.append(f"{el}s {stage_txt}")
            last_msg = stage_txt
            if p.get("failed"):
                errors.append(p.get("message", "")) if not errors else None
                break
        elif t == "card" and p.get("kind") == "preflight":  # S8: the pick is checked BEFORE building
            pf = p.get("preflight") or {}
            print(f"{C['m']}{rel(t0)} preflight card{C['x']} {p.get('title')!r} · {p.get('body', '')[:160]!r}"
                  + (f" {C['y']}warning: {p['warning']}{C['x']}" if p.get("warning") else "")
                  + f" {C['dim']}style={pf.get('style')} actions={p.get('actions')}{C['x']}")
            preflights.append({"t": round(time.monotonic() - t0, 1), "title": p.get("title"), "body": p.get("body"),
                               "warning": p.get("warning"), "style": pf.get("style")})
            if not answered:  # a later preflight card replaces the first: answer once
                answered = True
                await ws.send(json.dumps({"type": "action", "payload": {"kind": "build"}}))
                print(f"{C['dim']}{rel(t0)} > action build{C['x']}")
        elif t == "lesson.ready":
            ready = p
            print(f"{C['g']}{rel(t0)} lesson.ready {p['lesson'].get('title')!r} · {len(p['steps'])} steps{C['x']}")
            break
        elif t == "error":
            errors.append(p.get("message", ""))
            print(f"{C['r']}{rel(t0)} error: {p.get('message')}{C['x']}")
            timeout = min(timeout, time.monotonic() - t0 + 3)  # the engine follows up with lesson.building{failed}
    build_s = time.monotonic() - t0
    # what the first step looks like to the app (step.started + checklist), briefly
    if ready:
        end = time.monotonic() + 1.5
        while time.monotonic() < end:
            msg = await recv(ws, 0.3)
            if msg and msg.get("type") in ("step.started", "check.updated", "video.seek", "error"):
                print(f"{C['dim']}{rel(t0)} {msg['type']:14} {json.dumps(msg['payload'], ensure_ascii=False)[:160]}{C['x']}")
    await ws.close()
    eng_log = engine.log_since(log_off)
    path = "?"
    if "lesson cache hit" in eng_log:
        path = "cache"
    rec: dict = {"stage": "build", "stages": stages, "preflight": preflights, "target": target, "url": url or (picked or {}).get("url"), "goal": goal,
                 "build_s": round(build_s, 1), "ok": bool(ready), "errors": errors,
                 "engine_log_errors": [ln for ln in eng_log.splitlines()
                                       if re.search(r"ERROR|Traceback|failed|429|quota", ln)][:15]}
    if ready:
        st = engine.state()
        graph, how = _full_graph(engine, ready["lesson"]["id"], len(ready["steps"]))
        print(f"{C['dim']}  (graph from {how}; engine workdir {st.get('workdir')}){C['x']}")
        info = outline(graph or {}, topic=goal)
        model = (info.get("build") or {}).get("model") or {}
        video_by = str(model.get("video", ""))
        if path != "cache":
            path = ("gemini (watched the video)" if "watched the video" in video_by else
                    "claude transcript" if "transcript" in video_by else video_by or "?")
            if build_s < 15:  # the builder keeps the video draft in demo/cache/lessons/raw/: only the adapt pass ran
                path += f" (video draft from raw cache; adapt pass only: {model.get('adapt')})"
            else:
                path += f" (adapt: {model.get('adapt')})"
        engine_wd = st.get("workdir") or ""
        wd_leak = [f"engine workdir {engine_wd}"] if re.search(r"pinn", engine_wd, re.I) and not re.search(r"pinn", goal, re.I) else []
        rec.update({"path": path, "model": model, "engine_workdir": engine_wd, "lesson_id": ready["lesson"]["id"],
                    **info, "leaks": wd_leak + info["leaks"]})
        print(f"\n{C['bold']}build: {'OK' if ready else 'FAILED'} in {build_s:.1f}s · path {path} · "
              f"{info['n_steps']} steps · engine workdir {engine_wd}{C['x']}")
        if rec["leaks"]:
            print(f"{C['r']}LEAKS: {rec['leaks']}{C['x']}")
    else:
        print(f"\n{C['r']}build FAILED after {build_s:.1f}s: {errors}{C['x']}")
        for ln in rec["engine_log_errors"]:
            print(f"  {C['dim']}{ln[:240]}{C['x']}")
    log_result(rec)
    return rec


# ---------------------------------------------------------------------------------------------- run
LIVE_TYPES = {"step.started", "check.updated", "step.passed", "spotlight", "offtrack", "card", "status", "error",
              "video.seek", "video.pause", "video.play", "diagram", "lesson.ready", "screen.seen"}


async def cmd_run(engine: Engine, duration: float | None, show_metrics: bool, send: list[str] | None = None) -> None:
    ws = await connect(engine)
    t0 = time.monotonic()
    print(f"{C['bold']}{now()} watching :{engine.port} — work in your editor/terminal; type hint | explain | ask <q> | "
          f"show_me | back | diagram | apply_fix | pass | goto <i> | state | quit{C['x']}")
    st = engine.state()
    print(f"{C['dim']}  phase {st.get('phase')} · step {st.get('stepId')} · workdir {st.get('workdir')} · "
          f"screen {st.get('screen')} · precision {st.get('precisionMode')}{C['x']}")

    async def reader() -> None:
        async for raw in ws:
            msg = json.loads(raw)
            t, p = msg.get("type"), msg.get("payload", {})
            if t == "metric" and not show_metrics:
                continue
            if t not in LIVE_TYPES and t != "metric":
                continue
            print(f"{C['dim']}{rel(t0)}{C['x']} " + _fmt_live(t, p), flush=True)

    async def do(line: str) -> bool:
        cmd, _, rest = line.strip().partition(" ")
        if not cmd:
            return True
        if cmd in ("quit", "q", "exit"):
            return False
        if cmd == "sleep":
            await asyncio.sleep(float(rest or 1))
        elif cmd == "state":
            print(json.dumps(engine.state(), indent=1)[:3000])
        elif cmd == "pass":
            httpx.post(f"{engine.http}/debug/pass", timeout=10)
        elif cmd == "goto":
            httpx.post(f"{engine.http}/debug/goto/{int(rest or 0)}", timeout=10)
        elif cmd in ("hint", "explain", "ask", "show_me", "back", "diagram", "apply_fix", "voice_toggle"):
            await ws.send(json.dumps({"type": "action", "payload": {"kind": cmd, **({"text": rest} if rest else {})}}))
        else:
            print(f"? {cmd}")
        return True

    async def stdin() -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line or not await do(line):
                return

    async def scripted() -> None:
        for line in send or []:
            await asyncio.sleep(1.0)
            print(f"{C['dim']}{rel(t0)} > {line}{C['x']}")
            await do(line)
        await asyncio.Event().wait()  # keep watching after the script ran

    tasks = [asyncio.create_task(reader()), asyncio.create_task(scripted())]
    if sys.stdin.isatty():
        tasks.append(asyncio.create_task(stdin()))
    if duration:
        tasks.append(asyncio.create_task(asyncio.sleep(duration)))
    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in tasks:
        t.cancel()
    await ws.close()


def _fmt_live(t: str, p: dict) -> str:
    if t == "step.started":
        v = p.get("video") or {}
        return (f"{C['b']}{C['bold']}step.started #{p.get('index')} {p.get('stepId')} · {p.get('title')}{C['x']} "
                f"[{_mmss(v.get('start'))}–{_mmss(v.get('end'))}]\n           {C['dim']}{(p.get('instructions') or '')[:200]}{C['x']}")
    if t == "check.updated":
        col = {"pass": C["g"], "fail": C["r"]}.get(p.get("status"), C["dim"])
        return (f"{col}check {p.get('status'):7}{C['x']} {p.get('stepId')}/{p.get('checkId')} {p.get('label')}"
                + (f" {C['dim']}· {p['detail']}{C['x']}" if p.get("detail") else ""))
    if t == "step.passed":
        return f"{C['g']}{C['bold']}step.passed {p.get('stepId')} → {p.get('nextStepId')}{C['x']}"
    if t == "spotlight":
        if p.get("clear"):
            return f"{C['dim']}spotlight clear{C['x']}"
        return f"{C['m']}spotlight{C['x']} {p.get('app')} {p.get('rect')} {p.get('caption')!r} matched={p.get('matched')!r}"
    if t == "offtrack":
        d = p.get("diff") or {}
        return (f"{C['y']}{C['bold']}offtrack [{p.get('severity')}] {p.get('title')}{C['x']} — {p.get('body')}"
                + (f"\n           diff {d.get('file')}:{d.get('line')}  yours {d.get('yours')!r} → {d.get('expected')!r}" if d else "")
                + (f"\n           cite {p['citation'].get('url')}" if p.get("citation") else "")
                + f"  actions {p.get('actions')}")
    if t == "card":
        return (f"{C['c']}card [{p.get('kind')}] {p.get('title')}{C['x']} — {(p.get('body') or '')[:300]}"
                + (f"  ⏩ {p['videoJump']}" if p.get("videoJump") else ""))
    if t == "status":
        return f"{C['dim']}status {p.get('state')}{C['x']}"
    if t == "error":
        return f"{C['r']}error {p.get('message')}{C['x']}"
    if t == "metric":
        return f"{C['dim']}metric {p.get('name')}[{p.get('step')}] = {p.get('value')}{C['x']}"
    return f"{C['dim']}{t} {json.dumps(p, ensure_ascii=False)[:160]}{C['x']}"


# ---------------------------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=int(os.environ.get("STAGE_PORT", "8790")))
    ap.add_argument("--no-screen", action="store_true", help="start the engine with ORCH_SCREEN=0")
    ap.add_argument("--open", action="store_true", help="ORCH_OPEN_WORKSPACE=1 (open VS Code on lesson.ready)")
    ap.add_argument("--workdir", help="TUT_WORKDIR for a newly started engine (default: unset, like the engine's own default)")
    ap.add_argument("--fresh", action="store_true", help="restart the engine first")
    ap.add_argument("--env", action="append", default=[], metavar="K=V",
                    help="extra env for a newly started engine (repeatable), e.g. LESSON_MODEL=gemini-3.1-flash-lite")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--timeout", type=float, default=90)
    b = sub.add_parser("build")
    b.add_argument("target", help="YouTube URL, or N = result #N of the last search (by score)")
    b.add_argument("goal", nargs="?", default="")
    b.add_argument("--timeout", type=float, default=420)
    r = sub.add_parser("run")
    r.add_argument("--seconds", type=float, default=None)
    r.add_argument("--metrics", action="store_true")
    r.add_argument("--send", action="append", default=[], metavar="CMD",
                   help="scripted commands, 1 s apart (hint | explain | ask <q> | sleep <s> | pass | goto <i> | ...)")
    e = sub.add_parser("engine")
    e.add_argument("action", choices=["status", "stop", "start", "log"])
    args = ap.parse_args()

    eng = Engine(args.port)
    if args.cmd == "engine":
        if args.action == "stop":
            eng.stop()
        elif args.action == "start":
            eng.ensure(screen=not args.no_screen, open_ws=args.open, workdir=args.workdir, fresh=args.fresh, extra_env=args.env)
        elif args.action == "log":
            print(eng.log_since(max(0, eng.log_size() - 8000)))
        else:
            h = eng.health()
            print(json.dumps({"health": h, "state": eng.state() if h else None}, indent=1)[:4000] if h else "no engine")
        return
    eng.ensure(screen=not args.no_screen, open_ws=args.open, workdir=args.workdir, fresh=args.fresh, extra_env=args.env)
    if args.cmd == "search":
        asyncio.run(cmd_search(eng, args.query, args.timeout))
    elif args.cmd == "build":
        asyncio.run(cmd_build(eng, args.target, args.goal, args.timeout))
    elif args.cmd == "run":
        try:
            asyncio.run(cmd_run(eng, args.seconds, args.metrics, args.send))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
