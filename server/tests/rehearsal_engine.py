"""The Demo rehearsal's PRIVATE engine (server/tests/demo_rehearsal.py starts it; never run it by hand on its own).

    python -m server.tests.rehearsal_engine --port 8899     # with the env demo_rehearsal.engine_env() builds

The same FastAPI app as `python -m server.orchestrator.main`, under its own command line (a `pkill -f
server.orchestrator.main` aimed at the :8787 engine never takes it down), with every desktop side effect made a logged
no-op BEFORE any engine module is imported:

  - subprocess: `open`, the `code` CLI, osascript, pbcopy, screencapture, say, brew, ... run /usr/bin/true instead
    (asyncio's subprocesses go through subprocess.Popen too)
  - Accessibility: AX reads answer "API disabled", AX writes / presses do nothing (no window raised, minimized,
    moved or put in full screen; VS Code's AX tree is never switched on)
  - Quartz: no synthetic key / mouse events; the keyboard / mouse idle reader is off (a presenter with hands off)
  - Workspace.open / goto (VS Code opening on the lesson folder, jumps to a line): recorded only

Each one is appended to $REHEARSAL_SIDE_EFFECTS (JSON lines) so the rehearsal can check "Start opened nn.py".
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time

LOG = os.environ.get("REHEARSAL_SIDE_EFFECTS", "")
# Programs that would touch the desktop, the clipboard or the machine outside the temp folder.
BLOCK = {"open", "code", "code-insiders", "cursor", "osascript", "pbcopy", "pbpaste", "screencapture", "say", "afplay",
         "killall", "pkill", "kill", "brew", "defaults", "launchctl", "shortcuts", "automator"}
_SHELLS = {"sh", "bash", "zsh", "dash"}
_SEPARATORS = {"&&", "||", ";", "|", "&"}


def note(what: str, **kw) -> None:
    if not LOG:
        return
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "what": what, **kw}, default=str) + "\n")
    except OSError:
        pass


def _words(args, shell: bool) -> list[str]:
    if isinstance(args, (str, bytes, os.PathLike)):
        s = os.fsdecode(args)
        if not shell:
            return [s]
        try:
            return shlex.split(s)
        except ValueError:
            return s.split()
    return [os.fsdecode(a) for a in args]


def _programs(words: list[str]) -> list[str]:
    """Every program a command line would start: argv[0], and each command inside `sh -c "a && b | c"`."""
    if not words:
        return []
    out, first = [], os.path.basename(words[0])
    out.append(first)
    if first in _SHELLS and "-c" in words[:-1]:
        inner = words[words.index("-c") + 1]
        try:
            toks = shlex.split(inner)
        except ValueError:
            toks = inner.split()
        start = True
        for tok in toks:
            if tok in _SEPARATORS:
                start = True
                continue
            if start and "=" not in tok.split("/")[0]:  # skip FOO=bar prefixes
                out.append(os.path.basename(tok))
                if tok not in ("cd", "env", "exec", "nohup", "time"):
                    start = False
    return out


class GuardedPopen(subprocess.Popen):
    def __init__(self, args, *a, **kw):
        words = _words(args, bool(kw.get("shell")))
        bad = [p for p in _programs(words) if p in BLOCK
               and not (p == "defaults" and words[1:2] == ["read"])]  # setup's VS Code version read is harmless
        if bad:
            note("blocked", program=bad[0], argv=words[:10])
            args = ["/usr/bin/true"]
            kw["shell"] = False
            kw.pop("executable", None)
            if a:  # positional bufsize / executable: keep bufsize only
                a = a[:1]
        super().__init__(args, *a, **kw)


def _inert_macos() -> None:
    AX_DISABLED = -25211  # kAXErrorAPIDisabled

    def ax_write(name):
        def fn(*args, **kw):
            note("ax", call=name, attr=str(args[1]) if len(args) > 1 else "")
            return AX_DISABLED
        return fn

    for modname in ("HIServices", "ApplicationServices"):
        try:
            mod = __import__(modname)
        except Exception:  # noqa: BLE001 - not on this Mac / not installed: nothing to guard
            continue
        for name in ("AXUIElementSetAttributeValue", "AXUIElementPerformAction", "AXUIElementPostKeyboardEvent"):
            if hasattr(mod, name):
                setattr(mod, name, ax_write(name))
        if hasattr(mod, "AXUIElementCopyAttributeValue"):
            mod.AXUIElementCopyAttributeValue = lambda *a, **k: (AX_DISABLED, None)
        if hasattr(mod, "AXUIElementCopyAttributeNames"):
            mod.AXUIElementCopyAttributeNames = lambda *a, **k: (AX_DISABLED, None)
        if hasattr(mod, "AXUIElementCopyMultipleAttributeValues"):
            mod.AXUIElementCopyMultipleAttributeValues = lambda *a, **k: (AX_DISABLED, None)
        if hasattr(mod, "AXUIElementCopyElementAtPosition"):
            mod.AXUIElementCopyElementAtPosition = lambda *a, **k: (AX_DISABLED, None)
        mod.AXIsProcessTrusted = lambda: False
        mod.AXIsProcessTrustedWithOptions = lambda *a, **k: False
    try:
        import Quartz

        for name in ("CGEventPost", "CGEventPostToPid", "CGEventPostToPSN", "CGWarpMouseCursorPosition",
                     "CGDisplayMoveCursorToPoint"):
            if hasattr(Quartz, name):
                setattr(Quartz, name, (lambda n: lambda *a, **k: note("quartz", call=n))(name))
    except Exception:  # noqa: BLE001
        pass


def install() -> None:
    subprocess.Popen = GuardedPopen  # type: ignore[misc]
    if sys.platform == "darwin":
        _inert_macos()

    from server.orchestrator import inputs, workspace

    orig_init = inputs.Inputs.__init__

    def hands_off(self) -> None:  # no real keyboard / mouse idle times (whoever types on this Mac mid-rehearsal)
        orig_init(self)
        self.q = None

    inputs.Inputs.__init__ = hands_off

    def ws_open(self, workdir, force=False, full=False, explicit=False, file=None, busy=None, cancelled=None):
        would = bool(self.enabled or force) and not (self.blocked and not explicit)
        note("workspace.open", workdir=str(workdir), file=file and str(file), force=force, full=full,
             explicit=explicit, would_open=would)
        if would:
            self.opened = str(workdir)

    def ws_goto(self, path, line, explicit=False):
        note("workspace.goto", path=str(path), line=line, explicit=explicit)

    if not (hasattr(workspace.Workspace, "open") and hasattr(workspace.Workspace, "goto")):
        raise SystemExit("rehearsal_engine: Workspace.open/goto moved; refusing to start an engine that could "
                         "open VS Code on this desktop")
    workspace.Workspace.open = ws_open
    workspace.Workspace.goto = ws_goto
    try:
        from server.workspace import editor

        editor.ax_trusted = lambda: False
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    port = os.environ.get("ENGINE_PORT", "")
    if port == "8787" or "--port" in sys.argv and sys.argv[sys.argv.index("--port") + 1] == "8787":
        raise SystemExit("rehearsal_engine: never on :8787 (the live engine)")
    if not os.environ.get("REHEARSAL_SIDE_EFFECTS"):
        raise SystemExit("rehearsal_engine: start it through server/tests/demo_rehearsal.py (its env isolates it)")
    install()
    from server.orchestrator.main import run

    sys.argv = ["server.tests.rehearsal_engine", *sys.argv[1:]]
    note("engine.start", pid=os.getpid(), home=os.environ.get("HOME"))
    run()


if __name__ == "__main__":
    main()
