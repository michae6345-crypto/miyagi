""""Explain this" for text the learner selected: one Explain card in Miyagi's overlay (nothing is drawn in VS Code).

Two ways in, one answer:
  VS Code  the companion's "Miyagi: Explain this" (ctrl+cmd+E, or the editor's right-click menu) posts
           {type: "explain_selection", file, relPath, text, startLine, endLine, languageId, truncated, around}
           to POST /vscode/event; main.py hands it to explain_from_vscode().
  drawer   the app's "Explain more" pop-up sends the existing action {kind: "explain", text: <the selection>};
           LessonSession._action hands explain-with-text to answer(). Plain explain (no text) is unchanged.

Both run inside LessonSession.action("explain", text), so: proactive cards wait while the learner's question is
answered (ASK_KINDS), a failure gets the same "Couldn't reach Claude" card with Try again as a typed question, and
retry re-sends the same selection (with its file and lines, see remember / recall). One VS Code explanation at a
time: a press while one is still being answered, or the same selection again within REPEAT_S of its card, is
dropped (VS Code repeats a held keybinding and shows nothing while Claude thinks, so learners press again; each press
would otherwise be its own Sonnet call and its own card). The card: kind "explain",
title "About `<first line of the selection>`", body = the coach's explanation (server/coach/selection.py, Sonnet)
with the current step as context. Without a lesson it still answers (no step context, no status changes).
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("orchestrator.selection")

MAX_CHARS = 2000  # the extension cuts at the same length
TITLE_CHARS = 28
AROUND_CHARS = 3000
REPEAT_S = 5.0  # the same VS Code selection again this soon after its card: dropped (a held key / double press)
_LAST = "_explain_selection"  # session attribute: the last VS Code selection (retry re-sends it with its file/lines)
_RUNNING = "_explain_selection_task"  # session attribute: the VS Code explanation in flight (asyncio.Task)
_DONE = "_explain_selection_done"  # session attribute: (text, session.clock()) when its card was shown

NOTHING_SELECTED = {"kind": "answer", "title": "Nothing to explain",
                    "body": "Select the code you want explained in VS Code, then press Control-Command-E "
                            "(or right-click it and choose Miyagi: Explain this)."}


def _text(v: Any) -> str:
    """The selection as sent, minus surrounding blank lines and trailing spaces, at most MAX_CHARS."""
    return str(v or "")[:MAX_CHARS].strip("\r\n").rstrip() if isinstance(v, str) else ""


def _int(v: Any) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def card_title(text: str) -> str:
    """'About `def add(a, b):…`': the first non-empty line, squeezed and cut at ~TITLE_CHARS ("…" when cut or when
    more lines follow)."""
    lines = [" ".join(ln.replace("`", "'").split()) for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return "About this"
    head = lines[0]
    if len(head) > TITLE_CHARS:
        head = head[: TITLE_CHARS - 1].rstrip() + "…"
    elif len(lines) > 1:
        head += "…"
    return f"About `{head}`"


def from_vscode(body: dict) -> dict:
    """The extension's explain_selection event -> a selection dict (see server/coach/selection.py)."""
    text = _text(body.get("text"))
    sel: dict[str, Any] = {"source": "vscode", "text": text, "title": card_title(text),
                           "truncated": bool(body.get("truncated")) or len(str(body.get("text") or "")) > MAX_CHARS}
    for k in ("file", "relPath", "languageId"):
        if isinstance(body.get(k), str) and body[k]:
            sel[k] = body[k]
    for k in ("startLine", "endLine"):
        if (n := _int(body.get(k))) is not None:
            sel[k] = n
    around = body.get("around")
    if isinstance(around, dict) and isinstance(around.get("text"), str) and around["text"].strip():
        sel["around"] = {"startLine": _int(around.get("startLine")) or 1, "text": around["text"][:AROUND_CHARS]}
    return sel


def from_drawer(text: str | None) -> dict:
    t = _text(text)
    return {"source": "drawer", "text": t, "title": card_title(t), "truncated": len(str(text or "")) > MAX_CHARS}


def remember(session: Any, sel: dict) -> None:
    setattr(session, _LAST, sel)


def recall(session: Any, text: str | None) -> dict:
    """The selection behind action explain + `text`: the last VS Code one when it is the same text (a retry, or the
    VS Code path itself), else the drawer's."""
    last = getattr(session, _LAST, None)
    if last and last.get("text") == _text(text):
        return last
    return from_drawer(text)


def offline_card(step: dict | None, sel: dict) -> dict:
    """The stub (DEMO=1 / ORCH_STUBS without the coach): the step's own idea under the selection's title."""
    body = ((step or {}).get("why") or (step or {}).get("instructions")
            or "Claude is offline, so I can't explain this selection right now.")
    return {**({"stepId": step["id"]} if step else {}), "kind": "explain", "title": sel.get("title") or "About this",
            "body": body}


def explain_from_vscode(session: Any, body: dict) -> bool:
    """POST /vscode/event {type: "explain_selection"}: answer in the background (the extension waits 300 ms at most).
    -> whether an explanation was started (False: nothing selected, and a short card says so; or the press was
    dropped because one is still being answered or this same selection's card came under REPEAT_S ago). A failed or
    stale answer shows no card and sets no mark, so pressing again after it calls Claude again."""
    sel = from_vscode(body)
    running = getattr(session, _RUNNING, None)
    if running is not None and not running.done():  # its answer is on the way: no second Sonnet call, no second card
        log.info("explain selection from VS Code: still answering the last one; press dropped")
        return False
    if not sel["text"].strip():
        step = session.step
        session._spawn(session._emit_card({**({"stepId": step["id"]} if step else {}), **NOTHING_SELECTED}))
        return False
    done = getattr(session, _DONE, None)
    if done and done[0] == sel["text"] and session.clock() - done[1] < REPEAT_S:  # just answered: the card is up
        log.info("explain selection from VS Code: same selection answered %.1fs ago; press dropped",
                 session.clock() - done[1])
        return False
    remember(session, sel)
    log.info("explain selection from VS Code: %s:%s-%s (%d chars)", sel.get("relPath") or sel.get("file"),
             sel.get("startLine"), sel.get("endLine"), len(sel["text"]))
    setattr(session, _RUNNING, session._spawn(session.action("explain", sel["text"])))
    return True


async def answer(session: Any, step: dict | None, text: str) -> None:
    """Action explain with text (from LessonSession._action): one Explain card about the selection, not queued with
    the engine's own cards (it's the learner asking)."""
    sel = recall(session, text)
    session._record("question", {"kind": "explain_selection", "source": sel["source"], "text": sel["text"][:300]}, step)
    gen = session.step_gen
    if step is not None:
        await session._status("thinking")
    ctx: dict[str, Any] = {"lesson": (session.graph or {}).get("lesson", {})}
    if step is not None and sel["source"] == "drawer":  # lesson text: the learner's own code helps relate it
        ctx["code"], ctx["file"] = session._code_excerpt(step, limit=4000)
    card = dict(await session.m.explain_selection(step, sel, ctx))
    if step is not None and gen != session.step_gen:
        return  # the learner moved to another step meanwhile: an answer about the old one would mislead
    card["title"] = sel["title"]  # the same title live, offline and stubbed
    if step is not None:
        card["stepId"] = step["id"]
    await session._emit_card(card)
    setattr(session, _DONE, (sel["text"], session.clock()))  # a repeat press right after this card is dropped
    if step is not None:
        await session._status("offtrack" if session.last_offtrack else ("passed" if session.passed else "watching"))
