"""Open the learner's project in VS Code and jump to each step's target.

On lesson.ready: `open -a "Visual Studio Code" <workdir>` (fallback: `code <workdir>`).
On step.started: `code -r -g <file>:<line>` for the step's first target whose file exists
(line = first line matching target.match, else 1).

Off unless ORCH_OPEN_WORKSPACE=1 (scripts/miyagi-engine.sh turns it on). Commands run
detached; failures are logged, never raised.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .config import env_flag

log = logging.getLogger("orchestrator.workspace")

VSCODE_APP = "Visual Studio Code"
BUNDLED_CLI = "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"


def code_cli() -> str | None:
    """The editor CLI for `-g file:line` jumps: S2's choice when available (e.g. Cursor when installed), so the
    jumps go to the same editor open_editor opened; else VS Code's `code`."""
    ws = _s2()
    editor = getattr(ws, "editor", None) if ws is not None else None
    fn = getattr(editor, "code_cli", None) if editor is not None else None
    if fn is not None:
        try:
            cli = fn()
            if cli:
                return cli
        except Exception:  # noqa: BLE001
            pass
    found = shutil.which("code")
    if found:
        return found
    return BUNDLED_CLI if Path(BUNDLED_CLI).exists() else None


SKIP_SEARCH = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}


def resolve_file(workdir: str | Path, rel: str, open_titles: list[str] | None = None) -> Path | None:
    """The real path of a lesson file: workdir/<rel>; git's rebase todo under .git/rebase-merge/; the same
    file nested one level down (create-react-app's demo-app/src/...); a file the editor has open (its window
    title) with the same name. None if nothing matches."""
    wd = Path(workdir)
    rel = (rel or "").strip()
    if not rel:
        return None
    p = Path(rel) if Path(rel).is_absolute() else wd / rel
    if p.is_file():
        return p
    name = Path(rel).name
    if name == "git-rebase-todo":
        for cand in (wd / ".git" / "rebase-merge" / name, wd / ".git" / "rebase-apply" / name):
            if cand.is_file():
                return cand
    if wd.is_dir():
        try:
            for child in sorted(wd.iterdir()):
                if child.is_dir() and child.name not in SKIP_SEARCH and not child.name.startswith("."):
                    cand = child / rel
                    if cand.is_file():
                        return cand
            hits = [h for h in wd.rglob(name) if not (set(h.relative_to(wd).parts) & SKIP_SEARCH)][:2]
            if len(hits) == 1:
                return hits[0]
        except OSError:
            pass
    for title in open_titles or []:  # "● App.js — demo-app" -> App.js
        t = title.lstrip("● ").split(" — ")[0].split(" - ")[0].strip()
        if t == name and wd.is_dir():
            hits = [h for h in wd.rglob(t) if not (set(h.relative_to(wd).parts) & SKIP_SEARCH)][:1]
            if hits:
                return hits[0]
    return None


def _accepts_kw(fn, name: str) -> bool:
    import inspect

    try:
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def line_rect(path: str | Path, line: int) -> dict | None:
    """S2: where `line` of `path` is on screen in the open editor ({x, y, w, h, ...}, spotlight space), via
    Accessibility, else E6's locate_line. None when it can't tell. Blocking (a few AX reads): use a thread."""
    ws = _s2()
    fn = getattr(ws, "editor_line_rect", None) if ws is not None else None
    if fn is None:
        return None
    try:
        return fn(str(path), int(line))
    except Exception:  # noqa: BLE001
        log.exception("editor_line_rect failed")
        return None


def line_location(path: str | Path, line: int) -> dict:
    """S2's editor_line_location: {rect | None, source, reason, direction?, ...} (Accessibility, else E6's
    locate_line). {} when unavailable. Blocking: use a thread."""
    ws = _s2()
    fn = getattr(ws, "editor_line_location", None) if ws is not None else None
    if fn is None:
        r = line_rect(path, line)
        return {"rect": r} if r else {}
    try:
        return dict(fn(str(path), int(line)) or {})
    except Exception:  # noqa: BLE001
        log.exception("editor_line_location failed")
        return {}


def target_location(workdir: str | Path, step: dict) -> tuple[Path, int] | None:
    """(absolute file, 1-based line) of the step's first target whose file exists."""
    for t in step.get("targets") or []:
        f = t.get("file")
        if not f:
            continue
        path = resolve_file(workdir, f)
        if path is None:
            continue
        line = 1
        match = t.get("match")
        if match:
            try:
                text = path.read_text(errors="replace")
            except OSError:
                return path, 1
            try:
                rx = re.compile(match)
                hit = lambda s: rx.search(s) is not None  # noqa: E731
            except re.error:
                hit = lambda s: match in s  # noqa: E731
            for i, ln in enumerate(text.splitlines(), start=1):
                if hit(ln):
                    line = i
                    break
        return path, line
    return None


