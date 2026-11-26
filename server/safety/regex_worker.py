"""Lesson regexes run in a separate process with a hard deadline (ReDoS; OWASP LLM06 / A08).

A lesson's check patterns come from a model, a cached graph or a shared lesson. CPython's `re` has no timeout and
holds the GIL while it backtracks, and no set of shape rules catches every catastrophic pattern ('-?' * 27 + '-' * 27
+ 'x', (?:a|aa){16}... , \\d+\\d+\\d+x). So every search with a lesson pattern that could backtrack runs in ONE
long-lived worker process (plain `re`, stdlib only) and must answer within DEADLINE_S. On a timeout the worker is
killed and started again and the search counts as "no match" (count_skips() tells a check that passes on "no
match", screen_absent, that this one wasn't an answer). A timeout is the pattern's only when the worker spent the
time on it: the worker reports its CPU time with every answer and the killed one's is read back (wait4), so a
timeout where it barely ran (a SIGSTOP, heavy swap, a starved CPU: the Mac stalled, not the pattern) is asked once
more with CONFIRM_S, and is a strike only when that runs out too. A strike counts at most once per STRIKE_GAP_S per
pattern (one check's several searches are one strike), the pattern is skipped for that long after it, and strikes
expire after STRIKE_TTL_S (monotonic clock). After BAN_STRIKES of them the pattern is remembered as bad (is_bad():
safe_compile refuses it from then on, every sink's `except re.error` treats it as invalid), so a stall of the Mac
never bans a real pattern. An answer already waiting when the engine itself was the one stalled is read, never
counted as a timeout.

Per lesson (budget(key) around a lesson's evaluation, server.orchestrator.session): after LESSON_TIMEOUTS pattern
timeouts (a stall of the Mac is not one) in one lesson within LESSON_WINDOW_S, or once the worker has spent
LESSON_CPU_S of CPU time on that lesson's searches within LESSON_WINDOW_S (every answer carries the worker's CPU
time, so a pattern that stays just under the deadline is charged what it costs), every other pattern of that lesson
that would need the worker counts as "no match" without running, so a cached or shared graph full of distinct slow
patterns costs a few seconds per window, never one deadline (or one near-deadline search) per pattern per frame.
A real lesson's search costs about 0.02 ms of CPU (0.1 ms on a 64 KB window): LESSON_CPU_S is some 10^5 of them per
window. A search outside any budget() (one on the event loop) uses the running lesson's Budget (set_fallback), so
those sinks are bounded the same way.

  GuardedPattern   what server.safety.patterns.safe_compile returns: .search / .match / .fullmatch / .finditer /
                   .findall / .pattern / .flags / .groups / .groupindex like re.Pattern, the matching done in the
                   worker. A pattern with no repeat, no alternation and no backreference (linear in the text) runs
                   in-process.
  GuardedMatch     what its search returns: .group / .groups / .groupdict / .start / .end / .span / [i] like re.Match

If the worker can't start at all (no interpreter to spawn), a pattern that passed the shape checks
(server.safety.patterns) runs in-process: the shape checks are the second line, not the only one.
"""
from __future__ import annotations

import atexit
import contextlib
import contextvars
import hashlib
import inspect
import json
import logging
import os
import re
import select
import sys
import threading
import time
import weakref
from collections import OrderedDict, deque
from subprocess import DEVNULL, PIPE
from subprocess import Popen as _Popen  # bound at import: a test's mock of subprocess.Popen never replaces the worker
from typing import Any

log = logging.getLogger("server.safety")

DEADLINE_S = 0.25  # one search, from the request written to the answer read (a real lesson pattern takes < 10 ms)
START_S = 10.0  # the worker's own start (an interpreter on a busy Mac), never counted against a pattern
MAX_MATCHES = 10_000  # finditer / findall: at most this many matches come back
CACHE_TEXT = 4096  # answers for texts up to this long are kept (the same OCR lines come back every frame)
CACHE_SIZE = 4096
RETRY_SPAWN_S = 30.0  # after a failed start, how long the in-process fallback is used before trying again
BAN_STRIKES = 2  # strikes before a pattern is refused everywhere (one can be the Mac stalling, not the pattern)
CPU_SLOW_S = 0.6 * DEADLINE_S  # a timed-out search whose worker used this much CPU on it: the pattern's own cost
CONFIRM_S = 1.0  # a timeout whose worker barely ran (or whose CPU time can't be read) is asked again with this long
STRIKE_GAP_S = 5.0  # one strike per pattern per this long (search_wrapped is 4 searches, a big file 17), and the
                    # pattern is skipped meanwhile (its next search would cost another deadline)
