"""Desktop test 8 (Nov 15, nn4 "Train it", engine-t8.log 05:53:09-05:53:37): "Hint 1 of 2: Look at how W1, W2 and W3
start…" stayed up next to the ▷ loupe for ~15 s after the learner had started the weights random again (05:53:22),
until step 4 passed. The engine knew at once (stale_advice: "off-track 'All weights start at zero' not sent: what it
is about is gone from nn.py (gone)", and run_pointing put the ▷ box back), but nothing took the card down.

The card that a Hint / "Not yet" put in the slot is remembered with what it is about:
  - the culprit lines of a run step's "Not yet" (run_pointing.culprit: W1..W3 not random, a diagnosed line, a
    NameError's line): gone once culprit() finds none (the cause changed: a rerun is next);
  - else the off-track diagnosis up when it went out (stale_advice.state: its line is gone from VS Code's text, or
    stale_advice.forget dropped that diagnosis).
Once that is gone the card goes within ~1 s (a frame, a VS Code edit / save event, or the forget itself): the
contract has no "close this card" event, so the clear is the same card again with `dismissAfterMs` 1 (the app closes a
card on its own after that long). An off-track card ("Not yet" in the app) is cleared the same way: a step card with
its title and body, dismissAfterMs 1 (a `card` takes the off-track's place in the slot, then closes).
Nothing is cleared that another card has replaced (any later card / off-track forgets the one tracked) or the learner
closed (card.closed), so a clear never brings an old card back over a newer one.

Hooks in LessonSession (kept tiny for merges): _emit_card -> sent, _offer_offtrack -> sent_offtrack, card_seen ->
closed, on_screen -> follow; stale_advice.forget -> forgotten; main.py POST /vscode/event (dirty / save / editor) ->
follow(force=True); evaluate -> checks_moved; _pass_step -> step_passed.

Desktop test 9 (V10, video lesson s3, 06:17:46-06:19:27): "Not yet · Plot cell not executed yet, no output" stayed up
after the cells ran; nothing refreshed it. A generated / video lesson's "Not yet" (a Not yet card or the off-track)
also rests on the step's checks that failed when it went out (`checks`: {checkId: row}). Every evaluate (a frame's
background re-check, a save, a run's end, Check my work) compares them: one of them passes now -> none left failing:
the card goes; some left: the card is sent again, a "Not yet" naming only those (code_gate.not_yet_body), and that
one is tracked. A check that can't be told now (pending) changes nothing. The step passing (or Skip) clears a tracked
card before step.passed (the app's step.passed closes an off-track itself, not a card), so a "Not yet" card never
outlives its step. The curated lesson keeps its own basis (culprit lines / diagnosis) only.
"""
from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger("orchestrator.session")

CLEAR_MS = 1  # the clear's dismissAfterMs: the app closes the card right away (its own ~100 ms close)
POLL_S = 0.5  # a frame checks at most this often (VS Code's text is read through the companion)


def _advice(card: dict) -> bool:
    """A Hint, or a step judge's "Not yet": advice about the learner's code."""
    return (card.get("kind") == "hint" or card.get("verdict") == "not_done"
            or str(card.get("title") or "").strip().lower() == "not yet")


def _not_yet(card: dict) -> bool:
    """A "Not yet": the judge's / Check's card, or an off-track (the app's "Not yet"), not a Hint."""
    return card.get("verdict") == "not_done" or str(card.get("title") or "").strip().lower() == "not yet"


def _open(s: Any) -> dict[str, dict]:
    """{checkId: row} of the step's rows not passing now: evaluate's last_failed (the drawer's red rows + the other
    route's) and its results' rows that aren't green (what Check's "Not yet" body names)."""
    rows = [*(getattr(s, "last_failed", None) or []),
            *(r for r in getattr(s, "last_results", None) or [] if isinstance(r, dict) and r.get("status") != "pass")]
    out: dict[str, dict] = {}
    for r in rows:
        if isinstance(r, dict) and r.get("checkId") and str(r["checkId"]) not in out:
            out[str(r["checkId"])] = dict(r)
    return out


