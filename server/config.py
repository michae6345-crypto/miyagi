"""Shared key accessor for every engine module (bring-your-own-key).

The app sends `config.keys` on connect; the orchestrator stores them here (in memory only,
never logged). Modules read keys with `get_key("anthropic")` instead of os.environ, so the
app's keys win over .env:

    from server.config import get_key
    key = get_key("gemini")   # app key > env var > None

Names match `config.keys` in shared/contracts/events.ts.
"""

from __future__ import annotations

import os

KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "brightdata": "BRIGHTDATA_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "tigerUrl": "TIGER_DATABASE_URL",
}

_app_keys: dict[str, str] = {}


def usable(value: str | None) -> bool:
    """Non-empty and not a placeholder like `postgres://...`."""
    return bool(value) and "..." not in value  # type: ignore[operator]


def set_app_keys(keys: dict) -> None:
    """Store keys from the app (empty / placeholder values are ignored)."""
    for name in KEY_ENV:
        v = (keys.get(name) or "").strip()
        if usable(v):
            _app_keys[name] = v
        else:
            _app_keys.pop(name, None)


def get_key(name: str) -> str | None:
    """The app's key if it sent one, else the environment (.env), else None."""
    if name in _app_keys:
        return _app_keys[name]
    v = os.environ.get(KEY_ENV.get(name, name), "")
    return v if usable(v) else None


def key_source(name: str) -> str:
    """'ok' (from the app) | 'env' | 'missing' — the config.status value (never the key)."""
    if name in _app_keys:
        return "ok"
    return "env" if get_key(name) else "missing"
