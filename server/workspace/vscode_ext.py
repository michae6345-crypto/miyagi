"""Client for the Miyagi VS Code companion extension (vscode-ext/): exact editor state and actions, no OCR.

    from server.workspace import vscode_ext as vx
    st = vx.state()                          # the focused VS Code window's /state, or None (not running)
    st = vx.state(folder=lesson_dir)         # the window that has the lesson folder open (else the focused one)
    vx.open_file(path, line=12)              # opens in the window whose folder holds the file; never a new window
    vx.highlight(path, 12, 14); vx.clear_highlight()
    vx.show_terminal(); vx.run_in_terminal("python calculator.py", cwd=lesson_dir)
    vx.last_command()                        # {commandLine, exitCode, outputTail[], running, cwd} (shell integration)
    vx.apply(path, new_text=...)             # WorkspaceEdit + save: works on unsaved buffers
    vx.save(path)                            # ⌘S on that file (0.0.4 /save; older: a no-op /apply that saves)
    vx.replace_line(path, yours, expected)   # E5's apply_fix semantics (indentation kept)
    vx.diff(path, new_text)                  # preview only
    vx.buffer_text(path)                     # the editor's text, unsaved edits included
    vx.active_editor()                       # same shape as server.workspace.active.active_editor(), source "extension"

Every call is synchronous, returns within TIMEOUT_S (0.3 s) and returns None when no window answers (extension
not installed, VS Code closed, timeout). From async code: `await asyncio.to_thread(vx.state)`. A running
extension that refuses a request answers {"ok": False, "error": ...} (not_found, find_not_found, ...). A slow action
answers {"ok": True, "pending": True, "id": n}; its result arrives later as an `action_done` event.

Each VS Code window runs its own extension on the next free port from 8791 (MIYAGI_VSCODE_PORTS, default
"8791-8799"); calls go to the window that has the file/folder open, else the focused (or last focused) one.

Events: the extension posts editor / save / dirty / focus / terminal / command_start / command_end / action_done /
ready to POST /vscode/event, which calls `record_event`. `subscribe(cb)` to react (sync or async callbacks).

Token (ROADMAP 5.3): every call carries X-Miyagi-Token, the engine's per-launch token (`set_link_token`, from
main.run(); in any other process, a live engine's token from server.engine_token). The companion (0.0.7+) requires it
while a live engine has written one, so another local program can't drive VS Code through it; older companions
ignore the header.
"""

from __future__ import annotations

import asyncio
import http.client
import inspect
import json
import logging
import os
import threading
import time
import urllib.parse
from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, wait
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any

log = logging.getLogger("server.workspace.vscode_ext")

HOST = "127.0.0.1"
TIMEOUT_S = 0.3
DEFAULT_PORTS = "8791-8799"
MAX_RESPONSE = 8 * 1024 * 1024

_POOL = ThreadPoolExecutor(max_workers=12, thread_name_prefix="vscode-ext")
_link_token: str | None = None
_disk_token: tuple[float, str | None] = (0.0, None)
TOKEN_TTL_S = 2.0


def set_link_token(token: str | None) -> None:
    """The engine's own token (main.run() sets it once): sent on every call to the companion."""
    global _link_token
    _link_token = token or None


def link_token() -> str | None:
    """This engine's token, else (a test, a script) a live engine's from server.engine_token (re-read every 2 s)."""
    global _disk_token
    if _link_token:
        return _link_token
    now = time.monotonic()
    if now - _disk_token[0] >= TOKEN_TTL_S:
        try:
            from server import engine_token

            live = engine_token.live_tokens()
        except Exception:  # noqa: BLE001 - no token: an older companion / no engine, the call goes without
            live = []
        _disk_token = (now, live[0] if live else None)
    return _disk_token[1]


# ------------------------------------------------------------------ transport

def ports() -> list[int]:
    """MIYAGI_VSCODE_PORTS: "8791-8799" or "8791,8792" (default 8791-8799)."""
    spec = os.environ.get("MIYAGI_VSCODE_PORTS", "").strip() or DEFAULT_PORTS
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = (int(x) for x in part.split("-", 1))
                out.extend(range(a, b + 1))
            else:
                out.append(int(part))
        except ValueError:
            log.warning("ignoring bad MIYAGI_VSCODE_PORTS entry %r", part)
    return list(dict.fromkeys(p for p in out if 0 < p < 65536))


def _http(port: int, method: str, path: str, body: dict | None, timeout: float) -> dict | None:
    conn = http.client.HTTPConnection(HOST, port, timeout=timeout)
    try:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        if tok := link_token():
            headers["X-Miyagi-Token"] = tok
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        raw = resp.read(MAX_RESPONSE)
        out = json.loads(raw) if raw else {}
        if not isinstance(out, dict):
            return None
        out.setdefault("ok", 200 <= resp.status < 300)
        return out
    except (OSError, http.client.HTTPException, ValueError):
        return None
    finally:
        conn.close()


