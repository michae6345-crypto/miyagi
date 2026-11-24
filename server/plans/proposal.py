"""Plan proposals (ui-v4 contract PlanProposal): what a playlist or a goal would become as a plan, before the learner
accepts it with plan.start.

from_playlist() is deterministic and free: the playlist's catalog plan (shipped playlists name it; otherwise the
playlist title matched like a goal, keywords only) gives the tool, skills and project, and each video takes the skills
of the catalog lesson its title matches best. from_goal() uses goal.suggest (keywords first; one guarded model call only
when nothing matches clearly, and only to pick catalog ids) and builds the lessons from catalog lessons, the plans to
finish first included, each saying where it came from. Lessons whose skills the learner already has are left out.
"""

from __future__ import annotations

from typing import Any

from . import catalog
from . import goal as goal_mod
from .playlist import video_minutes

MAX_CHAIN = 3  # plans in one goal proposal (the top plan and what it needs first)


def _skill_labels(plans: list[dict]) -> dict[str, str]:
    return {s["id"]: s["label"] for p in plans for s in p["skills"]}


def _skills_used(plans: list[dict], ids: set[str]) -> list[dict]:
    seen: dict[str, dict] = {}
    for p in plans:
        for s in p["skills"]:
            if s["id"] in ids and s["id"] not in seen:
                seen[s["id"]] = {"id": s["id"], "label": s["label"], "needs": list(s["needs"])}
    return list(seen.values())


def _have(skills: list[dict], have: set[str]) -> dict | None:
    return {"done": sum(1 for s in skills if s["id"] in have), "of": len(skills)} if skills else None


def _project(plan: dict) -> dict | None:
    pr = plan.get("project") or {}
    return {"title": pr["title"], "brief": pr.get("brief") or "", "checks": list(pr.get("checks") or [])} \
        if pr.get("title") else None


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def playlist_plan(pl: dict) -> dict | None:
    """The catalog plan a playlist teaches: the one it was picked for, else a confident keyword match on its title."""
    if pl.get("planId") and catalog.get(pl["planId"]):
        return catalog.get(pl["planId"])
    m = goal_mod.match(f"{pl.get('title') or ''} {pl.get('channel') or ''}")
    return catalog.get(m["matches"][0]["planId"]) if m["confident"] and m["matches"] else None


def _best_lesson(title: str, plan: dict) -> dict | None:
    terms = goal_mod._terms(title)
    best, score = None, 0
    for le in plan["lessons"]:
        s = len(terms & goal_mod._terms(le["title"])) * 2 + len(terms & goal_mod._terms(le["goal"]))
        if s > score:
            best, score = le, s
    return best


def from_playlist(pl: dict, *, have: set[str] | frozenset[str] = frozenset()) -> dict:
    """A PlanProposal for a playlist (playlist.list_videos' output): one lesson per video, in order."""
    plan = playlist_plan(pl)
    labels = _skill_labels([plan]) if plan else {}
    lessons, grown = [], set()
    for v in pl["videos"]:
        le = _clean({"title": v["title"], "videoId": v["id"], "seconds": v.get("seconds"),
                     "minutes": video_minutes(v.get("seconds"))})
        match = _best_lesson(v["title"], plan) if plan else None
        if match and match["grows"]:
            le["grows"] = list(match["grows"])
            le["skills"] = [labels.get(g, g) for g in match["grows"]]
            grown.update(match["grows"])
        lessons.append(le)
    skills = _skills_used([plan], grown) if plan else []
    mins = [le["minutes"] for le in lessons if isinstance(le.get("minutes"), int)]
    return _clean({
        "title": pl.get("title") or "Playlist", "source": "playlist",
        "tool": dict(plan["tool"]) if plan and plan["tool"].get("id") else None,
        "lessons": lessons, "skills": skills or None, "project": _project(plan) if plan else None,
        "minutes": sum(mins) if mins else None, "fromPlans": [plan["id"]] if plan else None,
        "have": _have(skills, set(have)),
    })


def _chain(plan_id: str, done: set[str] | frozenset[str]) -> list[str]:
    """plan_id with the plans it needs first that are not done, prerequisites first, at most MAX_CHAIN."""
    out: list[str] = []

    def walk(pid: str, depth: int) -> None:
        plan = catalog.get(pid)
        if plan is None or pid in out:
            return
        if depth < MAX_CHAIN:
            for n in plan["needs"]:
                if n not in done:
                    walk(n, depth + 1)
        if pid not in out:
            out.append(pid)

    walk(plan_id, 0)
    return out[-MAX_CHAIN:]