STRIKE_TTL_S = 600.0  # a strike older than this (monotonic clock) is forgotten: two stalls hours apart never ban
LESSON_TIMEOUTS = 3  # timeouts in one lesson before its other worker patterns stop running (budget())
LESSON_WINDOW_S = 600.0  # ... within this long (a monotonic clock): an old stall doesn't stop a lesson for good
LESSON_CPU_S = 3.0  # the worker's CPU time on one lesson's searches within LESSON_WINDOW_S before they stop (budget())
MAX_REMEMBERED = 1 << 16  # banned / struck patterns kept (as 16-byte hashes), oldest forgotten first

_CHILD = r"""
import json, re, sys, time
out, inp, cache = sys.stdout, sys.stdin, {}
out.write("ready %r\n" % time.process_time()); out.flush()
while True:
    line = inp.readline()
    if not line:
        break
    try:
        q = json.loads(line)
        key = (q["p"], q["f"])
        rx = cache.get(key)
        if rx is None:
            if len(cache) > 512:
                cache.clear()
            rx = cache[key] = re.compile(q["p"], q["f"])
        t, op, pos, end = q["t"], q["op"], q["pos"], q["end"]
        if op == "finditer":
            res = []
            for m in rx.finditer(t, pos, end):
                res.append(m.regs)
                if len(res) >= q["max"]:
                    break
        else:
            m = getattr(rx, op)(t, pos, end)
            res = m.regs if m is not None else None
        out.write(json.dumps({"r": res, "c": time.process_time()}) + "\n")
    except Exception as e:
        out.write(json.dumps({"e": type(e).__name__ + ": " + str(e), "c": time.process_time()}) + "\n")
    out.flush()
"""

# hash(pattern) -> why: struck BAN_STRIKES times in the worker, never run again with any flags (lesson validation
# reads it without the MULTILINE / IGNORECASE a sink adds). hash(pattern) -> (strikes so far, below BAN_STRIKES, and
# the monotonic time of the last one).
_BAD: dict[bytes, str] = {}
_STRIKES: dict[bytes, tuple[int, float]] = {}
_BAN_LOCK = threading.Lock()


def _hkey(pattern: str) -> bytes:
    return hashlib.blake2b(pattern.encode("utf-8", "surrogatepass"), digest_size=16).digest()


def _remember(table: dict, key: bytes, value: Any) -> None:
    table.pop(key, None)
    table[key] = value
    while len(table) > MAX_REMEMBERED:
        table.pop(next(iter(table)))


def is_bad(pattern: str, flags: int = 0) -> str | None:
    """Why `pattern` is refused after running too long in the worker (BAN_STRIKES times), else None. (`flags`: for
    symmetry with pattern_problem; a pattern that timed out with any flags is refused with all of them.)"""
    return _BAD.get(_hkey(pattern)) if isinstance(pattern, str) else None


def strike(pattern: str) -> str | None:
    """Count one confirmed worker timeout against `pattern`; why it is now refused (its BAN_STRIKES-th), else None.
    Within STRIKE_GAP_S of the last counted strike it counts nothing (one check searches a pattern several times: the
    raw and the collapsed screen text, a big file's windows); a strike older than STRIKE_TTL_S is forgotten."""
    k, now = _hkey(pattern), time.monotonic()
    with _BAN_LOCK:
        if k in _BAD:
            return _BAD[k]
        n, last = _STRIKES.get(k, (0, 0.0))
        if n and now - last < STRIKE_GAP_S:
            return None
        if n and now - last >= STRIKE_TTL_S:
            n = 0
        n += 1
        if n < BAN_STRIKES:
            _remember(_STRIKES, k, (n, now))
            return None
        _STRIKES.pop(k, None)
        why = f"pattern ran longer than {int(DEADLINE_S * 1000)} ms {n} times (catastrophic backtracking)"
        _remember(_BAD, k, why)
        return why


