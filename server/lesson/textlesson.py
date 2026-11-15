"""No-video lessons ("Just teach me"): goal -> researched, step-by-step lesson in the same step-graph schema.

No Gemini. Claude only:
  * plan (claude-sonnet-5-5): 3-8 steps for the goal, adapted to the learner's starter files;
  * research (claude-sonnet-5-5 + the web_search / web_fetch server tools), in parallel: official docs
    and tutorials; only URLs that came back from the tools are ever cited;
  * per step (claude-haiku-5-5, Opus only when a quality check fails): the exact code to type, where to
    type it (targets: file + anchor), machine-checkable checks, hints, common mistakes.
Step 1 goes out through on_update as soon as it's ready (no waiting on research); the rest follow in
order. lesson.mode = "lesson"; steps have no `video`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time

from . import builder, claude, cost, gemini
from .schema import schema_errors
from .workdir import scan

log = logging.getLogger("server.lesson")

RESEARCH_MODEL_ROLE = "segment"  # Sonnet: good at searching + summarizing
RESEARCH_WAIT_S = float(os.environ.get("LESSON_TEXT_RESEARCH_WAIT_S", "25"))  # later steps wait this long for notes
WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 4},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 2},
]

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "libraries": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "version": {"type": "string"}},
                                                 "required": ["name", "version"]}},
        "steps": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "instructions": {"type": "string"}, "file": {"type": "string"}},
            "required": ["title", "instructions", "file"]}},
    },
    "required": ["title", "libraries", "steps"],
}

STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "file": {"type": "string", "description": "file to create/edit, relative to the workdir"},
        "code": {"type": "string", "description": "the exact code to type in this step (only this step's addition)"},
        "run_command": {"type": "string", "description": "command to run afterwards, if any"},
        "expected_output": {"type": "string"},
        "checks": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["screen_contains", "screen_absent", "metric_threshold", "metric_trend"]},
            "label": {"type": "string"}, "app": {"type": "string"}, "pattern": {"type": "string"},
            "metric": {"type": "string"}, "metric_pattern": {"type": "string"}, "op": {"type": "string"}, "value": {"type": "number"}},
            "required": ["type", "label"]}},
        "precision_checks": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["file_exists", "file_contains", "command_exit_ok", "output_contains"]},
            "label": {"type": "string"}, "file": {"type": "string"}, "pattern": {"type": "string"}, "command": {"type": "string"}},
            "required": ["type", "label"]}},
        "targets": {"type": "array", "items": {"type": "object", "properties": {
            "file": {"type": "string"}, "match": {"type": "string"}, "caption": {"type": "string"}, "app": {"type": "string"}},
            "required": ["file", "match", "caption"]}},
        "hints": {"type": "array", "items": {"type": "string"}},
        "common_mistakes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["file", "code", "checks", "targets", "hints"],
}

SYSTEM = """You are a patient programming teacher building a hands-on lesson with no video: the learner
types code in their own editor while an overlay boxes exactly where to type and checks their screen
(on-device OCR of the editor and terminal). Teach by doing: small steps, each ending in something
visible. Use current, official APIs."""

PLAN_PROMPT = """Learner's goal: {goal}

The learner's project folder (starter files from their workspace):
{workdir}

Plan a hands-on lesson of 3-8 steps that reaches the goal from this starting point. Each step adds one
small, visible piece (a function, a component, a command that prints something).
The app has already created the lesson folder and opens each file for the learner: never tell them to
mkdir, cd, touch or create folders, and never write absolute paths; name files relative to the lesson folder
("in calculator.py"). Use the terminal only for real tool commands (npm create, pip install, running the program).
Order: step 1 is always typing code into a file (never a terminal step); a step that runs a program comes
AFTER the steps that write that program's code.
title: imperative, <= 6 words; instructions: ONE imperative sentence, at most 10 words, no parentheses; say
"terminal" only for commands and name the file only for code ("Add an add function to calculator.py.",
"Run your calculator in the terminal."); file: the file the step edits (relative path), or "" for a
terminal-only step. libraries: what the lesson uses, with current major versions."""

STEP_PROMPT = """Learner's goal: {goal}. Lesson: "{lesson}". All steps: {outline}

Write step {index}: "{title}". {instructions}
File: {file}

The learner's project folder now:
{workdir}

Code from the earlier steps (already typed):
{earlier}

