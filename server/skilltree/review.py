"""review.start {skillId: <catalog id>}: a quick review of a mastered catalog skill, with no build and no model call.

The steps behind the skill are replayed from the newest cached lesson in which the learner passed it (the lesson's own
folder, so the checks run on the learner's own code). Each replayed step carries skillIds [the skill], so its pass is
a review in ledger.record_pass (due: the next round; early: practice). lesson.review.key is "skilltree::<id>", which
sessions/review.py never schedules (its own Leitner boxes are for the older skill-map skills).
"""

from __future__ import annotations

import copy
from typing import Any, Callable

from . import catalog, ledger, tagging

KEY_PREFIX = "skilltree::"


def review_graph(skill_id: str, find_graph: Callable[[str], dict | None]) -> dict | None:
    """find_graph(lessonId) -> that lesson's cached graph or None. None: not a mastered catalog skill, or no cached
    lesson has a step behind it."""
    sk = catalog.skill(skill_id)
    row = ledger.load().get(skill_id) if sk else None
    if not sk or not row or not row.get("masteredAt"):
        return None
    lessons = list(dict.fromkeys(p["lessonId"] for p in reversed(row["passes"]) if p.get("lessonId")))
    for lid in lessons:
        src = find_graph(lid)
        if not isinstance(src, dict) or not src.get("steps"):
            continue
        tags = tagging.tag_graph(src)
        steps = [s for s in src["steps"] if isinstance(s, dict) and skill_id in tags.get(s.get("id"), [])]
        if not steps:
            continue
        g: dict[str, Any] = copy.deepcopy(src)
        les = g.setdefault("lesson", {})
        base, base_title = str(les.get("id") or lid), les.get("title")
        les["id"] = f"review-{skill_id.replace('.', '-')}-{base}"[:120]
        les["title"] = f"Review: {sk.label}"[:200]
        les["goal"] = f"A quick check on {sk.label}"
        les["mode"] = "lesson"
        # lessonId / lessonTitle: the source lesson, so a review pass is recorded under the step's own key (one
        # SkillInfo.steps entry per underlying step, skill_hooks.record) rather than a second "review-..." key
        les["review"] = {"key": KEY_PREFIX + skill_id, "label": sk.label, "skillId": skill_id, "lessonId": base,
                         **({"lessonTitle": str(base_title)[:200]} if base_title else {})}
        for k in ("nextTopics", "learnFirst", "prerequisites", "curated", "provisional", "complete", "grows"):
            les.pop(k, None)
        keep = {s["id"] for s in steps}
        g["steps"] = [{**copy.deepcopy(s), "skillIds": [skill_id]} for s in src["steps"] if isinstance(s, dict) and s.get("id") in keep]
        return g
    return None
