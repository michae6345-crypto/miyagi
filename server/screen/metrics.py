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
from collections import deque
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


def _local_extract_metrics(pattern: str, text: str) -> list[tuple[int, float]]:
    """Fallback with the same contract as `server.checks.extract_metrics` (E3), used until that
    lands on main: named groups `step`/`value`, last group as value, line order as step."""
    rx = re.compile(pattern)
    pts: dict[int, float] = {}
    order = 0
    for line in text.splitlines():
        m = rx.search(line)
        if not m:
            continue
        gd = m.groupdict()
        raw_v = gd.get("value") if "value" in gd else (m.group(m.lastindex) if m.lastindex else None)
        v = parse_number(raw_v) if raw_v is not None else None
        if v is None:
            continue
        if gd.get("step") is not None:
            st = parse_step(gd["step"])
            if st is None:
                continue
        else:
            st = order
        order += 1
        pts[st] = v
    return sorted(pts.items())


try:  # one parser for both the evaluator and the screen reader
    from server.checks import extract_metrics
except ImportError:  # E3's PR not merged yet
    extract_metrics = _local_extract_metrics


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
        self.patterns: dict[str, str] = {}
        self._has_step: dict[str, bool] = {}
        for name, p in patterns.items():
            self.add_pattern(name, p)
        self.series: dict[str, _Series] = {}
        self.restarts = 0
        self.run_id = f"screen-{lesson_id}"
        self._prev_lines: list[str] = []
        self._stale: list[str] = []   # lines of a previous run still visible after a restart
        self._lock = threading.Lock()

    def add_pattern(self, name: str, pattern: str) -> None:
        rx = re.compile(pattern)
        if "value" not in rx.groupindex and not rx.groups:
            raise ValueError(f"metric_pattern for {name!r} needs a (?P<value>...) group: {pattern}")
        self.patterns[name] = pattern
        self._has_step[name] = "step" in rx.groupindex

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
            collapsed = " ".join(text.split())
            for name, pattern in self.patterns.items():
                # E3's shared parser, one OCR line at a time, so evaluator and reader agree
                pts = extract_metrics(pattern, text) or (
                    extract_metrics(pattern, collapsed) if collapsed != text else [])
                if not pts:
                    continue
                step, value = pts[-1]
                # no step group: -1 makes us synthesise a counter for lines new this frame
                parsed.append((name, int(step) if self._has_step[name] else -1, float(value), text))

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


# ---------------------------------------------------------------------- Tiger Data (optional, dev only)

_PSYCOPG: bool | None = None


def _psycopg_installed() -> bool:
    """psycopg is no longer an engine dependency (DISTRIBUTION-PLAN, claude/eng-drop-vendors). Without it the
    Tiger writer below is a no-op even when TIGER_DATABASE_URL is set, instead of retrying a missing driver."""
    global _PSYCOPG
    if _PSYCOPG is None:
        import importlib.util

        try:
            _PSYCOPG = importlib.util.find_spec("psycopg") is not None
        except (ImportError, ValueError):
            _PSYCOPG = False
    return _PSYCOPG


