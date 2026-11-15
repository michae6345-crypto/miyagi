"""diagnose(): failed step → `offtrack` payload (shared/contracts/events.ts)."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from . import llm, scene, web
from .common import (
    citation_menu,
    clamp_body,
    clamp_title,
    clamp_words,
    failed_checks_text,
    get_lesson,
    lesson_gen,
    number_lines,
    on_new_lesson,
    order_actions,
    resolve_citation,
    step_brief,
    system_blocks,
)
from .metrics import summarize
from .playbook import (
    BY_ID,
    CITATIONS,
    GUIDING_QUESTIONS,
    FailureMode,
    match,
    offending_line,
    playbook_text,
)
from .pointing import lesson_mode
from .screen import TARGETS_RULES, TARGETS_SCHEMA, ScreenContext, TargetStream
from .triage import triage

log = logging.getLogger("coach.diagnose")

# Stable across every call and lesson → first cache breakpoint.
COACH_SYSTEM = f"""You are the coach inside a tutorial overlay. A learner is following a tutorial on any topic (web development, React, data science, ML, a CLI tool, Blender...); the video is paused because their own code, terminal output or run failed this step's machine check. You write the small card they see next to their work.

Voice: a calm, precise senior engineer sitting beside them. Name the actual cause, then the one change to make. No hype, no exclamation marks, no "Great question", no apologies, no hedging filler. Assume a skeptical expert may read the card: every claim must be correct and specific.

Hard limits:
- title: 3 to 7 words (hard maximum 8), plain statement of the cause (not a question, no trailing period), in sentence case (capitalize only the first word and proper nouns), with code names in backticks ("`subtract` and `divide` not written yet").
- body: at most 30 words, at most 2 sentences. Sentence 1: why it fails. Sentence 2: what to do, stated completely in words with the concrete value or name (e.g. "Set lr to 1e-3."), because the diff is often hidden at first.
- Refer to their code by its real names (variables, functions) when helpful.
- diff_expected: the smallest replacement for the learner's offending line(s): one contiguous block of at most 8 lines that makes EVERY edit your body's action sentence asks for (if the fix touches two nearby lines, the block covers both), in the learner's style and variable names; "" if no code change applies. If the fix adds training stages, keep the total training budget about the same (split the epochs across stages). diff_yours: the learner's current line(s) copied exactly from the numbered excerpt (without line numbers); "" if none. diff_line: the 1-based line number of diff_yours in the excerpt, 0 if none. diff_file: the file name if known, else "".
- Ground the card in evidence: WEB SOURCES (official docs, changelogs, Stack Overflow / GitHub issues fetched live for this failure) take precedence over memory for API names, versions and deprecations. If a web source contradicts your memory, trust the source. Prefer official docs over community posts.
- diff_command: when the fix is a terminal action (install or upgrade a package, add a CLI flag, re-run with an option), that single shell command; else "". It can go with or without a code diff.
- citation_id: pick one id from the CITATIONS list (web:N, source:..., or a playbook id) only when that source directly supports the card; otherwise "none". Never invent a source.
- playbook_id: the matching playbook entry id, or "none" if no entry fits. Do not force a match: if the evidence does not fit an entry, diagnose from first principles.
- severity: "warn" when it runs but the result is off (a metric plateaus, a test count is short, output differs); "fail" when it crashes, errors, or produces nan/inf.
- actions: include "apply_fix" only when diff_expected is non-empty; include "show_me" when a specific line is implicated.
- guiding_question: one Socratic question (at most 20 words) about THIS cause that leads the learner to the fix without stating it, e.g. "What happens to Adam's steps when the learning rate is large?". It is the first rung of the hint ladder.