{research}
Return for THIS step only (files are relative to the lesson folder, which already exists and is open; no
mkdir/cd/touch, no absolute paths):
- code: exactly what to type in this step (only the new/changed lines, correct and runnable with the
  earlier steps' code), file: where it goes;
- targets: file + `match` = a short literal anchor already in the file or typed in this step (e.g.
  "function add(", "export default App") + caption, so the overlay can box exactly where to type;
- checks (at least one; graded from the learner's screen): screen_contains with app "Code" and a SHORT regex
  (< 60 chars, spacing-tolerant) for a distinctive fragment of this step's code; and, if the step runs
  something, a screen_contains with app "Terminal" on what it PRINTS (never the typed command);
  precision_checks: file_contains on the same fragment in `file`, command_exit_ok for a quick run;
{stack_guide}
- hints: 2-3, gentlest first; common_mistakes: concrete ones for this step."""


def _key(goal: str, workdir: str, info) -> str:
    return "text-" + hashlib.sha256(json.dumps(["text", " ".join(goal.lower().split()), builder.workdir_fingerprint(workdir, info)]).encode()).hexdigest()[:16]


async def research(goal: str) -> dict:
    """Web research with Claude's web_search / web_fetch tools -> {"notes", "sources": [{url, title}]}.
    Sources are only URLs that appeared in the tools' results."""
    prompt = (f"Find the official documentation and one or two high-quality tutorials for: {goal}. "
              "Then write concise notes (<= 300 words) a teacher needs: current setup commands, the key APIs with "
              "their exact current names/signatures, and pitfalls. Cite the pages you used.")
    messages = [{"role": "user", "content": prompt}]
    mid = claude.model(RESEARCH_MODEL_ROLE)
    sources: dict[str, str] = {}
    notes: list[str] = []
    for _turn in range(3):  # pause_turn: send the paused turn back and the server resumes
        cost.count("claude_calls")
        async with claude.client().messages.stream(model=mid, max_tokens=8000, messages=messages, tools=WEB_TOOLS,
                                                   thinking={"type": "adaptive"}, output_config={"effort": "low"}) as st:
            msg = await st.get_final_message()
        u = getattr(msg, "usage", None)
        cost.add_tokens(mid, getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0))
        for b in msg.content:
            t = getattr(b, "type", "")
            if t == "web_search_tool_result" and isinstance(getattr(b, "content", None), list):  # an error is an object, not a list
                for r in b.content:
                    if getattr(r, "url", None):
                        sources.setdefault(r.url, getattr(r, "title", "") or r.url)
            elif t == "web_fetch_tool_result":
                c = getattr(b, "content", None)
                url = getattr(c, "url", None)
                if url:
                    sources.setdefault(url, url)
            elif t == "text" and getattr(b, "text", ""):
                notes.append(b.text)
        if msg.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": msg.content}]
    return {"notes": "\n".join(notes).strip()[:4000], "sources": [{"url": u, "title": t} for u, t in sources.items()]}


async def build_text_lesson(goal: str, workdir: str, on_update=None, *, cache: bool = True, refresh: bool = False) -> dict:
    """See module docstring. Returns the complete graph; on_update(graph, complete) gets step 1 first."""
    t0 = time.time()
    counter = cost.current() or cost.start()
    info = scan(workdir)
    key = _key(goal, workdir, info)
    path = builder.CACHE_DIR / f"{key}.json"
    if cache and not refresh and path.is_file():
        g = json.loads(path.read_text())
        g["lesson"]["workdir"] = workdir
        return g

    research_task = asyncio.ensure_future(_safe_research(goal))
    summary = info.summary_for_prompt().replace(str(info.root), "the lesson folder")

    def plan_ok(o: dict) -> str | None:
        n = len(o.get("steps") or [])
        return None if 3 <= n <= 8 else f"{n} steps"

    builder._emit("planning", "planning the lesson")
    plan = await claude._generate_json(SYSTEM, PLAN_PROMPT.format(goal=goal, workdir=summary), PLAN_SCHEMA,
                                       effort="medium", role="segment", check=plan_ok)
    steps_plan = order_plan(plan["steps"])
    outline = "; ".join(f"{i}. {s['title']}" for i, s in enumerate(steps_plan, 1))
    libs = {lb["name"]: lb.get("version", "") for lb in plan.get("libraries") or [] if lb.get("name")}
    done: dict[int, dict] = {}
    sources: list[dict] = []
    warnings: list[str] = []

    def graph_now(complete: bool) -> dict:
        ordered = [done[i] for i in sorted(done) if all(j in done for j in range(1, i + 1))]
        g = {"lesson": {"id": f"lesson-{key[5:13]}", "title": plan.get("title") or goal, "goal": goal, "workdir": workdir,
                        "libraries": libs, "mode": "lesson", "complete": complete, "builtBy": "claude"},
             "sources": [{"id": f"src{i}", "kind": "repo" if "github.com/" in s["url"] else "blog", "title": s["title"][:200], "url": s["url"]}
                         for i, s in enumerate(sources, 1)],
             "steps": json.loads(json.dumps(ordered)),
             "build": {"mode": "lesson", "seconds": round(time.time() - t0, 1), "warnings": list(warnings),
                       "model": {"plan": claude.model("segment"), "steps": claude.model("detail"), "research": claude.model(RESEARCH_MODEL_ROLE)}}}
        return g

    async def emit(complete: bool) -> None:
        if on_update is None:
            return
        try:
            r = on_update(graph_now(complete), complete)
            if asyncio.iscoroutine(r):
                await r
        except Exception as e:  # noqa: BLE001
            log.warning("on_update failed: %s", e)

    async def step(i: int, earlier: str, notes: str) -> dict:
        sp = steps_plan[i - 1]
        prompt = STEP_PROMPT.format(goal=goal, lesson=plan.get("title", ""), outline=outline, index=i, title=sp["title"],
                                    instructions=sp["instructions"], file=sp.get("file") or "(terminal)", workdir=summary,
                                    earlier=earlier or "(none yet)",
                                    research=(f"Research notes (current docs):\n{notes}\n" if notes else ""),
                                    stack_guide=gemini.STACK_GUIDE)

        def ok(o: dict) -> str | None:
            if not ((o.get("code") or "").strip() or (o.get("run_command") or "").strip()):
                return "no code"
            if not o.get("checks"):
                return "no checks"
            if not any((t.get("match") or "").strip() for t in o.get("targets") or []):
                return "no target anchor"
            return None

        d = await claude._generate_json(SYSTEM, prompt, STEP_SCHEMA, effort="low", structured=False, role="detail", check=ok)
        return shape_step(sanitize_step(_assemble_step(i, sp, d), workdir))

    # 1. step 1 right away (no waiting for research)
    first = await step(1, "", "")
    done[1] = first
    log.info("text lesson: step 1 ready in %.1fs", time.time() - t0)
    builder._emit("first_steps", "1 step")
    await emit(False)

    # 2. research (bounded wait), then the rest in parallel, appended in order
    try:
        res = await asyncio.wait_for(asyncio.shield(research_task), max(0.0, RESEARCH_WAIT_S - (time.time() - t0)))
    except (asyncio.TimeoutError, TimeoutError):
        res = {"notes": "", "sources": []}
        warnings.append("research took too long; later steps were written without it")
    sources.extend(res.get("sources") or [])
    earlier = f"# {first.get('file') or ''}\n{first.get('code', '')}"
    tasks = {i: asyncio.ensure_future(step(i, earlier, res.get("notes", ""))) for i in range(2, len(steps_plan) + 1)}
    for i in range(2, len(steps_plan) + 1):
        try:
            done[i] = await tasks[i]
        except RuntimeError as e:
            warnings.append(f"step {i} ({steps_plan[i - 1]['title']}) failed: {str(e)[:160]}")
            continue
        builder._emit("more_steps", f"step {i}/{len(steps_plan)}")
        await emit(False)

    g = graph_now(True)
    g["steps"] = [done[i] for i in sorted(done)]
    for k, s in enumerate(g["steps"], 1):  # renumber if a middle step failed
        _renumber(s, k)
    link_run_steps(g["steps"])
    _finalize(g, info)
    g["build"]["cost"] = json.loads(json.dumps(counter))
    errs = schema_errors(g)
    if errs:
        raise RuntimeError("text lesson failed contract validation:\n" + "\n".join(errs))
    if cache and g["steps"] and not any("failed" in w for w in warnings):
        builder.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(g, indent=2))
    await emit(True)
    return g


