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
        "overview": {"type": "string", "description": "<= 60 words: what we build and the plan, in plain words"},
        "primer": {"type": "array", "description": "3-5 core concepts a beginner needs before the steps", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "body": {"type": "string"}, "code": {"type": "string"}, "diagramPrompt": {"type": "string"}},
            "required": ["title", "body", "code", "diagramPrompt"]}},
        "steps": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "instructions": {"type": "string"}, "file": {"type": "string"},
            "what": {"type": "string"}, "why": {"type": "string"},
            "concepts": {"type": "array", "items": {"type": "integer"}, "description": "1-based numbers of the primer concepts this step uses"},
            "estMinutes": {"type": "integer", "description": "whole minutes a beginner needs for this step"}},
            "required": ["title", "instructions", "file", "what", "why", "concepts", "estMinutes"]}},
        # learn-anything screens (drawer v2, "Before you start"): same call, no extra model call
        "build": {"type": "object", "properties": {"summary": {"type": "string"}, "outcome": {"type": "string"}},
                  "required": ["summary", "outcome"]},
        "flow": {"type": "array", "description": "3-6 boxes of a 'how it works' diagram", "items": {"type": "object", "properties": {
            "label": {"type": "string"}, "detail": {"type": "string"},
            "step": {"type": "integer", "description": "1-based number of the step that builds this box, 0 if none"}},
            "required": ["label", "detail", "step"]}},
        "prerequisites": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "why": {"type": "string"}}, "required": ["title", "why"]}},
        "learnFirst": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "minutes": {"type": "integer"},
            "kind": {"type": "string", "enum": ["notebook", "interactive", "video", "read"]},
            "covers": {"type": "integer", "description": "1-based number of the prerequisite it teaches"}},
            "required": ["title", "minutes", "kind", "covers"]}},
    },
    "required": ["title", "overview", "libraries", "primer", "steps", "build", "flow", "prerequisites", "learnFirst"],
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
The app also creates each step's file (empty) before that step starts: never ask the learner to create a file
("In calculator.py, type ...", never "Create calculator.py and type ...").
Order: step 1 is always typing code into a file (never a terminal step); a step that runs a program comes
AFTER the steps that write that program's code.
Also teach the ideas, in plain words for a complete beginner:
- overview (<= 60 words): what we're building and the plan, e.g. "We'll build a command-line notes app. First a
  list to hold notes, then functions to add and show them, then saving them to a file so they survive a restart."
- primer: 3-5 core concepts the steps rely on (e.g. "What a variable is", "Functions are reusable recipes",
  "Running a .py file"): title <= 6 words; body <= 40 words, no jargon; code: a tiny example (1-3 lines);
  diagramPrompt: one sentence describing a picture that would help, or "" if none would.
- per step: what (<= 12 words: the plan line for this step, e.g. "A list that holds your notes"),
  why (<= 25 words: what this part does in the app), concepts (numbers of the primer concepts it uses),
  estMinutes (whole minutes a beginner needs for the step, typing included; usually 2-8).
- build: summary (<= 20 words: what the learner will build, e.g. "A calculator that runs in your terminal"),
  outcome (<= 25 words: what the finished program does when you run it, e.g. "Type 8, / and 2 and it prints 4.0").
- flow: 3-6 boxes of a "how it works" diagram, left to right, following how the finished program works: label
  (<= 3 words), detail (a formula, a key call or <= 4 words, e.g. "float(input())" or "max(0, N·L)"), step (the
  number of the step that builds that box, or 0).
- prerequisites: 2-5 things the learner should already know before step 1, not what this lesson teaches: title
  (<= 4 words, e.g. "Python functions"), why (<= 12 words: where this lesson relies on it).
