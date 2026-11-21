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

The cloud URL is the proxy's API root, `https://<host>/v1` (not the bare host): the engine appends
`/anthropic` and `/gemini`, so the SDKs land on the proxy's `/v1/anthropic/v1/messages` and
`/v1/gemini/v1beta/models/{model}:generateContent` (claude/eng-proxy cloud/app.py). The app mints the
install token at `<host>/v1/register`. A bare host would 404 on every call.

The install token lives here in memory only. It is never written to os.environ (no ANTHROPIC_API_KEY,
GEMINI_API_KEY, MIYAGI_CLOUD_TOKEN or ANTHROPIC_BASE_URL export), so a learner's subprocess (their code,
pip, a kernel, VS Code terminals) cannot inherit a credential that bills miyagi; `safe_env()` strips the
rest. A non-cloud key (Settings or .env) always goes to https://api.anthropic.com: ANTHROPIC_BASE_URL
is ignored by every engine client.

Cost guards (BUILD-PLAN E4): `guard_model()` turns any Opus / Fable / Mythos choice into Sonnet
unless MIYAGI_ALLOW_OPUS=1 (and never through the cloud, which rejects them), and
`fallback_kwargs()` adds the server-side refusal fallback only in a form that cannot land on Opus.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

log = logging.getLogger("server.config")

KEY_ENV = {  # what the app may send in config.keys, and what config.status reports (ConfigStatus in events.ts)
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "brightdata": "BRIGHTDATA_API_KEY",  # retired: .env only, see RETIRED_KEYS
    "tigerUrl": "TIGER_DATABASE_URL",  # retired: always 'missing', see RETIRED_KEYS
    "elevenlabs": "ELEVENLABS_API_KEY",
    "miyagiToken": "MIYAGI_CLOUD_TOKEN",  # the app's anonymous install token for the miyagi cloud proxy
}
# Dropped vendors (DISTRIBUTION-PLAN, claude/eng-drop-vendors): miyagi no longer asks for Bright Data or Tiger
# Data. Both names stay in KEY_ENV only because config.status must still carry them (ConfigStatus requires
# `brightdata` and `tigerUrl` until the contract makes them optional). A value the app sends for either is
# ignored: never stored, never exported to os.environ.
# - Bright Data is an optional dev extra, read from .env only (BRIGHTDATA_API_KEY): the finder, the coach's web
#   lookups and the transcript fetch use it when it is set and skip it otherwise (no key = no call).
#   config.status.brightdata is 'env' or 'missing'.
# - Tiger Data is replaced by the local SQLite store (server/checks/tiger.py, `metrics_db_path()`); the engine's
#   writer no longer reads TIGER_DATABASE_URL, so config.status.tigerUrl is always 'missing'.
# Full code removal is ROADMAP 3.6.
RETIRED_KEYS = ("brightdata", "tigerUrl")
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
    before = cloud_token()
    for name in KEY_ENV:
        if name in RETIRED_KEYS:  # the app can no longer supply these (Bright Data is .env only, Tiger is gone)
            _app_keys.pop(name, None)
            continue
        v = (keys.get(name) or "").strip()
        if usable(v):
            _app_keys[name] = v
        else:
            _app_keys.pop(name, None)
    raw = keys.get("miyagiCloud")
    _app_cloud_url = _clean_url(raw if isinstance(raw, str) else None)
    if raw and not _app_cloud_url:
        log.warning("config.keys.miyagiCloud is not an https URL; the cloud is off")
    if cloud_token() != before:  # a new install token (or none): whatever the proxy said about the old one is moot
        _clear_verdict()


def _env_key(name: str) -> str | None:
    v = os.environ.get(KEY_ENV.get(name) or name, "")
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
    """config.status.cloud: 'ok' (URL and token) | 'missing' (URL but no token yet) | 'off', or what the proxy last
    said about the current token (cloud_verdict): 'unauthorized' (unknown or disabled install) | 'paused' | 'quota'."""
    if not cloud_url():
        return "off"
    if not cloud_token():
        return "missing"
    v = cloud_verdict()
    return v["state"] if v else "ok"


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
    """'ok' (from the app) | 'cloud' (the miyagi cloud) | 'env' | 'missing': the config.status value (never the key).
    tigerUrl is always 'missing': the engine no longer reads TIGER_DATABASE_URL (the local store replaced Tiger)."""
    if name == "tigerUrl":
        return "missing"
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
    # an explicit base URL: a Settings or .env key always goes to api.anthropic.com and never follows
    # ANTHROPIC_BASE_URL (which the engine ignores, for 'env' mode too) to the proxy or anywhere else
    return {"api_key": key, "base_url": ANTHROPIC_DIRECT_URL}


