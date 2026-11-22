"""The lesson file's exact text from the VS Code companion extension (server/workspace/vscode_ext.py): the editor's
live buffer, unsaved edits included. Checks on VS Code, the Check button's judge and the coach read the step's code
from here first, then from the file on disk, and only as a last resort from OCR, which misreads code (live test
00:55: "import numpy as np" OCR'd as "import numey as np" -> a false "Fix import to numpy as np").

    bufs = EditorBuffers(enabled=lambda: <real screen reader>)
    await bufs.refresh(paths, folder)  # at most one /text call per file per TTL_S (a tick), each capped at TIMEOUT_S
    bufs.text(path)                    # VS Code's text when a tab has the file open, else None (read the disk)
    bufs.dirty(path)                   # True / False (newest of that read and the extension's dirty/save events), None
    check_on_editor(check, paths, bufs, search, on_file)  # a VS Code screen check graded on that exact text

Never touches the editor in tests: `enabled()` is False without the real screen reader, and every read is then None.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

log = logging.getLogger("orchestrator.editor_text")

TTL_S = 1.0  # one read per file per tick: an evaluation within this reuses the last read
MAX_AGE_S = 4.0  # an older read says nothing (no evaluation lately): callers fall back to the title / the disk
TIMEOUT_S = 0.15  # per request; the extension answers localhost in a few ms


def _key(p: Any) -> str:
    try:
        return os.path.normcase(os.path.realpath(os.fspath(p)))
    except (OSError, TypeError, ValueError):
        return str(p)


def _ext() -> Any:
    try:
        return importlib.import_module("server.workspace.vscode_ext")
    except Exception:  # noqa: BLE001
        return None


def _read(ext: Any, paths: list[str], folder: str | None) -> list[dict | None]:
    """Blocking: one window scan, then one /text per file. {text, dirty, open} per path (open: a tab shows it)."""
    wins = ext.windows(timeout=TIMEOUT_S)
    out: list[dict | None] = []
    for p in paths:
        w = ext.pick(wins, file=p, folder=folder)
        if w is None:
            out.append(None)
            continue
        tabs = {_key(t["file"]) for t in w.get("openFiles") or [] if isinstance(t, dict) and t.get("file")
                and "://" not in str(t["file"])}
        dirty = {_key(f) for f in w.get("dirtyFiles") or [] if isinstance(f, str) and "://" not in f}
        if p not in tabs and p not in dirty:  # not open, no unsaved edits: the disk is its text (no /text call)
            out.append({"text": None, "dirty": False, "open": False})
            continue
        buf = ext.buffer_text(p, port=int(w["port"]), timeout=TIMEOUT_S)
        ok = isinstance(buf, dict) and buf.get("ok", True) and isinstance(buf.get("text"), str)
        out.append({"text": buf["text"], "dirty": bool(buf.get("dirty")), "open": p in tabs} if ok else None)
    return out


class EditorBuffers:
    def __init__(self, enabled: Callable[[], bool], clock: Callable[[], float] = time.time):
        self._enabled, self._clock = enabled, clock  # wall clock: compared with the extension events' "received"
        self._reads: dict[str, tuple[float, dict | None]] = {}

    def clear(self) -> None:
        """Forget the reads: the next refresh asks VS Code again (Check pressed, a save)."""
        self._reads.clear()

    async def refresh(self, paths: Iterable[Any], folder: str | None = None) -> None:
        now = self._clock()
        need = [k for k in dict.fromkeys(_key(p) for p in paths)
                if not k.endswith(".ipynb") and now - self._reads.get(k, (-1e9, None))[0] >= TTL_S]
        if not need or not self._enabled() or (ext := _ext()) is None:
            return
        try:
            got = await asyncio.to_thread(_read, ext, need, folder)
        except Exception as e:  # noqa: BLE001 - no extension text this tick: the disk / screen decide
            log.info("editor text unavailable (%s)", e)
            got = [None] * len(need)
        for k, b in zip(need, got):
            self._reads[k] = (now, b)  # asked at `now`: a dirty / save event after it is newer than this read

    def _fresh(self, path: Any) -> tuple[float, dict] | None:
        t, b = self._reads.get(_key(path), (-1e9, None))
        return (t, b) if b is not None and self._clock() - t <= MAX_AGE_S else None

    def text(self, path: Any) -> str | None:
        """VS Code's exact text of `path` (unsaved edits included) when a tab has it open; None: read the disk."""
        f = self._fresh(path)
        return f[1]["text"] if f and f[1]["open"] else None

    def unsaved_text(self, path: Any) -> str | None:
        """The buffer's text only while it holds unsaved edits (else the disk has the same)."""
        f = self._fresh(path)
        return f[1]["text"] if f and f[1]["dirty"] else None

    def dirty(self, path: Any) -> bool | None:
        """Does VS Code hold unsaved edits of `path`? The newest of the last read and a dirty / save event the
        extension posted after it. None: unknown (no recent read; or a clean read from a window with no tab of it)."""
        f = self._fresh(path)
        if f is None or not self._enabled() or (ext := _ext()) is None:
            return None
        t, val = f[0], (f[1]["dirty"] if f[1]["open"] or f[1]["dirty"] else None)
        k = _key(path)
        try:
            for ev in reversed(ext.recent_events()):
                if ev.get("received", 0) <= t:
                    break
                if ev.get("type") in ("dirty", "save") and ev.get("file") and _key(ev["file"]) == k:
                    return bool(ev.get("dirty")) if ev.get("type") == "dirty" else False
        except Exception:  # noqa: BLE001
            pass
        return val

    def named(self, name: str) -> list[str]:
        """The read files called `name` (nn.py), freshest first."""
        n = Path(str(name)).name
        hits = [(t, k) for k, (t, b) in self._reads.items() if b is not None and Path(k).name == n]
        return [k for _, k in sorted(hits, reverse=True)]


