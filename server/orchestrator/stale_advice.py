"""Advice that outlived the code it was about, and a file fix that went to the clipboard (QA 11-15, the curated
neural-network lesson, step nn4 "Train it", engine-live.log 02:56-03:00).

The learner typed `python3 nn.py` into nn.py (line 41): they couldn't see the terminal. Two off-tracks said to delete
it. They deleted it without saving, and the engine kept saying it: the speak ladder re-sent the cached diagnosis, a
kept one went out late, Check's "Not yet" quoted its title, and the answer to "whats going wrong rn" was handed the
old card (and the disk) and said "Delete the python3 nn.py line, around line 41" once more. Do it for me on that card
answered "Command copied: paste it in your terminal (⌘V)": the coach had put the line to delete in `diff.command`.
Earlier (Bug C) a judge's "Not yet: Fix import to numpy as np; save nn.py" stayed up over three green rows.

    evidence(card)                      the code a card's advice rests on: the diff's lines it changes / deletes, the
                                        code (or line N) it says to delete, a shell command typed into the file
    await fresh(s, step)                VS Code's text of the step's file this tick (the coach's code excerpt reads it)
    note(s, step, card, code)           the diagnosis read `code`: its evidence is later checked against that too
    await state(s, step, card)          "" it stands | gone from VS Code's text: "unsaved" fixed, not saved |
                                        "edited" changed some other way, not saved | "gone" saved
    await drop_offtrack(s, step, full)  before an off-track goes out (new, the ladder's re-send, a kept one)
    await check_pressed(s, step)        Check: a stale off-track is forgotten (fixed, unsaved: "You fixed it")
    await before_answer(s, step)        a question / Explain: VS Code's exact text now, no stale card in its context
    await answer(s, step, card)         the answer never repeats a fix whose line is gone
    await line_fix(s, step, diff)       Do it for me: a line to delete is a previewed patch, never the clipboard
    await checks_win(s, step, gen)      Check: every row green -> no "Not yet" that contradicts them (Bug C)
    judge_contradicts(s, card)          the judge's own "Not yet" over all-green rows: not sent

VS Code's text comes from the companion extension (editor_text.EditorBuffers); without it the file on disk decides,
so nothing here drops a card it can't disprove; a check that can't read either leaves the card as it was.
"""

from __future__ import annotations

import difflib
import logging
import re
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger("orchestrator.stale_advice")

DELETE = re.compile(r"\b(?:delete|remove|take\s+out|erase|get\s+rid\s+of)\b", re.I)
TICK = re.compile(r"`([^`\n]{3,})`")
LINE_REF = re.compile(r"\blines?\s+(\d{1,5})\b", re.I)
FILE_NAME = re.compile(r"[\w./-]+\.\w{1,5}")
SEEN_MAX = 8  # diagnoses whose code is remembered (per session)


def _norm(s: Any) -> str:
    return " ".join(str(s or "").split())


def _codeish(t: str) -> bool:
    """A piece of code worth checking for (`python3 nn.py`, `W1 = np.zeros((2, 4))`), not a name or a file name."""
    t = t.strip()
    return bool(re.search(r"[\s()=\[\]{}:,+*/<>]", t)) and not FILE_NAME.fullmatch(t)


def _words(card: dict) -> str:
    return f"{card.get('title') or ''}\n{card.get('body') or ''}"


def is_deletion(diff: dict | None) -> bool:
    """A diff whose fix is to delete the learner's line(s): `yours` with no `expected` (the coach keeps that shape only
    for a deletion: diagnose._deletes_line)."""
    diff = diff or {}
    return bool(str(diff.get("yours") or "").strip()) and not str(diff.get("expected") or "").strip()


def evidence(card: dict | None) -> list[tuple[str, bool]]:
    """[(text, whole_line)]: what the card's advice rests on, as the learner's file reads it. diff.yours's lines the fix
    changes or deletes (whole lines); for a card that says to delete / remove something, the code it names in
    backticks (part of a line) and diff.command (a whole line: a shell command typed into the file). [] = nothing."""
    if not isinstance(card, dict):
        return []
    diff = card.get("diff") if isinstance(card.get("diff"), dict) else {}
    keep = {_norm(x) for x in str(diff.get("expected") or "").splitlines() if x.strip()}
    out = [(_norm(x), True) for x in str(diff.get("yours") or "").splitlines() if x.strip() and _norm(x) not in keep]
    words = _words(card)
    cmd = _norm(diff.get("command"))
    if DELETE.search(words) or (cmd and not str(diff.get("expected") or "").strip()):
        out += [(_norm(t), False) for t in TICK.findall(words) if _codeish(t)]
        if cmd:
            out.append((cmd, True))
    return list(dict.fromkeys(x for x in out if x[0]))


