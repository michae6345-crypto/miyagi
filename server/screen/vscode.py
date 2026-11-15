"""What the frontmost VS Code window is showing: folder, file, path, symbol, dirty. Pure Python.

    vscode_window(obs) -> VSCodeWindow | None

Sources, best first (each field independently):
- folder: the title bar's command center ("python-calculator-e430dc"), the window title
  ("● calculator.py — python-calculator-e430dc"), the Explorer's folder header, the breadcrumb root.
- file:   the window title (the active editor), else the breadcrumb's file segment.
- path:   the breadcrumb between the folder and the file ("src/calculator.py"), OCR dots repaired
          from the title ("calculatorpy" -> "calculator.py").
- dirty:  "●" in the window title (VS Code's default title has ${dirty}) or on the active tab; the
          AX snapshot's dirty flag when Accessibility is granted (reader adds it).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import match as M
from .lines import EDITOR_APPS
from .types import Block, ScreenObservation, Window

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


def _breadcrumb(obs: ScreenObservation, w: Window) -> Block | None:
    cands = [b for b in obs.blocks_in(None) if b.app == w.app and b.window == w.title and M.is_breadcrumb(b.text)
             and b.rect.y < w.rect.y + w.rect.h * 0.4]
    return min(cands, key=lambda b: b.rect.y) if cands else None


def vscode_window(obs: ScreenObservation, app: str | None = None) -> VSCodeWindow | None:
    """The frontmost VS Code (or Cursor) window in `obs`, or None if none is on screen."""
    w = _frontmost_editor(obs, app)
    if w is None:
        return None
    out = VSCodeWindow(app=w.app, title=w.title)
    t_file, t_folder, t_dirty = parse_title(w.title)
    if t_file:
        out.file, out.sources["file"] = t_file, "title"
    if t_folder:
        out.folder, out.sources["folder"] = t_folder, "title"
    if w.title:
        out.dirty, out.sources["dirty"] = t_dirty, "title"

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

    # breadcrumb: folder › dirs › file › symbol
    crumb = _breadcrumb(obs, w)
    if crumb is not None:
        segs = [s.strip() for s in _CRUMB_SPLIT.split(crumb.text) if s.strip()]
        # file names as the tabs spell them (OCR keeps the dot there more often than in the breadcrumb)
        tabs = {_alnum(b.text.strip().strip("".join(_DIRTY)).split()[0]): b.text.strip().split()[0]
                for b in obs.blocks_in(None) if b.app == w.app and b.window == w.title and b.text.strip()
                and crumb.rect.y - 45 <= b.rect.y < crumb.rect.y and _FILE.search(b.text.strip().split()[0])}
        fi = None
        for i, s in enumerate(segs):
            if (out.file and _alnum(s) == _alnum(out.file)) or _FILE.search(s) or _alnum(s) in tabs:
                fi = i
                break
        if fi is not None:
            name = out.file if out.file and _alnum(segs[fi]) == _alnum(out.file) else tabs.get(_alnum(segs[fi]),
                                                                                                    segs[fi])
            start = 1 if out.folder and segs and _alnum(segs[0]) == _alnum(out.folder) else 0
            if not out.folder and fi > 0:
                out.folder, out.sources["folder"] = segs[0], "breadcrumb"
                start = 1
            out.path = "/".join(segs[start:fi] + [name])
            out.sources["path"] = "breadcrumb"
            if not out.file:
                out.file, out.sources["file"] = name, "breadcrumb"
            if fi + 1 < len(segs):
                out.symbol = segs[-1]

    # Explorer folder header (upper-cased) as the last resort for the folder
    if not out.folder:
        heads = [b for b in obs.blocks_in(None) if b.app == w.app and b.window == w.title
                 and re.fullmatch(r"[A-Z0-9_.\-]{3,}", b.text.strip()) and b.text.strip() not in ("EXPLORER", "OUTLINE",
                                                                                                 "TIMELINE")]
        if heads:
            out.folder, out.sources["folder"] = min(heads, key=lambda b: b.rect.y).text.strip().lower(), "explorer"

    # a ● on the active tab (OCR rarely keeps it, but use it when it does)
    if not out.dirty and out.file:
        for b in obs.blocks_in(None):
            if b.app == w.app and b.window == w.title and _alnum(out.file) in _alnum(b.text) and \
                    any(d in b.text for d in _DIRTY) and b.rect.y < w.rect.y + 120:
                out.dirty, out.sources["dirty"] = True, "tab"
                break
    return out
