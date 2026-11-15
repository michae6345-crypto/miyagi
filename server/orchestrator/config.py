"""Paths and env flags for the orchestrator."""

from __future__ import annotations

import os
import re
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


LESSONS_ROOT = Path(os.environ.get("MIYAGI_LESSONS", "~/miyagi/lessons")).expanduser()


def default_workdir() -> Path:
    """Where the engine looks before any lesson exists: TUT_WORKDIR, else the lessons root
    (never a demo folder: LIVE lessons get their own workspace, see lesson_workdir)."""
    if os.environ.get("TUT_WORKDIR"):
        return Path(os.environ["TUT_WORKDIR"]).expanduser().resolve()
    return LESSONS_ROOT


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:48] or "lesson"


def lesson_workdir(url: str, goal: str) -> Path:
    """The learner's project folder for a new lesson: TUT_WORKDIR (e.g. the hero's demo/pinn-lab)
    or ~/miyagi/lessons/<goal or video slug>, created if missing. (S2's server/workspace.prepare
    replaces this once it lands.)"""
    if os.environ.get("TUT_WORKDIR"):
        return default_workdir()
    vid = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{6,})", url or "")
    path = LESSONS_ROOT / _slug(goal or (vid.group(1) if vid else url))
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def lesson_file() -> Path | None:
    """ORCH_LESSON=<step graph json> (absolute or repo-relative): the lesson used when live building
    isn't possible (no Gemini key / not cached) and, with ORCH_AUTOSTART=1, loaded at startup."""
    v = os.environ.get("ORCH_LESSON")
    if not v:
        return None
    p = Path(v).expanduser()
    return p if p.is_absolute() else REPO_ROOT / p


def precision_setting() -> str:
    """ORCH_PRECISION=auto (workdir on disk or a tut run) | on | off (screen checks only)."""
    v = os.environ.get("ORCH_PRECISION", "auto").strip().lower()
    return v if v in ("auto", "on", "off") else "auto"


# Timings (seconds). Overridable for tests. Speech policy: docs/research/screen-understanding.md §4.
IDLE_GATE_S = float(os.environ.get("ORCH_IDLE_GATE_S", "3"))  # idle after the learner acted
STUCK_S = float(os.environ.get("ORCH_STUCK_S", "50"))  # no check progress for this long
TYPING_GUARD_S = float(os.environ.get("ORCH_TYPING_GUARD_S", "2"))  # never speak within this of a keystroke
LADDER_MIN_S = float(os.environ.get("ORCH_LADDER_MIN_S", "20"))  # concept card -> exact fix, at the earliest
ADVANCE_DELAY_S = float(os.environ.get("ORCH_ADVANCE_DELAY_S", "0.4"))
METRIC_EVAL_INTERVAL_S = float(os.environ.get("ORCH_METRIC_EVAL_S", "0.5"))
WATCH_INTERVAL_S = float(os.environ.get("ORCH_WATCH_S", "0.5"))