def cooling(pattern: str) -> bool:
    """`pattern` was struck less than STRIKE_GAP_S ago: skipped until then (each search would cost a deadline)."""
    got = _STRIKES.get(_hkey(pattern)) if isinstance(pattern, str) else None
    return got is not None and time.monotonic() - got[1] < STRIKE_GAP_S


_SKIPS: contextvars.ContextVar[tuple[list, ...]] = contextvars.ContextVar("miyagi_regex_skips", default=())


@contextlib.contextmanager
def count_skips():
    """Yields [n]: how many guarded searches inside came back "no match" without an answer: a timeout, or a pattern
    skipped after a strike (cooling). A check that passes on no match (screen_absent: "no Traceback on screen") waits
    on those instead of passing while an error may be showing. Nests (an outer count sees the inner searches) and
    holds in the thread asyncio.to_thread runs the evaluation in. A lesson whose budget is spent is not counted: that
    lasts up to LESSON_WINDOW_S, and a screen_absent row waiting that long would stop the lesson."""
    box = [0]
    tok = _SKIPS.set((*_SKIPS.get(), box))
    try:
        yield box
    finally:
        _SKIPS.reset(tok)


def _note_skip() -> None:
    for box in _SKIPS.get():
        box[0] += 1


class Budget:
    """One lesson's worker timeouts and CPU time (see the module docstring). exhausted: LESSON_TIMEOUTS timeouts, or
    LESSON_CPU_S of the worker's CPU time, in the last LESSON_WINDOW_S (monotonic clock), so its other worker
    patterns don't run; a lesson that stalled once on a busy Mac gets its patterns back later, a graph of slow
    patterns costs a few seconds per window."""

    __slots__ = ("key", "times", "told", "costs", "spent", "lock")

    def __init__(self, key: Any) -> None:
        self.key, self.times, self.told = key, [], False
        self.costs: deque = deque()  # (monotonic time, CPU seconds), oldest first; `spent` is their sum
        self.spent, self.lock = 0.0, threading.Lock()

    def charge(self, cpu: float | None) -> None:
        """Count `cpu` seconds the worker spent on one of this lesson's searches."""
        if not cpu or cpu <= 0:
            return
        now = time.monotonic()
        with self.lock:
            self._expire(now)
            if self.costs and now - self.costs[-1][0] < 1.0:  # one entry per second: a long window stays small
                t, c = self.costs[-1]
                self.costs[-1] = (t, c + cpu)
            else:
                self.costs.append((now, cpu))
            self.spent += cpu

    def _expire(self, now: float) -> None:
        while self.costs and now - self.costs[0][0] >= LESSON_WINDOW_S:
            self.spent -= self.costs.popleft()[1]
        if not self.costs:
            self.spent = 0.0  # no float drift left over

    @property
    def cpu(self) -> float:
        """The worker's CPU seconds on this lesson's searches in the last LESSON_WINDOW_S."""
        with self.lock:
            self._expire(time.monotonic())
            return max(self.spent, 0.0)

    def add(self) -> None:
        self.times = [t for t in self.times if time.monotonic() - t < LESSON_WINDOW_S][-LESSON_TIMEOUTS:]
        self.times.append(time.monotonic())

    @property
    def timeouts(self) -> int:
        return sum(1 for t in self.times if time.monotonic() - t < LESSON_WINDOW_S)

    @property
    def exhausted(self) -> bool:
        if self.timeouts >= LESSON_TIMEOUTS or self.cpu >= LESSON_CPU_S:
            return True
        self.told = False
        return False


_BUDGETS: OrderedDict = OrderedDict()
_CURRENT: contextvars.ContextVar[Budget | None] = contextvars.ContextVar("miyagi_regex_budget", default=None)


