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
    brightdata: str | None
    serp_zone: str
    unlocker_zone: str
    github: str | None

    @property
    def has_brightdata(self) -> bool:
        return bool(self.brightdata)


def resolve_keys(api_keys: dict | None = None) -> Keys:
    """api_keys uses the config.keys names ({"gemini": ..., "brightdata": ...}); never logged."""
    load_env()
    k = api_keys or {}
    return Keys(
        gemini=_usable(k.get("gemini")) or _usable(os.environ.get("GEMINI_API_KEY")) or _usable(os.environ.get("GOOGLE_API_KEY")),
        brightdata=_usable(k.get("brightdata")) or _usable(os.environ.get("BRIGHTDATA_API_KEY")),
        serp_zone=_usable(os.environ.get("BRIGHTDATA_SERP_ZONE")) or "serp_api1",
        unlocker_zone=_usable(os.environ.get("BRIGHTDATA_UNLOCKER_ZONE")) or "web_unlocker1",
        github=_usable(k.get("github")) or _usable(os.environ.get("GITHUB_TOKEN")),
    )


def _chain(var: str, default: str) -> list[str]:
    load_env()
    return [m.strip() for m in os.environ.get(var, default).split(",") if m.strip()]


def triage_models() -> list[str]:
    """Fast text models, in order. Deliberately NOT gemini-4-hydrogen / gemini-3.8-flash: those are
    server/lesson's models and a free-tier key has small per-model daily caps."""
    return _chain("FINDER_MODEL", "gemini-3.1-flash-lite,gemini-3.5-flash-lite")


def skim_models() -> list[str]:
    return _chain("FINDER_SKIM_MODEL", "gemini-3.1-flash-lite,gemini-3.5-flash-lite")


def grounding_model() -> str:
    load_env()
    return os.environ.get("FINDER_GROUNDING_MODEL", "gemini-3.1-flash-lite")


CACHE_DIR = ROOT / "demo" / "cache" / "search"
