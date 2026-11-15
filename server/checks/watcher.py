"""Workdir file watcher the orchestrator subscribes to (re-evaluate file_* checks on save).

    from server.checks.watcher import watch_workdir

    w = watch_workdir(workdir, on_change=lambda paths: ...)   # callback, runs on a worker thread
    # or, from async code:
    async for paths in w.changes():                          # list of workdir-relative paths
        ...
    w.stop()

Uses watchdog (FSEvents on macOS) when installed, else a polling thread (0.5 s).
Events are debounced (editors write files in several syscalls) and noise is
ignored (.git, __pycache__, .venv, node_modules, swap/temp files).
"""
from __future__ import annotations

import asyncio
import fnmatch
import os
import threading
import time
from collections.abc import AsyncIterator, Callable

IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache",
               ".ruff_cache", ".ipynb_checkpoints", "runs", "wandb", "lightning_logs"}
IGNORE_GLOBS = ["*.pyc", "*.swp", "*.swx", "*~", ".#*", "#*#", ".DS_Store", "*.tmp", "4913", "*.crdownload"]

OnChange = Callable[[list[str]], None]


def _ignored(rel: str) -> bool:
    parts = rel.replace(os.sep, "/").split("/")
    if any(p in IGNORE_DIRS for p in parts[:-1]):
        return True
    name = parts[-1]
    return any(fnmatch.fnmatch(name, g) for g in IGNORE_GLOBS)


class Watcher:
    def __init__(self, workdir: str, on_change: OnChange | None = None, debounce: float = 0.25,
                 poll_interval: float = 0.5, force_polling: bool = False):
        self.workdir = os.path.abspath(workdir)
        self.debounce = debounce
        self.poll_interval = poll_interval
        self._callbacks: list[OnChange] = [on_change] if on_change else []
        self._enders: list[Callable[[], None]] = []
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._stopped = threading.Event()
        self._observer = None
        self._poll_thread: threading.Thread | None = None
        self.backend = "polling"
        if not force_polling:
            try:
                self._start_watchdog()
                self.backend = "watchdog"
            except Exception:  # noqa: BLE001, S110 — never let a subscriber kill the watcher
                self._observer = None
        if self._observer is None:
            self._start_polling()

    # ------------------------------------------------------------ public
    def subscribe(self, cb: OnChange) -> None:
        self._callbacks.append(cb)

    async def changes(self) -> AsyncIterator[list[str]]:
        """Async iterator of debounced change batches; ends when stop() is called."""
        loop = asyncio.get_running_loop()
        q: asyncio.Queue[list[str] | None] = asyncio.Queue()
        cb = lambda paths: loop.call_soon_threadsafe(q.put_nowait, paths)
        self._callbacks.append(cb)
        self._enders.append(lambda: loop.call_soon_threadsafe(q.put_nowait, None))
        try:
            while not self._stopped.is_set():
                item = await q.get()
                if item is None:
                    break
                yield item
        finally:
            if cb in self._callbacks:
                self._callbacks.remove(cb)

    def stop(self) -> None:
        self._stopped.set()
        if self._timer:
            self._timer.cancel()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=2)
        for end in self._enders:
            try:
                end()  # wake async iterators so they finish
            except Exception:  # noqa: BLE001, S110 — never let a subscriber kill the watcher
                pass

    def __enter__(self) -> Watcher:
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # ------------------------------------------------------------ internals
    def _notify(self, abs_path: str) -> None:
        try:
            rel = os.path.relpath(abs_path, self.workdir)
        except ValueError:
            return
        if rel.startswith("..") or _ignored(rel):
            return
        with self._lock:
            self._pending.add(rel)
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            paths = sorted(self._pending)
            self._pending.clear()
            self._timer = None
        if not paths or self._stopped.is_set():
            return
        for cb in list(self._callbacks):
            try:
                cb(paths)
            except Exception:  # noqa: BLE001, S110 — never let a subscriber kill the watcher
                pass

    def _start_watchdog(self) -> None:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        watcher = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):
                if event.is_directory or event.event_type in ("opened", "closed_no_write"):
                    return
                watcher._notify(event.src_path)
                dest = getattr(event, "dest_path", None)
                if dest:
                    watcher._notify(dest)

        obs = Observer()
        obs.schedule(Handler(), self.workdir, recursive=True)
        obs.daemon = True
        obs.start()
        self._observer = obs

    def _snapshot(self) -> dict[str, tuple[float, int]]:
        snap: dict[str, tuple[float, int]] = {}
        for root, dirs, files in os.walk(self.workdir):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for f in files:
                p = os.path.join(root, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                snap[p] = (st.st_mtime, st.st_size)
        return snap

    def _start_polling(self) -> None:
        def loop() -> None:
            prev = self._snapshot()
            while not self._stopped.wait(self.poll_interval):
                cur = self._snapshot()
                for p in cur.keys() | prev.keys():
                    if cur.get(p) != prev.get(p):
                        self._notify(p)
                prev = cur

        self._poll_thread = threading.Thread(target=loop, name="workdir-poll", daemon=True)
        self._poll_thread.start()


def watch_workdir(workdir: str, on_change: OnChange | None = None, **kw) -> Watcher:
    return Watcher(workdir, on_change=on_change, **kw)


if __name__ == "__main__":  # python -m server.checks.watcher <dir>
    import sys

    w = watch_workdir(sys.argv[1] if len(sys.argv) > 1 else ".", on_change=lambda p: print("changed:", p, flush=True))
    print(f"watching {w.workdir} via {w.backend}; Ctrl-C to stop", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        w.stop()
