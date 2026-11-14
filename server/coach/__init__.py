"""server/coach (E5): diagnosis cards, explanations, hint ladder, outdated-API fixes.

Orchestrator usage:
    from server import coach
    coach.set_lesson(step_graph)                       # once per lesson (prompt-cache prefix)
    coach.set_keys(config_keys)                      # optional: app-provided keys (BYOK)
    try:
        card = await coach.diagnose(step, failed, metrics, code, error_text=tail)
    except coach.CoachUnavailable as e:              # outside DEMO=1 there is no canned card
        ...  # show e.reason
    ws.send({"type": "offtrack", "payload": coach.public(card)})
"""

from .actions import do_it_for_me, inflight, locate
from .common import get_lesson, set_lesson, system_blocks
from .diagnose import diagnose, playbook_card, public
from .explain import explain
from .hints import apply_fix, hint
from .llm import CoachUnavailable, OutdatedFixUnavailable, set_keys
from .metrics import summarize as summarize_metrics
from .outdated import fix_outdated
from .playbook import match as match_playbook
from .screen import Box, ScreenContext
from .triage import triage


async def warm() -> dict:
    """Open the API connection and pre-warm the cached coach prefix for the current lesson."""
    from . import llm
    from .diagnose import COACH_SYSTEM, OFFTRACK_SCHEMA, screen_schema

    system = system_blocks(COACH_SYSTEM, get_lesson())
    return await llm.warm([
        {"system": system, "schema": OFFTRACK_SCHEMA},  # diagnose without a screen
        {"system": system, "schema": screen_schema(OFFTRACK_SCHEMA)},  # diagnose with a screen
    ])


def cancel(key: str | None = None) -> int:
    """Abort in-flight coach calls started via `inflight.start` (call on any real user action)."""
    return inflight.cancel(key)


__all__ = [
    "Box",
    "CoachUnavailable",
    "OutdatedFixUnavailable",
    "ScreenContext",
    "apply_fix",
    "cancel",
    "diagnose",
    "do_it_for_me",
    "explain",
    "fix_outdated",
    "hint",
    "inflight",
    "locate",
    "match_playbook",
    "playbook_card",
    "public",
    "set_keys",
    "set_lesson",
    "summarize_metrics",
    "triage",
    "warm",
]
