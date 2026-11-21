"""Shared key accessor for every engine module (bring-your-own-key, or the miyagi cloud).

The app sends `config.keys` on connect; the orchestrator stores them here (in memory only,
never logged). Modules read keys with `get_key("anthropic")` instead of os.environ, so the
app's keys win over .env:

    from server.config import get_key
    key = get_key("gemini")   # app key > cloud token > env var > None

Names match `config.keys` in shared/contracts/events.ts.

miyagi cloud (DISTRIBUTION-PLAN section 1). When the app sends `miyagiCloud` (the proxy URL) and
`miyagiToken` (the anonymous install token), or the engine runs with MIYAGI_CLOUD_URL and
MIYAGI_CLOUD_TOKEN, Claude and Gemini calls go through the proxy with the token as the provider
key. A key the learner typed in Settings (bring-your-own-key) always wins for its provider and
always goes straight to that provider, never to the proxy. Build every client from
`anthropic_kwargs()` / `gemini_kwargs()` so this holds everywhere.

Cost guards (BUILD-PLAN E4): `guard_model()` turns any Opus / Fable / Mythos choice into Sonnet
unless MIYAGI_ALLOW_OPUS=1 (and never through the cloud, which rejects them), and
`fallback_kwargs()` adds the server-side refusal fallback only in a form that cannot land on Opus.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit

log = logging.getLogger("server.config")

KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "brightdata": "BRIGHTDATA_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "tigerUrl": "TIGER_DATABASE_URL",
    "miyagiToken": "MIYAGI_CLOUD_TOKEN",  # the app's anonymous install token for the miyagi cloud proxy
}
CLOUD_URL_ENV = "MIYAGI_CLOUD_URL"  # config.keys.miyagiCloud wins over it
CLOUD_PROVIDERS = ("anthropic", "gemini")  # what the proxy forwards (Gemini: watching YouTube video only)
ANTHROPIC_DIRECT_URL = "https://api.anthropic.com"

_app_keys: dict[str, str] = {}
_app_cloud_url: str | None = None


def usable(value: str | None) -> bool:
    """Non-empty and not a placeholder like `postgres://...`."""
    return bool(value) and "..." not in value  # type: ignore[operator]


def _clean_url(value: str | None) -> str | None:
    """An http(s) URL without a trailing slash, else None. Plain http only for this Mac (local proxy runs)."""
    v = (value or "").strip().rstrip("/")
    if not usable(v):
        return None
    try:
        u = urlsplit(v)
    except ValueError:
        return None
    if not u.hostname or u.query or u.fragment:
        return None
    if u.scheme == "https" or (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1")):
        return v
    return None


def set_app_keys(keys: dict) -> None:
    """Store keys from the app (empty / placeholder values are ignored), plus the cloud URL."""
    global _app_cloud_url
    for name in KEY_ENV:
        v = (keys.get(name) or "").strip()
        if usable(v):
            _app_keys[name] = v
        else:
            _app_keys.pop(name, None)
    raw = keys.get("miyagiCloud")
    _app_cloud_url = _clean_url(raw if isinstance(raw, str) else None)
    if raw and not _app_cloud_url:
        log.warning("config.keys.miyagiCloud is not an https URL; the cloud is off")


def _env_key(name: str) -> str | None:
    v = os.environ.get(KEY_ENV.get(name, name), "")
    return v if usable(v) else None


# ------------------------------------------------------------------ the miyagi cloud


def cloud_url() -> str | None:
    """The proxy's base URL: config.keys.miyagiCloud, else MIYAGI_CLOUD_URL, else None."""
    return _app_cloud_url or _clean_url(os.environ.get(CLOUD_URL_ENV))


def cloud_token() -> str | None:
    return _app_keys.get("miyagiToken") or _env_key("miyagiToken")


def cloud_on() -> bool:
    """Both the proxy URL and an install token are known."""
    return bool(cloud_url() and cloud_token())


def mode(provider: str) -> str:
    """How calls to `provider` are made: 'byok' (a key from the app's Settings, sent direct) | 'cloud'
    (the install token, through the proxy) | 'env' (a key from .env, sent direct) | 'missing'."""
    if provider in _app_keys:
        return "byok"
    if provider in CLOUD_PROVIDERS and cloud_on():
        return "cloud"
    return "env" if _env_key(provider) else "missing"


