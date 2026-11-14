"""open_editor(): open a lesson folder in a new VS Code window, focused on a file."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("server.workspace")

VSCODE_APP = "Visual Studio Code"
BUNDLED_CLI = "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"

Runner = Callable[[list[str]], bool]


def code_cli() -> str | None:
    if found := shutil.which("code"):
        return found
    return BUNDLED_CLI if Path(BUNDLED_CLI).exists() else None


def _run(argv: list[str]) -> bool:
    """Run and wait briefly: the `code` CLI hands off to the app and exits 0 within a few seconds."""
    try:
        r = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=15, check=False, start_new_session=True)
    except subprocess.TimeoutExpired:
        return True  # still handing off: the window is coming
    except OSError as e:
        log.warning("could not run %s: %s", argv[0], e)
        return False
    if r.returncode != 0:
        log.warning("%s exited %s: %s", Path(argv[0]).name, r.returncode, r.stderr.decode(errors="replace")[:200])
    return r.returncode == 0


def open_editor(path: Path | str, file: str | None = None, *, runner: Runner | None = None) -> bool:
    """`code -n <dir> -g <file>`; fallback `open -a "Visual Studio Code" <dir> [<file>]`.

    `file` is relative to `path` (or absolute). Returns whether a command succeeded."""
    run = runner or _run
    folder = Path(path).expanduser().resolve()
    if not folder.is_dir():
        log.warning("open_editor: %s is not a folder", folder)
        return False
    target = None
    if file:
        f = Path(file).expanduser()
        f = f if f.is_absolute() else folder / f
        target = f if f.is_file() else None
    if cli := code_cli():
        argv = [cli, "-n", str(folder)] + (["-g", str(target)] if target else [])
        if run(argv):
            return True
    if sys.platform == "darwin":
        return run(["open", "-a", VSCODE_APP, str(folder)] + ([str(target)] if target else []))
    return False
