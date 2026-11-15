"""What the frontmost VS Code window is showing: folder, file, path, symbol, dirty. Pure Python.
This is the single source of truth for "which file is open": the reader attaches it to every
observation as `obs.editor`. Explorer rows NEVER decide the file (README.md listed in the Explorer
is not the open file).

    vscode_window(obs) -> VSCodeWindow | None

Sources, best first (each field independently):
- folder: the title bar's command center ("python-calculator-e430dc"), the window title
  ("● calculator.py — python-calculator-e430dc"), the Explorer's folder header, the breadcrumb root.
- file:   what the screen shows above the editor: the breadcrumb's file segment and the ACTIVE tab
          (the one with the close × or the dirty ●; the only tab when there is one); the window title
          only when neither is readable. A title that disagrees is kept in sources["title_file"].
- path:   the breadcrumb between the folder and the file ("src/calculator.py"), OCR dots repaired
          from the title ("calculatorpy" -> "calculator.py").
- dirty:  "●" in the window title (VS Code's default title has ${dirty}) or on the active tab; the
          AX snapshot's dirty flag when Accessibility is granted (reader adds it).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePath

from . import match as M
from .lines import EDITOR_APPS
from .types import Block, Rect, ScreenObservation, Window

_DIRTY = ("●", "•", "⚫")            # ● • ⚫ (OCR variants)
_TITLE_SEP = re.compile(r"\s+[—–-]\s+")   # " — " (VS Code on macOS), " – ", " - "
_CRUMB_SPLIT = re.compile(r"\s*[›>»]\s*")
_FILE = re.compile(r"\.[A-Za-z0-9]{1,6}$")


@dataclass
class VSCodeWindow:
    app: str
    title: str
    folder: str | None = None
    file: str | None = None           # active editor's file name
    path: str | None = None           # path inside the folder, from the breadcrumb ("src/calculator.py")
    symbol: str | None = None         # breadcrumb symbol after the file ("add")
    dirty: bool | None = None         # unsaved changes in the active editor (None: can't tell)
    sources: dict = field(default_factory=dict)   # field -> where it came from

    def to_dict(self) -> dict:
        return {"app": self.app, "title": self.title, "folder": self.folder, "file": self.file, "path": self.path,
                "symbol": self.symbol, "dirty": self.dirty, "sources": self.sources}


def _alnum(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", s.lower())


def _strip_dirty(s: str) -> tuple[str, bool]:
    t = s.strip()
    dirty = t.startswith(_DIRTY) or t.endswith(_DIRTY)
    return t.strip("".join(_DIRTY)).strip(), dirty


def parse_title(title: str) -> tuple[str | None, str | None, bool]:
    """"● calculator.py — python-calculator-e430dc" -> ("calculator.py", "python-calculator-e430dc", True).
    VS Code's default title is ${dirty}${activeEditorShort} — ${rootName} — ${profileName} — Visual Studio Code."""
    t, dirty = _strip_dirty(title or "")
    parts = [p.strip() for p in _TITLE_SEP.split(t) if p.strip()]
    parts = [p for p in parts if p not in ("Visual Studio Code", "Cursor", "Code", "VSCodium")]
    if not parts:
        return None, None, dirty
    if len(parts) == 1:   # no editor open: the title is just the folder (or the file, if it has an extension)
        return (parts[0], None, dirty) if _FILE.search(parts[0]) else (None, parts[0], dirty)
    first, second = parts[0], parts[1]
    if "[" in second:     # "folder [SSH: host]"
        second = second.split("[")[0].strip()
    return first, second, dirty


def _frontmost_editor(obs: ScreenObservation, app: str | None) -> Window | None:
    for w in obs.windows:
        if (app and M.app_matches(app, w.app, w.title)) or (not app and any(M.app_matches(e, w.app) for e in EDITOR_APPS)):
            return w
    return None


def _title_bar_blocks(obs: ScreenObservation, w: Window) -> list[Block]:
    return [b for b in obs.blocks_in(None) if b.app == w.app and b.window == w.title
            and w.rect.y - 2 <= b.rect.y and b.rect.y2 <= w.rect.y + 40]


_TAB_MARK = re.compile(r"\s*([×xX✕●•⚫])\s*$")


def _tab_name(text: str) -> str:
    """"notes.py ×" -> "notes.py"; "pinn_convection.py1 X" (problem count glued on) -> "pinn_convection.py"."""
    t = _TAB_MARK.sub("", text.strip()).strip()
    m = re.match(r"([\w.\-]+\.[A-Za-z]{1,6})", t)
    return m.group(1) if m else t.split()[0] if t else t


