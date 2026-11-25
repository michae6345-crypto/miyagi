"""Keep a Blender scene dump fresh before a check reads it (Nov 24, Blender integration).

A Blender step is graded by file_contains checks on "mug.scene.json": the scene of the learner's "mug.blend" as JSON
(format "dump_scene.py 1", blender-addon/dump_scene.py). Nothing else writes that file, so the evaluator calls
refresh(path) right before it reads one, and refresh brings it up to date:

  1. "off"      : refresh is disabled (the default: the eval runner and the tests never touch Blender). The engine
                  turns it on at start (server/orchestrator/main.py).
  2. "live"     : the miyagi bridge add-on inside the learner's running Blender has that .blend open
                  (server.workspace.blender_ext.live_state): its scene is written, only when the text changed. Asked
                  at most once a second per file; a gate with three checks on one dump asks once.
  3. "headless" : no live scene, and the .blend was saved after the dump (or there is no dump yet, or the file there
                  is not a dump: a lesson step's file is made empty with touch before the step starts): a background
                  Blender dumps the saved file (server.workspace.blender.dump_blend). Tried at most once every 10 s
                  per file. "none" when that dump failed (no Blender, a broken file); a failed .blend is not tried
                  again until it is saved again (its mtime or size changes), so a broken file does not start a
                  background Blender every 10 s while the gate (which holds the session lock) waits on it.
  4. "fresh"    : the dump on disk is as new as the .blend, or there is no .blend, or the .blend is empty (lesson mode
                  makes a step's file with touch before the step starts: an empty donut.blend is not a saved scene),
                  or this .blend already failed to dump: nothing to do.

Both sources are other lanes' modules, imported lazily: before they merge, refresh works and just finds nothing. It
never raises; a check reads whatever is on disk afterwards.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

FORMAT = "dump_scene.py 1"  # the tag every dump carries (blender-addon/miyagi_bridge/scene_dump.py)
LIVE_EVERY_S = 1.0  # ask the live bridge at most this often per dump
HEADLESS_EVERY_S = 10.0  # start a background Blender at most this often per dump
_SUFFIX = ".scene.json"
_HEAD_BYTES = 256  # a dump names its format in its first line or two: '{\n "dump": "dump_scene.py 1",'
_TAG = re.compile(r'"dump"\s*:\s*"' + re.escape(FORMAT) + '"')

_on = False
_guard = threading.Lock()  # guards the tables below
_locks: dict[str, threading.Lock] = {}
_live_at: dict[str, float] = {}  # when the live bridge was last asked, per dump
_live_ok: dict[str, bool] = {}  # did that ask give a scene
_headless_at: dict[str, float] = {}  # when a background dump was last started, per dump
_headless_failed: dict[str, tuple[int, int]] = {}  # the .blend (mtime_ns, size) whose background dump failed, per dump


def enable(on: bool = True) -> None:
    """Turn refreshing on (the engine) or off."""
    global _on
    _on = bool(on)


def enabled() -> bool:
    return _on


def reset() -> None:
    """Forget every throttle and lock (tests)."""
    with _guard:
        _locks.clear()
        _live_at.clear()
        _live_ok.clear()
        _headless_at.clear()
        _headless_failed.clear()


def blend_for(scene_json_path) -> Path:
    """mug.scene.json -> mug.blend, in the same folder."""
    p = Path(scene_json_path)
    name = p.name
    stem = name[: -len(_SUFFIX)] if name.lower().endswith(_SUFFIX) else p.stem
    return p.with_name(stem + ".blend")


def _default_live() -> Callable | None:
    try:
        from server.workspace import blender_ext
    except ImportError:
        return None
    return getattr(blender_ext, "live_state", None)


def _default_headless() -> Callable | None:
    try:
        from server.workspace import blender
    except ImportError:
        return None
    return getattr(blender, "dump_blend", None)


def _lock_for(key: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(key, threading.Lock())


def _mtime(path: str) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _saved_blend(path: str) -> tuple[int, int] | None:
    """(mtime_ns, size) of a saved .blend, or None when there is none. A 0-byte file is no .blend: lesson mode makes
    the step's file with touch before the step starts, and Blender cannot open it."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size) if st.st_size > 0 else None


