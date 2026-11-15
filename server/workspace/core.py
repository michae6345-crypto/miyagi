"""prepare(): one folder per lesson under ~/miyagi/lessons, scaffolded from the lesson itself."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path

from . import paths, scaffold

log = logging.getLogger("server.workspace")

STATE_DIR = ".miyagi-state"  # under lessons_root(): one JSON per folder (keeps the learner's folder clean)
# .vscode/settings.json in each code lesson folder (workspace settings; the learner's own VS Code settings stay as is).
# editor.accessibilitySupport is left out by default: our AXManualAccessibility read flips VS Code ("auto") into
# "Screen Reader Optimized", but "off" makes VS Code 1.146 empty the editor's and terminal's AX text, so Miyagi would
# fall back to OCR. MIYAGI_VSCODE_ACCESSIBILITY=off|on|auto writes that value (never "off" while VoiceOver runs).
# window.title: VS Code's macOS default title drops the "●" unsaved marker that the screen code reads.
VSCODE_A11Y = os.environ.get("MIYAGI_VSCODE_ACCESSIBILITY", "").strip().lower()
VSCODE_A11Y = VSCODE_A11Y if VSCODE_A11Y in ("off", "on", "auto") else ""
VSCODE_TITLE = "${dirty}${activeEditorShort}${separator}${rootName}${separator}${profileName}"
# Desktop test 8 (Nov 15, 05:50-05:54): VS Code's terminal sticky scroll pinned the 3-row `.venv/bin/python …/nn.py`
# command over an 11-row terminal (the early epochs and step 6's "[-1.0, 0.0, 1.0]" went under it); the minimap took
# width the code needed; and VS Code opened the folder with a zsh terminal of its own, so the ▷'s "Python" terminal
# made two. hideOnStartup "whenEmpty" + no persistent sessions: no terminal until a run makes its own.
LESSON_VIEW = {
    "terminal.integrated.stickyScroll.enabled": False,
    "editor.minimap.enabled": False,
    "terminal.integrated.enablePersistentSessions": False,
    "terminal.integrated.hideOnStartup": "whenEmpty",
}


def _state_file(folder: Path) -> Path:
    return folder.parent / STATE_DIR / f"{folder.name}.json"


def read_state(folder: Path) -> dict | None:
    """What prepare() did for this folder (stack, files, open_file, model, dropped...), or None."""
    try:
        return json.loads(_state_file(folder).read_text())
    except (OSError, ValueError):
        return None


def _own_folder(lesson: dict, root: Path | None = None) -> Path:
    return ((root or paths.lessons_root()).expanduser() / paths.folder_name(lesson)).resolve()


def _redirect(state: dict | None) -> Path | None:
    r = (state or {}).get("redirect")
    return Path(r) if r and Path(r).is_dir() else None


def lesson_folder(lesson: dict, *, root: Path | None = None) -> Path:
    """The folder prepare() returns for this lesson (the hero's, `<root>/<slug>-<hash>`, or the folder it continues in),
    found without creating or writing anything. Desktop test 10: the preflight card checks the packages in THIS folder's
    .venv, the same ones the setup card checks after Build (it used to check the build's placeholder folder, so a
    lesson .venv that already had TensorFlow showed "tensorflow ✕ · 4 to install")."""
    hero = paths.hero_workdir(lesson)
    if hero is not None:
        return hero
    folder = _own_folder(lesson, root)
    return _redirect(read_state(folder)) or folder


def prepare(lesson: dict, goal: str = "", *, root: Path | None = None, client=None) -> Path:
    """Create (or reuse) the learner's folder for this lesson and return its absolute path.

    `lesson` is the step graph from server.lesson.build_lesson. The hero lesson returns its own
    folder (demo/pinn-lab or ORCH_HERO_WORKDIR) untouched. Otherwise:
    `<root>/<slug-of-title>-<hash>/`, scaffolded once with Claude's starter files + README.md.
    A folder that was already scaffolded is returned as is (the learner's work is never
    overwritten); existing files are never replaced. Never raises on Claude/API problems: the
    folder then gets README.md only and read_state(folder)["error"] says why.
    """
    hero = paths.hero_workdir(lesson)
    if hero is not None:
        log.info("hero lesson: using %s", hero)
        return hero

    folder = _own_folder(lesson, root)
    folder.mkdir(parents=True, exist_ok=True)
    state = read_state(folder)
    if redirect := _redirect(state):  # "use this folder" (active.adopt_folder)
        log.info("lesson %s continues in %s", folder.name, redirect)
        return redirect
    if state and state.get("scaffolded") and not state.get("error"):
        log.info("reusing lesson folder %s", folder)
        # README is ours and cheap: rewrite it so wording fixes reach existing folders (no Claude call).
        sc = _state_scaffold(folder, state)
        _write_readme(folder, lesson, goal, sc)
        if sc.lesson_kind == "code":
            _write_vscode_settings(folder)
        return folder

    t0 = time.monotonic()
    sc = scaffold.generate(lesson, goal, client=client)
    written = _apply(folder, sc)
    readme = _write_readme(folder, lesson, goal, sc)
    if sc.lesson_kind == "code":
        _write_vscode_settings(folder)
    st = {
        "scaffolded": True,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lesson_id": paths.lesson_meta(lesson).get("id"),
        "title": paths.lesson_meta(lesson).get("title"),
        "lesson_kind": sc.lesson_kind,
        "stack": sc.stack,
        "summary": sc.summary,
        "setup": sc.setup,
        "open_file": sc.open_file,
        "files": written,
        "readme": readme,
        "git": {"init": sc.git_init, "ops": len(sc.git_ops), "commits": sum(op["op"] == "commit" for op in sc.git_ops)},
        "dropped": sc.dropped,
        "model": sc.model,
        "error": sc.error,
        "seconds": round(time.monotonic() - t0, 1),
    }
    sf = _state_file(folder)
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(st, indent=1))
    log.info("prepared %s: %d file(s), git=%s, dropped=%d%s", folder, len(written), sc.git_init,
             len(sc.dropped), f", error: {sc.error}" if sc.error else "")
    return folder


def set_redirect(lesson_folder: Path, to: Path) -> None:
    """Remember that this lesson continues in another folder (the learner's choice); prepare() returns it."""
    st = read_state(lesson_folder) or {}
    st["redirect"] = str(to)
    sf = _state_file(lesson_folder)
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(st, indent=1))


PREVIOUS_DIR = ".miyagi-previous"
# never set aside: installs, the video's downloads, our README; dot entries (.venv, .vscode, .git...) except notebook
# checkpoints, which hold the last run's notebook too
_KEEP = {"README.md", "tutorial", "venv", "node_modules", "__pycache__"}


def set_aside_previous(folder: str | Path) -> Path | None:
    """A FRESH build of a lesson whose folder is reused (Michael, Nov 15 7:19: test 9's mnist.ipynb passed s1-s3 by
    itself on a new build): the learner's files from the earlier run (notebooks, .py files, folders they made) move to
    <folder>/.miyagi-previous/<YYYYmmdd-HHMMSS>/, nothing deleted. Kept in place: .venv and other dot entries, tutorial/
    downloads, README.md and the starter files prepare() wrote (state "files"). Returns where they went, or None when
    there was nothing to move. A resume never comes here. Blocking (file I/O); never raises."""
    folder = Path(folder).expanduser().resolve()
    try:
        st = read_state(folder) or {}
        starters = {Path(f).parts[0] for f in st.get("files") or [] if f}
        if st.get("readme"):
            starters.add(Path(st["readme"]).parts[0])
        move = [p for p in folder.iterdir()
                if p.name not in _KEEP and p.name not in starters
                and (not p.name.startswith(".") or p.name == ".ipynb_checkpoints")]
        if not move:
            return None
        dest = folder / PREVIOUS_DIR / time.strftime("%Y%m%d-%H%M%S")
        n, i = dest, 1
        while n.exists():  # two fresh builds within a second
            n, i = dest.with_name(f"{dest.name}-{i}"), i + 1
        n.mkdir(parents=True)
        for p in move:
            p.rename(n / p.name)
        log.info("fresh build of %s: the last run's %s moved to %s", folder.name, ", ".join(sorted(p.name for p in move)),
                 n.relative_to(folder))
        return n
    except OSError as e:
        log.warning("could not set the last run's files aside in %s: %s", folder, e)
        return None


def open_file_for(folder: Path) -> str | None:
    """The starter file prepare() picked to open first (else README.md if present)."""
    st = read_state(folder) or {}
    f = st.get("open_file")
    if f and (folder / f).is_file():
        return f
    return st.get("readme") if st.get("readme") and (folder / st["readme"]).is_file() else None


# --------------------------------------------------------------------------- writing

def _write(folder: Path, rel: str, content: str, *, overwrite: bool = False) -> bool:
    p = (folder / rel).resolve()
    if folder not in p.parents:  # belt and braces on top of scaffold._safe_rel
        return False
    if p.exists() and not overwrite:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if content.endswith("\n") or not content else content + "\n")
    return True