def _tab_mark(text: str) -> str | None:
    m = _TAB_MARK.search(text.strip())
    if not m:
        return None
    return "dirty" if m.group(1) in _DIRTY else "clean"


def _active_tab(tabs: list[Block]) -> Block | None:
    """VS Code shows the close × (or the dirty ●) only on the active tab (and a hovered one); with a
    single tab, that tab."""
    marked = [b for b in tabs if _TAB_MARK.search(b.text.strip())]
    if len(marked) == 1:
        return marked[0]
    if len(tabs) == 1:
        return tabs[0]
    return None


def _breadcrumb(obs: ScreenObservation, w: Window, tabs: list[Block] | None = None) -> Block | None:
    """The breadcrumb row: `a › b › file › sym`, or, for a file at the root, just the file name in the
    row right under the tab row (never an Explorer entry: it must start at the editor's left edge)."""
    blocks = [b for b in obs.blocks_in(None) if b.app == w.app and b.window == w.title
              and b.rect.y < w.rect.y + w.rect.h * 0.4]
    cands = [b for b in blocks if M.is_breadcrumb(b.text)]
    if tabs:
        left = min(b.rect.x for b in tabs)
        row_y2 = max(b.rect.y2 for b in tabs)
        th = max(b.rect.h for b in tabs)
        cands = [b for b in cands if b.rect.x >= left - 40] + [
            b for b in blocks if row_y2 - 2 <= b.rect.y <= row_y2 + 2.5 * th and left - 40 <= b.rect.x <= left + 90
            and _FILE.search(_tab_name(re.sub(r"^[^\w.]+", "", b.text)))]
    return min(cands, key=lambda b: b.rect.y) if cands else None


def vscode_window(obs: ScreenObservation, app: str | None = None) -> VSCodeWindow | None:
    """The frontmost VS Code (or Cursor) window in `obs`, or None if none is on screen."""
    w = _frontmost_editor(obs, app)
    if w is None:
        return None
    out = VSCodeWindow(app=w.app, title=w.title)
    t_file, t_folder, t_dirty = parse_title(w.title)
    if t_folder:
        out.folder, out.sources["folder"] = t_folder, "title"

    # command center: the centred text in the title bar (VS Code shows the folder there)
    bar = [b for b in _title_bar_blocks(obs, w) if abs(b.rect.cx - w.rect.cx) < 0.25 * w.rect.w]
    if bar:
        cc = max(bar, key=lambda b: b.rect.w).text.strip()
        cc = re.sub(r"^[^\w]+", "", cc).split("[")[0].strip()      # drop the search icon / "[SSH: ...]"
        if cc and not _FILE.search(cc):
            if not out.folder:
                out.folder, out.sources["folder"] = cc, "command_center"
            elif _alnum(cc) == _alnum(out.folder):
                out.sources["folder"] = "title+command_center"

    # the editor's tab row and its active tab (never the Explorer)
    from .regions import _tab_row
    win_blocks = [b for b in obs.blocks_in(None) if b.app == w.app and b.window == w.title]
    tabs, _row = _tab_row(w, win_blocks)
    active = _active_tab(tabs)
    tab_names = {_alnum(_tab_name(b.text)): _tab_name(b.text) for b in tabs}

    # breadcrumb: folder › dirs › file › symbol (or just "notes.py" for a file at the root)
    crumb = _breadcrumb(obs, w, tabs)
    crumb_file = None
    if crumb is not None:
        segs = [s.strip() for s in _CRUMB_SPLIT.split(crumb.text) if s.strip()]
        segs = [re.sub(r"^[^\w.]+", "", s) for s in segs]         # file-type icons read as "•", "@" ...
        fi = None
        for i, s in enumerate(segs):
            if _FILE.search(s) or _alnum(s) in tab_names or (active and _alnum(s) == _alnum(_tab_name(active.text))):
                fi = i
                break
        if fi is not None:
            crumb_file = tab_names.get(_alnum(segs[fi]), segs[fi])
            start = 1 if out.folder and segs and _alnum(segs[0]) == _alnum(out.folder) else 0
            if not out.folder and fi > 0:
                out.folder, out.sources["folder"] = segs[0], "breadcrumb"
                start = 1
            out.path = "/".join(segs[start:fi] + [crumb_file])
            out.sources["path"] = "breadcrumb"
            if fi + 1 < len(segs):
                out.symbol = segs[-1]

    # the file: breadcrumb + active tab (what's on screen), the title only as a fallback
    tab_file = _tab_name(active.text) if active is not None else None
    if crumb_file and tab_file and _alnum(crumb_file) == _alnum(tab_file):
        out.file, out.sources["file"] = tab_file, "tab+breadcrumb"
    elif crumb_file:
        out.file, out.sources["file"] = crumb_file, "breadcrumb"
    elif tab_file:
        out.file, out.sources["file"] = tab_file, "tab"
        out.path = out.path or tab_file
    elif t_file:
        out.file, out.sources["file"] = t_file, "title"
    if t_file and out.file and _alnum(t_file) != _alnum(out.file):
        out.sources["title_file"] = t_file      # stale / other window title: the screen wins

    # dirty: the active tab's ● / ×, else the title's ●
    mark = _tab_mark(active.text) if active is not None else None
    if mark is not None and out.file and _alnum(_tab_name(active.text)) == _alnum(out.file):
        out.dirty, out.sources["dirty"] = mark == "dirty", "tab"
    elif w.title:
        out.dirty, out.sources["dirty"] = t_dirty, "title"

    # Explorer folder header (upper-cased) as the last resort for the folder
    if not out.folder:
        heads = [b for b in obs.blocks_in(None) if b.app == w.app and b.window == w.title
                 and re.fullmatch(r"[A-Z0-9_.\-]{3,}", b.text.strip()) and b.text.strip() not in ("EXPLORER", "OUTLINE",
                                                                                                 "TIMELINE")]
        if heads:
            out.folder, out.sources["folder"] = min(heads, key=lambda b: b.rect.y).text.strip().lower(), "explorer"

    return out


