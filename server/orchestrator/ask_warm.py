"""ask.warm (Nov 22, push to talk speed): the learner is holding Fn+Control past the minimum hold, so an ask (a circle,
or spoken words) is likely within a few seconds. Get ready for it, off the command queue and with no reply:

  - open or reuse the coach's keep-alive Anthropic client (engine -> miyagi cloud -> Anthropic, or direct with a key);
  - write the circle ask's fixed prefix (system prompt + lesson context + output format, the same thinking and effort)
    to the prompt cache with one 1-token request on the circle model (Haiku 5.5 by default; never Opus: llm.guard).

The app sends it at most once every 4 minutes (main/features/ptt.ts) and only when engine.hello lists "ask.warm". The
engine keeps its own gap too (GAP_S, under the 5-minute cache lifetime), so a second app or a replayed command never
pays for a second cache write, and one warm-up runs at a time. DEMO, stubs, offline or no key: nothing is sent.
Logs carry timings and token counts only, never the prompt.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

log = logging.getLogger("orchestrator.ask_warm")


def _gap_s() -> float:
    try:
        return max(0.0, float(os.environ.get("MIYAGI_ASK_WARM_GAP_S", "240")))
    except ValueError:
        return 240.0


GAP_S = _gap_s()  # 4 min: the cache lives 5 min after its last use


class AskWarm:
    def __init__(self, session: Any, gap_s: float | None = None, clock: Any = time.monotonic) -> None:
        self.session = session
        self.gap_s = GAP_S if gap_s is None else gap_s
        self.clock = clock
        self.last: float | None = None
        self.task: asyncio.Task | None = None

    def available(self) -> bool:
        """engine.hello lists ask.warm only when it can do something (the real coach is loaded)."""
        m = getattr(self.session, "m", None)
        try:
            return bool(m is not None and m.has_circle_warm())
        except Exception:  # noqa: BLE001
            return False

    def kick(self, ptt_id: str | None = None) -> bool:
        """Start a warm-up unless one is running or one ran within gap_s. Returns whether it started. Never blocks."""
        if not self.available():
            return False
        now = self.clock()
        if self.task is not None and not self.task.done():
            return False
        if self.last is not None and now - self.last < self.gap_s:
            return False
        self.last = now
        self.task = asyncio.get_running_loop().create_task(self._run(ptt_id))
        return True

    async def _run(self, ptt_id: str | None) -> None:
        t0 = time.monotonic()
        step = getattr(self.session, "step", None)
        out = await self.session.m.circle_warm(step)
        ms = int((time.monotonic() - t0) * 1000)
        if not isinstance(out, dict):
            return
        if out.get("skipped"):
            log.info("ask.warm %s: skipped (%s)", ptt_id or "-", out["skipped"])
            self.last = None  # nothing was written: the next hold may try again
        else:
            log.info("ask.warm %s: %d ms (tls %s s, cache %s s, cached tokens %s)", ptt_id or "-", ms, out.get("tls_s", "-"),
                     out.get("cache_s", "-"), out.get("cache", "-"))
