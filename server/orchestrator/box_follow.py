"""Desktop test 7 (Nov 15, Demo mode, nn2 / nn3): a stale "Type it here" box after VS Code scrolled.

The box went up ~0.4 s after step.started from Accessibility line rows read while VS Code was still scrolled where the
last step left it. Then the step start's own jump (`code -g nn.py:<section comment>`; the companion's reveal does the
same) landed and VS Code centred the comment, a line that was already on screen: the editor scrolled 7 / 8 rows and the
box stayed at the old screen y, below the end of the file. t6's _insert_follow re-read the row on frames (~2 s apart)
and 1.0 s / 3.5 s after the box went up: a jump that landed 1.2 s in left the box on the wrong row for 2.3 s, and the
box always showed the old row first.

- settle: the step's first insertion box waits for the step start's jump to land (the companion reports the cursor on
  the jump's line, or another scroll), at most JUMP_SETTLE_S after the jump, then AX_LAG_S for Accessibility to catch up.
  One box, on the right row. No companion: no wait.
- watch: while that box is up, the lesson window's view (file, visibleRanges, lineCount) is read from the companion
  every WATCH_FAST_S for FAST_FOR_S after the box went up, then every WATCH_S (one GET /state to that window's port, a
  few ms: no OCR, no model, no Accessibility). A change (a late jump, the learner's scroll, a reload from disk that
  changed the line count) re-places the box at once (_insert_follow), and once more AX_LAG_S2 later. The companion
  0.0.5 also posts `visible` events (vscode-ext: onDidChangeTextEditorVisibleRanges): those re-place it at once
  (on_visible). Plus t6's timed re-checks (RECHECK_S): a scroll that landed before the first read, or no companion.
- refollow: the row is re-planned from the file on every re-place (a reload / a paste moved the section comment: the
  new row), and never jumps. The row scrolled off screen (outside the companion's visibleRanges): the box goes, and it
  comes back on its row when it scrolls back (never a jump: the learner's scroll stays; _maybe_respot waits too).
- the OCR "never on the comment" check (_not_on_above) never uses a frame captured before the last scroll (`fresh_ocr`).

Hooks (tiny, for merges): session.start_step -> jumped; lesson_boxes._start_line_box -> settle; _insert_spot -> watch;
_insert_follow / _refollow_insert -> hidden / refollow; _not_on_above -> fresh_ocr; _maybe_respot -> hidden;
main.py POST /vscode/event `visible` -> on_visible.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from . import where_row

log = logging.getLogger("orchestrator.session")

JUMP_SETTLE_S = 1.2  # the step start's `code -g` lands 0.3-1 s after it is asked for (test 7: ~0.5 s)
SETTLE_POLL_S = 0.08
AX_LAG_S = 0.12  # the companion saw the scroll: Accessibility's rows follow within a frame or two
AX_LAG_S2 = 0.45  # ...and once more, in case they took longer
WATCH_FAST_S = 0.15  # right after the box went up: a late jump lands about now
FAST_FOR_S = 3.0
WATCH_S = 0.5  # then, for as long as the box is up (<= 1 s, one local HTTP read)
RECHECK_S = (0.3, 1.0, 2.5)  # re-read the row (Accessibility) this long after the box went up, view change or not


# ------------------------------------------------------------------ the lesson window's view (companion extension)

def _read_view(s: Any) -> dict | None:
    """Blocking (<= 0.3 s): {file, ranges, lines, cursor, port} of the lesson's VS Code window, or None (no companion,
    no window of the lesson folder). The window's port is remembered: one GET /state, not a scan of every port."""
    folder = getattr(s, "workdir", None)
    if not folder:
        return None
    try:
        from server.workspace import vscode_ext as vx
    except Exception:  # noqa: BLE001 - the extension is a refinement
        return None
    w = None
    port = getattr(s, "_view_port", None)
    if port:
        st = vx.window_state(int(port)) if hasattr(vx, "window_state") else None
        if st and any(where_row._inside(folder, f) for f in st.get("folders") or []):
            w = st
    if w is None:
        w, _ = where_row._lesson_ext_window(folder)
    s._view_port = (w or {}).get("port")
    if w is None:
        return None
    ranges = tuple((int(r.get("startLine") or 0), int(r.get("endLine") or 0))
                   for r in w.get("visibleRanges") or [] if isinstance(r, dict))
    cur = w.get("cursor") if isinstance(w.get("cursor"), dict) else {}
    return {"file": str(w.get("file") or ""), "ranges": ranges, "lines": int(w.get("lineCount") or 0),
            "cursor": int(cur.get("line") or 0), "port": w.get("port")}


