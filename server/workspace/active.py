"""Which VS Code window/file the learner is really in, and what to do when it's the wrong lesson folder.

    active_editor()                       -> {folder, folder_name, file, path, dirty, title, miyagi_lesson, source} | None
    wrong_folder(lesson_folder, files)    -> {learner_folder, lesson_folder, file, dirty, can_adopt, ...} | None
    adopt_folder(lesson_folder, learner)  -> {workdir, copied, skipped}   ("use this folder": copy missing files, never delete)

Sources, best first: Accessibility (the focused window's AXDocument = the exact file path), then VS Code's window
titles ("● calculator.py — python-calculator-e430dc": file — folder; from E6's window list when the caller passes
`titles`, else CGWindowList, which needs only the Screen Recording permission the engine already has). A folder
name from a title resolves to a path only under ~/miyagi/lessons (MIYAGI_LESSONS_DIR).
"""

from __future__ import annotations

import logging
import re
import shutil
from collections.abc import Callable, Iterable
from pathlib import Path

from . import paths

log = logging.getLogger("server.workspace")

VSCODE_BUNDLE = "com.microsoft.VSCode"
SEP = " — "  # VS Code's window.title separator
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".ipynb_checkpoints", "tutorial", ".mypy_cache", ".pytest_cache"}
MAX_COPY_BYTES = 5 * 1024 * 1024


def parse_title(title: str) -> dict | None:
    """"● calculator.py — python-calculator-e430dc" -> {file, folder_name, dirty}. None for an empty title."""
    t = (title or "").strip()
    if not t:
        return None
    dirty = t.startswith("●")
    t = t.lstrip("● ").strip()
    parts = [p.strip() for p in t.split(SEP) if p.strip()]
    parts = [p for p in parts if p not in ("Visual Studio Code", "Code")]
    if not parts:
        return None
    if len(parts) == 1:  # just the folder (no editor open) or just a file
        return {"file": None, "folder_name": parts[0], "dirty": dirty}
    file = parts[0] if parts[0] not in ("Welcome", "Settings", "Extensions") else None
    return {"file": file, "folder_name": parts[1], "dirty": dirty}


def lesson_folder_named(name: str | None) -> Path | None:
    """~/miyagi/lessons/<name> if it exists (title folder names only resolve there)."""
    if not name or "/" in name or name.startswith("."):
        return None
    p = paths.lessons_root() / name
    return p.resolve() if p.is_dir() else None


def is_lesson_folder(folder: str | Path | None) -> bool:
    if not folder:
        return False
    root = paths.lessons_root().resolve()
    f = Path(folder).expanduser().resolve()
    return f.parent == root and not f.name.startswith(".")


def _cg_vscode_titles(onscreen_only: bool = False) -> list[str]:
    """Titles of VS Code's normal windows, front to back (on-screen first; onscreen_only: only the windows the
    current Space shows, never a full-screen window on another Space)."""
    try:
        import AppKit
        import Quartz
    except ImportError:
        return []
    apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(VSCODE_BUNDLE) or []
    if not len(apps):
        return []
    pid = int(apps[0].processIdentifier())
    out: list[tuple[int, str]] = []
    for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID) or []:
        if int(w.get("kCGWindowOwnerPID", -1)) != pid or w.get("kCGWindowLayer", 1) != 0:
            continue
        name = str(w.get("kCGWindowName") or "")
        if name and (w.get("kCGWindowIsOnscreen") or not onscreen_only):
            out.append((0 if w.get("kCGWindowIsOnscreen") else 1, name))
    return [n for _, n in sorted(out, key=lambda x: x[0])]  # stable: z-order kept within each group


def vscode_windows(titles: Iterable[str] | None = None) -> list[dict]:
    """VS Code windows front to back: [{title, file, folder_name, folder (path or None), dirty, miyagi_lesson}]."""
    out = []
    for t in (list(titles) if titles is not None else _cg_vscode_titles()):
        p = parse_title(t)
        if p is None:
            continue
        folder = lesson_folder_named(p["folder_name"])
        out.append({**p, "title": t, "folder": str(folder) if folder else None, "miyagi_lesson": folder is not None})
    return out


def _find_in(folder: Path, name: str) -> Path | None:
    direct = folder / name
    if direct.is_file():
        return direct
    for p in sorted(folder.rglob(name)):
        rel = p.relative_to(folder)
        if p.is_file() and len(rel.parts) <= 4 and not (set(rel.parts) & SKIP_DIRS):
            return p
    return None


