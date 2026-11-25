"""The ambient help model-call cap (AMBIENT-HELP.md, "Privacy and cost"): at most AMBIENT_CALLS_PER_HOUR (20) model
calls in any rolling hour on this Mac, for Explain (error.explain) and How-do-I (help.ask) together.

    from server.ambient_cap import shared_cap
    wait = shared_cap().take()      # None: go ahead (the call is counted); else seconds until a slot frees
    shared_cap().refund()           # the call never reached a model (offline, no key): it does not count

The call times (and nothing else) are kept in <state dir>/ambient_calls.json, so an engine restart does not reset the
hour. Thread-safe; never raises (a file it cannot read or write only makes the count this process's own).
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

try:
    from shared.contracts.events import AMBIENT_CALLS_PER_HOUR
except Exception:  # pragma: no cover - the contract always ships with the engine
    AMBIENT_CALLS_PER_HOUR = 20

log = logging.getLogger("server.ambient_cap")

WINDOW_S = 3600.0
FILE_NAME = "ambient_calls.json"


def _state_dir() -> Path:
    return Path(os.environ.get("MIYAGI_STATE_DIR") or Path.home() / "miyagi" / "state")


class HourlyCap:
    def __init__(self, limit: int = AMBIENT_CALLS_PER_HOUR, window_s: float = WINDOW_S,
                 path: Path | None | bool = None, clock: Callable[[], float] = time.time) -> None:
        """path: the file the call times live in (None: <state dir>/ambient_calls.json, read on every take;
        False: memory only)."""
        self.limit = int(limit)
        self.window_s = float(window_s)
        self._path = path
        self.clock = clock
        self._lock = threading.Lock()
        self._times: list[float] = []

    def _file(self) -> Path | None:
        if self._path is False:
            return None
        return Path(self._path) if self._path else _state_dir() / FILE_NAME

    def _load(self, now: float) -> None:
        f = self._file()
        if f is not None and f.exists():
            try:  # the file is the truth (another engine run wrote it); unreadable: this process's own count
                data = json.loads(f.read_text(encoding="utf-8"))
                self._times = sorted(float(t) for t in data.get("calls", []) if isinstance(t, (int, float)))
            except (OSError, ValueError, AttributeError):
                pass
        self._times = [t for t in self._times if now - t < self.window_s and t <= now + 1]

    def _save(self) -> None:
        f = self._file()
        if f is None:
            return
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps({"calls": self._times[-self.limit * 2:]}), encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(f)
        except OSError:
            log.debug("ambient cap: could not save the call times", exc_info=True)

    def take(self) -> int | None:
        """Count one call now and return None, or (cap reached) return the whole seconds until the oldest call in the
        window leaves it (>= 1)."""
        with self._lock:
            now = self.clock()
            self._load(now)
            if len(self._times) >= self.limit:
                return max(1, math.ceil(self._times[0] + self.window_s - now))
            self._times.append(now)
            self._save()
            return None

    def refund(self) -> None:
        """Take back the latest call (it never reached a model)."""
        with self._lock:
            self._load(self.clock())
            if self._times:
                self._times.pop()
                self._save()

    def used(self) -> int:
        with self._lock:
            self._load(self.clock())
            return len(self._times)


_shared: HourlyCap | None = None
_shared_lock = threading.Lock()


def shared_cap() -> HourlyCap:
    """The one cap Explain and How-do-I share in this engine."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = HourlyCap()
        return _shared


def reset_shared(cap: HourlyCap | None = None) -> None:
    """Tests: a fresh (or the given) shared cap."""
    global _shared
    with _shared_lock:
        _shared = cap
