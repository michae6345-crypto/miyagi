"""Cost gate for every periodic coach call (Michael's key; the judge called Haiku every ~20 s on s2
while he was away with the display asleep).

    gate = PeriodicGate()                                   # base 20 s, cap 5 min, stop after 3 same
    if gate.allow(key, screen=obs_text, files=mtimes, screen_ok=reader_up, asleep=display_asleep):
        gate.started(key, screen=obs_text, files=mtimes)
        verdict = await call(...)
        gate.record(key, verdict_signature)

Rules:
1. only when the screen text or the files changed since the last call. The screen text is hashed
   after dropping clocks, dates and battery figures and ignoring line order (OCR noise must not count
   as change); files are hashed by path + mtime (+ size), or by content when no mtimes are given;
2. never when the screen reader is down or the display is asleep;
3. while the answer stays the same, the minimum interval doubles: 20 s → 40 → 80 … capped at 5 min;
   a different answer resets it to 20 s;
4. after 3 identical answers in a row: stop until the files change or the screen changes a lot
   (>= 25% of its lines differ, e.g. another app in front); a scrolling log doesn't count.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_NOISE = re.compile(
    r"\b\d{1,2}:\d{2}(?::\d{2})?\s?(?:[AaPp]\.?[Mm]\.?)?\b"  # clocks
    r"|\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}\b"  # dates
    r"|\b\d{1,3}\s?%"  # battery / progress percentages
)


def screen_lines(text: str) -> frozenset[str]:
    """The screen's lines without clocks/dates/percentages; a set, so line order doesn't matter."""
    lines = {re.sub(r"\s+", " ", _NOISE.sub("", ln)).strip() for ln in (text or "").splitlines()}
    lines.discard("")
    return frozenset(lines)


def screen_signature(text: str) -> str:
    """Hash of the screen text that ignores clocks/dates/percentages and line order."""
    return hashlib.sha256("\n".join(sorted(screen_lines(text))).encode()).hexdigest()[:16]


def _distance(a: frozenset[str], b: frozenset[str]) -> float:
    return 1.0 - len(a & b) / max(1, len(a | b))


def files_signature(files: dict[str, Any] | None) -> str:
    """{path: mtime} or {path: (mtime, size)} or {path: text} → hash."""
    items = []
    for path, v in sorted((files or {}).items()):
        items.append(f"{path}\x00{v!r}" if isinstance(v, (int, float, tuple, list)) else f"{path}\x00{hashlib.sha256(str(v).encode()).hexdigest()}")
    return hashlib.sha256("\n".join(items).encode()).hexdigest()[:16]


WAKE_DISTANCE = 0.25


@dataclass
class _State:
    last_t: float | None = None
    screen: str = ""
    lines: frozenset = frozenset()
    files: str = ""
    interval: float = 0.0
    verdict: Any = None
    same: int = 0
    stopped: bool = False


class PeriodicGate:
    def __init__(self, *, base_s: float = 20.0, cap_s: float = 300.0, stop_after: int = 3, clock: Callable[[], float] = time.monotonic):
        self.base_s, self.cap_s, self.stop_after, self.clock = base_s, cap_s, stop_after, clock
        self._s: dict[str, _State] = {}

    def _st(self, key: str) -> _State:
        return self._s.setdefault(key, _State(interval=self.base_s))

    def allow(self, key: str, *, screen: str = "", files: dict[str, Any] | None = None, screen_ok: bool = True, asleep: bool = False) -> bool:
        if not screen_ok or asleep:
            return False
        st = self._st(key)
        files_changed = files_signature(files) != st.files
        changed = st.last_t is None or files_changed or screen_signature(screen) != st.screen
        if not changed:
            return False  # rule 1 (and rule 4: a stopped key stays stopped until this changes)
        if st.stopped:
            # stopped after 3 identical answers: only a save or a real screen change (an app switch,
            # >= 25% of lines) wakes it; a scrolling log or a ticking counter does not
            if not files_changed and _distance(screen_lines(screen), st.lines) < WAKE_DISTANCE:
                return False
            st.stopped, st.same = False, 0
        if files_changed and st.last_t is not None:
            st.interval = self.base_s  # a save is real progress; screen-only changes keep the backoff
        return st.last_t is None or self.clock() - st.last_t >= st.interval

    def started(self, key: str, *, screen: str = "", files: dict[str, Any] | None = None) -> None:
        st = self._st(key)
        st.last_t, st.screen, st.files, st.lines = self.clock(), screen_signature(screen), files_signature(files), screen_lines(screen)

    def record(self, key: str, verdict: Any) -> None:
        st = self._st(key)
        if verdict is not None and verdict == st.verdict:
            st.same += 1
            st.interval = min(st.interval * 2, self.cap_s)
            st.stopped = st.same >= self.stop_after
        else:
            st.verdict, st.same, st.interval = verdict, 1, self.base_s

    def state(self, key: str) -> dict:
        st = self._st(key)
        return {"interval_s": st.interval, "same": st.same, "stopped": st.stopped}