def _checks(s: Any, card: dict, offtrack: bool) -> dict[str, dict] | None:
    """t9 (V10): the failing checks a generated / video lesson's "Not yet" reports on (None: not tracked by checks)."""
    from . import curated

    if not (offtrack or _not_yet(card)) or curated.active(s):
        return None
    return _open(s) or None


def _basis(s: Any, step: dict, off: dict | None, checks: dict[str, dict] | None = None) -> dict | None:
    from . import run_pointing

    culprit = None
    try:
        culprit = run_pointing.culprit(s, step) if s._run_command(step) else None
    except Exception:  # noqa: BLE001 - no culprit: the diagnosis alone decides
        log.info("advice_clear: no culprit for %s", step.get("id"))
    if off is not None and off.get("stepId") not in (None, step.get("id")):
        off = None
    if culprit is None and off is None and not checks:
        return None  # nothing it is about that can go away: it stays until the step moves on / the learner closes it
    return {"culprit": (culprit or {}).get("why"), "off": dict(off) if off is not None else None,
            "checks": checks or None}


def _track(s: Any, what: str, card: dict, basis: dict | None) -> None:
    s._advice_up = ({"gen": s.step_gen, "what": what, "card": dict(card), "checked": 0.0, **basis}
                    if basis is not None else None)


def sent(s: Any, card: dict) -> None:
    """_emit_card sent `card`: it holds the slot now. A Hint / "Not yet" is tracked; any other card ends tracking."""
    step = getattr(s, "step", None)
    if step is None or card.get("stepId") not in (None, step.get("id")) or not _advice(card):
        s._advice_up = None
        return
    _track(s, "card", card, _basis(s, step, getattr(s, "last_offtrack", None), _checks(s, card, False)))


def sent_offtrack(s: Any, step: dict, full: dict, shown: dict) -> None:
    """_offer_offtrack sent the off-track card `shown` (the diagnosis `full`)."""
    _track(s, "offtrack", shown, _basis(s, step, full, _checks(s, shown, True)))


def closed(s: Any, title: str, by: str | None) -> None:
    """card.closed from the app: that card left the slot (not "hidden": a covered slot shows it again)."""
    up = getattr(s, "_advice_up", None)
    if up is None or by == "hidden":
        return
    if str(up["card"].get("title") or "").strip().casefold() == str(title or "").strip().casefold():
        s._advice_up = None


async def _gone(s: Any, step: dict, up: dict) -> str:
    from . import run_pointing, stale_advice

    if up.get("culprit"):
        _p, lines = s._step_lines(step)
        if lines and run_pointing.culprit(s, step) is None:
            return "the code it points at changed"
        return ""
    if up.get("off") is not None:
        st = await stale_advice.state(s, step, up["off"])
        return f"its line is {st}" if st else ""
    return ""


async def clear(s: Any, up: dict, why: str) -> None:
    """Take the tracked card down now (see the module doc)."""
    if getattr(s, "_advice_up", None) is not up:
        return
    s._advice_up = None
    card = up["card"]
    if up["what"] == "card":
        payload = {**card, "dismissAfterMs": CLEAR_MS}
    else:
        payload = {"stepId": card.get("stepId"), "kind": "step", "title": card.get("title") or "",
                   "body": card.get("body") or "", "dismissAfterMs": CLEAR_MS}
    log.info("advice card %r cleared: %s (t8)", card.get("title"), why)
    await s.emit("card", payload)
    use = getattr(s, "_card_in_use", None)
    if use is not None and str(use[0]).strip().casefold() == str(card.get("title") or "").strip().casefold():
        s._card_in_use = None  # the learner's own card is gone: a kept off-track may go out