def _voiceover_on() -> bool:
    try:
        import AppKit
        return bool(AppKit.NSWorkspace.sharedWorkspace().isVoiceOverEnabled())
    except Exception:  # noqa: BLE001 - not macOS / no pyobjc
        return False


def _write_vscode_settings(folder: Path) -> None:
    """Add our keys to <folder>/.vscode/settings.json; a value already there always wins, and a file that isn't plain
    JSON (VS Code allows comments) is left alone. A lesson git repo ignores .vscode/ locally (.git/info/exclude)."""
    p = folder / ".vscode" / "settings.json"
    try:
        cur = json.loads(p.read_text()) if p.exists() else {}
    except (OSError, ValueError):
        return
    if not isinstance(cur, dict):
        return
    # Only code lessons get this file. No Copilot Chat panel in a lesson window (it took ~30% of the width), and no AI
    # that writes the code for the learner (that defeats the lesson). The learner's global settings stay as they are.
    want = {"window.title": VSCODE_TITLE, "workbench.secondarySideBar.defaultVisibility": "hidden",
            "chat.disableAIFeatures": True, **LESSON_VIEW, **python_terminal_settings(folder)}
    a11y = VSCODE_A11Y
    if not a11y:
        # The companion extension (installed Nov 14) gives exact buffer/terminal state, so the editor's AX text isn't
        # needed: turn off "Screen Reader Optimized" (Michael's desktop test) whenever it answers.
        try:
            from . import vscode_ext
            a11y = "off" if vscode_ext.available() else ""
        except Exception:  # noqa: BLE001 - best effort, never block lesson setup
            a11y = ""
    if a11y and not (a11y == "off" and _voiceover_on()):
        want["editor.accessibilitySupport"] = a11y
    if want.get("editor.accessibilitySupport") == "off":
        # t8: lines 1, 27 and 49 of nn.py ran past the editor's right edge. Wrapped only while the boxes come from the
        # OCR'd gutter (a line number per file line): the Accessibility caret row (accessibilitySupport not "off")
        # counts one row per file line, so a wrapped line above the box would put it a row off.
        want["editor.wordWrap"] = "on"
    try:
        if {**want, **cur} != cur:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({**want, **cur}, indent=2) + "\n")
        excl = folder / ".git" / "info" / "exclude"
        if excl.parent.is_dir():
            text = excl.read_text(errors="replace") if excl.exists() else ""
            if ".vscode/" not in text.splitlines():
                excl.write_text(text + ("\n" if text and not text.endswith("\n") else "") + ".vscode/\n")
    except OSError as e:
        log.warning("could not write VS Code settings for %s: %s", folder.name, e)


