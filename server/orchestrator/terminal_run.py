"""Run it for me in VS Code's terminal: make sure the command really ran, and say how it ended.

t5 (Nov 15, step 5): Run it for me typed `python3 main.py` into a brand-new "Miyagi" terminal; the Python extension's
venv auto-activation then typed ^C (to clear the prompt) and `source .venv/bin/activate`, so the program never ran.
VS Code reported no run of it, the "Running it" card stayed up, and the screen fallback passed "Ran python3 main.py"
because the command was on screen. The lesson's VS Code settings now turn that activation off
(server.workspace.core.PYTHON_TERMINAL); this is the run path's side of the fix:

    out = await follow(vx, cmd, workdir, seq, same=command_matches, alive=..., resend=..., live=...)
    out["why"]  # "ended" (out["end"]: the command_end), "not_started", "unseen", "running" or "gone"

follow() types the command again ONCE when VS Code's shell integration is up in the lesson's window and the command
didn't start (swallowed), or it ended interrupted (exit 130, ^C) or failed right after a venv activation ran there,
within RETRY_WINDOW_S of typing it (the race, not the learner's own Ctrl+C later on). verdict() is the one rule for
"does this run count": exit 0, or the step's expected output with no error it didn't ask for; never an interrupted run.
No model calls, no HTTP of its own (the caller passes the companion client).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

log = logging.getLogger("orchestrator.terminal_run")

TERMINAL_NAME = "Miyagi"  # vscode-ext/extension.js: the one terminal Run it for me types into
POLL_S = 0.3
START_WAIT_S = 4.0  # shell integration up in that window, and our command still hasn't started: it was swallowed
SETTLE_S = 1.0  # an activation ended there and ours didn't start after it: swallowed (no need to wait START_WAIT_S)
RETRY_WINDOW_S = 8.0  # an interrupted / failed end this soon after typing it is the race, not the learner's own ^C
ACT_GRACE_S = 1.0  # a failed end: how long to look for an activation that ran right after it
UNSEEN_S = 12.0  # VS Code reported nothing from that window at all (no shell integration): stop watching
SIGINT_EXIT = 130  # 128 + SIGINT: the shell's status for ^C (Python exits that way on KeyboardInterrupt too)
_INTERRUPT = re.compile(r"^\s*\^C|^\s*KeyboardInterrupt\b")
_ACTIVATE = re.compile(r"\bactivate\b")  # `source …/.venv/bin/activate`, `conda activate x`


def interrupted(code: Any, lines: Iterable[Any] | None = ()) -> bool:
    """Stopped before it finished: exit 130 (Ctrl+C), or ^C / KeyboardInterrupt at the end of its output."""
    if code == SIGINT_EXIT:
        return True
    if code == 0:
        return False
    return any(_INTERRUPT.search(str(x)) for x in list(lines or [])[-3:])


def verdict(code: Any, lines: Iterable[Any] | None, expect: Iterable[str] = (),
            run_output: Callable[..., tuple[bool, bool]] | None = None) -> tuple[str, str]:
    """(status, detail) of the step's run row for a finished run of its command: "pass" when it exited 0, or showed
    the step's expected output with no error the step didn't ask for ("run it and see the ZeroDivisionError");
    "fail" when it crashed or exited non-zero (the coach explains it); "pending" when it was interrupted (^C, exit 130)
    or VS Code didn't report its exit status and it showed nothing the step expects: run it again, nothing to explain.
    An interrupted run never passes."""
    lines = [str(x) for x in lines or []]
    if interrupted(code, lines):
        return "pending", "it stopped before it finished"
    err, shows = run_output(lines, list(expect)) if run_output is not None else (False, False)
    if code == 0:
        return "pass", "ran without errors"
    if shows and not err:
        return "pass", "ran and showed the expected output"
    if code is None and not err:
        return "pending", "run it again so I can see it finish"
    return "fail", f"the last run stopped with exit code {code}" if code else "the run printed an error"


def shell_reports() -> bool:
    """Has VS Code's shell integration reported a command in this engine run (the companion's command_start /
    command_end)? Then a run counts only on its command_end, never on what the terminal panel shows."""
    try:
        from server.workspace import vscode_ext as vx

        return vx.last_event("command_end") is not None or vx.last_event("command_start") is not None
    except Exception:  # noqa: BLE001
        return False


def _here(ev: dict, mine: str, workdir: str) -> bool:
    """A command event from the lesson folder (session._ext_commands_ended's rule)."""
    c = ev.get("command") or {}
    cwd = os.path.realpath(str(c["cwd"])) if c.get("cwd") else ""
    return (cwd == mine or cwd.startswith(mine + os.sep) or workdir in str(c.get("commandLine") or "")
            or (not cwd and any(os.path.realpath(str(f)) == mine for f in ev.get("folders") or [])))


def terminal_live(vx: Any, workdir: str) -> bool:
    """Is shell integration up in the "Miyagi" terminal of the window that has the lesson folder open (so VS Code
    reports when a command starts)? Blocking (one /state scan, 0.3 s at most): call it in a thread."""
    try:
        st = vx.state(folder=workdir) or {}
    except Exception:  # noqa: BLE001
        return False
    mine = os.path.realpath(str(workdir))
    if not any(os.path.realpath(str(f)) == mine or mine.startswith(os.path.realpath(str(f)) + os.sep)
               for f in st.get("folders") or []):
        return False
    return any(t.get("name") == TERMINAL_NAME and t.get("shellIntegration") for t in st.get("terminals") or [])


async def follow(vx: Any, cmd: str, workdir: str, seq: int, *, same: Callable[[str, str], bool],
                 alive: Callable[[], bool], resend: Callable[[], Awaitable[Any]],
                 live: Callable[[], Awaitable[bool]] | None = None, end_wait_s: float = 900.0,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep
                 ) -> dict:
    """Follow `cmd`, just typed into the lesson window's terminal (events after `seq`), until it ends. Returns
    {"why", "end", "started", "retried"}; why: "ended" (end = its command_end), "not_started" (shell integration is up
    there and it never started, even typed twice), "unseen" (VS Code reported nothing from that window: no shell
    integration), "running" (started, still running after end_wait_s) or "gone" (alive() turned false)."""
    want = cmd.strip().splitlines()[-1].strip()
    mine = os.path.realpath(str(workdir))
    sent, cursor, probe_t = clock(), int(seq or 0), 0.0
    retried = started = activated = blind = False
    live_t: float | None = None  # when shell integration was first seen up there (an event from it, or its /state)
    act_end: float | None = None  # a venv activation ended there after ours was typed
    end: dict | None = None
    end_t: float | None = None  # when its command_end came

    def out(why: str) -> dict:
        return {"why": why, "end": end, "started": started, "retried": retried}

    async def again(why: str) -> bool:
        nonlocal sent, retried, started, activated, blind, act_end, end, end_t
        log.info("run it for me: %s %s; typing it again", want[:80], why)
        retried, started, activated, blind, act_end, end, end_t = True, False, False, False, None, None, None
        sent = clock()
        try:
            return bool(await resend())
        except Exception:
            log.exception("run it for me: typing it again failed")
            return False

    while True:
        await sleep(POLL_S)
        if not alive():
            return out("gone")
        now = clock()
        try:
            evs = vx.recent_events(cursor)
        except Exception:  # noqa: BLE001
            evs = []
        for ev in evs:
            cursor = max(cursor, int(ev.get("seq") or 0))
            c = ev.get("command")
            if ev.get("type") not in ("command_start", "command_end") or not isinstance(c, dict):
                continue
            if not _here(ev, mine, str(workdir)):
                continue
            live_t = live_t or now
            line = str(c.get("commandLine") or "").strip()
            if line and same(want, line):
                started, blind = True, False
                if ev["type"] == "command_end":
                    end = c
            elif not line:
                if ev["type"] == "command_start" and not started:
                    started = blind = True  # a start whose line VS Code doesn't know yet: maybe ours (never type twice)
            else:
                if blind and ev["type"] == "command_end":
                    started = blind = False  # that start was this other command's
                if _ACTIVATE.search(line):
                    activated = True
                    if ev["type"] == "command_end":
                        act_end = now
        if end is not None:
            code, tail = end.get("exitCode"), end.get("outputTail") or []
            end_t = end_t or now
            quick = not retried and now - sent <= RETRY_WINDOW_S
            if quick and (interrupted(code, tail) or (activated and code not in (0, None))):
                last = end
                if await again("was interrupted" if interrupted(code, tail) else "ran before the .venv was activated"):
                    continue
                end = last
            elif quick and code not in (0, None) and not activated and now - end_t < ACT_GRACE_S:
                continue  # it failed: an activation typed while it ran shows up right after it (then it ran without it)
            return out("ended")
        if started:
            if now - sent > end_wait_s:
                return out("running")
            continue
        if live_t is None and live is not None and now - probe_t >= 1.0:
            probe_t = now
            try:
                if await live():
                    live_t = now
            except Exception:
                log.debug("run it for me: terminal state unavailable", exc_info=True)
        swallowed = (act_end is not None and now - act_end >= SETTLE_S) or \
            (live_t is not None and now - max(sent, live_t) >= START_WAIT_S)
        if swallowed:
            if not retried and await again("didn't start (VS Code's shell is up)"):
                continue
            return out("not_started")
        if live_t is None and now - sent >= UNSEEN_S:
            return out("unseen")