async def follow(s: Any, force: bool = False) -> None:
    """A frame (at most every POLL_S) / a VS Code edit or save (force): the tracked card's cause gone -> clear it."""
    up = getattr(s, "_advice_up", None)
    if up is None:
        return
    step = getattr(s, "step", None)
    if step is None or up["gen"] != s.step_gen or s.passed:
        s._advice_up = None  # step.started / step.passed took it down in the app
        return
    if not force:  # (an edit / save event checks at once and never holds up the next frame's check)
        now = time.monotonic()
        if now - up["checked"] < POLL_S:
            return
        up["checked"] = now
    try:
        why = await _gone(s, step, up)
    except Exception:  # noqa: BLE001 - can't tell: the card stays
        log.exception("advice_clear: check failed")
        return
    if why and up["gen"] == s.step_gen and not s.passed:
        await clear(s, up, why)


async def forgotten(s: Any, card: dict) -> None:
    """stale_advice.forget dropped the diagnosis `card`: a card resting on it goes too."""
    from . import stale_advice

    up = getattr(s, "_advice_up", None)
    if up is None or up["gen"] != s.step_gen:
        return
    off = up.get("off")
    if off is not None and stale_advice._key({**off, "stepId": off.get("stepId") or card.get("stepId")}) == \
            stale_advice._key(card):
        await clear(s, up, f"its diagnosis {card.get('title')!r} is gone")


def _passes(s: Any, cid: str, now: dict[str, dict]) -> bool:
    """The row `cid` passes in evaluate's latest results, or (the other route's row) no longer fails. A row still
    pending / failing is no change."""
    if cid in now:
        return False
    rows = [r for r in getattr(s, "last_results", None) or [] if isinstance(r, dict) and str(r.get("checkId")) == cid]
    return not rows or any(r.get("status") == "pass" for r in rows)


async def checks_moved(s: Any) -> None:
    """t9 (V10): evaluate published the step's rows (a frame's background re-check, a save, a run's end, Check my work).
    A tracked "Not yet" one of whose checks passes now: none of them left failing -> it goes; some left -> it is sent
    again naming only those (and that card is tracked)."""
    up = getattr(s, "_advice_up", None)
    if up is None or not up.get("checks"):
        return
    step = getattr(s, "step", None)
    if step is None or up["gen"] != s.step_gen or s.passed:
        return
    was: dict[str, dict] = up["checks"]
    now = _open(s)
    moved = [cid for cid in was if _passes(s, cid, now)]
    if not moved:
        return
    left = {cid: now[cid] for cid in was if cid in now}
    if not left:
        await clear(s, up, f"its checks pass now ({', '.join(moved)})")
        return
    from . import code_gate

    try:
        cmd = s._run_command(step) or ""
    except Exception:  # noqa: BLE001 - the rows alone say what's left
        cmd = ""
    card = up["card"]
    body = code_gate.not_yet_body("", list(left.values()), sid=str(step.get("id")), cmd=cmd)
    acts = [a for a in card.get("actions") or [] if a in ("hint", "show_me", "skip_step", "run_command", "check_step")]
    kind = card.get("kind") if up["what"] == "card" and card.get("kind") else "step"
    again = {"stepId": step.get("id"), "kind": kind, "verdict": "not_done", "title": "Not yet", "body": body,
             **({"actions": acts} if acts else {})}
    log.info("advice card %r sent again: %s pass now, still failing %s (t9)", card.get("title"), moved, list(left))
    await s.emit("card", again)
    _track(s, "card", again, {"culprit": None, "off": None, "checks": left})
    use = getattr(s, "_card_in_use", None)
    if use is not None and str(use[0]).strip().casefold() == str(card.get("title") or "").strip().casefold():
        s._card_in_use = (again["title"], use[1], use[2])  # still the learner's own card, now with what's left


async def step_passed(s: Any) -> None:
    """t9 (V10): the step passed / was skipped: a tracked Hint / "Not yet" card goes now (the app's step.passed closes
    the off-track, not a card; step.started only clears it later, and not at all while the next part builds)."""
    up = getattr(s, "_advice_up", None)
    if up is None:
        return
    if up["gen"] != s.step_gen or up["what"] == "offtrack":
        s._advice_up = None  # the app's step.passed closes the off-track itself
        return
    await clear(s, up, "the step passed")
