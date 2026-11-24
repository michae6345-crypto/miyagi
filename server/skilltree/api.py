"""The skill tree's wire payloads (pure reads of the catalog + this Mac's ledger and proofs).

    tracks(now=, tz=, track=None) -> {"tracks": [Track], "due": n}
    skill(skill_id, now=, tz=)    -> {"skill": SkillRow + lessons + steps + proofs} | None
    mastery(now=, tz=)            -> {"mastered": [SkillRow], "practicing": [SkillRow], "counts": {...}}
    reviews(now=, tz=, days=7)    -> {"due": n, "items": [ReviewRow]}   (due now first, then the next `days` days)
    update(events, now=, tz=)     -> {"events": [...], "skills": [SkillRow], "due": n}   (after a pass)

SkillRow = ledger.row_view: {id, label, track, planId, needs, state, passes, unassistedDays, daysNeeded,
lastPassAt?, masteredAt?, review? {dueAt, due, interval, stage, reps, lastResult?, lastAt?}, proofIds?}.
Times are epoch seconds. The exact field names follow the ui-v4 contract once it lands (shared/contracts).
"""

from __future__ import annotations

import time
from datetime import tzinfo
from typing import Any

from . import catalog, ledger, proofs

UPCOMING_DAYS = 7


def _now(now: float | None) -> float:
    return time.time() if now is None else float(now)


def _track(t: catalog.Track, rows: dict[str, dict], now: float, tz: tzinfo | None) -> dict:
    skills = [ledger.row_view(s.id, rows, now, tz) for s in t.skills]
    counts = {st: sum(1 for s in skills if s["state"] == st)
              for st in (ledger.MASTERED, ledger.PRACTICING, ledger.READY, ledger.LOCKED)}
    return {"id": t.id, "label": t.label, "topic": t.topic,
            "plans": [{"id": p.id, "title": p.title, "tool": p.tool, "level": p.level, "needs": p.needs,
                       "project": p.project, "skillIds": [s.id for s in p.skills]} for p in t.plans],
            "skills": skills, "counts": {**counts, "total": len(skills)},
            "due": sum(1 for s in skills if (s.get("review") or {}).get("due"))}


def tracks(*, now: float | None = None, tz: tzinfo | None = None, track: str | None = None) -> dict:
    now, rows = _now(now), ledger.load()
    out = [_track(t, rows, now, tz) for t in catalog.tracks() if track is None or t.id == track]
    return {"tracks": out, "due": sum(t["due"] for t in out)}


def skill(skill_id: str, *, now: float | None = None, tz: tzinfo | None = None) -> dict | None:
    sk = catalog.skill(skill_id)
    if sk is None:
        return None
    now, rows = _now(now), ledger.load()
    row = ledger.row_view(skill_id, rows, now, tz)
    plan = catalog.get().plan(sk.plan_id)
    row["lessons"] = [{"title": les.get("title"), "goal": les.get("goal"), "check": les.get("check")}
                      for les in (plan.lessons if plan else []) if skill_id in (les.get("grows") or [])]
    row["steps"] = [{k: p[k] for k in ("lessonId", "stepId", "at", "assisted") if k in p}
                    for p in reversed((rows.get(skill_id) or {}).get("passes") or [])][:10]
    row["proofs"] = proofs.for_skill(skill_id)
    row["proofIds"] = [p["id"] for p in row["proofs"]]
    if not row["proofIds"]:
        row.pop("proofIds")
    return {"skill": row}


def mastery(*, now: float | None = None, tz: tzinfo | None = None) -> dict:
    now, rows = _now(now), ledger.load()
    seen = [ledger.row_view(sid, rows, now, tz) for sid in rows if catalog.skill(sid)]
    mastered = sorted((r for r in seen if r["state"] == ledger.MASTERED), key=lambda r: -r["masteredAt"])
    practicing = sorted((r for r in seen if r["state"] == ledger.PRACTICING), key=lambda r: -(r.get("lastPassAt") or 0))
    return {"mastered": mastered, "practicing": practicing,
            "counts": {"mastered": len(mastered), "practicing": len(practicing),
                       "tracks": len({r["track"] for r in mastered + practicing})}}


def reviews(*, now: float | None = None, tz: tzinfo | None = None, days: int = UPCOMING_DAYS) -> dict:
    now = _now(now)
    items = ledger.due(now=now, tz=tz, within_s=days * 86_400)
    return {"due": sum(1 for i in items if i["due"]), "items": items}


def update(events: list[dict], *, now: float | None = None, tz: tzinfo | None = None,
           skill_ids: list[str] | None = None) -> dict:
    """What changed after a pass: the events and the touched skills' rows (the app patches its tree in place)."""
    now, rows = _now(now), ledger.load()
    ids = list(dict.fromkeys([*(skill_ids or []), *(e["skillId"] for e in events or [])]))
    out: dict[str, Any] = {"events": list(events or []),
                           "skills": [ledger.row_view(i, rows, now, tz) for i in ids if catalog.skill(i)]}
    out["due"] = len(ledger.due(now=now, tz=tz))
    return out