async def from_goal(goal: str, tool: str | None = None, *, done: set[str] | frozenset[str] = frozenset(),
                    have: set[str] | frozenset[str] = frozenset(), allow_model: bool = True) -> dict | None:
    """A PlanProposal for a goal, from catalog lessons; None when no catalog plan fits."""
    out = await goal_mod.suggest(goal, done=done, allow_model=allow_model)
    matches = [m for m in out["matches"] if catalog.get(m["planId"])]
    if tool:
        matches.sort(key=lambda m: catalog.get(m["planId"])["tool"].get("id") != tool)
    if not matches:
        return None
    top = catalog.get(matches[0]["planId"])
    chain = [catalog.get(pid) for pid in _chain(top["id"], done)]
    labels = _skill_labels(chain)
    have = set(have)
    lessons, grown = [], set()
    for plan in chain:
        for i, le in enumerate(plan["lessons"]):
            if le["grows"] and all(g in have for g in le["grows"]):
                continue  # a lesson the learner would not need
            lessons.append(_clean({"title": le["title"], "goal": le["goal"], "minutes": le.get("minutes"),
                                   "grows": list(le["grows"]), "skills": [labels.get(g, g) for g in le["grows"]],
                                   "from": {"planId": plan["id"], "index": i}}))
            grown.update(le["grows"])
    if not lessons:  # every skill is had: the top plan's lessons all the same (the learner asked for it)
        return _whole_plan(top, labels)
    tools: list[dict] = []
    for m in matches:
        t = catalog.get(m["planId"])["tool"]
        if t.get("id") and t["id"] not in [x["id"] for x in tools]:
            tools.append(dict(t))
    skills = _skills_used(chain, grown)
    mins = [le["minutes"] for le in lessons if isinstance(le.get("minutes"), int)]
    return _clean({
        "title": top["title"], "source": "goal", "tool": dict(top["tool"]) if top["tool"].get("id") else None,
        "tools": tools or None, "lessons": lessons, "skills": skills or None, "project": _project(top),
        "minutes": sum(mins) if mins else None, "fromPlans": [p["id"] for p in chain], "have": _have(skills, have),
        "note": f"Built from {len(chain)} plans." if len(chain) > 1 else None,
    })


def _whole_plan(plan: dict, labels: dict[str, str]) -> dict:
    lessons = [_clean({"title": le["title"], "goal": le["goal"], "minutes": le.get("minutes"), "grows": list(le["grows"]),
                       "skills": [labels.get(g, g) for g in le["grows"]], "from": {"planId": plan["id"], "index": i}})
               for i, le in enumerate(plan["lessons"])]
    return _clean({"title": plan["title"], "source": "goal", "tool": dict(plan["tool"]) if plan["tool"].get("id") else None,
                   "lessons": lessons, "project": _project(plan), "fromPlans": [plan["id"]],
                   "minutes": sum(le.get("minutes") or 0 for le in lessons) or None})


def accepted_lessons(proposal: Any) -> tuple[list[dict], set[int]]:
    """A proposal the learner accepted (the contract model or a dict) as plan lessons, and the indices they skipped."""
    raw = proposal.model_dump(by_alias=True) if hasattr(proposal, "model_dump") else dict(proposal or {})
    lessons, skipped = [], set()
    for le in raw.get("lessons") or []:
        if not isinstance(le, dict) or not isinstance(le.get("title"), str) or not le["title"].strip():
            continue
        vid = le.get("videoId")
        row = _clean({
            "title": " ".join(le["title"].split())[:200],
            "goal": " ".join(le["goal"].split())[:400] if isinstance(le.get("goal"), str) and le["goal"].strip() else None,
            "videoId": vid if isinstance(vid, str) and catalog.VIDEO_ID_RE.fullmatch(vid) else None,
            "seconds": _pos_int(le.get("seconds")), "minutes": _pos_int(le.get("minutes"), 600),
            "grows": [g for g in le.get("grows") or [] if isinstance(g, str)][:12] or None,
            "from": le["from"] if isinstance(le.get("from"), dict) else None,
        })
        if "goal" not in row and "videoId" not in row:
            continue  # nothing to build it from
        if le.get("skip") is True:
            skipped.add(len(lessons))
        lessons.append(row)
    return lessons, skipped


def _pos_int(v: Any, limit: int = 10 ** 6) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= limit else None


def tool_of(proposal: Any) -> dict | None:
    t = getattr(proposal, "tool", None)
    return {"id": t.id, "label": t.label} if t is not None and t.id else None


def project_of(proposal: Any) -> dict | None:
    pr = getattr(proposal, "project", None)
    return {"title": pr.title, "brief": pr.brief, "checks": list(pr.checks)} if pr is not None and pr.title else None
