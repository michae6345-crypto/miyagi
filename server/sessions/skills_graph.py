"""The Skills page's graph: Progress.graph (SkillGraphInfo in shared/contracts/events.py). progress.get, GET /progress.

    skills_graph.build_graph(history, current, current_graph, ...) -> SkillGraphInfo dict | None   (pure: no I/O, no model)
    skills_graph.graph()                                          -> the same, from what is saved on this Mac
    skills_graph.set_goal(capstone_id) / skills_graph.ack(until)  -> persist the learner's two choices (skills.json)
    skills_graph.skill_id(track, label)                           -> the id a skill has everywhere (graph, step.skillIds, LibraryItem.teaches)

Where it comes from (nothing is invented, no model call): the skill maps the engine already keeps. Every finished lesson
(history.json) stores the SkillMap its completion card drew, and the lesson in progress has one computed from the steps
passed and skipped (sessions/progress.current_map). A SkillMap names a track and its concepts (mastered / learning / next)
with a chain of edges and "shared idea" cross links. This module merges those maps into one graph across lessons:

- a skill is one concept of one track, keyed by track + label (case-insensitive: the same merge rule as progress.tracks and
  review.skill_key); the best state any lesson showed wins. state: mastered, practicing (a skipped step, or steps passed
  in the lesson in progress), ready (every prerequisite mastered), locked (a prerequisite is not mastered yet).
- edges: each map's chain is `requires`; a cross link from a skill that exists in another track is `helps`. An edge that
  would close a loop is dropped.
- one capstone per track: "<Track> project", requires every skill of the track. It counts as done once all of them are
  mastered (completedAt: the last of those masteredAt times). A real project step per track is a gap: nothing records one.
- goal: the capstone the learner picked (set_goal, kept in skills.json), else the furthest-along unfinished track's.
- next: the practicing / ready skill nearest the start of the goal's path (a practicing one first). With a lesson in
  progress that teaches it, it carries lessonId, libraryId and stepIndex.
- events: mastered / unlocked / capstone_done moments newer than ackedUntil (skills.ack), each with a stable id.
  A learner who never acked sees the last 24 hours, never the whole history replayed.
- review.dueAt comes from the spaced-review schedule (sessions/review.py); keepFresh lists up to 3 reviews due within a day.

Times are epoch seconds (the contract's Moment). Everything that reads the time takes `now` and `tz`.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, tzinfo
from typing import Any

from . import store

log = logging.getLogger("sessions")

MASTERED, PRACTICING, READY, LOCKED = "mastered", "practicing", "ready", "locked"
_RANK = {"not_started": 0, "practicing": 1, "mastered": 2}
_FROM_MAP = {"mastered": "mastered", "learning": "practicing", "next": "not_started"}
MAX_SKILLS = 400
MAX_EVENTS = 20
MAX_ALSO_READY = 3
MAX_KEEP_FRESH = 3
KEEP_FRESH_WITHIN_S = 86_400  # a review due within a day of now is worth a look
UNSEEN_WINDOW_S = 86_400  # no ack yet: events of the last day play, the older history never replays
PRACTICE_ORDER = (PRACTICING, READY)  # next: a practicing skill before a ready one


def _path():
    return store.state_dir() / "skills.json"


# ------------------------------------------------------------------------------------------------ ids and numbers
def slug(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:40].strip("-") or "x"


def skill_id(track: str, label: str) -> str:
    """The id of the skill `label` on `track` ("numpy.broadcasting"). The same everywhere the engine names a skill;
    build_graph adds -2, -3 only when two different labels slug alike on one track."""
    return f"{slug(track)}.{slug(label)}"


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def moment(v: Any) -> float | None:
    """A Moment (epoch seconds, or ISO text) as epoch seconds; None when it is neither."""
    if (n := _num(v)) is not None:
        return n
    if isinstance(v, str) and v.strip():
        try:
            d = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
            return d.timestamp()
        except ValueError:
            return None
    return None


def _clean(v: Any, limit: int = 80) -> str:
    return " ".join(str(v or "").split())[:limit]


# ------------------------------------------------------------------------------------------------ the learner's choices
def load_prefs() -> dict:
    """skills.json: {goal?: capstone id, ackedUntil?: epoch seconds}. Unreadable or foreign content reads as empty."""
    data = store._read(_path())
    out: dict[str, Any] = {}
    if isinstance(data, dict):
        if isinstance(data.get("goal"), str) and data["goal"]:
            out["goal"] = data["goal"][:120]
        if (t := _num(data.get("ackedUntil"))) is not None:
            out["ackedUntil"] = t
    return out


def _save_prefs(prefs: dict) -> None:
    store._write_atomic(_path(), {"version": 1, **{k: v for k, v in prefs.items() if k in ("goal", "ackedUntil")}})


def set_goal(capstone_id: str) -> dict:
    """The learner picked a goal. Stored as sent; build_graph ignores one that is not a capstone (any more)."""
    prefs = load_prefs()
    if cid := _clean(capstone_id, 120):  # a blank id picks nothing
        prefs["goal"] = cid
        _save_prefs(prefs)
    return prefs


def ack(until: Any) -> dict:
    """The unlock events up to `until` played. Never moves back: a late, older ack changes nothing."""
    prefs = load_prefs()
    t = moment(until)
    if t is not None and t > prefs.get("ackedUntil", 0):
        prefs["ackedUntil"] = t
        _save_prefs(prefs)
    return prefs


# ------------------------------------------------------------------------------------------------ merging the maps
class _Skill:
    __slots__ = ("track", "label", "id", "state", "detail", "mastered_at", "last", "lessons", "goal", "done", "total",
                 "order", "is_next_topic")

    def __init__(self, track: str, label: str, order: int) -> None:
        self.track, self.label, self.order = track, label, order
        self.id = ""
        self.state = "not_started"
        self.detail = ""
        self.mastered_at: float | None = None
        self.last: float | None = None
        self.lessons: dict[str, dict] = {}
        self.goal: str | None = None
        self.done = 0
        self.total = 0
        self.is_next_topic = True


def _words6(text: str) -> str:
    from server.lesson.skillmap import _words, MAX_LABEL_WORDS

    return _words(" ".join(str(text).split()), MAX_LABEL_WORDS)


def _sources(history: list[dict], current: dict | None, current_graph: dict | None,
             index: dict[str, str]) -> list[dict]:
    """The skill maps to merge, the lesson in progress first, then the finished lessons newest first."""
    out: list[dict] = []
    if isinstance(current, dict):
        from . import progress

        cm = progress.current_map(current, current_graph)
        if cm:
            taught: dict[str, list[str]] = {}
            try:
                from server.lesson.skillmap import node_steps

                taught = {t["id"]: t["steps"] for t in node_steps(current_graph)["taught"]}
            except Exception as e:  # noqa: BLE001 - evidence is an extra; the map still merges
                log.debug("skills graph: no step map for the saved lesson: %s", e)
            passed = {str(s) for s in current.get("passedSteps") or [] if s} - {str(s) for s in current.get("skippedSteps") or [] if s}
            out.append({"map": cm, "lessonId": current.get("lessonId"), "title": current.get("title"), "at": _num(current.get("lastActiveAt")),
                        "current": True, "taught": taught, "passed": passed,
                        "stepIndex": current.get("stepIndex"), "stepCount": current.get("stepCount")})
    for e in reversed([e for e in history or [] if isinstance(e, dict)]):
        if isinstance(e.get("skillMap"), dict):
            out.append({"map": e["skillMap"], "lessonId": e.get("lessonId"), "title": e.get("title"),
                        "at": _num(e.get("finishedAt")), "current": False, "taught": {}, "passed": set(),
                        "minutes": (e.get("result") or {}).get("minutes") if isinstance(e.get("result"), dict) else None})
    for s in out:
        lid = s.get("lessonId")
        s["libraryId"] = index.get(lid) if isinstance(lid, str) else None
    return out


def _merge(sources: list[dict]) -> tuple[dict[tuple[str, str], _Skill], list[tuple[str, str, str]], list[tuple]]:
    """(skills by (track, label) lowercase, requires edges as (from key, to key), cross links as (from key, to key, kind))."""
    skills: dict[tuple[str, str], _Skill] = {}
    requires: list[tuple[tuple[str, str], tuple[str, str]]] = []
    cross: list[tuple[tuple[str, str], tuple[str, str]]] = []
    for src in sources:
        m = src["map"]
        track = _clean(m.get("track"), 80)
        if not track:
            continue
        local: dict[str, tuple[str, str]] = {}
        topics = {_words6(n.get("title")).lower(): n for n in m.get("next") or [] if isinstance(n, dict) and n.get("title")}
        for n in m.get("nodes") or []:
            if not isinstance(n, dict):
                continue
            label = _clean(n.get("label"))
            state = _FROM_MAP.get(n.get("state"))
            if not label or state is None:
                continue
            key = (track.lower(), label.lower())
            local[str(n.get("id"))] = key
            sk = skills.get(key)
            if sk is None:
                if len(skills) >= MAX_SKILLS:
                    continue
                sk = skills[key] = _Skill(track, label, len(skills))
            taught_here = state != "not_started" or (src["current"] and str(n.get("id")) in src["taught"])
            if taught_here:
                sk.is_next_topic = False
            elif label.lower() in topics and sk.goal is None:
                sk.goal = _clean(topics[label.lower()].get("goal"), 120) or None
            at = src["at"]
            if _RANK[state] > _RANK[sk.state]:
                sk.state = state
                sk.detail = _clean(n.get("detail"), 120)
            if state == "mastered" and at is not None:
                sk.mastered_at = at if sk.mastered_at is None else min(sk.mastered_at, at)
            if state in ("mastered", "practicing") and at is not None:
                sk.last = at if sk.last is None else max(sk.last, at)
            if taught_here and isinstance(src.get("lessonId"), str):
                ref = sk.lessons.setdefault(src["lessonId"], {"lessonId": src["lessonId"], "role": "teaches"})
                if src.get("libraryId"):
                    ref["libraryId"] = src["libraryId"]
                if src.get("title") and isinstance(src["title"], str):
                    ref["title"] = _clean(src["title"], 120)
            if src["current"] and str(n.get("id")) in src["taught"]:
                step_ids = src["taught"][str(n.get("id"))]
                done = [s for s in step_ids if s in src["passed"]]
                if step_ids:
                    sk.total, sk.done = len(step_ids), len(done)
                    ref = sk.lessons.get(src["lessonId"]) if isinstance(src.get("lessonId"), str) else None
                    if ref is not None:
                        ref["stepIds"] = list(step_ids)
                    if done and sk.state == "not_started":
                        sk.state = "practicing"  # steps passed, not all of them yet: practicing, not still "next"
                        if at is not None:
                            sk.last = at if sk.last is None else max(sk.last, at)
                    if ref is not None and sk.state != "mastered" and src["stepIndex"] is not None:
                        ref["_current"] = {"stepIndex": src["stepIndex"], "stepCount": src["stepCount"]}
        for e in m.get("edges") or []:
            if isinstance(e, dict) and e.get("from") in local and e.get("to") in local:
                requires.append((local[e["from"]], local[e["to"]]))
        for c in m.get("cross") or []:
            if isinstance(c, dict) and c.get("to") in local and c.get("track") and c.get("label"):
                cross.append(((_clean(c["track"], 80).lower(), _clean(c["label"]).lower()), local[c["to"]]))
    return skills, requires, cross


def _reaches(adj: dict[Any, set], start: Any, goal: Any) -> bool:
    seen, stack = set(), [start]
    while stack:
        n = stack.pop()
        if n == goal:
            return True
        if n in seen:
            continue
        seen.add(n)
        stack.extend(adj.get(n, ()))
    return False


# ------------------------------------------------------------------------------------------------ the graph
def build_graph(history: list[dict], current: dict | None = None, current_graph: dict | None = None, *,
                index: dict[str, str] | None = None, review_rows: list[dict] | None = None,
                prefs: dict | None = None, activity: list[float] | None = None, now: float | None = None,
                tz: tzinfo | None = None) -> dict | None:
    """SkillGraphInfo from data already read (pure). None when no skill is known yet.

    history: store.completed(); current / current_graph: store.load() / load_graph(); index: lesson.id -> library id;
    review_rows: review.items(...) (skillId, label, track, dueAt, lastResult?, lastAt?); prefs: load_prefs();
    activity: extra epoch seconds the learner worked on (mastery.json); now / tz: the clock."""
    now = time.time() if now is None else float(now)
    prefs = prefs or {}
    from . import progress

    finished = progress.finished_at([e for e in history or [] if isinstance(e, dict)])
    if isinstance(current, dict) and progress.superseded(current, finished, is_current=True):
        current = None
    skills, req_pairs, cross_pairs = _merge(_sources(history, current, current_graph, index or {}))
    if not skills:
        return None

    # ids, in first-seen order within each track
    taken: set[str] = set()
    for sk in sorted(skills.values(), key=lambda s: s.order):
        base = skill_id(sk.track, sk.label)
        sid, k = base, 2
        while sid in taken:
            sid, k = f"{base}-{k}", k + 1
        taken.add(sid)
        sk.id = sid
    by_id = {sk.id: sk for sk in skills.values()}
    key_id = {k: sk.id for k, sk in skills.items()}

    # requires (no loops), then helps
    req: dict[str, set[str]] = {}
    edges: list[dict] = []
    for a, b in req_pairs:
        fa, fb = key_id.get(a), key_id.get(b)
        if not fa or not fb or fa == fb or fa in req.get(fb, ()):
            continue
        if _reaches(_children(req), fb, fa):
            continue  # fb already leads to fa: this edge would close a loop
        req.setdefault(fb, set()).add(fa)
        edges.append({"from": fa, "to": fb, "kind": "requires"})
    helps_seen: set[tuple[str, str]] = set()
    for a, b in cross_pairs:
        fa, fb = key_id.get(a), key_id.get(b)
        if fa and fb and fa != fb and (fa, fb) not in helps_seen and fa not in req.get(fb, ()) and skills_track(by_id, fa) != skills_track(by_id, fb):
            helps_seen.add((fa, fb))
            edges.append({"from": fa, "to": fb, "kind": "helps", "weight": 0.5})

    # states from prerequisites
    ordered = sorted(skills.values(), key=lambda s: s.order)
    state: dict[str, str] = {}
    for sk in ordered:
        if sk.state == "mastered":
            state[sk.id] = MASTERED
        elif sk.state == "practicing":
            state[sk.id] = PRACTICING
    for sk in ordered:
        if sk.id not in state:
            state[sk.id] = READY if all(state.get(r) == MASTERED for r in req.get(sk.id, ())) else LOCKED

    # review schedule
    due_at: dict[str, float] = {}
    from .review import skill_key as _rk

    rows_by_key = {_rk(r.get("track", ""), r.get("label", "")): r for r in review_rows or [] if isinstance(r, dict)}
    for sk in ordered:
        r = rows_by_key.get(_rk(sk.track, sk.label))
        if r and _num(r.get("dueAt")) is not None and state[sk.id] == MASTERED:
            due_at[sk.id] = float(r["dueAt"])

    # tracks and capstones
    track_order: list[str] = []
    members: dict[str, list[_Skill]] = {}
    for sk in ordered:
        if sk.track.lower() not in members:
            track_order.append(sk.track.lower())
            members[sk.track.lower()] = []
        members[sk.track.lower()].append(sk)
    cap_for_track: dict[str, str] = {}
    cap_nodes: list[dict] = []
    caps: list[dict] = []
    for tk in track_order:
        mem = members[tk]
        track = mem[0].track
        cid, k = f"{slug(track)}.capstone", 2
        while cid in taken:
            cid, k = f"{slug(track)}.capstone-{k}", k + 1
        taken.add(cid)
        cap_for_track[tk] = cid
        ids = [m.id for m in mem]
        all_done = all(state[i] == MASTERED for i in ids)
        started = any(state[i] in (MASTERED, PRACTICING) for i in ids)
        done_at = max((by_id[i].mastered_at or 0 for i in ids), default=0) if all_done else 0
        cstate = MASTERED if all_done else PRACTICING if started else LOCKED
        label = f"{track} project"
        cap_nodes.append({"id": cid, "label": label, "track": track, "kind": "capstone", "state": cstate,
                          "summary": f"Use what you learned in {track} on one small project."})
        cap = {"id": cid, "brief": f"Put your {track} skills to work on one small project.", "requires": ids}
        if all_done and done_at:
            cap["completedAt"] = done_at
        caps.append(cap)
        leaves = [i for i in ids if not any(i in req.get(j, ()) for j in ids)]  # the track's last skills lead to it
        for i in leaves:
            edges.append({"from": i, "to": cid, "kind": "requires"})

    out_skills: list[dict] = []
    for sk in ordered:
        row: dict[str, Any] = {"id": sk.id, "label": sk.label, "track": sk.track, "kind": "skill", "state": state[sk.id]}
        if sk.detail and len(sk.detail.split()) <= 14:
            row["summary"] = sk.detail
        if sk.total and sk.done:
            row["evidence"] = {"done": sk.done, "total": sk.total}
        if state[sk.id] == MASTERED and sk.mastered_at is not None:
            row["masteredAt"] = sk.mastered_at
        if sk.last is not None:
            row["lastPracticedAt"] = sk.last
        if sk.id in due_at:
            row["review"] = {"dueAt": due_at[sk.id]}
        refs = [{k2: v for k2, v in ref.items() if not k2.startswith("_")} for ref in sk.lessons.values()]
        if refs:
            row["lessons"] = refs
        out_skills.append(row)
    out_skills += cap_nodes

    # goal
    cap_ids = {c["id"] for c in caps}
    done_caps = {c["id"] for c in caps if c.get("completedAt") or all(state[i] == MASTERED for i in c["requires"])}
    goal = prefs.get("goal") if prefs.get("goal") in cap_ids else None
    if goal is None:
        best: tuple | None = None
        for n, tk in enumerate(track_order):
            cid = cap_for_track[tk]
            if cid in done_caps:
                continue
            ids = [m.id for m in members[tk]]
            frac = sum(state[i] == MASTERED for i in ids) / len(ids)
            recent = max((by_id[i].last or 0 for i in ids), default=0)
            rank = (frac, recent, -n)
            if best is None or rank > best[0]:
                best = (rank, cid)
        goal = best[1] if best else None
    goal_cap = next((c for c in caps if c["id"] == goal), None)

    # the path to the goal: the capstone's skills and everything upstream of them (requires only)
    path: list[str] = []
    if goal_cap:
        seen: set[str] = set()
        stack = list(goal_cap["requires"])
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            stack.extend(req.get(i, ()))
        depth = _depths(req, seen)
        path = sorted(seen, key=lambda i: (depth[i], by_id[i].order))

    nxt = None
    pick = next((i for want in PRACTICE_ORDER for i in path if state[i] == want), None)
    if pick is not None:
        nxt = _pick(by_id[pick], state[pick], goal_cap, caps, cap_nodes)

    also: list[str] = []
    for i in [*path, *[s.id for s in ordered]]:
        if len(also) >= MAX_ALSO_READY:
            break
        if i != pick and state[i] == READY and i not in also:
            also.append(i)

    fresh = sorted((i for i in due_at if due_at[i] <= now + KEEP_FRESH_WITHIN_S), key=lambda i: (due_at[i], by_id[i].order))[:MAX_KEEP_FRESH]

    # events
    acked = moment(prefs.get("ackedUntil"))
    if acked is None:
        acked = now - UNSEEN_WINDOW_S
    events: list[dict] = []
    for sk in ordered:
        if state[sk.id] == MASTERED and sk.mastered_at is not None and sk.mastered_at > acked:
            ev: dict[str, Any] = {"id": f"mastered:{sk.id}", "kind": "mastered", "skillId": sk.id, "at": sk.mastered_at}
            if (lid := next(iter(sk.lessons), None)) is not None:
                ev["lessonId"] = lid
            events.append(ev)
        elif state[sk.id] == READY and req.get(sk.id):
            ups = [(by_id[r].mastered_at or 0, r) for r in req[sk.id]]
            at, frm = max(ups)
            if at > acked:
                events.append({"id": f"unlocked:{sk.id}", "kind": "unlocked", "skillId": sk.id, "at": at, "from": frm})
    for c in caps:
        if c.get("completedAt") and c["completedAt"] > acked:
            events.append({"id": f"capstone_done:{c['id']}", "kind": "capstone_done", "skillId": c["id"], "at": c["completedAt"]})
    events.sort(key=lambda e: (e["at"], e["id"]))
    events = events[-MAX_EVENTS:]

    # week (the learner's local calendar week, Monday first)
    week = _week(ordered, state, activity or [], history, review_rows or [], goal_cap, now, tz, [sk.last for sk in ordered],
                 [c.get("completedAt") for c in caps])

    portfolio = [{"capstoneId": c["id"], "title": next(n["label"] for n in cap_nodes if n["id"] == c["id"]), "at": c["completedAt"],
                  "track": next(n["track"] for n in cap_nodes if n["id"] == c["id"]), "skillIds": c["requires"]}
                 for c in caps if c.get("completedAt")]

    out: dict[str, Any] = {"skills": out_skills, "edges": edges, "capstones": caps, "goal": goal, "alsoReady": also,
                           "keepFresh": fresh, "events": events, "ackedUntil": acked, "week": week, "portfolio": portfolio}
    if nxt:
        out["next"] = nxt
    return out


def skills_track(by_id: dict[str, _Skill], i: str) -> str:
    return by_id[i].track.lower()


def _children(req: dict[str, set[str]]) -> dict[str, set[str]]:
    """requires (to -> its prerequisites) turned around: skill -> the skills that require it."""
    out: dict[str, set[str]] = {}
    for to, froms in req.items():
        for f in froms:
            out.setdefault(f, set()).add(to)
    return out


def _depths(req: dict[str, set[str]], ids: set[str]) -> dict[str, int]:
    memo: dict[str, int] = {}

    def d(i: str, seen: frozenset = frozenset()) -> int:
        if i in memo:
            return memo[i]
        ups = [u for u in req.get(i, ()) if u in ids and u not in seen]
        memo[i] = 0 if not ups else 1 + max(d(u, seen | {i}) for u in ups)
        return memo[i]

    return {i: d(i) for i in ids}


def _pick(sk: _Skill, state: str, goal_cap: dict | None, caps: list[dict], cap_nodes: list[dict]) -> dict:
    """SkillPick for `sk`: the lesson in progress that teaches it (with its step), else a lesson that taught it, else a goal."""
    out: dict[str, Any] = {"skillId": sk.id}
    ref = next((r for r in sk.lessons.values() if "_current" in r), None) or next(iter(sk.lessons.values()), None)
    if ref:
        out["lessonId"] = ref["lessonId"]
        if ref.get("libraryId"):
            out["libraryId"] = ref["libraryId"]
        if ref.get("title"):
            out["lessonTitle"] = ref["title"]
        cur = ref.get("_current")
        if cur:
            if isinstance(cur.get("stepIndex"), int) and not isinstance(cur["stepIndex"], bool):
                out["stepIndex"] = cur["stepIndex"]
            if isinstance(cur.get("stepCount"), int) and not isinstance(cur["stepCount"], bool):
                out["stepCount"] = cur["stepCount"]
    else:
        out["goal"] = sk.goal or f"{sk.label} in {sk.track}"
    if state == PRACTICING:
        why = "You are partway through this one."
    elif goal_cap:
        title = next((n["label"] for n in cap_nodes if n["id"] == goal_cap["id"]), "your goal")
        why = _short(f"The next step toward {title}.", 12)
    else:
        why = "Ready for you now."
    out["why"] = why
    return out


def _short(text: str, words: int) -> str:
    w = text.split()
    return text if len(w) <= words else " ".join(w[:words]).rstrip(".,;:") + "."


def _week(ordered: list[_Skill], state: dict[str, str], activity: list[float], history: list[dict], review_rows: list[dict],
          goal_cap: dict | None, now: float, tz: tzinfo | None, lasts: list, cap_done: list) -> dict:
    today = datetime.fromtimestamp(now, tz).date()
    monday = today - timedelta(days=today.weekday())
    days = [False] * 7
    minutes = 0
    known = False

    def day_of(t: Any) -> int | None:
        if (n := _num(t)) is None:
            return None
        d = (datetime.fromtimestamp(n, tz).date() - monday).days
        return d if 0 <= d < 7 else None

    for t in [*activity, *lasts, *cap_done, *[e.get("finishedAt") for e in history if isinstance(e, dict)],
              *[r.get("lastAt") for r in review_rows if isinstance(r, dict)]]:
        if (d := day_of(t)) is not None:
            days[d] = True
    for e in history:
        if isinstance(e, dict) and day_of(e.get("finishedAt")) is not None and isinstance(e.get("result"), dict):
            m = e["result"].get("minutes")
            if isinstance(m, int) and not isinstance(m, bool) and m >= 0:
                minutes += m
                known = True
    out: dict[str, Any] = {
        "mastered": sum(1 for sk in ordered if state[sk.id] == MASTERED and day_of(sk.mastered_at) is not None),
        "keptFresh": sum(1 for r in review_rows if isinstance(r, dict) and r.get("lastResult") == "passed" and day_of(r.get("lastAt")) is not None),
        "days": days}
    if known:
        out["minutes"] = minutes
    if goal_cap:
        out["goalAway"] = sum(1 for i in goal_cap["requires"] if state[i] != MASTERED)
    return out


# ------------------------------------------------------------------------------------------------ from what is saved
def graph(now: float | None = None, tz: tzinfo | None = None) -> dict | None:
    """Progress.graph from the state on this Mac. None when nothing is known yet or the state cannot be read."""
    now = time.time() if now is None else float(now)
    try:
        history = store.completed()
        current = store.load()
        cur_graph = store.load_graph(current) if current is not None else None
    except Exception as e:  # noqa: BLE001
        log.warning("skills graph: could not read the saved state: %s", e)
        return None
    index: dict[str, str] = {}
    try:
        from server.lesson import library

        index = library.index_by_lesson_id()
    except Exception as e:  # noqa: BLE001 - linking to the library is a nicety
        log.debug("skills graph: no library index: %s", e)
    rows: list[dict] = []
    try:
        from . import review

        rows = review.items(history, review.load_state(), now, tz)
    except Exception as e:  # noqa: BLE001
        log.debug("skills graph: no review schedule: %s", e)
    activity: list[float] = []
    try:
        from . import mastery

        activity = [t for t in (_num(e.get("at")) for e in mastery.entries()) if t is not None]
    except Exception as e:  # noqa: BLE001
        log.debug("skills graph: no practice log: %s", e)
    try:
        return build_graph(history, current, cur_graph, index=index, review_rows=rows, prefs=load_prefs(), activity=activity,
                           now=now, tz=tz)
    except Exception as e:  # noqa: BLE001 - the Skills page falls back to the tracks; progress still answers
        log.warning("skills graph: could not build: %s", e)
        return None