# A Python lesson's terminals use its .venv without anything typed into them. t5 (Nov 15): the Python extension's
# auto-activation typed ^C + `source .venv/bin/activate` into the "Miyagi" terminal right after Run it for me typed
# `python3 main.py`, so the program never ran. With activation off, the .venv goes first on PATH instead. PATH alone
# isn't enough on macOS: VS Code starts zsh as a login shell, /etc/zprofile's path_helper (and Homebrew's shellenv in
# ~/.zprofile) put the system paths back in front, and `python3` would be Homebrew's, without NumPy. VS Code's shell
# integration re-applies VSCODE_PATH_PREFIX after the login profile (shellIntegration-profile.zsh / -bash.sh, #99878),
# so the prefix is given there too. VS Code sets that variable itself only for extensions that PREPEND to PATH
# (none here: Copilot and debugpy append), which would then win over this one.
_VENV = "${workspaceFolder}/.venv"
PYTHON_TERMINAL = {
    "python.terminal.activateEnvironment": False,  # also turns off the Python Environments extension's activation
    "terminal.integrated.env.osx": {"PATH": f"{_VENV}/bin:${{env:PATH}}", "VIRTUAL_ENV": _VENV,
                                    "VSCODE_PATH_PREFIX": f"{_VENV}/bin:"},
}