def gemini_http_options(role: str | None = None, *, key: str | None = None, **extra):
    """google.genai HttpOptions pointing at the proxy for a cloud token, else None (plus `extra`
    options such as retry_options, which are kept either way)."""
    if key is None:
        key = get_key("gemini")
    if is_cloud_token(key):
        from google.genai import types

        # v1beta: the proxy serves /v1/gemini/v1beta/models/{m} only, and google-genai 3.x defaults to v1
        extra.setdefault("api_version", "v1beta")
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


def _error_body(exc: BaseException) -> dict:
    """The parsed error JSON: anthropic's APIStatusError.body, or google.genai's APIError.details."""
    for attr in ("body", "details"):
        b = getattr(exc, attr, None)
        if isinstance(b, list) and len(b) == 1:
            b = b[0]
        if isinstance(b, dict):
            return b
    return {}


def _proxy_shaped(err: dict, status: int | None) -> bool:
    """The proxy's own error() shape: {type, status: TYPE.upper(), code: <http status>}. Anthropic's
    errors (forwarded unchanged) carry no code/status; Google's carry no type."""
    typ = err.get("type")
    return isinstance(typ, str) and err.get("status") == typ.upper() and err.get("code") == status


def cloud_error(exc: BaseException, provider: str = "anthropic") -> str | None:
    """'miyagi_paused' | 'miyagi_quota' | 'miyagi_auth' when `exc` (an SDK status error from a `provider`
    call) is the miyagi cloud turning the call away, else None. Look the card text up in CLOUD_ERRORS.

    Read against claude/eng-proxy cloud/app.py: the kill switch is 503 `proxy_disabled` (paused); a disabled
    install is 403 `permission_error` and an unknown token 401 (auth, in cloud mode only); the quota stop is
    429 `rate_limit_error` in the proxy's own shape (quota, so nobody retries it; an upstream 429 forwarded
    as is stays an ordinary rate limit). `miyagi_paused` / `miyagi_quota` / `miyagi_auth` as the type are
    read too (Core request 6).

    Side effect (install token self-heal): in cloud mode the verdict is remembered for the current install token
    (cloud_status() reports it) and the listeners from on_cloud_verdict() hear about each new one."""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    code = _classify_cloud(exc, provider, status)
    if code:
        try:
            _record_verdict(code, status, exc, provider)
        except Exception:  # classifying a refusal never raises
            log.exception("could not record the miyagi cloud verdict")
    return code


def _classify_cloud(exc: BaseException, provider: str, status) -> str | None:
    body = _error_body(exc)
    err = body.get("error") if isinstance(body.get("error"), dict) else {}
    typ = body.get("type")
    if typ in (None, "error"):
        typ = err.get("type")
    if typ in CLOUD_ERRORS:
        return typ
    text = str(exc)
    if typ == "proxy_disabled" or (status == 503 and ("miyagi_paused" in text or "proxy_disabled" in text)):
        return "miyagi_paused"
    if status == 429 and "miyagi_quota" in text:
        return "miyagi_quota"
    if mode(provider) != "cloud":  # a direct key: a 401/403/429 is the provider's, not the cloud's
        return None
    if status == 401 or (status == 403 and typ == "permission_error"):
        return "miyagi_auth"
    if status == 429 and typ == "rate_limit_error" and _proxy_shaped(err, 429):
        return "miyagi_quota"
    return None


# ------------------------------------------------------------------ what the proxy said about this install token
#
# cloud_error() remembers the proxy's refusal for the token in use, so config.status.cloud can say so and the app can
# heal: a 401 means the proxy does not know the token (its database was reset): the orchestrator sends the app
# `cloud.token_invalid` once per token and the app mints a new one. A 403 means an operator disabled this install:
# no token_invalid (a new token would dodge the switch), config.status.cloud is 'unauthorized'. Paused and over quota
# are transient: they expire on their own (the next refused call sets them again). A new token from the app
# (set_app_keys) clears the verdict. Only a short sha256 of the token is kept here; the token is never logged.

PAUSED_TTL_S = 120.0
CloudListener = Callable[[dict], None]

