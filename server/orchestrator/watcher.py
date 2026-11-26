"""Polling file watcher on the learner's workdir (no extra dependency, works everywhere)."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path

log = logging.getLogger("orchestrator.watcher")

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".ipynb_checkpoints", "runs", "outputs", "wandb"}
WATCH_EXT = {".py", ".ipynb", ".txt", ".toml", ".cfg", ".yaml", ".yml", ".json", ".md", ".sh", ".js", ".ts"}
MAX_FILES = 3000


def snapshot(root: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            p = os.path.join(dirpath, f)
            if os.path.splitext(f)[1] not in WATCH_EXT:
                continue
            try:
                out[p] = os.stat(p).st_mtime
            except OSError:
                continue
            if len(out) >= MAX_FILES:
                return out
    return out


class Watcher:
    def __init__(self, on_change: Callable[[list[str]], Awaitable[None]], interval: float = 0.5):
        self.on_change = on_change
        self.interval = interval
        self.root: Path | None = None
        self._snap: dict[str, float] = {}
        self._task: asyncio.Task | None = None

    def set_root(self, root: str | Path) -> None:
        self.root = Path(root)
        self._snap = snapshot(self.root)
        log.info("watching %s (%d files)", self.root, len(self._snap))

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def poll(self) -> list[str]:
        if self.root is None:
            return []
        new = snapshot(self.root)
        changed = [p for p, m in new.items() if self._snap.get(p) != m]
        changed += [p for p in self._snap if p not in new]
        self._snap = new
        return changed

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            try:
                changed = await asyncio.to_thread(self.poll)
                if changed:
                    await self.on_change(changed)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("watcher poll failed")
