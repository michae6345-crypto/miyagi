"""eng-agency fix round 5 (offline: no model, keys unset, no network; the only process is the regex worker's own
Python, paused with SIGSTOP to stand in for a stalled Mac)."""
from __future__ import annotations

import os
import signal
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.checks.evaluator import RunContext, evaluate_check, scan_windows
from server.checks.screen import search_screen, search_wrapped
from server.orchestrator import editor_text
from server.safety import regex_worker
from server.safety.commands import Allowed, Manual, parse_run_command
from server.safety.patterns import pattern_problem, safe_compile

pytestmark = pytest.mark.skipif(not hasattr(signal, "SIGSTOP"), reason="POSIX signals")

LOSS = r"loss:\s*[\d.]+"


def _slow(tag: str) -> str:
    return f"(?:{tag}x)?" + "-?" * 25 + "-" * 25 + "z"  # ~270 ms of CPU on SLOW_TEXT: past the 250 ms deadline


SLOW_TEXT = "# " + "-" * 25


def _warm() -> None:
    """A worker running (a search that needs it), so a stall has a process to stop."""
    assert safe_compile(LOSS).search(f"warm {uuid.uuid4().hex} loss: 1.0")
    assert regex_worker._WORKER.proc is not None


class _Stall:
    """SIGSTOP every regex worker (the running one and any restarted one) for `seconds`, then SIGCONT them: the Mac
    stalling (swap, a sleep, heavy load), not the pattern."""

    def __init__(self, seconds: float) -> None:
        self.seconds, self.stopped, self.first = seconds, set(), threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        end = time.monotonic() + self.seconds
        while time.monotonic() < end:
            p = regex_worker._WORKER.proc
            if p is not None and p.pid not in self.stopped:
                try:
                    os.kill(p.pid, signal.SIGSTOP)
                    self.stopped.add(p.pid)
                except ProcessLookupError:
                    pass
                self.first.set()
            time.sleep(0.002)
        for pid in self.stopped:
            try:
                os.kill(pid, signal.SIGCONT)
            except ProcessLookupError:
                pass

    def __enter__(self) -> _Stall:
        _warm()
        self.thread.start()
        assert self.first.wait(2.0)
        return self

    def __exit__(self, *exc) -> None:
        self.thread.join()


def _struck(p: str) -> bool:
    return regex_worker._hkey(p) in regex_worker._STRIKES or regex_worker.is_bad(p) is not None


# ------------------------------------------------------------------ 1. a stall is never a strike

def test_a_short_stall_answers_on_the_second_try_and_strikes_nothing(monkeypatch):
    """The reviewer's probe: the worker can't answer for 0.6 s. search_wrapped answers (the second try waits
    CONFIRM_S), and the pattern is neither struck nor refused."""
    text = f"epoch 3 {uuid.uuid4().hex} loss: 0.125"
    limits, real = [], regex_worker._WORKER.call

    def call(req, limit_s=regex_worker.DEADLINE_S):
        limits.append(limit_s)
        return real(req, limit_s)

    with _Stall(0.6):
        monkeypatch.setattr(regex_worker._WORKER, "call", call)
        t0 = time.monotonic()
        m = search_wrapped(LOSS, text)
        took = time.monotonic() - t0
    assert m and m.group(0) == "loss: 0.125"
    assert limits == [regex_worker.DEADLINE_S, regex_worker.CONFIRM_S]  # it did time out once, then answered
    assert took < regex_worker.DEADLINE_S + regex_worker.CONFIRM_S + 1.0
    assert not _struck(LOSS) and pattern_problem(LOSS) is None and safe_compile(LOSS)


def test_a_long_stall_is_no_answer_but_never_a_strike_or_a_ban(monkeypatch):
    """A stall that outlasts the second try too (the worker never ran: its CPU time says so): no answer, counted as
    a skip, never a strike. (A worker stopped while it starts waits START_S for its ready line, so this stall is
    the worker's answers, not its start.)"""
    p = r"loss:\s*[\d.]+\s*(?:ok|done)?"
    _never_answers(monkeypatch)
    key = ("long-stall", uuid.uuid4().hex)
    with regex_worker.budget(key) as b, regex_worker.count_skips() as skipped:
        for _ in range(3):  # three frames of one check (raw, collapsed, joined, punctuation each): no answer
            assert search_wrapped(p, f"no loss here {uuid.uuid4().hex}") is None
    assert skipped[0] >= 3 and b.timeouts == 0  # nor against the lesson: a frozen Mac never stops its checks
    assert not _struck(p) and pattern_problem(p) is None
    monkeypatch.undo()
    assert safe_compile(p).search(f"{uuid.uuid4().hex} loss: 2.5 done")  # after the stall it answers as before