def lesson_budget(key: Any) -> Budget:
    """The Budget of lesson `key` (made on first use; the 64 most recent lessons are kept)."""
    with _BAN_LOCK:
        b = _BUDGETS.get(key)
        if b is None:
            b = _BUDGETS[key] = Budget(key)
            while len(_BUDGETS) > 64:
                _BUDGETS.popitem(last=False)
        else:
            _BUDGETS.move_to_end(key)
        return b


_FALLBACK: Any = None  # a weakref.WeakMethod (or a plain callable) -> the key of the lesson now running, or None


def set_fallback(key_of: Any) -> None:
    """The Budget a guarded search uses when no budget() is active: `key_of()` (a bound method is held weakly) names
    the lesson running now (LessonSession._regex_key), so a lesson pattern searched on the event loop (a metric read
    off a run, code_gate, the notebook coach, the lesson-end summary, a target's match) counts against, and is stopped
    by, that lesson's Budget too. None: no fallback."""
    global _FALLBACK
    if key_of is None or not inspect.ismethod(key_of):
        _FALLBACK = key_of
    else:
        _FALLBACK = weakref.WeakMethod(key_of)


def _active() -> Budget | None:
    """The budget() in effect, else the fallback lesson's Budget, else None."""
    b = _CURRENT.get()
    if b is not None or (f := _FALLBACK) is None:
        return b
    if isinstance(f, weakref.WeakMethod) and (f := f()) is None:
        return None
    try:
        key = f()
    except Exception:  # noqa: BLE001 - a session being torn down: no budget, never a failed search
        return None
    return lesson_budget(key) if key is not None else None


@contextlib.contextmanager
def budget(key: Any):
    """Every guarded search inside counts against (and is stopped by) lesson `key`'s Budget. A context variable, so
    it holds in the thread asyncio.to_thread runs the evaluation in, and only there."""
    tok = _CURRENT.set(lesson_budget(key))
    try:
        yield _CURRENT.get()
    finally:
        _CURRENT.reset(tok)


class _Timeout(Exception):
    cpu: float | None = None  # CPU seconds the killed worker spent on this request (None: unknown)


class _Dead(Exception):
    pass