class TigerWriter:
    """Writes metric points to Tiger Data `training_metrics` on one background worker. Optional: a no-op unless
    TIGER_DATABASE_URL is set (in .env; the app no longer sends a Tiger URL) and psycopg is installed. The engine's
    own learning events and run metrics go to the local store (server.checks.tiger), not here.

    Never raises into the caller. On failure it keeps the points (bounded buffer) and retries
    with exponential backoff (1s, 2s, 4s ... capped at 60s), so a DB blip loses nothing and a
    dead DB never blocks the screen loop. `status` is a KeyState for `config.status.tigerUrl`.
    """

    MAX_BUFFER = 20000
    MAX_BACKOFF = 60.0

    def __init__(self, url: str | None = None):
        self._byok = url  # None -> TIGER_DATABASE_URL from env
        self._conn = None
        self._failures = 0
        self._next_try = 0.0
        self._last_ok = False
        self.last_error: str | None = None
        self._buf: deque[tuple[float, str, int, str, float]] = deque(maxlen=self.MAX_BUFFER)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._worker: threading.Thread | None = None
        self._warned = False

    # ------------------------------------------------------------------ config / status

    @property
    def url(self) -> str:
        return self._byok if self._byok is not None else os.environ.get("TIGER_DATABASE_URL", "")

    def set_url(self, url: str | None) -> None:
        """BYOK: use this Tiger URL instead of the engine's .env (None/"" = back to env)."""
        with self._lock:
            self._byok = url or None
            self._reset_conn()
            self._failures, self._next_try, self._last_ok, self.last_error = 0, 0.0, False, None
        self._wake.set()

    def _valid_url(self) -> bool:
        if not _psycopg_installed():  # Tiger is optional now (claude/eng-drop-vendors): no driver, no writes
            return False
        from urllib.parse import urlparse
        try:
            host = urlparse(self.url).hostname or ""
        except ValueError:
            return False
        return bool(host) and "..." not in self.url and host.strip(".") != ""

    @property
    def enabled(self) -> bool:
        return self._valid_url()

    @property
    def status(self) -> str:
        """KeyState from events.ts: ok | missing | invalid | env.
        missing = no URL, or psycopg not installed; invalid = placeholder URL or the last attempt failed;
        ok = app-provided URL (and not failing); env = .env URL (and not failing)."""
        if not self.url or not _psycopg_installed():
            return "missing"
        if not self._valid_url() or self._failures > 0:
            return "invalid"
        return "ok" if self._byok else "env"

    @property
    def pending(self) -> int:
        return len(self._buf)

    def check(self, timeout: float = 5.0) -> str:
        """Synchronously try `SELECT 1` and return the resulting status (for config.keys)."""
        if not self._valid_url():
            return self.status
        try:
            import psycopg
            with psycopg.connect(self.url, connect_timeout=int(timeout)) as c:
                c.execute("SELECT 1")
            self._failures, self.last_error = 0, None
        except Exception as e:  # noqa: BLE001
            self._failures = max(1, self._failures)
            self.last_error = str(e)[:200]
        return self.status

    # ------------------------------------------------------------------ writes

    def write(self, run_id: str, points: list[tuple[str, int, float]]) -> None:
        if not self._valid_url():
            if not self._warned:
                log.info("Tiger off (status=%s); screen metrics are not sent to Tiger", self.status)
                self._warned = True
            return
        t = time.time()
        with self._lock:
            self._buf.extend((t, run_id, step, name, value) for name, step, value in points)
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, name="tiger-writer", daemon=True)
                self._worker.start()
        self._wake.set()

    def flush(self, timeout: float = 10.0) -> bool:
        """Block until the buffer is empty (tests / shutdown). True if everything was written."""
        end = time.time() + timeout
        while self._buf and time.time() < end:
            self._wake.set()
            time.sleep(0.05)
        return not self._buf

    def _reset_conn(self) -> None:
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:  # noqa: BLE001, S110
            pass
        self._conn = None

    def _run(self) -> None:
        while True:
            self._wake.wait(timeout=5)
            self._wake.clear()
            if not self._buf:
                continue
            delay = self._next_try - time.time()
            if delay > 0:
                time.sleep(min(delay, 1.0))
                self._wake.set()
                continue
            with self._lock:
                batch = list(self._buf)
            try:
                import psycopg
                if self._conn is None or self._conn.closed:
                    self._conn = psycopg.connect(self.url, autocommit=True, connect_timeout=5)
                with self._conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO training_metrics (time, run_id, step, name, value) "
                        "VALUES (to_timestamp(%s), %s, %s, %s, %s)", batch)
                with self._lock:
                    for _ in range(min(len(batch), len(self._buf))):
                        self._buf.popleft()
                if self._failures:
                    log.info("Tiger writes recovered after %d failures", self._failures)
                self._failures, self._next_try, self.last_error = 0, 0.0, None
            except Exception as e:  # noqa: BLE001
                self._failures += 1
                self.last_error = str(e)[:200]
                backoff = min(self.MAX_BACKOFF, 2 ** (self._failures - 1))
                self._next_try = time.time() + backoff
                self._reset_conn()
                log.warning("Tiger write failed (%d, retry in %.0fs, %d pending): %s",
                            self._failures, backoff, len(self._buf), self.last_error)
            if self._buf:
                self._wake.set()