def cloud_status() -> str:
    """config.status.cloud: 'ok' (URL and token) | 'missing' (URL but no token yet) | 'off'."""
    if not cloud_url():
        return "off"
    return "ok" if cloud_token() else "missing"


def get_key(name: str) -> str | None:
    """The app's key if it sent one, else the cloud token (anthropic / gemini in cloud mode), else
    the environment (.env), else None. Pass the result to `anthropic_kwargs(key=...)` /
    `gemini_kwargs(key=...)`, which send a cloud token to the proxy and any other key direct."""
    if name in _app_keys:
        return _app_keys[name]
    if name in CLOUD_PROVIDERS and cloud_on():
        return cloud_token()
    return _env_key(name)


def is_cloud_token(key: str | None) -> bool:
    return bool(key) and cloud_on() and key == cloud_token()


def key_source(name: str) -> str:
    """'ok' (from the app) | 'cloud' (the miyagi cloud) | 'env' | 'missing': the config.status value (never the key)."""
    m = mode(name) if name in CLOUD_PROVIDERS else ("byok" if name in _app_keys else ("env" if _env_key(name) else "missing"))
    return {"byok": "ok"}.get(m, m)


def has_anthropic() -> bool:
    return mode("anthropic") != "missing"


def anthropic_kwargs(role: str | None = None, *, key: str | None = None) -> dict:
    """Constructor kwargs for anthropic.Anthropic / AsyncAnthropic: `{api_key, base_url[, default_headers]}`.

    `key` given: that key (a cloud token goes to the proxy, anything else straight to Anthropic).
    `key` None: the current mode (bring-your-own-key > cloud > .env); {} when there is no credential,
    so the SDK falls back to its own environment lookup. `role` (coach, scene, lesson, finder,
    diagram, workspace) rides along as `x-miyagi-role` on cloud calls for the proxy's usage log."""
    if key is None:
        m = mode("anthropic")
        if m == "missing":
            return {}
        key = cloud_token() if m == "cloud" else get_key("anthropic")
    if is_cloud_token(key):
        kw: dict = {"api_key": key, "base_url": f"{cloud_url()}/anthropic"}
        if role:
            kw["default_headers"] = {"x-miyagi-role": role}
        return kw
    # an explicit base URL: a direct key must never follow ANTHROPIC_BASE_URL to the proxy
    return {"api_key": key, "base_url": ANTHROPIC_DIRECT_URL}


def gemini_http_options(role: str | None = None, *, key: str | None = None, **extra):
    """google.genai HttpOptions pointing at the proxy for a cloud token, else None (plus `extra`
    options such as retry_options, which are kept either way)."""
    if key is None:
        key = get_key("gemini")
    if is_cloud_token(key):
        from google.genai import types

        return types.HttpOptions(base_url=f"{cloud_url()}/gemini", headers={"x-miyagi-role": role} if role else None,
                                 **extra)
    if extra:
        from google.genai import types

        return types.HttpOptions(**extra)
    return None


def gemini_kwargs(role: str | None = None, *, key: str | None = None, **http_extra) -> dict:
    """Constructor kwargs for google.genai.Client: `{api_key[, http_options]}`, or {} with no key.
    Through the cloud only video calls (a YouTube fileData part) are allowed; text calls get 403."""
    if key is None:
        key = get_key("gemini")
    if not key:
        return {}
    kw: dict = {"api_key": key}
    opts = gemini_http_options(role, key=key, **http_extra)
    if opts is not None:
        kw["http_options"] = opts
    return kw


def gemini_text_ok() -> bool:
    """May Gemini take a text-only call (finder scoring, the adapt pass)? Not through the cloud."""
    return mode("gemini") in ("byok", "env")


CLOUD_ERRORS = {  # plain card copy for the proxy's own refusals (no em dashes: UI copy)
    "miyagi_paused": "miyagi is paused for a moment. Try again in a few minutes.",
    "miyagi_quota": "You've reached today's limit. It resets tomorrow.",
    "miyagi_auth": "miyagi couldn't verify this Mac. Quit and reopen miyagi, then try again.",
}


