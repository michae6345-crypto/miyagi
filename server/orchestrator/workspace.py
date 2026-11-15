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
import threading
from pathlib import Path

from .config import env_flag

log = logging.getLogger("orchestrator.workspace")

VSCODE_APP = "Visual Studio Code"
BUNDLED_CLI = "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
# L5: a "Just teach me" lesson's automatic open waits at most this long while Miyagi is the active app (the learner
# stays in Miyagi's drawer, so "until they leave Miyagi" never came); after it only typing / clicking holds it.
LESSON_MIYAGI_WAIT_S = float(os.environ.get("ORCH_LESSON_OPEN_GRACE_S", "3"))
# A video / generated lesson's automatic open (Session._auto_open_editor): the player and overlay stay in front, so
# "until the learner leaves Miyagi" held VS Code ~30 s (Michael, Nov 15 7:19). Same idea, a shorter grace; typing
# still holds it (busy()).
VIDEO_MIYAGI_WAIT_S = float(os.environ.get("ORCH_VIDEO_OPEN_GRACE_S", "1.5"))


def code_cli() -> str | None:
    """The editor CLI for `-g file:line` jumps: S2's choice when available (VS Code's `code`), so the
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


def anchor_line(text: str, match: str) -> int | None:
    """1-based line of `match` in `text`: the literal text first ("return a + b" has a regex '+'), then as a regex.
    None when it isn't there."""
    lines = text.splitlines()
    for i, ln in enumerate(lines, start=1):
        if match in ln:
            return i
    try:
        rx = re.compile(match)
    except re.error:
        return None
    for i, ln in enumerate(lines, start=1):
        if rx.search(ln):
            return i
    return None


def target_location(workdir: str | Path, step: dict, missing: str = "first") -> tuple[Path, int] | None:
    """(absolute file, 1-based line) of the step's first target whose file exists. missing: where to point when
    the anchor isn't in the file: "first" (line 1) or "end" (where new code goes: the line after the last)."""
    for t in step.get("targets") or []:
        f = t.get("file")
        if not f:
            continue
        path = resolve_file(workdir, f)
        if path is None:
            continue
        match = t.get("match")
        if not match:
            return path, 1
        try:
            text = path.read_text(errors="replace")
        except OSError:
            return path, 1
        line = anchor_line(text, match)
        if line is None:
            line = (len(text.rstrip("\n").splitlines()) + 1) if missing == "end" else 1
        return path, line
    return None


def _s2():
    """S2's server.workspace (per-lesson folders + starter files), or None if it isn't installed."""
    try:
        import server.workspace as ws

        return ws
    except Exception:  # noqa: BLE001
        return None


def notebook_autosave(workdir: str | Path) -> bool:
    """t9 V3: a notebook lesson's folder under the lessons root autosaves (server.workspace.core.ensure_notebook_autosave),
    so the checks read the cells' outputs from the .ipynb. Never the repo's own folders. Never raises."""
    try:
        from server.workspace import core, paths

        root, folder = paths.lessons_root().expanduser().resolve(), Path(workdir).expanduser().resolve()
        if folder == root or root not in folder.parents or not folder.is_dir():
            return False
        return core.ensure_notebook_autosave(folder)
    except Exception:  # noqa: BLE001 - OCR still grades the output
        log.exception("notebook autosave settings failed")
        return False


def python_terminal_settings(workdir: str | Path) -> bool:
    """A Python lesson folder under the lessons root (a lesson built before t5's fix, opened again): its VS Code
    terminals use the .venv without auto-activation typing into them (server.workspace.core.ensure_python_terminal).
    Never the repo's own folders. True when .vscode/settings.json changed. Never raises."""
    try:
        from server.workspace import core, paths

        root, folder = paths.lessons_root().expanduser().resolve(), Path(workdir).expanduser().resolve()
        if folder == root or root not in folder.parents:
            return False
        return core.ensure_python_terminal(folder)
    except Exception:  # noqa: BLE001 - a refinement: Run it for me retries a swallowed command anyway
        log.exception("python terminal settings failed")
        return False


