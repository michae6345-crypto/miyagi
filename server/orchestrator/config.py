"""Paths and env flags for the orchestrator."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEMO_CACHE = REPO_ROOT / "demo" / "cache"

# `shared/contracts` is a plain folder, not an installed package: make it importable
# no matter where the server is launched from.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def env_file() -> Path | None:
    """TUT_ENV > this checkout's .env > the main checkout's .env (when running in a
    `.claude/worktrees/<name>` worktree, which has no .env of its own)."""
    if os.environ.get("TUT_ENV"):
        return Path(os.environ["TUT_ENV"]).expanduser()
    if (REPO_ROOT / ".env").exists():
        return REPO_ROOT / ".env"
    parts = REPO_ROOT.parts
    if ".claude" in parts:
        main = Path(*parts[: parts.index(".claude")]) / ".env"
        if main.exists():
            return main
    return None


try:  # load .env if present (never committed); real env vars win
    from dotenv import load_dotenv

    if env_file():
        load_dotenv(env_file())
except ImportError:  # pragma: no cover
    pass


def env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def demo_mode() -> bool:
    return env_flag("DEMO")


def port() -> int:
    return int(os.environ.get("ENGINE_PORT", "8787"))


def default_workdir() -> Path:
    """Where the learner works, before a lesson tells us otherwise."""
    if os.environ.get("TUT_WORKDIR"):
        return Path(os.environ["TUT_WORKDIR"]).expanduser().resolve()
    return (REPO_ROOT / "demo" / "pinn").resolve()


def resolve_workdir(lesson_workdir: str | None) -> Path:
    """TUT_WORKDIR env > lesson.workdir (absolute, or relative to repo root) > default."""
    if os.environ.get("TUT_WORKDIR"):
        return default_workdir()
    if lesson_workdir:
        p = Path(lesson_workdir).expanduser()
        if not p.is_absolute():
            p = REPO_ROOT / p
        return p.resolve()
    return default_workdir()


# Timings (seconds). Overridable for tests.
IDLE_GATE_S = float(os.environ.get("ORCH_IDLE_GATE_S", "5"))
ADVANCE_DELAY_S = float(os.environ.get("ORCH_ADVANCE_DELAY_S", "0.4"))
METRIC_EVAL_INTERVAL_S = float(os.environ.get("ORCH_METRIC_EVAL_S", "0.5"))
WATCH_INTERVAL_S = float(os.environ.get("ORCH_WATCH_S", "0.5"))
