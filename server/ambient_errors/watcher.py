"""From screen frames to error.seen events (AMBIENT-HELP.md section 1). Local only: no model, no network, no disk.

  scan(obs, muted)          every error one frame shows -> [Spotted]. Which rows are read:
                              a terminal app (Terminal, iTerm2, Warp, Ghostty...)   all of its rows
                              VS Code with a notebook (.ipynb) in front               all rows, as notebook cells
                              VS Code otherwise                                       its terminal panel only
                              a browser on Jupyter / Colab / an .ipynb                notebook tracebacks
                              a browser otherwise                                     console "Uncaught ..." only
                              any other app, a muted app, a private app, Miyagi       nothing
                            The Accessibility tree's terminal rows (obs.ax terminal_tail: exact text) beat OCR for the
                            same app and kind; the OCR rows still give the rect.
  ErrorWatcher              debounce, dedupe and pace:
                              - an error becomes error.seen only once it has been on screen VISIBLE_S (1 s): seen in
                                a frame, and no later frame without it (frames come only when the screen changes)
                              - one id per app + kind + title + file:line; printed again (more copies on screen, or
                                back after it went) -> the same id, `again` + 1, never a second peek
                              - at most one error.seen every GAP_S (5 s)
                              - gone (its app on screen, the error not, for CLEAR_S) -> {id, clear: true}, forgotten
                              - held at most TTL_S (10 min); dismissed ids stay quiet until they go and come back
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .detect import Found, Row, find_errors, _norm
from .text import for_app

VISIBLE_S = 1.0
GAP_S = 5.0
CLEAR_S = 3.0
TTL_S = 600.0

BROWSERS = ("google chrome", "chrome", "safari", "arc", "firefox", "microsoft edge", "brave browser", "chromium",
            "orion", "zen")
NOTEBOOK_HINTS = (".ipynb", "jupyter", "colab")
OWN_APPS = ("miyagi", "electron", "miyagi-overlay")
PANEL_TABS = ("PROBLEMS", "OUTPUT", "DEBUG CONSOLE", "TERMINAL", "PORTS")


@dataclass
class Spotted:
    """One error in one frame: `found` and where (`rect` a screen Rect or None, `via` "ax" / "ocr")."""

    app: str
    found: Found
    rect: Any = None
    via: str = "ocr"
    doc: str | None = None  # the focused editor's file path (Accessibility), to resolve a relative file:line

    @property
    def id(self) -> str:
        return self.found.key(self.app)


def _m():
    from server.screen import match as M  # lazy: the screen package is optional for the pure parts

    return M


def _is_browser(app: str) -> bool:
    a = (app or "").lower()
    return any(a == b or a.startswith(b) for b in BROWSERS)


def _is_code(app: str) -> bool:
    return _m().app_matches("Code", app) and not _m().is_terminal_app(app)


def _muted(app: str, muted: list[str] | tuple[str, ...]) -> bool:
    M = _m()
    if any(M.app_matches(x, app) for x in muted or () if x):
        return True
    a = (app or "").lower()
    if any(o in a for o in OWN_APPS):
        return True
    try:
        from server.screen.privacy import is_private_app

        return is_private_app(app)
    except Exception:  # noqa: BLE001
        return False


def _panel_rows(obs: Any, rows: list[Any], app: str) -> list[Any]:
    """VS Code's terminal panel rows: inside server.screen's terminal region, else below the panel's tab row."""
    try:
        from server.screen.regions import find_region

        reg = find_region(obs, "terminal")
    except Exception:  # noqa: BLE001 - a layout the region finder can't read
        reg = None
    if reg is not None and getattr(reg, "rect", None) is not None and _m().app_matches(app, getattr(reg, "app", app)):
        return [r for r in rows if reg.rect.contains(r.rect)]
    for k, r in enumerate(rows):
        up = r.text.upper()
        if sum(t in up for t in PANEL_TABS) >= 2:
            return [x for x in rows[k + 1:] if x.rect.y > r.rect.y]
    return []