def _has(ev: tuple[str, bool], text: str | None) -> bool:
    if text is None:
        return False
    want, whole = ev
    for ln in text.splitlines():
        n = _norm(ln)
        if n == want or (not whole and want in n):
            return True
    return False


def _key(card: dict | None) -> tuple:
    card = card or {}
    return (card.get("stepId"), _norm(card.get("title")))


def note(s: Any, step: dict, card: dict | None, code: str | None) -> None:
    """The diagnosis `card` was made from `code` (VS Code's text / the file / the screen): remember it, so its evidence
    counts as "was there" even after the learner fixed and saved it (then neither the editor nor the disk has it)."""
    if not isinstance(card, dict) or not code:
        return
    seen = getattr(s, "_advice_seen", None)
    if not isinstance(seen, dict):
        seen = s._advice_seen = {}
    key = _key({**card, "stepId": card.get("stepId") or step.get("id")})
    seen.pop(key, None)
    seen[key] = code
    while len(seen) > SEEN_MAX:
        seen.pop(next(iter(seen)))


def _path(s: Any, step: dict, diff: dict | None = None) -> Path | None:
    """The file the advice is about: the diff's file, else the step's, in the lesson folder."""
    from . import workspace as wsmod

    name = str((diff or {}).get("file") or "") or (s._step_file(step) or step.get("file") or "")
    if not name or not getattr(s, "workdir", None):
        return None
    titles = [getattr(w, "title", "") or "" for w in getattr(getattr(s, "last_obs", None), "windows", None) or []]
    try:
        return wsmod.resolve_file(s.workdir, name, titles)
    except Exception:  # noqa: BLE001
        return None


def _disk(path: Path | None) -> str | None:
    try:
        return path.read_text(errors="replace") if path is not None and path.is_file() else None
    except OSError:
        return None


async def _buffer(s: Any, path: Path | None, anew: bool = False) -> str | None:
    """VS Code's exact text of `path` (unsaved edits included), None when the extension has no tab of it (then the
    disk is its text). anew: forget this tick's reads first (Check / a question: the text now)."""
    bufs = getattr(s, "_buffers", None)
    if bufs is None or path is None:
        return None
    try:
        if anew:
            bufs.clear()
        await bufs.refresh([path], getattr(s, "workdir", None))
        text = bufs.text(path)
        return bufs.unsaved_text(path) if text is None else text
    except Exception:  # noqa: BLE001 - no editor text: the disk decides
        log.info("stale_advice: no editor text for %s", path)
        return None


async def fresh(s: Any, step: dict) -> None:
    """Read VS Code's text of the step's file now (at most once a tick), so _code_excerpt hands the coach the editor's
    exact text instead of falling back to the disk after a read older than editor_text.MAX_AGE_S."""
    try:
        await _buffer(s, _path(s, step))
    except Exception:  # noqa: BLE001 - the excerpt falls back to the disk, as before
        log.info("stale_advice: no fresh editor text for %s", step.get("id"))


