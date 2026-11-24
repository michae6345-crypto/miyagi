"""Passes, mastery and the review schedule of every catalog skill: ~/miyagi/state/skilltree.json (MIYAGI_STATE_DIR).

Mastery rule (Adrian's skill tree, Nov 22): a skill is mastered once the learner passed a step that practises it
UNASSISTED (no hint, no show me, no "Do it for me" on that step) on 2 different local days. Assisted passes are kept
(they count as practice) but never toward mastery. A skipped step is never a pass.

Review schedule: mastered -> a review is due 3 days later (from the start of that local day), then 7, 21 and 60 days
after each passed review (60 repeats). A review is any unassisted pass of a step that practises the skill once it is
due (or review.start's explicit result). An assisted pass or a miss of a due review sends it back to the 3-day stage.
Mastery is never taken back: review is a modifier on mastered, never a demotion (the contract's SkillGraphState rule).

    record_pass(skill_ids, lesson_id=, step_id=, assisted=, now=, tz=, proof_id=) -> [event]   (mastered / reviewed / review_missed)
    record_review(skill_id, passed, now=, tz=)                                     -> event | None
    skill_row(skill_id, now=, tz=)                                                 -> the skill's state (see _row)
    due(now=, tz=)                                                                 -> due reviews, oldest first
    forget(skill_id=None)                                                          -> drop one skill's record, or all

Every function that reads the time takes `now` (epoch s) and `tz` so tests are deterministic. Never calls a model or
the network. Writes are atomic (store._write_atomic) and serialised by a lock (the engine writes from worker threads).
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, time as dtime, timedelta, tzinfo
from typing import Any

from server.sessions import store

from . import catalog

INTERVALS = (3, 7, 21, 60)  # days: stage i waits INTERVALS[i] after mastery / the last review
MASTERY_DAYS = 2  # unassisted passes on this many different local days
MAX_PASSES = 30  # kept per skill (newest); mastery and the schedule are stored, so trimming never undoes them
MAX_SKILLS = 1000
MASTERED, PRACTICING, READY, LOCKED = "mastered", "practicing", "ready", "locked"

_lock = threading.RLock()


def path():
    return store.state_dir() / "skilltree.json"


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def day_of(t: float, tz: tzinfo | None = None) -> str:
    return datetime.fromtimestamp(t, tz).date().isoformat()


def due_at(base: float, days: int, tz: tzinfo | None = None) -> float:
    """The start of the local day `days` calendar days after `base`'s day (a DST change never moves it)."""
    day = datetime.fromtimestamp(base, tz).date() + timedelta(days=days)
    return datetime.combine(day, dtime.min, tzinfo=tz).timestamp()


# ------------------------------------------------------------------------------------------------ the file
def _clean_pass(p: Any) -> dict | None:
    if not isinstance(p, dict) or _num(p.get("at")) is None or not isinstance(p.get("day"), str):
        return None
    out = {"at": float(p["at"]), "day": p["day"][:10], "assisted": bool(p.get("assisted"))}
    for k in ("lessonId", "stepId", "proofId"):
        if isinstance(p.get(k), str) and p[k]:
            out[k] = p[k][:120]
    return out


def _clean_review(r: Any) -> dict | None:
    if not isinstance(r, dict) or not isinstance(r.get("stage"), int) or not 0 <= r["stage"] < len(INTERVALS) \
            or _num(r.get("dueAt")) is None:
        return None
    return {"stage": r["stage"], "dueAt": float(r["dueAt"]), "lastAt": _num(r.get("lastAt")),
            "lastResult": r.get("lastResult") if r.get("lastResult") in ("passed", "missed") else None,
            "reps": r["reps"] if isinstance(r.get("reps"), int) and r["reps"] >= 0 else 0}