def _call(port: int, method: str, path: str, body: dict | None = None, timeout: float = TIMEOUT_S) -> dict | None:
    """One request, hard-capped at `timeout` for the caller (the worker thread may finish a little later)."""
    timeout = min(timeout, TIMEOUT_S)
    fut = _POOL.submit(_http, port, method, path, body, timeout)
    try:
        return fut.result(timeout=timeout)
    except FutureTimeout:
        return None
    except Exception:
        log.exception("vscode-ext %s %s failed", method, path)
        return None


def _scan(method: str, path: str, body: dict | None = None, timeout: float = TIMEOUT_S) -> list[dict]:
    """The same request to every port at once; the answers that came back within `timeout`."""
    timeout = min(timeout, TIMEOUT_S)
    futs = [_POOL.submit(_http, p, method, path, body, timeout) for p in ports()]
    done, _ = wait(futs, timeout=timeout)
    out = []
    for f in futs:
        if f in done and f.exception() is None and isinstance(f.result(), dict):
            out.append(f.result())
    return out


# ------------------------------------------------------------------ windows

def windows(timeout: float = TIMEOUT_S) -> list[dict]:
    """Every VS Code window with the extension: their /state, focused first, then most recently focused. [] if none."""
    wins = [w for w in _scan("GET", "/state", timeout=timeout) if w.get("app") == "vscode" and w.get("port")]
    return sorted(wins, key=lambda w: (bool(w.get("windowFocused")), w.get("lastFocusedAt") or 0), reverse=True)


def window_state(port: int, timeout: float = TIMEOUT_S) -> dict | None:
    """The /state of exactly the window on `port` (a windows() entry's port; no scan of every port), or None."""
    st = _call(int(port), "GET", "/state", timeout=timeout)
    return st if st and st.get("app") == "vscode" and st.get("port") else None


def available() -> bool:
    return bool(windows())


def _inside(child: str | Path, parent: str | Path) -> bool:
    try:
        Path(child).expanduser().resolve().relative_to(Path(parent).expanduser().resolve())
        return True
    except (ValueError, OSError):
        return False


def pick(wins: list[dict], *, file: str | Path | None = None, folder: str | Path | None = None) -> dict | None:
    """The window to use: one whose workspace folders hold `file`, else one that has `folder` open (or a parent of
    it), else the focused / last focused window. `wins` must be in windows() order."""
    if not wins:
        return None
    for target in (file, folder):
        if target:
            hit = [w for w in wins if any(_inside(target, f) for f in w.get("folders") or [])]
            if hit:
                return hit[0]
    return wins[0]


def _window(file: str | Path | None = None, folder: str | Path | None = None) -> dict | None:
    return pick(windows(), file=file, folder=folder)


def _post(path: str, body: dict, *, file: str | Path | None = None, folder: str | Path | None = None) -> dict | None:
    w = _window(file=file, folder=folder)
    if w is None:
        return None
    return _call(int(w["port"]), "POST", path, body)


def _abs(file: str | Path | None, folder: str | Path | None) -> str | None:
    if file is None:
        return None
    p = Path(file).expanduser()
    if not p.is_absolute() and folder:
        p = Path(folder).expanduser() / p
    return str(p)


# ------------------------------------------------------------------ reads

def state(*, folder: str | Path | None = None, file: str | Path | None = None) -> dict | None:
    """{folders, file, relPath, dirty, languageId, cursor{line,column}, visibleRanges[{startLine,endLine}], dirtyFiles,
    openFiles, terminalOpen, terminals, lastCommand, windowFocused, lastFocusedAt, highlight, port, ...} or None."""
    return _window(file=file, folder=folder)


def last_command(*, folder: str | Path | None = None) -> dict | None:
    """The last terminal command in that window: {commandLine, exitCode (None while running or unknown), running,
    outputTail: [lines], cwd, terminal, startedAt, endedAt}. Needs VS Code 1.93+ shell integration."""
    st = state(folder=folder)
    return (st or {}).get("lastCommand")


def buffer_text(file: str | Path | None = None, *, folder: str | Path | None = None, port: int | None = None,
                timeout: float = TIMEOUT_S) -> dict | None:
    """{file, text, dirty, version, languageId, lineCount}: what the editor holds, unsaved edits included.
    No file: the active editor. port: exactly that window (a windows() entry's port), no window scan."""
    path = _abs(file, folder)
    if port is None:
        w = _window(file=path, folder=folder)
        if w is None:
            return None
        port = int(w["port"])
    q = "/text" + (f"?file={urllib.parse.quote(path)}" if path else "")
    return _call(int(port), "GET", q, timeout=timeout)


