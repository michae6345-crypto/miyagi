"""A run step's terminal-command typo -> an instant off-track card from cmd_typos (no model call), Nov 15 live test.

main.py's /vscode/event hands every VS Code `command_end` (and every `save`) here. On a lesson run step, a command that
failed or doesn't match the step's command goes through cmd_typos.diagnose; a match goes out as the usual off-track
card (title, body, "Retype as python3 nn.py" box on the terminal's command line, or "Delete this line" on the line of
nn.py that holds the command). While that card stands, the coach holds (holds()); anything not matched is left to it.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from . import cmd_typos

log = logging.getLogger("orchestrator.session")

HOLD_S = 120.0  # how long the deterministic card holds the coach back (a new command / save re-decides sooner)


def holds(session: Any, step: dict | None) -> bool:
    """Is a typo card standing on this step? Then the coach doesn't diagnose the same failure again (it paid ~3 s and
    a Sonnet call for the "python 3 nn.py" one)."""
    t = getattr(session, "_typo_card", None)
    off = getattr(session, "last_offtrack", None) or {}
    return (t is not None and step is not None and t[0] == session.step_gen and off.get("title") == t[1]
            and time.time() - t[2] < HOLD_S)


def _here(session: Any, ev: dict, c: dict) -> bool:
    """Is this command from after the step started (and not a replay)?"""
    started = (c.get("startedAt") or 0) / 1000 or float(ev.get("received") or 0)
    return started >= getattr(session, "_step_wall_t0", 0.0) - 1.0


async def on_vscode_event(session: Any, ev: dict) -> bool:
    """command_end / save from the VS Code companion -> True when a typo card went out."""
    step = getattr(session, "step", None)
    if (not isinstance(ev, dict) or step is None or not getattr(session, "lesson_mode", False)
            or getattr(session, "passed", False) or getattr(session, "awaiting_start", False)):
        return False
    expected = session._run_command(step)
    if not expected:
        return False  # a type step: nothing to compare against
    try:
        _p, file_lines = session._step_lines(step)
    except Exception:  # noqa: BLE001
        file_lines = []
    kind = ev.get("type")
    if kind == "save":  # the run command typed into nn.py (no run yet)
        v = cmd_typos.diagnose("", expected, file_lines=file_lines)
        typed = ""
    elif kind == "command_end":
        c = ev.get("command") if isinstance(ev.get("command"), dict) else None
        if c is None or not _here(session, ev, c):
            return False
        typed = str(c.get("commandLine") or "").strip()
        code = c.get("exitCode")
        out = [str(x) for x in c.get("outputTail") or []]
        v = cmd_typos.diagnose(typed, expected, output=out, exit_code=code if isinstance(code, int) else None,
                               lesson_dir=str(session.workdir), cwd=str(c.get("cwd") or "") or None,
                               file_lines=file_lines, has_python=getattr(session, "has_python", None))
        log.info("terminal command %r on %s (exit %s): %s", typed[:80], step.get("id"), code,
                 v["kind"] if v else "no typo (the coach decides)")
        if v is None:
            session._typo_card = None  # a real error / the right command: the coach may speak
    else:
        return False
    if v is None:
        return False
    await post(session, step, v, typed)
    return True


async def post(session: Any, step: dict, v: dict, typed: str) -> None:
    """The verdict as the off-track card (session._offer_offtrack: kept while a card is held, the box after it)."""
    gen = session.step_gen
    failed = [r for r in getattr(session, "last_failed", None) or [] if r.get("checkId")]
    ids = {r["checkId"] for r in failed}
    full = {"stepId": step.get("id"), "severity": "fail", "title": v["title"], "body": v["body"],
            "actions": ["hint"], "source": "typo", "level": 1}
    shown = dict(full)
    # the box: the line the learner typed (the terminal's last command line), or the line of nn.py holding the command
    full["anchor"] = v.get("anchor") or typed
    full["anchorCaption"] = v["caption"]
    session._typo_card = (gen, full["title"], time.time())
    log.info("typo card (%s): %s -> %s", v["kind"], typed[:80] or f"line {v.get('line')}", v["fix"])
    await session._offer_offtrack(gen, step, failed, ids, 1, full, shown)


def anchor_for(full: dict) -> tuple[str, str] | None:
    """session._offtrack_anchor's answer for a typo card: (the text to box, its caption); None for a coach card."""
    if full.get("source") != "typo" or not full.get("anchor"):
        return None
    return str(full["anchor"]), str(full.get("anchorCaption") or "")