def _ax_front_document() -> dict | None:
    """With Accessibility: the frontmost VS Code window's title and file (AXDocument). Best effort: None on any error."""
    try:
        return _ax_front_document_unsafe()
    except Exception as e:  # noqa: BLE001
        log.debug("AX front document failed: %r", e)
        return None


def _ax_front_document_unsafe() -> dict | None:
    from . import editor as ed

    if not ed.ax_trusted():
        return None
    pid = ed.find_pid("Visual Studio Code", VSCODE_BUNDLE)
    if pid is None:
        return None
    try:
        import ApplicationServices as A
    except ImportError:
        return None
    app = A.AXUIElementCreateApplication(pid)
    A.AXUIElementSetMessagingTimeout(app, 0.3)
    err, win = A.AXUIElementCopyAttributeValue(app, "AXFocusedWindow", None)
    if err != 0 or win is None:
        return None
    _, title = A.AXUIElementCopyAttributeValue(win, "AXTitle", None)
    _, doc = A.AXUIElementCopyAttributeValue(win, "AXDocument", None)
    return {"title": str(title or ""), "document": ed._doc_path(doc)}


def active_editor(*, titles: Iterable[str] | None = None, ax: Callable[[], dict | None] | None = None) -> dict | None:
    """The frontmost VS Code window: {folder, folder_name, file, path, dirty, title, miyagi_lesson, source}.

    folder/path are absolute when known: from AXDocument (any folder), else from the title for folders under
    ~/miyagi/lessons; None otherwise (the folder name is still there). None when VS Code has no window.
    With `titles` (the windows on screen, front to back), AX counts only when its focused window is the front one
    of those: VS Code's focused window can be a full-screen window on another Space while the screen shows another."""
    a = (ax or _ax_front_document)()
    if a and a.get("document") and titles is not None:
        titles = list(titles)
        ax_folder = (parse_title(a.get("title", "")) or {}).get("folder_name")
        front = parse_title(titles[0]) if titles else None
        if ax_folder and (front is None or front.get("folder_name") != ax_folder):
            a = None
    if a and a.get("document"):
        doc = Path(a["document"])
        p = parse_title(a.get("title", "")) or {"file": doc.name, "folder_name": None, "dirty": False}
        folder = None
        root = paths.lessons_root().resolve()
        if root in doc.parents:  # the lesson folder is the child of ~/miyagi/lessons the file is in
            folder = root / doc.relative_to(root).parts[0]
        elif p.get("folder_name"):
            folder = next((par for par in doc.parents if par.name == p["folder_name"]), None)
        folder = folder or doc.parent
        return {"folder": str(folder), "folder_name": folder.name, "file": doc.name, "path": str(doc),
                "dirty": bool(p.get("dirty")), "title": a.get("title", ""), "miyagi_lesson": is_lesson_folder(folder),
                "source": "ax"}
    wins = vscode_windows(titles)
    if not wins:
        return None
    w = wins[0]
    path = None
    if w["folder"] and w["file"]:
        hit = _find_in(Path(w["folder"]), w["file"])
        path = str(hit) if hit else None
    return {"folder": w["folder"], "folder_name": w["folder_name"], "file": w["file"], "path": path, "dirty": w["dirty"],
            "title": w["title"], "miyagi_lesson": w["miyagi_lesson"], "source": "title"}


_NOT_FOLDERS = {"Welcome", "Get Started", "Settings", "Extensions", "Keyboard Shortcuts", "Release Notes"}


def _names_folder(name: str | None) -> bool:
    """A title part that really is a folder (not VS Code's Welcome tab, an Untitled editor or a lone file)."""
    n = (name or "").strip()
    return bool(n) and n not in _NOT_FOLDERS and not n.startswith("Untitled") and not re.search(r"\.[A-Za-z0-9]{1,6}$", n)


def _in_project(name: str, lesson: Path) -> bool:
    """A window title's folder `name` is the lesson's project: the lesson folder ("in": a custom window.title may show
    its path), a folder above it, or one up to 2 levels inside it (create-react-app's demo-app/). The same rule as
    E6's server.screen.vscode.is_foreign and the coach's other_project."""
    n = name.split("[")[0].strip()   # "folder [SSH: host]"
    if lesson.name in n or n in lesson.parts:
        return True
    try:
        return any(p.name == n for pat in ("*", "*/*") for p in lesson.glob(pat) if p.is_dir())
    except OSError:
        return False