def active_editor() -> dict | None:
    """The focused window's editor in server.workspace.active.active_editor()'s shape (pass it as `active=` to
    wrong_folder), plus cursor/languageId/port. None without the extension or without an open file."""
    st = state()
    if not st or not st.get("file") or "://" in str(st["file"]) or str(st["file"]).startswith("untitled:"):
        return None
    path = Path(st["file"])
    folder = next((f for f in st.get("folders") or [] if _inside(path, f)), None) or str(path.parent)
    from .active import is_lesson_folder

    return {"folder": folder, "folder_name": Path(folder).name, "file": path.name, "path": str(path),
            "dirty": bool(st.get("dirty")), "title": None, "miyagi_lesson": is_lesson_folder(folder),
            "source": "extension", "cursor": st.get("cursor"), "languageId": st.get("languageId"),
            "port": st.get("port")}


# ------------------------------------------------------------------ actions

def open_file(file: str | Path, line: int | None = None, *, column: int | None = None,
              folder: str | Path | None = None, preserve_focus: bool = False, port: int | None = None) -> dict | None:
    """Open/reveal `file` (centered on `line`) in the window that has it, never a new window. port: exactly that
    window (a windows() entry's port), e.g. the lesson folder's own window."""
    path = _abs(file, folder)
    body: dict[str, Any] = {"file": path, "preserveFocus": preserve_focus}
    if line:
        body["line"] = int(line)
    if column:
        body["column"] = int(column)
    if port:
        return _call(int(port), "POST", "/open", body)
    return _post("/open", body, file=path, folder=folder)


def highlight(file: str | Path, start_line: int, end_line: int | None = None, *,
              folder: str | Path | None = None, focus: bool = False) -> dict | None:
    """A white 2px box (faint fill) around lines start..end, scrolled to the center. One highlight per window."""
    path = _abs(file, folder)
    body = {"file": path, "startLine": int(start_line), "endLine": int(end_line or start_line), "focus": focus}
    return _post("/highlight", body, file=path, folder=folder)


def clear_highlight() -> dict | None:
    """Remove the highlight in every window. None when no window answered."""
    answers = [a for a in (_call(int(w["port"]), "POST", "/highlight", {"clear": True}) for w in windows()) if a]
    return {"ok": True, "cleared": len(answers)} if answers else None


def show_terminal(*, folder: str | Path | None = None, cwd: str | Path | None = None,
                  preserve_focus: bool = False) -> dict | None:
    body: dict[str, Any] = {"show": True, "preserveFocus": preserve_focus}
    if cwd:
        body["cwd"] = str(cwd)
    return _post("/terminal", body, folder=folder or cwd)


def hide_terminal(*, folder: str | Path | None = None) -> dict | None:
    return _post("/terminal", {"show": False}, folder=folder)


def run_in_terminal(cmd: str, *, cwd: str | Path | None = None, folder: str | Path | None = None,
                    preserve_focus: bool = False) -> dict | None:
    """Type `cmd` + Enter in the window's "Miyagi" terminal (created once, then reused; `cd cwd &&` is added when the
    shell is elsewhere). Returns at once; the exit code and output come later via last_command() or a
    `command_end` event (when reportsExitCode)."""
    body: dict[str, Any] = {"cmd": cmd, "preserveFocus": preserve_focus}
    if cwd:
        body["cwd"] = str(cwd)
    return _post("/terminal/run", body, folder=folder or cwd)


def refresh_python(folder: str | Path, *, tries: int = 10, every_s: float = 2.0, sleep=time.sleep) -> dict | None:
    """After a pip install into <folder>/.venv (E20): the window that has `folder` open selects that .venv as its Python
    interpreter and restarts the Python language server, so Pylance re-reads the packages (it resolved `import
    requests` before the .venv existed and kept the warning). Only that window, never another one. Retries while the
    window or its extension is still starting (the folder opened the same second the install finished). Blocking.
    None when no window has the folder open; {"ok": False, "error": "no_route"} from an older extension."""
    root = str(Path(folder).expanduser().resolve())
    for k in range(max(1, tries)):
        w = next((w for w in windows() if any(_inside(root, f) or _inside(f, root) for f in w.get("folders") or [])), None)
        if w is not None:
            out = _call(int(w["port"]), "POST", "/python/refresh", {"folder": root})
            if out is not None:
                log.info("python refresh in %s: %s", Path(root).name, out)
                return out
        if k + 1 < tries:
            sleep(every_s)
    return None