def load() -> dict[str, dict]:
    """skill id -> {passes, masteredAt, review}. Unreadable or foreign content reads as empty; unknown ids are kept
    (a catalog update may bring them back) but never shown."""
    data = store._read(path())
    rows = data.get("skills") if isinstance(data, dict) else None
    out: dict[str, dict] = {}
    for sid, v in (rows.items() if isinstance(rows, dict) else []):
        if not isinstance(sid, str) or not isinstance(v, dict):
            continue
        passes = [p for p in (_clean_pass(x) for x in v.get("passes") or []) if p][-MAX_PASSES:]
        out[sid] = {"passes": passes, "masteredAt": _num(v.get("masteredAt")), "review": _clean_review(v.get("review"))}
    return out


def _save(rows: dict[str, dict]) -> None:
    if len(rows) > MAX_SKILLS:
        newest = sorted(rows.items(), key=lambda kv: max([p["at"] for p in kv[1]["passes"]] or [0]), reverse=True)
        rows = dict(newest[:MAX_SKILLS])
    store._write_atomic(path(), {"version": 1, "skills": rows})


# ------------------------------------------------------------------------------------------------ the rules
def unassisted_days(row: dict) -> list[str]:
    return sorted({p["day"] for p in row.get("passes") or [] if not p.get("assisted")})


def _schedule(stage: int, now: float, tz: tzinfo | None, result: str | None, reps: int) -> dict:
    return {"stage": stage, "dueAt": due_at(now, INTERVALS[stage], tz), "lastAt": now if result else None,
            "lastResult": result, "reps": reps}


def _review_outcome(sid: str, row: dict, passed: bool, now: float, tz: tzinfo | None) -> dict:
    old = row.get("review") or {"stage": 0, "reps": 0}
    stage = min(old["stage"] + 1, len(INTERVALS) - 1) if passed else 0
    row["review"] = _schedule(stage, now, tz, "passed" if passed else "missed", old.get("reps", 0) + (1 if passed else 0))
    return {"kind": "reviewed" if passed else "review_missed", "skillId": sid, "at": now,
            "nextDueAt": row["review"]["dueAt"], "interval": INTERVALS[stage]}


def record_pass(skill_ids: list[str], *, lesson_id: str | None = None, step_id: str | None = None, assisted: bool = False,
                now: float | None = None, tz: tzinfo | None = None, proof_id: str | None = None) -> list[dict]:
    """A step that practises `skill_ids` passed (never call this for a skipped step). Returns what changed:
    {"kind": "mastered" | "reviewed" | "review_missed", "skillId", "at", ...}. Unknown ids are ignored."""
    now = time.time() if now is None else float(now)
    ids = list(dict.fromkeys(s for s in skill_ids or [] if isinstance(s, str) and catalog.skill(s)))
    if not ids:
        return []
    events: list[dict] = []
    with _lock:
        rows = load()
        for sid in ids:
            row = rows.setdefault(sid, {"passes": [], "masteredAt": None, "review": None})
            p = {"at": now, "day": day_of(now, tz), "assisted": bool(assisted)}
            if lesson_id:
                p["lessonId"] = str(lesson_id)[:120]
            if step_id:
                p["stepId"] = str(step_id)[:120]
            if proof_id:
                p["proofId"] = str(proof_id)[:120]
            row["passes"] = (row["passes"] + [p])[-MAX_PASSES:]
            if row["masteredAt"] is None:
                if not assisted and len(unassisted_days(row)) >= MASTERY_DAYS:
                    row["masteredAt"] = now
                    row["review"] = _schedule(0, now, tz, None, 0)
                    events.append({"kind": "mastered", "skillId": sid, "at": now, "nextDueAt": row["review"]["dueAt"]})
            elif row["review"] is None:
                row["review"] = _schedule(0, now, tz, None, 0)  # a record from before the schedule: start it
            elif now >= row["review"]["dueAt"]:
                events.append(_review_outcome(sid, row, not assisted, now, tz))
        _save(rows)
    return events


