"""The lesson session's context memory (server/context): what it notes, and the block its coach prompts carry.

    context_memory.observe(s, "check.updated", payload)   # from LessonSession.emit, just before the event goes out
    context_memory.on_action(s, "skip_setup", None)       # from LessonSession.action
    context_memory.scan_soon(s, paths)                    # a save / a step start: incremental file outlines, in a thread
    context_memory.block(s, step, "explain")              # "" or "- [check s2] ..." for the coach (wrapped as data there)
    context_memory.lesson_loaded(s)                       # from LessonSession.load_graph: a fresh start forgets
    context_memory.wipe_all(s)                            # Delete my data (main.py: data.delete, config.keys)

Everything here is best effort: a failure is logged and never costs the event, the action or the coach call. Nothing
calls a model: the coach's own cards are the model summary (piggyback), the rest is rule-based (server.context.extract).
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path
from typing import Any

from server.context import extract, recall, scan, store

log = logging.getLogger("orchestrator.context_memory")

ENGINE_SESSION = secrets.token_hex(4)  # one engine run: notes of an earlier run of the same lesson stay readable
CARD_KINDS = frozenset({"explain", "answer", "hint", "step"})  # the coach's (and judge's) words, not setup chores
BUDGET = {"explain": 1200, "diagnose": 900, "judge": 600}


def _lesson_id(s: Any) -> str:
    return str(((getattr(s, "graph", None) or {}).get("lesson") or {}).get("id") or "")


def _step_id(s: Any, payload: dict | None = None) -> str:
    return str((payload or {}).get("stepId") or (getattr(s, "step", None) or {}).get("id") or "")


def _store(s: Any) -> store.ContextStore | None:
    lid = _lesson_id(s)
    if not lid or not store.enabled():
        return None
    st = getattr(s, "_ctx_store", None)
    if st is None or st.lesson_id != lid:
        st = store.ContextStore(lid, session=ENGINE_SESSION)
        try:
            s._ctx_store = st
        except AttributeError:
            pass
    return st


def lesson_loaded(s: Any) -> None:
    """LessonSession.load_graph, before its lesson.ready: a lesson that starts fresh (step 1: End then start again, Start
    new, a Demo take, a curated fresh folder) forgets the notes of its earlier run, so recall never says "s1 passed" or
    "you already did X" about a run that is gone. Only a Resumer restore (s.restoring: an engine restart's save, the
    resume card's Continue) keeps them. Never raises."""
    if not store.enabled() or getattr(s, "restoring", False):
        return
    try:
        lid = _lesson_id(s)
        if lid:
            store.wipe_lesson(lid)  # notes and file outlines; a scanner still holding them drops them (generation)
        for attr in ("_ctx_store", "_ctx_scanner"):
            if getattr(s, attr, None) is not None:
                setattr(s, attr, None)
    except Exception:  # noqa: BLE001 - memory never costs a lesson start
        log.debug("context wipe on a fresh start failed", exc_info=True)


def wipe_all(s: Any = None) -> int:
    """Delete my data, engine part: every lesson's notes and scan cache, and what the running session holds of them.
    → files removed. Never raises."""
    try:
        n = store.wipe_all()
    except Exception:  # noqa: BLE001 - the keys already went; a leftover note is logged, never a crash
        log.exception("context memory wipe failed")
        return 0
    for attr in ("_ctx_store", "_ctx_scanner"):
        try:
            if s is not None and getattr(s, attr, None) is not None:
                setattr(s, attr, None)
        except AttributeError:
            pass
    return n


def observe(s: Any, type_: str, payload: dict | None) -> None:
    """Note what an outgoing event says about the lesson. Never raises."""
    if not store.enabled():
        return
    try:
        _observe(s, type_, payload or {})
    except Exception:  # noqa: BLE001 - memory never costs an event
        log.debug("context note for %s failed", type_, exc_info=True)


def _observe(s: Any, type_: str, p: dict) -> None:
    if type_ == "lesson.ended":
        if p.get("reason") == "completed" and p.get("lessonId"):
            store.wipe_lesson(p["lessonId"])  # expires with the lesson: a finished lesson can't be resumed
        return
    st = _store(s)
    if type_ == "lesson.ready":
        store.prune()
        if st is not None:
            _note_lesson(s, st, p.get("lesson") or {})
        return
    if st is None:
        return
    step = _step_id(s, p)
    if type_ == "card" and p.get("kind") in CARD_KINDS and (p.get("title") or p.get("body")):
        summary, facts = extract.card_summary(p["kind"], p)
        st.add("coach", p["kind"], summary, facts, step=step)
    elif type_ == "card" and p.get("kind") == "setup" and (p.get("title") or p.get("body")):
        title, body = extract.short(p.get("title"), 80), extract.first_sentence(p.get("body"))
        st.add("setup", title or "card", extract.short("setup asked: " + ": ".join(x for x in (title, body) if x)))
    elif type_ == "offtrack" and not p.get("hold") and (p.get("title") or p.get("body")):
        summary, facts = extract.card_summary("offtrack", p)
        st.add("coach", "offtrack", summary, facts, step=step)
    elif type_ == "check.updated" and p.get("status") in ("pass", "fail"):
        label = extract.short(p.get("label") or p.get("checkId"), 80)
        detail = extract.short(p.get("detail"), 120) if p.get("status") == "fail" else ""
        st.add("check", str(p.get("checkId") or label), f"{label}: {'passed' if p['status'] == 'pass' else 'not yet'}"
               + (f" ({detail})" if detail else ""), {"status": p["status"]}, step=step)
    elif type_ == "step.passed":
        st.add("step", step, f"{step} {'skipped' if p.get('skipped') else 'passed'}", step=step)
    elif type_ == "step.started":
        st.add("step", step, extract.short(f"{step} started: {p.get('title') or ''}", 160), step=step)
        scan_soon(s)
    elif type_ == "setup.progress":
        if (got := extract.setup_summary(p)) is not None:
            st.add("setup", got[1].get("tool", ""), got[0], got[1])
    elif type_ == "screen.seen":
        _note_screen(s, st, p, step)


def _note_lesson(s: Any, st: store.ContextStore, shown: dict) -> None:
    """The lesson read (video, transcript or text): its title, step count and the libraries / apps it uses."""
    meta = (getattr(s, "graph", None) or {}).get("lesson") or {}
    title = shown.get("title") or meta.get("title") or ""
    libs = meta.get("libraries") or {}
    names = list(libs)[:6] if isinstance(libs, dict) else [str(x) for x in libs][:6] if isinstance(libs, list) else []
    n = len((getattr(s, "graph", None) or {}).get("steps") or [])
    summary = f"lesson: {title}" + (f"; {n} steps" if n else "") + (f"; uses {', '.join(names)}" if names else "")
    st.add("transcript", "lesson", extract.short(summary), {"libraries": names} if names else None)


def _note_screen(s: Any, st: store.ContextStore, p: dict, step: str) -> None:
    app = str(p.get("app") or "")
    if not app:
        return
    from server.screen.privacy import is_private_app

    if is_private_app(app):
        return  # never summarized (store.add refuses too)
    obs = getattr(s, "last_obs", None)
    title = next((getattr(w, "title", "") or "" for w in getattr(obs, "windows", None) or []
                  if getattr(w, "app", None) == app), "")
    lines: list[str] = []
    try:
        lines = list(((s._screen_lines() or {}) if hasattr(s, "_screen_lines") else {}).get(app) or [])
    except Exception:  # noqa: BLE001
        lines = []
    summary, facts = extract.screen_summary(app, title, lines[-80:])
    st.add("screen", app, summary, facts, step=step, app=app)


def on_action(s: Any, kind: str, text: str | None) -> None:
    """A learner's button press worth remembering (Skip setup, I have it, Run it for me ...). Never raises."""
    if not store.enabled():
        return
    try:
        got = extract.action_summary(kind, text)
        st = _store(s)
        if got is not None and st is not None:
            st.add("action", kind, got[0], got[1], step=_step_id(s))
    except Exception:  # noqa: BLE001
        log.debug("context note for action %s failed", kind, exc_info=True)


# ---------------------------------------------------------------- files
def _scan(lesson_id: str, folder: str, paths: list[str] | None, scanner: scan.FileScanner) -> int:
    changed = scanner.scan(folder, paths)
    st = store.ContextStore(lesson_id, session=ENGINE_SESSION)
    n = 0
    for f in changed:
        if scanner.wiped:  # Delete my data / a fresh start landed mid-scan: nothing read before it is noted
            break
        st.add("file", f.path, f.summary, f.facts)
        n += 1
    return n


def scan_soon(s: Any, paths: list[str] | None = None) -> None:
    """Outline new / changed lesson files in a thread (one scan at a time per session; a save during a scan is
    picked up by the next one). Never raises."""
    if not store.enabled():
        return
    lid, folder = _lesson_id(s), str(getattr(s, "workdir", "") or "")
    if not lid or not folder or not Path(folder).is_dir():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    sc = getattr(s, "_ctx_scanner", None)
    if sc is None or sc.lesson_id != lid:
        sc = scan.FileScanner(lid)
        try:
            s._ctx_scanner = sc
        except AttributeError:
            return
    busy = getattr(s, "_ctx_scan_task", None)
    if busy is not None and not busy.done():
        return  # the running scan's next turn (a save or step start) catches this change: the scan is incremental
    task = loop.create_task(asyncio.to_thread(_scan, lid, folder, list(paths) if paths else None, sc))
    task.add_done_callback(lambda t: t.cancelled() or (t.exception() and log.info(
        "context scan failed: %s", type(t.exception()).__name__)))
    try:
        s._ctx_scan_task = task
    except AttributeError:
        pass


# ---------------------------------------------------------------- the prompt block
def block(s: Any, step: dict | None, purpose: str = "explain", *, files_in_prompt: set[str] | None = None) -> str:
    """What we know so far for this lesson ("" when memory is off or nothing is known). The caller wraps it."""
    if not store.enabled():
        return ""
    try:
        exclude = {Path(f).name for f in files_in_prompt or set() if f} | {f for f in files_in_prompt or set() if f}
        return recall.what_we_know(_lesson_id(s), (step or {}).get("id"), purpose=purpose,
                                   budget=BUDGET.get(purpose, 900), exclude_files=exclude)
    except Exception:  # noqa: BLE001
        log.debug("context block failed", exc_info=True)
        return ""
