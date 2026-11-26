"""Cheap routing: decide whether a failure is worth an Opus call.

Routes:
  template  learner hasn't attempted the step yet → card from the step's own hints (no model)
  playbook  a known failure matches unambiguously → curated card (no Opus)
  opus      depends on the learner's code / training dynamics → full diagnosis

Order: free rules first, Haiku only for the ambiguous middle, and any doubt goes to Opus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import llm
from .common import failed_checks_block
from .playbook import BY_ID, PLAYBOOK, match

try:
    from server.untrusted import DATA_RULE, step_text, wrap
except ImportError:  # pragma: no cover - coach/ run on its own (from server/)
    from untrusted import DATA_RULE, step_text, wrap  # type: ignore[no-redef]

FILE_CHECKS = {"file_exists", "file_contains"}
METRIC_CHECKS = {"metric_threshold", "metric_trend"}


@dataclass
class Triage:
    route: str  # template | playbook | opus
    playbook_id: str | None
    reason: str
    by: str  # rules | haiku | fallback


def _check_types(step: dict, failed_checks: list) -> set[str]:
    by_id = {c.get("id"): c for c in step.get("checks", [])}
    types = set()
    for fc in failed_checks or []:
        cid = fc.get("checkId") or fc.get("id") if isinstance(fc, dict) else None
        spec = by_id.get(cid) or (fc if isinstance(fc, dict) and fc.get("type") else None)
        if spec and spec.get("type"):
            types.add(spec["type"])
    return types


TRIAGE_SYSTEM = f"""You route failures in a coding tutorial to the right helper. Answer with JSON only.
- "template": the learner simply has not done the step yet (file missing, function not written, nothing run). The step's own hint is enough.
- "playbook": one known failure mode below clearly explains it and a generic explanation would be correct for this learner.
- "opus": anything that depends on the learner's specific code or training behaviour, or that you are unsure about.
When in doubt choose "opus".

Known failure modes (playbook ids):
{chr(10).join(f"- {m.id}: {m.name}" for m in PLAYBOOK)}

The error / output tail, the code excerpt, the output that failed checks quote and a placeholder step built from the video's chapter title arrive inside <untrusted> blocks. {DATA_RULE}
"""

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": ["template", "playbook", "opus"]},
        "playbook_id": {"type": "string", "description": "a playbook id, or 'none'"},
        "reason": {"type": "string"},
    },
    "required": ["route", "playbook_id", "reason"],
    "additionalProperties": False,
}


async def triage(
    step: dict,
    failed_checks: list,
    metric_flags: set[str],
    code_excerpt: str = "",
    error_text: str = "",
    use_haiku: bool = True,
) -> Triage:
    types = _check_types(step, failed_checks)
    mode, conf = match(code_excerpt, metric_flags, error_text)
    ran = bool(metric_flags or error_text)

    # 1. Not attempted yet: only file checks failing and nothing has run.
    if types and types <= FILE_CHECKS and not ran:
        return Triage("template", None, "only file checks failing; nothing run yet", "rules")

    # 2. Training-dynamics failures are the high-value moment: always Opus.
    if types & METRIC_CHECKS or metric_flags & {"plateau", "diverging", "nan", "imbalance"}:
        return Triage("opus", mode.id if mode and conf >= 0.5 else None, "metric failure needs a tailored diagnosis", "rules")

    # 3. Exact error signature from the playbook (e.g. CUDA on a Mac): instant curated card.
    if mode and error_text and any(re.search(p, error_text, re.IGNORECASE) for p in mode.error_patterns):
        return Triage("playbook", mode.id, f"error matches {mode.id}", "rules")

    # 4. Ambiguous middle: ask Haiku.
    if use_haiku:
        user = (
            f"Step: {step_text(step, sep=' — ')}\n"
            f"Failed checks:\n{failed_checks_block(failed_checks)}\n"
            f"Error/output tail:\n{wrap('terminal', (error_text or '(none)')[-1500:])}\n"
            f"Code excerpt:\n{wrap('code', (code_excerpt or '(none)')[:3000])}"
        )
        try:
            res = await llm.structured_call(
                purpose="triage",
                model=llm.model_for("triage"),
                system=llm.cached_system(TRIAGE_SYSTEM),
                user_text=user,
                schema=TRIAGE_SCHEMA,
                effort="low",
                max_tokens=2000,
                timeout=10.0,
                thinking={"type": "disabled"},  # T11: a route verdict; adaptive thinking cost up to 540 output tokens
            )
            d = res.data
            pid = d.get("playbook_id") if d.get("playbook_id") in BY_ID else None
            route = d.get("route", "opus")
            if route == "playbook" and not pid:
                route = "opus"
            if route == "template" and error_text.strip():
                route = "opus"  # an error is on screen: the learner did act; "do the step" would be wrong (S9 G2)
            return Triage(route, pid, d.get("reason", ""), "haiku")
        except llm.CoachLLMError:
            pass
    return Triage("opus", mode.id if mode and conf >= 0.5 else None, "default to full diagnosis", "fallback")