_verdict_lock = threading.Lock()
_verdict: dict | None = None  # {"token": token id, "state": CloudState, "reason": str, "until": monotonic | None}
_announced: set[str] = set()  # token ids a cloud.token_invalid went out for (once per token)
_listeners: list[CloudListener] = []


def _token_id(token: str | None) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()[:16]


def _clear_verdict() -> None:
    global _verdict
    with _verdict_lock:
        _verdict = None


def on_cloud_verdict(fn: CloudListener) -> Callable[[], None]:
    """Call `fn(event)` on each new verdict about the current token, from whatever thread made the refused call.
    event: {"state": 'unauthorized' | 'paused' | 'quota', "reason": 'unknown_token' | 'disabled' | 'paused' | 'quota',
    "token_invalid": True the first time this token is reported unknown, "ttl": seconds until it lapses or None}.
    Returns the function that removes `fn`."""
    _listeners.append(fn)

    def off() -> None:
        if fn in _listeners:
            _listeners.remove(fn)

    return off


def cloud_verdict() -> dict | None:
    """The live verdict about the current install token ({state, reason}), or None."""
    with _verdict_lock:
        v = _verdict
    if v is None or v["token"] != _token_id(cloud_token()):
        return None
    if v["until"] is not None and time.monotonic() >= v["until"]:
        return None
    return {"state": v["state"], "reason": v["reason"]}


def token_invalid_pending() -> bool:
    """The proxy does not know the current token (a 401): the app should mint a new one."""
    v = cloud_verdict()
    return bool(v) and v["reason"] == "unknown_token"


def _seconds_to_utc_midnight() -> float:
    now = datetime.now(UTC)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60.0, (nxt - now).total_seconds())


def _exc_token(exc: BaseException) -> str | None:
    """The key the refused request carried (x-api-key / x-goog-api-key / Bearer), when the SDK error keeps the
    request; else None. Never logged: compared with the current token only."""
    response = getattr(exc, "response", None)
    for req in (getattr(exc, "request", None), getattr(response, "request", None) if response is not None else None):
        h = getattr(req, "headers", None)
        if h is None or not hasattr(h, "get"):
            continue
        v = h.get("x-api-key") or h.get("x-goog-api-key") or ""
        auth = h.get("authorization") or ""
        if not v and isinstance(auth, str) and auth[:7].lower() == "bearer ":
            v = auth[7:]
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _record_verdict(code: str, status, exc: BaseException, provider: str) -> None:
    global _verdict
    if mode(provider) != "cloud":
        return
    token = cloud_token()
    used = _exc_token(exc)
    if used is not None and used != token:  # a call made with an older token ended after the app sent a new one
        return
    if code == "miyagi_auth":
        state, reason, ttl = "unauthorized", ("unknown_token" if status == 401 else "disabled"), None
    elif code == "miyagi_paused":
        state, reason, ttl = "paused", "paused", PAUSED_TTL_S
    elif code == "miyagi_quota":
        state, reason, ttl = "quota", "quota", _seconds_to_utc_midnight()
    else:
        return
    tid = _token_id(token)
    with _verdict_lock:
        live = _verdict is not None and _verdict["token"] == tid and (
            _verdict["until"] is None or time.monotonic() < _verdict["until"])
        if live and _verdict["reason"] == reason:  # type: ignore[index]
            return  # already known: one event per verdict, not one per refused call
        _verdict = {"token": tid, "state": state, "reason": reason,
                    "until": None if ttl is None else time.monotonic() + ttl}
        first_invalid = reason == "unknown_token" and tid not in _announced
        if first_invalid:
            _announced.add(tid)
    log.warning("miyagi cloud: %s (config.status.cloud=%s)", reason, state)
    event = {"state": state, "reason": reason, "token_invalid": first_invalid, "ttl": ttl}
    for fn in [*_listeners]:
        try:
            fn(event)
        except Exception:  # a listener never breaks the caller's error handling
            log.exception("cloud verdict listener failed")


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
    every provider key, the cloud token and URL and any Bright Data / Tiger value removed, then `extra` added."""
    env = dict(os.environ if base is None else base)
    secret = set(KEY_ENV.values()) | {
        CLOUD_URL_ENV, "TIGER_DATABASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "GOOGLE_API_KEY", "ADMIN_PASSWORD"}
    for var in list(env):
        if var in secret or var.upper().startswith(_SECRET_PREFIXES):
            env.pop(var, None)
    env.update(extra)
    return env