# ---------------------------------------------------------------------- the lesson's own window

_EDITOR_NAMES = {M._norm_app(e) for e in EDITOR_APPS}


def _is_editor(app: str | None) -> bool:
    return M._norm_app(app) in _EDITOR_NAMES     # exact: "Xcode" is not "Code"


_NOT_FOLDERS = {"Welcome", "Get Started", "Settings", "Extensions", "Keyboard Shortcuts", "Release Notes"}
_SUBDIRS: dict[str, tuple[float, set[str]]] = {}


def _subfolders(folder: str) -> set[str]:
    """The (alnum) names of the folders up to 2 levels inside `folder`: create-react-app's demo-app/, the downloaded
    tutorial/. Cached 5 s (the reader asks every frame; a folder made mid-lesson still shows up)."""
    now = time.monotonic()
    hit = _SUBDIRS.get(folder)
    if hit is not None and now - hit[0] < 5.0:
        return hit[1]
    try:
        names = {_alnum(p.name) for pat in ("*", "*/*") for p in Path(folder).glob(pat) if p.is_dir()} \
            if Path(folder).is_absolute() else set()
    except OSError:
        names = set()
    _SUBDIRS.clear()   # one lesson at a time
    _SUBDIRS[folder] = (now, names)
    return names


def is_foreign(w: Window, folder: str | None) -> bool:
    """A VS Code/Cursor window on ANOTHER project than the lesson's (`folder`: its path, or a name): its title names a
    folder that is not the lesson folder, a folder above it or one up to 2 levels inside it ("requirements.txt —
    fine-tune-llm-…" while the lesson is python-calculator-e430dc). The same rule as server.coach.screen.other_project.
    A title that names no folder (custom window.title, a lone file, Untitled-1, Welcome) is never foreign: when in
    doubt the window counts."""
    name = parse_title(w.title or "")[1] if folder and _is_editor(w.app) else None
    if not name or name.startswith("Untitled") or name in _NOT_FOLDERS:
        return False
    want = _alnum(str(folder).rstrip("/").split("/")[-1])
    parts = [_alnum(p.split("[")[0]) for p in _TITLE_SEP.split(_strip_dirty(w.title or "")[0])]
    if not want or any(want in p for p in parts):   # "in": a custom title may show the folder's path
        return False
    got = _alnum(name)
    return bool(got) and got not in {_alnum(p) for p in PurePath(str(folder)).parts} \
        and got not in _subfolders(str(folder))


def window_shown(app: str | None, title: str | None, windows: list[Window]) -> bool:
    """For an editor app: is the window titled `title` (AX's focused window) one of `windows` (a frame's on-screen,
    lesson-scoped windows), by folder? VS Code's focused window can sit on another Space (full screen) or show another
    folder; its AX text and caret rect must not count then. Other apps / a title with no folder: True (can't tell)."""
    folder = parse_title(title or "")[1] if _is_editor(app) else None
    if not folder:
        return True
    return any(_is_editor(w.app) and _alnum(parse_title(w.title)[1] or "") == _alnum(folder) for w in windows)


