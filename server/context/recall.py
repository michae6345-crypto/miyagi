"""What we know so far: a compact block of a lesson's notes for a coach prompt.

    from server.context import recall
    text = recall.what_we_know("lesson-abc", step_id="s2", budget=1200)
    # "- [check s2] s2 checks: 1 passed, 1 not yet (Run nn.py)\n- [file nn.py] nn.py: 40 lines; imports torch ..."

The caller wraps it as data: f"WHAT WE KNOW SO FAR:\n{wrap('memory', text)}" (server.untrusted). Every line is the
learner's or the screen's text (redacted when it was saved), never an instruction.

Only the newest note of each slot counts (a file's latest outline, a check's latest result), and older notes that a
newer one of the same slot replaced are left out. Ranked: notes about this step first, then the rest, newest first
inside each group; whole lines are kept until `budget` characters (~4 characters a token, so 1200 is ~300 tokens).
"""

from __future__ import annotations

import time

from server.context.store import ContextStore, Entry, enabled

DEFAULT_BUDGET = 1200
MAX_AGE_S = 3 * 86400  # notes older than this are history, not "so far" (a lesson resumed days later)
# Which kinds a purpose wants. Coach answers already see the code and screen of this moment, so a file note is only
# about the other files; the judge is told what happened, never what a model said.
PURPOSE_KINDS: dict[str, frozenset[str]] = {
    "explain": frozenset({"file", "screen", "check", "coach", "setup", "action", "step", "transcript", "note"}),
    "diagnose": frozenset({"file", "screen", "check", "coach", "setup", "action", "step", "note"}),
    "judge": frozenset({"check", "setup", "action", "step", "file"}),
}


def _line(e: Entry) -> str:
    label = e.kind + (f" {e.source}" if e.source and e.source != e.step else "") + (f" {e.step}" if e.step else "")
    return f"- [{label.strip()}] " + " / ".join(e.summary.splitlines())


def select(entries: list[Entry], step_id: str | None = None, *, kinds: frozenset[str] | None = None,
           now: float | None = None, exclude_files: set[str] | None = None) -> list[Entry]:
    """The notes worth telling, best first: newest per slot, this step's first, then newest first."""
    now = time.time() if now is None else now
    newest: dict[tuple[str, str, str], Entry] = {}
    for e in entries:
        if kinds is not None and e.kind not in kinds:
            continue
        if now - e.t > MAX_AGE_S:
            continue
        if e.kind == "file" and exclude_files and (e.source in exclude_files or e.source.rsplit("/", 1)[-1] in exclude_files):
            continue  # the prompt already carries this file's full text
        prev = newest.get(e.slot)
        if prev is None or e.t >= prev.t:
            newest[e.slot] = e
    picked = list(newest.values())
    picked.sort(key=lambda e: (0 if step_id and e.step == step_id else 1, -e.t))
    return picked


def render(picked: list[Entry], budget: int = DEFAULT_BUDGET) -> str:
    lines: list[str] = []
    used = 0
    for e in picked:
        ln = _line(e)
        if used + len(ln) + 1 > budget:
            continue  # a shorter note further down may still fit
        lines.append(ln)
        used += len(ln) + 1
    return "\n".join(lines)


def what_we_know(lesson_id: str | None, step_id: str | None = None, *, purpose: str = "explain",
                 budget: int = DEFAULT_BUDGET, exclude_files: set[str] | None = None, now: float | None = None) -> str:
    """The block for one prompt ("" when memory is off or nothing is known)."""
    if not enabled() or not lesson_id:
        return ""
    entries = ContextStore(lesson_id).entries()
    if not entries:
        return ""
    picked = select(entries, step_id, kinds=PURPOSE_KINDS.get(purpose), now=now, exclude_files=exclude_files)
    return render(picked, budget)