def wrong_folder(lesson_folder: str | Path, lesson_files: Iterable[str] | None = None, *,
                 active: dict | None = None, titles: Iterable[str] | None = None,
                 window_check: bool = False) -> dict | None:
    """The learner edits a lesson file (same name) in ANOTHER folder than the one the lesson watches
    (reason "same_file"); with window_check=True (the lesson is bound to its own VS Code window: Miyagi opened it),
    ALSO when the VS Code window on screen shows another folder, whatever file it has open (reason "other_window").
    window_check reads only the windows the current Space shows (not a full-screen window on another Space).

    -> {learner_folder (path or None), learner_folder_name, lesson_folder, file, dirty, can_adopt, reason} | None.
    lesson_files: the lesson's file names/paths (targets, check files); default: the files in lesson_folder.
    can_adopt: "use this folder" is possible (the learner's folder path is known and is a real folder; never
    another Miyagi lesson's folder for "other_window")."""
    if window_check and active is None and titles is None:
        titles = _cg_vscode_titles(onscreen_only=True)
    act = active if active is not None else active_editor(titles=titles)
    if not act:
        return None
    lesson = Path(lesson_folder).expanduser().resolve()
    folder = Path(act["folder"]).resolve() if act.get("folder") else None
    if folder and (folder == lesson or lesson in folder.parents):
        return None
    if act.get("path") and lesson in Path(act["path"]).resolve().parents:
        return None  # a file of the lesson's own folder (AX / the extension: in a window on a folder above it)
    if not folder and act.get("folder_name") and _in_project(act["folder_name"], lesson):
        return None
    if lesson_files is None:
        names = {p.name for p in lesson.rglob("*") if p.is_file() and not (set(p.relative_to(lesson).parts) & SKIP_DIRS)} \
            if lesson.is_dir() else set()
    else:
        names = {Path(f).name for f in lesson_files if f}
    same_file = bool(act.get("file")) and act["file"] in names
    if not same_file and not (window_check and _names_folder(act.get("folder_name"))
                              and not (folder and folder in lesson.parents)):   # a window on a folder above the lesson
        return None
    learner = act.get("folder")
    return {"learner_folder": learner, "learner_folder_name": act.get("folder_name"), "lesson_folder": str(lesson),
            "file": act.get("file"), "path": act.get("path"), "dirty": bool(act.get("dirty")),
            "learner_is_miyagi_lesson": bool(act.get("miyagi_lesson")),
            "reason": "same_file" if same_file else "other_window",
            "can_adopt": bool(learner) and Path(learner).is_dir() and _safe_target(Path(learner), lesson)
            and (same_file or not act.get("miyagi_lesson"))}


def folder_on_screen(folder: str | Path) -> bool:
    """Is a VS Code window showing `folder` on screen now (the current Space)? (after Open: did it come forward?)"""
    name = Path(folder).expanduser().name
    return any(w.get("folder_name") == name for w in vscode_windows(_cg_vscode_titles(onscreen_only=True)))


def _safe_target(target: Path, lesson: Path) -> bool:
    t = target.expanduser().resolve()
    home = Path.home().resolve()
    if t in (Path("/"), home, paths.lessons_root().resolve()) or t in home.parents:
        return False
    return not (t in lesson.parents or lesson in t.parents)


def adopt_folder(lesson_folder: str | Path, learner_folder: str | Path) -> dict:
    """"Use this folder": the lesson continues in the folder the learner is in.

    Copies every file the lesson folder has that the learner's folder lacks (starter files, README, data;
    not .git/.venv/node_modules/tutorial downloads; ≤ 5 MB each). Never overwrites, never deletes. Records the
    redirect so prepare() returns the learner's folder for this lesson from now on.
    -> {workdir, copied: [rel], skipped: [rel: reason]}. Raises ValueError for an unsafe target."""
    src = Path(lesson_folder).expanduser().resolve()
    dst = Path(learner_folder).expanduser().resolve()
    if not dst.is_dir():
        raise ValueError(f"{dst} is not a folder")
    if not _safe_target(dst, src):
        raise ValueError(f"won't use {dst} as a lesson folder")
    copied, skipped = [], []
    if src.is_dir():
        for p in sorted(src.rglob("*")):
            rel = p.relative_to(src)
            if not p.is_file() or set(rel.parts) & SKIP_DIRS:
                continue
            target = dst / rel
            if target.exists():
                skipped.append(f"{rel}: already there")
                continue
            if p.stat().st_size > MAX_COPY_BYTES:
                skipped.append(f"{rel}: larger than 5 MB")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            copied.append(str(rel))
    from .core import set_redirect

    set_redirect(src, dst)
    log.info("lesson %s now uses %s (copied %d file(s))", src.name, dst, len(copied))
    return {"workdir": str(dst), "copied": copied, "skipped": skipped}
