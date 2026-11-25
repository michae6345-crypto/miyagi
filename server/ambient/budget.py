"""The ambient-help model budget: AMBIENT_CALLS_PER_HOUR calls in any rolling hour on this Mac, Explain and How-do-I
together (AMBIENT-HELP.md, Privacy and cost). One shared instance, BUDGET; memory only.

    wait = BUDGET.take()      # None: go ahead (the call is counted); else seconds until the next call may go
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

try:
    from shared.contracts.events import AMBIENT_CALLS_PER_HOUR
except Exception:  # noqa: BLE001 - the contract's value
    AMBIENT_CALLS_PER_HOUR = 20

WINDOW_S = 3600.0


class CallBudget:
    def __init__(self, limit: int = AMBIENT_CALLS_PER_HOUR, window_s: float = WINDOW_S,
                 clock: Callable[[], float] = time.monotonic):
        self.limit, self.window_s, self.clock = limit, window_s, clock
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def _trim(self, now: float) -> None:
        while self._calls and now - self._calls[0] >= self.window_s:
            self._calls.popleft()

    def take(self) -> int | None:
        """Count one model call now, or say how long until one may go (whole seconds, at least 1)."""
        with self._lock:
            now = self.clock()
            self._trim(now)
            if len(self._calls) >= self.limit:
                return max(1, int(self._calls[0] + self.window_s - now + 0.999))
            self._calls.append(now)
            return None

    def left(self) -> int:
        with self._lock:
            self._trim(self.clock())
            return self.limit - len(self._calls)


BUDGET = CallBudget()
