"""The Progress window's data: skills by track, finished lessons, lessons in progress. GET /progress, progress.get.

    from server.sessions import progress
    progress.progress()          -> ProgressPayload | None      (reads ~/miyagi/state; None = nothing to show yet)
    progress.build(...)          -> the same, from data passed in (pure: no I/O)
    progress.tracks(maps)        -> [SkillTrack]                (pure: merges skill maps by track)

Where it comes from (all on this Mac, all written by the engine as the learner works):
- history.json (store.completed()): finished lessons. E3 adds the lesson's skill map to each entry
  (`skillMap`, the same SkillMap the completion card drew) and may add `result` ({passed, skipped, total}).
- current.json + its graph (store.load / load_graph): the lesson in progress. Its skill map is computed here from the
  steps it has passed and skipped (lesson/skillmap.skill_map: pure, no model call).
- recent.json (store.recent()): unfinished lessons a newer one replaced (no graph kept, so no skills from them).

Never invented (BUILD-PLAN A8, "empty states when /progress is null"): a skill is mastered only when a skill map
said so; a track with no map has no row; there is no activity minutes or streak until something records them, so those
fields are absent rather than zero. `review` (sessions/review.py, the spaced-review scheduler: due and upcoming skills) is
added only when at least one skill has been mastered. Skipped steps are counted as skipped, never passed.

Skill states on the wire: "mastered" | "practicing" | "not_started" (SkillMap's mastered / learning / next). The
same skill in two lessons keeps its best state. Contract shape (W0-1 `progress`): app/agents/eng-modules.md.
"""

from __future__ import annotations

import logging
from typing import Any

from . import store

log = logging.getLogger("sessions")

MASTERED, PRACTICING, NOT_STARTED = "mastered", "practicing", "not_started"
_FROM_MAP = {"mastered": MASTERED, "learning": PRACTICING, "next": NOT_STARTED}
_RANK = {NOT_STARTED: 0, PRACTICING: 1, MASTERED: 2}
MAX_TRACKS = 20
MAX_SKILLS_PER_TRACK = 24
MAX_LESSONS = 50


