"""The catalog skill tree on progress.graph (contract SkillGraphInfo, ui-v4 round 3: tracks -> skills -> steps).

    merge(progress, current=None, now=, tz=) -> progress with graph.skills / edges / tracks / masteryDays / reviewDays

progress is contract_progress's output (may be {}); its graph (sessions/skills_graph.py, built from the lessons' own
skill maps) keeps every node it has. This adds, for every track the learner has touched (a passed step, or the lesson
running now), the track's catalog skills as SkillInfo nodes (id = catalogId = the catalog id, "bl.extrude"):

- state: mastered (2 unassisted days), practicing (a pass), ready (every need mastered), locked
- mastery {need, days, assisted}, schedule {dueAt, round, interval, lastAt, lastResult} and review {dueAt} once mastered
- steps: the Steps zoom, every step behind it (the passes, then the lesson running now's steps not passed yet)
- evidence {done, total} over those steps, proofIds newest first, lastPracticedAt
- requires edges from each catalog need; graph.tracks (SkillTrackInfo) in catalog order; keepFresh gets due reviews
- events: a "mastered" SkillEvent for a skill mastered after ackedUntil (the last day when nothing was acked)

Times are ISO 8601 with the learner's offset. Pure but for reading skilltree.json and the proofs folder.
"""

from __future__ import annotations

import time
from datetime import tzinfo
from typing import Any

from . import catalog, ledger, proofs
from .proofs import iso

MAX_STEPS = 30  # SkillInfo.steps per skill
MAX_KEEP_FRESH = 3
MAX_EVENTS = 20
UNSEEN_WINDOW_S = 86_400


def _moment(v: Any) -> float | None:
    try:
        from server.sessions.skills_graph import moment

        return moment(v)
    except Exception:  # noqa: BLE001 - an unreadable ack reads as none
        return None


def _key(p: dict) -> str:
    return f"{p.get('lessonId') or 'lesson'}:{p.get('stepId') or 'step'}"


def _steps(sid: str, row: dict, current: dict | None, tz: tzinfo | None) -> list[dict]:
    """Passed steps (one per key, the first pass, oldest first), then the running lesson's steps not passed yet."""
    seen: dict[str, dict] = {}
    for p in row.get("passes") or []:
        k = _key(p)
        if k not in seen:
            seen[k] = {"key": k, "lessonId": p.get("lessonId") or "lesson", "stepId": p.get("stepId") or "step",
                       "title": p.get("stepTitle") or p.get("stepId") or "Step", "passed": True, "at": iso(p["at"], tz),
                       "assisted": bool(p.get("assisted"))}
            if p.get("lessonTitle"):
                seen[k]["lessonTitle"] = p["lessonTitle"]
    out = list(seen.values())
    if current:
        les = current.get("lesson") or {}
        lid = str(les.get("id") or "")
        for st in current.get("steps") or []:
            if not isinstance(st, dict) or sid not in (current.get("tags") or {}).get(st.get("id"), []):
                continue
            k = f"{lid}:{st['id']}"
            if lid and k not in seen:
                ref = {"lessonId": lid, "stepId": st["id"], "title": str(st.get("title") or st["id"])[:200], "passed": False}
                if les.get("title"):
                    ref["lessonTitle"] = str(les["title"])[:200]
                out.append(ref)
    return out[-MAX_STEPS:]


def skill_info(sid: str, rows: dict[str, dict], now: float, tz: tzinfo | None, current: dict | None = None) -> dict:
    sk = catalog.skill(sid)
    row = rows.get(sid) or {"passes": [], "masteredAt": None, "review": None}
    state = ledger.state_of(sid, rows)
    info: dict[str, Any] = {"id": sid, "label": sk.label if sk else sid, "track": sk.track if sk else "", "kind": "skill",
                            "catalogId": sid, "state": state}
    if sk and sk.lessons:
        info["summary"] = f"Grown in {sk.lessons[0]}"[:80]
    steps = _steps(sid, row, current, tz)
    if steps:
        info["steps"] = steps
        info["evidence"] = {"done": sum(1 for s in steps if s["passed"]), "total": len(steps)}
    passes = row.get("passes") or []
    if passes:
        info["lastPracticedAt"] = iso(passes[-1]["at"], tz)
    info["mastery"] = {"need": ledger.MASTERY_DAYS, "days": ledger.unassisted_days(row)[:ledger.MASTERY_DAYS] if
                       row.get("masteredAt") else ledger.unassisted_days(row),
                       "assisted": sum(1 for p in passes if p.get("assisted"))}
    rv = row.get("review")
    if row.get("masteredAt"):
        info["masteredAt"] = iso(row["masteredAt"], tz)
        if rv:
            info["review"] = {"dueAt": iso(rv["dueAt"], tz)}
            sched = {"dueAt": iso(rv["dueAt"], tz), "round": rv["stage"], "interval": ledger.INTERVALS[rv["stage"]]}
            if rv.get("lastAt"):
                sched["lastAt"] = iso(rv["lastAt"], tz)
            if rv.get("lastResult"):
                sched["lastResult"] = "pass" if rv["lastResult"] == "passed" else "miss"
            info["schedule"] = sched
    ids = [p["proofId"] for p in reversed(passes) if p.get("proofId") and proofs.get(p["proofId"])]
    if ids:
        info["proofIds"] = list(dict.fromkeys(ids))[:proofs.FOR_SKILL]
    return info