class _Worker:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: Any = None
        self.pid = 0  # the process that started it (a fork never shares the parent's pipes)
        self.buf = b""
        self.failed_t: float | None = None
        self.cpu: float | None = None  # the worker's CPU time at its last answer (its own process_time())
        self.last = threading.local()  # .cost: CPU seconds the worker spent on this thread's last answered request

    # ------------------------------------------------------------------ lifecycle
    def _start(self) -> bool:
        if self.failed_t is not None and time.monotonic() - self.failed_t < RETRY_SPAWN_S:
            return False
        try:
            # -B: never a .pyc written into the signed app bundle's Python (the app runs the engine with -B too)
            self.proc = _Popen([sys.executable, "-I", "-S", "-B", "-c", _CHILD], stdin=PIPE, stdout=PIPE,
                               stderr=DEVNULL, bufsize=0, close_fds=True,
                               env={"PYTHONIOENCODING": "utf-8", "LC_ALL": "C"})
            self.pid, self.buf, self.cpu = os.getpid(), b"", None
            ready = self._read_line(time.monotonic() + START_S).split()
            if not ready or ready[0] != b"ready":
                raise _Dead("no ready line")
            self.cpu = _float(ready[1]) if len(ready) > 1 else None
        except (OSError, ValueError, _Timeout, _Dead) as exc:
            log.warning("regex worker did not start (%s): shape-checked patterns run in-process", exc)
            self._kill()
            self.failed_t = time.monotonic()
            return False
        self.failed_t = None
        return True

    def _kill(self) -> float | None:
        """Kill the worker; the CPU seconds it used in all (its rusage, read as it is reaped), None if unknown."""
        p, self.proc, self.buf = self.proc, None, b""
        if p is None:
            return None
        try:
            p.kill()
        except OSError:
            pass
        cpu = _reap(p)
        try:
            p.wait(timeout=2)
        except Exception:  # noqa: BLE001 - never block a sink on a worker that won't die
            pass
        for f in (p.stdin, p.stdout):
            try:
                f.close()
            except Exception:  # noqa: BLE001
                pass
        return cpu

    def close(self) -> None:
        with self.lock:
            self._kill()

    # ------------------------------------------------------------------ one request
    def _read_line(self, deadline: float) -> bytes:
        fd = self.proc.stdout.fileno()
        while b"\n" not in self.buf:
            # past the deadline: one more look without waiting (the engine itself may have been the one stopped, and
            # the answer has been waiting since)
            left = max(deadline - time.monotonic(), 0.0)
            ready, _, _ = select.select([fd], [], [], left)
            if not ready:
                raise _Timeout
            chunk = os.read(fd, 1 << 16)
            if not chunk:
                raise _Dead("worker closed its output")
            self.buf += chunk
        line, _, self.buf = self.buf.partition(b"\n")
        return line

    def _write(self, data: bytes, deadline: float) -> None:
        fd = self.proc.stdin.fileno()
        view = memoryview(data)
        while view:
            left = max(deadline - time.monotonic(), 0.0)
            _, ready, _ = select.select([], [fd], [], left)
            if not ready:
                raise _Timeout
            n = os.write(fd, view[: 1 << 16])
            view = view[n:]

    def call(self, req: dict, limit_s: float = DEADLINE_S) -> Any:
        """The worker's answer to `req` within `limit_s`; raises _Timeout (the worker was killed; .cpu: what it spent
        on this request) or _Unavailable."""
        data = (json.dumps(req) + "\n").encode("ascii")
        self.last.cost = 0.0
        with self.lock:
            if self.proc is not None and (self.pid != os.getpid() or self.proc.poll() is not None):
                self.proc, self.buf = None, b""  # a forked child or a dead worker: start a fresh one
            if self.proc is None and not self._start():
                raise _Unavailable
            # the deadline covers writing a 64 KB text too: the worker reads it at once while idle
            deadline = time.monotonic() + limit_s + len(data) / 50e6
            try:
                self._write(data, deadline)
                line = self._read_line(deadline)
            except _Timeout as t:
                before, total = self.cpu, self._kill()
                t.cpu = max(0.0, total - before) if total is not None and before is not None else None
                raise
            except (OSError, ValueError, _Dead) as exc:
                log.warning("regex worker failed (%s); starting it again", exc)
                self._kill()
                raise _Unavailable from exc
            ans = json.loads(line)
            before, after = self.cpu, _float(ans.get("c"))
            self.cpu = after
        if after is not None and before is not None:
            self.last.cost = max(0.0, after - before)  # what this search cost (compile + search + its JSON)
        if "e" in ans:
            raise re.error(str(ans["e"]))
        return ans["r"]


class _Unavailable(Exception):
    pass


def _float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _reap(p: Any) -> float | None:
    """Reap the killed worker `p` with wait4: its CPU seconds (user + system) in all, None if they can't be read."""
    wait4 = getattr(os, "wait4", None)
    pid = getattr(p, "pid", None)
    if wait4 is None or not isinstance(pid, int):
        return None
    end = time.monotonic() + 2.0
    while True:
        try:
            got, status, ru = wait4(pid, os.WNOHANG)
        except OSError:  # ChildProcessError too: already reaped (a poll() saw it die), its CPU time is gone
            return None
        if got == pid:
            with contextlib.suppress(ValueError):
                p.returncode = os.waitstatus_to_exitcode(status)  # Popen never waits for it again
            return ru.ru_utime + ru.ru_stime
        if time.monotonic() > end:
            return None
        time.sleep(0.002)


_WORKER = _Worker()
atexit.register(_WORKER.close)
_CACHE: OrderedDict = OrderedDict()
_CACHE_LOCK = threading.Lock()


_NO = object()  # _confirm: no answer (a confirmed or unresolved timeout)