def fit_beside_drawer(workdir: str | Path) -> str:
    """A run step: the lesson's VS Code window leaves room for Miyagi's drawer
    (server.workspace.editor.fit_beside_drawer; full screen / maximized under it: logged and left). Blocking (AX):
    call it in a thread. Never raises."""
    try:
        from server.workspace import editor

        return editor.fit_beside_drawer(str(workdir))
    except Exception:  # noqa: BLE001 - a refinement: the lesson runs without it
        log.exception("fit beside drawer failed")
        return "failed"


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


def lesson_folder(graph: dict) -> str | None:
    """The folder a build of `graph` works in (what prepare() returns, else the pinned TUT_WORKDIR), found without creating
    or writing anything; None when S2 isn't available. Desktop test 10: the preflight card checks this folder's .venv,
    the one the setup card checks after Build."""
    from . import config

    if os.environ.get("TUT_WORKDIR"):
        return str(config.default_workdir())
    ws = _s2()
    if ws is None:
        return None
    try:
        if config.demo_mode():  # prepare()'s demo folder: the hero's, else <lessons root>/<folder name>
            hero = ws.hero_workdir(graph) if hasattr(ws, "hero_workdir") else None
            return str(hero if hero is not None else ws.lessons_root() / ws.folder_name(graph))
        fn = getattr(ws, "lesson_folder", None)
        return str(fn(graph)) if fn is not None else None
    except Exception:  # noqa: BLE001
        log.exception("workspace.lesson_folder failed")
        return None


def prepare(graph: dict, goal: str) -> str | None:
    """Create/fill the lesson's folder (S2; may call Claude for starter files, 2-25 s, never raises).
    None when TUT_WORKDIR pins the folder or S2 isn't available."""
    if os.environ.get("TUT_WORKDIR"):
        return None
    ws = _s2()
    if ws is None:
        return None
    from . import config

    if config.demo_mode():  # DEMO costs nothing: the folder, but no Claude-written starter files
        try:
            hero = ws.hero_workdir(graph) if hasattr(ws, "hero_workdir") else None
            if hero is not None:
                return str(hero)
            folder = ws.lessons_root() / ws.folder_name(graph)
            folder.mkdir(parents=True, exist_ok=True)
            return str(folder)
        except Exception:  # noqa: BLE001
            log.exception("demo folder failed")
            return None
    try:
        return str(ws.prepare(graph, goal))
    except Exception:  # noqa: BLE001
        log.exception("workspace.prepare failed")
        return None


def set_aside_previous(folder: str | None, graph: dict) -> str | None:
    """A fresh build in a reused lesson folder: the last run's learner files go to <folder>/.miyagi-previous/<time>/
    (S2's set_aside_previous) so no step passes on them. Only Miyagi's own folder for this lesson: never the hero
    folder, a TUT_WORKDIR one, or a folder of the learner's that the lesson was redirected to (adopt_folder). Blocking."""
    if not folder or os.environ.get("TUT_WORKDIR"):
        return None
    ws = _s2()
    fn = getattr(ws, "set_aside_previous", None) if ws is not None else None
    if fn is None:
        return None
    try:
        hero = ws.hero_workdir(graph) if hasattr(ws, "hero_workdir") else None
        own = (ws.lessons_root() / ws.folder_name(graph)).expanduser().resolve()
        if (hero is not None and Path(hero).resolve() == Path(folder).resolve()) or own != Path(folder).resolve():
            return None
        moved = fn(folder)
        return str(moved) if moved else None
    except Exception:  # noqa: BLE001 - the lesson still starts, with the files as they were
        log.exception("setting the last run's files aside failed")
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
    from . import config

    if config.demo_mode():
        return None  # DEMO costs nothing (S2's check asks Claude haiku)
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


def editor_opens(card: dict, items: list[dict]) -> dict:
    """t9 V8: VS Code opens on the lesson folder by itself, so the setup card never asks to open it (no Open button, no
    "Open the lesson folder in Visual Studio Code?" in its body). In place; returns the card."""
    card["actions"] = [a for a in card.get("actions") or [] if a != "open_editor"]
    ed = next((it for it in items if it.get("kind") == "editor"), None)
    if ed and isinstance(card.get("body"), str):
        card["body"] = card["body"].replace(f" Open the lesson folder in {ed.get('label')}?", "")
    return card


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


