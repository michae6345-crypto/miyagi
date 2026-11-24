"""The skill tree's app messages. PROVISIONAL names until the ui-v4 contract (shared/contracts) lands; main.py parses
them here only while the contract does not list them, so the contract's models win once it does.

App -> engine (all instant reads / small local edits, answered to the app that asked):
    skills.tracks.get   {track?}               -> skills.tracks   api.tracks: every track (or one) with its skills
    skill.get           {id}                   -> skill           api.skill: one skill, its lessons, recent steps, proofs
    skills.mastery.get  {}                     -> skills.mastery  api.mastery
    skills.reviews.get  {days?}                -> skills.reviews  api.reviews: due now, then the next `days` (default 7)
    skill.proof.delete  {id} | {skillId}       -> skill (skillId) / skills.proofs {deleted}
    skill.forget        {id?}                  -> skills.mastery  (no id: forget every skill and every proof)
Engine -> app, after a step that practises catalog skills passes (or a due review is skipped):
    skills.update       api.update: {events: [{kind: mastered | reviewed | review_missed, skillId, at, ...}], skills, due}
"""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from . import api, catalog, ledger, proofs

COMMANDS = ("skills.tracks.get", "skill.get", "skills.mastery.get", "skills.reviews.get", "skill.proof.delete", "skill.forget")
READS = COMMANDS  # every one is answered beside the queue (local file reads / small writes)
EVENTS = ("skills.tracks", "skill", "skills.mastery", "skills.reviews", "skills.proofs", "skills.update")
SKILL_ID_RE = re.compile(r"^[a-z0-9_#+-]{1,12}\.[a-z0-9_]{1,40}$")
UNKNOWN_SKILL = "That skill isn't in the catalog."

Reply = Callable[[str, dict], Awaitable[None]]


def _skill_id(v: Any, what: str) -> str:
    if not isinstance(v, str) or not SKILL_ID_RE.match(v):
        raise ValueError(f"{what}: id must be a skill id")
    return v


def parse(type_: str, payload: Any) -> SimpleNamespace:
    """The payload as attributes; raises ValueError on a bad shape (main.py answers one error, the engine carries on)."""
    p = payload if isinstance(payload, dict) else {}
    if type_ == "skills.tracks.get":
        track = p.get("track")
        if track is not None and (not isinstance(track, str) or len(track) > 40):
            raise ValueError("skills.tracks.get: track must be a track id")
        return SimpleNamespace(track=track)
    if type_ == "skill.get":
        return SimpleNamespace(id=_skill_id(p.get("id"), type_))
    if type_ == "skills.reviews.get":
        days = p.get("days", api.UPCOMING_DAYS)
        if isinstance(days, bool) or not isinstance(days, int) or not 0 <= days <= 90:
            raise ValueError("skills.reviews.get: days must be 0-90")
        return SimpleNamespace(days=days)
    if type_ == "skill.proof.delete":
        pid, sid = p.get("id"), p.get("skillId")
        if pid is not None and (not isinstance(pid, str) or not proofs.ID_RE.match(pid)):
            raise ValueError("skill.proof.delete: id must be a proof id")
        if sid is not None:
            sid = _skill_id(sid, type_)
        if (pid is None) == (sid is None):
            raise ValueError("skill.proof.delete: send id or skillId")
        return SimpleNamespace(id=pid, skillId=sid)
    if type_ == "skill.forget":
        sid = p.get("id")
        return SimpleNamespace(id=None if sid is None else _skill_id(sid, type_))
    if type_ == "skills.mastery.get":
        return SimpleNamespace()
    raise ValueError(f"unknown skills command: {type_}")


def _forget(sid: str | None) -> None:
    if sid is None:
        proofs.wipe()
        ledger.forget()
    else:
        proofs.delete_for_skill(sid)
        ledger.forget(sid)


async def handle(type_: str, p: Any, reply: Reply) -> None:
    """Answer one skills command. Every file read / write runs in a worker thread."""
    if type_ == "skills.tracks.get":
        await reply("skills.tracks", await asyncio.to_thread(lambda: api.tracks(track=p.track)))
    elif type_ == "skill.get":
        got = await asyncio.to_thread(api.skill, p.id)
        await (reply("skill", got) if got else reply("error", {"message": UNKNOWN_SKILL}))
    elif type_ == "skills.mastery.get":
        await reply("skills.mastery", await asyncio.to_thread(api.mastery))
    elif type_ == "skills.reviews.get":
        await reply("skills.reviews", await asyncio.to_thread(lambda: api.reviews(days=p.days)))
    elif type_ == "skill.proof.delete":
        if p.skillId is not None:
            await asyncio.to_thread(proofs.delete_for_skill, p.skillId)
            got = await asyncio.to_thread(api.skill, p.skillId)
            await (reply("skill", got) if got else reply("error", {"message": UNKNOWN_SKILL}))
        else:
            ok = await asyncio.to_thread(proofs.delete, p.id)
            await reply("skills.proofs", {"deleted": 1 if ok else 0})
    elif type_ == "skill.forget":
        if p.id is not None and catalog.skill(p.id) is None:
            await reply("error", {"message": UNKNOWN_SKILL})
            return
        await asyncio.to_thread(_forget, p.id)
        await reply("skills.mastery", await asyncio.to_thread(api.mastery))
