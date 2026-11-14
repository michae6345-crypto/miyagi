"""diagnose(): failed step → `offtrack` payload (shared/contracts/events.ts)."""

from __future__ import annotations

import asyncio
import logging
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
- diff_expected: the smallest replacement for the learner's offending line(s), at most 4 lines, in the learner's style and variable names; "" if no code change applies. If the fix adds training stages, keep the total training budget about the same (split the epochs across stages). diff_yours: the learner's current line(s) copied exactly from the numbered excerpt (without line numbers); "" if none. diff_line: the 1-based line number of diff_yours in the excerpt, 0 if none. diff_file: the file name if known, else "".
- Ground the card in evidence: WEB SOURCES (official docs, changelogs, Stack Overflow / GitHub issues fetched live for this failure) take precedence over memory for API names, versions and deprecations. If a web source contradicts your memory, trust the source. Prefer official docs over community posts.
- diff_command: when the fix is a terminal action (install or upgrade a package, add a CLI flag, re-run with an option), that single shell command; else "". It can go with or without a code diff.
- citation_id: pick one id from the CITATIONS list (web:N, source:..., or a playbook id) only when that source directly supports the card; otherwise "none". Never invent a source.
- playbook_id: the matching playbook entry id, or "none" if no entry fits. Do not force a match: if the evidence does not fit an entry, diagnose from first principles.
- severity: "warn" when it runs but the result is off (a metric plateaus, a test count is short, output differs); "fail" when it crashes, errors, or produces nan/inf.
- actions: include "apply_fix" only when diff_expected is non-empty; include "show_me" when a specific line is implicated.
- guiding_question: one Socratic question (at most 20 words) about THIS cause that leads the learner to the fix without stating it, e.g. "What happens to Adam's steps when the learning rate is large?". It is the first rung of the hint ladder.

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
    metrics_text, flags = summarize(metrics_summary, goals=metric_goals(step))
    if error_text:
        flags |= {"nan"} if "nan" in error_text.lower() else set()

    # live-web grounding runs while triage decides; only Opus uses it
    lib, sym, query, err = grounding_query(step, failed_checks, error_text, code_excerpt, lesson)
    web_task = asyncio.create_task(web.gather(lib, sym, query, error=err, timeout=6.0))
    try:
        t = await triage(step, failed_checks, flags, code_excerpt, error_text, use_haiku=use_triage)
        if t.route == "template":
            card = template_card(step, failed_checks)
        elif t.route == "playbook" and t.playbook_id:
            card = playbook_card(step, BY_ID[t.playbook_id], code_excerpt, severity="fail" if error_text else "warn")
        else:
            sources = await web_task
            card = await _opus(step, failed_checks, metrics_text, flags, code_excerpt, error_text, lesson, effort, sources, screen, on_targets, cursor)
    finally:
        if not web_task.done():
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
    user = "\n\n".join(
        x for x in [
            f"CURRENT STEP:\n{step_brief(step)}",
            f"FAILED CHECKS:\n{failed_checks_text(failed_checks)}",
            f"METRICS (summary of the learner's latest run):\n{metrics_text}"
            + (f"\nauto-detected: {', '.join(sorted(flags))}" if flags else ""),
            f"ERROR / OUTPUT TAIL:\n{error_text[-2000:]}" if error_text else "ERROR / OUTPUT TAIL: (none)",
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
            model=llm.OPUS,
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
        if not llm.demo_mode():
            raise llm.CoachUnavailable(f"diagnosis unavailable: {e}") from e
        log.warning("opus diagnose failed (%s); DEMO=1 so using the offline playbook card", e)
        mode, conf = match(code_excerpt, flags, error_text)
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