async def _safe_research(goal: str) -> dict:
    try:
        return await research(goal)
    except Exception as e:  # noqa: BLE001  research makes the lesson better, never blocks it
        log.warning("research failed: %s", e)
        return {"notes": "", "sources": []}


def _assemble_step(i: int, sp: dict, d: dict) -> dict:
    s = {"id": f"s{i}", "index": i, "title": builder._clip_words(sp["title"], 6), "instructions": sp["instructions"].strip(),
         "code": d.get("code", ""), "file": d.get("file") or sp.get("file") or "",
         "checks": [c for j, raw in enumerate(d.get("checks") or [], 1) if (c := builder.clean_check(raw, f"s{i}c{j}"))],
         "precision_checks": [c for j, raw in enumerate(d.get("precision_checks") or [], 1) if (c := builder.clean_check(raw, f"s{i}p{j}"))],
         "targets": [{k: t[k] for k in ("app", "file", "match", "caption") if t.get(k)} for t in d.get("targets") or [] if t.get("match")],
         "explanations": [], "hints": [h for h in d.get("hints") or [] if h], "common_mistakes": [m for m in d.get("common_mistakes") or [] if m]}
    if (d.get("run_command") or "").strip():
        s["run_command"] = d["run_command"].strip()
    for t in s["targets"]:  # the overlay boxes the editor, and the file is what the step edits
        t.setdefault("app", "Code")
        t.setdefault("file", s["file"])
    return s


