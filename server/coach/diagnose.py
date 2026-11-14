"""diagnose(): failed step → `offtrack` payload (shared/contracts/events.ts)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from typing import Any

from . import llm, web
from .common import (
    citation_menu,
    clamp_body,
    clamp_title,
    clamp_words,
    failed_checks_text,
    get_lesson,
    number_lines,
    order_actions,
    resolve_citation,
    step_brief,
    system_blocks,
)
from .metrics import summarize
from .playbook import (
    BY_ID,
    CITATIONS,
    GUIDING_QUESTIONS,
    FailureMode,
    match,
    offending_line,
    playbook_text,
)
from .screen import TARGETS_RULES, TARGETS_SCHEMA, ScreenContext, TargetStream
from .triage import triage

log = logging.getLogger("coach.diagnose")

# Stable across every call and lesson → first cache breakpoint.
COACH_SYSTEM = f"""You are the coach inside a tutorial overlay. A learner is following a tutorial on any topic (web development, React, data science, ML, a CLI tool, Blender...); the video is paused because their own code, terminal output or run failed this step's machine check. You write the small card they see next to their work.

Voice: a calm, precise senior engineer sitting beside them. Name the actual cause, then the one change to make. No hype, no exclamation marks, no "Great question", no apologies, no hedging filler. Assume a skeptical expert may read the card: every claim must be correct and specific.

Hard limits:
- title: 3 to 7 words (hard maximum 8), plain statement of the cause (not a question, no trailing period).
- body: at most 30 words, at most 2 sentences. Sentence 1: why it fails. Sentence 2: what to do, stated completely in words with the concrete value or name (e.g. "Set lr to 1e-3."), because the diff is often hidden at first.
- Refer to their code by its real names (variables, functions) when helpful.
- diff_expected: the smallest replacement for the learner's offending line(s): one contiguous block of at most 8 lines that makes EVERY edit your body's action sentence asks for (if the fix touches two nearby lines, the block covers both), in the learner's style and variable names; "" if no code change applies. If the fix adds training stages, keep the total training budget about the same (split the epochs across stages). diff_yours: the learner's current line(s) copied exactly from the numbered excerpt (without line numbers); "" if none. diff_line: the 1-based line number of diff_yours in the excerpt, 0 if none. diff_file: the file name if known, else "".
- Ground the card in evidence: WEB SOURCES (official docs, changelogs, Stack Overflow / GitHub issues fetched live for this failure) take precedence over memory for API names, versions and deprecations. If a web source contradicts your memory, trust the source. Prefer official docs over community posts.
- diff_command: when the fix is a terminal action (install or upgrade a package, add a CLI flag, re-run with an option), that single shell command; else "". It can go with or without a code diff.
- citation_id: pick one id from the CITATIONS list (web:N, source:..., or a playbook id) only when that source directly supports the card; otherwise "none". Never invent a source.
- playbook_id: the matching playbook entry id, or "none" if no entry fits. Do not force a match: if the evidence does not fit an entry, diagnose from first principles.
- severity: "warn" when it runs but the result is off (a metric plateaus, a test count is short, output differs); "fail" when it crashes, errors, or produces nan/inf.
- actions: include "apply_fix" only when diff_expected is non-empty; include "show_me" when a specific line is implicated.
- guiding_question: one Socratic question (at most 20 words) about THIS cause that leads the learner to the fix without stating it, e.g. "What happens to Adam's steps when the learning rate is large?". It is the first rung of the hint ladder.

- Trust what is on screen (error text, versions in tracebacks) over the lesson's library versions: the learner may have a newer release than the tutorial.
- Never put `git add` or `git rebase/merge/cherry-pick --continue` in diff_command while the file still has conflict markers (<<<<<<< ======= >>>>>>>) that your diff does not remove: that would commit the markers. Say to resolve the markers first.

If the evidence is genuinely insufficient, say what to check next instead of guessing.

DOMAIN PLAYBOOK (curated ML failure modes; only one source of knowledge among many, use an entry only when the evidence fits):