NO_VIEW_S = 2.0  # no companion window of the lesson folder answered: don't ask again for this long


async def view(s: Any) -> dict | None:
    if getattr(getattr(s, "screen", None), "reader", None) is None:
        return None  # tests / no screen reader: never the real editor
    if time.monotonic() - float(getattr(s, "_view_none_t", -1e9)) < NO_VIEW_S:
        return None
    try:
        v = await asyncio.to_thread(_read_view, s)
    except Exception:  # noqa: BLE001 - a refinement: the box stays where it is
        log.exception("box_follow: reading the lesson window's view failed")
        v = None
    s._view_none_t = time.monotonic() if v is None else -1e9
    return v


def _sig(v: dict | None) -> tuple | None:
    return None if v is None else (v["file"], v["ranges"], v["lines"])


def _same_file(a: str, b: Any) -> bool:
    try:
        return bool(a) and Path(a).resolve() == Path(str(b)).resolve()
    except OSError:
        return False


def row_visible(v: dict | None, path: Any, line: int) -> bool | None:
    """Is file line `line` of `path` on screen in the lesson window? None: can't tell (no companion, another file in
    front, no ranges)."""
    if v is None or not v["ranges"] or not _same_file(v["file"], path):
        return None
    return any(a <= line <= b for a, b in v["ranges"])


def changed(s: Any) -> None:
    """The editor scrolled / reloaded just now: an OCR frame from before it is stale (fresh_ocr)."""
    s._view_t = time.time()


def fresh_ocr(s: Any) -> bool:
    """May the OCR'd frame decide where a row is? Not when it was captured before the editor last scrolled."""
    seen = float(getattr(s, "_view_t", 0.0) or 0.0)
    if not seen:
        return True
    try:
        obs = s.screen.latest()
    except Exception:  # noqa: BLE001
        return True
    t = getattr(obs, "t", None)
    return not isinstance(t, (int, float)) or float(t) >= seen


# ------------------------------------------------------------------ settle: the step's first box after its jump

def jumped(s: Any, step: dict) -> None:
    """start_step, right after its `code -g` jump to the step's anchor (workspace.goto_target): remember it."""
    from . import workspace as wsmod
    from .session import CODE_APP_NAMES

    front = s._live_front().strip().lower()
    if front and front not in CODE_APP_NAMES:
        return  # editor.jump only jumps with VS Code in front: nothing to wait for
    try:
        loc = wsmod.target_location(s.workdir, step, missing="end")
    except Exception:  # noqa: BLE001
        loc = None
    s._step_jump = (s.step_gen, time.monotonic(), int(loc[1]) if loc else 0)


async def settle(s: Any, gen: int) -> None:
    """Before the step's first insertion box: wait for the step start's jump to land (the cursor on the jump's line,
    or the view changed), at most JUMP_SETTLE_S after the jump; then AX_LAG_S. Returns at once with no jump pending
    or no companion."""
    j = getattr(s, "_step_jump", None)
    if j is None or j[0] != gen or time.monotonic() - j[1] >= JUMP_SETTLE_S:
        return
    first = await view(s)
    if first is None:
        return
    moved = False
    v = first
    while time.monotonic() - j[1] < JUMP_SETTLE_S:
        if gen != s.step_gen or s.passed:
            return
        if v is not first and (_sig(v) != _sig(first) or (j[2] and v["cursor"] == j[2])):
            moved = True
            break
        await asyncio.sleep(SETTLE_POLL_S)
        v = await view(s) or first
    if moved:
        changed(s)
        await asyncio.sleep(AX_LAG_S)
    log.info("box_follow: step start's jump to line %s %s after %.2f s; the box goes up now (t7)", j[2],
             "landed" if moved else "not seen", time.monotonic() - j[1])


# ------------------------------------------------------------------ watch: the box up follows every scroll

def hidden(s: Any, at: tuple | None) -> bool:
    """Is the step's insertion box for `at` off screen because its row scrolled away (refollow took it down), with no
    other box up meanwhile?"""
    h = getattr(s, "_insert_hidden", None)
    w = getattr(s, "_insert_watch_task", None)  # only while the watch that brings it back runs
    return bool(at is not None and h is not None and h == at[0] == s.step_gen and s.spot_rect is None
                and not s.passed and s.step is not None and w is not None and w[0] == h and not w[1].done())