def is_python_folder(folder: Path) -> bool:
    """A Python lesson folder: its .venv, requirements.txt / pyproject.toml, or a .py file at the top."""
    try:
        return ((folder / ".venv").is_dir() or (folder / "requirements.txt").is_file()
                or (folder / "pyproject.toml").is_file() or any(folder.glob("*.py")))
    except OSError:
        return False


def python_terminal_settings(folder: Path) -> dict:
    """PYTHON_TERMINAL for a Python lesson folder, else {}."""
    return json.loads(json.dumps(PYTHON_TERMINAL)) if is_python_folder(folder) else {}


def ensure_python_terminal(folder: Path | str) -> bool:
    """Merge PYTHON_TERMINAL into an existing Python lesson folder's .vscode/settings.json (a lesson built before this
    fix, opened again; Run it for me before it creates the terminal). A value already there wins, a file that isn't
    plain JSON is left alone. True when the file changed (VS Code picks it up within a second, for new terminals)."""
    folder = Path(folder)
    want = python_terminal_settings(folder)
    if not want:
        return False
    p = folder / ".vscode" / "settings.json"
    try:
        cur = json.loads(p.read_text()) if p.exists() else {}
        if not isinstance(cur, dict) or {**want, **cur} == cur:
            return False
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({**cur, **{k: v for k, v in want.items() if k not in cur}}, indent=2) + "\n")
        log.info("VS Code terminal settings for %s: the .venv without activation", folder.name)
        return True
    except (OSError, ValueError) as e:
        log.warning("could not merge terminal settings for %s: %s", folder.name, e)
        return False


def ensure_notebook_autosave(folder: Path | str) -> bool:
    """t9 V3: a notebook lesson's folder saves by itself (files.autoSave afterDelay, ~1 s): a run cell's outputs reach
    the .ipynb the checks read, and the learner never presses ⌘S. A value already there wins; a file that isn't plain
    JSON is left alone. True when the file changed (VS Code picks workspace settings up live)."""
    p = Path(folder) / ".vscode" / "settings.json"
    try:
        cur = json.loads(p.read_text()) if p.exists() else {}
        if not isinstance(cur, dict) or "files.autoSave" in cur:
            return False
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({**cur, "files.autoSave": "afterDelay"}, indent=2) + "\n")
        return True
    except (OSError, ValueError) as e:
        log.warning("could not turn on autosave for %s: %s", Path(folder).name, e)
        return False


def _git(folder: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "miyagi", "GIT_AUTHOR_EMAIL": "miyagi@localhost",
           "GIT_COMMITTER_NAME": "miyagi", "GIT_COMMITTER_EMAIL": "miyagi@localhost"}
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                   cwd=folder, env=env, check=True, capture_output=True, timeout=20)


