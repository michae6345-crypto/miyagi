"""What the learner has done on this Mac, step by step: ~/miyagi/state/mastery.json (MIYAGI_STATE_DIR overrides).

history.json (store.record_completed) only grows when a lesson's LAST step passes, so a learner who passed a `def`
in the weather lesson and then started the dice lesson still saw "Python functions: Not seen yet" (E23). Here every
passed step (never a skipped one) adds what it practised, read from the step itself: its title and plan line, the
primer concepts it used, and the constructs in its code ("def" -> functions, "for" -> loops, "import" -> importing
modules, a run step -> running programs in the terminal), with the file's language ("Python"). One entry per
lesson; store.prerequisite_status reads these entries after the finished lessons, so a later lesson's prerequisite
reads "passed" with that lesson as evidence ("Passed in Weather CLI"). Deterministic, no model call; never raises
into the lesson.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from . import store

log = logging.getLogger("sessions")

MAX_LESSONS = 50
MAX_PHRASES = 80

LANGUAGES = {".py": "Python", ".ipynb": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
             ".jsx": "JavaScript React", ".ts": "TypeScript", ".tsx": "TypeScript React", ".rb": "Ruby", ".go": "Go",
             ".rs": "Rust", ".java": "Java", ".sh": "shell", ".html": "HTML", ".css": "CSS", ".sql": "SQL"}

# (pattern on the step's code, what a step with it practised)
CONSTRUCTS: list[tuple[re.Pattern, tuple[str, ...]]] = [(re.compile(p, re.M), ph) for p, ph in [
    (r"^\s*(?:async\s+)?def\s+\w+\s*\(|\bfunction\b\s*\w*\s*\(|=>", ("functions", "defining functions", "function syntax")),
    (r"^\s*return\b", ("return values",)),
    (r"^\s*(?:from\s+\S+\s+)?import\b|\brequire\(", ("imports", "importing modules", "modules", "libraries")),
    (r"^\s*(?:for|while)\b", ("loops", "for loops")),
    (r"^\s*(?:if|elif)\b|\bif\s*\(", ("conditionals", "if statements")),
    (r"^\s*class\s+\w+", ("classes", "objects")),
    (r"^\s*(?:(?:const|let|var)\s+)?[A-Za-z_]\w*\s*=[^=]", ("variables", "assignment")),
    (r"\[[^\]]*,[^\]]*\]|\.append\(", ("lists", "arrays")),
    (r"\{\s*['\"\w]+\s*:", ("dictionaries", "dicts", "objects")),
    (r"\bprint\(|console\.log\(", ("print", "printing output", "output")),
    (r"\binput\(", ("input", "user input", "reading input")),
    (r"\bf['\"]|`[^`]*\$\{", ("strings", "f-strings", "string formatting")),
    (r"^\s*try\s*:|\btry\s*\{|\bexcept\b|\bcatch\b", ("exceptions", "error handling")),
    (r"\bopen\(", ("files", "reading files", "file handling")),
    (r"\brequests\.|\bfetch\(|\bhttpx\.|\burllib\b", ("HTTP requests", "APIs", "web APIs", "JSON")),
    (r"\bjson\b|\.json\(", ("JSON",)),
    (r"\brandom\.", ("random numbers", "the random module")),
    (r"\bsys\.argv\b|\bargparse\b|process\.argv", ("command line arguments", "command-line arguments")),
]]
RUN_PHRASES = ("running programs", "running scripts", "the terminal", "command line", "run")
SYNTAX_PHRASES = ("syntax", "basics")


def _path():
    return store.state_dir() / "mastery.json"


def entries() -> list[dict]:
    """Lessons with at least one passed step, newest first: {lessonId, title, covered: [phrases], at}."""
    data = store._read(_path())
    rows = [e for e in data if isinstance(e, dict) and e.get("lessonId")] if isinstance(data, list) else []
    return sorted(rows, key=lambda e: e.get("at") or 0, reverse=True)


def practised(step: dict, lesson: dict | None = None) -> list[str]:
    """What one passed step practised (phrases, in order, no repeats)."""
    lesson = lesson or {}
    code = step.get("code") or ""
    file = step.get("file") or ""
    run = (step.get("kind") == "run") or bool((step.get("run_command") or "").strip() and (not file or code.strip() == step["run_command"].strip()))
    lang = LANGUAGES.get(Path(file).suffix.lower(), "")
    out: list[str] = [step.get("title") or "", step.get("what") or ""]
    primer = {p.get("id"): p.get("title") for p in lesson.get("primer") or [] if isinstance(p, dict)}
    out += [primer.get(c) or "" for c in step.get("concepts") or []]
    if run:
        out += list(RUN_PHRASES) + ([f"running {lang}", f"{lang} scripts"] if lang else [])
        if re.search(r"\bpip3?\s+install\b|\bnpm\s+(?:i|install)\b", code + " " + (step.get("run_command") or "")):
            out += ["pip", "installing packages", "package managers"]
    elif code.strip():
        hits = [ph for rx, phrases in CONSTRUCTS if rx.search(code) for ph in phrases]
        out += hits + list(SYNTAX_PHRASES)
    if lang and (run or code.strip()):
        out.append(lang)
    seen, clean = set(), []
    for p in out:
        p = " ".join(str(p).split())
        if p and p.lower() not in seen:
            seen.add(p.lower())
            clean.append(p)
    return clean


def record_step(graph: dict, step_id: str | None) -> dict | None:
    """A step of `graph` passed (the learner did it; never call this for a skipped step): add what it practised to its
    lesson's entry. Returns the entry, or None when there is nothing to record."""
    les = (graph or {}).get("lesson") or {}
    step = next((s for s in (graph or {}).get("steps") or [] if isinstance(s, dict) and s.get("id") == step_id), None)
    if not les.get("id") or step is None:
        return None
    phrases = practised(step, les)
    if not phrases:
        return None
    rows = entries()
    old = next((e for e in rows if e["lessonId"] == les["id"]), None)
    covered = list((old or {}).get("covered") or [])
    have = {c.lower() for c in covered}
    covered += [p for p in phrases if p.lower() not in have]
    entry = {"lessonId": les["id"], "title": les.get("title") or "a lesson", "covered": covered[-MAX_PHRASES:], "at": time.time()}
    keep = [e for e in rows if e["lessonId"] != les["id"]][:MAX_LESSONS - 1]
    store._write_atomic(_path(), [entry] + keep)
    return entry


def record_step_safely(graph: dict, step_id: str | None) -> None:
    try:
        record_step(graph, step_id)
    except Exception as e:  # noqa: BLE001 - remembering progress must never break the lesson
        log.warning("could not record the passed step: %s", e)