def _ours(s: Any, gen: int) -> bool:
    at = getattr(s, "_insert_at", None)
    return gen == s.step_gen and not s.passed and at is not None and at[0] == gen and (
        s._insert_box_up(at) or hidden(s, at))


def start_watch(s: Any) -> None:
    """_insert_spot placed the step's box: one watch per step."""
    gen = s.step_gen
    t = getattr(s, "_insert_watch_task", None)
    if t is not None and t[0] == gen and not t[1].done():
        return
    s._insert_watch_task = (gen, s._spawn(watch(s, gen), timer=True))


async def watch(s: Any, gen: int) -> None:
    t0 = time.monotonic()
    last = _sig(await view(s))
    rechecks = list(RECHECK_S)
    again: float | None = None
    while True:
        el = time.monotonic() - t0
        await asyncio.sleep(WATCH_FAST_S if el < FAST_FOR_S else WATCH_S)
        if not _ours(s, gen):
            return  # the step moved on, the typing / a fix / an answer owns the box now
        el = time.monotonic() - t0
        due = False
        while rechecks and el >= rechecks[0]:
            rechecks.pop(0)
            due = True
        if again is not None and el >= again:
            again, due = None, True
        v = await view(s)
        sig = _sig(v)
        if sig is not None and sig != last:
            if last is not None:
                log.info("box_follow: the lesson window's view changed (%s -> %s): the box follows (t7)",
                         _brief(last), _brief(sig))
                changed(s)
                await asyncio.sleep(AX_LAG_S)
                due, again = True, time.monotonic() - t0 + AX_LAG_S2
            last = sig
        if due and _ours(s, gen):
            s._insert_follow()


def _brief(sig: tuple) -> str:
    return f"{Path(sig[0]).name} {','.join(f'{a}-{b}' for a, b in sig[1])} ({sig[2]} lines)"


def on_visible(s: Any, ev: dict) -> None:
    """POST /vscode/event {type: "visible"} (companion 0.0.5: the editor scrolled, or its line count changed): the
    step's insertion box follows at once, and once more after Accessibility caught up."""
    folder = getattr(s, "workdir", None)
    if not folder or not any(where_row._inside(folder, f) for f in ev.get("folders") or []):
        return
    at = getattr(s, "_insert_at", None)
    if s.step is None or at is None or at[0] != s.step_gen or not (s._insert_box_up(at) or hidden(s, at)):
        return
    changed(s)
    gen = s.step_gen

    async def follow() -> None:
        for d in (AX_LAG_S, AX_LAG_S2 - AX_LAG_S):
            await asyncio.sleep(d)
            if _ours(s, gen):
                s._insert_follow()

    s._spawn(follow(), timer=True)


# ------------------------------------------------------------------ refollow: re-plan, off screen, re-place

def _replan(s: Any, step: dict, at: tuple) -> tuple:
    """The step's row from the file as it is now (a reload / paste moved the section comment). -> (gen, row): `at`
    itself when the row is the same."""
    try:
        plan = s._insert_plan(step)
        row = s._insert_row(step, plan) if plan is not None else None
    except Exception:  # noqa: BLE001 - the row placed stands
        log.exception("box_follow: re-planning the row failed")
        row = None
    old = at[1]
    if row is None or (row[0]["line"], row[1], row[4]) == (old[0]["line"], old[1], old[4]):
        return at
    log.info("box_follow: the step's row is line %s now (was %s): the file changed under the box (t7)",
             row[0]["line"], old[0]["line"])
    return at[0], row


