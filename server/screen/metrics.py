"""Terminal metric reader: turn training logs that are *visible on screen* into metrics.

Given `metric_pattern` regexes (named groups `step` and `value`), each new observation's
lines are matched; every (name, step) is emitted once. A training restart (the same
`python train.py` run again, steps going back to 0 with different values) is detected and
starts a new run id so the orchestrator's curve doesn't mix two runs.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .match import app_matches, group_lines, norm
from .types import ScreenObservation

log = logging.getLogger("server.screen.metrics")

MetricCallback = Callable[[str, int, float], None]

# OCR mistakes inside numbers: O->0, l/I/|->1, S->5, ',' as decimal point.
_NUM_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", ",": ".", " ": ""})


def parse_number(s: str) -> float | None:
    s = s.strip().translate(_NUM_FIX)
    s = s.replace("e—", "e-").replace("E—", "e-")
    try:
        return float(s)
    except ValueError:
        return None


def parse_step(s: str) -> int | None:
    v = parse_number(s)
    return int(v) if v is not None and v >= 0 else None


@dataclass
class _Series:
    values: dict[int, float] = field(default_factory=dict)  # step -> value
    texts: dict[int, str] = field(default_factory=dict)     # step -> normalised line text
    max_step: int = -1


class TerminalMetricReader:
    """Feed it observations; it calls `callback(name, step, value)` for each new metric point.

    patterns: {metric_name: regex with (?P<step>..) and (?P<value>..)}.
    app: only read lines in this app's windows (None = any window; VS Code's integrated
    terminal lives inside "Code").
    """

    def __init__(self, lesson_id: str, patterns: dict[str, str], callback: MetricCallback | None = None,
                 app: str | None = None, tiger: TigerWriter | None = None,
                 on_restart: Callable[[str], None] | None = None):
        self.lesson_id = lesson_id
        self.app = app
        self.callback = callback
        self.on_restart = on_restart
        self.tiger = tiger
        self.patterns: dict[str, re.Pattern] = {}
        for name, p in patterns.items():
            self.add_pattern(name, p)
        self.series: dict[str, _Series] = {}
        self.restarts = 0
        self.run_id = f"screen-{lesson_id}"
        self._prev_lines: list[str] = []
        self._stale: list[str] = []   # lines of a previous run still visible after a restart
        self._lock = threading.Lock()

    def add_pattern(self, name: str, pattern: str) -> None:
        rx = re.compile(pattern, re.IGNORECASE)
        if "value" not in rx.groupindex:
            raise ValueError(f"metric_pattern for {name!r} needs a (?P<value>...) group: {pattern}")
        self.patterns[name] = rx

    def reset(self) -> None:
        """Forget everything seen (e.g. when the lesson moves to a new step)."""
        with self._lock:
            self.series.clear()
            self._prev_lines = []
            self._stale = []

    # ------------------------------------------------------------------ core

    def feed(self, obs: ScreenObservation) -> list[tuple[str, int, float]]:
        lines = [ln.text for ln in group_lines(obs.blocks) if app_matches(self.app, ln.app, ln.window)]
        with self._lock:
            out = self._feed_lines(lines)
        for name, step, value in out:
            if self.callback:
                try:
                    self.callback(name, step, value)
                except Exception:
                    log.exception("metric callback failed")
        if out and self.tiger:
            self.tiger.write(self.run_id, out)
        return out

    @staticmethod
    def _seen_in(text: str, pool: list[str]) -> bool:
        n = norm(text)
        return n in pool or any(fuzz.ratio(n, p) >= 92 for p in pool)

    def _was_visible(self, text: str) -> bool:
        return self._seen_in(text, self._prev_lines)

    def _feed_lines(self, lines: list[str]) -> list[tuple[str, int, float]]:
        out: list[tuple[str, int, float]] = []
        restart_votes = 0
        parsed: list[tuple[str, int, float, str]] = []
        for text in lines:
            for name, rx in self.patterns.items():
                m = rx.search(text) or rx.search(norm(text))
                if not m:
                    continue
                value = parse_number(m.group("value"))
                if value is None:
                    continue
                if "step" in rx.groupindex and m.group("step") is not None:
                    step = parse_step(m.group("step"))
                else:  # no step group: count occurrences
                    step = None
                if step is None and "step" in rx.groupindex:
                    continue
                parsed.append((name, step if step is not None else -1, value, text))

        # Restart detection: a line that was NOT on screen last frame, reporting a step we've
        # already recorded, with a clearly different value -> the user re-ran training.
        for name, step, value, text in parsed:
            s = self.series.get(name)
            if not s or step < 0 or step not in s.values or self._was_visible(text):
                continue
            old = s.values[step]
            rel = abs(old - value) / max(abs(old), abs(value), 1e-12)
            if rel > 0.02 and fuzz.ratio(norm(text), s.texts.get(step, "")) < 90:
                restart_votes += 1
        if restart_votes >= 1 and any(st < self.series[n].max_step for n, st, _, _ in parsed
                                      if n in self.series and st >= 0):
            self.restarts += 1
            self.run_id = f"screen-{self.lesson_id}-r{self.restarts + 1}"
            self.series.clear()
            # everything that was already on screen belongs to the old run
            self._stale = list(self._prev_lines)
            log.info("training restart detected -> %s", self.run_id)
            if self.on_restart:
                try:
                    self.on_restart(self.run_id)
                except Exception:
                    log.exception("on_restart callback failed")

        for name, step, value, text in parsed:
            if self._stale and self._seen_in(text, self._stale):
                continue
            s = self.series.setdefault(name, _Series())
            if step < 0:  # no step group: synthesise a counter for lines new this frame
                if self._was_visible(text):
                    continue
                step = s.max_step + 1
            if step in s.values:
                continue
            s.values[step] = value
            s.texts[step] = norm(text)
            s.max_step = max(s.max_step, step)
            out.append((name, step, value))

        self._prev_lines = [norm(t) for t in lines]
        out.sort(key=lambda p: (p[0], p[1]))
        return out


# ---------------------------------------------------------------------- Tiger Data

class TigerWriter:
    """Writes metric points to Tiger Data `training_metrics`. Never raises; disables itself
    after repeated failures (the demo must not die because the DB is down)."""

    def __init__(self, url: str | None = None):
        self.url = url if url is not None else os.environ.get("TIGER_DATABASE_URL", "")
        self._conn = None
        self._failures = 0
        self._warned = False
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._valid_url() and self._failures < 5

    def _valid_url(self) -> bool:
        from urllib.parse import urlparse
        try:
            host = urlparse(self.url).hostname or ""
        except ValueError:
            return False
        return bool(host) and "..." not in self.url and host.strip(".") != ""

    def _connect(self):
        import psycopg
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.url, autocommit=True, connect_timeout=5)
        return self._conn

    def write(self, run_id: str, points: list[tuple[str, int, float]]) -> None:
        if not self.enabled:
            if not self._warned:
                log.warning("TIGER_DATABASE_URL not set (or failing); screen metrics not persisted")
                self._warned = True
            return
        threading.Thread(target=self._write, args=(run_id, list(points), time.time()), daemon=True).start()

    def _write(self, run_id: str, points, t: float) -> None:
        with self._lock:
            try:
                conn = self._connect()
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO training_metrics (time, run_id, step, name, value) "
                        "VALUES (to_timestamp(%s), %s, %s, %s, %s)",
                        [(t, run_id, step, name, value) for name, step, value in points])
                self._failures = 0
            except Exception as e:  # noqa: BLE001
                self._failures += 1
                self._conn = None
                log.warning("Tiger write failed (%d/5): %s", self._failures, e)
