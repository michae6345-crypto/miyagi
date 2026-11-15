"""Desktop test 8 (Nov 15, "Just teach me" neural-net lesson): both "Not yet" cards went out with no `targets` (05:51:31
nn2 "Wrong sign in d_h2 tanh slope … line 25", 05:52:50 nn4 "All weights start at zero"). Adrian's app (PR #127,
core/islandPlace.ts) moves an open card off the lines an off-track is about only when the off-track carries targets, so
the nn4 card sat right on the W1 line it talked about. A lesson-mode off-track now carries the culprit region the engine
already measures, in the contract's offtrack.targets shape (screen points, top-left origin):

    targets: [{"boxId": 0, "label": <the box's caption>, "text": <the culprit line(s)>, "rect": {x, y, w, h}}]

boxId 0 = a box the engine measured (not one of the coach's set-of-mark OCR boxes; those are still never sent in lesson
mode, t5 (a) lesson_boxes._one_box). One target, the region the card is about. Where its rect comes from:
- attach(), as the off-track goes out: a run step's culprit (run_pointing.culprit: the W1..W3 init lines of a stuck run,
  the diagnosed line, a NameError's traceback line), measured where VS Code shows it now (Accessibility / gutter rows;
  lines scrolled off screen can't be under the card).
- update(), once a box is measured after the card went out: the diagnosed line (box_follow.diagnosis_spot finds it in
  the file, scrolls VS Code there and measures it after the scroll; session._offtrack_spot), the coach's streamed box,
  and the culprit box Hint / Show me put up (run_pointing.culprit_spot, after its own scroll). The same off-track goes
  out again with the targets (no voice, no record, no new card in the app: it reopens the same card), unless a card
  took its place since or a press is being answered with something else: a re-sent off-track would push that card off.
  Then the targets wait and go out when that card closes (card.closed, card_closed()).
Reconnect replay still sends the off-track without targets (session.replay, 0d7ca61): a rect from before is stale.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("orchestrator.session")

ATTACH_TIMEOUT_S = 0.6  # the rows' lookup as the card goes out; slower: the card goes now, its targets with a box later
SAME_PX = 4.0  # a re-measured rect within this of the one sent is the same (no re-send for jitter)


def target(rect: dict, label: str = "", text: str = "") -> dict:
    return {"boxId": 0, "label": " ".join(str(label or "").split())[:80], "text": str(text or "").strip(),
            "rect": {k: round(float(rect[k]), 1) for k in ("x", "y", "w", "h")}}


def _usable(rect: Any) -> bool:
    try:
        return isinstance(rect, dict) and float(rect["w"]) > 0 and float(rect["h"]) > 0
    except (KeyError, TypeError, ValueError):
        return False


def _same(a: list[dict], b: list[dict]) -> bool:
    return len(a) == len(b) and all(abs(float(x["rect"][k]) - float(y["rect"][k])) <= SAME_PX
                                    for x, y in zip(a, b) for k in ("x", "y", "w", "h"))


async def attach(s: Any, payload: dict) -> dict:
    """LessonSession.emit, a lesson's off-track (after its coach targets were dropped): + the run culprit's target when
    it is on screen. Remembered (as sent, minus targets) for update()."""
    import asyncio

    from . import run_pointing

    step, targets = s.step, []
    if step is not None and payload.get("stepId") in (None, step.get("id")):
        try:
            t = await asyncio.wait_for(run_pointing.culprit_target(s, step), ATTACH_TIMEOUT_S)
        except Exception as e:  # noqa: BLE001 - a timeout / lookup failure: the card goes out, its targets later
            log.info("offtrack targets: no culprit rect as the card goes out (%s)", e or type(e).__name__)
            t = None
        if t is not None:
            targets = [t]
    s._ot_state = {"gen": s.step_gen, "payload": {k: v for k, v in payload.items() if k != "targets"},
                   "targets": targets, "carded": False, "pending": None, "culprit": _has_culprit(s)}
    if targets:
        log.info("offtrack %r: targets %s (%s)", payload.get("title"), targets[0]["rect"], targets[0]["label"])
        return {**payload, "targets": targets}
    return payload


def carded(s: Any) -> None:
    """A card went out: it took the off-track card's place in the app's one card slot."""
    if (st := getattr(s, "_ot_state", None)) is not None:
        st["carded"] = True


def _has_culprit(s: Any) -> bool:
    """Is the standing off-track about run_pointing's culprit lines (a run step: W1..W3 of a stuck run, a diagnosed
    line, a NameError's line)? Then that culprit going away is what makes the off-track stale."""
    try:
        from . import run_pointing

        return s.step is not None and run_pointing.culprit(s, s.step) is not None
    except Exception:  # noqa: BLE001 - unknown: stale_advice decides
        return False