{playbook_text()}
{TARGETS_RULES}
"""

OFFTRACK_SCHEMA = {
    "type": "object",
    "properties": {
        "playbook_id": {"type": "string"},
        "severity": {"type": "string", "enum": ["warn", "fail"]},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "citation_id": {"type": "string"},
        "diff_expected": {"type": "string"},
        "diff_yours": {"type": "string"},
        "diff_file": {"type": "string"},
        "diff_line": {"type": "integer"},
        "diff_command": {"type": "string"},
        "guiding_question": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {"type": "string", "enum": ["explain", "show_me", "apply_fix", "hint"]},
        },
    },
    "required": [
        "playbook_id", "severity", "title", "body", "citation_id",
        "diff_expected", "diff_yours", "diff_file", "diff_line", "diff_command", "actions", "guiding_question",
    ],
    "additionalProperties": False,
}

# last diagnosis per step: hint() and apply_fix() reuse its diff/citation
LAST: dict[str, dict] = {}


def _target_file(step: dict) -> str:
    for t in step.get("targets", []) or []:
        if t.get("file"):
            return t["file"]
    for c in step.get("checks", []) or []:
        if c.get("file"):
            return c["file"]
    return ""


def playbook_card(step: dict, mode: FailureMode, code_excerpt: str = "", severity: str = "warn") -> dict:
    """Curated, offline card for a known failure mode (also the fallback when the API fails)."""
    yours, line = offending_line(mode, code_excerpt)
    diff = None
    if mode.diff_expected:
        diff = {"expected": mode.diff_expected, "yours": yours}
        if f := _target_file(step):
            diff["file"] = f
        if line:
            diff["line"] = line
    c = CITATIONS[mode.citation_id]
    return {
        "stepId": step.get("id", ""),
        "severity": severity,
        "title": mode.card_title,
        "body": mode.card_body,
        **({"diff": diff} if diff else {}),
        "citation": {"label": c["label"], "url": c["url"]},
        **({"guidingQuestion": GUIDING_QUESTIONS[mode.id]} if mode.id in GUIDING_QUESTIONS else {}),
        "actions": order_actions(["show_me"] if line else [], has_diff=bool(diff)),
        "_meta": {"route": "playbook", "playbook_id": mode.id},
    }


def template_card(step: dict, failed_checks: list) -> dict:
    """Learner hasn't done the step yet: restate it with the gentlest hint. No model call."""
    hints = step.get("hints") or []
    first = failed_checks[0] if failed_checks else {}
    label = first.get("label") if isinstance(first, dict) else str(first)
    body = hints[0] if hints else step.get("instructions", "")
    return {
        "stepId": step.get("id", ""),
        "severity": "warn",
        "title": clamp_title(f"Not yet: {label}" if label else step.get("title", "Step not done yet")),
        "body": clamp_words(body, 30),
        "actions": order_actions(["show_me"] if step.get("targets") else [], has_diff=False),
        "_meta": {"route": "template"},
    }


SELF_EXPLAINING = re.compile(
    r"NameError|ReferenceError|is not defined|no-undef|SyntaxError|IndentationError|Unexpected token"
    r"|unexpected indent|unterminated|missing \)|Unexpected end of input",
    re.IGNORECASE,
)
ERROR_LINE = re.compile(
    r"Traceback|\b\w*Error\b|\berror:|\bfatal:|Failed to compile|needs merge|\bCONFLICT\b|You must|is not defined"
    r"|cannot find module|command not found|No such file|Permission denied|\bERR!",
    re.IGNORECASE,
)
CONFLICT_MARKERS = re.compile(r"^(<{7}|={7}|>{7})", re.MULTILINE)


def screen_errors(screen: ScreenContext, max_lines: int = 12) -> str:
    """Error / refusal lines visible on screen (terminal, editor problems panel, browser overlay)."""
    lines = [b.text for b in sorted(screen.boxes, key=lambda b: (b.y, b.x)) if ERROR_LINE.search(b.text)]
    return "\n".join(lines[-max_lines:])


def _unsafe_git_continue(command: str, code: str, yours: str, expected: str) -> bool:
    if not re.search(r"\bgit\s+add\b|--continue\b", command):
        return False
    markers_now = bool(CONFLICT_MARKERS.search(code or ""))
    resolved_by_diff = bool(CONFLICT_MARKERS.search(yours or "")) and not CONFLICT_MARKERS.search(expected or "")
    return markers_now and not resolved_by_diff


_SOURCE = re.compile(r'"source"\s*:\s*\[')
_CELL_TYPE = re.compile(r'"cell_type"\s*:\s*"(\w+)"')
_JSON_STR = re.compile(r'"(?:[^"\\]|\\.)*"')


