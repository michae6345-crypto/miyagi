"""diagnose(): failed step → `offtrack` payload (shared/contracts/events.ts)."""

from __future__ import annotations

import logging
from typing import Any

from . import llm
from .common import (
    citation_menu,
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
    FailureMode,
    match,
    offending_line,
    playbook_text,
)
from .triage import triage

log = logging.getLogger("coach.diagnose")

# Stable across every call and lesson → first cache breakpoint.
COACH_SYSTEM = f"""You are the coach inside a tutorial overlay. A learner is following a video tutorial; the video is paused because their own code or training run failed this step's machine check. You write the small card they see next to their editor.

Voice: a calm, precise senior researcher sitting beside them. Name the actual cause, then the one change to make. No hype, no exclamation marks, no "Great question", no apologies, no hedging filler. Assume a skeptical expert may read the card: every claim must be correct and specific.

Hard limits:
- title: 3 to 7 words (hard maximum 8), plain statement of the cause (not a question, no trailing period).
- body: at most 30 words, at most 2 sentences. Sentence 1: why it fails. Sentence 2: what to do.
- Refer to their code by its real names (variables, functions) when helpful.
- diff_expected: the smallest replacement for the learner's offending line(s), at most 4 lines, in the learner's style and variable names; "" if no code change applies. If the fix adds training stages, keep the total training budget about the same (split the epochs across stages). diff_yours: the learner's current line(s) copied exactly from the numbered excerpt (without line numbers); "" if none. diff_line: the 1-based line number of diff_yours in the excerpt, 0 if none. diff_file: the file name if known, else "".
- citation_id: pick one id from the CITATIONS list only when the source directly supports the card; otherwise "none". Never invent a source.
- playbook_id: the matching playbook entry id, or "none" if no entry fits. Do not force a match: if the evidence does not fit an entry, diagnose from first principles.
- severity: "warn" when the code runs but the result is off (e.g. loss plateaus); "fail" when it crashes or produces nan/inf.
- actions: include "apply_fix" only when diff_expected is non-empty; include "show_me" when a specific line is implicated.

If the evidence is genuinely insufficient, say what to check next instead of guessing.

DOMAIN PLAYBOOK (known failure modes; use when the evidence fits):

{playbook_text()}
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
        "actions": {
            "type": "array",
            "items": {"type": "string", "enum": ["explain", "show_me", "apply_fix", "hint"]},
        },
    },
    "required": [
        "playbook_id", "severity", "title", "body", "citation_id",
        "diff_expected", "diff_yours", "diff_file", "diff_line", "actions",
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


def _shape(data: dict, step: dict, code_excerpt: str, lesson: dict | None) -> dict:
    expected = (data.get("diff_expected") or "").strip("\n")
    yours = (data.get("diff_yours") or "").strip()
    diff = None
    if expected:
        diff = {"expected": expected, "yours": yours}
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
    cit = resolve_citation(data.get("citation_id"), lesson)
    if cit is None and pid in BY_ID and data.get("citation_id") not in (None, "none"):
        cit = resolve_citation(BY_ID[pid].citation_id, lesson)  # model named a bad id for a known entry
    out = {
        "stepId": step.get("id", ""),
        "severity": data.get("severity") if data.get("severity") in ("warn", "fail") else "warn",
        "title": _title(data.get("title", ""), pid),
        "body": clamp_words(data.get("body", ""), 34),
        "actions": order_actions(data.get("actions") or [], has_diff=bool(diff)),
        "_meta": {"route": "opus", "playbook_id": pid if pid in BY_ID else None},
    }
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
) -> dict:
    """Return an `offtrack` payload for the failed step.

    Extra keys starting with `_` (e.g. `_meta`: route, model, latency, usage) are
    for logs; strip them before sending (see `public()`).
    """
    lesson = lesson if lesson is not None else get_lesson()
    metrics_text, flags = summarize(metrics_summary)
    if error_text:
        flags |= {"nan"} if "nan" in error_text.lower() else set()

    t = await triage(step, failed_checks, flags, code_excerpt, error_text, use_haiku=use_triage)
    if t.route == "template":
        card = template_card(step, failed_checks)
    elif t.route == "playbook" and t.playbook_id:
        card = playbook_card(step, BY_ID[t.playbook_id], code_excerpt, severity="fail" if error_text else "warn")
    else:
        card = await _opus(step, failed_checks, metrics_text, flags, code_excerpt, error_text, lesson, effort)
    card["_meta"]["triage"] = {"route": t.route, "by": t.by, "reason": t.reason}
    LAST[card["stepId"]] = card
    return card


async def _opus(step, failed_checks, metrics_text, flags, code_excerpt, error_text, lesson, effort) -> dict:
    file = _target_file(step)
    user = "\n\n".join(
        [
            f"CURRENT STEP:\n{step_brief(step)}",
            f"FAILED CHECKS:\n{failed_checks_text(failed_checks)}",
            f"METRICS (summary of the learner's latest run):\n{metrics_text}"
            + (f"\nauto-detected: {', '.join(sorted(flags))}" if flags else ""),
            f"ERROR / OUTPUT TAIL:\n{error_text[-2000:]}" if error_text else "ERROR / OUTPUT TAIL: (none)",
            f"LEARNER CODE ({file or 'excerpt'}), numbered:\n{number_lines(code_excerpt) or '(not available)'}",
            f"CITATIONS you may use (id: source):\n{citation_menu(lesson)}",
            "Write the card.",
        ]
    )
    try:
        res = await llm.structured_call(
            purpose="diagnose",
            model=llm.OPUS,
            system=system_blocks(COACH_SYSTEM, lesson),
            user_text=user,
            schema=OFFTRACK_SCHEMA,
            effort=effort,
            max_tokens=8000,
            timeout=40.0,
        )
    except llm.CoachLLMError as e:
        log.warning("opus diagnose failed (%s); using playbook fallback", e)
        mode, conf = match(code_excerpt, flags, error_text)
        if mode and conf >= 0.4:
            card = playbook_card(step, mode, code_excerpt, severity="fail" if error_text else "warn")
        else:
            card = template_card(step, failed_checks)
        card["_meta"]["fallback_reason"] = str(e)
        return card
    card = _shape(res.data, step, code_excerpt, lesson)
    card["_meta"].update(model=res.model, latency_s=round(res.latency_s, 2), usage=res.usage, source=res.source)
    return card


def public(payload: dict) -> dict:
    """Strip private `_` keys before sending over the WebSocket."""
    return {k: v for k, v in payload.items() if not k.startswith("_")}