def test_a_timeout_reads_back_the_cpu_the_worker_spent():
    req = {"p": _slow(uuid.uuid4().hex[:6]), "f": 0, "op": "search", "t": SLOW_TEXT, "pos": 0,
           "end": len(SLOW_TEXT), "max": 10}
    with pytest.raises(regex_worker._Timeout) as busy:
        regex_worker._WORKER.call(req)
    assert busy.value.cpu is not None and busy.value.cpu > 0.05  # it was backtracking the whole time
    with _Stall(0.6):
        with pytest.raises(regex_worker._Timeout) as idle:
            regex_worker._WORKER.call({**req, "p": LOSS, "t": f"x {uuid.uuid4().hex}"})
    assert idle.value.cpu is not None and idle.value.cpu < 0.05  # stopped: it never ran


def test_a_timeout_whose_cpu_time_cant_be_read_is_asked_again(monkeypatch):
    calls = []
    real = regex_worker._WORKER.call

    def call(req, limit_s=regex_worker.DEADLINE_S):
        calls.append(limit_s)
        if len(calls) == 1:
            raise regex_worker._Timeout()  # cpu None: unknown
        return real(req, limit_s)

    monkeypatch.setattr(regex_worker._WORKER, "call", call)
    p = r"acc(?:uracy)?:\s*\d+"
    assert safe_compile(p).search(f"{uuid.uuid4().hex} accuracy: 97")
    assert calls == [regex_worker.DEADLINE_S, regex_worker.CONFIRM_S] and not _struck(p)


# ------------------------------------------------------------------ 1. one check is one strike; strikes expire

def test_one_check_is_one_strike_and_the_pattern_rests_after_it():
    p = _slow(uuid.uuid4().hex[:6])
    t0 = time.monotonic()
    assert search_wrapped(p, SLOW_TEXT + "\n# more") is None  # up to 4 searches: one strike, the rest skipped
    assert regex_worker._STRIKES[regex_worker._hkey(p)][0] == 1 and regex_worker.is_bad(p) is None
    assert regex_worker.cooling(p)
    for _ in range(5):  # more frames inside STRIKE_GAP_S: skipped at once, never another deadline or strike
        assert search_screen(p, SLOW_TEXT) is None
    assert time.monotonic() - t0 < 2 * regex_worker.DEADLINE_S + 1.5
    assert regex_worker._STRIKES[regex_worker._hkey(p)][0] == 1 and pattern_problem(p) is None


def test_a_slow_pattern_is_still_refused_after_two_checks_apart(monkeypatch):
    p = _slow(uuid.uuid4().hex[:6])
    real, offset = time.monotonic, [0.0]
    monkeypatch.setattr(regex_worker.time, "monotonic", lambda: real() + offset[0])
    assert search_screen(p, SLOW_TEXT) is None and regex_worker.is_bad(p) is None
    offset[0] += regex_worker.STRIKE_GAP_S + 0.1
    assert search_screen(p, SLOW_TEXT) is None
    assert regex_worker.is_bad(p) and pattern_problem(p) and "longer than" in pattern_problem(p)


def test_old_strikes_expire(monkeypatch):
    p = f"never-run-{uuid.uuid4().hex}"
    real, offset = time.monotonic, [0.0]
    monkeypatch.setattr(regex_worker.time, "monotonic", lambda: real() + offset[0])
    assert regex_worker.strike(p) is None
    assert regex_worker.strike(p) is None  # the same check's second search: not counted
    offset[0] += regex_worker.STRIKE_TTL_S + 1  # hours later: the old strike is gone
    assert regex_worker.strike(p) is None and regex_worker.is_bad(p) is None
    assert regex_worker._STRIKES[regex_worker._hkey(p)][0] == 1
    offset[0] += regex_worker.STRIKE_GAP_S + 1  # a second strike soon after that one does ban it
    assert regex_worker.strike(p) and regex_worker.is_bad(p)


# ------------------------------------------------------------------ 2. screen_absent waits on a search that didn't answer

def _never_answers(monkeypatch):
    def call(req, limit_s=regex_worker.DEADLINE_S):
        t = regex_worker._Timeout()
        t.cpu = 0.0  # the worker never ran: a stall
        raise t

    monkeypatch.setattr(regex_worker._WORKER, "call", call)


NO_TRACEBACK = {"id": "c1", "type": "screen_absent", "label": "no error", "app": "Terminal",
                "pattern": r"Traceback|Error:"}


def test_screen_absent_waits_when_its_search_timed_out(monkeypatch):
    screen = {"Terminal": ["$ python3 nn.py", "Traceback (most recent call last):", f"  {uuid.uuid4().hex}"]}
    _never_answers(monkeypatch)
    r = evaluate_check(NO_TRACEBACK, RunContext(screen=screen))
    assert r["status"] == "pending" and "checking again" in r["detail"]
    assert not _struck(NO_TRACEBACK["pattern"])
    monkeypatch.undo()
    assert evaluate_check(NO_TRACEBACK, RunContext(screen=screen))["status"] == "fail"  # answered: the error shows
    clean = {"Terminal": ["$ python3 nn.py", f"done {uuid.uuid4().hex}"]}
    assert evaluate_check(NO_TRACEBACK, RunContext(screen=clean))["status"] == "pass"