async def state(s: Any, step: dict, card: dict | None, anew: bool = False) -> str:
    """Is the card's advice still about the learner's code? "" yes (or it can't be told). Its line is gone from VS
    Code's text (else the file's): "unsaved" the editor differs from the disk and has what the card asked for (a
    deletion: nothing; a change: its new line), "edited" the editor differs from the disk otherwise, "gone" saved."""
    ev = evidence(card)
    words = _words(card or {})
    refs = [int(n) for n in LINE_REF.findall(words)] if DELETE.search(words) else []
    if not ev and not refs:
        return ""
    path = _path(s, step, (card or {}).get("diff") if isinstance((card or {}).get("diff"), dict) else None)
    if (path is not None and path.suffix.lower() == ".ipynb") or \
            (path is None and _step_name(s, step).lower().endswith(".ipynb")):
        return _notebook_state(s, step, card, ev, path)
    if path is None:
        return ""
    disk = _disk(path)
    buf = await _buffer(s, path, anew)
    if disk is not None and refs:  # "delete … around line 41": what line 41 of the file reads
        lines = disk.splitlines()
        ev += [(_norm(lines[n - 1]), True) for n in refs if 0 < n <= len(lines) and _codeish(lines[n - 1])]
    seen = (getattr(s, "_advice_seen", None) or {}).get(_key(card))
    ev = [e for e in ev if _has(e, seen) or _has(e, disk)]  # it really was in their code (never a misquote)
    cur = buf if buf is not None else disk
    if not ev or cur is None or any(_has(e, cur) for e in ev):
        return ""
    if buf is None or disk is None or buf == disk:
        return "gone"
    diff = (card or {}).get("diff") if isinstance((card or {}).get("diff"), dict) else {}
    want = [(_norm(x), True) for x in str(diff.get("expected") or "").splitlines() if x.strip()]
    return "unsaved" if all(_has(w, buf) for w in want) else "edited"


def _step_name(s: Any, step: dict) -> str:
    fn = getattr(s, "_step_file", None)
    try:
        return str((fn(step) if fn is not None else None) or step.get("file") or "")
    except Exception:  # noqa: BLE001
        return str(step.get("file") or "")


def _notebook_source(s: Any, step: dict, path: Path | None) -> str | None:
    """A notebook's cells as text (its file is JSON; the coach read its cells), None when it can't be read."""
    try:
        from server.checks.notebook import find_notebook, read_notebook

        if path is None or not path.is_file():
            path = find_notebook(getattr(s, "workdir", None), [_step_name(s, step)])
        nb = read_notebook(path)
        return nb.source_text if nb is not None else None
    except Exception:  # noqa: BLE001 - can't read it: the card stands
        log.info("stale_advice: no notebook text for %s", step.get("id"))
        return None


def _notebook_state(s: Any, step: dict, card: dict | None, ev: list[tuple[str, bool]], path: Path | None) -> str:
    """t11 (s2: "load_dat() should be load_data()" stayed known after the fix passed): a notebook diagnosis is stale
    when the code it rests on was in the cells (or in what the coach read) and no cell has it now: "gone" (the lesson
    folder autosaves the notebook, so its cells are VS Code's). Never from a line number (cells have their own)."""
    if not ev:
        return ""
    src = _notebook_source(s, step, path)
    seen = (getattr(s, "_advice_seen", None) or {}).get(_key(card))
    ev = [e for e in ev if _has(e, seen) or _has(e, src)]  # it really was in their code (never a misquote)
    if not ev or src is None or any(_has(e, src) for e in ev):
        return ""
    return "gone"


def _name(s: Any, step: dict, card: dict | None = None) -> str:
    diff = (card or {}).get("diff") if isinstance((card or {}).get("diff"), dict) else None
    p = _path(s, step, diff)
    return p.name if p is not None else Path(s._step_file(step) or step.get("file") or "").name


def save_card(step: dict, name: str, st: str, kind: str = "step") -> dict:
    """The line the card was about is gone from the editor, not saved yet: say it plainly. "unsaved" (the fix the card
    asked for is in the editor): "You fixed it / Save nn.py (⌘S)."; "edited" (changed some other way): no claim."""
    if st == "unsaved":
        return {"stepId": step["id"], "kind": kind, "title": "You fixed it", "body": f"Save {name} (⌘S)."}
    return {"stepId": step["id"], "kind": kind, "title": f"Save {name}", "body": f"Save {name} (⌘S) so I can check it."}


def gone_card(step: dict, name: str, kind: str = "answer") -> dict:
    """The line the card was about is gone from the saved file too."""
    return {"stepId": step["id"], "kind": kind, "title": "Already gone",
            "body": f"{name} no longer has that line. Press Check to see where this step stands."}


def _forget_coach(step_id: str | None, title: str) -> None:
    """The coach's own copy of the diagnosis (hints, Explain and Do it for me fall back to it)."""
    mod = sys.modules.get("server.coach.diagnose")
    last = getattr(mod, "LAST", None)
    if isinstance(last, dict) and step_id in last and _norm((last.get(step_id) or {}).get("title")) == title:
        last.pop(step_id, None)