def scan(obs: Any, muted: list[str] | tuple[str, ...] = ()) -> list[Spotted]:
    """Every error one frame shows, front window first."""
    M = _m()
    lines = M.group_lines(list(getattr(obs, "blocks", None) or []))
    by_win: dict[tuple[str, str], list[Any]] = {}
    for ln in lines:
        by_win.setdefault((ln.app or "", ln.window or ""), []).append(ln)
    out: list[Spotted] = []
    seen_ids: set[str] = set()
    for (app, title), rows in by_win.items():
        if not app or _muted(app, muted):
            continue
        t = (title or "").lower()
        notebook = any(h in t for h in NOTEBOOK_HINTS)
        if M.is_terminal_app(app):
            pick, browser = rows, False
        elif _is_code(app):
            pick, browser = (rows if notebook else _panel_rows(obs, rows, app)), False
        elif _is_browser(app):
            pick, browser = rows, True
        else:
            continue
        for f in find_errors([Row(r.text, r.rect) for r in pick], notebook=notebook, browser=browser):
            out.append(Spotted(app=app, found=f, rect=f.rect(), via="ocr"))
    ax = getattr(obs, "ax", None) or {}
    tail = ax.get("terminal_tail") if isinstance(ax, dict) else None
    ax_app = str(ax.get("app") or "") if isinstance(ax, dict) else ""
    doc = ax.get("document") if isinstance(ax, dict) else None
    if tail and ax_app and not _muted(ax_app, muted) and (M.is_terminal_app(ax_app) or _is_code(ax_app)):
        exact = find_errors([Row(str(x)) for x in tail])
        for f in exact:
            twin = next((s for s in out if M.app_matches(ax_app, s.app) and s.found.kind == f.kind
                         and s.via == "ocr"), None)
            if twin is not None:  # the same error read twice: AX's exact text, OCR's place on screen
                out.remove(twin)
            out.append(Spotted(app=twin.app if twin else ax_app, found=f, rect=twin.rect if twin else None,
                               via="ax"))
    for s in out:
        if isinstance(doc, str) and doc:
            s.doc = doc
    # one Spotted per id and frame, with how many copies the frame shows (count)
    uniq: list[Spotted] = []
    for s in out:
        if s.id in seen_ids:
            continue
        seen_ids.add(s.id)
        uniq.append(s)
    for s in uniq:
        s.found.copies = sum(1 for x in out if x.id == s.id)
    return uniq


def apps_on_screen(obs: Any) -> set[str]:
    """The normalised names of the apps whose text this frame shows (an error can only be 'gone' from one of them)."""
    names = {_norm(b.app or "") for b in getattr(obs, "blocks", None) or [] if getattr(b, "app", None)}
    ax = getattr(obs, "ax", None) or {}
    if isinstance(ax, dict) and ax.get("app") and ax.get("terminal_tail"):
        names.add(_norm(str(ax["app"])))
    return names


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Held:
    id: str
    spotted: Spotted
    first_t: float
    last_t: float
    at: str
    copies: int = 1
    shown: bool = False
    again: int = 0
    absent_since: float | None = None
    explanation: dict | None = None
    dirty: bool = False  # shown, and printed again since: send error.seen with the new `again`
    extra: dict = field(default_factory=dict)

    @property
    def app(self) -> str:
        return self.spotted.app


def target(rect: Any, app: str, via: str, label: str = "The error") -> dict | None:
    """An AmbientTarget for a screen rect."""
    if rect is None:
        return None
    d = rect.to_dict() if hasattr(rect, "to_dict") else dict(rect)
    return {"x": d["x"], "y": d["y"], "w": d["w"], "h": d["h"], "label": label, "app": app, "via": via}


def seen_payload(h: Held) -> dict:
    f = h.spotted.found
    out: dict[str, Any] = {"id": h.id, "app": h.app, "kind": f.kind, "title": for_app(f.title)[:80],
                           "lines": [for_app(x) for x in f.lines], "at": h.at}
    if f.file:
        out["file"] = for_app(f.file)
    for k, v in (("line", f.line), ("col", f.col), ("exitCode", f.exit_code), ("lang", f.lang)):
        if v is not None:
            out[k] = v
    if (t := target(h.spotted.rect, h.app, "ocr")) is not None:  # a rect always comes from OCR rows
        out["rect"] = t
    if h.again:
        out["again"] = h.again
    return out