def refresh_python(folder: str) -> dict | None:
    """E20: after a pip install into <folder>/.venv, the lesson's VS Code window selects that .venv and restarts its
    Python language server (companion extension), so `import requests` loses Pylance's warning. Blocking (retries for
    up to ~20 s while the window starts): run it in a thread. Never raises; None when no window answered."""
    try:
        from server.workspace import vscode_ext

        return vscode_ext.refresh_python(folder)
    except Exception:  # noqa: BLE001 - a refinement: the lesson runs without it
        log.exception("refresh_python failed")
        return None


def goto_argv(path: str, line: int) -> list[str] | None:
    """S2: the jump command for the learner's editor (VS Code), so jumps never launch a
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


def reveal_line(path: str | Path, line: int) -> bool:
    """t8 (desktop test 8, 05:51:05 / 05:53:38): the step start's `code -r -g` activated VS Code, its Dock icon bounced
    and the CLI's own icon flashed by it. The companion extension reveals the line instead (POST /open: file + line,
    preserveFocus) in the window whose folders hold the file, never another window. Blocking (<= ~0.6 s).
    -> True when that window answered ok; False: no such window (the caller uses the CLI)."""
    try:
        from server.workspace import vscode_ext as vx
    except Exception:  # noqa: BLE001 - no companion module: the CLI
        return False
    p = Path(path).expanduser()
    wins = [w for w in vx.windows() if any(vx._inside(p, f) for f in w.get("folders") or [])]
    if not wins:
        return False
    res = vx.open_file(str(p), int(line), preserve_focus=True, port=int(wins[0]["port"]))
    ok = isinstance(res, dict) and bool(res.get("ok", True))
    if ok:
        log.info("revealed %s:%s through the companion (no code CLI)", p.name, line)
    return ok


def _editor_in_front() -> bool:
    """Is the learner's editor the active app (S2's editor.jump gate for an automatic jump)? Unknown: True."""
    ws = _s2()
    ed_mod = getattr(ws, "editor", None) if ws is not None else None
    if ed_mod is None or not hasattr(ed_mod, "editor_focused"):
        return True
    try:
        ed = ed_mod.preferred_editor()
        return ed is None or bool(ed_mod.editor_focused(ed))
    except Exception:  # noqa: BLE001
        return True


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
        # ORCH_OPEN_WORKSPACE=0 said out loud (QA, rehearsal and stage engines): nothing opens VS Code on its own, not even
        # "Just teach me". Only the learner pressing "Open VS Code" (explicit) still does. Unset keeps the default.
        self.blocked = enabled is None and os.environ.get("ORCH_OPEN_WORKSPACE", "").strip().lower() in {"0", "false", "no", "off"}
        self.run = runner or self._spawn  # injectable for tests
        self.opened: str | None = None
        self.lesson_key = ""  # the current lesson's id (session.load_graph): the editor opens once per lesson + folder
        self.reveal = None  # (path, line) -> revealed? t8: the companion's /open; None = reveal_line on real windows
        self.front = None  # () -> is the editor the active app? None = _editor_in_front (tests inject both)

    @staticmethod
    def _spawn(argv: list[str]) -> bool:
        try:
            subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True
        except OSError as e:
            log.warning("could not run %s: %s", argv[0], e)
            return False

    def _key(self) -> str:
        return f"{id(self)}:{self.lesson_key}"

    def _guarded(self, ws) -> bool:
        return hasattr(ws, "editor") and hasattr(ws.editor, "open_lesson_editor")

    def open(self, workdir: str, force: bool = False, full: bool = False, explicit: bool = False,
             file: str | None = None, busy=None, cancelled=None, miyagi_wait_s: float | None = None) -> None:
        """force: open even though auto-open (ORCH_OPEN_WORKSPACE) is off. full: "Just teach me" (the editor fills the
        screen). explicit: the learner pressed "Open VS Code" (may bring an already-open window forward).
        S2 opens the folder AT MOST ONCE per lesson + folder (`code <folder>`, never `-n`), arranges once, and an
        automatic open waits until the learner isn't in Miyagi's launcher/cards or typing.
        file (L2): the file to show, the step's own; None = S2's starter pick (open_file_for, e.g. README.md).
        busy / cancelled (L5, real windows only): what holds an automatic open and what drops it (a newer lesson).
        miyagi_wait_s: how long Miyagi in front holds an automatic open (then only busy() does); None = the default
        (LESSON_MIYAGI_WAIT_S when full, else until the learner leaves Miyagi)."""
        if not (self.enabled or force) or (self.blocked and not explicit) or not Path(workdir).is_dir():
            return
        if self.run == self._spawn:  # real windows only: tests inject a runner
            python_terminal_settings(workdir)
        ws = _s2()
        if ws is not None and self._guarded(ws):
            real = self.run == self._spawn  # tests inject a runner: never touch real windows or real focus
            wait = miyagi_wait_s if miyagi_wait_s is not None else (LESSON_MIYAGI_WAIT_S if full else None)
            holds = {"busy": busy, "cancelled": cancelled, "miyagi_wait_s": wait}
            ws.editor.open_lesson_editor(
                workdir, file or ws.open_file_for(Path(workdir)), lesson_id=self._key(), fullscreen=full and real,
                explicit=explicit, runner=None if (real and not full) else self.run, **(holds if real else {}),
                **({} if real else {"focus": lambda: None, "background": False, "arrange_windows": False,
                                     "trusted": lambda: False, "previous": None, "windows": lambda: []}))
            self.opened = workdir
            return
        if self.opened == workdir:  # older S2: at most once per folder
            return
        self.opened = workdir
        if ws is not None:
            runner = None if self.run == self._spawn else self.run
            ok = ws.open_editor(workdir, file or ws.open_file_for(Path(workdir)), runner=runner)
            log.info("opened workspace %s in VS Code: %s", workdir, ok)
            return
        ok = False
        if sys.platform == "darwin":
            ok = self.run(["open", "-a", VSCODE_APP, workdir])
        if not ok and (cli := code_cli()):
            ok = self.run([cli, workdir])
        log.info("opened workspace %s in VS Code: %s", workdir, ok)

    def goto(self, path: str, line: int, explicit: bool = False) -> None:
        """Jump to file:line. Automatic jumps (step start, spotlight retries) only run when VS Code is already the
        active app with its window up, so they never steal focus from Miyagi or spawn a window while VS Code is
        still starting. explicit=True: a learner action (Do it for me).
        t8: an automatic jump goes through the companion extension first (POST /open, preserveFocus, in a thread: no
        `code` CLI, so VS Code's Dock icon never bounces); the CLI only when no lesson window of it answers."""
        reveal = self.reveal if self.reveal is not None else (reveal_line if self.run == self._spawn else None)
        if not explicit and reveal is not None:
            front = self.front if self.front is not None else _editor_in_front

            def go() -> None:
                try:
                    if not front():  # as the CLI jump: only with VS Code in front (else reveal_step_line has its say)
                        return
                    if reveal(path, line):
                        return
                except Exception:  # noqa: BLE001 - the CLI jump below
                    log.exception("companion reveal of %s:%s failed", path, line)
                self._cli_goto(path, line, explicit)

            if self.reveal is not None:  # tests: in line, so they see what ran
                go()
            else:
                threading.Thread(target=go, daemon=True, name="miyagi-goto").start()
            return
        self._cli_goto(path, line, explicit)

    def _cli_goto(self, path: str, line: int, explicit: bool = False) -> None:
        ws = _s2()
        if ws is not None and hasattr(getattr(ws, "editor", None), "jump"):
            real = self.run == self._spawn
            mine = self._key()
            ws.editor.jump(path, line, explicit=explicit, runner=self.run,
                           **({} if real else {"focus": lambda: ("com.microsoft.VSCode", "Code"),
                                               "window_up": lambda ed: True,
                                               "opening": lambda: any(k[0] == mine and st["state"] != "open"
                                                                      for k, st in ws.editor._opened.items())}))
            return
        argv = goto_argv(path, line)
        if argv:
            self.run(argv)

    def goto_target(self, workdir: str, step: dict, explicit: bool = False, missing: str = "first") -> None:
        loc = target_location(workdir, step, missing=missing)
        if loc is None:
            return
        path, line = loc
        self.goto(str(path), line, explicit=explicit)
