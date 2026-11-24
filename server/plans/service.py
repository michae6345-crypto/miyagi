"""The plans messages of the ui-v4 contract (shared/contracts/events.py, UI-V4.md section 3), answered beside the
lesson queue. The payloads arrive parsed by the contract (main.parse_command -> parse_app_message).

  plans.list {}                         -> plans {items: PlanState[], reqId?}
  plan.start {catalogId | playlistId+url+proposal | goal+proposal, reqId?} -> plans
  plan.remove {id}                      -> plans
  playlist.get {url, reqId?}            -> playlist (twice: the videos with proposing: true, then the proposal)
  plan.propose {goal, tool?, reqId?}    -> plan.proposal (twice: proposing: true, then the proposal)

A plan lesson starts through learn / learn_url / library.start carrying plan {id, index} (orchestrator/main.py).
Every reply echoes the command's reqId. A lookup that fails says why in `error` (LookupError_); a plan.start that
cannot add the plan answers `error {message, reqId}`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from . import catalog, progress
from . import playlist as pl_mod
from . import proposal as prop

log = logging.getLogger("plans")

COMMANDS = ("plans.list", "plan.start", "plan.remove", "playlist.get", "plan.propose")

PLAN_NOT_FOUND = "That plan is not in the catalog on this Mac."
PLAN_START_WHAT = "Pick a plan, a playlist or a goal to add."
LOOKUP_ERRORS = {"bad_url": "unsupported", "not_found": "not_found", "offline": "offline"}


def _rid(p: Any) -> dict:
    rid = getattr(p, "reqId", None)
    return {"reqId": rid} if isinstance(rid, str) and rid else {}


def plans_payload(req: dict | None = None) -> dict:
    """`plans`: every plan in progress on this Mac (PlanState), the most recently used first."""
    return {"items": progress.all_views(), **(req or {})}


async def handle(type_: str, p: Any, reply: Any, *, allow_model: bool = True) -> None:
    """One plans command. Blocking file work runs in a thread."""
    req = _rid(p)
    if type_ == "plans.list":
        await reply("plans", await asyncio.to_thread(plans_payload, req))
    elif type_ == "plan.remove":
        if isinstance(p.id, str) and progress.KEY_RE.fullmatch(p.id):
            await asyncio.to_thread(progress.remove, p.id)
        await reply("plans", await asyncio.to_thread(plans_payload, req))
    elif type_ == "plan.start":
        if await _start(p, reply, req):
            await reply("plans", await asyncio.to_thread(plans_payload, req))
    elif type_ == "playlist.get":
        await _playlist(p, reply, req)
    elif type_ == "plan.propose":
        await _propose(p, reply, req, allow_model=allow_model)


async def _start(p: Any, reply: Any, req: dict) -> bool:
    """Add the plan. False when it could not be added (the error is already said)."""
    async def fail(message: str) -> bool:
        await reply("error", {"message": message, **req})
        return False

    if p.catalogId:
        try:
            await asyncio.to_thread(progress.start_catalog, p.catalogId)
        except KeyError:
            return await fail(PLAN_NOT_FOUND)
        return True
    plid = p.playlistId or (pl_mod.playlist_id(p.url) if p.url else None)
    if plid:
        if not catalog.PLAYLIST_ID_RE.fullmatch(plid):
            return await fail("That is not a YouTube playlist link.")
        lessons, skipped = prop.accepted_lessons(p.proposal) if p.proposal is not None else ([], set())
        lessons = [le for le in lessons if le.get("videoId")]
        title, channel = getattr(p.proposal, "title", "") or "", ""
        if not lessons:  # no proposal: the playlist's own videos (shipped list or cache; else one fetch)
            try:
                pl = await pl_mod.list_videos(plid)
            except pl_mod.PlaylistUnavailable as e:
                return await fail(str(e))
            lessons, skipped, title, channel = pl_mod.lessons_from(pl), set(), pl.get("title") or "", pl.get("channel") or ""
        await asyncio.to_thread(lambda: progress.start_playlist(
            plid, lessons, title=title, channel=channel, url=p.url or None, tool=prop.tool_of(p.proposal),
            project=prop.project_of(p.proposal), skipped=skipped))
        return True
    goal = " ".join((p.goal or "").split())
    if p.proposal is not None or goal:
        proposal = p.proposal
        if proposal is None:  # a goal with no proposal: make one (keywords first, as plan.propose)
            done = await asyncio.to_thread(progress.done_plan_ids)
            have = await asyncio.to_thread(progress.skills_done)
            got = await prop.from_goal(goal, done=done, have=have)
            if got is None:
                return await fail("No plan fits that goal yet. Try saying it another way.")
            from shared.contracts.events import PlanProposal

            proposal = PlanProposal.model_validate(got)
        lessons, skipped = prop.accepted_lessons(proposal)
        if not lessons:
            return await fail(PLAN_START_WHAT)
        await asyncio.to_thread(lambda: progress.start_goal(
            goal or proposal.title, lessons, title=proposal.title, tool=prop.tool_of(proposal),
            project=prop.project_of(proposal), skipped=skipped))
        return True
    return await fail(PLAN_START_WHAT)


async def _playlist(p: Any, reply: Any, req: dict) -> None:
    base = {"url": p.url, **req}
    try:
        pl = await pl_mod.list_videos(p.url)
    except pl_mod.PlaylistUnavailable as e:
        await reply("playlist", {**base, "proposing": False, "error": LOOKUP_ERRORS.get(e.reason, "unknown")})
        return
    except Exception:  # noqa: BLE001 - said, not dropped
        log.exception("playlist.get failed")
        await reply("playlist", {**base, "proposing": False, "error": "unknown"})
        return
    info = {**base, "playlistId": pl["playlistId"], "title": pl.get("title") or None, "channel": pl.get("channel") or None,
            "videoCount": pl["videoCount"], "totalSeconds": pl.get("totalSeconds"), "videos": pl["videos"]}
    info = {k: v for k, v in info.items() if v is not None}
    await reply("playlist", {**info, "proposing": True})
    have = await asyncio.to_thread(progress.skills_done)
    await reply("playlist", {**info, "proposing": False, "proposal": prop.from_playlist(pl, have=have)})


async def _propose(p: Any, reply: Any, req: dict, *, allow_model: bool) -> None:
    goal = " ".join((p.goal or "").split())
    base = {"goal": goal, **req}
    await reply("plan.proposal", {**base, "proposing": True})
    try:
        done = await asyncio.to_thread(progress.done_plan_ids)
        have = await asyncio.to_thread(progress.skills_done)
        got = await prop.from_goal(goal, getattr(p, "tool", None), done=done, have=have, allow_model=allow_model)
    except Exception:  # noqa: BLE001 - said, not dropped
        log.exception("plan.propose failed")
        await reply("plan.proposal", {**base, "proposing": False, "error": "unknown"})
        return
    if got is None:
        await reply("plan.proposal", {**base, "proposing": False, "error": "not_found"})
    else:
        await reply("plan.proposal", {**base, "proposing": False, "proposal": got})