def cloud_error(exc: BaseException) -> str | None:
    """'miyagi_paused' | 'miyagi_quota' | 'miyagi_auth' when `exc` (an SDK status error) is the proxy
    turning a call away, else None. Look the card text up in CLOUD_ERRORS."""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    body = getattr(exc, "body", None)
    typ = None
    if isinstance(body, dict):
        typ = body.get("type")
        err = body.get("error")
        if typ in (None, "error") and isinstance(err, dict):
            typ = err.get("type")
    if typ in ("miyagi_paused", "miyagi_quota"):
        return typ
    if status == 503 and "miyagi_paused" in str(exc):
        return "miyagi_paused"
    if status == 429 and "miyagi_quota" in str(exc):
        return "miyagi_quota"
    if status == 401 and cloud_on() and mode("anthropic") == "cloud":
        return "miyagi_auth"
    return None


# ------------------------------------------------------------------ cost guards (E4)

SONNET = "claude-sonnet-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
_PREMIUM = ("opus", "fable", "mythos")


def is_premium(model: str | None) -> bool:
    m = (model or "").lower()
    return any(p in m for p in _PREMIUM)


def opus_allowed() -> bool:
    """Opus (and Fable / Mythos) is opt-in only: MIYAGI_ALLOW_OPUS=1, and never through the cloud."""
    return os.environ.get("MIYAGI_ALLOW_OPUS", "0") == "1" and mode("anthropic") != "cloud"


def guard_model(model: str | None, default: str = SONNET, *, allow: bool | None = None) -> str:
    """`model`, unless it is Opus / Fable / Mythos and that is not allowed: then `default` (Sonnet).
    `allow` overrides the MIYAGI_ALLOW_OPUS check (lesson/claude.py keeps LESSON_ALLOW_OPUS); the
    cloud never gets one either way."""
    m = (model or "").strip() or default
    if not is_premium(m):
        return m
    ok = opus_allowed() if allow is None else (allow and mode("anthropic") != "cloud")
    if ok:
        return m
    if m not in _warned:
        _warned.add(m)
        log.warning("%s needs MIYAGI_ALLOW_OPUS=1 (and no miyagi cloud); using %s", m, default)
    return default


_warned: set[str] = set()


def fallback_kwargs(model: str) -> dict:
    """The server-side refusal fallback for `model`, only where it cannot reach an Opus nobody opted into.

    Sonnet 5.5: "default" (the API's documented targets for it are Claude Sonnet 5 only: cyber and frontier_llm
    declines rerun there, the rest stay refusals). An opted-in Opus / Fable: "default" (its targets are Opus 5 /
    Opus 4.8). A premium model that is not allowed, Haiku, anything else: none. The miyagi cloud prices by the
    response's model and strips `fallbacks` if an Opus id ever comes back. Add the result to a
    `client.beta.messages` call; {} means use `client.messages`."""
    m = (model or "").lower()
    if m.startswith(SONNET) or (is_premium(m) and opus_allowed()):
        return {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    return {}


# ------------------------------------------------------------------ learner subprocesses

_SECRET_PREFIXES = ("ANTHROPIC_", "GEMINI_", "GOOGLE_API", "GOOGLE_GENAI", "BRIGHTDATA_", "ELEVENLABS_", "TIGER_",
                    "MIYAGI_CLOUD")


def safe_env(base: dict | None = None, **extra: str) -> dict[str, str]:
    """A copy of the environment (or `base`) for a learner's subprocess (their code, pip, a kernel, VS Code):
    every provider key, the cloud token and URL and the Tiger URL removed, then `extra` added."""
    env = dict(os.environ if base is None else base)
    secret = set(KEY_ENV.values()) | {CLOUD_URL_ENV, "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "GOOGLE_API_KEY",
                                      "ADMIN_PASSWORD"}
    for var in list(env):
        if var in secret or var.upper().startswith(_SECRET_PREFIXES):
            env.pop(var, None)
    env.update(extra)
    return env
