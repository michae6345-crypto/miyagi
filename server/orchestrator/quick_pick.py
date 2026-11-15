"""t9 screen.avoid: VS Code's quick-pick (the input box at the top centre: the kernel picker, the command palette,
"Select Interpreter") opens UNDER Miyagi's overlay, and the "Not yet" card and the step pill cover it. The engine says
where it is; Adrian's app moves both out of the way.

- Where: the reader's "ui:quickpick" region (server.screen.ax.find_quickpick: VS Code's focused element is the picker's
  input while it is open; its parents up to the widget), screen points, top-left origin (the spotlight.rect space).
- When: Engine._avoid_loop calls poll() every POLL_S, only while a lesson is active; one AX look, no model calls.
- What: `screen.avoid {rects: [{kind: "quickpick", x, y, w, h}]}` only when the set changes; `{rects: []}` once it
  closed (the app clears it). Nothing at all while no lesson runs (the app drops it on lesson.ended).
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("orchestrator.session")

POLL_S = 0.5
KIND = "quickpick"


def active(s) -> bool:
    """A lesson is loaded (built, running, held by "Before you start", a Demo lesson)."""
    return getattr(s, "graph", None) is not None


async def look(s) -> list[dict] | None:
    """The quick-pick's rects now ([] = closed), or None when the look failed (nothing changes then)."""
    region = getattr(s.screen, "region", None) if getattr(s, "screen", None) is not None else None
    if region is None:
        return []
    try:
        r = await asyncio.to_thread(region, f"ui:{KIND}")
    except Exception:  # noqa: BLE001
        log.exception("ui:%s lookup failed", KIND)
        return None
    if not r:
        return []
    return [{"kind": KIND, **{k: float(round(float(r[k]))) for k in ("x", "y", "w", "h")}}]


async def poll(s) -> None:
    """One look: `screen.avoid` when the set of rects changed since the last one sent (this lesson)."""
    if not active(s):
        s._avoid_sent = None  # the next lesson starts from nothing (the app drops it on lesson.ended)
        return
    epoch = getattr(s, "lesson_epoch", 0)
    rects = await look(s)
    if rects is None or not active(s) or getattr(s, "lesson_epoch", 0) != epoch:  # failed, or the lesson changed
        return
    sent = getattr(s, "_avoid_sent", None)
    if rects == (sent[1] if sent is not None and sent[0] == epoch else []):  # a new lesson starts from nothing
        return
    s._avoid_sent = (epoch, rects)
    log.info("screen.avoid: %s", rects or "nothing (the quick-pick closed)")
    await s.emit("screen.avoid", {"rects": rects})