async def forget(s: Any, step: dict, card: dict) -> None:
    """Never repeat this diagnosis: not as the off-track, not from the ladder's cache, not kept for later, not in the
    coach's context. Its box goes with it."""
    key = _key(card)
    if s.last_offtrack is not None and _key(s.last_offtrack) == key:
        s.last_offtrack = None
    if getattr(s, "full_card", None) is not None and _key(s.full_card) == key:
        s.full_card = None
    pend = getattr(s, "_pending_offtrack", None)
    if pend is not None and _key(pend.get("full")) == key:
        s._pending_offtrack = None
    if getattr(s, "_offtrack_key", None) and _norm(s._offtrack_key[-1]) == key[1].lower():
        s._offtrack_key = None  # the same mistake made again later is a new card
    _forget_coach(key[0], key[1])
    (getattr(s, "_advice_seen", None) or {}).pop(key, None)
    track = getattr(s, "spot_track", None)
    if track:
        lines = [e for e, _ in evidence(card)]
        try:
            lines.append(s._offtrack_anchor(step, card)[0])
        except Exception:  # noqa: BLE001 - the evidence lines alone decide
            log.info("stale_advice: no anchor for %r", card.get("title"))
        if track[0] in {re.escape(x) for x in lines if x} | {re.escape(_norm(x)) for x in lines if x}:
            s.spot_track = None
    own = getattr(s, "_spot_owner", None)
    if own and own[0] == "offtrack" and getattr(s, "spot_rect", None) is not None and s.last_offtrack is None:
        s.spot_track = None
        await s.emit("spotlight", {"clear": True})
    from . import advice_clear

    await advice_clear.forgotten(s, card)  # t8: the Hint / Not yet card resting on it goes too


async def drop_offtrack(s: Any, step: dict, full: dict) -> bool:
    """Before an off-track goes out (a new diagnosis, the ladder's level-3 re-send of the cached one, a kept one): its
    line gone from VS Code's text -> not sent, forgotten, and when that edit isn't saved "You fixed it / Save nn.py".
    -> True when it was dropped."""
    try:
        st = await state(s, step, full)
    except Exception:  # noqa: BLE001
        log.exception("stale_advice: off-track check failed")
        return False
    if not st:
        return False
    name = _name(s, step, full)
    log.info("off-track %r not sent: what it is about is gone from %s (%s)", full.get("title"), name, st)
    await forget(s, step, full)
    if st != "gone":
        await s._emit_card(save_card(step, name, st), window_s=60.0)
    await s._status("offtrack" if s.last_offtrack else "watching")
    return True


async def check_pressed(s: Any, step: dict) -> bool:
    """Check, before the judge: the off-track up says to delete a line VS Code no longer has -> forgotten (Check's
    "Not yet" and the notice never quote it); not saved yet -> the answer is "You fixed it / Save nn.py (⌘S)."."""
    card = s.last_offtrack
    if not card:
        return False
    try:
        st = await state(s, step, card, anew=True)
    except Exception:  # noqa: BLE001
        log.exception("stale_advice: check-time off-track check failed")
        return False
    if not st:
        return False
    log.info("check: off-track %r is stale (%s); forgotten", card.get("title"), st)
    await forget(s, step, card)
    if st == "gone":
        return False
    await s._emit_card(save_card(step, _name(s, step, card), st), window_s=2.0)
    await s._status("watching", check=True)
    return True


async def before_answer(s: Any, step: dict) -> str:
    """A question / Explain is about to be answered: VS Code's exact text of the step's file now (the coach's context
    reads it, never last tick's disk), and a diagnosis whose line is gone leaves its context. -> its state."""
    path = _path(s, step)
    await _buffer(s, path, anew=True)
    card = s.last_offtrack
    if card is None:
        mod = sys.modules.get("server.coach.diagnose")
        card = (getattr(mod, "LAST", None) or {}).get(step.get("id"))
    st = ""
    if isinstance(card, dict):
        try:
            st = await state(s, step, card)
        except Exception:  # noqa: BLE001
            log.exception("stale_advice: pre-answer check failed")
        if st:
            log.info("question: off-track %r is stale (%s); left out of the answer's context", card.get("title"), st)
            await forget(s, step, card)
    s._answer_stale = (s.step_gen, st)
    return st