def _cell_sources_tolerant(t: str) -> list[tuple[int, str]]:
    """Code-cell sources from notebook JSON that may be cut off mid-way (the orchestrator sends
    the first 6000 chars): scan each `"source": [...]` array string by string, stop at the cut."""
    out: list[tuple[int, str]] = []
    marks = [m.end() for m in _SOURCE.finditer(t)]
    types = [(m.start(), m.group(1)) for m in _CELL_TYPE.finditer(t)]
    prev_end = 0
    for n, pos in enumerate(marks):
        # nbformat writes keys sorted, so a cell's "cell_type" precedes its "source": take the last
        # one after the previous source array (else the first one after this array)
        before = [ty for p, ty in types if prev_end <= p < pos]
        after = [ty for p, ty in types if p > pos and (n + 1 >= len(marks) or p < marks[n + 1])]
        ctype = before[-1] if before else (after[0] if after else "code")
        parts, i = [], pos
        while True:
            m = re.compile(r"\s*(,)?\s*").match(t, i)
            i = m.end()
            if i >= len(t) or t[i] == "]":
                break
            sm = _JSON_STR.match(t, i)
            if not sm:  # the cut fell inside this string: keep what we have of it
                tail = t[i + 1:] if t[i] == '"' else ""
                parts.append(tail.encode().decode("unicode_escape", errors="ignore") if "\\" in tail else tail)
                i = len(t)
                break
            try:
                parts.append(json.loads(sm.group(0)))
            except json.JSONDecodeError:
                break
            i = sm.end()
        prev_end = i
        if ctype == "code" and parts:
            out.append((n, "".join(parts)))
    return out


def notebook_code(text: str) -> str:
    """A Jupyter notebook's JSON → its code cells' source, separated by `# %% [cell N]` markers.
    Works on truncated JSON too. Anything that isn't a notebook is returned unchanged."""
    t = (text or "").lstrip()
    if not (t.startswith("{") and ('"cells"' in t[:20000] or '"cell_type"' in t[:20000])):
        return text
    try:
        nb = json.loads(t)
        cells = [(i, "".join(c.get("source") or []) if isinstance(c.get("source"), list) else (c.get("source") or ""))
                 for i, c in enumerate(nb.get("cells") or []) if c.get("cell_type") == "code"]
    except json.JSONDecodeError:
        cells = _cell_sources_tolerant(t)
    out = [f"# %% [cell {i}]\n" + src.rstrip("\n") for i, src in cells]
    return "\n".join(out) if out else "# (notebook: no code cell source within the excerpt)"


def _title(title: str, pid: str | None) -> str:
    """Over-long titles are not chopped mid-phrase: use the curated title, else trim."""
    title = (title or "").strip().rstrip(".")
    if len(title.split()) <= 8:
        return title
    if pid in BY_ID:
        return BY_ID[pid].card_title
    return clamp_title(title)


def _shape(data: dict, step: dict, code_excerpt: str, lesson: dict | None, sources: list[dict] | None = None) -> dict:
    expected = (data.get("diff_expected") or "").strip("\n")
    yours = (data.get("diff_yours") or "").strip()
    command = (data.get("diff_command") or "").strip()
    if command and _unsafe_git_continue(command, code_excerpt, yours, expected):
        command = ""  # would commit unresolved conflict markers (S9 QA, verified)
    diff = None
    if command and not expected:  # terminal-only fix: the app copies it to the clipboard
        diff = {"expected": "", "yours": "", "command": command}
    if expected:
        diff = {"expected": expected, "yours": yours, **({"command": command} if command else {})}
        f = data.get("diff_file") or _target_file(step)
        if f:
            diff["file"] = f
        line = int(data.get("diff_line") or 0)
        if not line and yours:
            for i, l in enumerate((code_excerpt or "").splitlines(), start=1):
                if l.strip() == yours.splitlines()[0].strip():
                    line = i
                    break
        if line:
            diff["line"] = line
    pid = data.get("playbook_id")
    cit = resolve_citation(data.get("citation_id"), lesson, sources)
    if cit is None and pid in BY_ID and data.get("citation_id") not in (None, "none"):
        cit = resolve_citation(BY_ID[pid].citation_id, lesson)  # model named a bad id for a known entry
    out = {
        "stepId": step.get("id", ""),
        "severity": data.get("severity") if data.get("severity") in ("warn", "fail") else "warn",
        "title": _title(data.get("title", ""), pid),
        "body": clamp_body(data.get("body", "")),
        "actions": order_actions(data.get("actions") or [], has_diff=bool(diff)),
        "_meta": {"route": "opus", "playbook_id": pid if pid in BY_ID else None},
    }
    if q := (data.get("guiding_question") or "").strip():
        out["guidingQuestion"] = clamp_words(q, 24)
    if diff:
        out["diff"] = diff
    if cit:
        out["citation"] = cit
    return out