def _renumber(s: dict, k: int) -> None:
    s["index"], s["id"] = k, f"s{k}"
    for key, tag in (("checks", "c"), ("precision_checks", "p")):
        for j, c in enumerate(s.get(key) or [], 1):
            c["id"] = f"s{k}{tag}{j}"


def _finalize(g: dict, info) -> None:
    """Same deterministic clean-up as video lessons: stack error text, literal regexes, repair."""
    builder.normalize_checks(g, info.metrics)
    fixed = builder.repair(g, info)
    g["steps"] = fixed["steps"]
    probs = [p for p in builder.lint(g, info.metrics, set(info.files)) if not re.match(r"^s\d+: video", p)]
    g["build"]["warnings"] += probs


_SETUP_CMD = re.compile(r"^\s*(mkdir|touch|cd|md|New-Item|ni|type\s+nul)\b", re.I)
_SETUP_PHRASE = re.compile(r"\b(mkdir|touch|cd\s+\S|create (a|the|an) (new )?(folder|directory)|in your terminal,? run)\b", re.I)
_ABS_PATH = re.compile(r"(?<![\w.])(/Users/|/home/|/tmp/|/private/|[A-Z]:\\\\)[^\s`'\"]*")


def sanitize_step(step: dict, workdir: str) -> dict:
    """The engine prepares the folder and opens the file: strip absolute paths and folder-setup commands
    from what the learner reads, keep one short action, and make sure a check looks for the typed code."""
    root = str(workdir).rstrip("/")
    for k in ("instructions", "code"):
        t = step.get(k) or ""
        if root:
            t = t.replace(root + "/", "").replace(root, "the lesson folder")
        t = _ABS_PATH.sub(lambda m: m.group(0).rsplit("/", 1)[-1], t)
        step[k] = t
    code_lines = [ln for ln in (step.get("code") or "").splitlines()]
    kept = [ln for ln in code_lines if not _SETUP_CMD.match(ln) and not re.match(r"^\s*&&", ln)]
    kept = [re.sub(r"^\s*(mkdir|touch|cd)\b[^&;]*(&&|;)\s*", "", ln, flags=re.I) for ln in kept]
    step["code"] = "\n".join(kept).strip("\n")
    if step.get("run_command") and _SETUP_CMD.match(step["run_command"]):
        step.pop("run_command")
    # whole sentences (split at ". " so "calculator.py" stays intact); drop the ones that are folder setup
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", step.get("instructions") or "") if x.strip()]
    sentences = [x for x in sentences if not _SETUP_PHRASE.search(x)]
    instr = sentences[0] if sentences else ""
    f = step.get("file") or ""
    if len(instr) < 8:
        instr = f"In {f}, type the code below." if f else "Type the code below."
    step["instructions"] = instr
    # the check that counts is the typed code in the file; terminal checks for a step that no longer runs anything go
    if not step.get("run_command"):
        step["checks"] = [c for c in step["checks"] if c.get("app") not in ("Terminal", "iTerm2")]
    if f and step["code"].strip() and not any(c.get("type") == "file_contains" for c in step.get("precision_checks") or []):
        frag = next((ln.strip() for ln in step["code"].splitlines() if len(ln.strip()) >= 6), step["code"].strip())[:60]
        step.setdefault("precision_checks", []).append({"id": "", "type": "file_contains", "label": "code typed in the file",
                                                         "file": f, "pattern": builder.literal_pattern(frag)})
    if not step["checks"] and f and step["code"].strip():
        frag = next((ln.strip() for ln in step["code"].splitlines() if len(ln.strip()) >= 6), step["code"].strip())[:60]
        step["checks"] = [{"id": "", "type": "screen_contains", "label": "code typed", "app": "Code", "pattern": builder.literal_pattern(frag)}]
    for key, tag in (("checks", "c"), ("precision_checks", "p")):
        for j, c in enumerate(step.get(key) or [], 1):
            c["id"] = f"{step['id']}{tag}{j}"
    return step