async def answer(s: Any, step: dict, card: dict) -> dict:
    """The answer card: when it tells the learner to delete code VS Code no longer has, "You fixed it / Save nn.py"
    (unsaved) or "Already gone" instead (and no box on it). A stale diagnosis met before the answer with the fix
    unsaved: the answer starts with "You fixed it. Save nn.py (⌘S).". Else as it came."""
    try:
        st = await state(s, step, card)
    except Exception:  # noqa: BLE001
        log.exception("stale_advice: answer check failed")
        return card
    name = _name(s, step)
    pre = getattr(s, "_answer_stale", None)
    pre = pre[1] if pre and pre[0] == s.step_gen else ""
    if st:
        log.info("answer %r repeats a fix that is already made (%s): replaced", card.get("title"), st)
        out = {k: v for k, v in card.items() if k not in ("targets", "where", "videoJump", "citation", "diff")}
        kind = card.get("kind") or "answer"
        return {**out, **(gone_card(step, name, kind) if st == "gone" else save_card(step, name, st, kind))}
    if pre == "unsaved" and not re.search(r"⌘S|\bsave\b", str(card.get("body") or ""), re.I):
        return {**card, "body": f"You fixed it. Save {name} (⌘S). {card.get('body') or ''}".strip()}
    return card


def _compiles(text: str, path: Path) -> bool:
    try:
        compile(text, str(path), "exec")
        return True
    except (SyntaxError, ValueError):
        return False


def _find(text: str, lines: list[str], near: int | None = None) -> tuple[int, int] | None:
    """(start, end) 0-based of the contiguous lines of `text` that read `lines` (whitespace aside), the match closest
    to line `near` (1-based) when there are several."""
    want = [_norm(x) for x in lines if x.strip()]
    have = [_norm(x) for x in text.splitlines()]
    hits = [i for i in range(len(have) - len(want) + 1) if want and have[i:i + len(want)] == want]
    if not hits:
        return None
    i = min(hits, key=lambda h: abs(h + 1 - near)) if isinstance(near, int) and near > 0 else hits[0]
    return i, i + len(want)


async def line_fix(s: Any, step: dict, diff: dict) -> bool:
    """Do it for me on a card whose fix is to delete line(s) of the file (diff.yours with no expected, or a shell
    command typed into a .py file that the coach put in diff.command): the "Type this for you?" preview of that
    deletion (confirm -> _apply_patch), "Delete line 41" when VS Code holds unsaved edits, "You fixed it / Save" when
    the line is already gone from the editor. Never the clipboard. -> True when handled (False: the usual flow)."""
    if not isinstance(diff, dict) or str(diff.get("expected") or "").strip():
        return False
    path = _path(s, step, diff)
    if path is None or path.suffix.lower() == ".ipynb":
        return False
    cmd = _norm(diff.get("command"))
    if is_deletion(diff):
        targets = [x for x in str(diff.get("yours") or "").splitlines() if x.strip()]
    elif cmd and not str(diff.get("yours") or "").strip() and path.suffix == ".py":
        targets = [cmd]  # the command itself may be a line of the file: then that line is the fix (02:59:22)
    else:
        return False
    disk = _disk(path)
    buf = await _buffer(s, path, anew=True)
    cur = buf if buf is not None else disk
    if cur is None:
        return False
    line = diff.get("line") if isinstance(diff.get("line"), int) else None
    span = _find(cur, targets, line)
    unsaved = buf is not None and disk is not None and buf != disk
    if span is None:
        seen = (getattr(s, "_advice_seen", None) or {}).get(_key(s.last_offtrack))
        if not (_find(disk or "", targets) or _find(seen or "", targets)):
            return False  # never in their file (a real terminal command, a misquote): the usual flow
        log.info("Do it for me: %r is already gone from %s (%s)", targets[0], path.name, "unsaved" if unsaved else "saved")
        if s.last_offtrack:
            await forget(s, step, s.last_offtrack)
        await s._emit_card(save_card(step, path.name, "unsaved", "answer") if unsaved else gone_card(step, path.name),
                           window_s=1.0)
        await s._status("offtrack" if s.last_offtrack else "watching")
        return True
    n = span[0] + 1
    shown = _norm(targets[0])
    what = f"line {n}" if span[1] - span[0] == 1 else f"lines {n}-{span[1]}"
    if unsaved:  # VS Code holds unsaved edits: writing the file would lose them
        await s._card(step, f"Delete {what}", f"In {path.name}, delete {what} ({shown}), then save with ⌘S.",
                      kind="answer", actions=["show_me"])
        await s._status("offtrack" if s.last_offtrack else "watching")
        return True
    old = cur.splitlines(keepends=True)
    new_lines = old[:span[0]] + old[span[1]:]
    new_text = "".join(new_lines)
    if path.suffix == ".py" and _compiles(cur, path) and not _compiles(new_text, path):  # never break working code
        log.info("Do it for me: deleting %s of %s would not compile; by hand", what, path.name)
        await s._card(step, f"Delete {what}", f"In {path.name}, delete {what} ({shown}).", kind="answer",
                      actions=["show_me"])
        await s._status("offtrack" if s.last_offtrack else "watching")
        return True
    from server.safety.paths import relative_to_lesson

    rel = relative_to_lesson(getattr(s, "workdir", None), path)  # the confirm card names the file as the folder does
    s.pending_patch = {"path": path, "old": cur, "new": new_text, "line": max(1, n - 1), "first": [],
                       "result": f"Deleted {what} from {rel}."}  # (_apply_patch checks the path again)
    udiff = "".join(difflib.unified_diff(old, new_lines, f"a/{rel}", f"b/{rel}"))
    log.info("Do it for me: delete %s (%r) of %s, previewed", what, shown, rel)
    await s._card(step, "Type this for you?", f"Deletes {what} ({shown}) from {rel}.", kind="answer",
                  diff=udiff, actions=["confirm"])
    await s._status("offtrack" if s.last_offtrack else "watching")
    return True


