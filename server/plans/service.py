"""The plans messages: App -> Engine commands and their replies (the orchestrator's dispatch calls into here).

Reads and edits are answered at once, beside the lesson queue (READS). plan.lesson.start starts a lesson, so it queues
like any lesson start (orchestrator/main.py Engine.plan_lesson_start).

Names follow the ui-v4 contract. Until shared/contracts/events.py carries them, parse() validates the payloads here
(the same fallback main.parse_command uses for the v2 commands).
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

from . import catalog, progress
from . import goal as goal_mod
from . import playlist as pl_mod

log = logging.getLogger("plans")

READS = ("plans.list", "plan.get", "plans.progress.get", "plan.start", "plan.goal", "plan.playlist",
         "plan.lesson.done", "plan.remove")
STARTS = ("plan.lesson.start",)
COMMANDS = READS + STARTS

PLAN_NOT_FOUND = "That plan is not on this Mac any more."
GOAL_EMPTY = "Say what you want to learn or make."


def _key(v: Any) -> str:
    if not isinstance(v, str) or not progress.KEY_RE.fullmatch(v.strip()):
        raise ValueError("not a plan id")
    return v.strip()


def _index(v: Any, *, optional: bool = False) -> int | None:
    if v is None and optional:
        return None
    if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < 1000:
        raise ValueError("index must be a lesson number")
    return v


def _text(v: Any, limit: int) -> str:
    return " ".join(v.split())[:limit] if isinstance(v, str) else ""


def parse(type_: str, payload: Any) -> SimpleNamespace:
    """The command's payload, checked. Raises ValueError (the engine answers `error`)."""
    p = payload if isinstance(payload, dict) else {}
    if type_ in ("plans.list", "plans.progress.get"):
        return SimpleNamespace()
    if type_ in ("plan.get", "plan.remove"):
        return SimpleNamespace(id=_key(p.get("id")))
    if type_ == "plan.start":  # a catalog plan or a playlist plan ("yt-<id>"), or a playlist link
        url = _text(p.get("url"), 500)
        if url:
            if not pl_mod.playlist_id(url):
                raise ValueError("plan.start: not a playlist link")
            return SimpleNamespace(id=None, url=url, goal=_text(p.get("goal"), goal_mod.MAX_GOAL_CHARS))
        return SimpleNamespace(id=_key(p.get("id")), url=None, goal=_text(p.get("goal"), goal_mod.MAX_GOAL_CHARS))
    if type_ == "plan.goal":
        return SimpleNamespace(text=_text(p.get("text"), goal_mod.MAX_GOAL_CHARS))
    if type_ == "plan.playlist":
        url = _text(p.get("url"), 500)
        if not url:
            raise ValueError("plan.playlist: url is required")
        return SimpleNamespace(url=url, refresh=p.get("refresh") is True)
    if type_ == "plan.lesson.done":
        return SimpleNamespace(id=_key(p.get("id")), index=_index(p.get("index")), done=p.get("done") is not False)
    if type_ == "plan.lesson.start":
        return SimpleNamespace(id=_key(p.get("id")), index=_index(p.get("index"), optional=True))
    raise ValueError(f"unknown plans command {type_}")


def _progress_by_plan() -> dict[str, dict]:
    return {v["key"]: v for v in progress.all_views()}


def plans_payload() -> dict:
    """`plans`: the catalog as rows, each with the learner's progress on it when started."""
    by_key = _progress_by_plan()
    rows = []
    for plan in catalog.plans():
        row = catalog.summary(plan)
        v = by_key.get(plan["id"])
        if v:
            row["progress"] = {"done": v["done"], "total": v["total"], "active": v["active"], "complete": v["complete"]}
        rows.append(row)
    playlists = [_row_progress(v) for v in by_key.values() if v["kind"] == "playlist"]
    return {"plans": rows, "playlists": playlists}


def _row_progress(v: dict) -> dict:
    return {"id": v["key"], "title": v["title"], "channel": v.get("channel", ""), "done": v["done"],
            "total": v["total"], "active": v["active"], "complete": v["complete"]}


def plan_payload(key: str) -> dict | None:
    """`plan`: a catalog plan with its lessons, skills, playlists and progress; or a playlist plan's progress."""
    plan = catalog.get(key)
    if plan is not None:
        return {"id": key, "kind": "catalog", "plan": catalog.detail(plan), "progress": progress.view(key),
                "playlists": [_playlist_row(p) for p in catalog.playlists(key)]}
    v = progress.view(key)
    if v is None:
        return None
    return {"id": key, "kind": "playlist", "plan": None, "progress": v, "playlists": []}


def _playlist_row(p: dict) -> dict:
    secs = [v["seconds"] for v in p["videos"] if isinstance(v.get("seconds"), int)]
    return {"playlistId": p["playlistId"], "title": p["title"], "channel": p["channel"], "url": p["url"],
            "videoCount": len(p["videos"]), "totalSeconds": sum(secs) if len(secs) == len(p["videos"]) else None}


def progress_payload() -> dict:
    """`plans.progress`: every plan in progress, and the one Continue resumes."""
    views = progress.all_views()
    active = next((v for v in views if v["active"] and not v["complete"]), None)
    return {"plans": views, "resume": active or next((v for v in views if not v["complete"]), None)}


async def handle(type_: str, p: SimpleNamespace, reply: Any, *, allow_model: bool = True) -> None:
    """One read or edit. Blocking file work runs in a thread. Failures the learner should see go out as `error`."""
    if type_ == "plans.list":
        await reply("plans", await asyncio.to_thread(plans_payload))
    elif type_ == "plan.get":
        got = await asyncio.to_thread(plan_payload, p.id)
        if got is None:
            await reply("error", {"message": PLAN_NOT_FOUND})
        else:
            await reply("plan", got)
    elif type_ == "plans.progress.get":
        await reply("plans.progress", await asyncio.to_thread(progress_payload))
    elif type_ == "plan.start":
        await _start(p, reply)
    elif type_ == "plan.goal":
        if not p.text:
            await reply("error", {"message": GOAL_EMPTY})
            return
        done = await asyncio.to_thread(progress.done_plan_ids)
        out = await goal_mod.suggest(p.text, done=done, allow_model=allow_model)
        await reply("plan.matches", out)
    elif type_ == "plan.playlist":
        try:
            pl = await pl_mod.list_videos(p.url, refresh=p.refresh)
        except pl_mod.PlaylistUnavailable as e:
            await reply("error", {"message": str(e)})
            return
        pl["id"] = progress.playlist_key(pl["playlistId"])
        await reply("plan.playlist", pl)
    elif type_ == "plan.lesson.done":
        v = await asyncio.to_thread(progress.mark_done, p.id, p.index, p.done)
        if v is None:
            await reply("error", {"message": PLAN_NOT_FOUND})
        else:
            await reply("plan.progress", v)
    elif type_ == "plan.remove":
        await asyncio.to_thread(progress.remove, p.id)
        await reply("plans.progress", await asyncio.to_thread(progress_payload))


async def _start(p: SimpleNamespace, reply: Any) -> None:
    url = p.url
    if p.id and p.id.startswith("yt-"):
        url = p.id[3:]
    if url:
        try:
            pl = await pl_mod.list_videos(url)
        except pl_mod.PlaylistUnavailable as e:
            await reply("error", {"message": str(e)})
            return
        v = await asyncio.to_thread(progress.start_playlist, pl)
    else:
        try:
            v = await asyncio.to_thread(progress.start_catalog, p.id, goal=p.goal or None)
        except KeyError:
            await reply("error", {"message": PLAN_NOT_FOUND})
            return
    await reply("plan.progress", v)