async def _cause_gone(s: Any, st: dict) -> str:
    """(audit) Has the code the standing off-track is about changed since its targets were measured? The culprit is
    gone (the weights start random now, the diagnosed line changed) or stale_advice says its line is gone / edited.
    Then a rerun / re-grade is next, and a re-send would bring the old "Not yet" back over the fixed code (t8b's
    advice_clear takes that card down; its card.closed must not put it back). -> why, "" while it still stands."""
    try:
        if st.get("culprit") or _has_culprit(s):
            st["culprit"] = True
            from . import run_pointing

            return "the code it points at changed" if run_pointing.culprit(s, s.step) is None else ""
        from . import stale_advice

        gone = await stale_advice.state(s, s.step, s.last_offtrack)
        return f"its line is {gone}" if gone else ""
    except Exception:  # noqa: BLE001 - can't tell: the targets stand
        log.exception("offtrack targets: staleness check failed")
        return ""


def _standing(s: Any, st: dict | None) -> bool:
    return (st is not None and getattr(s, "lesson_mode", False) and st["gen"] == s.step_gen and not s.passed
            and s.last_offtrack is not None)


async def _send(s: Any, st: dict, targets: list[dict], why: str) -> None:
    st["targets"], st["pending"] = targets, None
    log.info("offtrack %r again with targets %s (%s)", st["payload"].get("title"), targets[0]["rect"], why)
    await s._emit_raw("offtrack", {**st["payload"], "targets": targets})


async def update(s: Any, rect: Any, label: str = "", text: str = "") -> bool:
    """A box on the region the standing off-track is about was just measured: send that off-track again with it as its
    target (module doc), or keep it for when the card on top closes. -> sent now."""
    st = getattr(s, "_ot_state", None)
    if not _standing(s, st) or not _usable(rect):
        return False
    targets = [target(rect, label, text)]
    if st["targets"] and _same(targets, st["targets"]):
        return False
    from .session import _ANSWERED  # (session imports this module)

    answered = _ANSWERED.get()
    st["culprit"] = st.get("culprit") or _has_culprit(s)  # (audit) what makes these targets stale later
    if st["carded"] or getattr(s, "_asks_in_flight", 0) or (answered is not None and "offtrack" not in answered):
        st["pending"] = targets  # a card is (about to be) on top of it: sent when that card closes
        return False
    await _send(s, st, targets, "measured after the card went out")
    return True


async def card_closed(s: Any) -> None:
    """card.closed (by the learner or a timeout): the app shows the off-track card again; its waiting targets go too."""
    st = getattr(s, "_ot_state", None)
    if not _standing(s, st):
        return
    st["carded"] = False  # (an off-track card the learner closed with ✕ stays closed: the app ignores its re-sends)
    if st.get("pending"):
        if why := await _cause_gone(s, st):
            log.info("offtrack %r: no re-send with targets: %s", st["payload"].get("title"), why)
            st["pending"] = None
            return
        await _send(s, st, st["pending"], "the card on top of it closed")