def _s2():
    """S2's server.workspace (per-lesson folders + starter files), or None if it isn't installed."""
    try:
        import server.workspace as ws

        return ws
    except Exception:  # noqa: BLE001
        return None


def build_workdir(url: str, goal: str) -> str:
    """The workdir to hand build_lesson. TUT_WORKDIR pins one folder (dev); otherwise S2 decides
    (the hero video -> demo/pinn-lab, anything else -> a not-yet-existing path), falling back to
    config.lesson_workdir."""
    from . import config

    if os.environ.get("TUT_WORKDIR"):
        return str(config.default_workdir())
    ws = _s2()
    if ws is not None:
        return ws.build_workdir(url)
    return str(config.lesson_workdir(url, goal))


def prepare(graph: dict, goal: str) -> str | None:
    """Create/fill the lesson's folder (S2; may call Claude for starter files, 2-25 s, never raises).
    None when TUT_WORKDIR pins the folder or S2 isn't available."""
    if os.environ.get("TUT_WORKDIR"):
        return None
    ws = _s2()
    if ws is None:
        return None
    try:
        return str(ws.prepare(graph, goal))
    except Exception:  # noqa: BLE001
        log.exception("workspace.prepare failed")
        return None


CODE_APPS = {"code", "vs code", "vscode", "visual studio code", "cursor", "terminal", "iterm", "iterm2"}


def needs_editor(graph: dict) -> bool:
    """Does this lesson happen in a code editor? True if its targets/checks name a code app or a file;
    False for, e.g., a Blender or Figma tutorial (their targets name those apps and no files)."""
    apps: set[str] = set()
    files = False
    for st in graph.get("steps", []):
        for t in st.get("targets") or []:
            apps.add((t.get("app") or "").strip().lower())
            files = files or bool(t.get("file"))
        for c in (st.get("checks") or []) + (st.get("precision_checks") or []):
            apps.add((c.get("app") or "").strip().lower())
            files = files or c.get("type", "").startswith(("file_", "command_")) or bool(c.get("file"))
    apps.discard("")
    if apps & CODE_APPS:
        return True
    if apps:  # only non-code apps named (Blender, Figma, ...)
        return False
    return files


def requirements(graph: dict, folder: str) -> list[dict] | None:
    """S2's setup check: the lesson's tools, each checked on this Mac (read-only; Claude haiku, cached per
    lesson). None when S2's module isn't available; [] when it couldn't tell (no key / error). Blocking: run
    it in a thread."""
    ws = _s2()
    fn = getattr(ws, "requirements", None) if ws is not None else None
    if fn is None:
        return None
    try:
        return list(fn(graph, workdir=folder) or [])
    except Exception:  # noqa: BLE001
        log.exception("workspace.requirements failed")
        return []


def setup_card(items: list[dict], resources: list[dict] | None = None) -> dict | None:
    ws = _s2()
    fn = getattr(ws, "setup_card", None) if ws is not None else None
    if fn is None:
        return None
    return fn(items, resources=resources) if resources else fn(items)


def find_resources(graph: dict) -> list[dict]:
    """S2: code / notebooks / data the video links (one watch-page fetch per video, cached). Blocking."""
    ws = _s2()
    fn = getattr(ws, "find_resources", None) if ws is not None else None
    try:
        return list(fn(graph) or []) if fn else []
    except Exception:  # noqa: BLE001
        log.exception("workspace.find_resources failed")
        return []


def download_resources(graph: dict, folder: str) -> tuple[list[dict], str]:
    """S2: download them into <lesson folder>/tutorial/ (never run). -> (results, one-line summary). Blocking."""
    ws = _s2()
    fn = getattr(ws, "download_resources", None) if ws is not None else None
    if fn is None:
        return [], "Downloads aren't available."
    res = list(fn(graph, folder=folder) or [])
    summ = getattr(ws, "download_summary", None)
    return res, (summ(res) if summ else f"Downloaded {len(res)} files.")


def editor_needed(items: list[dict]) -> bool:
    ws = _s2()
    fn = getattr(ws, "editor_needed", None) if ws is not None else None
    return bool(fn(items)) if fn else any(it.get("kind") == "editor" and it.get("needed") for it in items)


def install(item: dict, folder: str, on_line) -> dict:
    """S2: brew / brew --cask / pip into <folder>/.venv. ONLY after the learner said yes. Blocking."""
    ws = _s2()
    fn = getattr(ws, "install", None) if ws is not None else None
    if fn is None:
        return {"ok": False, "tool": item.get("tool"), "error": "installer not available"}
    return dict(fn(item, workdir=folder, on_line=on_line))


