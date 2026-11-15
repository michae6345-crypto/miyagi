"""What the learner is physically doing: cursor, last keystroke/click, unsaved files, text under the cursor.

macOS, no extra permission:
  - cursor: CGEventGetLocation (global points, top-left origin, the spotlight's coordinate space)
  - idle: CGEventSourceSecondsSinceLastEventType (key-down / mouse-down)
  - unsaved files: VS Code puts a leading "●" in its window title for a dirty editor
    (window titles come with the screen observation)
  - text under the cursor: the OCR line whose rect contains the cursor

E6's accessibility layer (element under cursor, live buffer, exact line rects) can replace these later.
Elsewhere (Linux CI, tests) everything degrades to None and the session falls back to its own clock.
"""

from __future__ import annotations

import logging
import re
import sys
import time
from typing import Any

log = logging.getLogger("orchestrator.inputs")

DIRTY_MARK = "●"
OWN_FRONT_TTL_S = 1.0  # how long a "is Miyagi the active app?" answer is reused (lsappinfo, ~15 ms)


class Inputs:
    def __init__(self) -> None:
        self.q: Any = None
        if sys.platform == "darwin":
            try:
                import Quartz

                self.q = Quartz
            except Exception as e:  # noqa: BLE001
                log.warning("Quartz unavailable (%s); no cursor/idle signals", e)
        self._own_t, self._own = -1e9, False
        # E5: which app got the keys / clicks. The OS only gives global ages; attribute() (session.tick ~1/s and every
        # app switch) books the events since its last call to the app that was in front: the lesson's own editor /
        # terminal (work) or anything else (Miyagi's ask box, the Claude app, a browser: foreign).
        self._work_now = True  # the app in front at the last attribute() is one the lesson is done in
        self._seen: dict[str, float | None] = {"key": None, "click": None}  # newest event already booked (monotonic)
        self._work_t: dict[str, float] = {"key": -1e9, "click": -1e9}  # newest event booked as lesson work

    @property
    def available(self) -> bool:
        return self.q is not None

    def attribute(self, work_now: bool | None = None) -> None:
        """Book the keys / clicks since the last call to the app that was in front meanwhile (the last `work_now`;
        foreign whenever Miyagi itself has the keyboard now), then remember `work_now` (None: unchanged)."""
        if self.q is not None:
            now = time.monotonic()
            work = self._work_now and not self.miyagi_in_front()
            for kind, since in (("key", self.seconds_since_key()), ("click", self.seconds_since_click())):
                if since is None:
                    continue
                at, last = now - since, self._seen[kind]
                if last is None or at > last + 0.05:  # something new since the last booking
                    self._seen[kind] = at
                    if work:
                        self._work_t[kind] = at
        if work_now is not None:
            self._work_now = bool(work_now)

    def mark_foreign(self) -> None:
        """The learner just submitted text typed into Miyagi (an ask, a learn query, an explain): whatever was typed
        since the last booking went there, not into the lesson's files."""
        work, self._work_now = self._work_now, False
        self.attribute()
        self._work_now = work

    def _work_since(self, kind: str) -> float | None:
        if self.q is None:
            return None
        self.attribute()
        return max(0.0, time.monotonic() - self._work_t[kind])

    def seconds_since_work_key(self) -> float | None:
        """Seconds since the last key typed into the lesson's own editor / terminal (E5)."""
        return self._work_since("key")

    def seconds_since_work_click(self) -> float | None:
        return self._work_since("click")

    def seconds_since_work_input(self) -> float | None:
        vals = [v for v in (self.seconds_since_work_key(), self.seconds_since_work_click()) if v is not None]
        return min(vals) if vals else None

    def miyagi_in_front(self) -> bool:
        """Is Miyagi's own overlay (the launcher, a card's text box) the active app? Keys typed there are a question
        for Miyagi, not work in the editor (QA 11-14: typing a question held a stuck card, released on Enter).
        Launch Services via server.workspace.editor (live; NSWorkspace goes stale here), cached OWN_FRONT_TTL_S."""
        if self.q is None:
            return False
        now = time.monotonic()
        if now - self._own_t >= OWN_FRONT_TTL_S:
            self._own_t = now
            try:
                from server.workspace.editor import miyagi_focused

                self._own = bool(miyagi_focused())
            except Exception:  # noqa: BLE001
                self._own = False
        return self._own

    def cursor(self) -> tuple[float, float] | None:
        if self.q is None:
            return None
        try:
            p = self.q.CGEventGetLocation(self.q.CGEventCreate(None))
            return float(p.x), float(p.y)
        except Exception:  # noqa: BLE001
            return None

    def _since(self, event_type: Any) -> float | None:
        if self.q is None:
            return None
        try:
            return float(self.q.CGEventSourceSecondsSinceLastEventType(self.q.kCGEventSourceStateHIDSystemState, event_type))
        except Exception:  # noqa: BLE001
            return None

    def seconds_since_key(self) -> float | None:
        return self._since(self.q.kCGEventKeyDown) if self.q else None

    def seconds_since_click(self) -> float | None:
        return self._since(self.q.kCGEventLeftMouseDown) if self.q else None

    def seconds_since_input(self) -> float | None:
        vals = [v for v in (self.seconds_since_key(), self.seconds_since_click()) if v is not None]
        return min(vals) if vals else None