# --------------------------------------------------------------------------- #
# Step order and wording for no-video lessons (Michael: "Type this in the VS Code terminal (use python…"
# with `python calculator.py` while calculator.py was still empty)
# --------------------------------------------------------------------------- #
_RUN_FILE = re.compile(r"\b([\w./-]+\.(?:py|js|mjs|ts|rs|go|rb|java|sh))\b")
_RUN_WORD = re.compile(r"\b(run|execute|launch|start)\b", re.I)
MAX_WORDS = 10


def _is_run_plan(st: dict) -> bool:
    return not (st.get("file") or "").strip()


def _ran_file(text: str) -> str | None:
    m = _RUN_FILE.search(text or "")
    return m.group(1) if m else None


def order_plan(steps: list[dict]) -> list[dict]:
    """Step 1 types code into a file (never a terminal step); a run step that the plan put before any of the code
    it runs moves after the last step writing that file. Done on the plan, before any step is built or shown,
    so step ids never change later."""
    steps = list(steps)
    for _ in range(len(steps)):
        moved = False
        for k, st in enumerate(steps):
            if not _is_run_plan(st):
                continue
            f = _ran_file(f"{st.get('title', '')} {st.get('instructions', '')}")
            writers = [j for j, o in enumerate(steps) if f and (o.get("file") or "") == f]
            if writers and min(writers) > k:  # runs a file nobody has written yet
                steps.insert(max(writers), steps.pop(k))
                moved = True
                break
        if not moved:
            break
    if steps and _is_run_plan(steps[0]):
        first_code = next((k for k, st in enumerate(steps) if not _is_run_plan(st)), None)
        if first_code is not None:
            steps.insert(0, steps.pop(first_code))
    return steps


def _noun(file: str) -> str:
    stem = re.sub(r"[_-]+", " ", os.path.splitext(os.path.basename(file or ""))[0]).strip()
    return stem if stem and stem.lower() not in ("main", "index", "app", "script") else "program"


def _is_run_step(st: dict) -> bool:
    cmd, code = (st.get("run_command") or "").strip(), (st.get("code") or "").strip()
    return bool(cmd) and (not (st.get("file") or "").strip() or not code or code == cmd)


def shape_step(st: dict) -> dict:
    """One imperative sentence, <= 10 words, no parentheticals; 'terminal' only for commands, the file only for code."""
    text = re.sub(r"\s*\([^)]*\)", "", st.get("instructions") or "")  # no parentheticals
    text = re.split(r"(?<=[.!?])\s+", text.strip())[0] if text.strip() else ""
    text = re.sub(r"\s*(and\s+)?(type|run|enter)\s+(this|the following|it)?\s*:?\s*$", "", text, flags=re.I).rstrip(" :,;")
    if _is_run_step(st):
        ran = _ran_file(st["run_command"]) or st.get("file") or ""
        st["code"] = st["run_command"]  # the snippet is the command to type in the terminal
        if ran:
            st["file"] = ran  # the file it runs (checks look for its code there)
        st["instructions"] = f"Run your {_noun(ran)} in the terminal."
        return st
    f = st.get("file") or ""
    words = text.split()
    if (not words or len(words) > MAX_WORDS or re.search(r"\bterminal\b", text, re.I) or _RUN_WORD.match(text)):
        text = f"In {f}, type the code below." if f else "Type the code below."
    elif not text.endswith((".", "!", "?")):
        text += "."
    st["instructions"] = text[0].upper() + text[1:] if text else text
    return st


def link_run_steps(steps: list[dict]) -> None:
    """A run step's check requires the code it runs to be in the file: the last fragment written to that file."""
    for k, st in enumerate(steps):
        if not _is_run_step(st):
            continue
        f = st.get("file") or ""
        writers = [o for o in steps[:k] if (o.get("file") or "") == f and not _is_run_step(o) and (o.get("code") or "").strip()]
        if not writers:
            continue
        lines = [ln.strip() for ln in writers[-1]["code"].splitlines() if ln.strip()]
        frag = next((ln for ln in reversed(lines) if len(ln) >= 6), max(lines, key=len) if lines else "")
        if not frag:
            continue
        pc = st.setdefault("precision_checks", [])
        pc[:] = [c for c in pc if c.get("type") != "file_contains"]
        pc.insert(0, {"id": "", "type": "file_contains", "label": builder.plain_label(f"code is in {f}", {"type": "file_contains", "file": f}), "file": f,
                      "pattern": builder.literal_pattern(frag[:60])})
        for j, c in enumerate(pc, 1):
            c["id"] = f"{st['id']}p{j}"