def _visible_parts(r: Rect, front: list[Rect]) -> list[Rect]:
    """`r` minus every rect in `front` (the windows in front of it), as up to a few rects."""
    parts = [r]
    for o in front:
        out = []
        for p in parts:
            ix1, iy1, ix2, iy2 = max(p.x, o.x), max(p.y, o.y), min(p.x2, o.x2), min(p.y2, o.y2)
            if ix1 >= ix2 or iy1 >= iy2:
                out.append(p)
                continue
            if p.y < iy1:
                out.append(Rect(p.x, p.y, p.w, iy1 - p.y))
            if iy2 < p.y2:
                out.append(Rect(p.x, iy2, p.w, p.y2 - iy2))
            if p.x < ix1:
                out.append(Rect(p.x, iy1, ix1 - p.x, iy2 - iy1))
            if ix2 < p.x2:
                out.append(Rect(ix2, iy1, p.x2 - ix2, iy2 - iy1))
        parts = out
    return [p for p in parts if p.w > 1 and p.h > 1]


def scope_to_folder(blocks: list[Block], windows: list[Window], folder: str | None
                    ) -> tuple[list[Block], list[Window], list[Window], list[Rect]]:
    """Bind a frame to the lesson's own editor window: drop the VS Code windows of OTHER folders (and their OCR text)
    so checks, the coach and spotlights never read or box another project.
    -> (blocks, windows, foreign windows (front to back), the screen areas those foreign windows show)."""
    foreign = [w for w in windows if is_foreign(w, folder)]
    if not foreign:
        return blocks, windows, [], []
    keys = {(w.app, w.title) for w in foreign}
    hidden: list[Rect] = []
    for i, w in enumerate(windows):
        if (w.app, w.title) in keys:
            hidden += _visible_parts(w.rect, [o.rect for o in windows[:i]])
    return ([b for b in blocks if (b.app, b.window) not in keys], [w for w in windows if (w.app, w.title) not in keys],
            foreign, hidden)


# ---------------------------------------------------------------------- the active file, from every source

def _name(p: str | None) -> str | None:
    if not p:
        return None
    return p.replace("\\", "/").rstrip("/").split("/")[-1] or None


def resolve_active(extension: dict | None = None, ax: dict | None = None, title: dict | None = None,
                   ocr: dict | None = None) -> dict:
    """Combine the active-file reads, freshest and most exact first:

    1. extension: the companion extension's active editor ({file, path, folder, dirty}) -> trusted alone
    2. ax:        AXDocument of the focused VS Code window ({path, dirty})            -> trusted alone
    3. title:     the live window title "● file — folder" ({file, folder, dirty})
    4. ocr:       the active tab + breadcrumb of a fresh frame ({file, path, folder, dirty})
    Title and OCR are reported only when they agree (by file name). Otherwise `file` is None and
    `confidence` is "unsure"; never a guess. Explorer rows are never a source.
    -> {file, path, folder, dirty, source, confidence: exact | agreed | unsure | none, candidates}"""
    cands = {k: v for k, v in (("extension", extension), ("ax", ax), ("title", title), ("ocr", ocr)) if v}
    out = {"file": None, "path": None, "folder": None, "dirty": None, "source": None, "confidence": "none",
           "candidates": {k: {"file": v.get("file") or _name(v.get("path")), "dirty": v.get("dirty")}
                          for k, v in cands.items()}}
    for src in ("extension", "ax"):
        v = cands.get(src)
        name = (v or {}).get("file") or _name((v or {}).get("path"))
        if name:
            out.update(file=name, path=v.get("path"), folder=v.get("folder"), dirty=v.get("dirty"), source=src,
                       confidence="exact")
            return out
    t, o = cands.get("title"), cands.get("ocr")
    tn, on = (t or {}).get("file"), (o or {}).get("file")
    if tn and on and _alnum(tn) == _alnum(on):
        out.update(file=tn, path=(o or {}).get("path"), folder=(t or {}).get("folder") or (o or {}).get("folder"),
                   dirty=(t or {}).get("dirty") if (t or {}).get("dirty") is not None else (o or {}).get("dirty"),
                   source="title+ocr", confidence="agreed")
    elif tn or on:
        out["confidence"] = "unsure"
        out["folder"] = (t or {}).get("folder") or (o or {}).get("folder")
    return out


def ocr_only(win: VSCodeWindow | None) -> dict | None:
    """The OCR part of a vscode_window() read (tab / breadcrumb), without its title fallback."""
    if win is None or win.sources.get("file") not in ("tab", "breadcrumb", "tab+breadcrumb"):
        return None
    dirty = win.dirty if win.sources.get("dirty") == "tab" else None
    return {"file": win.file, "path": win.path, "folder": win.folder, "dirty": dirty}