def _apply(folder: Path, sc: scaffold.Scaffold) -> list[str]:
    written: list[str] = []
    if sc.git_init and not (folder / ".git").exists():
        try:
            _git(folder, "init", "-q", "-b", sc.git_default_branch)
            for op in sc.git_ops:
                if op["op"] == "commit":
                    for rel, content in op["files"].items():
                        if _write(folder, rel, content, overwrite=True):
                            written.append(rel)
                    _git(folder, "add", "-A")
                    _git(folder, "commit", "-q", "--allow-empty", "-m", op["message"])
                elif op["op"] == "branch":
                    _git(folder, "checkout", "-q", "-b", op["name"])
                elif op["op"] == "checkout":
                    _git(folder, "checkout", "-q", op["name"])
        except (subprocess.SubprocessError, OSError) as e:
            err = getattr(e, "stderr", b"") or b""
            sc.dropped.append(f"git history: {e} {err.decode(errors='replace')[:200]}".strip())
            log.warning("git history for %s failed: %s", folder, e)
    for rel, content in sc.files.items():
        if _write(folder, rel, content):
            written.append(rel)
    return sorted(set(written))


def _state_scaffold(folder: Path, state: dict) -> scaffold.Scaffold:
    sc = scaffold.Scaffold(lesson_kind=state.get("lesson_kind") or "code", stack=state.get("stack") or "",
                           summary=state.get("summary") or "", setup=state.get("setup") or [])
    sc.files = {f: "" for f in state.get("files") or [] if (folder / f).is_file()}
    sc.git_init = bool((state.get("git") or {}).get("init"))
    sc.git_ops = [{"op": "commit"}] * int((state.get("git") or {}).get("commits") or 0)
    return sc


def refresh_readme(folder: str | Path, lesson: dict, goal: str = "") -> str | None:
    """t10: rewrite our README from the lesson as it will run (after the lesson's .venv / notebook normalisations, so
    step 1 isn't "Create venv and start Jupyter" any more). Only a folder prepare() scaffolded, only our own README.
    Never raises; -> the README's name or None."""
    try:
        folder = Path(folder)
        state = read_state(folder) if folder.is_dir() else None
        if not state or not state.get("scaffolded") or state.get("error"):
            return None
        return _write_readme(folder, lesson, goal or str(state.get("goal") or ""), _state_scaffold(folder, state))
    except Exception:  # noqa: BLE001
        log.exception("README refresh failed for %s", folder)
        return None


def _folder_note(folder: Path) -> str:
    """t10: what the lesson folder really starts with ("The folder starts empty" was wrong next to .venv/ and
    tutorial/)."""
    have = []
    if (folder / ".venv").is_dir() or (folder / "venv").is_dir():
        have.append("`.venv/` is the lesson's Python environment (Miyagi made it; you don't need to make another)")
    if (folder / "tutorial").is_dir():
        have.append("`tutorial/` holds the video's own files, the finished version (peek only when you're stuck)")
    if not have:
        return "The folder starts empty: step 1 creates the project."
    return " ".join(f"{h}." for h in have)