async def refollow(s: Any, gen: int, step: dict) -> None:
    """_insert_follow's check (one at a time; a request during one asks again after it): the step's insertion box on
    its row as the editor shows it now. Never a jump, no model call."""
    while True:
        was = getattr(s, "_insert_at", None)
        if gen != s.step_gen or was is None or was[0] != gen or not (s._insert_box_up(was) or hidden(s, was)) \
                or s._code_progress(step) is not None or s._fix_active():
            return  # the step moved on, another box is up, or the typing / a fix decides the box now
        at = _replan(s, step, was)
        prog = at[1][0]
        v = await view(s)
        if row_visible(v, prog["path"], int(prog["line"])) is False:
            await _hide(s, gen, was, int(prog["line"]), v)
        else:
            spot = await s._row_box(step, *at[1], jump=False)
            r, old = (spot or {}).get("rect"), s.spot_rect
            up = s._insert_box_up(was)
            if r and gen == s.step_gen and getattr(s, "_insert_at", None) is was and (hidden(s, was) or (up and (
                    at is not was or abs(float(r["y"]) - float(old["y"])) > s.SPOT_MOVE_PX))):
                if old is not None:
                    log.info("insertion box: line %s moved %+.0f pt on screen (a scroll); the box follows it (t6/t7)",
                             prog["line"], float(r["y"]) - float(old["y"]))
                else:
                    log.info("insertion box: line %s is on screen again; the box is back (t7)", prog["line"])
                s._insert_at, s._insert_hidden = at, None
                await s._show_spot(spot, steady=True, owner="step", verify=False)
        if not getattr(s, "_insert_follow_again", False):
            return
        s._insert_follow_again = False


# ------------------------------------------------------------------ a diagnosis's line: on screen, boxed

REVEAL_WAIT_S = 1.2


async def diagnosis_spot(s: Any, step: dict, anchor: str, caption: str) -> dict | None:
    """t7 (t6 persona: "Wrong sign in tanh slope: change + to - on line 23" while VS Code showed lines 35-48 and
    nothing was boxed): the line a diagnosis is about, found in the step's file by its text (never a fuzzy OCR match;
    the model's line number can be off), brought on screen in the lesson's own VS Code window when it is scrolled
    away (the companion's reveal: no focus change; else the `code -g` jump), and boxed on its row. None: not in the
    file, or no row on screen (the caller's OCR / target fallbacks)."""
    from . import spot_lines

    if getattr(getattr(s, "screen", None), "reader", None) is None or not anchor:
        return None
    p, lines = s._step_lines(step)
    n = spot_lines.find_line(lines, anchor) if p is not None else None
    if n is None:
        return None
    prog = {"path": p, "line": n, "kind": "change", "expect": ""}
    gen = s.step_gen
    spot = await s._progress_spot(step, prog, caption=caption, jump=False)
    if spot is None and not s.typing():  # (a reveal moves the cursor: never under the learner's keystrokes)
        v = await view(s)
        if v is not None and v.get("port") and row_visible(v, p, n) is not True:
            await _reveal(s, v, str(p), n)
        else:
            spot = await s._progress_spot(step, prog, caption=caption, jump=True)  # no companion: `code -g`
        if spot is None and gen == s.step_gen:
            spot = await s._progress_spot(step, prog, caption=caption, jump=False)
    if spot is None or gen != s.step_gen:
        return None
    if s._run_command(step):
        spot.pop("snippet", None)  # a run step's snippet is its command: never under a line of the file
    log.info("diagnosis box: line %s of %s (%r) (t7)", n, Path(p).name, anchor[:40])
    return spot


async def _reveal(s: Any, v: dict, path: str, line: int) -> None:
    """The companion's /open (centred, focus stays), then wait for the view to show `line` (<= REVEAL_WAIT_S) and
    for Accessibility to follow."""
    try:
        from server.workspace import vscode_ext as vx

        res = await asyncio.to_thread(vx.open_file, path, line, folder=s.workdir, preserve_focus=True,
                                      port=int(v["port"]))
    except Exception:  # noqa: BLE001 - a convenience: the caller's fallbacks stand
        log.exception("box_follow: revealing line %s failed", line)
        return
    if not (isinstance(res, dict) and res.get("ok")):
        return
    t0 = time.monotonic()
    while time.monotonic() - t0 < REVEAL_WAIT_S:
        await asyncio.sleep(SETTLE_POLL_S)
        if row_visible(await view(s), path, line):
            changed(s)
            await asyncio.sleep(AX_LAG_S)
            return


async def _hide(s: Any, gen: int, at: tuple, line: int, v: dict) -> None:
    """The row scrolled off screen: the box goes (never a box on whatever scrolled under it)."""
    if hidden(s, at):
        return
    async with s._spot_lock():
        own = getattr(s, "_spot_owner", None)
        if gen != s.step_gen or s.spot_rect is None or own is None or own[:2] != ("step", gen) \
                or s._spot_caption != at[1][1]:
            return
        log.info("insertion box: line %s scrolled off screen (%s): the box goes until it is back (t7)", line,
                 ", ".join(f"{a}-{b}" for a, b in v["ranges"]))
        s._insert_hidden = gen
        await s.emit("spotlight", {"clear": True})
