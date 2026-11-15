"""QA of the coach copy in "Just teach me" (lesson mode), zero cost: no Claude/Gemini/Bright Data calls.

For each cached text lesson (lessons/text-*.json, snapshots of demo/cache/lessons on integration/live),
steps 1-3, and six beginner states (empty file, unsaved, typed in another folder's calculator.py, a typo,
terminal closed, the right code), it runs the REAL orchestrator session in-process: real checks, the
real coach module with no API key (DEMO=1: its offline cards; the model routes can't be tested under the
cost freeze), the screen drawn as full-screen VS Code and OCR'd with the engine's Vision path, a fake
clock and fake keyboard. The learner types, saves (or not), goes idle, asks for a hint and "Show me", and
waits out the stuck timer. Every card / offtrack / spotlight caption / step action line is graded:

  words   card body and title <= 12 words
  file    names the real file (calculator.py)            (action cards)
  app     names VS Code (not "your editor", not another app) (action cards)
  cursor  never says "Cursor"
  label   never glues a check label into a template ("Not yet: …", "Still missing: …")
  one     one action (not "Type …, then save …", not "Skip it, or ask …")

usage (from a checkout of the commit under test, this folder copied in):
  env ANTHROPIC_API_KEY= TUT_ENV=/dev/null DEMO=1 PYTHONPATH=. python -m evals.coach.teach.run_teach
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"

STATES = ["empty", "unsaved", "wrong_folder", "typo", "terminal_closed", "right"]

# ---------------------------------------------------------------- lessons: starter + the file after each step
ADD = "def add(a, b):\n    return a + b\n"
OPS3 = "def subtract(a, b):\n    return a - b\n\ndef multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n    return a / b\n"
DIV_GUARD = ('def subtract(a, b):\n    return a - b\n\ndef multiply(a, b):\n    return a * b\n\n'
             'def divide(a, b):\n    if b == 0:\n        return "Error: divide by zero"\n    return a / b\n')
STARTER_A = '"""A simple Python calculator."""\n\n# Step 1: Start building your calculator here\n'
STARTER_C = "# Simple calculator\n# Write your code below\n"

LESSONS = {
    "A": {"file": "text-43e26ca1d86c37ed.json", "folder": "python-calculator-e430dc", "py": "python", "starter": STARTER_A,
          "after": [STARTER_A + ADD + "\nprint(add(2, 3))\n",
                    STARTER_A + ADD + "\nprint(add(2, 3))\n",
                    STARTER_A + ADD + "\n" + OPS3 + "\nprint(add(2, 3))\n"]},
    "B": {"file": "text-c39ab4384e24d6b4.json", "folder": "_new", "py": "python3", "starter": "",
          "after": ['print("Calculator ready")\n',
                    'print("Calculator ready")\n',
                    ADD + "\n" + DIV_GUARD + "\nprint(add(2, 3))\nprint(divide(8, 0))\n"]},
    "C": {"file": "text-c541a8d6e6f0fb3b.json", "folder": "i-wanna-build-a-calc-in-python-in-vs-cods-9808de", "py": "python",
          "starter": STARTER_C,
          "after": [STARTER_C + 'print("Simple Calculator")\n',
                    STARTER_C + 'print("Simple Calculator")\n',
                    STARTER_C + ADD + '\nprint("Simple Calculator")\nprint(add(2, 3))\n']},
}


def typo(text: str) -> tuple[str, str]:
    """`def(a, b):` for the first function of the step (the hub's example); `prnt(` where there is no def."""
    if "def add(a, b):" in text and "def subtract" not in text:
        return text.replace("def add(a, b):", "def(a, b):", 1), "def add(a, b): -> def(a, b):"
    if "def subtract(a, b):" in text:
        return text.replace("def subtract(a, b):", "def(a, b):", 1), "def subtract(a, b): -> def(a, b):"
    return text.replace("print(", "prnt(", 1), "print( -> prnt(  (no def in this step)"


def run_py(py: str, folder: Path) -> list[str]:
    """The real output of `python calculator.py` in that folder (stdout + stderr), as a terminal shows it."""
    p = subprocess.run([sys.executable, "calculator.py"], cwd=folder, capture_output=True, text=True, timeout=20)
    out = p.stdout + p.stderr
    for f in (str(folder.resolve()), str(folder)):
        out = out.replace(f, f"/Users/learner/miyagi/lessons/{folder.name}")
    return [f"learner@MacBook-Pro {folder.name} % {py} calculator.py", *out.rstrip("\n").splitlines(),
            f"learner@MacBook-Pro {folder.name} % "]


# ---------------------------------------------------------------- a screen bridge over one OCR'd frame
class ObsBridge:
    active = True

    def __init__(self) -> None:
        self.obs = None
        self.png: Path | None = None
        self.reader = None  # no live reader: editor-line AX lookups are skipped, as in tests

    def latest(self):
        return self.obs

    def lines(self, obs=None):
        o = obs or self.obs
        return o.lines_by_app() if o is not None else None

    def locate(self, match: str, app: str | None = None):
        from server.screen.match import locate_match

        if self.obs is None or not match:
            return None
        r = locate_match(self.obs, match, app)
        if r is None:
            return None
        return {"rect": r.rect.to_dict(), "app": r.app, "matched": (r.matched or "")[:200]}

    def region(self, name: str, app: str | None = None):
        from server.screen.regions import find_region

        reg = find_region(self.obs, name, app) if self.obs is not None else None
        return reg.rect.to_dict() if reg else None

    def screenshot(self):
        from PIL import Image

        return Image.open(self.png).convert("RGB") if self.png else None

    def set_overlay(self, rects):
        pass

    def poke(self):
        pass

    def watch(self, *a, **k):
        pass

    def unwatch(self):
        pass

    def stop(self):
        pass

    def down_reason(self):
        return None


def draw(state: str, L: dict, k: int, root: Path, frame: Path) -> dict:
    """Make the learner's folder(s) for this state and the screen. -> facts about the state."""
    from server.screen.reader import observe_image

    from .render import render

    lesson_dir = root / L["folder"]
    lesson_dir.mkdir(parents=True, exist_ok=True)
    prev = L["starter"] if k == 0 else L["after"][k - 1]
    right = L["after"][k]
    on_disk, shown, folder, dirty, term, note = right, right, L["folder"], False, None, ""
    if state == "empty":
        on_disk = shown = L["starter"]
    elif state == "unsaved":
        on_disk, dirty = prev, True
    elif state == "wrong_folder":
        on_disk, folder = prev, "Desktop"
        (root / "Desktop").mkdir(exist_ok=True)
        (root / "Desktop" / "calculator.py").write_text(right)
    elif state == "typo":
        on_disk, note = typo(right)
        shown = on_disk
    (lesson_dir / "calculator.py").write_text(on_disk)
    if state in ("typo", "right"):  # they ran it: the real output in VS Code's terminal panel
        term = run_py(L["py"], lesson_dir)
    elif state != "terminal_closed":
        term = [f"learner@MacBook-Pro {L['folder']} % "]
    tree = ["calculator.py", "README.md"] if folder != "Desktop" else ["calculator.py", "Screenshot 2026-11-14.png", "notes.txt"]
    caret = max(1, len(shown.splitlines()))
    render(frame, folder=folder, file="calculator.py", code=shown, tree=tree, dirty=dirty, terminal=term, caret_line=caret)
    obs = observe_image(str(frame))
    return {"obs": obs, "lesson_dir": lesson_dir, "on_disk": on_disk, "shown": shown, "terminal": term, "note": note,
            "title": f"{'● ' if dirty else ''}calculator.py — {folder}"}


# ---------------------------------------------------------------- one run
async def run_one(lid: str, k: int, state: str, work: Path) -> dict:
    from server.orchestrator.hub import Hub
    from server.orchestrator.inputs import FakeInputs
    from server.orchestrator.modules import Modules
    from server.orchestrator.session import LessonSession

    import server.coach as coach_pkg

    routes: list[dict] = []
    real_diag = getattr(coach_pkg, "_qa_real_diagnose", None) or coach_pkg.diagnose
    coach_pkg._qa_real_diagnose = real_diag

    async def diag(*a, **kw):  # same call, but keep the route the orchestrator's public() strips
        card = await real_diag(*a, **kw)
        m = (card or {}).get("_meta") or {}
        routes.append({"route": m.get("route"), "triage": m.get("triage"), "fallback": m.get("fallback_reason"),
                       "playbook": m.get("playbook_id"), "title": (card or {}).get("title")})
        return card

    diag.__signature__ = __import__("inspect").signature(real_diag)
    coach_pkg.diagnose = diag
    L = LESSONS[lid]
    graph = json.loads((HERE / "lessons" / L["file"]).read_text())
    root = work / f"{lid}-s{k + 1}-{state}"
    st = draw(state, L, k, root, root / "screen.png")
    os.environ["TUT_WORKDIR"] = str(st["lesson_dir"])

    class Clock:
        t = 1000.0

        def __call__(self):
            return self.t

    clock = Clock()
    inputs = FakeInputs(clock)
    bridge = ObsBridge()
    bridge.obs, bridge.png = st["obs"], root / "screen.png"
    hub = Hub(strict=False)
    log_: list[dict] = []  # every event, in order (the hub's history is a bounded deque)
    phase = ["load"]

    async def emit(type_: str, payload: dict | None = None) -> None:
        log_.append({"type": type_, "payload": payload or {}, "phase": phase[0]})
        await hub.emit(type_, payload)

    s = LessonSession(emit, Modules(demo=True), clock=clock, idle_gate_s=3, advance_delay_s=0, metric_eval_s=0,
                      result_stagger_s=0, build_tick_s=0.01, screen=bridge, seen_interval_s=0, inputs=inputs)
    s.last_obs = st["obs"]
    g = copy.deepcopy(graph)
    g["lesson"]["workdir"] = str(st["lesson_dir"])
    await s.load_graph(g)
    await s.drain()
    if k:
        await s.start_step(k)
        await s.drain()
    mark = len(log_)
    started_ix = max((i for i, e in enumerate(log_) if e["type"] == "step.started"), default=0)
    timeline: list[str] = []

    async def settle(label: str) -> None:
        phase[0] = label
        await asyncio.sleep(0)
        await s.drain()
        for _ in range(3):  # spawned coach tasks
            await asyncio.sleep(0.05)
            await s.drain()
        timeline.append(label)

    phase[0] = "typed / screen"
    # the learner works on the step: types (except "empty"), the screen changes, saves when the state says so
    if state != "empty":
        inputs.key()
    clock.t += 0.5
    await s.on_screen(st["obs"])
    await settle("typed / screen")
    async def step(label: str, coro) -> None:
        phase[0] = label
        await coro
        await settle(label)

    if state in ("typo", "terminal_closed", "right"):
        await step("saved", s.on_file_change([str(st["lesson_dir"] / "calculator.py")]))
    clock.t += 1.0
    await step("tick while typing", s.tick())
    clock.t += 4.0
    await step("idle 5 s", s.tick())
    if state in ("typo", "terminal_closed", "right") and not s.passed:
        clock.t += 25.0
        await step("saved again", s.on_file_change([str(st["lesson_dir"] / "calculator.py")]))
        clock.t += 4.0
        await step("idle after 2nd save", s.tick())
    if not s.passed:
        await step("hint", s.action("hint"))
        await step("show me", s.action("show_me"))
        clock.t += 100.0
        await step("idle 100 s", s.tick())
    await s.end_lesson("qa run done")  # cancels the lesson's timers (spotlight retries)
    events = [e for e in log_[mark:] if e["type"] != "lesson.ended"]
    cut = next((i for i, e in enumerate(events) if e["type"] == "step.passed"), None)
    after_pass = events[cut + 1:] if cut is not None else []
    events = events[:cut + 1] if cut is not None else events  # grade only the step under test
    started = log_[started_ix] if log_ and log_[started_ix]["type"] == "step.started" else None
    passed = any(e["type"] == "step.passed" for e in events)
    step = g["steps"][k]
    labels = [c.get("label", "") for st_ in g["steps"] for c in (st_.get("checks") or []) + (st_.get("precision_checks") or [])]
    copy_items = collect(events, started)
    for it in copy_items:
        it["grades"] = grade(it, labels)
    return {"lesson": lid, "lesson_title": g["lesson"]["title"], "step": step["id"], "step_title": step["title"], "state": state,
            "note": st["note"], "window_title": st["title"], "on_disk": st["on_disk"], "terminal": st["terminal"],
            "passed": passed, "status": next((e["payload"].get("state") for e in reversed(events) if e["type"] == "status"), None),
            "checks": {e["payload"]["checkId"]: [e["payload"]["status"], e["payload"].get("detail")] for e in events if e["type"] == "check.updated"},
            "copy": copy_items, "timeline": timeline, "coach_routes": routes,
            "next_step_cards": [[e["payload"].get("title"), e["payload"].get("body")] for e in after_pass if e["type"] in ("card", "offtrack")][:4],
            "errors": [e["payload"].get("message") for e in events if e["type"] == "error"]}


def collect(events: list[dict], started: dict | None) -> list[dict]:
    out = []
    if started:
        p = started["payload"]
        out.append({"src": "step.started", "title": p.get("title", ""), "body": p.get("instructions", ""), "kind": "action line"})
    seen = set()
    for e in events:
        t, p = e["type"], e.get("payload") or {}
        if t in ("card", "offtrack"):
            key = (t, p.get("title"), p.get("body"))
            if key in seen:
                continue
            seen.add(key)
            out.append({"src": t, "title": p.get("title", ""), "body": p.get("body", ""), "kind": p.get("kind") or t,
                        "level": p.get("level"), "actions": p.get("actions"), "when": e.get("phase")})
        elif t == "spotlight" and p.get("caption"):
            key = ("spot", p.get("caption"))
            if key in seen:
                continue
            seen.add(key)
            out.append({"src": "spotlight", "title": "", "body": p["caption"], "kind": "caption", "when": e.get("phase")})
    return out


# ---------------------------------------------------------------- grading
IMPERATIVE = {"type", "run", "save", "open", "press", "click", "add", "delete", "replace", "move", "check", "use", "put",
              "write", "define", "change", "rename", "select", "go", "scroll", "try", "skip", "ask", "paste", "copy", "close",
              "confirm", "make", "create", "indent", "remove", "fix", "keep", "start", "wrap", "quote", "call", "leave",
              "look", "watch", "compare", "undo", "apply", "re-run", "rerun", "enter", "bring", "show", "follow", "finish",
              "fill", "insert", "place", "set", "cd"}
STATUS_TITLES = re.compile(r"^(Looks done\?|Undone|Fix applied|Building the next part…|Command copied)$")
LABEL_GLUE = re.compile(r"\b(Not yet|Still missing|Missing)\s*:", re.I)


def words(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))