def _all_green(s: Any) -> bool:
    rows = list(getattr(s, "last_results", None) or [])
    return bool(rows) and all(r.get("status") == "pass" for r in rows) and not getattr(s, "_code_block", None)


def judge_contradicts(s: Any, card: dict) -> bool:
    """The judge's own "Not yet" (verdict not_done) while every row the drawer shows for the step is green: not sent
    (Bug C: "Fix import to numpy as np; save nn.py" over three Passed rows). The save card / the checks decide.
    An Untitled editor tab is the exception: the judge's "Save the Untitled tab as nn.py" is the real answer."""
    if card.get("verdict") != "not_done" or not _all_green(s) or s._untitled_editor():
        return False
    log.info("judge's %r not sent: every check of the step passes", card.get("body") or card.get("title"))
    return True


async def checks_win(s: Any, step: dict, gen: int) -> bool:
    """Check, the judge said not done, every row green: no "Not yet" that contradicts them. Re-graded on VS Code's
    text now; a pass passes; a row turning red lets the usual "Not yet" name it; still green and the file unsaved (or
    not on disk) -> "Save nn.py (⌘S) and this step is done."; another folder -> its card; nothing failing anywhere ->
    the checks win: the step passes. -> True when it answered."""
    from . import editor_text

    if not _all_green(s) or s._untitled_editor() or s.awaiting_resume or getattr(s, "awaiting_start", False):
        return False
    log.info("check: the judge says not done, every row is green; re-grading %s", step.get("id"))
    s._buffers.clear()
    await s.evaluate("check")
    if s.passed or gen != s.step_gen:
        return True
    if not _all_green(s):
        return False
    path = _path(s, step)
    buf, disk = s._buffers.text(path) if path is not None else None, _disk(path)
    name = path.name if path is not None else Path(s._step_file(step) or step.get("file") or "").name
    if name and (s._save_file or s._dirty_step_file(step) or (buf is not None and buf != disk)
                 or s._file_unready(step)):
        await s._emit_card(editor_text.save_card(step["id"], name), window_s=2.0)
        await s._status("watching", check=True)
        return True
    if s._editor_state_card(step, unsaved=False):  # another lesson's folder: "Wrong folder?"
        await s._status("watching", check=True)
        return True
    if not s.last_failed:
        log.info("check: every check of %s passes; the checks win over the judge", step.get("id"))
        await s._pass_step()
        return True
    return False
