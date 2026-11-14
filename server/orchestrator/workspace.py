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
    found = shutil.which("code")
    if found:
        return found
    return BUNDLED_CLI if Path(BUNDLED_CLI).exists() else None


def target_location(workdir: str | Path, step: dict) -> tuple[Path, int] | None:
    """(absolute file, 1-based line) of the step's first target whose file exists."""
    for t in step.get("targets") or []:
        f = t.get("file")
        if not f:
            continue
        path = Path(f) if Path(f).is_absolute() else Path(workdir) / f
        if not path.is_file():
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


def requirements(graph: dict, folder: str) -> dict | None:
    """S2's requirements check, if server.workspace provides one:
    {needs_editor: bool, title?, summary?, items?: [{name, installed, install?}]}. Else None."""
    ws = _s2()
    fn = getattr(ws, "requirements", None) if ws is not None else None
    if fn is None:
        return None
    try:
        out = fn(graph, folder)
        return dict(out) if out else None
    except Exception:  # noqa: BLE001
        log.exception("workspace.requirements failed")
        return None


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

    def open(self, workdir: str, force: bool = False) -> None:
        """force: the learner asked for it (the "Open VS Code?" card), so ignore the auto-open flag."""
        if not (self.enabled or force) or not Path(workdir).is_dir() or self.opened == workdir:
            return
        self.opened = workdir
        ws = _s2()
        if ws is not None:  # S2: `code -n <dir> -g <starter file>`, fallback `open -a`
            ok = ws.open_editor(workdir, ws.open_file_for(Path(workdir)), runner=self.run)
            log.info("opened workspace %s in VS Code: %s", workdir, ok)
            return
        ok = False
        if sys.platform == "darwin":
            ok = self.run(["open", "-a", VSCODE_APP, workdir])
        if not ok and (cli := code_cli()):
            ok = self.run([cli, workdir])
        log.info("opened workspace %s in VS Code: %s", workdir, ok)

    def goto(self, path: str, line: int) -> None:
        cli = code_cli()
        if cli:
            self.run([cli, "-r", "-g", f"{path}:{line}"])

    def goto_target(self, workdir: str, step: dict) -> None:
        loc = target_location(workdir, step)
        cli = code_cli()
        if loc is None or cli is None:
            return
        path, line = loc
        self.run([cli, "-r", "-g", f"{path}:{line}"])