def goto_argv(path: str, line: int) -> list[str] | None:
    """S2: the jump command for the learner's editor (Cursor if that's theirs), so jumps never launch a
    second editor; else VS Code's `code -r -g`."""
    ws = _s2()
    fn = getattr(ws, "goto_argv", None) if ws is not None else None
    if fn is not None:
        try:
            return fn(path, line)
        except Exception:  # noqa: BLE001
            log.exception("workspace.goto_argv failed")
    cli = code_cli()
    return [cli, "-r", "-g", f"{path}:{line}"] if cli else None


def editor_label() -> str:
    ws = _s2()
    fn = getattr(ws, "editor_label", None) if ws is not None else None
    try:
        return fn() if fn else "VS Code"
    except Exception:  # noqa: BLE001
        return "VS Code"


class Workspace:
    def __init__(self, enabled: bool | None = None, runner=None):
        self.enabled = env_flag("ORCH_OPEN_WORKSPACE", False) if enabled is None else enabled
        self.run = runner or self._spawn  # injectable for tests
        self.opened: str | None = None

    @staticmethod
    def _spawn(argv: list[str]) -> bool:
        try:
            subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True
        except OSError as e:
            log.warning("could not run %s: %s", argv[0], e)
            return False

    def open(self, workdir: str, force: bool = False, full: bool = False) -> None:
        """force: the learner asked for it (the "Open VS Code?" card), so ignore the auto-open flag.
        full: "Just teach me" lessons: the editor fills the screen (no video to dock beside it)."""
        if not (self.enabled or force) or not Path(workdir).is_dir() or self.opened == workdir:
            return
        self.opened = workdir
        ws = _s2()
        if ws is not None and full and hasattr(ws, "open_editor_report"):
            ok = self._open_full(ws, workdir)
            log.info("opened workspace %s full screen: %s", workdir, ok)
            return
        if ws is not None:  # S2: `code -n <dir> -g <starter file>` (PATH, else the app's bundled CLI), fallback `open -a`
            # the real engine lets S2 run its own runner: it waits for the CLI's exit code, so a failing `code`
            # falls back to `open -a "Visual Studio Code" <dir>` (tests inject theirs)
            runner = None if self.run == self._spawn else self.run
            ok = ws.open_editor(workdir, ws.open_file_for(Path(workdir)), runner=runner)
            log.info("opened workspace %s in VS Code: %s", workdir, ok)
            return
        ok = False
        if sys.platform == "darwin":
            ok = self.run(["open", "-a", VSCODE_APP, workdir])
        if not ok and (cli := code_cli()):
            ok = self.run([cli, workdir])
        log.info("opened workspace %s in VS Code: %s", workdir, ok)

    def _open_full(self, ws, workdir: str) -> bool:
        """S2 opens the editor; then, with Accessibility, S2's arrange() sizes its window to the WHOLE visible
        screen (fraction 1.0). Not a macOS full-screen Space: the overlay must stay on top of it."""
        try:
            from server.workspace import editor as ed
        except Exception:  # noqa: BLE001
            ed = None
        real = self.run == self._spawn  # tests inject a runner: never move real windows from a test
        if real and _accepts_kw(ws.open_editor_report, "fullscreen"):  # S2 (#41): macOS full screen via AX
            rep = ws.open_editor_report(workdir, ws.open_file_for(Path(workdir)), runner=self.run, fullscreen=True)
            log.info("full screen editor: %s", rep.get("fullscreen"))
            return bool(rep.get("opened"))
        editor = ed.preferred_editor() if ed is not None else None
        prev = ed.frontmost_app(skip={editor["app"]}) if (ed is not None and editor) else None
        rep = ws.open_editor_report(workdir, ws.open_file_for(Path(workdir)), runner=self.run,
                                    arrange_windows=False, previous=prev)
        if (rep.get("opened") and real and ed is not None and editor and rep.get("ax_trusted")
                and os.environ.get("MIYAGI_ARRANGE", "1") != "0"):
            import threading

            threading.Thread(target=ed.arrange, args=(editor, prev, rep), kwargs={"fraction": 1.0},
                             daemon=True, name="miyagi-arrange-full").start()
        return bool(rep.get("opened"))

    def goto(self, path: str, line: int) -> None:
        argv = goto_argv(path, line)
        if argv:
            self.run(argv)

    def goto_target(self, workdir: str, step: dict) -> None:
        loc = target_location(workdir, step)
        if loc is None:
            return
        path, line = loc
        argv = goto_argv(str(path), line)
        if argv:
            self.run(argv)