def is_dump(path: str) -> bool:
    """True when `path` holds a scene dump: its first bytes carry '"dump": "dump_scene.py 1"'. An empty file (a lesson
    step's file made with touch before the step starts) or any other JSON is not one."""
    try:
        with open(path, "rb") as f:
            head = f.read(_HEAD_BYTES)
    except OSError:
        return False
    return bool(_TAG.search(head.decode("utf-8", "replace")))


def to_text(doc: dict) -> str:
    """A dump as the dumper writes it: indent 1, keys in order, non-ASCII kept, one trailing newline."""
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def write_if_changed(path: str, text: str) -> bool:
    """Write `text` to `path` atomically (a temp file beside it, then os.replace), only when it differs from what is
    there. -> True when the file was written."""
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except (OSError, UnicodeDecodeError):
        pass
    folder = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True


def _try_live(key: str, blend: str, live, now: float) -> str | None:
    """Step 2: "live" when the bridge gave (or, within LIVE_EVERY_S, last gave) a scene, else None."""
    last = _live_at.get(key)
    if last is not None and now - last < LIVE_EVERY_S:
        return "live" if _live_ok.get(key) else None
    _live_at[key] = now
    _live_ok[key] = False
    fn = live if live is not None else _default_live()
    if fn is None:
        return None
    try:
        doc = fn(blend)
    except Exception as e:  # noqa: BLE001  a bridge that misbehaves is no bridge
        log.debug("live scene for %s failed: %s", blend, e)
        return None
    if not isinstance(doc, dict) or doc.get("dump") != FORMAT:
        return None
    write_if_changed(key, to_text(doc))
    _live_ok[key] = True
    return "live"


def _try_headless(key: str, blend: str, headless, now: float) -> str | None:
    """Step 3: dump the saved .blend when the dump is missing, is not a dump (empty, or other JSON), or is older than
    the .blend, the .blend is not empty and has not already failed as it is now, and the last try is
    HEADLESS_EVERY_S old."""
    saved = _saved_blend(blend)
    if saved is None:
        return None
    b = saved[0] / 1e9
    j = _mtime(key)
    if j is not None and b <= j and is_dump(key):
        return None
    if _headless_failed.get(key) == saved:  # this very file failed before: wait for the next save
        return None
    last = _headless_at.get(key)
    if last is not None and now - last < HEADLESS_EVERY_S:
        return None
    _headless_at[key] = now
    fn = headless if headless is not None else _default_headless()
    doc = None
    if fn is not None:
        try:
            doc = fn(blend, key)
        except Exception as e:  # noqa: BLE001  dump_blend never raises; a stand-in might
            log.debug("headless dump of %s failed: %s", blend, e)
    if doc is None:
        _headless_failed[key] = saved
        return "none"
    _headless_failed.pop(key, None)
    return "headless"


def refresh(scene_json_path: str, *, live=None, headless=None, clock=time.monotonic) -> str:
    """Bring `scene_json_path` up to date before a check reads it (see the module doc). -> "off" | "live" |
    "headless" | "fresh" | "none". `live(blend_path)` -> dump dict or None and `headless(blend_path, json_path)` ->
    dict or None default to the bridge and the background dumper. Never raises."""
    if not _on:
        return "off"
    try:
        key = os.path.abspath(str(scene_json_path))
        blend = str(blend_for(key))
        with _lock_for(key):
            now = clock()
            return (_try_live(key, blend, live, now) or _try_headless(key, blend, headless, now) or "fresh")
    except Exception as e:  # noqa: BLE001  a check must still read whatever is on disk
        log.warning("scene refresh of %s failed: %s", scene_json_path, e)
        return "none"