class FakeInputs:
    """Test double driven by the session's clock: call .key() / .click() / .move(x, y)."""

    def __init__(self, clock) -> None:
        self.clock = clock
        self.key_t = -1e9
        self.click_t = -1e9
        self.pos: tuple[float, float] | None = None
        self.available = True
        self.own_front = False  # tests: Miyagi's launcher / card box is the active app
        self.foreign_front = False  # tests: another app (the Claude app, a browser) is in front, not the lesson's
        self.work_key_t = -1e9  # the last key / click made in the lesson's own editor / terminal (E5)
        self.work_click_t = -1e9

    def miyagi_in_front(self) -> bool:
        return self.own_front

    def _work(self) -> bool:
        return not (self.own_front or self.foreign_front)

    def key(self) -> None:
        self.key_t = self.clock()
        if self._work():
            self.work_key_t = self.key_t

    def click(self) -> None:
        self.click_t = self.clock()
        if self._work():
            self.work_click_t = self.click_t

    def attribute(self, work_now: bool | None = None) -> None:
        pass  # key() / click() book each event as it happens (own_front / foreign_front)

    def mark_foreign(self) -> None:
        pass

    def seconds_since_work_key(self) -> float | None:
        return self.clock() - self.work_key_t

    def seconds_since_work_click(self) -> float | None:
        return self.clock() - self.work_click_t

    def seconds_since_work_input(self) -> float | None:
        return min(self.seconds_since_work_key(), self.seconds_since_work_click())

    def move(self, x: float, y: float) -> None:
        self.pos = (x, y)

    def cursor(self) -> tuple[float, float] | None:
        return self.pos

    def seconds_since_key(self) -> float | None:
        return self.clock() - self.key_t

    def seconds_since_click(self) -> float | None:
        return self.clock() - self.click_t

    def seconds_since_input(self) -> float | None:
        return min(self.seconds_since_key(), self.seconds_since_click())


def dirty_files(obs: Any) -> set[str]:
    """File names VS Code shows as unsaved ("● name.py — folder" window titles)."""
    out: set[str] = set()
    for w in getattr(obs, "windows", None) or []:
        title = (getattr(w, "title", "") or "").strip()
        if title.startswith(DIRTY_MARK):
            name = re.split(r"\s[—–-]\s", title[len(DIRTY_MARK):].strip(), maxsplit=1)[0].strip()
            if name:
                out.add(name)
    return out


def text_under(obs: Any, x: float, y: float, slack: float = 6.0) -> dict | None:
    """The OCR line at (x, y): {text, app, rect} (nearest line within `slack` points)."""
    best, best_d = None, slack + 1
    for b in getattr(obs, "blocks", None) or []:
        r = b.rect
        dx = max(r.x - x, 0, x - (r.x + r.w))
        dy = max(r.y - y, 0, y - (r.y + r.h))
        d = max(dx, dy)
        if d < best_d:
            best, best_d = b, d
    if best is None:
        return None
    return {"text": best.text[:200], "app": best.app, "rect": best.rect.to_dict()}