def _text(v: Any, limit: int = 200) -> str | None:
    """Display text, or None when empty or when it holds a filesystem path (so the caller's fallback, e.g. "Lesson",
    applies before scrub() would drop the whole field). Key-shaped text is removed."""
    if not isinstance(v, str):
        return None
    from server.lesson.library import _clean_text  # pure; deferred like the other library uses here

    c = _clean_text(v)
    t = " ".join(c.split()) if c is not None else ""
    return (t if len(t) <= limit else t[: limit - 1].rstrip() + "…") if t else None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _count(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 10_000 else None


# ------------------------------------------------------------------------------------------------ skills
def tracks(maps: list[dict]) -> list[dict]:
    """SkillMaps (newest first) merged by track: [{track, mastered, total, skills: [{id, label, state}]}].
    A skill is keyed by its label (case-insensitive) within its track; the best state seen wins; order is the order a
    skill was first seen (the track's own left-to-right order). Tracks with no skills are left out."""
    order: list[str] = []
    by_track: dict[str, dict[str, Any]] = {}
    for m in maps:
        if not isinstance(m, dict):
            continue
        name = _text(m.get("track"), 80)
        if not name:
            continue
        key = name.lower()
        t = by_track.get(key)
        if t is None:
            t = by_track[key] = {"track": name, "skills": {}, "order": []}
            order.append(key)
        for n in m.get("nodes") or []:
            if not isinstance(n, dict):
                continue
            label = _text(n.get("label"), 80)
            state = _FROM_MAP.get(n.get("state"))
            if not label or state is None:
                continue
            sk = label.lower()
            have = t["skills"].get(sk)
            if have is None:
                t["skills"][sk] = {"id": _text(n.get("id"), 80) or sk, "label": label, "state": state}
                t["order"].append(sk)
            elif _RANK[state] > _RANK[have["state"]]:
                have["state"] = state
    out = []
    for key in order[:MAX_TRACKS]:
        t = by_track[key]
        skills = [t["skills"][k] for k in t["order"][:MAX_SKILLS_PER_TRACK]]
        if not skills:
            continue
        out.append({"track": t["track"], "mastered": sum(s["state"] == MASTERED for s in skills),
                    "total": len(skills), "skills": skills})
    return out


def current_map(state: dict | None, graph: dict | None) -> dict | None:
    """The in-progress lesson's skill map from what it has passed / skipped so far (None without a graph)."""
    if not isinstance(state, dict) or not isinstance(graph, dict) or not graph.get("steps"):
        return None
    from server.lesson import skillmap  # pure (no I/O, no model)

    results = {"passed": [str(s) for s in state.get("passedSteps") or [] if s],
               "skipped": [str(s) for s in state.get("skippedSteps") or [] if s]}
    try:
        return skillmap.skill_map(graph, results)
    except Exception as e:  # noqa: BLE001 - a progress view must not fail on one odd graph
        log.warning("progress: no skill map for the saved lesson: %s", e)
        return None


# ------------------------------------------------------------------------------------------------ lessons
def finished_at(history: list[dict]) -> dict[str, float | None]:
    """lessonId -> its latest finishedAt (None when no history entry for it has one), from store.completed()."""
    out: dict[str, float | None] = {}
    for e in history or []:
        lid = e.get("lessonId") if isinstance(e, dict) else None
        if not isinstance(lid, str) or not lid:
            continue
        t = _num(e.get("finishedAt"))
        prev = out.get(lid)
        out[lid] = t if prev is None else (prev if t is None else max(prev, t))
    return out


def superseded(row: dict, finished: dict[str, float | None], is_current: bool = False) -> bool:
    """True when a saved lesson row (current.json or a recent.json entry) was finished after it was last active, so
    it is not in progress any more. The one rule library Continue and progress inProgress both use, so they agree.

    A row whose lesson was never finished is kept. A replay (active after its last finish) is kept. When a timestamp
    is missing: the current lesson is kept (it is the live session), a recent row is dropped (it can't prove it is
    newer than the finish)."""
    lid = row.get("lessonId")
    if not isinstance(lid, str) or lid not in finished:
        return False
    done, active = finished[lid], _num(row.get("lastActiveAt"))
    if done is None or active is None:
        return not is_current
    return done >= active


def _finished_row(e: dict, index: dict[str, str]) -> dict | None:
    lid = e.get("lessonId")
    if not isinstance(lid, str) or not lid:
        return None
    row: dict[str, Any] = {"lessonId": lid, "title": _text(e.get("title")) or "Lesson"}
    if (t := _num(e.get("finishedAt"))) is not None:
        row["finishedAt"] = round(t, 3)
    res = e.get("result")
    if isinstance(res, dict):
        counts = {k: c for k in ("passed", "skipped", "total") if (c := _count(res.get(k))) is not None}
        if counts:
            row["result"] = counts
    if lid in index:
        row["libraryId"] = index[lid]
    return row


def _active_row(s: dict, index: dict[str, str]) -> dict | None:
    lid = s.get("lessonId")
    if not isinstance(lid, str) or not lid:
        return None
    row: dict[str, Any] = {"lessonId": lid, "title": _text(s.get("title")) or "Lesson",
                           "mode": "lesson" if s.get("mode") == "lesson" else "video"}
    for k in ("stepIndex", "stepCount"):
        if (c := _count(s.get(k))) is not None:
            row[k] = c
    passed = s.get("passedSteps")
    skipped = s.get("skippedSteps")
    if isinstance(passed, list):
        row["passed"] = len({str(x) for x in passed if x} - {str(x) for x in skipped or [] if x})
    if isinstance(skipped, list):
        row["skipped"] = len({str(x) for x in skipped if x})
    if t := _text(s.get("stepTitle")):
        row["stepTitle"] = t
    if (t2 := _num(s.get("lastActiveAt"))) is not None:
        row["lastActiveAt"] = round(t2, 3)
    if lid in index:
        row["libraryId"] = index[lid]
    return row


def build(history: list[dict], current: dict | None = None, current_graph: dict | None = None,
          recent: list[dict] | None = None, index: dict[str, str] | None = None,
          review: dict | None = None) -> dict | None:
    """ProgressPayload from data already read (pure). None when there is nothing at all to show.

    history: store.completed() (oldest first); current / current_graph: store.load() / load_graph();
    recent: store.recent(); index: lesson.id -> library id (library.index_by_lesson_id()); review: review.payload()
    ({due, items}), passed through as is when given."""
    index = index or {}
    history = [e for e in history or [] if isinstance(e, dict)]
    newest_first = list(reversed(history))
    finished = finished_at(history)
    if not isinstance(current, dict) or superseded(current, finished, is_current=True):
        current = None  # finished after it was last active: a completed row, not an in-progress one

    maps: list[dict] = []
    cm = current_map(current, current_graph) if current else None
    if cm:
        maps.append(cm)
    maps += [e["skillMap"] for e in newest_first if isinstance(e.get("skillMap"), dict)]

    completed = [r for r in (_finished_row(e, index) for e in newest_first[:MAX_LESSONS]) if r]
    active: list[dict] = []
    seen: set[str] = set()
    rows = ([current] if current else []) + [r for r in recent or [] if isinstance(r, dict)
                                                and not superseded(r, finished)]
    for s in rows:
        row = _active_row(s, index)
        if row is None or row["lessonId"] in seen:
            continue
        seen.add(row["lessonId"])
        active.append(row)

    skills = tracks(maps)
    if not skills and not completed and not active:
        return None
    out: dict[str, Any] = {"skills": skills, "completed": completed, "inProgress": active}
    if isinstance(review, dict) and review.get("items"):
        out["review"] = review
    return out


def progress() -> dict | None:
    """GET /progress and progress.get: build() over what is saved on this Mac. None when there is nothing yet (or the
    state folder can't be read): the app shows its empty states."""
    try:
        history = store.completed()
        current = store.load()
        graph = store.load_graph(current) if current is not None else None
        recent = store.recent()
    except Exception as e:  # noqa: BLE001
        log.warning("progress: could not read the saved state: %s", e)
        return None
    from server.lesson import library  # scrub() + the library index

    try:
        index = library.index_by_lesson_id()
    except Exception as e:  # noqa: BLE001 - linking to the library is a nicety
        log.debug("progress: no library index: %s", e)
        index = {}
    try:
        from . import review

        due = review.payload()
    except Exception as e:  # noqa: BLE001 - the schedule is an extra: progress still answers without it
        log.warning("progress: no review schedule: %s", e)
        due = None
    out = build(history, current, graph, recent, index, due)
    if out is not None:  # Nov 22 (Skills page): the merged skill graph, additive; absent = the app draws `skills` as chains
        try:
            from . import skills_graph

            if (g := skills_graph.graph()) is not None:
                out["graph"] = g
        except Exception as e:  # noqa: BLE001 - the graph is an extra: progress still answers without it
            log.warning("progress: no skill graph: %s", e)
    return library.scrub(out) if out is not None else None
