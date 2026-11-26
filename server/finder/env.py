"""Keys and settings. Same .env lookup as the other modules: $TUT_ENV, the repo root,
then the main checkout when running inside a worktree. App keys (config.keys) win."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_loaded = False


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    candidates = [Path(p) for p in [os.environ.get("TUT_ENV")] if p] + [ROOT / ".env"]
    if ROOT.parent.name == "worktrees" and ROOT.parent.parent.name == ".claude":
        candidates.append(ROOT.parents[2] / ".env")
    for p in candidates:
        if p.is_file():
            load_dotenv(p, override=False)


def _usable(v: str | None) -> str | None:
    v = (v or "").strip()
    return v if v and "..." not in v else None


@dataclass(frozen=True)
class Keys:
    gemini: str | None
    anthropic: str | None
    github: str | None


def _shared(name: str) -> str | None:
    """server.config.get_key (the app's bring-your-own-key store) when that module exists."""
    try:
        from server.config import get_key  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        return _usable(get_key(name))
    except Exception:
        return None


def resolve_keys(api_keys: dict | None = None) -> Keys:
    """Order: api_keys (config.keys names) > server.config.get_key > env (.env). Never logged."""
    load_env()
    k = api_keys or {}

    def pick(name: str, *envs: str) -> str | None:
        if name in k:  # an explicit value (even "") wins, so callers/tests can switch a provider off
            return _usable(k.get(name))
        return _shared(name) or next((v for v in (_usable(os.environ.get(e)) for e in envs) if v), None)

    return Keys(
        gemini=_no_cloud_gemini(pick("gemini", "GEMINI_API_KEY", "GOOGLE_API_KEY")),
        anthropic=pick("anthropic", "ANTHROPIC_API_KEY"),
        github=_usable(k.get("github")) or _usable(os.environ.get("GITHUB_TOKEN")),
    )


def _no_cloud_gemini(key: str | None) -> str | None:
    """None for the miyagi cloud's install token: the cloud lets Gemini watch lesson videos only, so the finder's
    Gemini (text scoring, the skim) stays off and Claude scores (sources.py). A Settings / .env key still works."""
    try:
        from server.config import is_cloud_token  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - the finder run on its own
        return key
    if is_cloud_token(key):
        return None
    return key


def _chain(var: str, default: str) -> list[str]:
    load_env()
    return [m.strip() for m in os.environ.get(var, default).split(",") if m.strip()]


def triage_models() -> list[str]:
    """Fast text models, in order. Deliberately NOT gemini-4-hydrogen / gemini-3.8-flash: those are
    server/lesson's models and a free-tier key has small per-model daily caps."""
    return _chain("FINDER_MODEL", "gemini-3.1-flash-lite,gemini-3.5-flash-lite")


def skim_models() -> list[str]:
    return _chain("FINDER_SKIM_MODEL", "gemini-3.1-flash-lite,gemini-3.5-flash-lite")


def skim_top() -> int:
    """How many top videos Gemini skims. Default 0 (off): Gemini is reserved for the lesson builder.
    FINDER_SKIM_TOP=3 turns it back on; FINDER_SKIMS=0/1 is an on/off alias (0 always wins)."""
    load_env()
    if os.environ.get("FINDER_SKIMS", "").strip() == "0":
        return 0
    try:
        n = int(os.environ.get("FINDER_SKIM_TOP", "") or 0)
    except ValueError:
        n = 0
    if n == 0 and os.environ.get("FINDER_SKIMS", "").strip() == "1":
        n = 3
    return max(0, n)


def video_reads() -> int:
    """How many top videos Claude takes a second look at, from their own text (full description, chapter titles,
    a transcript excerpt): the default replacement for the Gemini skim. FINDER_VIDEO_READS, default 3; 0 = off."""
    load_env()
    try:
        return max(0, int(os.environ.get("FINDER_VIDEO_READS", "3")))
    except ValueError:
        return 3


def gemini_fallback() -> bool:
    """Gemini scores rows only if Claude fails AND FINDER_GEMINI_FALLBACK=1 (default off, same reason)."""
    load_env()
    return os.environ.get("FINDER_GEMINI_FALLBACK", "0") == "1"


ALL_KINDS = ("video", "blog", "notebook", "repo", "paper")


def kinds() -> set[str]:
    """Which result kinds the finder searches for. Default: YouTube videos only (Michael: the list is
    videos; "Build a lesson from the internet" is a separate path). FINDER_KINDS=all brings back
    blogs, notebooks, repos and papers; a comma list (e.g. "video,repo") picks some."""
    load_env()
    raw = os.environ.get("FINDER_KINDS", "video").strip().lower()
    if raw in ("all", "*"):
        return set(ALL_KINDS)
    picked = {k.strip() for k in raw.split(",") if k.strip() in ALL_KINDS}
    return picked or {"video"}


def min_score() -> int:
    """Relevance floor: a row the model scored below this is never sent (FINDER_MIN_SCORE, default 40)."""
    load_env()
    try:
        return max(0, min(100, int(os.environ.get("FINDER_MIN_SCORE", "40"))))
    except ValueError:
        return 40


def long_video_s() -> float:
    """Same setting as server/lesson (progressive build above it): LESSON_LONG_VIDEO_S, default 30 min."""
    load_env()
    try:
        return float(os.environ.get("LESSON_LONG_VIDEO_S", 30 * 60))
    except ValueError:
        return 30 * 60


CACHE_DIR = ROOT / "demo" / "cache" / "search"