CLAUSE_VERB = re.compile(r"(?:^|[,.;:!?]\s+|\bthen\s+|\band\s+|\bor\s+)(" + "|".join(sorted(IMPERATIVE, key=len, reverse=True)) + r")\b", re.I)


def actions(body: str) -> int:
    """Imperative verbs that open a clause: "In x.py, type …" = 1; "write …, then add …" = 2; "Skip it, or ask …" = 2."""
    return len(CLAUSE_VERB.findall(re.sub(r"`[^`]*`", "", body or "")))


def grade(it: dict, labels: list[str]) -> dict:
    title, body = it.get("title") or "", it.get("body") or ""
    text = f"{title} {body}"
    status = bool(STATUS_TITLES.match(title))
    action_card = it["src"] in ("card", "offtrack") and not status
    g = {"words": words(body) <= 12 and words(title) <= 12,
         "cursor": not re.search(r"\bCursor\b", text),
         "label": not (LABEL_GLUE.search(text) or any(len(l.split()) >= 3 and l.lower() in text.lower() for l in labels)),
         "one": actions(body) <= 1}
    if action_card or it["src"] == "step.started":
        g["file"] = "calculator.py" in text
        g["app"] = bool(re.search(r"\bVS Code\b|Visual Studio Code", text))
    return g


