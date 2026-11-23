"""The engine's untrusted-lesson checks, run on the server before a shared lesson is auto-approved.

A port of server/lesson/schema.py validate_untrusted_lesson() (origin/integration/live 0dc60fd6). The engine *repairs*
a graph (drops a bad check, a bad path, a bad regex; marks a bad command as manual); the cloud must not serve a
lesson the engine would have to repair, so here every such repair is a *problem*, and any problem leaves the upload
pending for an operator (LESSON_AUTO_APPROVE_VALIDATED). An empty list means the engine would load the lesson as is.

Ported, as the engine has them:
  * paths (server/safety/paths.py rel_problem, read rules): step file / notebook, step files, target files, check
    files, plus the lesson's top-level files: no NUL, backslash, drive, absolute or `~` path, no `..`; a step file
    or notebook is never inside .git/, .vscode/, .venv/, venv/, node_modules/, .idea/, .github/, .devcontainer/
  * regexes (server/safety/patterns.py static_problem, vendored in lesson_patterns.py): every check pattern and
    metric_pattern must be short, compile and have no catastrophic backtracking shape; a target's match is checked
    with IGNORECASE and may be literal text that does not compile
  * at most 24 checks per list of a step, 24 targets per step and 400 patterns in the lesson
  * sources must be https; lesson.workdir must be absent (the engine only honours a folder under the learner's own
    lessons root, which a shared lesson cannot know)

Stricter on the cloud already (app.py validate_lesson refuses the upload outright): run_command and check commands
match a short allowlist (python/pytest/node/npm run with plain arguments), which covers the engine's
is_structural_manual (shell syntax, URLs, curl/bash/npx, invisible characters); libraries are plain names and
versions; only the known keys are allowed.

Not ported (needs the engine or the learner's Mac): the regex worker's run-time deadline and ban list, the
resolve()-and-stay-inside-the-folder check on disk, and the workdir rules that depend on the learner's home folder.
The engine still applies all of them when it loads a shared lesson, so this is an extra line in front of them.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from lesson_patterns import static_problem

MAX_STEP_CHECKS = 24
MAX_STEP_TARGETS = 24
MAX_LESSON_PATTERNS = 400
WRITE_DENY_DIRS = frozenset({".git", ".vscode", ".venv", "venv", "node_modules", ".idea", ".github", ".devcontainer"})
_DRIVE = re.compile(r"^[A-Za-z]:")


def rel_problem(s) -> str | None:
    """Why `s` (a path relative to the lesson folder) is refused on its text alone (the engine's read rules)."""
    if not isinstance(s, str) or not s.strip():
        return "no path"
    if "\x00" in s:
        return "NUL in the path"
    if "\\" in s or _DRIVE.match(s):
        return "not a POSIX relative path"
    if s.startswith(("/", "~")):
        return "absolute or home path"
    parts = [p for p in PurePosixPath(s).parts if p not in ("", ".")]
    if not parts:
        return "no path"
    if ".." in parts:
        return "goes up out of the lesson folder"
    return None


def _protected_dir(rel: str) -> str | None:
    hit = next((p for p in PurePosixPath(rel).parts[:-1] if p.casefold() in WRITE_DENY_DIRS), None)  # APFS
    return f"{hit}/ is never a step file" if hit else None


def _short(v) -> str:
    return repr(str(v)[:60])


def review(lesson) -> list[str]:
    """Every repair the engine's validate_untrusted_lesson would make to `lesson`, as short notes. [] = clean."""
    if not isinstance(lesson, dict):
        return ["not a lesson"]
    notes: list[str] = []
    patterns = 0
    meta = lesson.get("lesson")
    if isinstance(meta, dict) and meta.get("workdir") not in (None, ""):
        notes.append("lesson.workdir is set")
    for s in lesson.get("sources") or []:
        url = s.get("url") if isinstance(s, dict) else None
        if not isinstance(s, dict) or (url not in (None, "") and not str(url).startswith("https://")):
            notes.append(f"source {_short(url)}: not https")
    for f in lesson.get("files") or []:
        if isinstance(f, str) and (why := rel_problem(f)):
            notes.append(f"files {_short(f)}: {why}")
    for i, step in enumerate(lesson.get("steps") or []):
        if not isinstance(step, dict):
            notes.append(f"step {i + 1}: not an object")
            continue
        sid = step.get("id") or f"step {i + 1}"
        for key in ("file", "notebook"):
            f = step.get(key)
            if f not in (None, "") and (why := rel_problem(str(f)) or _protected_dir(str(f))):
                notes.append(f"{sid}.{key} {_short(f)}: {why}")
        if isinstance(step.get("files"), list):
            bad = [f for f in step["files"] if not isinstance(f, str) or rel_problem(f) is not None]
            if bad:
                notes.append(f"{sid}.files: {len(bad)} unsafe path(s)")
        targets = step.get("targets")
        if isinstance(targets, list):
            if len(targets) > MAX_STEP_TARGETS:
                notes.append(f"{sid}: {len(targets)} targets, over {MAX_STEP_TARGETS}")
            for t in targets:
                if not isinstance(t, dict):
                    continue
                f = t.get("file")
                if f not in (None, "") and (why := rel_problem(str(f))):
                    notes.append(f"{sid} target {_short(f)}: {why}")
                m = t.get("match")
                if isinstance(m, str) and m:
                    why = static_problem(m, re.IGNORECASE)
                    if why and not why.startswith("invalid pattern"):  # literal text first, a regex only if it compiles
                        notes.append(f"{sid} target match: {why}")
                    else:
                        patterns += 1
        for key in ("checks", "precision_checks"):
            checks = step.get(key)
            if not isinstance(checks, list):
                continue
            if len(checks) > MAX_STEP_CHECKS:
                notes.append(f"{sid}.{key}: {len(checks)} checks, over {MAX_STEP_CHECKS}")
            for c in checks:
                if not isinstance(c, dict):
                    continue
                cid = c.get("id") or "?"
                f = c.get("file")
                if f not in (None, "") and (why := rel_problem(str(f))):
                    notes.append(f"{sid} check {cid}: file {_short(f)}: {why}")
                for k in ("pattern", "metric_pattern"):
                    if c.get(k) is not None:
                        if why := static_problem(c.get(k)):
                            notes.append(f"{sid} check {cid}: {k}: {why}")
                        else:
                            patterns += 1
    if patterns > MAX_LESSON_PATTERNS:
        notes.append(f"{patterns} patterns, over {MAX_LESSON_PATTERNS} per lesson")
    return notes