def record_review(skill_id: str, passed: bool, *, now: float | None = None, tz: tzinfo | None = None) -> dict | None:
    """review.start's explicit result for a mastered skill (passed, or skipped / missed), due or not. None when the skill
    is not mastered (nothing to review)."""
    now = time.time() if now is None else float(now)
    with _lock:
        rows = load()
        row = rows.get(skill_id)
        if not row or row.get("masteredAt") is None:
            return None
        ev = _review_outcome(skill_id, row, passed, now, tz)
        _save(rows)
    return ev


def forget(skill_id: str | None = None) -> int:
    """Delete one skill's record (passes, mastery, schedule), or every skill's. Returns how many went."""
    with _lock:
        if skill_id is None:
            n = len(load())
            try:
                path().unlink()
            except FileNotFoundError:
                pass
            return n
        rows = load()
        if rows.pop(skill_id, None) is None:
            return 0
        _save(rows)
        return 1


# ------------------------------------------------------------------------------------------------ reads
def state_of(sid: str, rows: dict[str, dict]) -> str:
    row = rows.get(sid) or {}
    if row.get("masteredAt"):
        return MASTERED
    if row.get("passes"):
        return PRACTICING
    sk = catalog.skill(sid)
    needs = [n for n in (sk.needs if sk else ()) if catalog.skill(n)]
    return READY if all((rows.get(n) or {}).get("masteredAt") for n in needs) else LOCKED


def row_view(sid: str, rows: dict[str, dict], now: float, tz: tzinfo | None = None) -> dict:
    """One skill as the wire shows it (catalog facts + this Mac's record)."""
    sk = catalog.skill(sid)
    row = rows.get(sid) or {"passes": [], "masteredAt": None, "review": None}
    days = unassisted_days(row)
    out: dict[str, Any] = {"id": sid, "label": sk.label if sk else sid, "track": sk.track if sk else "",
                           "planId": sk.plan_id if sk else "", "needs": list(sk.needs) if sk else [],
                           "state": state_of(sid, rows), "passes": len(row["passes"]),
                           "unassistedDays": min(len(days), MASTERY_DAYS), "daysNeeded": MASTERY_DAYS}
    if row["passes"]:
        out["lastPassAt"] = row["passes"][-1]["at"]
    if row["masteredAt"]:
        out["masteredAt"] = row["masteredAt"]
    rv = row.get("review")
    if row["masteredAt"] and rv:
        out["review"] = {"dueAt": rv["dueAt"], "due": now >= rv["dueAt"], "interval": INTERVALS[rv["stage"]],
                         "stage": rv["stage"], "reps": rv["reps"], **({"lastResult": rv["lastResult"]} if rv["lastResult"] else {}),
                         **({"lastAt": rv["lastAt"]} if rv["lastAt"] else {})}
    proofs = [p["proofId"] for p in row["passes"] if p.get("proofId")]
    if proofs:
        out["proofIds"] = proofs[-5:][::-1]
    return out


def skill_row(skill_id: str, *, now: float | None = None, tz: tzinfo | None = None) -> dict | None:
    if catalog.skill(skill_id) is None:
        return None
    return row_view(skill_id, load(), time.time() if now is None else float(now), tz)


def due(*, now: float | None = None, tz: tzinfo | None = None, within_s: float = 0.0) -> list[dict]:
    """Reviews due by now (+ within_s), oldest due first: [{skillId, label, track, dueAt, interval, overdueDays}]."""
    now = time.time() if now is None else float(now)
    out = []
    for sid, row in load().items():
        rv, sk = row.get("review"), catalog.skill(sid)
        if not sk or not row.get("masteredAt") or not rv or rv["dueAt"] > now + within_s:
            continue
        out.append({"skillId": sid, "label": sk.label, "track": sk.track, "dueAt": rv["dueAt"],
                    "interval": INTERVALS[rv["stage"]], "due": now >= rv["dueAt"],
                    "overdueDays": max(0, (datetime.fromtimestamp(now, tz).date()
                                           - datetime.fromtimestamp(rv["dueAt"], tz).date()).days)})
    return sorted(out, key=lambda r: (r["dueAt"], r["skillId"]))