def _run(gp: GuardedPattern, op: str, text: str, pos: int, endpos: int) -> Any:
    """regs (or a list of regs for finditer) for `op` on `text`; None for no match, a timeout or a refused pattern."""
    key = (gp.pattern, gp.flags, op, text, pos, endpos) if len(text) <= CACHE_TEXT else None
    if key is not None:
        with _CACHE_LOCK:
            if key in _CACHE:
                _CACHE.move_to_end(key)
                return _CACHE[key]
    empty = [] if op == "finditer" else None
    if is_bad(gp.pattern, gp.flags):
        return empty
    if cooling(gp.pattern):  # struck a moment ago (this same check's other searches): not another deadline
        _note_skip()
        return empty
    b = _active()
    if b is not None and b.exhausted:
        if not b.told:
            b.told = True
            log.warning("lesson %r: %d regex timeouts, %.1f s of regex CPU time; its other slow-capable patterns "
                        "no longer run", str(b.key)[:60], b.timeouts, b.cpu)
        return empty
    end = min(endpos, len(text))
    req = {"p": gp.pattern, "f": gp.flags, "op": op, "t": text, "pos": pos, "end": end, "max": MAX_MATCHES}
    try:
        res = _WORKER.call(req)
        _charge(b)
    except _Timeout as t:
        res = _confirm(gp, req, b, t)
        if res is _NO:
            _note_skip()
            return empty
        _charge(b)
    except _Unavailable:
        res = _local(gp, op, text, pos, end)
    if key is not None:
        with _CACHE_LOCK:
            _CACHE[key] = res
            if len(_CACHE) > CACHE_SIZE:
                _CACHE.popitem(last=False)
    return res


def _charge(b: Budget | None) -> None:
    """Charge the CPU time the worker spent on this thread's last answer to the lesson's Budget `b`."""
    if b is not None:
        b.charge(getattr(_WORKER.last, "cost", 0.0))


def _confirm(gp: GuardedPattern, req: dict, b: Budget | None, t: _Timeout) -> Any:
    """After a timeout: the answer when the worker barely ran (the Mac stalled, not the pattern) and a second try
    within CONFIRM_S answers; else _NO, and a strike against the pattern when the worker spent CPU_SLOW_S on it (or
    its CPU time can't be read and the second try ran out too)."""
    slow = t.cpu is not None and t.cpu >= CPU_SLOW_S
    if not slow:
        try:
            return _WORKER.call(req, CONFIRM_S)
        except _Timeout as again:
            slow = again.cpu is None or again.cpu >= CPU_SLOW_S
        except _Unavailable:
            return _NO  # no worker to ask again: not a strike, and never the in-process search of a pattern that hung
    if not slow:
        # nor against the lesson's budget: one freeze of the Mac during a check (4 searches) would otherwise stop the
        # lesson's patterns for LESSON_WINDOW_S. A pattern can't land here by itself: its own cost shows as CPU time.
        log.warning("lesson pattern %r: no answer in %d ms + %d ms, but the worker barely ran (the Mac stalled): "
                    "not counted against it", gp.pattern[:80], int(DEADLINE_S * 1000), int(CONFIRM_S * 1000))
        return _NO
    if b is not None:
        b.add()
        b.charge(t.cpu)
    why = strike(gp.pattern)
    log.warning("lesson pattern %r ran past %d ms%s", gp.pattern[:80], int(DEADLINE_S * 1000),
                f": refused from now on ({why})" if why else " (a strike: not refused yet)")
    return _NO


def _local(gp: GuardedPattern, op: str, text: str, pos: int, end: int) -> Any:
    """The fallback when no worker can start: the shape-checked pattern in-process."""
    if op == "finditer":
        out = []
        for m in gp._rx.finditer(text, pos, end):
            out.append(m.regs)
            if len(out) >= MAX_MATCHES:
                break
        return out
    m = getattr(gp._rx, op)(text, pos, end)
    return m.regs if m is not None else None