# ---------------------------------------------------------------- main
async def main(only: list[str]) -> None:
    import logging

    logging.basicConfig(level=logging.ERROR)
    from server.coach import llm

    assert not llm.has_credentials(), "an API key is visible: refusing to run (cost freeze)"
    assert os.environ.get("DEMO") == "1"
    OUT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="teach-qa-"))
    results = []
    for lid in LESSONS:
        for k in range(3):
            for state in STATES:
                tag = f"{lid}-s{k + 1}-{state}"
                if only and not any(o in tag for o in only):
                    continue
                try:
                    r = await run_one(lid, k, state, work)
                except Exception as e:  # noqa: BLE001
                    import traceback

                    r = {"lesson": lid, "step": f"s{k + 1}", "state": state, "crash": f"{type(e).__name__}: {e}",
                         "trace": traceback.format_exc()[-1500:]}
                results.append(r)
                bad = [(c["src"], c["title"], c["body"], [k_ for k_, v in c["grades"].items() if not v]) for c in r.get("copy", [])
                       if not all(c["grades"].values())]
                print(f"{tag}: passed={r.get('passed')} status={r.get('status')} copy={len(r.get('copy', []))} fails={len(bad)} "
                      f"{r.get('crash', '')}", flush=True)
    (OUT / "teach.json").write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str))
    print(f"wrote {OUT / 'teach.json'} ({len(results)} runs); work dir {work}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