def _fmt_t(t) -> str:
    try:
        t = int(float(t))
    except (TypeError, ValueError):
        return ""
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def _write_readme(folder: Path, graph: dict, goal: str, sc: scaffold.Scaffold) -> str | None:
    """README.md (MIYAGI.md if the lesson itself has the learner write README.md)."""
    meta = paths.lesson_meta(graph)
    name = "MIYAGI.md" if "README.md" in scaffold.learner_creates(graph) else "README.md"
    srcs = [s for s in graph.get("sources") or [] if s.get("url")]
    # The video's own topic leads; what the learner typed is only context.
    title = meta.get("title") or (srcs[0].get("title") if srcs else "") or "Lesson"
    lines = [f"# {title}", ""]
    asked = (goal or meta.get("goal") or "").strip()
    if asked and asked.lower() not in title.lower():
        lines += [f"<sub>You asked for: {asked}</sub>", ""]
    if note := goal_match_note(meta.get("goalMatch")):
        lines += [f"> {note}", ""]
    if srcs:
        lines += ["## Tutorial", ""] + [f"- [{s.get('title') or s['url']}]({s['url']})" for s in srcs] + [""]
    steps = graph.get("steps") or []
    if steps:
        lines += ["## Steps", ""]
        for i, s in enumerate(steps, 1):
            v = s.get("video") or {}
            at = f" ({_fmt_t(v.get('start'))})" if v.get("start") is not None and _fmt_t(v.get("start")) else ""
            text = f"{s.get('index', i)}. {s.get('title', '')}{at}"
            # A title shown in the editor must not satisfy an editor screen check by itself.
            if scaffold.leaks(name, text, graph):
                text = f"{s.get('index', i)}. Step {s.get('index', i)}{at} (see the overlay)"
            lines.append(text)
        lines.append("")
    if sc.setup:
        lines += ["## Before step 1", "", "```bash"] + sc.setup + ["```", ""]
    if sc.files or sc.git_init:
        lines += ["## Starter files", ""]
        if sc.summary:
            lines += [sc.summary, ""]
        lines += [f"- `{p}`" for p in sc.files]
        if sc.git_init:
            lines.append(f"- a git repository with a prepared history ({sum(op['op'] == 'commit' for op in sc.git_ops)} commits)")
        data = [p for p in sc.files if Path(p).suffix in (".csv", ".tsv", ".jsonl")]
        if data:
            lines += ["", "Data files here are small samples with the tutorial's columns, not the original dataset."]
        lines.append("")
    elif sc.lesson_kind == "no_code":
        line = "Nothing to set up here: this lesson happens in the apps the video uses{}, not in code files."
        named = line.format(f" ({sc.stack})" if sc.stack else "")
        lines += [line.format("") if scaffold.leaks(name, named, graph) else named, ""]
    elif sc.lesson_kind == "conceptual":
        lines += ["Nothing to set up here: this lesson explains ideas; there is no code to write.", ""]
    elif not sc.error:
        lines += [_folder_note(folder), ""]
    lines += ["_Prepared by miyagi. Starter files only; every step is yours to write._" if sc.lesson_kind == "code"
              else "_Prepared by miyagi._", ""]
    # Nothing in the README may pass an editor screen check on its own: drop any line that would.
    lines = [ln for ln in lines if not ln.strip() or ln.startswith("#") or not scaffold.leaks(name, ln, graph)]
    text = "\n".join(lines)
    target = folder / name
    if scaffold.leaks(name, text, graph) or (target.exists() and not _ours(target)):
        return None
    _write(folder, name, text, overwrite=True)
    return name


GOAL_MATCH_LOW = 0.7  # below this the README shows a heads-up (0.5 "different project/tool" included)


def goal_match_note(gm) -> str:
    """A heads-up line when E2's lesson.goalMatch says the video only partly matches the request.

    E2 sends {"score": 0..1 | null, "note": "<one sentence>"}; null = unknown (no goal / not scored), never low.
    Also accepts a number (0..1, or 0..100), a level string, or {level?, reason?|explanation?}.
    "" when the match is fine or unknown."""
    if gm is None or gm == "":
        return ""
    score, level, why = None, "", ""
    if isinstance(gm, bool):
        return ""
    if isinstance(gm, (int, float)):
        score = float(gm)
    elif isinstance(gm, str):
        level = gm
    elif isinstance(gm, dict):
        raw = gm.get("score", gm.get("value"))
        score = float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
        level = str(gm.get("level") or gm.get("match") or "")
        why = str(gm.get("note") or gm.get("reason") or gm.get("explanation") or gm.get("why") or "").strip()
    if score is not None and score > 1:
        score /= 100
    # E2's rubric: 1 = the video achieves the goal, 0.5 = related but a different project/tool, 0 = unrelated.
    low = (score is not None and score < GOAL_MATCH_LOW) or level.strip().lower() in ("low", "none", "poor", "weak", "partial", "mismatch")
    if not low:
        return ""
    pct = f" (match {round(score * 100)}%)" if score is not None else ""
    return f"Heads-up: this video only partly matches what you asked for{pct}." + (f" {why}" if why else "")


def _ours(p: Path) -> bool:
    try:
        return "_Prepared by miyagi." in p.read_text(errors="replace")
    except OSError:
        return False