- learnFirst: 0-3 short mini-lessons for the prerequisites a beginner most likely lacks: title, minutes (2-10),
  kind (notebook, interactive, video or read), covers (the number of the prerequisite it teaches).
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
mkdir/cd/touch, no absolute paths). The code above is already in the files: never re-type or rename anything
that exists; to change existing code give only the new lines and anchor them to the existing line they go after
or inside; call only names that exist by now. A step either types code or runs a command, never both:
- code: the COMPLETE code to type in this step, every line, never "..." or placeholders (only the new lines,
  correct and runnable with the
  earlier steps' code), file: where it goes;
- targets: file + `match` = a short literal anchor already in the file or typed in this step (e.g.
  "function add(", "export default App") + caption, so the overlay can box exactly where to type;
- checks (at least one; graded from the learner's screen): screen_contains with app "Code" and a SHORT regex
  (< 60 chars, spacing-tolerant) for a distinctive fragment of this step's code; and, if the step runs
  something, a screen_contains with app "Terminal" on what it PRINTS (never the typed command);
  precision_checks: file_contains on the same fragment in `file`, command_exit_ok for a quick run;
{stack_guide}
- the step's file already exists (the app creates it, empty, before the step starts): captions and hints never
  ask the learner to create it ("In calculator.py, type ...", never "Create calculator.py and ...");
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
        log.info("claude research call: model=%s in=%s out=%s", mid, getattr(u, "input_tokens", "?"), getattr(u, "output_tokens", "?"))
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
        log.info("text lesson: cache hit %s", path.name)
        return fill_missing(g)  # a lesson cached by an older builder: complete labels, overview, what / why

    research_task = asyncio.ensure_future(_safe_research(goal))
    summary = info.summary_for_prompt().replace(str(info.root), "the lesson folder")

    def plan_ok(o: dict) -> str | None:
        n = len(o.get("steps") or [])
        return None if 3 <= n <= 8 else f"{n} steps"

    builder._emit("planning", "planning the lesson")
    plan = await claude._generate_json(SYSTEM, PLAN_PROMPT.format(goal=goal, workdir=summary), PLAN_SCHEMA,
                                       effort="medium", role="segment", check=plan_ok)
    primer = make_primer(plan.get("primer") or [])
    overview = _words(plan.get("overview") or "", 60)
    steps_plan = order_plan(plan["steps"])
    overview = overview or overview_fallback(plan.get("title") or goal, steps_plan)  # the drawer always has one
    build = make_build(plan.get("build") or {}, steps_plan)
    flow = make_flow(plan.get("flow") or [], plan["steps"], steps_plan)  # step numbers -> the reordered plan
    prereqs, learn_first = make_needs(plan.get("prerequisites") or [], plan.get("learnFirst") or [])
    outline = "; ".join(f"{i}. {s['title']}" for i, s in enumerate(steps_plan, 1))
    libs = {lb["name"]: lb.get("version", "") for lb in plan.get("libraries") or [] if lb.get("name")}
    done: list[dict] = []  # steps in order (a plan step may become two: code, then run)
    sources: list[dict] = []
    warnings: list[str] = []
    state: dict[str, str] = {}  # file -> its content after the steps so far

    def graph_now(complete: bool) -> dict:
        ordered = json.loads(json.dumps(done))
        first = {}  # plan step number -> the index of its first built step (a plan step may become code + run)
        for k, st in enumerate(ordered, 1):
            if m := re.match(r"s(\d+)", st["id"]):
                first.setdefault(int(m.group(1)), k)
            _renumber(st, k)
        b = dict(build)
        if complete and b and all(st.get("estMinutes") for st in ordered):
            b["estMinutes"] = sum(st["estMinutes"] for st in ordered)  # exactly the steps' estimates added up
        boxes = [dict({k: v for k, v in x.items() if k != "step"}, **({"stepIndex": first[x["step"]]} if x.get("step") in first else {}))
                 for x in flow]  # stepIndex = the built step's index (1-based, as StepSummary.index)
        needs = {"build": b, "flow": boxes, "prerequisites": prereqs, "learnFirst": learn_first}
        g = {"lesson": {"id": f"lesson-{key[5:13]}", "title": plan.get("title") or goal, "goal": goal, "workdir": workdir,
                        "libraries": libs, "mode": "lesson", "complete": complete, "builtBy": "claude", "primer": primer,
                        **({"overview": overview} if overview else {}), **{k: v for k, v in needs.items() if v}},
             "sources": [{"id": f"src{i}", "kind": "repo" if "github.com/" in s["url"] else "blog", "title": s["title"][:200], "url": s["url"]}
                         for i, s in enumerate(sources, 1)],
             "steps": ordered,
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

    async def step(i: int, notes: str) -> list[dict]:
        sp = steps_plan[i - 1]
        earlier = "\n\n".join(f"# {f}\n{c}" for f, c in state.items() if c.strip())
        prompt = STEP_PROMPT.format(goal=goal, lesson=plan.get("title", ""), outline=outline, index=i, title=sp["title"],
                                    instructions=sp["instructions"], file=sp.get("file") or "(terminal)", workdir=summary,
                                    earlier=earlier or "(none yet)",
                                    research=(f"Research notes (current docs):\n{notes}\n" if notes else ""),
                                    stack_guide=gemini.STACK_GUIDE)

        def ok(o: dict) -> str | None:
            if not ((o.get("code") or "").strip() or (o.get("run_command") or "").strip()):
                return "no code"
            if re.search(r"^\s*(\.\.\.|…)\s*$|#\s*\.\.\.|//\s*\.\.\.|\.\.\.\s*(rest|more|etc)", o.get("code") or "", re.M | re.I):
                return "code has a '...' placeholder instead of the complete code"
            if not o.get("checks"):
                return "no checks"
            if not any((t.get("match") or "").strip() for t in o.get("targets") or []):
                return "no target anchor"
            return None

        d = await claude._generate_json(SYSTEM, prompt, STEP_SCHEMA, effort="low", structured=False, role="detail", check=ok)
        problem = consistency_problem(d.get("file") or sp.get("file") or "", d.get("code") or "", d.get("run_command") or "", state)
        if problem:  # contradicts the file the earlier steps produced: Opus rewrites it, told exactly what's wrong
            log.info("step %d: %s; rewriting with %s", i, problem, claude.escalation_model())
            fix = (f"\n\nYour previous answer for this step was wrong: it {problem}. The file already contains the code "
                   "above. Never re-type something that exists: give only the NEW lines, and put the target anchor on the "
                   "existing line they go after (or inside). Only call names that exist by now.")
            try:
                d2 = await claude._generate_json(SYSTEM, prompt + fix, STEP_SCHEMA, effort="medium", structured=False,
                                                 role="escalate", escalate=False, check=ok)
                p2 = consistency_problem(d2.get("file") or sp.get("file") or "", d2.get("code") or "", d2.get("run_command") or "", state)
                d = d2
                if p2:
                    warnings.append(f"step {i}: still {p2}")
            except RuntimeError as e:
                warnings.append(f"step {i}: {problem} (rewrite failed: {str(e)[:80]})")
        st = _assemble_step(i, sp, d)
        st["expected_output"] = (d.get("expected_output") or "").strip()
        out = []
        parts = split_code_and_run(sanitize_step(st, workdir))
        for part in parts:
            part = explain_step(shape_step(use_python3(part)), sp, primer, len(parts))
            if not _is_run_step(part):
                f = part.get("file") or ""
                before = state.get(f, "")
                state[f] = (state.get(f, "").rstrip("\n") + "\n" + (part.get("code") or "")).lstrip("\n") if f else state.get(f, "")
                exact_anchor(part, state.get(f, ""), before)
            out.append(part)
        return out

    # 1. step 1 right away (no waiting for research)
    done.extend(await step(1, ""))
    log.info("text lesson: step 1 ready in %.1fs", time.time() - t0)
    builder._emit("first_steps", "1 step")
    await emit(False)

    # 2. research (bounded wait), then the rest one by one: each step is written against the file the
    #    earlier steps produced, so nothing is re-added, renamed or called before it exists
    try:
        res = await asyncio.wait_for(asyncio.shield(research_task), max(0.0, RESEARCH_WAIT_S - (time.time() - t0)))
    except (asyncio.TimeoutError, TimeoutError):
        res = {"notes": "", "sources": []}
        warnings.append("research took too long; later steps were written without it")
    sources.extend(res.get("sources") or [])
    for i in range(2, len(steps_plan) + 1):
        try:
            done.extend(await step(i, res.get("notes", "")))
        except RuntimeError as e:
            warnings.append(f"step {i} ({steps_plan[i - 1]['title']}) failed: {str(e)[:160]}")
            continue
        builder._emit("more_steps", f"step {i}/{len(steps_plan)}")
        await emit(False)

    g = graph_now(True)
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
    s = {"id": f"s{i}", "index": i, "title": _short_title(sp["title"], 6), "instructions": sp["instructions"].strip(),
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
    for st in g["steps"]:  # a run step always keeps a check on its terminal, even if the model's was too vague
        if _is_run_step(st) and not st.get("checks"):
            from .schema import stack_of, standard_error_pattern

            stack = stack_of(st) or stack_of({}, g["lesson"].get("libraries") or {}) or "python"
            st["checks"] = [{"id": f"{st['id']}c1", "type": "screen_absent", "label": "No errors in the terminal",
                             "app": "Terminal", "pattern": standard_error_pattern(stack)}]
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
        st["instructions"] = "In the terminal, run the command below."
        return st
    f = st.get("file") or ""
    code_lines = [ln for ln in (st.get("code") or "").splitlines() if ln.strip()]
    if code_lines and _RUN_TITLE.match(st.get("title") or ""):  # "Run the calculator" on a step that types code
        st["title"] = _code_title(st)
    if code_lines:  # exactly what to do: where to type, and that the snippet below is the whole thing
        what = "line" if len(code_lines) == 1 else "lines"
        text = f"In {f}, type the {what} below." if f else f"Type the {what} below."
    elif not text or len(text.split()) > MAX_WORDS:
        text = "Read this step, then continue."
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
        if (oc := run_output_check(st)) and not any(c.get("pattern") == oc["pattern"] for c in st.get("checks") or []):
            st.setdefault("checks", []).append(oc)
            for j, c in enumerate(st["checks"], 1):
                c["id"] = f"{st['id']}c{j}"
        pc.insert(0, {"id": "", "type": "file_contains", "label": builder.plain_label(f"code is in {f}", {"type": "file_contains", "file": f}), "file": f,
                      "pattern": builder.literal_pattern(frag[:60])})
        for j, c in enumerate(pc, 1):
            c["id"] = f"{st['id']}p{j}"


# --------------------------------------------------------------------------- #
# S11's rehearsal fixes: python3, one action per step, real run checks, exact anchors, no contradictions
# --------------------------------------------------------------------------- #
import builtins as _builtins  # noqa: E402
import keyword as _keyword  # noqa: E402
import shutil  # noqa: E402
import sys  # noqa: E402


def python_cmd() -> str:
    """'python3' on macOS / wherever plain `python` is missing (LESSON_PYTHON overrides)."""
    if os.environ.get("LESSON_PYTHON"):
        return os.environ["LESSON_PYTHON"]
    if shutil.which("python") is None and shutil.which("python3") is not None:
        return "python3"
    return "python3" if sys.platform == "darwin" else "python"


_PY = re.compile(r"(?<![\w./-])python(?![\w.])")


def use_python3(st: dict) -> dict:
    py = python_cmd()
    if py == "python":
        return st
    is_run = _is_run_step(st)  # decide before rewriting (the command and the snippet change together)
    for k in ("run_command", "instructions"):
        if st.get(k):
            st[k] = _PY.sub(py, st[k])
    if is_run and st.get("code"):
        st["code"] = _PY.sub(py, st["code"])
    for c in (st.get("checks") or []) + (st.get("precision_checks") or []):
        if c.get("command"):
            c["command"] = _PY.sub(py, c["command"])
    return st


def split_code_and_run(st: dict) -> list[dict]:
    """A step never carries both code to type and a command to run: split it into a code step, then a run step."""
    cmd, code, f = (st.get("run_command") or "").strip(), (st.get("code") or "").strip(), (st.get("file") or "").strip()
    if not (cmd and code and f and code != cmd):
        return [st]
    term = lambda c: c.get("app") in ("Terminal", "iTerm2")  # noqa: E731
    code_step = dict(st, checks=[c for c in st.get("checks") or [] if not term(c)],
                     precision_checks=[c for c in st.get("precision_checks") or [] if c.get("type") != "command_exit_ok"])
    code_step.pop("run_command", None)
    code_step.pop("expected_output", None)
    run_step = dict(st, id=f"{st['id']}r", title=builder._clip_words(f"Run {os.path.basename(f)}", 6), code=cmd,
                    checks=[c for c in st.get("checks") or [] if term(c)],
                    precision_checks=[c for c in st.get("precision_checks") or [] if c.get("type") == "command_exit_ok"],
                    targets=[], hints=list(st.get("hints") or [])[:1], common_mistakes=[])
    if not code_step["checks"]:
        code_step["checks"] = [{"id": "", "type": "screen_contains", "label": "", "app": "Code", "pattern": builder.literal_pattern(
            next((ln.strip() for ln in code.splitlines() if len(ln.strip()) >= 4), code)[:60])}]
        code_step["checks"][0]["label"] = builder.plain_label("", code_step["checks"][0])
    return [code_step, run_step]


def run_output_check(st: dict) -> dict | None:
    """An exact-line check on what the run prints (e.g. '5' for print(add(2, 3)))."""
    out = [ln.strip() for ln in (st.get("expected_output") or "").splitlines() if ln.strip()]
    if not out:
        return None
    line = out[-1][:80]
    c = {"id": "", "type": "screen_contains", "label": "", "app": "Terminal",
         "pattern": r"^\s*" + builder.literal_pattern(line) + r"\s*$"}
    c["label"] = builder.plain_label(f"Prints {line}", c)  # a whole phrase, never "Prints Result: the sum of"
    return c


def _skeleton(s: str) -> str:
    return re.sub(r"[\W_]+", "", (s or "").lower())


def _unique_line(match: str, text: str) -> bool:
    """Exactly one line of `text` holds `match` once OCR noise is ignored ("return a + b" vs "return a / b" read as
    "return a /b": both are "returnab", so the box could land on either)."""
    k = _skeleton(match)
    return bool(k) and sum(1 for ln in (text or "").splitlines() if k in _skeleton(ln)) == 1


def exact_anchor(st: dict, file_text: str, before: str | None = None) -> None:
    """Each code step's target is a literal line that exists in the file after this step (never line 1 by default),
    and is the only such line on screen when the step starts (`before`: the file before this step)."""
    f, code = st.get("file") or "", st.get("code") or ""
    lines = [ln.strip() for ln in code.splitlines() if ln.strip() and not ln.strip().startswith(("#", "//"))]
    if not f or not lines:
        return

    def unique(m: str) -> bool:
        return before is None or _unique_line(m, before if m in before else file_text)

    ok = [t for t in st.get("targets") or [] if (t.get("match") or "").strip() and t["match"].strip() in file_text
          and unique(t["match"].strip())]
    if ok:
        st["targets"] = [dict(t, file=f, app="Code") for t in ok]
        return
    first = lines[0]
    st["targets"] = [{"app": "Code", "file": f, "match": first, "caption": "type here"}]


_DEF = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)|^\s*(?:export\s+)?(?:function|const|let|var|class)\s+([A-Za-z_$][\w$]*)", re.M)
_CALL = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\s*\(")
_PY_KNOWN = set(dir(_builtins)) | set(_keyword.kwlist) | {"self", "cls", "super", "print", "input"}


def _defined(code: str) -> set[str]:
    return {a or b for a, b in _DEF.findall(code or "")}


def consistency_problem(file: str, code: str, run_command: str, state: dict[str, str]) -> str | None:
    """Does this step contradict the file the earlier steps produced? (re-defines a name already written, or,
    in Python, calls something that doesn't exist yet)."""
    if not file or not code.strip() or code.strip() == run_command.strip():
        return None
    before = state.get(file, "")
    again = sorted(_defined(code) & _defined(before))
    if again:
        return f"contradicts earlier steps: {', '.join(again)} already written in {file}"
    first = next((ln.strip() for ln in code.splitlines() if ln.strip() and not ln.strip().startswith(("#", "//"))), "")
    if len(first) >= 8 and any(ln.strip() == first for ln in before.splitlines()):  # the step reads as "type X" for an X
        return f"re-types `{first[:60]}`, which an earlier step already wrote in {file}"  # already there (or as a run step)
    if file.endswith(".py"):
        known = _defined(before) | _defined(code) | _PY_KNOWN
        imported = set(re.findall(r"^\s*(?:from\s+\S+\s+)?import\s+([\w, ]+)", before + "\n" + code, re.M))
        known |= {n.strip() for grp in imported for n in grp.split(",") if n.strip()}
        known |= set(re.findall(r"^\s*([A-Za-z_]\w*)\s*=", before + "\n" + code, re.M))
        bare = re.sub(r"(\"\"\"|\'\'\')[\s\S]*?\1|\"(?:\\.|[^\"\\])*\"|\'(?:\\.|[^\'\\])*\'", '""', code)  # not inside strings
        bare = re.sub(r"#.*", "", bare)
        missing = sorted({n for n in _CALL.findall(bare) if n not in known})
        if missing:
            return f"calls {', '.join(missing)}, not written yet in {file}"
    return None


# --------------------------------------------------------------------------- #
# Teaching the ideas: "Before you start" primer + per-step kind / what / why / concepts
# --------------------------------------------------------------------------- #

def _words(text: str, n: int) -> str:
    """At most n words, cut at a sentence or clause boundary (never mid-phrase)."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t.split()) <= n:
        return t
    for parts in (re.split(r"(?<=[.!?])\s+", t), re.split(r"(?<=[,;:])\s+|\s+[—-]\s+", t)):
        out = ""
        for p in parts:
            cand = (out + " " + p).strip() if out else p
            if len(cand.split()) > n:
                break
            out = cand
        if out:
            return out.rstrip(",;:—- ") + ("" if out.endswith((".", "!", "?")) else ".")
    return " ".join(t.split()[:n]).rstrip(",;:") + "."  # one long clause: last resort


def make_primer(items: list[dict]) -> list[dict]:
    out = []
    for k, it in enumerate(items[:5], 1):
        title = (it.get("title") or "").strip()
        body = (it.get("body") or "").strip()
        if not title or not body:
            continue
        p = {"id": f"p{k}", "title": _short_title(title, 6), "body": _words(body, 40)}
        code = (it.get("code") or "").strip()
        if code:
            p["code"] = "\n".join(code.splitlines()[:4])
        dp = (it.get("diagramPrompt") or "").strip()
        if dp:
            p["diagramPrompt"] = _words(dp, 30)
        out.append(p)
    return out


def step_kind(st: dict) -> str:
    if _is_run_step(st):
        return "run"
    return "code" if (st.get("code") or "").strip() else "read"


_RUN_CONCEPT = re.compile(r"\b(run|running|terminal|command|execute)", re.I)


def explain_step(st: dict, sp: dict, primer: list[dict], parts: int = 1) -> dict:
    """kind / what (<= 12 words) / why (<= 25 words) / concepts (primer ids) / estMinutes on every step."""
    st["kind"] = step_kind(st)
    if est := _minutes(sp.get("estMinutes")):  # the plan's estimate; split into code + run, the run part takes 1 min of it
        st["estMinutes"] = est if parts < 2 else 1 if st["kind"] == "run" else max(1, est - 1)
    ids = [p["id"] for p in primer]
    if st["kind"] == "run":  # a run step split off a code step: its own plain explanation
        prog = _noun(st.get("file") or "")
        st["what"] = _words(f"Run your {prog} and see what it prints", 12)
        st["why"] = _words(_WHY_RUN, 25)
        st["concepts"] = [p["id"] for p in primer if _RUN_CONCEPT.search(p["title"] + " " + p["body"])][:2]
        return st
    st["what"] = _words(sp.get("what") or st.get("title") or "", 12)
    st["why"] = _words(sp.get("why") or "", 25) or WHY_FALLBACK  # the drawer always explains the step
    nums = [n for n in sp.get("concepts") or [] if isinstance(n, int)]
    st["concepts"] = [ids[n - 1] for n in nums if 1 <= n <= len(ids)]
    return st


WHY_FALLBACK = "Each step adds one small piece you can check before moving on, so mistakes show up early."
_WHY_RUN = "Running the file makes the computer follow your code line by line, so you can check it works."
_RUN_TITLE = re.compile(r"^\s*(run|execute|launch|try|test)\b", re.I)
_DANGLING = re.compile(r"\s+(in|on|to|at|for|of|with|from|by|into|the|a|an|and|or|is|are|was|be|your|its|this|that)$", re.I)
_VERB_START = re.compile(r"^(build|create|make|write|code|program|set up)\b", re.I)


def _short_title(text: str, n: int = 6) -> str:
    """At most n words, never ending on a dangling word ("Add the add function to the" -> "Add the add function")."""
    words = " ".join((text or "").split()).split(" ")
    if len(words) <= n:
        return " ".join(words)
    t = " ".join(words[:n]).rstrip(",;:—- ")
    while _DANGLING.search(t):
        t = _DANGLING.sub("", t)
    return t


def _code_title(st: dict) -> str:
    """A title for a step that types code (the plan called it "Run …")."""
    names = [a or b for a, b in _DEF.findall(st.get("code") or "")]
    if names:
        return _short_title("Write " + " and ".join(f"{n}()" for n in names[:2]), 6)
    f = os.path.basename(st.get("file") or "")
    return f"Add the code to {f}" if f else "Add the code"


def overview_fallback(title: str, steps: list[dict]) -> str:
    """'What we're building' (<= 60 words) from the title and the step titles, when the plan gave none."""
    t = " ".join((title or "").split()).rstrip(".")
    intro = (f"You'll {t[0].lower()}{t[1:]}." if _VERB_START.match(t) else f"You'll build {t}.") if t else ""
    names = [" ".join((s.get("title") or "").split()).rstrip(".") for s in steps]
    names = [x[0].lower() + x[1:] for x in names if x]
    return _words(intro + (f" Step by step: {', then '.join(names)}." if names else ""), 60)


def fill_missing(g: dict) -> dict:
    """A lesson cached by an older builder: complete check labels (never cut, never the regex), an overview, and
    what / why on every step. Deterministic, no model call."""
    les = g.get("lesson") or {}
    steps = g.get("steps") or []
    if not (les.get("overview") or "").strip():
        les["overview"] = overview_fallback(les.get("title") or les.get("goal") or "", steps)
    for st in steps:
        for c in (st.get("checks") or []) + (st.get("precision_checks") or []):
            lbl = c.get("label") or ""
            if not 1 <= len(lbl.split()) <= 6 or builder.label_is_cut(lbl, c) or re.match(r"\s*(code|terminal|editor)\s*:", lbl, re.I):
                c["label"] = builder.plain_label(lbl, c)  # only broken ones: a good label is kept word for word
        if not (st.get("what") or "").strip():
            st["what"] = _words(st.get("title") or "", 12)
        if not (st.get("why") or "").strip():
            st["why"] = _WHY_RUN if _is_run_step(st) else WHY_FALLBACK
    return g


# --------------------------------------------------------------------------- #
# Learn-anything screens (mockups 01 drawer v2, 03 "Before you start"): build / flow / prerequisites / learnFirst /
# estMinutes, from the same plan call. Prerequisite status is "unknown" here; the orchestrator marks "passed" from
# the lessons finished on this Mac (server/sessions/store.prerequisite_status) when it sends lesson.ready.
# --------------------------------------------------------------------------- #
_FORMULA = re.compile(r"[=+*/()·²³^<>×÷−\[\]]")
LEARN_KINDS = ("notebook", "interactive", "video", "read")


def _minutes(v, hi: int = 30) -> int | None:
    try:
        m = int(round(float(v)))
    except (TypeError, ValueError, OverflowError):
        return None
    return min(hi, m) if m >= 1 else None


def make_build(raw: dict, steps_plan: list[dict]) -> dict:
    summary, outcome = _words(raw.get("summary") or "", 20), _words(raw.get("outcome") or "", 25)
    if not summary or not outcome:
        return {}
    est = [_minutes(sp.get("estMinutes")) for sp in steps_plan]
    return {"summary": summary, "outcome": outcome, **({"estMinutes": sum(est)} if est and all(est) else {})}


def make_flow(items: list[dict], plan_steps: list[dict], steps_plan: list[dict]) -> list[dict]:
    """3-6 boxes; `step` is renumbered from the model's plan to the reordered plan (order_plan), 0/absent = none."""
    out = []
    for it in items[:6]:
        label = _short_title(it.get("label") or "", 3)
        if not label:
            continue
        box = {"label": label}
        d = " ".join((it.get("detail") or "").split())
        if d:
            box["detail"] = d[:40] if _FORMULA.search(d) else _short_title(d, 4)
        n = it.get("step")
        if isinstance(n, int) and 1 <= n <= len(plan_steps):
            moved = next((k for k, sp in enumerate(steps_plan, 1) if sp is plan_steps[n - 1]), None)
            if moved:
                box["step"] = moved
        out.append(box)
    return out if len(out) >= 3 else []


def make_needs(raw_prereqs: list[dict], raw_learn: list[dict]) -> tuple[list[dict], list[dict]]:
    prereqs, ids = [], {}  # ids: the model's prerequisite number -> our id
    for n, it in enumerate(raw_prereqs[:5], 1):
        title, why = _short_title(it.get("title") or "", 4), _words(it.get("why") or "", 12)
        if not title or not why:
            continue
        pid = base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or f"need{n}"
        k = 2
        while pid in ids.values():
            pid, k = f"{base}-{k}", k + 1
        ids[n] = pid
        prereqs.append({"id": pid, "title": title, "why": why, "status": "unknown"})
    learn = []
    for it in raw_learn[:3]:
        title = _short_title(it.get("title") or "", 6)
        if title and it.get("covers") in ids:
            learn.append({"title": title, "minutes": _minutes(it.get("minutes"), 15) or 5,
                          "kind": it.get("kind") if it.get("kind") in LEARN_KINDS else "read", "covers": ids[it["covers"]]})
    return prereqs, learn
