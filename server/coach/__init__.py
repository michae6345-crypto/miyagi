"""server/coach (E5): diagnosis cards, explanations, hint ladder, outdated-API fixes.

Orchestrator usage:
    from server import coach
    coach.set_lesson(step_graph)                       # once per lesson (prompt-cache prefix)
    card = await coach.diagnose(step, failed, metrics, code, error_text=tail)
    ws.send({"type": "offtrack", "payload": coach.public(card)})
"""

from .common import set_lesson
from .diagnose import diagnose, playbook_card, public
from .explain import explain
from .hints import apply_fix, hint
from .metrics import summarize as summarize_metrics
from .outdated import fix_outdated
from .playbook import match as match_playbook
from .triage import triage

__all__ = [
    "apply_fix",
    "diagnose",
    "explain",
    "fix_outdated",
    "hint",
    "match_playbook",
    "playbook_card",
    "public",
    "set_lesson",
    "summarize_metrics",
    "triage",
]
