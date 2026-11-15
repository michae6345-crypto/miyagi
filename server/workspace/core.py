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


def _state_file(folder: Path) -> Path:
    return folder.parent / STATE_DIR / f"{folder.name}.json"


def read_state(folder: Path) -> dict | None:
    """What prepare() did for this folder (stack, files, open_file, model, dropped...), or None."""
    try:
        return json.loads(_state_file(folder).read_text())
    except (OSError, ValueError):
        return None


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

    base = (root or paths.lessons_root()).expanduser()
    folder = (base / paths.folder_name(lesson)).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    state = read_state(folder)
    if state and state.get("redirect") and Path(state["redirect"]).is_dir():  # "use this folder" (active.adopt_folder)
        log.info("lesson %s continues in %s", folder.name, state["redirect"])
        return Path(state["redirect"])
    if state and state.get("scaffolded") and not state.get("error"):
        log.info("reusing lesson folder %s", folder)
        # README is ours and cheap: rewrite it so wording fixes reach existing folders (no Claude call).
        sc = scaffold.Scaffold(lesson_kind=state.get("lesson_kind") or "code", stack=state.get("stack") or "",
                               summary=state.get("summary") or "", setup=state.get("setup") or [])
        sc.files = {f: "" for f in state.get("files") or [] if (folder / f).is_file()}
        sc.git_init = bool((state.get("git") or {}).get("init"))
        sc.git_ops = [{"op": "commit"}] * int((state.get("git") or {}).get("commits") or 0)
        _write_readme(folder, lesson, goal, sc)
        return folder

    t0 = time.monotonic()
    sc = scaffold.generate(lesson, goal, client=client)
    written = _apply(folder, sc)
    readme = _write_readme(folder, lesson, goal, sc)
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
        lines += ["The folder starts empty: step 1 creates the project.", ""]
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
