"""The skill tree's ui-v4 messages (shared/contracts UI-V4.md section 4).

    proof.get {id} | {skillId}, reqId?  -> proof {items: [Proof], skillId?, reqId?}   (one pass, or a skill's newest five)
    data.delete {what?}                 -> proofs go when `what` is absent (Delete my data), or lists "proofs" / "all"

The tree itself rides on progress.graph (graph.merge, from progress.get). Everything is local and answered beside the
command queue.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from . import proofs

Reply = Callable[[str, dict], Awaitable[None]]
PROOF_KINDS = frozenset({"proofs", "all"})


def proof_payload(proof_id: str | None, skill_id: str | None, req_id: str | None = None) -> dict:
    """ProofEvent: an unknown id or a skill with no proofs answers an empty list (never an error)."""
    if proof_id:
        rec = proofs.get(proof_id)
        items = [proofs.wire(rec)] if rec else []
    elif skill_id:
        items = [proofs.wire(r) for r in proofs.for_skill(skill_id)]
    else:
        items = []
    out: dict[str, Any] = {"items": items}
    if skill_id:
        out["skillId"] = skill_id
    if req_id:
        out["reqId"] = req_id
    return out


async def proof_get(p: Any, reply: Reply) -> None:
    await reply("proof", await asyncio.to_thread(proof_payload, getattr(p, "id", None), getattr(p, "skillId", None),
                                                 getattr(p, "reqId", None)))


def deletes_proofs(what: list[str] | None) -> bool:
    return what is None or bool(PROOF_KINDS & set(what))
