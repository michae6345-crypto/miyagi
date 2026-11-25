"""The labels of an app's controls, from its accessibility tree (how-do-I, AMBIENT-HELP.md section 3). Local only.

    snap = read(app_name)    # Controls(app, window, items=[Control(label, role, path, rect)]) | None

Menu bar items always (a closed menu's items are listed with their path, "File > Export", and no rect: the help step
can name them, bon can point once the menu is open), the focused window's buttons, fields, tabs, checkboxes, popups
and links with their rects (screen points, top-left: the AmbientTarget space), and an open sheet / dialog's controls.
A bounded walk (node budget, short messaging timeout). Never a screenshot. None without the Accessibility grant or
when the app isn't running.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger("server.ambient")

MAX_NODES = 1800
MAX_CONTROLS = 250
MAX_MENU_ITEMS = 40  # per menu
LABEL_MAX = 60
ROLES = {"AXButton", "AXMenuButton", "AXPopUpButton", "AXCheckBox", "AXRadioButton", "AXTab", "AXTextField",
         "AXSearchField", "AXComboBox", "AXLink", "AXSlider", "AXDisclosureTriangle", "AXMenuItem", "AXMenuBarItem",
         "AXTabButton", "AXCell"}
SKIP_ROLES = {"AXTextArea", "AXStaticText", "AXImage", "AXScrollBar", "AXTable", "AXOutline", "AXWebArea"}
MIYAGI_NAMES = {"miyagi", "Miyagi", "Electron"}  # our own windows are never "the app"


@dataclass
class Control:
    label: str
    role: str
    path: str = ""                       # "File > Export" for a menu item
    rect: tuple[float, float, float, float] | None = None  # x, y, w, h (screen points, top-left)

    def to_dict(self) -> dict:
        return {"label": self.label, "role": self.role, "path": self.path,
                "rect": list(self.rect) if self.rect else None}


@dataclass
class Controls:
    app: str
    window: str = ""
    items: list[Control] = field(default_factory=list)

    def signature(self) -> tuple:
        """What changes when the screen changes as a step says: the window, the open menus, the visible controls."""
        return (self.window, tuple(sorted((c.path or c.label, c.role) for c in self.items if c.rect)))


def clean_label(s: object) -> str:
    t = re.sub(r"\s+", " ", str(s or "")).strip()
    return t[:LABEL_MAX]


def _rect_ok(r) -> bool:
    return r is not None and r.w > 2 and r.h > 2 and r.x > -20000 and r.y > -20000


def _find_app(name: str):
    """NSRunningApplication for `name` (localized name, case-insensitive; or a bundle id). None when not running."""
    from AppKit import NSWorkspace

    want = (name or "").strip().lower()
    if not want:
        return None
    for a in NSWorkspace.sharedWorkspace().runningApplications():
        if str(a.localizedName() or "").lower() == want or str(a.bundleIdentifier() or "").lower() == want:
            return a
    for a in NSWorkspace.sharedWorkspace().runningApplications():  # "Code" for "Visual Studio Code" and the like
        nm = str(a.localizedName() or "").lower()
        if nm and int(a.activationPolicy()) == 0 and (want in nm or nm in want):
            return a
    return None


def frontmost_app() -> str | None:
    """The frontmost app's name, never Miyagi's own window."""
    try:
        from AppKit import NSWorkspace
    except ImportError:
        return None
    a = NSWorkspace.sharedWorkspace().frontmostApplication()
    name = str(a.localizedName() or "") if a is not None else ""
    return name if name and name not in MIYAGI_NAMES else None


def read(app_name: str, *, max_nodes: int = MAX_NODES) -> Controls | None:
    """The app's controls (see module doc). None: no grant, no AX binding, or the app isn't running."""
    try:
        return _read(app_name, max_nodes)
    except Exception as e:  # noqa: BLE001 - help works without targets
        log.info("controls of %s unavailable (%s)", app_name, type(e).__name__)
        return None


def _read(app_name: str, max_nodes: int) -> Controls | None:
    from server.screen import ax

    if ax.AX is None or not ax.trusted():
        return None
    running = _find_app(app_name)
    if running is None:
        return None
    pid = int(running.processIdentifier())
    app_el = ax.AX.AXUIElementCreateApplication(pid)
    ax.AX.AXUIElementSetMessagingTimeout(app_el, ax.MESSAGING_TIMEOUT)
    if str(running.bundleIdentifier() or "") in ax.ELECTRON_EDITORS:
        ax.enable_electron_ax(app_el, pid)
    out = Controls(app=str(running.localizedName() or app_name))
    budget = [max_nodes]

    def add(label: str, role: str, path: str, el) -> None:
        if len(out.items) >= MAX_CONTROLS or not label:
            return
        r = ax.rect_of(el)
        out.items.append(Control(label, role, path, (r.x, r.y, r.w, r.h) if _rect_ok(r) else None))

    def menu(el, prefix: str, depth: int, opened: bool) -> None:
        for m in ax.attr(el, "AXChildren") or []:  # AXMenu
            for n, item in enumerate(ax.attr(m, "AXChildren") or []):
                budget[0] -= 1
                if budget[0] <= 0 or n >= MAX_MENU_ITEMS:
                    return
                title = clean_label(ax.attr(item, "AXTitle"))
                if not title:
                    continue
                path = f"{prefix} > {title}"
                if opened:
                    add(title, "AXMenuItem", path, item)
                else:
                    out.items.append(Control(title, "AXMenuItem", path, None))
                if depth < 2 and ax.attr(item, "AXChildren"):
                    menu(item, path, depth + 1, opened and bool(ax.attr(item, "AXSelected")))

    for top in ax.attr(ax.attr(app_el, "AXMenuBar"), "AXChildren") or []:
        title = clean_label(ax.attr(top, "AXTitle"))
        if not title or title == "Apple":
            continue
        add(title, "AXMenuBarItem", title, top)
        menu(top, title, 1, bool(ax.attr(top, "AXSelected")))

    win = ax.attr(app_el, "AXFocusedWindow") or ax.attr(app_el, "AXMainWindow")
    out.window = clean_label(ax.attr(win, "AXTitle"))
    queue = [win] if win is not None else []
    while queue and budget[0] > 0 and len(out.items) < MAX_CONTROLS:
        el = queue.pop(0)
        budget[0] -= 1
        role = str(ax.attr(el, "AXRole") or "")
        if role in ROLES:
            label = ""
            for a in ("AXTitle", "AXDescription", "AXHelp", "AXPlaceholderValue"):
                label = clean_label(ax.attr(el, a))
                if label:
                    break
            if label:
                add(label, role, "", el)
        if role in SKIP_ROLES:
            continue
        queue.extend(ax.attr(el, "AXChildren") or [])
    return out