class ErrorWatcher:
    """Pure state over frames and ticks; `clock` is monotonic seconds. Every method returns the events to send:
    [("error.seen", payload)]."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, now_iso: Callable[[], str] = iso_now,
                 visible_s: float = VISIBLE_S, gap_s: float = GAP_S, clear_s: float = CLEAR_S,
                 ttl_s: float = TTL_S) -> None:
        self.clock = clock
        self.now_iso = now_iso
        self.visible_s, self.gap_s, self.clear_s, self.ttl_s = visible_s, gap_s, clear_s, ttl_s
        self.held: dict[str, Held] = {}
        self.quiet: dict[str, str] = {}  # dismissed / expired id -> its app (normalised): quiet until gone and back
        self.last_sent = -1e9
        self.on_screen_apps: set[str] = set()

    # -- inputs
    def frame(self, spotted: list[Spotted], apps: set[str]) -> list[tuple[str, dict]]:
        now = self.clock()
        self.on_screen_apps = set(apps)
        ids = {s.id for s in spotted}
        for qid, qapp in list(self.quiet.items()):
            if qid not in ids and qapp in apps:
                self.quiet.pop(qid)  # gone from its app: the next time it shows is news again
        for s in spotted:
            if s.id in self.quiet:
                continue
            copies = max(1, int(s.found.copies or 1))
            h = self.held.get(s.id)
            if h is None:
                self.held[s.id] = Held(id=s.id, spotted=s, first_t=now, last_t=now, at=self.now_iso(), copies=copies)
                continue
            back = h.absent_since is not None
            if h.shown and (back or copies > h.copies):
                h.again += 1
                h.dirty = True
            h.spotted = s if (s.rect is not None or h.spotted.rect is None) else Spotted(
                s.app, s.found, h.spotted.rect, h.spotted.via, s.doc)
            h.copies, h.last_t, h.absent_since = copies, now, None
        for h in list(self.held.values()):
            if h.id in ids:
                continue
            if not h.shown:
                del self.held[h.id]  # not on screen 1 s: never news
            elif h.absent_since is None and _norm(h.app) in apps:
                h.absent_since = now
        return self.tick()

    def tick(self) -> list[tuple[str, dict]]:
        now = self.clock()
        out: list[tuple[str, dict]] = []
        for h in list(self.held.values()):
            if h.shown and h.absent_since is not None and now - h.absent_since >= self.clear_s:
                del self.held[h.id]
                out.append(("error.seen", {"id": h.id, "clear": True}))
            elif now - h.first_t >= self.ttl_s:
                del self.held[h.id]
                self.quiet[h.id] = _norm(h.app)
        if now - self.last_sent >= self.gap_s:
            ready = [h for h in self.held.values() if h.absent_since is None and (
                (not h.shown and now - h.first_t >= self.visible_s) or h.dirty)]
            if ready:
                h = min(ready, key=lambda x: (x.shown, x.first_t))  # a new peek before an `again` update
                h.shown, h.dirty = True, False
                self.last_sent = now
                out.append(("error.seen", seen_payload(h)))
        return out

    def dismiss(self, eid: str) -> None:
        h = self.held.pop(eid, None)
        if h is not None:
            self.quiet[eid] = _norm(h.app)

    def get(self, eid: str) -> Held | None:
        h = self.held.get(eid)
        if h is not None and self.clock() - h.first_t >= self.ttl_s:
            self.held.pop(eid, None)
            return None
        return h if h is not None and h.shown else None

    def forget_all(self) -> list[tuple[str, dict]]:
        """Spotting turned off, or a lesson started: forget every error; the shown ones are cleared."""
        out = [("error.seen", {"id": h.id, "clear": True}) for h in self.held.values() if h.shown]
        self.held.clear()
        self.quiet.clear()
        return out