def _track_info(t: catalog.Track, infos: dict[str, dict]) -> dict:
    skills = [infos[s.id] for s in t.skills if s.id in infos]
    mastered = sum(1 for s in skills if s["state"] == ledger.MASTERED)
    nxt = next((s["id"] for s in skills if s["state"] == ledger.PRACTICING), None) or \
        next((s["id"] for s in skills if s["state"] == ledger.READY), None)
    out = {"id": t.id, "label": t.label, "mastered": mastered, "total": len(skills), "planIds": [p.id for p in t.plans]}
    if nxt:
        out["next"] = nxt
    last = max((s["lastPracticedAt"] for s in skills if s.get("lastPracticedAt")), default=None)
    if last:
        out["lastPracticedAt"] = last
    return out


def touched_tracks(rows: dict[str, dict], current: dict | None) -> list[str]:
    ids = {sk.track for sid in rows if (sk := catalog.skill(sid)) is not None and rows[sid].get("passes")}
    for tags in ((current or {}).get("tags") or {}).values():
        ids.update(sk.track for sid in tags if (sk := catalog.skill(sid)) is not None)
    return [t.id for t in catalog.tracks() if t.id in ids]


def merge(progress: dict | None, *, current: dict | None = None, now: float | None = None,
          tz: tzinfo | None = None) -> dict:
    now = time.time() if now is None else float(now)
    out = dict(progress or {})
    rows = ledger.load()
    tracks = touched_tracks(rows, current)
    if not tracks:
        return out
    graph = dict(out.get("graph") or {})
    by_track = catalog.get().tracks_by_id
    infos: dict[str, dict] = {}
    for tid in tracks:
        for sk in by_track[tid].skills:
            infos[sk.id] = skill_info(sk.id, rows, now, tz, current)
    keep = [s for s in graph.get("skills") or [] if isinstance(s, dict) and s.get("id") not in infos]
    graph["skills"] = keep + list(infos.values())
    edges = [e for e in graph.get("edges") or [] if isinstance(e, dict)
             and e.get("from") not in infos and e.get("to") not in infos]
    for sid in infos:
        for need in catalog.skill(sid).needs:
            if need in infos:
                edges.append({"from": need, "to": sid, "kind": "requires"})
    graph["edges"] = edges
    graph["tracks"] = list(graph.get("tracks") or []) + [_track_info(by_track[t], infos) for t in tracks]
    graph["masteryDays"] = ledger.MASTERY_DAYS
    graph["reviewDays"] = list(ledger.INTERVALS)
    fresh = list(graph.get("keepFresh") or [])
    for r in ledger.due(now=now, tz=tz):
        if len(fresh) >= MAX_KEEP_FRESH:
            break
        if r["skillId"] in infos and r["skillId"] not in fresh:
            fresh.append(r["skillId"])
    if fresh:
        graph["keepFresh"] = fresh
    acked = _moment(graph.get("ackedUntil"))
    since = acked if acked is not None else now - UNSEEN_WINDOW_S
    events = list(graph.get("events") or [])
    for sid, info in infos.items():
        at = (rows.get(sid) or {}).get("masteredAt")
        if at and at > since and len(events) < MAX_EVENTS:
            events.append({"id": f"mastered-{sid}-{int(at)}", "kind": "mastered", "skillId": sid, "at": iso(at, tz)})
    if events:
        graph["events"] = events
    out["graph"] = graph
    return out