class GuardedPattern:
    """A lesson pattern that matches in the worker process (see the module docstring). The same reading API as
    re.Pattern for what the engine uses."""

    __slots__ = ("_rx", "_local", "pattern", "flags", "groups", "groupindex")

    def __init__(self, rx: re.Pattern[str], linear: bool) -> None:
        self._rx = rx
        self._local = linear  # no repeat / alternation / backreference: linear in the text, run in-process
        self.pattern = rx.pattern
        self.flags = rx.flags
        self.groups = rx.groups
        self.groupindex = rx.groupindex

    def __repr__(self) -> str:
        return f"GuardedPattern({self.pattern!r})"

    def _one(self, op: str, string: str, pos: int, endpos: int) -> Any:
        if not isinstance(string, str):
            raise TypeError("expected string")
        if self._local:
            return getattr(self._rx, op)(string, pos, endpos)
        regs = _run(self, op, string, pos, endpos)
        return GuardedMatch(self, string, regs, pos, endpos) if regs is not None else None

    def search(self, string: str, pos: int = 0, endpos: int = sys.maxsize) -> Any:
        return self._one("search", string, pos, endpos)

    def match(self, string: str, pos: int = 0, endpos: int = sys.maxsize) -> Any:
        return self._one("match", string, pos, endpos)

    def fullmatch(self, string: str, pos: int = 0, endpos: int = sys.maxsize) -> Any:
        return self._one("fullmatch", string, pos, endpos)

    def finditer(self, string: str, pos: int = 0, endpos: int = sys.maxsize):
        if not isinstance(string, str):
            raise TypeError("expected string")
        if self._local:
            return self._rx.finditer(string, pos, endpos)
        return iter([GuardedMatch(self, string, r, pos, endpos) for r in _run(self, "finditer", string, pos, endpos)])

    def findall(self, string: str, pos: int = 0, endpos: int = sys.maxsize) -> list:
        if self._local:
            return self._rx.findall(string, pos, endpos)
        out = []
        for m in self.finditer(string, pos, endpos):
            if self.groups == 0:
                out.append(m.group(0))
            elif self.groups == 1:
                out.append(m.group(1) or "")
            else:
                out.append(tuple(g or "" for g in m.groups()))
        return out


class GuardedMatch:
    """A match the worker found: the spans it sent back, read on the caller's own text."""

    __slots__ = ("re", "string", "regs", "pos", "endpos")

    def __init__(self, rx: GuardedPattern, string: str, regs: Any, pos: int, endpos: int) -> None:
        self.re, self.string, self.pos, self.endpos = rx, string, pos, min(endpos, len(string))
        self.regs = tuple((int(a), int(b)) for a, b in regs)

    def _index(self, g: int | str) -> int:
        if isinstance(g, str):
            if g not in self.re.groupindex:
                raise IndexError("no such group")
            return self.re.groupindex[g]
        if not isinstance(g, int) or not 0 <= g < len(self.regs):
            raise IndexError("no such group")
        return g

    def _get(self, i: int, default: Any = None) -> Any:
        a, b = self.regs[i]
        return default if a < 0 else self.string[a:b]

    def group(self, *gs: int | str) -> Any:
        if not gs:
            return self._get(0)
        if len(gs) == 1:
            return self._get(self._index(gs[0]))
        return tuple(self._get(self._index(g)) for g in gs)

    def __getitem__(self, g: int | str) -> Any:
        return self._get(self._index(g))

    def groups(self, default: Any = None) -> tuple:
        return tuple(self._get(i, default) for i in range(1, len(self.regs)))

    def groupdict(self, default: Any = None) -> dict:
        return {name: self._get(i, default) for name, i in self.re.groupindex.items()}

    def start(self, g: int | str = 0) -> int:
        return self.regs[self._index(g)][0]

    def end(self, g: int | str = 0) -> int:
        return self.regs[self._index(g)][1]

    def span(self, g: int | str = 0) -> tuple[int, int]:
        return self.regs[self._index(g)]

    @property
    def lastindex(self) -> int | None:
        hit = [i for i in range(1, len(self.regs)) if self.regs[i][0] >= 0]
        return max(hit) if hit else None

    @property
    def lastgroup(self) -> str | None:
        li = self.lastindex
        return next((n for n, i in self.re.groupindex.items() if i == li), None) if li is not None else None

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"<GuardedMatch span={self.regs[0]} match={self.group(0)!r}>"