async def diagnose(
    step: dict,
    failed_checks: list,
    metrics_summary: Any = None,
    code_excerpt: str = "",
    *,
    error_text: str = "",
    lesson: dict | None = None,
    use_triage: bool = True,
    effort: str = "low",
    screen: ScreenContext | None = None,
    on_targets: Callable[[list[dict]], Any] | None = None,
    cursor: dict | None = None,
) -> dict:
    """Return an `offtrack` payload for the failed step.

    With `screen` (a set-of-mark ScreenContext) Opus also sees the screen and returns
    `targets` first: [{boxId, label, text, rect}] in screen points. The reply is streamed and
    `on_targets(targets)` fires the moment that array is complete, before the rest of the card,
    so the spotlight can move early. Cancel the awaiting task to abort (stream is closed).
    `cursor` ({"x", "y", "under": {"text", "app", "rect"}}, screen points) tells the coach what
    the learner is pointing at when no full `screen` is attached.

    Extra keys starting with `_` (e.g. `_meta`: route, model, latency, usage) are
    for logs; strip them before sending (see `public()`).
    """
    lesson = lesson if lesson is not None else get_lesson()
    if not error_text.strip() and screen is not None:
        # screen-first lessons have no captured stderr: an error/refusal visible on screen is the
        # error text (S9 QA: without it, triage sent git/React failures to the "not done yet" card)
        error_text = screen_errors(screen)
    code_excerpt = notebook_code(code_excerpt)  # .ipynb JSON → cell sources (S9 QA)
    metrics_text, flags = summarize(metrics_summary, goals=metric_goals(step))
    if error_text:
        flags |= {"nan"} if "nan" in error_text.lower() else set()

    # live-web grounding runs while triage decides; only Opus uses it. It is worth waiting for only
    # when there is an error message to look up (docs/changelogs); for metric-only failures the
    # search came back unused and cost 2-4 s before Opus could start (rehearsal, s8 lr=0.3).
    lib, sym, query, err = grounding_query(step, failed_checks, error_text, code_excerpt, lesson)
    # S9 re-run: 6/8 cards waited the full cap for generic hits; self-explaining errors skip it
    wants_web = error_text.strip() and not SELF_EXPLAINING.search(error_text)
    web_task = asyncio.create_task(web.gather(lib, sym, query, error=err, timeout=1.5)) if wants_web else None
    try:
        t = await triage(step, failed_checks, flags, code_excerpt, error_text, use_haiku=use_triage)
        if t.route == "template":
            card = template_card(step, failed_checks)
        elif t.route == "playbook" and t.playbook_id:
            card = playbook_card(step, BY_ID[t.playbook_id], code_excerpt, severity="fail" if error_text else "warn")
        else:
            sources = await web_task if web_task is not None else []
            card = await _opus(step, failed_checks, metrics_text, flags, code_excerpt, error_text, lesson, effort, sources, screen, on_targets, cursor)
    finally:
        if web_task is not None and not web_task.done():
            web_task.cancel()
    card["_meta"]["triage"] = {"route": t.route, "by": t.by, "reason": t.reason}
    LAST[card["stepId"]] = card
    return card


def metric_goals(step: dict) -> dict[str, str]:
    """metric name -> "down" | "up" from the step's own checks (op < means lower is better)."""
    goals = {}
    for c in step.get("checks", []) or []:
        if c.get("metric"):
            goals[c["metric"]] = "up" if c.get("op") in (">", ">=") else "down"
    return goals


def grounding_query(step: dict, failed_checks: list, error_text: str, code: str, lesson: dict | None) -> tuple[str, str, str, str]:
    """(library, symbol, community query, error line) for the web layer. Generic: no domain hardcoding."""
    libs = ((lesson or {}).get("lesson") or {}).get("libraries") or {}
    command = next((c.get("command", "") for c in step.get("checks", []) or [] if c.get("command")), "")
    if error_text:
        lib, sym = web.detect(error_text, code, libs, command)
        line = web.error_line(error_text)
        return lib, sym, line, line
    title = ((lesson or {}).get("lesson") or {}).get("title", "")
    labels = ", ".join(str(c.get("label", "")) for c in failed_checks or [] if isinstance(c, dict))
    return "", "", f"{title} {step.get('title', '')} {labels}".strip(), ""