- Trust what is on screen (error text, versions in tracebacks) over the lesson's library versions: the learner may have a newer release than the tutorial.
- Never say or guess which file is open or active in the editor from the screen text: the Explorer, tab strip, breadcrumbs and overlays (e.g. VS Code's inline chat over line 1) all show file names. Only an "ACTIVE FILE" line says which file is open; without it, don't mention it at all.
- The body states the cause and the fix; it never asks the learner a question.
- Code read from the screen (OCR) can contain recognition errors and editor overlays (hover tooltips like "(function) def add(a: Any, b: Any) -> None", autocomplete). Never claim a line is malformed, misnamed or missing syntax because of how OCR text looks; only a saved file or an actual error message can show that.
- Never put `git add` or `git rebase/merge/cherry-pick --continue` in diff_command while the file still has conflict markers (<<<<<<< ======= >>>>>>>) that your diff does not remove: that would commit the markers. Say to resolve the markers first.

If the evidence is genuinely insufficient, say what to check next instead of guessing.

DOMAIN PLAYBOOK (curated ML failure modes; only one source of knowledge among many, use an entry only when the evidence fits):

{playbook_text()}
{TARGETS_RULES}
"""

OFFTRACK_SCHEMA = {
    "type": "object",
    "properties": {
        "playbook_id": {"type": "string"},
        "severity": {"type": "string", "enum": ["warn", "fail"]},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "citation_id": {"type": "string"},
        "diff_expected": {"type": "string"},
        "diff_yours": {"type": "string"},
        "diff_file": {"type": "string"},
        "diff_line": {"type": "integer"},
        "diff_command": {"type": "string"},
        "guiding_question": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {"type": "string", "enum": ["explain", "show_me", "apply_fix", "hint"]},
        },
    },
    "required": [
        "playbook_id", "severity", "title", "body", "citation_id",
        "diff_expected", "diff_yours", "diff_file", "diff_line", "diff_command", "actions", "guiding_question",
    ],
    "additionalProperties": False,
}

# last diagnosis per step: hint() and apply_fix() reuse its diff/citation
LAST: dict[str, dict] = {}


def _target_file(step: dict) -> str:
    for t in step.get("targets", []) or []:
        if t.get("file"):
            return t["file"]
    for c in step.get("checks", []) or []:
        if c.get("file"):
            return c["file"]
    return ""


def playbook_card(step: dict, mode: FailureMode, code_excerpt: str = "", severity: str = "warn") -> dict:
    """Curated, offline card for a known failure mode (also the fallback when the API fails)."""
    yours, line = offending_line(mode, code_excerpt)
    diff = None
    if mode.diff_expected:
        diff = {"expected": mode.diff_expected, "yours": yours}
        if f := _target_file(step):
            diff["file"] = f
        if line:
            diff["line"] = line
    c = CITATIONS[mode.citation_id]
    return {
        "stepId": step.get("id", ""),
        "severity": severity,
        "title": mode.card_title,
        "body": mode.card_body,
        **({"diff": diff} if diff else {}),
        "citation": {"label": c["label"], "url": c["url"]},
        **({"guidingQuestion": GUIDING_QUESTIONS[mode.id]} if mode.id in GUIDING_QUESTIONS else {}),
        "actions": order_actions(["show_me"] if line else [], has_diff=bool(diff)),
        "_meta": {"route": "playbook", "playbook_id": mode.id},
    }


OPEN_FILE_CLAIM = re.compile(
    r"\b(?:editor|tab|window|vs ?code)\b[^.?!]*\b(?:shows|showing|has|is on|displays|is open|opened)\b"
    r"|\b(?:is|isn't|is not) (?:the )?(?:open|active|current) (?:file|tab)\b|\bopen in the editor\b|\bnot (?:the )?open file\b",
    re.IGNORECASE,
)


def _active_file_line(active: dict | None) -> str:
    if not active:
        return ""  # unknown: the system rule forbids naming the open file
    from .pointing import editor_state

    ed = editor_state(None, active)
    name = ed.get("untitled") or ed.get("file") or "unknown"
    return f"ACTIVE FILE (from the editor window, authoritative): {name}{' (unsaved)' if ed.get('unsaved') else ''}"


def _no_questions_or_open_file_claims(card: dict, known_active: bool) -> bool:
    """Michael: no Socratic questions on these cards, and never "the editor shows X" guessed from the
    screen. Drops such sentences from the body (and a claiming title); False if nothing is left."""
    def keep(sentence: str) -> bool:
        return not sentence.rstrip().endswith("?") and (known_active or not OPEN_FILE_CLAIM.search(sentence))

    sentences = [x for x in re.split(r"(?<=[.!?])\s+", card.get("body", "")) if x.strip()]
    kept = [x for x in sentences if keep(x)]
    if not kept:
        return False
    card["body"] = " ".join(kept)
    if card.get("why"):
        card["why"] = " ".join(x for x in re.split(r"(?<=[.!?])\s+", card["why"]) if x.strip() and keep(x))
    if not keep(card.get("title", "") + "."):
        card["title"] = clamp_title(kept[0])
    return True


LESSON_MODE_RULE = (
    'LESSON MODE ("Just teach me"): the learner types this lesson\'s code in VS Code. Make the body\'s LAST '
    "sentence ONE action of at most 12 words that names the file and VS Code (e.g. \"In VS Code, name the "
    "function add on line 4 of calculator.py.\"); the first sentence is the why."
)


def _lesson_action(card: dict) -> None:
    """Lesson mode: the card shows one <=12-word action; the why moves behind Explain (S9 #6)."""
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", card.get("body", "")) if x.strip()]
    if not sentences:
        return
    action = clamp_words(sentences[-1], 12)
    card["why"] = " ".join(sentences[:-1])
    card["body"] = action if action.endswith((".", "!", "?", "…")) else action + "."


def error_card(step: dict, error_text: str, code: str) -> dict:
    """No model available but an error is visible: name it, from the error itself (S9: `SyntaxError` under
    `def(a, b):` got the "Start: …" card). Says only what the error and the file show."""
    key = web.error_line(error_text)
    etype = (re.search(r"([A-Za-z_]*(?:Error|Exception|Warning))\b", key) or re.search(r"(error|fatal)", key, re.IGNORECASE))
    etype = etype.group(1) if etype else "Error"
    files = re.findall(r'File "([^"]+)"', error_text)
    fname = (files[-1] if files else (step.get("file") or "")).rsplit("/", 1)[-1] or "your file"
    lines = re.findall(r"\bline (\d+)\b", error_text)
    n = int(lines[-1]) if lines else None
    code_lines = (code or "").splitlines()
    src = code_lines[n - 1].strip() if n and 0 < n <= len(code_lines) else ""
    msg = key.split(":", 1)[1].strip() if ":" in key else key
    if etype == "SyntaxError" and re.match(r"def\s*\(", src):
        body = f"`def` needs a name: line {n} of {fname}."
    elif n:
        body = clamp_words(f"{etype} on line {n} of {fname}: {msg}", 12)
    else:
        body = clamp_words(f"{etype} in {fname}: {msg}", 12)
    return {
        "stepId": step.get("id", ""),
        "severity": "fail",
        "title": clamp_title(f"{etype} in {fname}"),
        "body": body,
        "actions": order_actions(["show_me"] if n else [], has_diff=False),
        "_meta": {"route": "error_offline"},
    }


def template_card(step: dict, failed_checks: list, screen: Any = None, empty_file: bool = False) -> dict:
    """The learner hasn't started the step yet: NOT an off-track. One plain instruction from the step
    itself (Michael: "Not yet: calculator.py created" + a Socratic question read as a wrong diagnosis).
    `notStarted: true` tells the orchestrator to show it as a nudge, not an `offtrack`. No model call."""
    from .pointing import start_instruction

    return {
        "stepId": step.get("id", ""),
        "severity": "warn",
        "title": clamp_title(f"Start: {step.get('title', 'this step')}"),
        "body": clamp_words(start_instruction(step, screen, empty_file=empty_file), 30),
        "actions": order_actions(["show_me"] if step.get("targets") else [], has_diff=False),
        "notStarted": True,
        "_meta": {"route": "template"},
    }


SELF_EXPLAINING = re.compile(
    r"NameError|ReferenceError|is not defined|no-undef|SyntaxError|IndentationError|Unexpected token"
    r"|unexpected indent|unterminated|missing \)|Unexpected end of input",
    re.IGNORECASE,
)
ERROR_LINE = re.compile(
    r"Traceback|\b\w*Error\b|\berror:|\bfatal:|Failed to compile|needs merge|\bCONFLICT\b|You must|is not defined"
    r"|cannot find module|command not found|No such file|Permission denied|\bERR!",
    re.IGNORECASE,
)
# Is an output tail an error? Stricter than ERROR_LINE: case-sensitive, so ML metric names like
# `rel_error 0.3` / `val_error` in a passing run's log don't count (S11: hero tail = metric lines).
ERROR_SIGNATURE = re.compile(
    r"Traceback \(most recent call last\)|^\s*[\w.]*(?:Error|Exception|Warning)\b:|(?:^|\s)(?:error|fatal):\s"
    r"|^\s*\d+:\d+\s+error\s|\bERR!|Failed to compile|\bCONFLICT\b|needs merge|You must|is not defined"
    r"|command not found|No such file or directory|Permission denied|Segmentation fault|Killed\b",
    re.MULTILINE,
)
CONFLICT_MARKERS = re.compile(r"^(<{7}|={7}|>{7})", re.MULTILINE)


def screen_errors(screen: ScreenContext, max_lines: int = 12) -> str:
    """Error / refusal lines visible on screen (terminal, editor problems panel, browser overlay)."""
    lines = [b.text for b in sorted(screen.boxes, key=lambda b: (b.y, b.x)) if ERROR_LINE.search(b.text)]
    return "\n".join(lines[-max_lines:])


def _unsafe_git_continue(command: str, code: str, yours: str, expected: str) -> bool:
    if not re.search(r"\bgit\s+add\b|--continue\b", command):
        return False
    markers_now = bool(CONFLICT_MARKERS.search(code or ""))
    resolved_by_diff = bool(CONFLICT_MARKERS.search(yours or "")) and not CONFLICT_MARKERS.search(expected or "")
    return markers_now and not resolved_by_diff


_SOURCE = re.compile(r'"source"\s*:\s*\[')
_CELL_TYPE = re.compile(r'"cell_type"\s*:\s*"(\w+)"')
_JSON_STR = re.compile(r'"(?:[^"\\]|\\.)*"')


def _cell_sources_tolerant(t: str) -> list[tuple[int, str]]:
    """Code-cell sources from notebook JSON that may be cut off mid-way (the orchestrator sends
    the first 6000 chars): scan each `"source": [...]` array string by string, stop at the cut."""
    out: list[tuple[int, str]] = []
    marks = [m.end() for m in _SOURCE.finditer(t)]
    types = [(m.start(), m.group(1)) for m in _CELL_TYPE.finditer(t)]
    prev_end = 0
    for n, pos in enumerate(marks):
        # nbformat writes keys sorted, so a cell's "cell_type" precedes its "source": take the last
        # one after the previous source array (else the first one after this array)
        before = [ty for p, ty in types if prev_end <= p < pos]
        after = [ty for p, ty in types if p > pos and (n + 1 >= len(marks) or p < marks[n + 1])]
        ctype = before[-1] if before else (after[0] if after else "code")
        parts, i = [], pos
        while True:
            m = re.compile(r"\s*(,)?\s*").match(t, i)
            i = m.end()
            if i >= len(t) or t[i] == "]":
                break
            sm = _JSON_STR.match(t, i)
            if not sm:  # the cut fell inside this string: keep what we have of it
                tail = t[i + 1:] if t[i] == '"' else ""
                parts.append(tail.encode().decode("unicode_escape", errors="ignore") if "\\" in tail else tail)
                i = len(t)
                break
            try:
                parts.append(json.loads(sm.group(0)))
            except json.JSONDecodeError:
                break
            i = sm.end()
        prev_end = i
        if ctype == "code" and parts:
            out.append((n, "".join(parts)))
    return out


def notebook_code(text: str) -> str:
    """A Jupyter notebook's JSON → its code cells' source, separated by `# %% [cell N]` markers.
    Works on truncated JSON too. Anything that isn't a notebook is returned unchanged."""
    t = (text or "").lstrip()
    if not (t.startswith("{") and ('"cells"' in t[:20000] or '"cell_type"' in t[:20000])):
        return text
    try:
        nb = json.loads(t)
        cells = [(i, "".join(c.get("source") or []) if isinstance(c.get("source"), list) else (c.get("source") or ""))
                 for i, c in enumerate(nb.get("cells") or []) if c.get("cell_type") == "code"]
    except json.JSONDecodeError:
        cells = _cell_sources_tolerant(t)
    out = [f"# %% [cell {i}]\n" + src.rstrip("\n") for i, src in cells]
    return "\n".join(out) if out else "# (notebook: no code cell source within the excerpt)"


def _title(title: str, pid: str | None) -> str:
    """Over-long titles are not chopped mid-phrase: use the curated title, else trim."""
    title = (title or "").strip().rstrip(".")
    if len(title.split()) <= 8:
        return title
    if pid in BY_ID:
        return BY_ID[pid].card_title
    return clamp_title(title)


_CAMEL_BRANDS = frozenset({"iPhone", "iPad", "iOS", "macOS", "eBay", "iCloud"})


def _tidy_title(title: str, step: dict, code_excerpt: str = "") -> str:
    """E11: sentence case, code names in backticks: "subtract, multiply, divide not written yet" -> "`subtract`,
    `multiply`, `divide` not written yet". Wrapped: the step's def / class names, add() and snake_case tokens, dotted
    lowercase names (`calc.py`, `np.mean`, `torch.no_grad`), and a lowercase first word that is a name in the code
    (`lr`, assigned or passed as `lr=`); otherwise the first letter is capitalized. A wrapped first word is never
    capitalized. Text already in backticks is left alone."""
    src = f"{step.get('code') or ''}\n{code_excerpt or ''}"
    defs = set(re.findall(r"\b(?:def|class)\s+([A-Za-z_]\w*)", src))
    assigned = re.findall(r"\b([A-Za-z_]\w*)\s*=(?!=)|^\s*(?:from|import)\s+([A-Za-z_]\w*)", src, re.MULTILINE)
    names = defs | {a or b for a, b in assigned}  # + variables, keyword args and imported modules (`lr`, `pandas`)

    def wrap(m: re.Match, at_start: bool) -> str:
        tok = m.group(1)
        code = (tok.rstrip("()") in defs or tok.endswith("()") or ("_" in tok and re.search(r"[A-Za-z]", tok))
                or ("." in tok and tok[:1].islower())  # calc.py, np.mean (Node.js is a name: left alone)
                or (re.fullmatch(r"[a-z]+[A-Z]\w*", tok) and tok not in _CAMEL_BRANDS))  # useEffect, not macOS
        first = at_start and tok[:1].islower() and tok in names
        return f"`{tok}`" if code or first else tok

    word = re.compile(r"(?<![\w`.])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\(\))?)(?![\w`(.])")
    parts = re.split(r"(`[^`]*`)", title or "")
    for i in range(0, len(parts), 2):  # outside backticks only
        parts[i] = word.sub(lambda m, i=i: wrap(m, i == 0 and m.start() == 0), parts[i])
    out = "".join(parts)
    lead = re.match(r"\S*", out).group(0)
    return out[0].upper() + out[1:] if lead.islower() else out  # "macOS …" keeps its case


def _shape(data: dict, step: dict, code_excerpt: str, lesson: dict | None, sources: list[dict] | None = None) -> dict:
    expected = (data.get("diff_expected") or "").strip("\n")
    yours = (data.get("diff_yours") or "").strip()
    command = (data.get("diff_command") or "").strip()
    if command and _unsafe_git_continue(command, code_excerpt, yours, expected):
        command = ""  # would commit unresolved conflict markers (S9 QA, verified)
    diff = None
    if command and not expected:  # terminal-only fix: the app copies it to the clipboard
        diff = {"expected": "", "yours": "", "command": command}
    if expected:
        diff = {"expected": expected, "yours": yours, **({"command": command} if command else {})}
        f = data.get("diff_file") or _target_file(step)
        if f:
            diff["file"] = f
        line = int(data.get("diff_line") or 0)
        if not line and yours:
            for i, l in enumerate((code_excerpt or "").splitlines(), start=1):
                if l.strip() == yours.splitlines()[0].strip():
                    line = i
                    break
        if line:
            diff["line"] = line
    pid = data.get("playbook_id")
    cit = resolve_citation(data.get("citation_id"), lesson, sources)
    if cit is None and pid in BY_ID and data.get("citation_id") not in (None, "none"):
        cit = resolve_citation(BY_ID[pid].citation_id, lesson)  # model named a bad id for a known entry
    out = {
        "stepId": step.get("id", ""),
        "severity": data.get("severity") if data.get("severity") in ("warn", "fail") else "warn",
        "title": _tidy_title(_title(data.get("title", ""), pid), step, code_excerpt),
        "body": clamp_body(data.get("body", "")),
        "actions": order_actions(data.get("actions") or [], has_diff=bool(diff)),
        "_meta": {"route": "opus", "playbook_id": pid if pid in BY_ID else None},
    }
    if q := (data.get("guiding_question") or "").strip():
        out["guidingQuestion"] = clamp_words(q, 24)
    if diff:
        out["diff"] = diff
    if cit:
        out["citation"] = cit
    return out


async def diagnose(
    step: dict,
    failed_checks: list,
    metrics_summary: Any = None,
    code_excerpt: str = "",
    *,
    error_text: str = "",
    lesson: dict | None = None,
    use_triage: bool = True,
    effort: str = "low",
    screen: ScreenContext | None = None,
    on_targets: Callable[[list[dict]], Any] | None = None,
    cursor: dict | None = None,
    file_state: dict | None = None,
    code_source: str = "file",
    active_file: dict | None = None,
) -> dict:
    """Return an `offtrack` payload for the failed step.

    Holds (no diagnosis, no model call; the card carries `hold` and the orchestrator must NOT show
    it as an offtrack), from Michael's live misdiagnosis of an unsaved, OCR'd `def add(a, b):`:
      - `hold: "wrong_folder"`: `file_state["wrong_folder"]`, the learner edits a same-named file
        elsewhere (the orchestrator shows its own card);
      - `hold: "unsaved"`: `file_state["saved"] is False`, or the screen shows the step's file
        unsaved (●, Untitled-N) → the only message is "Save with ⌘S so I can check it.";
      - `hold: "unconfirmed"`: `code_source="screen"` (the excerpt is OCR) and it doesn't match the
        previous read of this step: two agreeing reads before claiming anything; say nothing.

    With `screen` (a set-of-mark ScreenContext) Opus also sees the screen and returns
    `targets` first: [{boxId, label, text, rect}] in screen points. The reply is streamed and
    `on_targets(targets)` fires the moment that array is complete, before the rest of the card,
    so the spotlight can move early. Cancel the awaiting task to abort (stream is closed).
    `cursor` ({"x", "y", "under": {"text", "app", "rect"}}, screen points) tells the coach what
    the learner is pointing at when no full `screen` is attached.

    Extra keys starting with `_` (e.g. `_meta`: route, model, latency, usage) are
    for logs; strip them before sending (see `public()`).
    """
    gen = lesson_gen()
    lesson = lesson if lesson is not None else get_lesson()
    active_file = active_file if active_file is not None else getattr(screen, "active_file", None)
    if screen is not None and hasattr(screen, "drop_foreign"):  # screen rows from another project's window never reach the prompt
        error_text = screen.drop_foreign(error_text)
        if code_source == "screen":
            code_excerpt = screen.drop_foreign(code_excerpt)
    if (held := _hold(step, screen, file_state, code_excerpt, code_source, active_file, error_text)) is not None:
        return held
    if _empty_code_step(step, code_excerpt, file_state):  # an empty file at a code step: not started, not off track
        card = template_card(step, failed_checks, screen, empty_file=True)
        card["_meta"]["triage"] = {"route": "template", "by": "rules", "reason": "the step's file is empty"}
        return card
    memo_key = _memo_key(step, failed_checks, metrics_summary, code_excerpt, error_text, screen)
    if (hit := _MEMO.get(step.get("id", ""))) and hit[0] == memo_key and time.monotonic() - hit[1] < MEMO_TTL_S:
        card = copy.deepcopy(hit[2])  # same failure, same code, same screen: no second paid call
        card["_meta"]["memo"] = True
        return card
    if not error_text.strip() and screen is not None:
        # screen-first lessons have no captured stderr: an error/refusal visible on screen is the
        # error text (S9 QA: without it, triage sent git/React failures to the "not done yet" card)
        error_text = screen_errors(screen)
    error_text = scene.with_error(step.get("id"), error_text)  # an error a Haiku glance saw after a run (no new call)
    code_excerpt = notebook_code(code_excerpt)  # .ipynb JSON → cell sources (S9 QA)
    metrics_text, flags = summarize(metrics_summary, goals=metric_goals(step))
    if error_text:
        flags |= {"nan"} if "nan" in error_text.lower() else set()
    # the orchestrator passes the run's output tail even when it exited 0 ("step N | loss …",
    # ::metric:: lines): that is context, not an error (S11). Only an error signature makes it one.
    has_error = bool(ERROR_SIGNATURE.search(error_text or ""))

    # live-web grounding runs while triage decides; only Opus uses it. It is worth waiting for only
    # when there is an error message to look up (docs/changelogs); for metric-only failures the
    # search came back unused and cost 2-4 s before Opus could start (rehearsal, s8 lr=0.3).
    lib, sym, query, err = grounding_query(step, failed_checks, error_text if has_error else "", code_excerpt, lesson)
    # S9 re-run: 6/8 cards waited the full cap for generic hits; self-explaining errors skip it
    wants_web = has_error and not SELF_EXPLAINING.search(error_text)
    web_task = asyncio.create_task(web.gather(lib, sym, query, error=err, timeout=1.5)) if wants_web else None
    try:
        t = await triage(step, failed_checks, flags, code_excerpt, error_text, use_haiku=use_triage)
        if t.route == "template":
            card = template_card(step, failed_checks, screen)
        elif t.route == "playbook" and t.playbook_id:
            card = playbook_card(step, BY_ID[t.playbook_id], code_excerpt, severity="fail" if has_error else "warn")
        else:
            sources = await web_task if web_task is not None else []
            card = await _opus(step, failed_checks, metrics_text, flags, code_excerpt, error_text, lesson, effort, sources, screen, on_targets, cursor, active_file)
    finally:
        if web_task is not None and not web_task.done():
            web_task.cancel()
    card["_meta"]["triage"] = {"route": t.route, "by": t.by, "reason": t.reason}
    if gen == lesson_gen():  # a diagnosis that outlived its lesson must not become the next lesson's "s3"
        LAST[card["stepId"]] = card
        _MEMO[step.get("id", "")] = (memo_key, time.monotonic(), copy.deepcopy(card))
    return card


MEMO_TTL_S = 600.0
_MEMO: dict[str, tuple[str, float, dict]] = {}  # step id → (inputs hash, time, card)


def reset_memo() -> None:
    _MEMO.clear()


def _memo_key(step: dict, failed_checks: list, metrics: Any, code: str, error_text: str, screen: Any) -> str:
    from .gate import screen_signature

    def last_values(m: Any) -> Any:  # a metric series is summarized by its last point per name
        if isinstance(m, dict):
            return sorted((k, tuple(v[-1]) if isinstance(v, list) and v and isinstance(v[-1], (list, tuple)) else repr(v)) for k, v in m.items())
        return repr(m)

    scr = screen_signature("\n".join(b.text for b in screen.boxes)) if hasattr(screen, "boxes") else ""
    blob = json.dumps([step.get("id"), [(c.get("checkId") or c.get("id"), c.get("status"), c.get("detail")) if isinstance(c, dict) else str(c)
                                        for c in failed_checks or []],
                       last_values(metrics), code, error_text, scr], default=str, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


_SCREEN_READS: dict[str, str] = {}  # step id → last OCR'd code excerpt (normalized)
on_new_lesson(LAST.clear, _MEMO.clear, _SCREEN_READS.clear)  # all keyed by bare step ids, which every lesson reuses


def _empty_code_step(step: dict, code: str, file_state: dict | None) -> bool:
    if (file_state or {}).get("empty"):
        return True
    return lesson_mode(step) and bool((step.get("code") or "").strip()) and not (code or "").strip() and (step.get("file") or "") != "(terminal)"


def _hold(step: dict, screen: Any, file_state: dict | None, code: str, code_source: str, active_file: dict | None = None,
          error_text: str = "") -> dict | None:
    from .pointing import editor_state, step_file

    sid = step.get("id", "")
    fs = file_state or {}

    def card(hold: str, title: str, body: str) -> dict:
        return {"stepId": sid, "severity": "warn", "title": title, "body": body, "actions": [], "hold": hold,
                "_meta": {"route": "hold", "hold": hold}}

    if fs.get("wrong_folder"):
        return card("wrong_folder", "Different folder", "This file isn't in the lesson folder.")
    name = (step_file(step) or "").rsplit("/", 1)[-1]
    ed = editor_state(screen, active_file) if (screen is not None or active_file) else {}
    unsaved_on_screen = bool(ed) and ed.get("unsaved") and (ed.get("untitled") or not name or ed.get("file") == name)
    if fs.get("saved") is False or unsaved_on_screen:
        return card("unsaved", "Save so I can check", "Save with ⌘S so I can check it.")
    if code_source == "screen" and code.strip():
        norm = re.sub(r"\s+", "", code)
        prev, _SCREEN_READS[sid] = _SCREEN_READS.get(sid), norm
        # an error to explain (a traceback, "SyntaxError: …") needs no second read of the code: t3 held a run's
        # SyntaxError as "unconfirmed" on every frame for 20 s
        if prev != norm and not ERROR_SIGNATURE.search(error_text or ""):
            return card("unconfirmed", "", "")
    else:
        _SCREEN_READS.pop(sid, None)
    return None


def metric_goals(step: dict) -> dict[str, str]:
    """metric name -> "down" | "up" from the step's own checks (op < means lower is better)."""
    goals = {}
    for c in step.get("checks", []) or []:
        if c.get("metric"):
            goals[c["metric"]] = "up" if c.get("op") in (">", ">=") else "down"
    return goals


def grounding_query(step: dict, failed_checks: list, error_text: str, code: str, lesson: dict | None) -> tuple[str, str, str, str]:
    """(library, symbol, community query, error line) for the web layer. Generic: no domain hardcoding."""
    libs = ((lesson or {}).get("lesson") or {}).get("libraries") or {}
    command = next((c.get("command", "") for c in step.get("checks", []) or [] if c.get("command")), "")
    if error_text:
        lib, sym = web.detect(error_text, code, libs, command)
        line = web.error_line(error_text)
        return lib, sym, line, line
    title = ((lesson or {}).get("lesson") or {}).get("title", "")
    labels = ", ".join(str(c.get("label", "")) for c in failed_checks or [] if isinstance(c, dict))
    return "", "", f"{title} {step.get('title', '')} {labels}".strip(), ""


async def _opus(step, failed_checks, metrics_text, flags, code_excerpt, error_text, lesson, effort, sources=None, screen=None, on_targets=None, cursor=None, active_file=None) -> dict:
    sources = sources or []
    file = _target_file(step)
    key_error = web.error_line(error_text) if ERROR_SIGNATURE.search(error_text or "") else ""
    user = "\n\n".join(
        x for x in [
            f"CURRENT STEP:\n{step_brief(step)}",
            f"FAILED CHECKS:\n{failed_checks_text(failed_checks)}",
            f"METRICS (summary of the learner's latest run):\n{metrics_text}"
            + (f"\nauto-detected: {', '.join(sorted(flags))}" if flags else ""),
            f"ERROR / OUTPUT TAIL:\n{error_text[-2000:]}" if error_text else "ERROR / OUTPUT TAIL: (none)",
            f"THE ERROR MESSAGE (your cause must agree with exactly what it says, for the version that printed it):\n{key_error}"
            if key_error else "",
            f"LEARNER CODE ({file or 'excerpt'}), numbered:\n{number_lines(code_excerpt) or '(not available)'}",
            f"WEB SOURCES (fetched live for this failure):\n{web.sources_text(sources)}" if sources else "WEB SOURCES: (none available)",
            f"CITATIONS you may use (id: source):\n{citation_menu(lesson, sources)}",
            cursor_text(cursor) if cursor and screen is None else "",
            LESSON_MODE_RULE if lesson_mode(step) else "",
            _active_file_line(active_file),
            "Write the card.",
        ] if x
    )
    schema, content, stream = OFFTRACK_SCHEMA, None, None
    if screen is not None:
        schema = screen_schema(OFFTRACK_SCHEMA)
        content = [{"type": "text", "text": user}, *screen.claude_content()]
        user = user + "\n\n" + screen.text()  # fixture key covers the screen text, not the pixels
        stream = TargetStream(screen, on_targets)
    try:
        res = await llm.structured_call(
            purpose="diagnose",
            model=llm.model_for("diagnose"),
            system=system_blocks(COACH_SYSTEM, lesson),
            user_text=user,
            schema=schema,
            effort=effort,
            max_tokens=8000,
            timeout=40.0,
            user_content=content,
            on_text=stream,
        )
    except llm.CoachLLMError as e:
        mode, conf = match(code_excerpt, flags, error_text)
        if not llm.demo_mode():
            # live: only a network outage, only when opted in, only a confident match on their code
            if e.kind == "connection" and llm.offline_fallback() and mode and conf >= 0.6:
                log.warning("opus unreachable (%s); offline playbook card %s (conf %.1f)", e, mode.id, conf)
                card = playbook_card(step, mode, code_excerpt, severity="fail" if ERROR_SIGNATURE.search(error_text or "") else "warn")
                card["offline"] = True  # additive public field: the app may badge it "offline"
                card["_meta"].update(fallback_reason=str(e), confidence=round(conf, 2))
                return card
            raise llm.CoachUnavailable(f"diagnosis unavailable: {e}") from e
        log.warning("opus diagnose failed (%s); DEMO=1 so using the offline playbook card", e)
        if mode and conf >= 0.4:
            card = playbook_card(step, mode, code_excerpt, severity="fail" if ERROR_SIGNATURE.search(error_text or "") else "warn")
        elif ERROR_SIGNATURE.search(error_text or ""):
            card = error_card(step, error_text, code_excerpt)  # a visible error is never "not started" (S9)
        else:
            card = template_card(step, failed_checks)
        card["_meta"]["fallback_reason"] = str(e)
        return card
    card = _shape(res.data, step, code_excerpt, lesson, sources)
    if not _no_questions_or_open_file_claims(card, known_active=bool(active_file)):
        return {"stepId": step.get("id", ""), "severity": "warn", "title": "", "body": "", "actions": [], "hold": "unconfirmed",
                "_meta": {"route": "hold", "hold": "unconfirmed", "reason": "the card only asked a question or guessed the open file"}}
    if lesson_mode(step):
        _lesson_action(card)
    if screen is not None:
        card["targets"] = stream.fired if stream.fired is not None else screen.resolve_targets(res.data.get("targets"))
        if stream.fired is None and on_targets is not None and card["targets"]:
            await llm._maybe_await(on_targets(card["targets"]))
        card["_meta"]["screen"] = {"boxes": len(screen.boxes), "cursor": list(screen.cursor)}
    card["_meta"]["web_sources"] = sources  # full dicts; explain() reuses them
    card["_meta"].update(model=res.model, latency_s=round(res.latency_s, 2), usage=res.usage, source=res.source)
    return card


def cursor_text(cursor: dict) -> str:
    """'LEARNER CURSOR: at (x, y) over "text" (app)' from the orchestrator's cursor dict."""
    under = cursor.get("under") or {}
    s = f"LEARNER CURSOR: at ({float(cursor.get('x', 0)):.0f}, {float(cursor.get('y', 0)):.0f})"
    if under.get("text"):
        s += f' over "{str(under["text"])[:120]}"' + (f" ({under['app']})" if under.get("app") else "")
    return s + " (what they are looking at or pointing to; mention it only if relevant)"


def screen_schema(base: dict) -> dict:
    """Same schema with `targets` as the FIRST property, so it streams before the prose."""
    return {
        **base,
        "properties": {"targets": TARGETS_SCHEMA, **base["properties"]},
        "required": ["targets", *base["required"]],
    }


def public(payload: dict) -> dict:
    """Strip private `_` keys before sending over the WebSocket."""
    return {k: v for k, v in payload.items() if not k.startswith("_")}