def check_on_editor(check: dict, paths: list[Path], bufs: EditorBuffers, search: Callable | None,
                    on_file: Callable | None, windows: Callable | None = None) -> tuple[dict, bool] | None:
    """Grade a VS Code screen_contains check on the exact text of its files: the editor's buffer of each file VS Code
    has open (unsaved edits included), else the file on disk. -> (result, unsaved): `unsaved` = the pass is only in
    an unsaved buffer, the file on disk lacks it (the save passes the step). None when VS Code has none of the files
    open (the screen decides, as before). `windows` (server.checks' scan_windows): a buffer is searched in the same
    64 KB windows as the file on disk (up to 1 MB), never a multi-MB buffer in one regex worker request."""
    pattern = check.get("pattern")
    texts = [(p, bufs.text(p)) for p in paths]
    if not pattern or search is None or on_file is None or all(t is None for _, t in texts):
        return None
    first = None
    for p, text in texts:
        if text is None:
            res = on_file(check, p)
        else:
            try:
                pieces = [sc.text for _, sc in windows(text)] if windows is not None else [text]
                hit = any(search(pattern, piece) is not None for piece in pieces)
            except re.error as e:
                return _result(check, "fail", f"invalid pattern: {e}"), False
            if hit:
                unsaved = bool(bufs.dirty(p)) and on_file(check, p).get("status") != "pass"
                return _result(check, "pass", f"typed in {p.name}"), unsaved
            res = _result(check, "fail", f"not in {p.name} yet")
        if res.get("status") == "pass":
            return res, False
        first = first or res
    return first, False


def _result(check: dict, status: str, detail: str) -> dict:
    return {"checkId": str(check.get("id", "")), "label": str(check.get("label", check.get("id", ""))),
            "status": status, "detail": detail}


def without_apps(lines: dict | None, apps: Iterable[str]) -> dict | None:
    """OCR lines by app minus `apps` (the code editor): with VS Code's exact text in hand, OCR must not judge code."""
    if not isinstance(lines, dict):
        return lines
    drop = {a.lower() for a in apps}
    return {a: ls for a, ls in lines.items() if (a or "").strip().lower() not in drop}


def save_card(step_id: str, name: str) -> dict:
    """Every check passes on the editor's text; only the save is missing. Calm, no Do it for me / Skip."""
    return {"stepId": step_id, "kind": "step", "title": "Save to finish",
            "body": f"Save {name} (⌘S) and this step is done.", "actions": []}