async def _opus(step, failed_checks, metrics_text, flags, code_excerpt, error_text, lesson, effort, sources=None, screen=None, on_targets=None, cursor=None) -> dict:
    sources = sources or []
    file = _target_file(step)
    key_error = web.error_line(error_text) if error_text else ""
    user = "\n\n".join(
        x for x in [
            f"CURRENT STEP:\n{step_brief(step)}",
            f"FAILED CHECKS:\n{failed_checks_text(failed_checks)}",
            f"METRICS (summary of the learner's latest run):\n{metrics_text}"
            + (f"\nauto-detected: {', '.join(sorted(flags))}" if flags else ""),
            f"ERROR / OUTPUT TAIL:\n{error_text[-2000:]}" if error_text else "ERROR / OUTPUT TAIL: (none)",
            f"THE ERROR MESSAGE (your cause must agree with exactly what it says, for the version that printed it):\n{key_error}"
            if key_error else "",
            f"LEARNER CODE ({file or 'excerpt'}), numbered:\n{number_lines(code_excerpt) or '(not available)'}",
            f"WEB SOURCES (fetched live for this failure):\n{web.sources_text(sources)}" if sources else "WEB SOURCES: (none available)",
            f"CITATIONS you may use (id: source):\n{citation_menu(lesson, sources)}",
            cursor_text(cursor) if cursor and screen is None else "",
            "Write the card.",
        ] if x
    )
    schema, content, stream = OFFTRACK_SCHEMA, None, None
    if screen is not None:
        schema = screen_schema(OFFTRACK_SCHEMA)
        content = [{"type": "text", "text": user}, *screen.claude_content()]
        user = user + "\n\n" + screen.text()  # fixture key covers the screen text, not the pixels
        stream = TargetStream(screen, on_targets)
    try:
        res = await llm.structured_call(
            purpose="diagnose",
            model=llm.model_for("diagnose"),
            system=system_blocks(COACH_SYSTEM, lesson),
            user_text=user,
            schema=schema,
            effort=effort,
            max_tokens=8000,
            timeout=40.0,
            user_content=content,
            on_text=stream,
        )
    except llm.CoachLLMError as e:
        mode, conf = match(code_excerpt, flags, error_text)
        if not llm.demo_mode():
            # live: only a network outage, only when opted in, only a confident match on their code
            if e.kind == "connection" and llm.offline_fallback() and mode and conf >= 0.6:
                log.warning("opus unreachable (%s); offline playbook card %s (conf %.1f)", e, mode.id, conf)
                card = playbook_card(step, mode, code_excerpt, severity="fail" if error_text else "warn")
                card["offline"] = True  # additive public field: the app may badge it "offline"
                card["_meta"].update(fallback_reason=str(e), confidence=round(conf, 2))
                return card
            raise llm.CoachUnavailable(f"diagnosis unavailable: {e}") from e
        log.warning("opus diagnose failed (%s); DEMO=1 so using the offline playbook card", e)
        if mode and conf >= 0.4:
            card = playbook_card(step, mode, code_excerpt, severity="fail" if error_text else "warn")
        else:
            card = template_card(step, failed_checks)
        card["_meta"]["fallback_reason"] = str(e)
        return card
    card = _shape(res.data, step, code_excerpt, lesson, sources)
    if screen is not None:
        card["targets"] = stream.fired if stream.fired is not None else screen.resolve_targets(res.data.get("targets"))
        if stream.fired is None and on_targets is not None and card["targets"]:
            await llm._maybe_await(on_targets(card["targets"]))
        card["_meta"]["screen"] = {"boxes": len(screen.boxes), "cursor": list(screen.cursor)}
    card["_meta"]["web_sources"] = sources  # full dicts; explain() reuses them
    card["_meta"].update(model=res.model, latency_s=round(res.latency_s, 2), usage=res.usage, source=res.source)
    return card


def cursor_text(cursor: dict) -> str:
    """'LEARNER CURSOR: at (x, y) over "text" (app)' from the orchestrator's cursor dict."""
    under = cursor.get("under") or {}
    s = f"LEARNER CURSOR: at ({float(cursor.get('x', 0)):.0f}, {float(cursor.get('y', 0)):.0f})"
    if under.get("text"):
        s += f' over "{str(under["text"])[:120]}"' + (f" ({under['app']})" if under.get("app") else "")
    return s + " (what they are looking at or pointing to; mention it only if relevant)"


def screen_schema(base: dict) -> dict:
    """Same schema with `targets` as the FIRST property, so it streams before the prose."""
    return {
        **base,
        "properties": {"targets": TARGETS_SCHEMA, **base["properties"]},
        "required": ["targets", *base["required"]],
    }


def public(payload: dict) -> dict:
    """Strip private `_` keys before sending over the WebSocket."""
    return {k: v for k, v in payload.items() if not k.startswith("_")}