def apply(file: str | Path, new_text: str | None = None, *, edits: Iterable[dict] | None = None, save: bool = True,
          reveal: bool = True, folder: str | Path | None = None) -> dict | None:
    """Edit through VS Code (WorkspaceEdit), then save: the learner's unsaved buffer is edited, not clobbered on
    disk behind its back. new_text replaces everything (and creates a missing file); edits are
    {find, replace} | {startLine, endLine, text} | {startLine, startColumn, endLine, endColumn, text} (1-based)."""
    path = _abs(file, folder)
    body: dict[str, Any] = {"file": path, "save": save, "reveal": reveal}
    if new_text is not None:
        body["newText"] = new_text
    elif edits is not None:
        body["edits"] = list(edits)
    else:
        raise ValueError("apply() needs new_text or edits")
    return _post("/apply", body, file=path, folder=folder)


def save(file: str | Path, *, folder: str | Path | None = None) -> dict | None:
    """Save `file` in the window that has it, as ⌘S does: its unsaved edits go to disk (Run it for me / Check on a run
    step, so what runs is what the editor shows). The 0.0.4 extension's POST /save -> {ok, file, open, saved, dirty};
    an older one (no_route): a no-op /apply edit (empty text at 1:1) that saves the buffer as it is: no text change,
    no cursor move, nothing revealed. None when no window answered."""
    path = _abs(file, folder)
    w = _window(file=path, folder=folder)
    if w is None:
        return None
    port = int(w["port"])
    out = _call(port, "POST", "/save", {"file": path})
    if out is not None and out.get("error") == "no_route":
        noop = {"startLine": 1, "startColumn": 1, "endLine": 1, "endColumn": 1, "text": ""}
        out = _call(port, "POST", "/apply", {"file": path, "edits": [noop], "save": True, "reveal": False})
    return out


def replace_line(file: str | Path, yours: str, expected: str, *, save: bool = True,
                 folder: str | Path | None = None) -> dict | None:
    """Replace the first line equal to `yours` (trimmed) with `expected`, keeping its indentation."""
    return apply(file, edits=[{"find": yours, "replace": expected}], save=save, folder=folder)


def diff(file: str | Path, new_text: str, *, title: str | None = None, folder: str | Path | None = None) -> dict | None:
    """Side-by-side preview: the file (as the editor has it) on the left, `new_text` on the right. Changes nothing."""
    path = _abs(file, folder)
    body: dict[str, Any] = {"file": path, "newText": new_text}
    if title:
        body["title"] = title
    return _post("/diff", body, file=path, folder=folder)


# ------------------------------------------------------------------ events (POST /vscode/event)

_events: deque[dict] = deque(maxlen=200)
_latest: dict[str, dict] = {}
_subscribers: list[Callable[[dict], Any]] = []
_lock = threading.Lock()
_seq = 0
# Companion 0.0.5's `visible` (every scroll, 80 ms debounce) goes to the subscribers and last_event only: in the
# 200-event history a long scroll pushed out the command_end / dirty events that recent_events() readers still need.
_NOT_KEPT = frozenset({"visible"})


def record_event(ev: dict) -> dict:
    """Store one extension event and hand it to the subscribers. Returns the stored event (with seq, received)."""
    global _seq
    if not isinstance(ev, dict):
        return {}
    with _lock:
        _seq += 1
        item = {**ev, "seq": _seq, "received": time.time()}
        if str(ev.get("type") or "") not in _NOT_KEPT:
            _events.append(item)
        _latest[str(ev.get("type") or "")] = item
        subs = list(_subscribers)
    for cb in subs:
        try:
            res = cb(item)
            if inspect.isawaitable(res):
                try:
                    asyncio.get_running_loop().create_task(res)
                except RuntimeError:  # no running loop: run it here
                    asyncio.run(res)
        except Exception:
            log.exception("vscode-ext event subscriber failed")
    return item


def subscribe(cb: Callable[[dict], Any]) -> Callable[[], None]:
    """cb(event) for every event (sync, or async when an event loop is running). Returns an unsubscribe function."""
    with _lock:
        _subscribers.append(cb)

    def unsubscribe() -> None:
        with _lock:
            if cb in _subscribers:
                _subscribers.remove(cb)

    return unsubscribe


def recent_events(since: int = 0) -> list[dict]:
    """Events with seq > since (the last 200 at most)."""
    with _lock:
        return [e for e in _events if e["seq"] > since]


def last_event(type_: str | None = None) -> dict | None:
    with _lock:
        if type_ is None:
            return _events[-1] if _events else None
        return _latest.get(type_)


def reset_events() -> None:
    """Tests only."""
    global _seq
    with _lock:
        _events.clear()
        _latest.clear()
        _subscribers.clear()
        _seq = 0
