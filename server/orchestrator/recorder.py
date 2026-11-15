"""Record every `tut run` ingest event to demo/runs/<run_id>.jsonl, and replay a recorded run
through the state machine as if it were live (the DEMO=1 safety net for the training run).

Replay looks in demo/cache/runs/ first (curated, committed by the demo owner), then demo/runs/
(local recordings, gitignored). Copy the good take into demo/cache/runs/ to keep it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from .config import DEMO_CACHE, REPO_ROOT, env_flag

log = logging.getLogger("orchestrator.recorder")

RUNS_DIR = REPO_ROOT / "demo" / "runs"
CACHE_RUNS = DEMO_CACHE / "runs"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:80] or "run"


class Recorder:
    def __init__(self, out_dir: Path = RUNS_DIR, enabled: bool | None = None):
        self.out_dir = out_dir
        self.enabled = env_flag("ORCH_RECORD", True) if enabled is None else enabled
        self._t0: dict[str, float] = {}

    def record(self, ev: dict) -> None:
        if not self.enabled or ev.get("replay"):
            return
        run_id = str(ev.get("run_id") or "run")
        now = time.monotonic()
        t0 = self._t0.setdefault(run_id, now)
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            with open(self.out_dir / f"{_safe(run_id)}.jsonl", "a") as f:
                f.write(json.dumps({"dt": round(now - t0, 3), "event": ev}) + "\n")
        except OSError as e:
            log.warning("could not record run %s: %s", run_id, e)


def list_recordings() -> list[Path]:
    out: list[Path] = []
    for d in (CACHE_RUNS, RUNS_DIR):
        if d.is_dir():
            out += sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return out


def find_recording(name: str | None) -> Path | None:
    recs = list_recordings()
    if not name:
        return recs[0] if recs else None
    for p in recs:
        if p.stem == name or p.name == name:
            return p
    return None


def load(path: Path) -> list[tuple[float, dict]]:
    items = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if "event" in rec:
            items.append((float(rec.get("dt", 0)), rec["event"]))
        else:  # a bare ingest event per line also works
            items.append((0.0, rec))
    return items


async def replay(path: Path, ingest: Callable[[dict], Awaitable[None]], speed: float = 1.0,
                 max_gap: float = 2.0) -> str:
    """Feed a recording into `ingest` with its original pacing (gaps capped at max_gap s).
    Uses a fresh run_id so it counts as a new run for the active step."""
    items = load(path)
    run_id = f"replay-{path.stem}-{int(time.time()) % 100000}"
    prev = 0.0
    for dt, ev in items:
        gap = min(max(0.0, dt - prev), max_gap) / max(speed, 1e-3)
        prev = dt
        if gap:
            await asyncio.sleep(gap)
        await ingest({**ev, "run_id": run_id, "replay": True})
    log.info("replayed %s as %s (%d events)", path.name, run_id, len(items))
    return run_id


def default_speed() -> float:
    return float(os.environ.get("ORCH_REPLAY_SPEED", "1"))