def test_screen_absent_on_a_run_output_waits_too(monkeypatch):
    _never_answers(monkeypatch)
    ctx = RunContext(screen={"Code": ["x = 1"]}, exit_code=1,
                     output_tail=["Traceback (most recent call last):", f"ValueError: {uuid.uuid4().hex}"])
    assert evaluate_check(NO_TRACEBACK, ctx)["status"] == "pending"


# ------------------------------------------------------------------ 3. pip's user-install fallback without a .venv

def test_a_python_without_a_lesson_venv_keeps_pips_user_install(tmp_path):
    res = parse_run_command("python3 -m pip install numpy", tmp_path)
    assert isinstance(res, Allowed) and res.argv == ("python3", "-m", "pip", "install", "numpy")
    (tmp_path / "test.py").write_text("print('a learner test')\n")  # pip never imports `test`
    assert parse_run_command("python3 -m pip install numpy", tmp_path).argv[1] == "-m"


@pytest.mark.parametrize("make", ["pip.py", "random.py", "JSON.py", "email/__init__.py", "pip/", "ssl.cpython-312.so",
                                  "tempfile.pyc"])
def test_without_a_venv_a_lesson_file_pip_would_import_is_manual(tmp_path, make):
    target = tmp_path / make
    if make.endswith("/"):
        target.mkdir()
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("print('HIJACKED')\n")
    (tmp_path / "requirements.txt").write_text("numpy\n")
    for cmd in ("python3 -m pip install numpy", "python -m pip install -r requirements.txt"):
        res = parse_run_command(cmd, tmp_path)
        assert isinstance(res, Manual) and not res.structural, (cmd, res)
        assert make.split("/")[0] in res.reason
    assert parse_run_command("pip install numpy", tmp_path).argv == ("pip", "install", "numpy")  # never on its path


def test_a_plain_folder_named_like_a_module_is_not_a_package(tmp_path):
    (tmp_path / "email").mkdir()  # no __init__.py: a namespace portion never wins over the real email package
    (tmp_path / "email" / "notes.txt").write_text("hi\n")
    assert isinstance(parse_run_command("python3 -m pip install numpy", tmp_path), Allowed)


def test_with_the_lesson_venv_pip_runs_isolated_even_next_to_a_pip_py(tmp_path):
    (tmp_path / "pip.py").write_text("print('HIJACKED')\n")
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    os.symlink(sys.executable, tmp_path / ".venv" / "bin" / "python")
    for cmd in ("python3 -m pip install numpy", "python3 -I -m pip install numpy", ".venv/bin/python -m pip install numpy"):
        res = parse_run_command(cmd, tmp_path)
        assert isinstance(res, Allowed) and res.argv[1:4] == ("-I", "-m", "pip"), (cmd, res)
        assert parse_run_command(res.command, tmp_path).argv == res.argv  # the card's command parses to itself


# ------------------------------------------------------------------ 4. a VS Code buffer is searched in windows

def test_a_big_editor_buffer_is_searched_in_64kb_windows():
    path = Path("/lesson/train.py")
    code = "import numpy as np\n" + "".join(f"print('epoch {i}', {i * 0.001:.3f})\n" for i in range(120_000))
    assert len(code) > 2_000_000
    bufs = SimpleNamespace(text=lambda p: code, dirty=lambda p: False)
    sizes: list[int] = []

    def search(pattern, text):
        sizes.append(len(text))
        return search_screen(pattern, text)

    def on_file(check, p):
        return {"checkId": "c1", "status": "fail", "detail": "not on disk"}

    check = {"id": "c1", "label": "loop", "type": "screen_contains", "app": "Code", "pattern": r"epoch 119990'"}
    res, unsaved = editor_text.check_on_editor(check, [path], bufs, search, on_file, scan_windows)
    assert res["status"] == "pass" and not unsaved
    assert sizes and max(sizes) <= 64 * 1024
    sizes.clear()  # a line near the top is past the 1 MB the windows cover: not found, but never one 2 MB request
    res, _ = editor_text.check_on_editor({**check, "pattern": r"import numpy as np"}, [path], bufs, search, on_file,
                                         scan_windows)
    assert res["status"] == "fail" and max(sizes) <= 64 * 1024 and sum(sizes) <= 1.2 * 1024 * 1024
    # without windows (a stub checks module): the whole buffer, as before
    res, _ = editor_text.check_on_editor({**check, "pattern": r"import numpy as np"}, [path], bufs, search_screen,
                                         on_file)
    assert res["status"] == "pass"
