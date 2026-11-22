"""miyagi-cloud: the API key proxy for the Miyagi desktop tutor.

Every user's AI calls come here with an anonymous install token. We hold the Anthropic and
Gemini keys, enforce model allowlists, request-body allowlists, rate limits and caps, forward the
call, and count usage per token.

Logs carry method, path, status, latency, model, token counts and the token-hash prefix only:
never bodies, prompts, screenshots, tokens, keys, account ids or IP addresses.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import ipaddress
import json
import logging
import math
import os
import re
import secrets
import shutil
import sys
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, quote, urlsplit

import anyio
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.datastructures import Headers

from store import MIN_RETAIN_DAYS, PLANS, PREFIX_LEN, Store, lesson_hash, open_store, this_month, today

VERSION = "0.2.0"
# Overridable only so local tests can point at a mock upstream.
ANTHROPIC_URL = os.environ.get("UPSTREAM_ANTHROPIC_URL", "https://api.anthropic.com/v1/messages")
GEMINI_URL = os.environ.get("UPSTREAM_GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stdout)
log = logging.getLogger("miyagi.cloud")
logging.getLogger("uvicorn.access").disabled = True  # it would log query strings; we log our own line
logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx logs full upstream URLs at INFO


# --------------------------------------------------------------------------- settings

def _env_list(name: str, default: str) -> list[str]:
    return [m.strip() for m in os.environ.get(name, default).split(",") if m.strip()]


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def _now() -> float:
    """Wall clock for the rate limiter (tests replace it to move time)."""
    return time.time()


# Admin token (A22). A weak token never crashes the process (production would go down on merge): it turns /admin off.
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
ADMIN_TOKEN_DENYLIST = frozenset({"test", "admin", "changeme", "password", "admin-test", "test-admin", "secret", "letmein",
                                  "default", "miyagi", "adminadmin", "admin123", "password123", "changeme123", "admintoken",
                                  "admin_token", "miyagi-admin", "qwerty", "123456"})


def admin_token_problem(token: str) -> str | None:
    """Why `token` is too weak to guard /admin, or None when it is strong enough."""
    if len(token) < 32:
        return "shorter than 32 characters"
    if token.strip().lower() in ADMIN_TOKEN_DENYLIST:
        return "a well-known value"
    if len(set(token)) < 12:
        return "fewer than 12 distinct characters"
    return None


ADMIN_PROBLEM = admin_token_problem(ADMIN_TOKEN)
ADMIN_ENABLED = ADMIN_PROBLEM is None
if not ADMIN_ENABLED:
    log.error("ADMIN_TOKEN is %s: every /admin route answers 503 until it is replaced with "
              "python -c 'import secrets;print(secrets.token_urlsafe(32))'", ADMIN_PROBLEM)

def _env_key(name: str) -> str:
    """An upstream API key from the environment, trimmed. A pasted key often ends in a newline or space, and httpx
    then refuses to send the header at all (h11 LocalProtocolError, every call a 502). Logs only that it was trimmed."""
    raw = os.environ.get(name, "")
    key = raw.strip().strip('"').strip("'").strip()
    if key != raw:
        log.warning("%s had surrounding whitespace or quotes; trimmed (%d chars removed)", name, len(raw) - len(key))
    return key


ANTHROPIC_KEY = _env_key("ANTHROPIC_API_KEY")
GEMINI_KEY = _env_key("GEMINI_API_KEY")
PROXY_ENABLED = _env_bool("PROXY_ENABLED", True)  # the deploy-time switch; POST /admin/proxy/pause is the runtime one
ALLOWED_ANTHROPIC = _env_list("ALLOWED_ANTHROPIC_MODELS", "claude-sonnet-5-5,claude-haiku-5-5")
# Gemini is off by default: the founders' D1 decision is Claude only at launch (Gemini's terms are 18+, miyagi's gate
# is 13+). An empty list (unset, empty, or "none") makes every /v1/gemini call a 403 gemini_disabled. It stays
# configurable so Gemini can come back, for example through Vertex AI once an adult-held account exists: set
# ALLOWED_GEMINI_MODELS to a comma-separated list (and GEMINI_API_KEY) to turn it on again.
ALLOWED_GEMINI = [m for m in _env_list("ALLOWED_GEMINI_MODELS", "") if m.lower() not in ("none", "off")]
# Upper bound on Anthropic max_tokens (thinking included). The lesson builder asks for 32000 with adaptive thinking
# (server/lesson/claude.py), so a lower cap cuts its replies short. Spend is bounded by the dollar caps below, which
# reserve max_tokens at the output price while a call is in flight; a per-call cap never bounded abuse on its own.
MAX_TOKENS_CAP = _env_int("MAX_TOKENS_CAP", 32_000)
ALLOW_FAST_MODE = _env_bool("ALLOW_FAST_MODE", False)  # speed:"fast" bills 2x
ANTHROPIC_VERSION = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")
# anthropic-beta values forwarded; anything else is refused. Default: the one the engine sends (the refusal fallback).
ANTHROPIC_BETAS = frozenset(_env_list("ANTHROPIC_BETAS", "server-side-fallback-2026-07-01"))
# Anthropic server tools allowed (base names): empty = none. "web_search,web_fetch" lets the engine's finder and
# text lessons search; every use is counted at SERVER_TOOL_USD and max_uses is capped at SERVER_TOOL_MAX_USES.
ANTHROPIC_SERVER_TOOLS = frozenset(t for t in _env_list("ANTHROPIC_SERVER_TOOLS", "") if t in ("web_search", "web_fetch"))
SERVER_TOOL_MAX_USES = _env_int("SERVER_TOOL_MAX_USES", 5)
# web_fetch always goes upstream with a max_content_tokens (a fetched page is billed as input), at most this many.
WEB_FETCH_MAX_CONTENT_TOKENS = max(_env_int("WEB_FETCH_MAX_CONTENT_TOKENS", 20_000), 1)
# On Gemini 2.5 and later, thinking tokens count against maxOutputTokens. The engine sends neither maxOutputTokens
# nor a thinkingConfig (lesson/gemini.py _generate_json, finder/gemini.py), so dynamic thinking (up to 24576 tokens on
# Flash) and the JSON answer share this one clamp: 32768 leaves the answer at least 8192 tokens. No thinkingBudget is
# inserted (Gemini 3 prefers thinkingLevel); the reservation holds the whole clamp at the output price.
GEMINI_MAX_OUTPUT_TOKENS = _env_int("GEMINI_MAX_OUTPUT_TOKENS", 32_768)
GEMINI_MAX_THINKING_TOKENS = _env_int("GEMINI_MAX_THINKING_TOKENS", 2048)  # clamp on a thinkingBudget a client sends
# Reservation estimates (the cost held while a call is in flight; settled to the real usage when it ends).
# Input tokens held for a YouTube fileData part without both offsets (about 30 minutes at the engine's 0.5 fps).
GEMINI_VIDEO_RESERVE_TOKENS = _env_int("GEMINI_VIDEO_RESERVE_TOKENS", 300_000)
# videoMetadata.fps is clamped to this before forwarding (the engine samples at 0.5 fps, and 2 fps for a step's clip).
GEMINI_MAX_FPS = _env_float("GEMINI_MAX_FPS", 2.0)
# The most input one Gemini call can bill (the model's context window): the cap on any input reservation.
GEMINI_CONTEXT_TOKENS = _env_int("GEMINI_CONTEXT_TOKENS", 1_048_576)
IMAGE_RESERVE_TOKENS = 5_000  # one base64 image (a screenshot is ~1.6k tokens on Claude; held high on purpose)
WEB_SEARCH_RESERVE_TOKENS = 8_000  # the result blocks one web search adds to the input
CHARS_PER_TOKEN = 3  # the input estimate: forwarded JSON bytes / 3 (real text is ~4 per token: errs high)
MAX_BODY = int(_env_float("MAX_BODY_MB", 2) * 1024 * 1024)
# The engine sends Gemini a YouTube fileData part and a prompt (no inline video or screenshots): well under 1 MB.
MAX_GEMINI_BODY = int(_env_float("MAX_GEMINI_BODY_MB", 2) * 1024 * 1024)
# Request bodies of forwarded AI calls held in memory at once (from the moment their Content-Length is accepted until
# the call ends), in total and per client network (mint_bucket): past either, 429 concurrency_limit_error.
MAX_INFLIGHT_BODY = int(_env_float("MAX_INFLIGHT_BODY_MB", 64) * 1024 * 1024)
MAX_INFLIGHT_BODY_PER_IP = int(_env_float("MAX_INFLIGHT_BODY_PER_IP_MB", 16) * 1024 * 1024)
# JSON shape bounds, checked while parsing and before anything is copied (a body of a million empty objects is 400,
# not a gigabyte of dicts). The engine's largest bodies hold a few hundred objects.
JSON_MAX_OBJECTS = _env_int("JSON_MAX_OBJECTS", 50_000)
ANTHROPIC_MAX_MESSAGES = 1000
ANTHROPIC_MAX_BLOCKS = 4000  # content blocks in every message and the system prompt together (top level)
GEMINI_MAX_CONTENTS = 500
GEMINI_MAX_PARTS = 2000  # in every content and the system instruction together
GEMINI_MAX_FUNCTIONS = 256  # functionDeclarations, every tool together
GEMINI_MAX_SAFETY = 32
PROXY_HOPS = _env_int("TRUSTED_PROXY_HOPS", 1)  # Render's load balancer appends the client IP
CLIENT_IP_HEADER = os.environ.get("CLIENT_IP_HEADER", "").strip().lower()  # e.g. cf-connecting-ip; used only when set

# Rate limits (Michael's ask): per process and per instance, in memory. See class RateLimit.
RATE_LIMIT_ENABLED = _env_bool("RATE_LIMIT_ENABLED", True)
RATE_LIMIT_PER_IP_PER_HOUR = _env_int("RATE_LIMIT_PER_IP_PER_HOUR", 100)
# Per install token: above a normal lesson's busiest hour (scene looks alone are up to 720 an hour, plus the judge,
# screen picks, coach cards and events). An abuse brake only: the dollar caps bound spend.
RATE_LIMIT_PER_TOKEN_PER_HOUR = _env_int("RATE_LIMIT_PER_TOKEN_PER_HOUR", 2400)
ADMIN_RATE_LIMIT_PER_IP_PER_HOUR = _env_int("ADMIN_RATE_LIMIT_PER_IP_PER_HOUR", 20)
ADMIN_LOCKOUT_FAILURES = _env_int("ADMIN_LOCKOUT_FAILURES", 5)
RATE_LIMIT_MAX_KEYS = _env_int("RATE_LIMIT_MAX_KEYS", 200_000)
ADMIN_FAILURE_MAX_KEYS = _env_int("ADMIN_FAILURE_MAX_KEYS", 20_000)  # its own, smaller bound (a few MB at most)
# Install token minting (/v1/install, /v1/register), in SQLite so a deploy does not reset it. Schools share one IP.
REGISTER_PER_HOUR = _env_int("REGISTER_LIMIT_PER_HOUR", 20)
REGISTER_PER_DAY = _env_int("REGISTER_LIMIT_PER_DAY", 60)
GLOBAL_MINTS_WARN = _env_int("GLOBAL_MINTS_WARN_PER_HOUR", 500)
GLOBAL_MINTS_MAX = _env_int("GLOBAL_MINTS_PER_HOUR", 2000)
# Mints count per network: IPv4 the address, IPv6 this prefix (ISPs hand one home a /56 or a /48, not one /64).
MINT_IPV6_PREFIX = min(max(_env_int("MINT_IPV6_PREFIX", 48), 16), 64)
# Concurrency (A23): forwarded AI calls in flight. The engine alone runs up to ~10 at once (README, Calls in flight).
PER_TOKEN_INFLIGHT = _env_int("PER_TOKEN_INFLIGHT", 10)
GLOBAL_INFLIGHT = _env_int("GLOBAL_INFLIGHT", 80)
# A request body must arrive within this many seconds (408 after), so slow uploads cannot hold slots or memory.
BODY_READ_TIMEOUT_S = _env_float("BODY_READ_TIMEOUT_S", 20)

# Caps (A01, R01). Every cap keys on the install token or the linked user, in dollars counted on the server from the
# usage table (estimated cost, in-flight reservations included). The client-set x-miyagi-role header is a label for
# the log line and the usage view only: no cap reads it. 0 turns a cap off. "pro" installs skip the per-install caps.
FREE_LESSON_BUILDS_PER_MONTH = _env_int("FREE_LESSON_BUILDS_PER_MONTH", 3)  # new videos; cache hits are free
# Anonymous (unlinked) installs, per install and UTC day: about 3x one lesson (D13; Area C estimates ~$0.50), and
# above one build's peak reservation (the builder runs up to 4 Claude calls at once, each holding max_tokens at the
# output price: about $0.35 for a 32000-token Sonnet call). Set it from a measured lesson.
FREE_DAILY_USD = _env_float("FREE_DAILY_USD", 2.00)
# Linked installs: per Supabase user, every install of theirs together.
LINKED_DAILY_USD = _env_float("LINKED_DAILY_USD", 3.00)
# Request counts per UTC day (anonymous install / linked user): off by default. A count stops a normal lesson (scene
# looks alone are up to 720 Haiku calls an hour) while saying little about cost. Set only as an extra abuse brake,
# far above a lesson's calls.
FREE_DAILY_REQUESTS = _env_int("FREE_DAILY_REQUESTS", 0)
LINKED_DAILY_REQUESTS = _env_int("LINKED_DAILY_REQUESTS", 0)
# Tokens (input, cache reads and writes included, plus output) per linked user per UTC day, every install of theirs
# together: a backstop under LINKED_DAILY_USD in case a price in PRICES is wrong. A heavy day of lessons is a few
# million tokens (scene looks are ~2k-token Haiku calls, up to 720 an hour), so 20M only stops a runaway client.
# Counted from settled usage (not reserved): parallel calls can pass it by about PER_TOKEN_INFLIGHT calls. 0 = off.
LINKED_DAILY_TOKENS = _env_int("LINKED_DAILY_TOKENS", 20_000_000)
# Sign-in required for model calls (default off: the app offers "Continue without an account" and the privacy policy
# says signing in is optional). On: /v1/anthropic, /v1/gemini and POST /v1/lessons/{id}/build answer 401
# signin_required unless the install is linked to a Supabase user (POST /v1/link). Every other route stays open.
REQUIRE_SIGNIN = _env_bool("REQUIRE_SIGNIN", False)
LINK_MAX_INSTALLS_PER_USER = _env_int("LINK_MAX_INSTALLS_PER_USER", 10)
# Every anonymous install minted from one network (mint bucket: IPv4 address or IPv6 /48) together, per UTC day,
# so minting many installs cannot multiply FREE_DAILY_USD. 0 = off.
ANON_DAILY_USD_PER_NETWORK = _env_float("ANON_DAILY_USD_PER_NETWORK", 5.0)
# The global spend brake: an ABUSE BRAKE, OFF by default. When set (dollars), once the estimated spend of every
# install together reaches it in the current UTC day, every forwarded AI call, pro included, gets a 429 until UTC
# midnight. A fixed breaker trips on a good launch day and shuts everyone out (D13), so demand is handled by the
# daily new-install cap (NEW_INSTALLS_PER_DAY) and the alerts instead, and the hard stop is the provider's prepaid
# balance (R02). If you set it, set it far above ALERT_DAILY_USD. Unset, empty or 0: off.
DAILY_USD_CAP = _env_float("DAILY_USD_CAP", 0.0)
# New installs minted per UTC day, every network together (POST /v1/install and /v1/register; D13). Past it, new
# installs get 429 miyagi_full ("miyagi is full today, try tomorrow.") until UTC midnight; installs already minted
# keep working. Counted in SQLite, so restarts and deploys do not reset it. 0 = off.
NEW_INSTALLS_PER_DAY = _env_int("NEW_INSTALLS_PER_DAY", 500)

# Alerts (R01 step 6). ALERT_WEBHOOK_URL: a Discord or Slack incoming-webhook URL (a secret: never logged). Unset:
# no alerts. Each alert fires at most once per UTC day (alerts_sent in SQLite):
# - spend_50 / spend_80 / spend_100: today's estimated spend, every install together, passes 50 / 80 / 100% of
#   ALERT_DAILY_USD (the daily alert line, D13);
# - token:<id>: one install token spends more than ALERT_TOKEN_DAILY_USD today (default 3x FREE_DAILY_USD);
# - installs_full: NEW_INSTALLS_PER_DAY is reached; mints_high: GLOBAL_MINTS_WARN_PER_HOUR is reached in an hour;
# - brake: DAILY_USD_CAP (when set) is reached.
ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
ALERT_DAILY_USD = _env_float("ALERT_DAILY_USD", 25.0)
ALERT_TOKEN_DAILY_USD = _env_float("ALERT_TOKEN_DAILY_USD", 3 * FREE_DAILY_USD)
ALERT_LEVELS = (50, 80, 100)
ALERT_SPEND_CHECK_S = 10.0  # the spend alerts read the day's total at most this often per process
if ALERT_WEBHOOK_URL and not ALERT_WEBHOOK_URL.lower().startswith("https://"):
    log.error("ALERT_WEBHOOK_URL is not an https URL: alerts are off until it is fixed")
    ALERT_WEBHOOK_URL = ""
# The commit Render deployed (Render sets RENDER_GIT_COMMIT), shown on /healthz. Only a hex SHA is reported.
_commit = os.environ.get("RENDER_GIT_COMMIT", "").strip().lower()
DEPLOYED_COMMIT = _commit[:40] if re.fullmatch(r"[0-9a-f]{7,40}", _commit) else None

# Shared lesson cache (ROADMAP 3.1, A08)
MAX_LESSON_BYTES = int(_env_float("MAX_LESSON_KB", 128) * 1024)
# The draft schema versions accepted. No engine branch uploads lessons yet, so the one version in use is 1.
LESSON_SCHEMAS = frozenset(int(x) for x in _env_list("LESSON_SCHEMAS", "1") if x.isdigit())
LESSON_PUTS_PER_DAY = _env_int("LESSON_PUTS_PER_DAY", 10)
LESSON_AUTO_APPROVE_N = _env_int("LESSON_AUTO_APPROVE_N", 0)
LESSON_DISK_MAX_PCT = _env_float("LESSON_DISK_MAX_PCT", 85)
# Pending (unreviewed) uploads: dropped after this many days, and at most this many bytes in total and per uploader
# network (IPv4 /24, IPv6 /48), so minted tokens cannot fill the disk (and trip the gate above for honest uploads).
LESSON_PENDING_MAX_DAYS = _env_float("LESSON_PENDING_MAX_DAYS", 14)
LESSON_PENDING_MAX_BYTES = int(_env_float("LESSON_PENDING_MAX_MB", 128) * 1024 * 1024)
LESSON_PENDING_PER_NET_BYTES = int(_env_float("LESSON_PENDING_PER_NET_MB", 8) * 1024 * 1024)
# Retention (README, Data we keep): per-install detail rows older than this many days are folded into per-day totals
# or deleted, hourly and at startup (Store.prune). Never below MIN_RETAIN_DAYS (35): the monthly build cap needs them.
RETAIN_DAYS = max(_env_int("RETAIN_DAYS", MIN_RETAIN_DAYS), MIN_RETAIN_DAYS)
PRUNE_EVERY_S = max(_env_float("PRUNE_EVERY_S", 3600), 60)
# An anonymous install's mint network hash (the ANON_DAILY_USD_PER_NETWORK pool) is dropped this many days after it was
# minted. 0 (default): kept while the install stays anonymous (linking or deleting drops it). A short value lets an
# install minted that long ago escape its network's pool and be capped per install only (FREE_DAILY_USD).
MINT_NET_RETAIN_DAYS = max(_env_float("MINT_NET_RETAIN_DAYS", 0), 0)
TIMEOUT = httpx.Timeout(connect=10.0, read=_env_float("UPSTREAM_READ_TIMEOUT_S", 300), write=60.0, pool=10.0)

if not ANTHROPIC_KEY or (ALLOWED_GEMINI and not GEMINI_KEY):
    log.warning("missing upstream key(s): anthropic=%s gemini=%s (those routes return 503)",
                "set" if ANTHROPIC_KEY else "MISSING", "set" if GEMINI_KEY else "MISSING")
if not ALLOWED_GEMINI:
    log.info("Gemini is off (ALLOWED_GEMINI_MODELS is empty): /v1/gemini answers 403 gemini_disabled")

# USD per 1M tokens (input, output). Estimates for the caps and the admin view, not billing.
# Gemini rows are placeholders: check Google's pricing page. Override with PRICES_JSON='{"model": [in, out]}'.
PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "gemini-3.8-flash": (0.30, 2.50),
    "gemini-4-hydrogen": (1.25, 10.00),
}
PRICES.update({k: tuple(v) for k, v in json.loads(os.environ.get("PRICES_JSON", "{}")).items()})
DEFAULT_PRICE = (2.00, 10.00)
SERVER_TOOL_USD = 0.01  # one web search ($10 per 1,000); any other server tool use is counted the same, defensively


def estimate_usd(model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0, server_tool_uses: int = 0,
                 price: tuple[float, float] | None = None, cache_write_1h: int = 0) -> float:
    """cache_write: every cache-write token (5-minute writes 1.25x input); cache_write_1h: those of them written with
    a 1-hour ttl, 2x input (the proxy strips that ttl, so this only guards against a provider-side default)."""
    pin, pout = price or PRICES.get(model, DEFAULT_PRICE)
    plain = max(inp - cache_read - cache_write, 0)
    h1 = min(max(cache_write_1h, 0), cache_write)
    tokens = (plain * pin + cache_read * pin * 0.1 + (cache_write - h1) * pin * 1.25 + h1 * pin * 2.0 + out * pout) / 1_000_000
    return tokens + max(server_tool_uses, 0) * SERVER_TOOL_USD


def answer_price(answer: str | None, requested: str) -> tuple[float, float]:
    """The price a finished call is settled at, from the model that answered (a server-side fallback may answer on
    another model). The requested model, or a dated variant of it: its price. Another known, non-Opus model: its own
    price. Opus, or a model with no PRICES entry: the higher of its PRICES entry and DEFAULT_PRICE, and never below
    the requested model's, so a fallback can never make a call look cheaper than it was."""
    req = PRICES.get(requested, DEFAULT_PRICE)
    if not answer or (answer.startswith(requested) and not _opus(answer)):
        return req
    if answer in PRICES and not _opus(answer):
        return PRICES[answer]
    own = PRICES.get(answer, DEFAULT_PRICE)
    return max(own[0], DEFAULT_PRICE[0], req[0]), max(own[1], DEFAULT_PRICE[1], req[1])


def output_price(model: str) -> float:
    return PRICES.get(model, DEFAULT_PRICE)[1] / 1_000_000


def input_price(model: str) -> float:
    return PRICES.get(model, DEFAULT_PRICE)[0] / 1_000_000


# --------------------------------------------------------------------------- app + middleware

store: Store
http: httpx.AsyncClient


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global store, http
    store = open_store()
    http = httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False)
    log.info("miyagi-cloud %s up: db=%s proxy_enabled=%s paused=%s rate_limit=%s admin=%s alerts=%s", VERSION, store.path,
             PROXY_ENABLED, runtime_paused(), RATE_LIMIT_ENABLED, "on" if ADMIN_ENABLED else "OFF (weak ADMIN_TOKEN)",
             "on" if ALERT_WEBHOOK_URL else "off")
    prune_now()
    pruner = asyncio.create_task(_prune_loop())
    try:
        yield
    finally:
        pruner.cancel()
        await http.aclose()


def prune_now() -> dict | None:
    """Store.prune with the configured retention. Never raises: a failed prune is logged and retried next hour."""
    try:
        n = store.prune(RETAIN_DAYS, LESSON_PENDING_MAX_DAYS * 86400, mint_net_days=MINT_NET_RETAIN_DAYS)
    except Exception:
        log.exception("pruning old rows failed")
        return None
    if any(n.values()):
        log.info("pruned old rows: %s", " ".join(f"{k}={v}" for k, v in n.items() if v))
    return n


async def _prune_loop() -> None:
    while True:
        await asyncio.sleep(PRUNE_EVERY_S)
        await anyio.to_thread.run_sync(prune_now)


# --------------------------------------------------------------------------- client IP

_xff_logged: set[str] = set()  # "any" once the first request is logged, "entries" once one with entries is

# Cloudflare's published edge ranges (https://www.cloudflare.com/ips/): a chosen X-Forwarded-For entry in one of
# these is Cloudflare, not the learner, and TRUSTED_PROXY_HOPS (or CLIENT_IP_HEADER) is wrong.
CLOUDFLARE_NETS = tuple(ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
    "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22", "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32",
    "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32"))


def _ip_kind(ip) -> str:
    """What kind of address the chosen entry is, for the staging check: never the address itself."""
    if ip is None:
        return "not a valid address (the socket peer is used)"
    if any(ip.version == n.version and ip in n for n in CLOUDFLARE_NETS):
        return "a Cloudflare address (wrong hop count)"
    if ip.is_global:
        return "a global address"
    return "a private or reserved address (likely a proxy: wrong hop count)"


def _log_xff(entries: list[str], chosen) -> None:
    """At INFO, once per process (plus once more when the first request had no entries): the NUMBER of
    X-Forwarded-For entries and what kind of address the chosen one is. Never the values."""
    key = "entries" if entries else "any"
    if key in _xff_logged or (not entries and _xff_logged):
        return
    _xff_logged.update({"any", key})
    kind = _ip_kind(chosen) if entries and PROXY_HOPS > 0 and len(entries) >= PROXY_HOPS else "none (the socket peer is used)"
    log.info("first request: %d X-Forwarded-For entr%s (TRUSTED_PROXY_HOPS=%d); the chosen entry is %s", len(entries),
             "y" if len(entries) == 1 else "ies", PROXY_HOPS, kind)


def _parse_ip(raw: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """One address out of a header value: ports stripped ("1.2.3.4:5", "[::1]:5"), anything else invalid."""
    s = raw.strip().strip('"')
    if not s or len(s) > 64:
        return None
    if s.startswith("["):
        end = s.find("]")
        if end < 0:
            return None
        s = s[1:end]
    elif s.count(":") == 1:
        s = s.split(":", 1)[0]
    try:
        return ipaddress.ip_address(s.split("%", 1)[0])
    except ValueError:
        return None


def client_ip_scope(scope) -> str:
    """The client's IP from a raw ASGI scope.

    CLIENT_IP_HEADER (when set and valid) wins. Else the X-Forwarded-For entry at position -TRUSTED_PROXY_HOPS:
    each trusted proxy appends the address it saw, so entries further left are whatever the client wrote and are
    never trusted. Fewer entries than hops, an invalid entry or hops 0: the socket peer."""
    headers = scope.get("headers") or []
    if CLIENT_IP_HEADER:
        for k, v in headers:
            if k.decode("latin-1").lower() == CLIENT_IP_HEADER:
                if ip := _parse_ip(v.decode("latin-1")):
                    return str(ip)
                break
    entries: list[str] = []
    for k, v in headers:
        if k.lower() == b"x-forwarded-for":
            entries += [e for e in v.decode("latin-1").split(",") if e.strip()]
    chosen = _parse_ip(entries[-PROXY_HOPS]) if PROXY_HOPS > 0 and len(entries) >= PROXY_HOPS else None
    if len(_xff_logged) < 2:
        _log_xff(entries, chosen)  # the count and kind only, never the addresses: the staging check
    if chosen is not None:
        return str(chosen)
    peer = str((scope.get("client") or ("", 0))[0] or "")
    ip = _parse_ip(peer)
    return str(ip) if ip else (peer[:64] or "unknown")


def ip_bucket(ip: str) -> str:
    """The rate-limit key for an address: IPv4 as is, IPv6 by its /64 (one home or phone gets a whole /64)."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if a.version == 6:
        if a.ipv4_mapped:
            return str(a.ipv4_mapped)
        return str(ipaddress.ip_network(f"{a}/64", strict=False))
    return str(a)


def mint_bucket(ip: str) -> str:
    """The network install minting (and the anonymous per-network spend ceiling) counts by: IPv4 the full address,
    IPv6 its /MINT_IPV6_PREFIX (48), since one home or phone line routinely gets a /56 or a /48 to pick /64s from."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    if a.version == 4:
        return str(a)
    return str(ipaddress.ip_network(f"{a}/{MINT_IPV6_PREFIX}", strict=False))


def ip_net(ip: str) -> str:
    """A coarser network for "different uploaders" (lesson auto-approval): IPv4 /24, IPv6 /48."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return str(ipaddress.ip_network(f"{a}/{24 if a.version == 4 else 48}", strict=False))


def client_ip(request: Request) -> str:
    return client_ip_scope(request.scope)


# --------------------------------------------------------------------------- rate limits

class SlidingWindowLimiter:
    """Sliding-window counters, O(1) per key: the count in the current fixed window plus the previous window's count
    weighted by how much of it still overlaps the sliding window.

    Memory is bounded: at most `max_keys` keys. Keys sit in an OrderedDict in the order their window last started
    (a key moves to the end whenever its window rolls), so the front holds the oldest windows. Expired keys (no
    request for two windows) are swept from the front at most once a minute; when the dict is still full a new key
    evicts the oldest-window key."""

    def __init__(self, max_keys: int, window: float = 3600.0) -> None:
        self.max_keys = max(1, max_keys)
        self.window = window
        self._d: OrderedDict[str, list] = OrderedDict()  # key -> [window index, count in it, count in the previous]
        self._swept = -math.inf

    def __len__(self) -> int:
        return len(self._d)

    def _sweep(self, w: int) -> None:
        d = self._d
        while d:
            _k, entry = next(iter(d.items()))
            if entry[0] >= w - 1:
                break
            d.popitem(last=False)

    def hit(self, key: str, limit: int, now: float | None = None) -> float:
        """Count one request for `key` unless that would pass `limit` per window (limit <= 0: no limit).
        Returns 0.0 when counted, else the seconds until one more request fits."""
        if limit <= 0:
            return 0.0
        t = _now() if now is None else now
        w = int(t // self.window)
        if t - self._swept >= 60:
            self._swept = t
            self._sweep(w)
        entry = self._d.get(key)
        if entry is None or entry[0] < w - 1:
            curr, prev = 0, 0
        elif entry[0] == w - 1:
            curr, prev = 0, entry[1]
        else:
            curr, prev = entry[1], entry[2]
        elapsed = (t - w * self.window) / self.window
        if prev * (1 - elapsed) + curr + 1 > limit:
            return self._wait(curr, prev, elapsed, limit)
        if entry is not None and entry[0] == w:
            entry[1] += 1
            return 0.0
        if entry is not None:
            del self._d[key]  # its window rolled: re-insert at the end (newest window)
        elif len(self._d) >= self.max_keys:
            self._sweep(w)
            while len(self._d) >= self.max_keys:
                self._d.popitem(last=False)  # evict the oldest-window key
        self._d[key] = [w, curr + 1, prev]
        return 0.0

    def _wait(self, curr: int, prev: int, elapsed: float, limit: int) -> float:
        room = limit - 1  # the weighted count must drop to this for one more request
        W = self.window
        if curr <= room and prev > 0:
            dt = W * (1 - (room - curr) / prev) - elapsed * W
        else:  # this window alone is full: wait for the next one, where it counts as the (decaying) previous window
            dt = (1 - elapsed) * W + (W * max(0.0, 1 - room / curr) if curr else 0.0)
        return max(dt, 1.0)


class AdminFailures:
    """Failed admin authentications per IP bucket: a tuple of the last ADMIN_LOCKOUT_FAILURES times (a few floats,
    no deque). That many within an hour lock the bucket out of /admin until the oldest of them is an hour old.
    Bounded by its own ADMIN_FAILURE_MAX_KEYS (20000, a few MB): the least recently failing bucket goes first."""

    def __init__(self, max_keys: int, window: float = 3600.0) -> None:
        self.max_keys, self.window = max(1, max_keys), window
        self._d: OrderedDict[str, tuple[float, ...]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._d)

    def record(self, bucket: str) -> int:
        n = max(ADMIN_LOCKOUT_FAILURES, 1)
        now = _now()
        times = (*self._d.pop(bucket, ()), now)[-n:]
        while len(self._d) >= self.max_keys:
            self._d.popitem(last=False)
        self._d[bucket] = times
        return sum(1 for t in times if now - t < self.window)

    def locked(self, bucket: str) -> float:
        """Seconds until `bucket` may try /admin again, 0.0 when it is not locked out."""
        if ADMIN_LOCKOUT_FAILURES <= 0:
            return 0.0
        times = self._d.get(bucket)
        if not times or len(times) < ADMIN_LOCKOUT_FAILURES:
            return 0.0
        left = times[-ADMIN_LOCKOUT_FAILURES] + self.window - _now()
        return max(left, 1.0) if left > 0 else 0.0


limiter = SlidingWindowLimiter(RATE_LIMIT_MAX_KEYS)
admin_failures = AdminFailures(ADMIN_FAILURE_MAX_KEYS)

TOKEN_COUNTED = ("/v1/anthropic/", "/v1/gemini/", "/v1/lessons/")
RATE_MESSAGES = {
    "ip_hourly": "Too many requests from this network. Try again in a few minutes.",
    "token_hourly": "This install is sending too many requests. Try again in a few minutes.",
    "admin": "Too many admin requests from this network. Try again later.",
    "admin_lockout": "Too many wrong admin tokens from this network. Try again later.",
    "install_hourly": "Too many new installs from this network. Try again later.",
    "install_daily": "Too many new installs from this network today. Try again tomorrow.",
    "install_global": "miyagi is setting up a lot of new installs right now. Try again in a while.",
}


def rate_limited(limit: str, wait_s: float) -> JSONResponse:
    """429 in error()'s shape, type rate_limit_error, plus `limit` and `resets_at`. Retry-After is at least 1 s;
    x-should-retry: false (no SDK auto-retry) when the wait is over a minute."""
    wait = max(1, math.ceil(wait_s))
    resets = datetime.fromtimestamp(_now() + wait, UTC)
    body = {"type": "error", "error": {"type": "rate_limit_error", "status": "RATE_LIMIT_ERROR", "code": 429,
                                       "message": RATE_MESSAGES[limit], "limit": limit, "resets_at": _iso(resets)}}
    headers = {"retry-after": str(wait)}
    if wait > 60:
        headers["x-should-retry"] = "false"
    return JSONResponse(body, status_code=429, headers=headers)


def token_from_headers(get) -> str:
    """Bearer token; SDKs pointed at the proxy may instead send it as x-api-key / x-goog-api-key."""
    auth = get("authorization") or ""
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return (get("x-api-key") or get("x-goog-api-key") or "").strip()


def _known_token(scope) -> str | None:
    """The hash of the presented install token when it is a known, enabled one; else None.

    Read through Starlette's Headers, exactly as authenticate() reads it (request.headers.get: the FIRST of a
    repeated header). A plain dict would keep the last one, so [Bearer <guess>, Bearer <valid>] would check the
    guess but count it against the valid token's budget instead of the IP's."""
    token = token_from_headers(Headers(scope=scope).get)
    if not token or len(token) > 200:
        return None
    h = hash_token(token)
    row = store.get_token(h)
    return h if row is not None and not row["disabled"] else None


# --------------------------------------------------------------------------- middleware

class BodyTooLarge(Exception):
    pass


def _is_admin(path: str) -> bool:
    return path == "/admin" or path.startswith("/admin/")


# Routes that only ever take a few hundred bytes (install metadata, an admin form or JSON field): their declared and
# running body size is held to this in Guard, before anything is buffered, and their handlers read the body under
# BODY_READ_TIMEOUT_S. A stalled or oversized install body can no longer pin megabytes per request.
SMALL_BODY_MAX = 4 * 1024
SMALL_BODY_PATHS = ("/v1/install", "/v1/register")


def body_limit(path: str) -> int:
    """The most body bytes Guard lets a request to `path` send (declared Content-Length and running count)."""
    if path in SMALL_BODY_PATHS or _is_admin(path):
        return SMALL_BODY_MAX
    if path in ("/v1/link", "/v1/account/delete"):
        return LINK_MAX_BODY
    if path == "/v1/events":
        return EVENTS_MAX_BYTES
    return MAX_GEMINI_BODY if path.startswith("/v1/gemini/") else MAX_BODY


def _size(n: int) -> str:
    return f"{n // (1024 * 1024)} MB" if n >= 1024 * 1024 else f"{n // 1024} KB"


def too_large(limit: int) -> JSONResponse:
    return error(413, "request_too_large", f"Request body over {_size(limit)}.")


def runtime_paused() -> bool:
    """The operators' runtime pause (POST /admin/proxy/pause), read from SQLite on every /v1 request. A read that
    fails is logged and counts as not paused: the call then fails at admission anyway, which needs the same database."""
    try:
        return store.paused()
    except Exception:
        log.exception("reading the runtime pause flag failed")
        return False


PAUSED_MESSAGE = "Miyagi cloud AI is paused by the operators. Try again later."


class Guard:
    """Pure ASGI middleware: kill switches (PROXY_ENABLED and the runtime pause), no browser origins on /v1, admin
    off for a weak ADMIN_TOKEN, body size limit, one log line per request (RateLimit's 429s included: Guard is the
    outer middleware).

    Handlers put model / token counts / token prefix on request.state; we log them after the
    response (including a streamed one) has finished.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        start, path, status = time.monotonic(), scope["path"], [0]
        state = scope.setdefault("state", {})
        headers = Headers(scope=scope)  # a repeated header reads as its first value, as everywhere else

        async def send_logged(msg):
            if msg["type"] == "http.response.start":
                status[0] = msg["status"]
            await send(msg)

        try:
            if path.startswith("/v1/") and (not PROXY_ENABLED or runtime_paused()):
                return await error(503, "proxy_disabled", PAUSED_MESSAGE)(scope, receive, send_logged)
            if path.startswith("/v1/") and "origin" in headers:
                return await error(403, "forbidden", "Browser origins are not allowed.")(scope, receive, send_logged)
            if _is_admin(path) and not ADMIN_ENABLED:
                return await error(503, "admin_disabled", "Admin is disabled: ADMIN_TOKEN is too weak. "
                                   "Set a strong one (32+ random characters).")(scope, receive, send_logged)
            limit = body_limit(path)
            declared = headers.get("content-length", "")
            if declared.isdigit() and int(declared) > limit:
                return await too_large(limit)(scope, receive, send_logged)
            seen = [0]

            async def receive_limited():
                msg = await receive()
                seen[0] += len(msg.get("body", b""))
                if seen[0] > limit:
                    raise BodyTooLarge
                return msg

            try:
                await self.app(scope, receive_limited, send_logged)
            except BodyTooLarge:
                if status[0] == 0:
                    await too_large(limit)(scope, receive, send_logged)
        finally:
            extra = "".join(f" {k}={state[k]}" for k in ("model", "role", "tokens_in", "tokens_out", "held", "tok", "linked", "rl")
                            if state.get(k) is not None)
            log.info("%s %s %s %dms%s", scope["method"], path, status[0] or 500, (time.monotonic() - start) * 1000, extra)


class RateLimit:
    """Pure ASGI middleware: Michael's per-IP rate limiter, directly inside Guard.

    Registered as

        app.add_middleware(RateLimit)
        app.add_middleware(Guard)

    Starlette makes the last-added middleware the outermost, so Guard runs first (kill switch, origin block, body
    limit) and writes the log line for every 429 this one sends.

    Per hour, sliding window (RATE_LIMIT_ENABLED=1 turns it on; it is on by default):
    - every /v1/* and /admin* request counts against its client IP (RATE_LIMIT_PER_IP_PER_HOUR, 100); /healthz never;
    - /v1/anthropic/*, /v1/gemini/*, /v1/lessons/* and /v1/events count against the install token instead
      (RATE_LIMIT_PER_TOKEN_PER_HOUR, 2400), but only when the presented token is a known, enabled one: a missing or
      unknown token counts against the IP, so guessing tokens is IP-limited;
    - /admin* also counts against ADMIN_RATE_LIMIT_PER_IP_PER_HOUR (20) per IP;
    - ADMIN_LOCKOUT_FAILURES (5) wrong admin tokens from one IP within an hour lock that IP out of /admin* (429
      admin_lockout, the right token included) until the oldest of them is an hour old. This one holds even with
      RATE_LIMIT_ENABLED=0.
    IPv6 clients are counted by their /64. The counters live in this process's memory: they are per process and per
    instance (one Render starter instance today), and a deploy resets them. Install minting has its own limit in
    SQLite (Store.mint_check), which survives deploys."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        admin = _is_admin(path)
        if not (admin or path.startswith("/v1/")):  # /healthz (and anything else) is never limited
            return await self.app(scope, receive, send)
        state = scope.setdefault("state", {})
        bucket = ip_bucket(client_ip_scope(scope))
        state["ip_bucket"] = bucket
        denied: tuple[str, float] | None = None
        if admin and (wait := admin_failures.locked(bucket)):
            denied = ("admin_lockout", wait)
        if denied is None and RATE_LIMIT_ENABLED:
            denied = self.check(scope, path, admin, bucket)
        if denied is not None:
            state["rl"] = denied[0]
            return await rate_limited(*denied)(scope, receive, send)
        await self.app(scope, receive, send)

    @staticmethod
    def check(scope, path: str, admin: bool, bucket: str) -> tuple[str, float] | None:
        if admin and (wait := limiter.hit("admin:" + bucket, ADMIN_RATE_LIMIT_PER_IP_PER_HOUR)):
            return "admin", wait
        if path.startswith(TOKEN_COUNTED) or path == "/v1/events":
            if h := _known_token(scope):
                wait = limiter.hit("tok:" + h, RATE_LIMIT_PER_TOKEN_PER_HOUR)
                return ("token_hourly", wait) if wait else None
        wait = limiter.hit("ip:" + bucket, RATE_LIMIT_PER_IP_PER_HOUR)
        return ("ip_hourly", wait) if wait else None


app = FastAPI(title="miyagi-cloud", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(RateLimit)  # inner: per-IP / per-token / admin rate limits (Michael's ask)
app.add_middleware(Guard)  # outer: kill switch, origins, body size, the log line. No CORSMiddleware on purpose.


def error(status: int, kind: str, message: str) -> JSONResponse:
    """One error shape both SDKs can read: Anthropic's {type, error:{type,message}} plus Google's code/status."""
    return JSONResponse({"type": "error", "error": {"type": kind, "status": kind.upper(), "code": status, "message": message}},
                        status_code=status)


# --------------------------------------------------------------------------- auth + quota hooks

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def presented_token(request: Request) -> str:
    """Bearer token; SDKs pointed at the proxy may instead send it as x-api-key / x-goog-api-key."""
    return token_from_headers(request.headers.get)


def authenticate(request: Request) -> tuple[str | None, JSONResponse | None]:
    token = presented_token(request)
    if not token or len(token) > 200:
        return None, error(401, "authentication_error", "Missing or invalid install token. Get one at /v1/install.")
    h = hash_token(token)
    row = store.get_token(h)
    if row is None:
        return None, error(401, "authentication_error", "Unknown install token. Get a new one at /v1/install.")
    request.state.tok = h[:PREFIX_LEN]
    request.state.linked = 1 if store.get_link(h) else None  # linked or not, for the log line: never the account id
    if row["disabled"]:
        return None, error(403, "permission_error", "This install has been disabled.")
    return h, None


SIGNIN_REQUIRED = {"error": "signin_required", "message": "Sign in to keep using miyagi."}


def authenticate_model_call(request: Request) -> tuple[str | None, JSONResponse | None]:
    """authenticate() for the routes that spend money (/v1/anthropic, /v1/gemini, POST /v1/lessons/{id}/build). With
    REQUIRE_SIGNIN on, an install that is not linked to a Supabase user (the links table, POST /v1/link) gets
    401 {"error": "signin_required", ...} after the token checks (unknown 401, disabled 403) and before anything else.
    The flat shape is the one /v1/link uses. Caution: the engine on integration/live reads every cloud 401 as an
    unknown token and asks the app to mint a new one; it must read this error first before the flag is turned on."""
    token_hash, denied = authenticate(request)
    if denied:
        return None, denied
    if REQUIRE_SIGNIN and not request.state.linked:
        return None, JSONResponse(SIGNIN_REQUIRED, status_code=401, headers={"x-should-retry": "false"})
    return token_hash, None


def _next_utc_midnight() -> datetime:
    now = datetime.now(UTC)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _next_utc_month() -> datetime:
    now = datetime.now(UTC)
    return (now.replace(day=28) + timedelta(days=4)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def quota_error(kind: str, limit: str, used: int | float, cap: int | float, resets: datetime, message: str,
                **extra) -> JSONResponse:
    """429 in error()'s shape plus what the app needs to show it: `limit` (lesson_builds | daily_requests |
    daily_spend | daily_usd | lesson_uploads | user_daily_cap), `used`, `cap` and `resets_at`. `x-should-retry: false`
    stops the SDKs' automatic retries. The engine reads type `miyagi_quota` (server/config.py CLOUD_ERRORS) and
    `miyagi_lesson_quota` (lesson cache)."""
    body = {"type": "error", "error": {"type": kind, "status": kind.upper(), "code": 429, "message": message,
                                       "limit": limit, "used": used, "cap": cap, "resets_at": _iso(resets), **extra}}
    retry = max(60, int((resets - datetime.now(UTC)).total_seconds()))
    return JSONResponse(body, status_code=429, headers={"retry-after": str(retry), "x-should-retry": "false"})


ROLE_RE = re.compile(r"[a-z][a-z0-9_-]{0,23}")


def request_role(request: Request) -> str | None:
    """The engine's x-miyagi-role (coach, scene, lesson, screen, finder, diagram, workspace), when it is well formed.
    The client sets it, so it is only a label for the log line and the usage view: no cap reads it, and no role is
    ever exempt from the caps."""
    role = request.headers.get("x-miyagi-role", "").strip().lower()
    return role if ROLE_RE.fullmatch(role) else None


def _caps(token_hash: str) -> dict:
    """The caps for this token, from server-side state only (its plan, its link, its mint network): pro none, linked
    per user, anonymous per install and per mint network."""
    row = store.get_token(token_hash) or {}
    none = {"net": None, "net_usd_cap": 0.0}
    if row.get("plan") == "pro":
        return {"daily_cap": 0, "usd_cap": 0.0, "token_cap": 0, "user_id": None, **none}
    link = store.get_link(token_hash)
    if link:
        return {"daily_cap": LINKED_DAILY_REQUESTS, "usd_cap": LINKED_DAILY_USD, "token_cap": LINKED_DAILY_TOKENS,
                "user_id": link["user_id"], **none}
    return {"daily_cap": FREE_DAILY_REQUESTS, "usd_cap": FREE_DAILY_USD, "token_cap": 0, "user_id": None,
            "net": row.get("mint_net"), "net_usd_cap": ANON_DAILY_USD_PER_NETWORK}


USER_DAILY_CAP_MESSAGE = "You've used today's free help. It resets at midnight UTC."
_USER_CAP_UNIT = {"daily": "requests", "usd": "usd", "tokens": "tokens"}


def check_quota(token_hash: str, role: str | None, provider: str, model: str, reserve_usd: float = 0.0,
                dry_run: bool = False) -> JSONResponse | None:
    """Every cap on one forwarded AI call. None means allowed, and the call is then already counted with its cost
    estimate reserved (unless dry_run, which only checks): caps are checked and counted in one store transaction,
    so parallel calls cannot overshoot them. `role` is recorded as a label only.

    1. DAILY_USD_CAP, the global abuse brake (off by default): every install together, pro included.
    2. Every call whatever its role: anonymous installs FREE_DAILY_USD each; linked installs LINKED_DAILY_USD and
       LINKED_DAILY_TOKENS per Supabase user, all their installs together. Pro: none. (FREE_DAILY_REQUESTS /
       LINKED_DAILY_REQUESTS: optional request counts on the same scopes, off by default.)
    3. Anonymous installs: ANON_DAILY_USD_PER_NETWORK for every unlinked install minted from the same network.
    The lesson build cap lives on POST /v1/lessons/{id}/build, the new-install cap on POST /v1/install.

    A linked user's caps answer limit "user_daily_cap" (unit usd | tokens | requests, scope account) with the
    "today's free help" message; the type stays miyagi_quota, which is what the engine shows its limit card for."""
    c = _caps(token_hash)
    hit, used, cap = store.admit_call(token_hash, provider, model, role, c["daily_cap"], usd_cap=c["usd_cap"],
                                      user_id=c["user_id"], global_usd_cap=DAILY_USD_CAP, reserve_usd=reserve_usd,
                                      net=c["net"], net_usd_cap=c["net_usd_cap"], token_cap=c["token_cap"],
                                      dry_run=dry_run)
    scope = "account" if c["user_id"] else "install"
    if c["user_id"] and hit in _USER_CAP_UNIT:
        unit = _USER_CAP_UNIT[hit]
        return quota_error("miyagi_quota", "user_daily_cap", round(used, 4) if unit == "usd" else int(used), cap,
                           _next_utc_midnight(), USER_DAILY_CAP_MESSAGE, scope="account", unit=unit)
    if hit == "global_usd":
        log.warning("daily USD brake reached: est. $%.2f of $%.2f", used, DAILY_USD_CAP)
        alert("brake", f"miyagi-cloud: the global spend brake (DAILY_USD_CAP ${DAILY_USD_CAP:.2f}) is reached at est. "
                       f"${used:.2f} today. Every AI call is refused until UTC midnight.")
        return quota_error("miyagi_quota", "daily_usd", round(used, 2), DAILY_USD_CAP, _next_utc_midnight(),
                           "miyagi has used today's cloud budget. Back tomorrow.")
    if hit == "daily":
        return quota_error("miyagi_quota", "daily_requests", used, cap, _next_utc_midnight(),
                           "You've reached today's limit. It resets tomorrow.", scope=scope)
    if hit == "usd":
        return quota_error("miyagi_quota", "daily_spend", round(used, 4), cap, _next_utc_midnight(),
                           "You've reached today's limit. It resets tomorrow.", scope=scope)
    if hit == "net_usd":
        return quota_error("miyagi_quota", "daily_spend", round(used, 4), cap, _next_utc_midnight(),
                           "Free use from this network is used up for today. Sign in to keep going, or come back tomorrow.",
                           scope="network")
    return None


# --------------------------------------------------------------------------- alerts (R01 step 6)

_alerted: set[tuple[str, str]] = set()  # (day, key) this process already claimed or saw claimed: skips the database
_spend_checked = [0.0]  # when the spend alerts last read the day's total


def _seen(day: str, key: str) -> bool:
    if _alerted and next(iter(_alerted))[0] != day:
        _alerted.clear()  # a new UTC day: yesterday's keys can fire again
    return (day, key) in _alerted


def _alert_payload(text: str) -> dict:
    """Discord takes {"content"}, Slack (and most other incoming webhooks) {"text"}."""
    host = (urlsplit(ALERT_WEBHOOK_URL).hostname or "").lower()
    if host in ("discord.com", "discordapp.com") or host.endswith((".discord.com", ".discordapp.com")):
        return {"content": text[:1900]}
    return {"text": text}


def _post_webhook(payload: dict) -> None:
    """POST one alert, with one retry. Logs only the status or the exception class: the URL is a secret."""
    for attempt in range(2):
        try:
            r = httpx.post(ALERT_WEBHOOK_URL, json=payload, timeout=10.0, follow_redirects=False)
            if r.status_code < 300:
                return
            log.warning("alert webhook answered %s", r.status_code)
        except httpx.HTTPError as e:
            log.warning("alert webhook failed: %s", type(e).__name__)
        if attempt == 0:
            time.sleep(5)


def _dispatch(payload: dict) -> None:
    """Send off the request path, in a daemon thread (tests replace this)."""
    threading.Thread(target=_post_webhook, args=(payload,), daemon=True, name="miyagi-alert").start()


def alert(key: str, text: str) -> bool:
    """Send `text` to ALERT_WEBHOOK_URL at most once per UTC day per `key`, across processes and restarts (the
    first claim in alerts_sent wins). No webhook set: nothing at all. Never raises. Returns whether it was sent."""
    if not ALERT_WEBHOOK_URL:
        return False
    k = (today(), key)
    if _seen(*k):
        return False
    try:
        first = store.claim_alert(key, k[0])
    except Exception:
        log.exception("claiming an alert failed")
        return False
    _alerted.add(k)
    if not first:
        return False
    log.warning("alert sent: %s", key)
    try:
        _dispatch(_alert_payload(text))
    except Exception:
        log.exception("sending an alert failed")
    return True


def check_spend_alerts(token_hash: str) -> None:
    """After a call settles: the day's spend against the alert line (at most every ALERT_SPEND_CHECK_S), and this
    install's spend against ALERT_TOKEN_DAILY_USD."""
    if not ALERT_WEBHOOK_URL:
        return
    day = today()
    try:
        if ALERT_TOKEN_DAILY_USD > 0:
            prefix = token_hash[:PREFIX_LEN]
            if not _seen(day, f"token:{prefix}"):
                spent = store.usd_today_for(token_hash)
                if spent > ALERT_TOKEN_DAILY_USD:
                    alert(f"token:{prefix}", f"miyagi-cloud: install {prefix} has spent est. ${spent:.2f} today, over the "
                                             f"${ALERT_TOKEN_DAILY_USD:.2f} alert line for one install. "
                                             f"Disable it with /admin/tokens/{prefix}/disable if it looks wrong.")
        levels = [p for p in ALERT_LEVELS if not _seen(day, f"spend_{p}")]
        now = _now()
        if ALERT_DAILY_USD > 0 and levels and now - _spend_checked[0] >= ALERT_SPEND_CHECK_S:
            _spend_checked[0] = now
            total = store.usd_today()
            for p in levels:
                if total >= ALERT_DAILY_USD * p / 100:
                    alert(f"spend_{p}", f"miyagi-cloud: est. spend today is ${total:.2f}, {p}% of the "
                                        f"${ALERT_DAILY_USD:.2f} daily alert line.")
    except Exception:  # alerts never break a response
        log.exception("checking the spend alerts failed")


# --------------------------------------------------------------------------- calls in flight (A23)

class Inflight:
    """Forwarded AI calls in flight, per install token (`per`) and in total (`total`), and the request-body bytes
    they hold, in total (`bytes_total`) and per client network (`bytes_per_net`). One event loop: no lock.

    The per-token slot and the body bytes are taken before the request body is read (so one install cannot open more
    than PER_TOKEN_INFLIGHT bodies, and all installs together cannot buffer more than MAX_INFLIGHT_BODY), the global
    slot only once the body has arrived (so slow bodies cannot hold the slots every other install needs)."""

    def __init__(self) -> None:
        self.per: dict[str, int] = {}
        self.total = 0
        self.bytes_total = 0
        self.bytes_per_net: dict[str, int] = {}

    def acquire_token(self, key: str) -> bool:
        if PER_TOKEN_INFLIGHT > 0 and self.per.get(key, 0) >= PER_TOKEN_INFLIGHT:
            return False
        self.per[key] = self.per.get(key, 0) + 1
        return True

    def release_token(self, key: str) -> None:
        n = self.per.get(key, 0)
        if n <= 1:
            self.per.pop(key, None)
        else:
            self.per[key] = n - 1

    def acquire_global(self) -> bool:
        if GLOBAL_INFLIGHT > 0 and self.total >= GLOBAL_INFLIGHT:
            return False
        self.total += 1
        return True

    def release_global(self) -> None:
        self.total = max(self.total - 1, 0)

    def acquire_bytes(self, net: str, n: int) -> str | None:
        """Hold `n` body bytes for network `net`. None when held, else which budget is full ("bytes" | "bytes_net")."""
        if MAX_INFLIGHT_BODY > 0 and self.bytes_total + n > MAX_INFLIGHT_BODY:
            return "bytes"
        if MAX_INFLIGHT_BODY_PER_IP > 0 and self.bytes_per_net.get(net, 0) + n > MAX_INFLIGHT_BODY_PER_IP:
            return "bytes_net"
        self.bytes_total += n
        self.bytes_per_net[net] = self.bytes_per_net.get(net, 0) + n
        return None

    def release_bytes(self, net: str, n: int) -> None:
        self.bytes_total = max(self.bytes_total - n, 0)
        left = self.bytes_per_net.get(net, 0) - n
        if left <= 0:
            self.bytes_per_net.pop(net, None)
        else:
            self.bytes_per_net[net] = left

    def acquire(self, key: str) -> str | None:
        """Both slots at once; None when taken, else which limit is full ("token" | "global")."""
        if not self.acquire_global():
            return "global"
        if not self.acquire_token(key):
            self.release_global()
            return "token"
        return None

    def release(self, key: str) -> None:
        self.release_token(key)
        self.release_global()


inflight = Inflight()

_INFLIGHT_429 = {
    "token": ("inflight_token", "Too many AI calls at once from this install."),
    "global": ("inflight_global", "miyagi is very busy. Try again in a moment."),
    "bytes": ("inflight_bytes", "miyagi is very busy. Try again in a moment."),
    "bytes_net": ("inflight_bytes_network", "Too many large AI requests at once from this network. Try again in a moment."),
}


def too_many_inflight(which: str) -> JSONResponse:
    """429 for the concurrency limits. Its type is not rate_limit_error on purpose: the engine reads a proxy-shaped
    rate_limit_error as "today's limit", and this one clears in a second (the SDKs retry it after retry-after)."""
    limit, msg = _INFLIGHT_429[which]
    body = {"type": "error", "error": {"type": "concurrency_limit_error", "status": "CONCURRENCY_LIMIT_ERROR", "code": 429,
                                       "message": msg, "limit": limit,
                                       "resets_at": _iso(datetime.fromtimestamp(_now() + 1, UTC))}}
    return JSONResponse(body, status_code=429, headers={"retry-after": "1"})


class Call:
    """One forwarded AI call: its in-flight slots, the body bytes it holds, and its cost reservation. finish()
    releases them and settles the reservation exactly once, whatever ends the call (a response, an upstream error,
    the end of a stream, a client disconnect).

    Settling: finish() with no usage means nothing reached the provider, or the provider refused the call (a non-200
    status, not billed): the reservation is dropped. finish(usage) with a terminal usage (Anthropic's message_delta /
    message_stop, Gemini's final chunk with finishReason, or a whole non-stream body with its usage) settles to the
    real cost. Anything else (the client hung up, the upstream stream dropped, a cancelled read) keeps the whole
    reservation, or the observed cost when that is higher: the provider bills the prefill whether or not we saw it."""

    def __init__(self, request: Request, token_hash: str, provider: str, model: str, net: str = "", body_bytes: int = 0) -> None:
        self.request, self.token_hash, self.provider, self.model = request, token_hash, provider, model
        self.net, self.body_bytes = net, body_bytes
        self.reserve = 0.0
        self.day = today()
        self.admitted = False
        self.done = False
        self.global_slot = False  # the per-token slot is held from open_call(); the global one from take_global()

    def take_global(self) -> bool:
        """The global in-flight slot, taken once the body has been read. False: the service is full."""
        if not self.global_slot and inflight.acquire_global():
            self.global_slot = True
        return self.global_slot

    def admit(self, reserve_usd: float) -> JSONResponse | None:
        denied = check_quota(self.token_hash, request_role(self.request), self.provider, self.model, reserve_usd)
        if denied is None:
            self.admitted, self.reserve, self.day = True, reserve_usd, today()
        return denied

    def finish(self, usage: Usage | None = None) -> None:
        if self.done:
            return
        self.done = True
        inflight.release_token(self.token_hash)
        if self.body_bytes:
            inflight.release_bytes(self.net, self.body_bytes)
        if self.global_slot:
            self.global_slot = False
            inflight.release_global()
        if not self.admitted:
            return
        model, inp, out, usd = (usage or Usage(self.provider)).totals(self.request, self.provider, self.model)
        if usage is not None and not usage.complete and usd < self.reserve:
            usd = self.reserve  # no terminal usage: the provider billed something we did not see
            self.request.state.held = round(self.reserve, 4)
            log.info("call ended without its final usage: holding the $%.4f reservation", self.reserve)
        try:
            store.settle(self.token_hash, self.provider, self.model, self.day, self.reserve, model, inp, out, usd)
        except Exception:  # never let accounting break a response
            log.exception("settling a call failed")
        check_spend_alerts(self.token_hash)


def open_call(request: Request, token_hash: str, provider: str, model: str) -> Call | JSONResponse:
    """Before the body is read: require its Content-Length, check the caps without counting (so a call that is
    already over a cap never reads its body), then take the per-token in-flight slot and hold the body's bytes in
    the in-flight budget (MAX_INFLIGHT_BODY in total, MAX_INFLIGHT_BODY_PER_IP per network). Returns the Call
    holding them, or the response to send. The global slot comes later (Call.take_global, after the body is read)."""
    declared = request.headers.get("content-length", "")
    if not declared.isdigit() or len(declared) > 12:
        return error(411, "length_required", "AI calls need a Content-Length header.")
    request.state.role = request_role(request)  # a label for the log line only
    if denied := check_quota(token_hash, request_role(request), provider, model, dry_run=True):
        return denied
    if not inflight.acquire_token(token_hash):
        return too_many_inflight("token")
    n = int(declared)
    net = mint_bucket(client_ip(request))
    if which := inflight.acquire_bytes(net, n):
        inflight.release_token(token_hash)
        return too_many_inflight(which)
    return Call(request, token_hash, provider, model, net, n)


def request_timeout() -> JSONResponse:
    return error(408, "request_timeout", f"The request body did not arrive within {BODY_READ_TIMEOUT_S:g} s.")


async def read_body(request: Request) -> bytes | None:
    """The request body, or None when it did not arrive within BODY_READ_TIMEOUT_S (send request_timeout())."""
    try:
        with anyio.fail_after(BODY_READ_TIMEOUT_S):
            return await request.body()
    except TimeoutError:
        return None


def small_body_too_large(request: Request, max_bytes: int) -> JSONResponse | None:
    """413 when a route that only takes a small body (a login form, a JWT) declares a bigger one. Guard's running
    count still stops a body that lies about its length at body_limit(path)."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        return too_large(max_bytes)
    return None


async def read_model(request: Request, model: type[BaseModel], max_bytes: int = SMALL_BODY_MAX):
    """A small JSON body validated as `model`, read under BODY_READ_TIMEOUT_S and at most `max_bytes`: the model
    instance, or the response to send (413, 408, or 422 for a body that is not that JSON object). Routes take this
    instead of a Pydantic body parameter, which FastAPI would read in full, with no time limit, before the handler."""
    if too_big := small_body_too_large(request, max_bytes):
        return too_big
    raw = await read_body(request)
    if raw is None:
        return request_timeout()
    if len(raw) > max_bytes:
        return too_large(max_bytes)
    try:
        return model.model_validate(parse_json_object(raw, max_objects=64))
    except (BadBody, ValidationError):
        return error(422, "invalid_request_error", f"Body must be a JSON object with the fields of {model.__name__}.")


def mint_token(request: Request, install_id: str | None, app_version: str, platform: str) -> tuple[str, str] | JSONResponse:
    """One new install token, rate limited per client network (mint_bucket: IPv4 address, IPv6 /48) in SQLite
    (Store.mint_check). Returns (token, token_id); only the token's hash is stored, with that network, which
    ANON_DAILY_USD_PER_NETWORK sums over.

    token_id is the first PREFIX_LEN hex characters of that hash: public, the same id the admin views and
    /admin/tokens/{prefix}/disable use, and useless for calling the proxy."""
    net = mint_bucket(client_ip(request))
    r = store.mint_check(net, REGISTER_PER_HOUR, REGISTER_PER_DAY, GLOBAL_MINTS_MAX, new_per_day=NEW_INSTALLS_PER_DAY)
    if r["hit"]:
        if r["hit"] == "new_installs":
            log.warning("daily new-install cap reached: %d today (NEW_INSTALLS_PER_DAY=%d); new installs refused until "
                        "UTC midnight", r["used"], NEW_INSTALLS_PER_DAY)
            alert("installs_full", f"miyagi-cloud: today's new-install cap ({NEW_INSTALLS_PER_DAY}) is reached. New installs "
                                   "see \"miyagi is full today\" until UTC midnight; existing installs keep working.")
            return installs_full()
        if r["hit"] == "global":
            log.error("install mint ceiling reached: %d this hour (GLOBAL_MINTS_PER_HOUR=%d); new installs refused",
                      r["used"], GLOBAL_MINTS_MAX)
        return rate_limited({"hour": "install_hourly", "day": "install_daily", "global": "install_global"}[r["hit"]], r["retry_s"])
    _warn_mints(r["global"])
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)  # 43 urlsafe characters after the prefix
    h = hash_token(token)
    token_id = h[:PREFIX_LEN]
    store.add_token(h, install_id or token_id, app_version or "unknown", platform or "unknown", mint_net=net)
    request.state.tok = token_id
    return token, token_id


_mint_warned_hour = -1


def _warn_mints(this_hour: int) -> None:
    global _mint_warned_hour
    hour = int(time.time() // 3600)
    if GLOBAL_MINTS_WARN > 0 and this_hour >= GLOBAL_MINTS_WARN and _mint_warned_hour != hour:
        _mint_warned_hour = hour
        log.warning("install minting is high: %d this hour (warn at %d, refuse at %d)", this_hour, GLOBAL_MINTS_WARN, GLOBAL_MINTS_MAX)
        alert("mints_high", f"miyagi-cloud: {this_hour} new installs this hour, past the warning line of "
                            f"{GLOBAL_MINTS_WARN} (refused from {GLOBAL_MINTS_MAX} an hour).")


FULL_MESSAGE = "miyagi is full today, try tomorrow."


def installs_full() -> JSONResponse:
    """429 for the daily new-install cap, in error()'s shape with its own type, `miyagi_full`, so the app can show
    FULL_MESSAGE instead of a generic failure. No counts (the route is public). x-should-retry: false; retry-after
    and resets_at say UTC midnight."""
    resets = _next_utc_midnight()
    body = {"type": "error", "error": {"type": "miyagi_full", "status": "MIYAGI_FULL", "code": 429, "message": FULL_MESSAGE,
                                       "limit": "new_installs", "resets_at": _iso(resets)}}
    retry = max(60, int((resets - datetime.now(UTC)).total_seconds()))
    return JSONResponse(body, status_code=429, headers={"retry-after": str(retry), "x-should-retry": "false"})


# --------------------------------------------------------------------------- usage sniffing

_USAGE_RE = re.compile(r'"(input_tokens|output_tokens|cache_read_input_tokens|cache_creation_input_tokens|ephemeral_1h_input_tokens|'
                       r'web_search_requests|web_fetch_requests|code_execution_requests|'
                       r'promptTokenCount|candidatesTokenCount|thoughtsTokenCount|cachedContentTokenCount)"\s*:\s*(\d+)')
_MODEL_RE = re.compile(r'"(?:model|modelVersion)"\s*:\s*"([A-Za-z0-9._\-]{1,80})"')


# Server-sent event lines worth parsing for the end of a call (cheap substring test first).
_TERMINAL_HINTS = {"anthropic": (b"message_delta", b"message_stop"), "gemini": (b"finishReason",)}
_SSE_LINE_MAX = 8 * 1024 * 1024  # a longer partial line is dropped: the call then keeps its whole reservation
_USAGE_KEY = {"anthropic": "usage", "gemini": "usageMetadata"}


class Usage:
    """Reads token counts out of a response as it streams by (JSON or SSE). Last value of each field wins,
    which matches both APIs: Anthropic's message_delta and Gemini's final chunk carry cumulative totals.

    `complete` says the final usage was seen, so the counts are the whole bill: a server-sent event that ends the
    call (Anthropic message_delta / message_stop, a Gemini chunk with a finishReason and its usageMetadata), parsed
    as JSON so text the model wrote (always inside escaped strings) cannot fake it; a whole non-stream body with its
    usage object (feed_body); or a non-SSE stream that ended cleanly with usage seen (end_of_stream)."""

    def __init__(self, provider: str = "anthropic") -> None:
        self.provider = provider
        self.fields: dict[str, int] = {}
        self.model: str | None = None
        self.complete = False
        self.sse = False
        self._tail = ""
        self._line = b""

    def feed(self, chunk: bytes) -> None:
        text = self._tail + chunk.decode("latin-1")
        for name, n in _USAGE_RE.findall(text):
            self.fields[name] = int(n)
        if self.model is None and (m := _MODEL_RE.search(text)):
            self.model = m.group(1)
        self._tail = text[-256:]
        if self.sse and not self.complete:
            self._scan_events(chunk)

    def _scan_events(self, chunk: bytes) -> None:
        lines = (self._line + chunk).split(b"\n")
        self._line = lines.pop()
        if len(self._line) > _SSE_LINE_MAX:
            self._line = b""
        hints = _TERMINAL_HINTS.get(self.provider, ())
        for line in lines:
            if line.startswith(b"data:") and any(h in line for h in hints) and self._terminal(line[5:]):
                self.complete = True
                return

    def _terminal(self, data: bytes) -> bool:
        try:
            obj = json.loads(data)
        except (ValueError, RecursionError):
            return False
        if not isinstance(obj, dict):
            return False
        if self.provider == "anthropic":
            return obj.get("type") in ("message_delta", "message_stop")
        cands = obj.get("candidates")
        return (isinstance(cands, list) and any(isinstance(c, dict) and c.get("finishReason") for c in cands)
                and isinstance(obj.get("usageMetadata"), dict))

    def feed_body(self, content: bytes) -> None:
        """A whole non-stream 200 body: complete when it parses and carries the provider's usage object."""
        self.feed(content)
        try:
            obj = json.loads(content)
        except (ValueError, RecursionError):
            return
        self.complete = isinstance(obj, dict) and isinstance(obj.get(_USAGE_KEY.get(self.provider, "")), dict)

    def end_of_stream(self) -> None:
        """The upstream stream ended cleanly. An SSE stream is complete only through its terminal event; a non-SSE
        stream (Gemini's JSON array) when usage was seen in it."""
        if not self.sse and self.fields:
            self.complete = True

    def totals(self, request: Request, provider: str, requested_model: str) -> tuple[str, int, int, float]:
        """(model, input tokens, output tokens, estimated USD), also put on request.state for the log line. The usage
        row is the answering model's when it is not the requested one; the price follows answer_price()."""
        f = self.fields
        answer = self.model
        model = requested_model if not answer or answer.startswith(requested_model) else answer
        price = answer_price(answer, requested_model)
        if provider == "anthropic":
            cr, cw = f.get("cache_read_input_tokens", 0), f.get("cache_creation_input_tokens", 0)
            inp, out = f.get("input_tokens", 0) + cr + cw, f.get("output_tokens", 0)
            tools = f.get("web_search_requests", 0) + f.get("web_fetch_requests", 0) + f.get("code_execution_requests", 0)
            h1 = f.get("ephemeral_1h_input_tokens", 0)
        else:
            cr, cw, tools, h1 = f.get("cachedContentTokenCount", 0), 0, 0, 0
            inp, out = f.get("promptTokenCount", 0), f.get("candidatesTokenCount", 0) + f.get("thoughtsTokenCount", 0)
        request.state.model, request.state.tokens_in, request.state.tokens_out = model, inp, out
        return model, inp, out, estimate_usd(model, inp, out, cr, cw, tools, price=price, cache_write_1h=h1)


# --------------------------------------------------------------------------- forwarding

def _redact(body: bytes) -> bytes:
    for key in (ANTHROPIC_KEY, GEMINI_KEY):
        if key:
            body = body.replace(key.encode(), b"[redacted]")
    return body


_BILLING_RE = re.compile(r"credit balance|billing|insufficient.{0,20}(credit|fund|quota)|quota exceeded|exceeded your current quota",
                         re.IGNORECASE)


def _provider_error(provider: str, status: int, kind: str, google_status: str, message: str, retry_after: str | None = None) -> Response:
    """A fixed message in the provider's own error shape (not the proxy's), so the engine treats it as the provider's
    (an ordinary, retryable rate limit or overload), never as a miyagi refusal."""
    if provider == "anthropic":
        body = {"type": "error", "error": {"type": kind, "message": message}}
    else:
        body = {"error": {"code": status, "message": message, "status": google_status}}
    headers = {"retry-after": retry_after} if retry_after else None
    return JSONResponse(body, status_code=status, headers=headers)


def upstream_error(provider: str, status: int, body: bytes, retry_after: str | None = None) -> Response:
    """Upstream refusals that say something about our account (credentials, credit, quota, rate, overload) get a
    fixed generic message; the provider's text is logged here (keys redacted), never passed on. Other errors (a 400
    about the request itself) pass through, redacted."""
    text = _redact(body)[:2000].decode("utf-8", "replace")
    retry = retry_after if retry_after and retry_after.isdigit() and int(retry_after) <= 3600 else None
    if status in (401, 403):
        log.error("upstream %s rejected our credentials (status %s): %s", provider, status, text[:300])
        return error(502, "upstream_auth_error", "The AI provider rejected the proxy's credentials. The operators have been notified.")
    if status == 402 or (status in (400, 429) and _BILLING_RE.search(text)):
        log.error("upstream %s billing or quota problem (status %s): %s", provider, status, text[:300])
        return error(503, "upstream_unavailable", "The AI service is unavailable right now. Try again later.")
    if status == 429:
        log.warning("upstream %s rate limited us: %s", provider, text[:300])
        return _provider_error(provider, 429, "rate_limit_error", "RESOURCE_EXHAUSTED",
                               "The AI provider is busy. Try again in a moment.", retry or "10")
    if status >= 500:
        log.warning("upstream %s error %s: %s", provider, status, text[:300])
        if status in (503, 529):  # overloaded: Anthropic says 529, Google 503
            out = 529 if provider == "anthropic" and status == 529 else 503
            return _provider_error(provider, out, "overloaded_error", "UNAVAILABLE",
                                   "The AI provider is overloaded. Try again in a moment.", retry)
        return _provider_error(provider, status, "api_error", "INTERNAL", "The AI provider had an error. Try again.", retry)
    return Response(_redact(body)[:20_000], status_code=status, media_type="application/json")


PASS_HEADERS = ("content-type", "request-id", "x-request-id")


class SlotResponse(Response):
    """Wraps a StreamingResponse so the call is finished (slot released, cost settled) and the upstream stream
    closed whatever happens: the stream ends, the client disconnects mid-stream, or the body never starts."""

    def __init__(self, inner: StreamingResponse, call: Call, usage: Usage, upstream: httpx.Response) -> None:
        self.inner, self.call, self.usage, self.upstream = inner, call, usage, upstream
        self.status_code, self.background, self.raw_headers = inner.status_code, None, inner.raw_headers

    async def __call__(self, scope, receive, send):
        try:
            await self.inner(scope, receive, send)
        finally:
            self.call.finish(self.usage)
            with anyio.CancelScope(shield=True):
                try:
                    await self.upstream.aclose()
                except Exception:  # already closed or broken: nothing to do
                    pass


async def forward(call: Call, url: str, headers: dict, params: dict, body: bytes, stream: bool) -> Response:
    """Send the call upstream. Every path out of here finishes the call (slot and reservation): with no usage only
    when the provider never got the request or refused it (a non-200 status); otherwise with what was seen, so a
    call that ended before its final usage keeps its reservation (Call.finish)."""
    request, provider, model = call.request, call.provider, call.model
    usage = Usage(provider)
    req = http.build_request("POST", url, headers=headers, params=params, content=body)
    try:
        resp = await http.send(req, stream=True)
    except BaseException as e:
        # Never connected: not billed. Anything later (a read timeout waiting for a non-stream answer, the client
        # hanging up while we wait): the provider may be answering, and billing, right now.
        call.finish(None if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)) else usage)
        if isinstance(e, httpx.HTTPError):
            # the exception text can quote a header value (the key), so log only which header names were refused
            bad = [k for k, v in headers.items() if not isinstance(v, str) or v != v.strip() or any(c in v for c in "\r\n\0")]
            log.warning("upstream %s unreachable: %s%s", provider, type(e).__name__, f" (bad header: {', '.join(bad)})" if bad else "")
            return error(502, "upstream_unreachable", f"Could not reach the {provider} API. Try again.")
        raise

    if resp.status_code != 200 or not stream:
        try:
            try:
                content = await resp.aread()
            finally:
                with anyio.CancelScope(shield=True):
                    await resp.aclose()
        except httpx.HTTPError as e:
            log.warning("upstream %s read failed: %s", provider, type(e).__name__)
            call.finish(usage if resp.status_code == 200 else None)  # a 200 cut short was billed: hold
            return error(502, "upstream_unreachable", f"The {provider} API connection dropped. Try again.")
        except BaseException:  # cancelled (the client hung up) or anything else: the slot must still come back
            call.finish(usage if resp.status_code == 200 else None)
            raise
        if resp.status_code != 200:
            request.state.model = model
            call.finish()
            return upstream_error(provider, resp.status_code, content, resp.headers.get("retry-after"))
        usage.feed_body(content)
        call.finish(usage)
        out_headers = {k: v for k, v in resp.headers.items() if k.lower() in PASS_HEADERS}
        return Response(content, status_code=200, headers=out_headers)

    out_headers = {k: v for k, v in resp.headers.items() if k.lower() in PASS_HEADERS}
    usage.sse = "event-stream" in resp.headers.get("content-type", "").lower()

    async def relay():
        try:
            async for chunk in resp.aiter_bytes():
                usage.feed(chunk)
                yield chunk
            usage.end_of_stream()
        except httpx.HTTPError as e:
            log.warning("upstream %s stream dropped: %s", provider, type(e).__name__)
        finally:
            call.finish(usage)  # first, and synchronous: it must run even if the close below is cancelled
            await resp.aclose()

    out_headers["cache-control"] = "no-cache"
    return SlotResponse(StreamingResponse(relay(), status_code=200, headers=out_headers), call, usage, resp)


class _TooManyObjects(Exception):
    pass


def parse_json_object(raw: bytes, max_objects: int | None = None) -> dict:
    """The body as a JSON object. Counts objects while parsing and stops at JSON_MAX_OBJECTS, so a body of a million
    empty objects never becomes a million dicts. Raises BadBody."""
    limit = JSON_MAX_OBJECTS if max_objects is None else max_objects
    seen = [0]

    def count(obj: dict) -> dict:
        seen[0] += 1
        if limit > 0 and seen[0] > limit:
            raise _TooManyObjects
        return obj

    try:
        data = json.loads(raw, object_hook=count)
    except _TooManyObjects:
        raise BadBody(f"The body has more than {limit} JSON objects.") from None
    except RecursionError:
        raise BadBody("The body is nested too deep.") from None
    except (ValueError, UnicodeDecodeError):
        raise BadBody("Body must be a JSON object.") from None
    if not isinstance(data, dict):
        raise BadBody("Body must be a JSON object.")
    return data


def _json_object(raw: bytes) -> dict | None:
    """parse_json_object, or None for any body it refuses (the routes with their own 400 message)."""
    try:
        return parse_json_object(raw)
    except BadBody:
        return None


def _opus(model) -> bool:
    return isinstance(model, str) and "opus" in model.lower()


# --------------------------------------------------------------------------- request body allowlists (A02)
#
# The upstream JSON is rebuilt from allowlisted keys only, so a client cannot reach a feature we did not mean to
# pay for (server tools, MCP, containers, priority tier, file or URL fetches, other models). Unknown keys are dropped;
# the dangerous ones below are refused with a 400 so a caller learns at once.

class BadBody(Exception):
    """A request body the proxy refuses (400 invalid_request_error with this message)."""


ANTHROPIC_REFUSED = ("mcp_servers", "container", "service_tier", "context_management")
THINKING_TYPES = ("adaptive", "disabled", "enabled", "between_tools")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
_WEB_TOOL_RE = re.compile(r"(web_search|web_fetch)_\d{8}")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _anthropic_model_ok(m) -> bool:
    return isinstance(m, str) and m in ALLOWED_ANTHROPIC and not _opus(m)


def _no_opus_anywhere(value, depth: int = 0) -> None:
    """Any `model`-like key, at any depth, naming Opus is refused (a tool's advisor model, fallbacks, ...)."""
    if depth > 8:
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and "model" in k.lower() and (_opus(v) or (isinstance(v, list) and any(_opus(x) for x in v))):
                raise BadBody("Opus models are not allowed on this proxy.")
            _no_opus_anywhere(v, depth + 1)
    elif isinstance(value, list):
        for v in value:
            _no_opus_anywhere(v, depth + 1)


_MAX_BLOCK_DEPTH = 32
_MODEL_DATA_BLOCKS = ("tool_use", "server_tool_use")  # their `input` is the model's own JSON, not content blocks


def _cache_control(cc) -> dict:
    """A cache breakpoint as forwarded: {"type": "ephemeral"}, with ttl "5m" kept when given and any other ttl
    dropped. A 1-hour cache write costs 2x input, against the 1.25x the caps price every cache write at."""
    if not isinstance(cc, dict) or cc.get("type") != "ephemeral":
        raise BadBody('cache_control must be {"type": "ephemeral"}.')
    return {"type": "ephemeral", "ttl": "5m"} if cc.get("ttl") == "5m" else {"type": "ephemeral"}


def _check_blocks(content, depth: int = 0) -> None:
    """Content may not make Anthropic fetch a URL or read an uploaded file, or mount a container upload, at any
    depth: every object and list under the content is walked (a document's source.content, a tool result's
    content, a search result's content, ...), not only the `content` keys. Nesting deeper than _MAX_BLOCK_DEPTH
    is refused rather than left unchecked. Every cache_control on the way is rewritten in place (_cache_control)."""
    if depth > _MAX_BLOCK_DEPTH:
        raise BadBody("Message content is nested too deep.")
    if isinstance(content, list):
        for v in content:
            _check_blocks(v, depth + 1)
        return
    if not isinstance(content, dict):
        return
    if content.get("type") == "container_upload":
        raise BadBody("container_upload blocks are not allowed on this proxy.")
    src = content.get("source")
    if isinstance(src, dict) and src.get("type") in ("url", "file"):
        raise BadBody(f"{src.get('type')} sources are not allowed on this proxy; send base64 data.")
    skip = "input" if content.get("type") in _MODEL_DATA_BLOCKS else None
    if content.get("cache_control") is not None:
        content["cache_control"] = _cache_control(content["cache_control"])
    for k, v in content.items():
        if k != skip and isinstance(v, (dict, list)):
            _check_blocks(v, depth + 1)


def _clean_tool(t: dict) -> tuple[dict, int, int]:
    """(the tool as forwarded, how many server-tool uses it may make, the input tokens those uses may add)."""
    kind = t.get("type")
    if kind in (None, "custom"):
        if not isinstance(t.get("name"), str) or not t["name"] or len(t["name"]) > 128 or not isinstance(t.get("input_schema"), dict):
            raise BadBody("A client tool needs a name and an input_schema.")
        out = {"name": t["name"], "input_schema": t["input_schema"]}
        if kind == "custom":
            out["type"] = "custom"
        if isinstance(t.get("description"), str):
            out["description"] = t["description"]
        if isinstance(t.get("strict"), bool):
            out["strict"] = t["strict"]
        if t.get("cache_control") is not None:
            out["cache_control"] = _cache_control(t["cache_control"])
        return out, 0, 0
    m = _WEB_TOOL_RE.fullmatch(kind) if isinstance(kind, str) else None
    if m and m.group(1) in ANTHROPIC_SERVER_TOOLS:
        cap = max(SERVER_TOOL_MAX_USES, 1)
        uses = t.get("max_uses")
        uses = min(uses, cap) if _is_int(uses) and uses > 0 else cap
        out = {"type": kind, "name": m.group(1), "max_uses": uses}
        for key in ("allowed_domains", "blocked_domains"):
            if isinstance(t.get(key), list) and all(isinstance(d, str) for d in t[key]):
                out[key] = t[key][:64]
        for key in ("user_location", "citations"):
            if isinstance(t.get(key), dict):
                out[key] = t[key]
        if t.get("cache_control") is not None:
            out["cache_control"] = _cache_control(t["cache_control"])
        if m.group(1) == "web_fetch":  # always bounded: without it one fetch may pull a whole page in as input
            mct = t.get("max_content_tokens")
            out["max_content_tokens"] = (min(mct, WEB_FETCH_MAX_CONTENT_TOKENS) if _is_int(mct) and mct > 0
                                         else WEB_FETCH_MAX_CONTENT_TOKENS)
            return out, uses, uses * out["max_content_tokens"]
        return out, uses, uses * WEB_SEARCH_RESERVE_TOKENS
    raise BadBody(f"Tool type {str(kind)[:40]!r} is not allowed on this proxy (client tools only).")


def sanitize_anthropic(body: dict) -> tuple[dict, int, int]:
    """The Messages API body to forward, rebuilt from allowlisted keys, the most server-tool uses it may make, and
    the input tokens those uses may add (fetched pages, search results). Raises BadBody."""
    model = body.get("model")
    if not _anthropic_model_ok(model):
        raise BadBody(f"Model not allowed on this proxy. Allowed: {', '.join(ALLOWED_ANTHROPIC)}.")
    for key in ANTHROPIC_REFUSED:
        if key in body:
            raise BadBody(f"{key} is not allowed on this proxy.")
    _no_opus_anywhere({k: v for k, v in body.items() if k not in ("messages", "system")})
    for k, v in body.items():  # any other model-like field must name an allowed model (it is dropped either way)
        if k not in ("model", "fallbacks") and isinstance(k, str) and "model" in k.lower():
            vals = v if isinstance(v, list) else [v]
            if not all(_anthropic_model_ok(x) for x in vals):
                raise BadBody(f"{k[:40]} must name an allowed model.")
    if body.get("speed") == "fast" and not ALLOW_FAST_MODE:
        raise BadBody("speed=fast (fast mode) is not enabled on this proxy.")
    mt = body.get("max_tokens")
    if not _is_int(mt) or mt < 0:
        raise BadBody("max_tokens must be a non-negative integer.")
    mt = min(mt, MAX_TOKENS_CAP)
    out: dict = {"model": model, "max_tokens": mt}

    messages = body.get("messages")
    if not isinstance(messages, list):
        raise BadBody("messages must be a list.")
    if len(messages) > ANTHROPIC_MAX_MESSAGES:
        raise BadBody(f"At most {ANTHROPIC_MAX_MESSAGES} messages.")
    system = body.get("system")
    blocks = sum(len(m["content"]) for m in messages if isinstance(m, dict) and isinstance(m.get("content"), list))
    if blocks + (len(system) if isinstance(system, list) else 0) > ANTHROPIC_MAX_BLOCKS:
        raise BadBody(f"At most {ANTHROPIC_MAX_BLOCKS} content blocks in all.")
    clean_msgs = []
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") not in ("user", "assistant", "system"):
            raise BadBody("Each message needs a role (user, assistant or system) and content.")
        content = msg.get("content")
        if not isinstance(content, (str, list)):
            raise BadBody("Message content must be a string or a list of blocks.")
        _check_blocks(content)
        clean_msgs.append({"role": msg["role"], "content": content})
    out["messages"] = clean_msgs
    if "system" in body:
        if not isinstance(body["system"], (str, list)):
            raise BadBody("system must be a string or a list of blocks.")
        _check_blocks(body["system"])
        out["system"] = body["system"]
    for key in ("temperature", "top_p"):
        if _is_num(body.get(key)):
            out[key] = body[key]
    if _is_int(body.get("top_k")):
        out["top_k"] = body["top_k"]
    stops = body.get("stop_sequences")
    if isinstance(stops, list) and len(stops) <= 16 and all(isinstance(s, str) and len(s) <= 500 for s in stops):
        out["stop_sequences"] = stops
    if isinstance(body.get("stream"), bool):
        out["stream"] = body["stream"]
    if body.get("speed") == "fast":  # only reachable with ALLOW_FAST_MODE
        out["speed"] = "fast"

    thinking = body.get("thinking")
    if thinking is not None:
        if not isinstance(thinking, dict) or thinking.get("type") not in THINKING_TYPES:
            raise BadBody(f"thinking.type must be one of: {', '.join(THINKING_TYPES)}.")
        th = {"type": thinking["type"]}
        if "budget_tokens" in thinking:
            b = thinking["budget_tokens"]
            if not _is_int(b) or b < 1 or b >= mt or b > MAX_TOKENS_CAP:
                raise BadBody(f"thinking.budget_tokens must be below max_tokens and at most {MAX_TOKENS_CAP}.")
            th["budget_tokens"] = b
        if thinking.get("display") in ("summarized", "omitted", "updates"):
            th["display"] = thinking["display"]
        out["thinking"] = th

    oc = body.get("output_config")
    if isinstance(oc, dict):  # the engine's structured outputs (format) and effort
        clean_oc: dict = {}
        if oc.get("effort") in EFFORTS:
            clean_oc["effort"] = oc["effort"]
        fmt = oc.get("format")
        if isinstance(fmt, dict) and fmt.get("type") == "json_schema" and isinstance(fmt.get("schema"), dict):
            clean_oc["format"] = {"type": "json_schema", "schema": fmt["schema"]}
        if clean_oc:
            out["output_config"] = clean_oc

    server_uses = server_tokens = 0
    tools = body.get("tools")
    if tools is not None:
        if not isinstance(tools, list) or len(tools) > 64 or not all(isinstance(t, dict) for t in tools):
            raise BadBody("tools must be a list of at most 64 tool objects.")
        clean_tools = []
        for t in tools:
            ct, uses, tokens = _clean_tool(t)
            clean_tools.append(ct)
            server_uses += uses
            server_tokens += tokens
        out["tools"] = clean_tools
    tc = body.get("tool_choice")
    if isinstance(tc, dict) and tc.get("type") in ("auto", "any", "tool", "none"):
        clean_tc = {"type": tc["type"]}
        if isinstance(tc.get("name"), str):
            clean_tc["name"] = tc["name"][:128]
        if isinstance(tc.get("disable_parallel_tool_use"), bool):
            clean_tc["disable_parallel_tool_use"] = tc["disable_parallel_tool_use"]
        out["tool_choice"] = clean_tc

    fb = body.get("fallbacks")
    if fb is not None:  # the engine sends "default" with Sonnet (its documented targets are Sonnet 5 only)
        if fb == "default":
            out["fallbacks"] = "default"
        elif isinstance(fb, list) and fb and all(isinstance(f, dict) and _anthropic_model_ok(f.get("model")) for f in fb):
            out["fallbacks"] = [{"model": f["model"]} for f in fb]
        else:
            raise BadBody("fallbacks must be \"default\" or a list of allowed (non-Opus) models.")
    return out, server_uses, server_tokens


def check_betas(header: str) -> str | None:
    """The anthropic-beta header to forward: only ANTHROPIC_BETAS values. Raises BadBody for any other value."""
    values = [b.strip() for b in header.split(",") if b.strip()]
    if any(v not in ANTHROPIC_BETAS for v in values):
        allowed = ", ".join(sorted(ANTHROPIC_BETAS)) or "none"
        raise BadBody(f"An anthropic-beta value is not allowed on this proxy. Allowed: {allowed}.")
    return ",".join(values) or None


# --------------------------------------------------------------------------- cost reservations
#
# What a call may cost, held against the USD caps while it is in flight (Call.admit), then settled to the real
# usage. Input counts too: a large prompt with max_tokens=1 is not free, and 80 of them in flight at once must not
# pass DAILY_USD_CAP by more than about one call.

def _images(value, depth: int = 0) -> tuple[int, int]:
    """(characters of base64 image data, number of images) under an Anthropic or Gemini body. Images are billed by
    their pixels, not their bytes, so they are reserved at IMAGE_RESERVE_TOKENS each instead of bytes / 3."""
    if depth > 40:
        return 0, 0
    if isinstance(value, list):
        sums = [_images(v, depth + 1) for v in value]
        return sum(s[0] for s in sums), sum(s[1] for s in sums)
    if not isinstance(value, dict):
        return 0, 0
    src = value.get("source")
    if value.get("type") == "image" and isinstance(src, dict) and src.get("type") == "base64" and isinstance(src.get("data"), str):
        return len(src["data"]), 1
    inline = value.get("inlineData")
    if (isinstance(inline, dict) and isinstance(inline.get("data"), str)
            and str(inline.get("mimeType", "")).startswith("image/")):
        return len(inline["data"]), 1
    sums = [_images(v, depth + 1) for v in value.values() if isinstance(v, (dict, list))]
    return sum(s[0] for s in sums), sum(s[1] for s in sums)


def input_tokens_estimate(payload_len: int, clean: dict) -> int:
    """The forwarded body's input tokens, erring high: bytes / CHARS_PER_TOKEN, images at IMAGE_RESERVE_TOKENS."""
    b64, n = _images(clean)
    return max(payload_len - b64, 0) // CHARS_PER_TOKEN + n * IMAGE_RESERVE_TOKENS


def anthropic_reserve(clean: dict, payload_len: int, server_uses: int, server_tokens: int) -> float:
    """Input (the body, plus what the allowed server tools may add) at the input price, max_tokens (thinking
    included) at the output price, and $0.01 per allowed server-tool use."""
    model = clean["model"]
    inp = input_tokens_estimate(payload_len, clean) + server_tokens
    return inp * input_price(model) + clean["max_tokens"] * output_price(model) + server_uses * SERVER_TOOL_USD


_OFFSET_RE = re.compile(r"\s*(\d{1,6}(?:\.\d{1,9})?)s\s*")


def _offset_s(v) -> float | None:
    """Seconds from a videoMetadata offset ("600s" or a number); None when unparseable, negative or not finite."""
    if _is_num(v):
        return float(v) if math.isfinite(v) and v >= 0 else None
    m = _OFFSET_RE.fullmatch(v) if isinstance(v, str) else None
    return float(m.group(1)) if m else None


def _video_tokens(part: dict, low: bool) -> int:
    """Input tokens one YouTube fileData part may cost, at most GEMINI_CONTEXT_TOKENS. Per second: fps x frame tokens
    (258, or 70 at MEDIA_RESOLUTION_LOW) + 32 audio tokens; fps defaults to Gemini's 1 and is clamped to
    GEMINI_MAX_FPS. With a window (an end offset after its start: the engine's windows) its seconds at that rate.
    Without one (no end, an unparseable offset, or end <= start): a whole video, GEMINI_VIDEO_RESERVE_TOKENS (sized
    for about 30 minutes at the engine's 0.5 fps), scaled up when this part's rate is higher than that one."""
    vm = part.get("videoMetadata") if isinstance(part.get("videoMetadata"), dict) else {}
    fps = vm.get("fps")
    fps = min(float(fps), GEMINI_MAX_FPS) if _is_num(fps) and math.isfinite(fps) and fps > 0 else 1.0
    per_s = fps * (70 if low else 258) + 32
    start, end = _offset_s(vm.get("startOffset", 0)), _offset_s(vm.get("endOffset"))
    if start is None or end is None or end <= start:
        tokens = GEMINI_VIDEO_RESERVE_TOKENS * max(per_s / (0.5 * 258 + 32), 1.0)  # never below the flat reserve
    else:
        tokens = (end - start) * per_s
    return int(min(tokens, GEMINI_CONTEXT_TOKENS))


def gemini_reserve(clean: dict, model: str, payload_len: int) -> float:
    """Input (the body, every video part) at the input price; the clamped maxOutputTokens at the output price.
    Thinking counts against maxOutputTokens on Gemini 2.5 and later, so the clamp bounds answer and thinking together
    (a clamped thinkingBudget above it, only possible when GEMINI_MAX_THINKING_TOKENS is set higher, is held instead)."""
    gen = clean.get("generationConfig") or {}
    low = gen.get("mediaResolution") == "MEDIA_RESOLUTION_LOW"
    parts = [p for c in clean.get("contents", []) for p in c.get("parts", [])]
    parts += (clean.get("systemInstruction") or {}).get("parts", [])
    video = sum(_video_tokens(p, low) for p in parts if "fileData" in p)
    budget = (gen.get("thinkingConfig") or {}).get("thinkingBudget")
    out = max(gen.get("maxOutputTokens", GEMINI_MAX_OUTPUT_TOKENS), budget if _is_int(budget) else 0)
    inp = min(input_tokens_estimate(payload_len, clean) + video, GEMINI_CONTEXT_TOKENS)  # no call can bill more
    return inp * input_price(model) + out * output_price(model)


GEMINI_PART_KEYS = ("text", "inlineData", "fileData", "videoMetadata", "functionCall", "functionResponse", "thought",
                    "thoughtSignature")
GEMINI_GEN_KEYS = ("temperature", "topP", "topK", "stopSequences", "responseMimeType", "responseSchema",
                   "responseJsonSchema", "mediaResolution")
_YOUTUBE_URI_RE = re.compile(r"https://(?:www\.youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})(?:[?&][A-Za-z0-9_=&%.-]{0,200})?")


def _youtube_uri(uri) -> str:
    """The canonical watch URL for an allowed YouTube fileUri. Anything else (another host, a Files API upload, a
    Cloud Storage path) raises BadBody: Gemini would otherwise fetch it on our account."""
    m = _YOUTUBE_URI_RE.fullmatch(uri) if isinstance(uri, str) else None
    if not m:
        raise BadBody("fileData.fileUri must be a YouTube video (https://www.youtube.com/watch?v=ID or https://youtu.be/ID).")
    return f"https://www.youtube.com/watch?v={m.group(1)}"


# Keys that make Gemini read a file or fetch a URL, in either JSON spelling (the API accepts proto snake_case too).
# They may appear only as a validated top-level fileData; anywhere else in a part (a functionResponse's parts, a
# functionCall's args, ...) the body is refused, so nothing nested can reach Google unchecked.
_GEMINI_FILE_KEYS = frozenset({"fileData", "file_data", "fileUri", "file_uri"})


def _no_file_refs(value, depth: int = 0) -> None:
    if depth > _MAX_BLOCK_DEPTH:
        raise BadBody("A part is nested too deep.")
    if isinstance(value, dict):
        for k, v in value.items():
            if k in _GEMINI_FILE_KEYS:
                raise BadBody("fileData is only allowed as a top-level part holding a YouTube video.")
            _no_file_refs(v, depth + 1)
    elif isinstance(value, list):
        for v in value:
            _no_file_refs(v, depth + 1)


def _function_response(fr) -> dict:
    """{id?, name, response} only. A multimodal functionResponse.parts (file_data / inline_data the model would read)
    is refused: the engine never sends one, and it would carry files past the YouTube-only fileData check."""
    if not isinstance(fr, dict) or not isinstance(fr.get("name"), str):
        raise BadBody("functionResponse needs a name and a response object.")
    if "parts" in fr:
        raise BadBody("functionResponse.parts is not allowed on this proxy.")
    out = {"name": fr["name"][:128], "response": fr.get("response") if isinstance(fr.get("response"), dict) else {}}
    if isinstance(fr.get("id"), str):
        out["id"] = fr["id"][:128]
    return out


def _video_metadata(vm) -> dict:
    """startOffset / endOffset / fps only, fps clamped to GEMINI_MAX_FPS (the engine uses at most 2). A window that
    ends before it starts is refused: it would reserve nothing."""
    if not isinstance(vm, dict):
        raise BadBody("videoMetadata must be an object.")
    out = {k: vm[k] for k in ("startOffset", "endOffset") if k in vm and (_is_num(vm[k]) or isinstance(vm[k], str))}
    start, end = _offset_s(out.get("startOffset", 0)), _offset_s(out.get("endOffset"))
    if start is not None and end is not None and end < start:
        raise BadBody("videoMetadata.endOffset must not be before startOffset.")
    if "fps" in vm:
        fps = vm["fps"]
        if not _is_num(fps) or not math.isfinite(fps) or fps <= 0:
            raise BadBody("videoMetadata.fps must be a positive number.")
        out["fps"] = min(float(fps), GEMINI_MAX_FPS)
    return out


def _gemini_parts(parts) -> list:
    if not isinstance(parts, list):
        raise BadBody("parts must be a list.")
    out = []
    for p in parts:
        if not isinstance(p, dict):
            raise BadBody("Each part must be an object.")
        cp = {k: p[k] for k in GEMINI_PART_KEYS if k in p}
        if "functionResponse" in cp:
            cp["functionResponse"] = _function_response(cp["functionResponse"])
        if "videoMetadata" in cp:
            cp["videoMetadata"] = _video_metadata(cp["videoMetadata"])
        for k, v in cp.items():  # everything but the top-level fileData checked below
            if k != "fileData":
                _no_file_refs(v)
        if "fileData" in cp:
            fd = cp["fileData"]
            if not isinstance(fd, dict):
                raise BadBody("fileData must be an object.")
            clean = {"fileUri": _youtube_uri(fd.get("fileUri"))}
            if isinstance(fd.get("mimeType"), str):
                clean["mimeType"] = fd["mimeType"]
            cp["fileData"] = clean
        if cp:
            out.append(cp)
    return out


def _gemini_bounds(body: dict, contents: list) -> None:
    """Counts checked before anything is copied: contents, parts (every content and the system instruction),
    functionDeclarations and safetySettings. Raises BadBody past a bound."""
    if len(contents) > GEMINI_MAX_CONTENTS:
        raise BadBody(f"At most {GEMINI_MAX_CONTENTS} contents.")
    si = body.get("systemInstruction")
    holders = [*contents, si] if isinstance(si, dict) else contents
    parts = sum(len(c["parts"]) for c in holders if isinstance(c, dict) and isinstance(c.get("parts"), list))
    if parts > GEMINI_MAX_PARTS:
        raise BadBody(f"At most {GEMINI_MAX_PARTS} parts in all.")
    tools = body.get("tools")
    if isinstance(tools, list):
        if len(tools) > GEMINI_MAX_FUNCTIONS:
            raise BadBody(f"At most {GEMINI_MAX_FUNCTIONS} tools.")
        fns = sum(len(t["functionDeclarations"]) for t in tools
                  if isinstance(t, dict) and isinstance(t.get("functionDeclarations"), list))
        if fns > GEMINI_MAX_FUNCTIONS:
            raise BadBody(f"At most {GEMINI_MAX_FUNCTIONS} functionDeclarations.")
    ss = body.get("safetySettings")
    if isinstance(ss, list) and len(ss) > GEMINI_MAX_SAFETY:
        raise BadBody(f"At most {GEMINI_MAX_SAFETY} safetySettings.")


def sanitize_gemini(body: dict) -> tuple[dict, int]:
    """The generateContent body to forward, rebuilt from allowlisted keys, and its (clamped) maxOutputTokens.
    Raises BadBody."""
    if "cachedContent" in body or "cached_content" in body:
        raise BadBody("cachedContent is not allowed on this proxy.")
    contents = body.get("contents")
    if not isinstance(contents, list):
        raise BadBody("contents must be a list.")
    _gemini_bounds(body, contents)
    out: dict = {"contents": []}
    for c in contents:
        if not isinstance(c, dict):
            raise BadBody("Each content must be an object.")
        cc: dict = {"parts": _gemini_parts(c.get("parts", []))}
        if isinstance(c.get("role"), str):
            cc["role"] = c["role"]
        out["contents"].append(cc)
    si = body.get("systemInstruction")
    if si is not None:
        if not isinstance(si, dict):
            raise BadBody("systemInstruction must be an object.")
        out["systemInstruction"] = {"parts": _gemini_parts(si.get("parts", []))}
        if isinstance(si.get("role"), str):
            out["systemInstruction"]["role"] = si["role"]
    tools = body.get("tools")
    if tools is not None:
        if not isinstance(tools, list):
            raise BadBody("tools must be a list.")
        clean_tools = []
        for t in tools:
            if not isinstance(t, dict) or set(t) - {"functionDeclarations"}:
                raise BadBody("Only functionDeclarations tools are allowed on this proxy (no googleSearch, codeExecution, urlContext...).")
            if isinstance(t.get("functionDeclarations"), list):
                clean_tools.append({"functionDeclarations": t["functionDeclarations"]})
        if clean_tools:
            out["tools"] = clean_tools
    tc = body.get("toolConfig")
    if isinstance(tc, dict) and isinstance(tc.get("functionCallingConfig"), dict):
        out["toolConfig"] = {"functionCallingConfig": tc["functionCallingConfig"]}
    ss = body.get("safetySettings")
    if isinstance(ss, list) and all(isinstance(s, dict) for s in ss):
        out["safetySettings"] = [{k: s[k] for k in ("category", "threshold", "method") if k in s} for s in ss]

    gc = body.get("generationConfig") if isinstance(body.get("generationConfig"), dict) else {}
    gen = {k: gc[k] for k in GEMINI_GEN_KEYS if k in gc}
    gen["candidateCount"] = 1
    req = gc.get("maxOutputTokens")
    max_out = min(req, GEMINI_MAX_OUTPUT_TOKENS) if _is_int(req) and req > 0 else GEMINI_MAX_OUTPUT_TOKENS
    gen["maxOutputTokens"] = max_out
    th = gc.get("thinkingConfig")
    if isinstance(th, dict):
        clean_th: dict = {}
        if "thinkingBudget" in th:
            b = th["thinkingBudget"]
            clean_th["thinkingBudget"] = min(b, GEMINI_MAX_THINKING_TOKENS) if _is_int(b) and b >= 0 else GEMINI_MAX_THINKING_TOKENS
        if isinstance(th.get("includeThoughts"), bool):
            clean_th["includeThoughts"] = th["includeThoughts"]
        if th.get("thinkingLevel") in ("minimal", "low", "medium", "high", "MINIMAL", "LOW", "MEDIUM", "HIGH"):
            clean_th["thinkingLevel"] = th["thinkingLevel"]
        if clean_th:
            gen["thinkingConfig"] = clean_th
    out["generationConfig"] = gen
    return out, max_out


# --------------------------------------------------------------------------- routes

@app.get("/healthz")
async def healthz():
    """Liveness plus what an operator checks after a deploy: the deployed commit, and booleans only (never a key, a
    path or a count). Always 200 while the process runs, so a database hiccup does not make Render restart it."""
    try:
        db_ok = store.ping()
    except Exception:
        db_ok = False
    paused = runtime_paused() if db_ok else False
    return {"ok": True, "version": VERSION, "commit": DEPLOYED_COMMIT, "proxy_enabled": PROXY_ENABLED and not paused,
            "paused": paused, "db_ok": db_ok, "gemini_enabled": bool(ALLOWED_GEMINI), "require_signin": REQUIRE_SIGNIN,
            "keys_configured": {"anthropic": bool(ANTHROPIC_KEY), "gemini": bool(GEMINI_KEY)}}


TOKEN_PREFIX = "mi_"  # the app (main/features/cloud.ts TOKEN_RE) only keeps tokens of this shape


class RegisterBody(BaseModel):
    install_id: str = Field(min_length=1, max_length=128)
    app_version: str = Field(min_length=1, max_length=64)
    platform: str = Field(min_length=1, max_length=32)


@app.post("/v1/register")
async def register(request: Request):
    body = await read_model(request, RegisterBody)
    if isinstance(body, JSONResponse):
        return body
    minted = mint_token(request, body.install_id, body.app_version, body.platform)
    if isinstance(minted, JSONResponse):
        return minted
    token, token_id = minted
    return {"token": token, "token_id": token_id}


class InstallBody(BaseModel):
    """What the desktop app sends (app/src/main/features/cloud.ts). Every field optional; extra fields ignored."""
    app: str = Field(default="", max_length=64)
    os: str = Field(default="", max_length=64)
    arch: str = Field(default="", max_length=32)


@app.post("/v1/install")
async def install(request: Request):
    body = await read_model(request, InstallBody)
    if isinstance(body, JSONResponse):
        return body
    platform = "/".join(x for x in (body.os.strip(), body.arch.strip()) if x)
    minted = mint_token(request, None, body.app.strip(), platform)
    if isinstance(minted, JSONResponse):
        return minted
    token, token_id = minted
    return {"token": token, "token_id": token_id}


# --------------------------------------------------------------------------- accounts: POST /v1/link
#
# The app sends its install token and the signed-in Supabase user's access token; we verify the JWT
# (supabase_auth.py: a Google sign-in, not anonymous) and remember install -> user. Unlinked installs keep using the
# proxy with the anonymous caps, and signing out never unlinks. Errors use the flat {"error": kind} shape the app's
# link client reads.

import supabase_auth  # noqa: E402  (kept beside the one route that uses it)
from starlette.concurrency import run_in_threadpool  # noqa: E402

verifier = supabase_auth.SupabaseVerifier.from_env()  # SUPABASE_URL, SUPABASE_ALLOW_HS256, SUPABASE_JWT_SECRET; tests swap it


LINK_MAX_BODY = 16 * 1024  # {"access_token": "<JWT>"}: a Supabase JWT is 1-2 KB


def link_error(status: int, kind: str) -> JSONResponse:
    return JSONResponse({"error": kind}, status_code=status)


@app.post("/v1/link")
async def link(request: Request):
    token = presented_token(request)
    h = hash_token(token) if token and len(token) <= 200 else None
    row = store.get_token(h) if h else None
    if row is None or row["disabled"]:
        return link_error(401, "bad_install_token")
    request.state.tok = h[:PREFIX_LEN]
    if too_big := small_body_too_large(request, LINK_MAX_BODY):
        return too_big
    raw = await read_body(request)
    if raw is None:
        return request_timeout()
    if len(raw) > LINK_MAX_BODY:
        return error(413, "request_too_large", f"Request body over {LINK_MAX_BODY // 1024} KB.")
    body = _json_object(raw)
    try:  # the first call (and one every 10 minutes) fetches the JWKS: keep it off the event loop
        claims = await run_in_threadpool(verifier.verify, (body or {}).get("access_token"))
    except supabase_auth.AuthUnavailable:
        return link_error(503, "link_unavailable")
    except supabase_auth.BadAccessToken:
        return link_error(403, "bad_access_token")
    user_id = claims["sub"]
    if not store.link_user_capped(h, user_id, LINK_MAX_INSTALLS_PER_USER):
        log.warning("link refused: the user already has %d installs linked", LINK_MAX_INSTALLS_PER_USER)
        return link_error(403, "too_many_installs")
    request.state.linked = 1
    return {"ok": True, "user_id": user_id}


# --------------------------------------------------------------------------- accounts: POST /v1/account/delete
#
# Deletes what the cloud holds for an install and, signed in, for the whole account (README, Deleting an account).
# Same install-token check, body cap and JWT verifier as /v1/link; rate limited per client IP like it.

SUPABASE_ADMIN_URL = (os.environ.get("SUPABASE_URL", "").strip() or supabase_auth.DEFAULT_SUPABASE_URL).rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = _env_key("SUPABASE_SERVICE_ROLE_KEY")  # Supabase secret (service_role) key: dashboard only
supabase_transport: httpx.AsyncBaseTransport | None = None  # tests inject an httpx.MockTransport: never the network


async def delete_supabase_user(user_id: str) -> str | None:
    """DELETE the Supabase auth user through the Admin API. None when it is gone (a 404 counts: already deleted),
    else why not: "no_service_key" | "supabase_<status>" | "supabase_unreachable". Logs neither the id nor the key."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        return "no_service_key"
    url = f"{SUPABASE_ADMIN_URL}/auth/v1/admin/users/{quote(user_id, safe='')}"
    headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=False, transport=supabase_transport) as c:
            r = await c.delete(url, headers=headers)
    except httpx.HTTPError as e:
        log.warning("supabase user delete failed: %s", type(e).__name__)
        return "supabase_unreachable"
    if r.status_code in (200, 204, 404):
        return None
    log.warning("supabase user delete answered %s", r.status_code)
    return f"supabase_{r.status_code}"


async def finish_account_delete(user_id: str) -> str:
    """Delete the Supabase user; on failure remember the request (deletion_requests) and alert. "deleted" | "pending"."""
    why = await delete_supabase_user(user_id)
    if why is None:
        store.clear_deletion_request(user_id)
        return "deleted"
    store.add_deletion_request(user_id)
    log.warning("account deletion pending: local data deleted, Supabase user not (%s)", why)
    alert("account_delete_pending", f"miyagi-cloud: an account deletion is pending ({why}). Its cloud data is deleted, "
                                    "its Supabase auth user is not yet. See GET /admin/deletions; retry with "
                                    "POST /admin/deletions/retry once SUPABASE_SERVICE_ROLE_KEY works.")
    return "pending"


@app.post("/v1/account/delete")
async def account_delete(request: Request):
    """Contract (the app builds against it):
    Authorization: Bearer <mi_ install token>; body {"access_token": "<Supabase JWT>"} signed in, or {} signed out.
    200 {"ok": true, "install": true | false, "account": "deleted" | "none" | "pending"}: `install` says whether the
    calling install token was a live one (and is now deleted). A valid access token deletes the account and every
    install linked to it even when the install token is missing, unknown or disabled (an earlier signed-out delete,
    a wiped install file): then `install` is false.
    401 {"error": "bad_install_token"}: only when there is no valid access token AND the install token is bad (so a
    repeated signed-out call gets 401, which the app treats as already deleted). 403 {"error": "bad_access_token"}:
    the access token is invalid and the install token is live; nothing deleted. 400 {"error": "bad_request"} (live
    install token, body not a JSON object); 413; 503 {"error": "delete_unavailable"} (the JWT cannot be verified
    right now: nothing deleted, retry)."""
    token = presented_token(request)
    h = hash_token(token) if token and len(token) <= 200 else None
    row = store.get_token(h) if h else None
    live = row is not None and not row["disabled"]
    if too_big := small_body_too_large(request, LINK_MAX_BODY):
        return too_big
    raw = await read_body(request)
    if raw is None:
        return request_timeout()
    if len(raw) > LINK_MAX_BODY:
        return error(413, "request_too_large", f"Request body over {LINK_MAX_BODY // 1024} KB.")
    body = _json_object(raw) if raw.strip() else {}
    if body is None:
        return link_error(400, "bad_request") if live else link_error(401, "bad_install_token")
    access, user_id = body.get("access_token"), None
    if access is not None and access != "":
        try:
            claims = await run_in_threadpool(verifier.verify, access)
        except supabase_auth.AuthUnavailable:
            return link_error(503, "delete_unavailable")  # never 401 here: the app would take it as done
        except supabase_auth.BadAccessToken:
            return link_error(403, "bad_access_token") if live else link_error(401, "bad_install_token")
        user_id = claims["sub"]
    if not live and user_id is None:
        return link_error(401, "bad_install_token")
    n = await run_in_threadpool(store.delete_account, h if live else None, user_id)
    log.info("account delete: %d install(s), signed %s, install token %s", n["installs"], "in" if user_id else "out",
             "live" if live else "gone")
    account = await finish_account_delete(user_id) if user_id else "none"
    return {"ok": True, "install": live, "account": account}


@app.post("/v1/anthropic/messages")
@app.post("/v1/anthropic/v1/messages")  # so the Anthropic SDK works with base_url=<proxy>/v1/anthropic
async def anthropic_messages(request: Request):
    token_hash, denied = authenticate_model_call(request)
    if denied:
        return denied
    if not ANTHROPIC_KEY:
        return error(503, "upstream_not_configured", "Anthropic is not configured on this proxy.")
    try:
        beta = check_betas(request.headers.get("anthropic-beta", ""))
    except BadBody as e:
        return error(400, "invalid_request_error", str(e))
    call = open_call(request, token_hash, "anthropic", "pending")  # caps checked, per-token slot taken before the body
    if isinstance(call, JSONResponse):
        return call
    try:
        raw = await read_body(request)  # bounded in time: a slow body holds only this install's own slot
        if raw is None:
            call.finish()
            return request_timeout()
        try:  # bounded while parsing (JSON_MAX_OBJECTS) and counted before anything is copied
            body = parse_json_object(raw)
            model = body.get("model")
            request.state.model = model if isinstance(model, str) and len(model) <= 80 else None
            clean, server_uses, server_tokens = sanitize_anthropic(body)
        except BadBody as e:
            call.finish()
            return error(400, "invalid_request_error", str(e))
        del raw, body
        call.model = clean["model"]
        payload = json.dumps(clean).encode()
        stream = clean.get("stream") is True
        reserve = anthropic_reserve(clean, len(payload), server_uses, server_tokens)
        del clean  # only the encoded payload is held while the call is upstream
        if not call.take_global():  # the global slot only once the body is here
            call.finish()
            return too_many_inflight("global")
        if denied := call.admit(reserve):
            call.finish()
            return denied
    except BaseException:
        call.finish()
        raise

    headers = {"x-api-key": ANTHROPIC_KEY, "content-type": "application/json",
               "anthropic-version": ANTHROPIC_VERSION, "accept-encoding": "identity"}
    client_version = request.headers.get("anthropic-version", "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", client_version):
        headers["anthropic-version"] = client_version  # the SDK knows which response shapes it parses
    if beta:
        headers["anthropic-beta"] = beta
    params = {"beta": "true"} if request.query_params.get("beta") == "true" else {}
    return await forward(call, ANTHROPIC_URL, headers, params, payload, stream=stream)


GEMINI_METHODS = {"generateContent": False, "streamGenerateContent": True}
_GEMINI_MODEL_RE = re.compile(r"[a-z0-9][a-z0-9.\-]{0,63}")


@app.post("/v1/gemini/{target}")
@app.post("/v1/gemini/v1beta/models/{target}")  # so google-genai works with base_url=<proxy>/v1/gemini
async def gemini(target: str, request: Request):
    token_hash, denied = authenticate_model_call(request)
    if denied:
        return denied
    if not ALLOWED_GEMINI:
        # Off by default (D1: Claude only). 403 with its own type, not the 404 of an unknown model: the engine marks
        # Gemini unavailable on a 403 instead of walking its fallback models, and gemini_disabled is not the
        # permission_error of a disabled install, so the install keeps working for Claude.
        return error(403, "gemini_disabled", "Gemini is off on this proxy. miyagi uses Claude.")
    if not GEMINI_KEY:
        return error(503, "upstream_not_configured", "Gemini is not configured on this proxy.")
    model, _, method = target.partition(":")
    model = model.removeprefix("models/")
    if method not in GEMINI_METHODS:
        return error(404, "not_found_error", "Use {model}:generateContent or {model}:streamGenerateContent.")
    if not _GEMINI_MODEL_RE.fullmatch(model) or model not in ALLOWED_GEMINI:
        # 404 like Google's own unknown-model reply, so the engine skips to its next fallback model at once
        return error(404, "not_found", f"Model not available on this proxy. Allowed: {', '.join(ALLOWED_GEMINI)}.")
    request.state.model = model
    call = open_call(request, token_hash, "gemini", model)  # caps checked, per-token slot taken before the body
    if isinstance(call, JSONResponse):
        return call
    try:
        raw = await read_body(request)  # bounded in time: a slow body holds only this install's own slot
        if raw is None:
            call.finish()
            return request_timeout()
        try:  # bounded while parsing (JSON_MAX_OBJECTS) and counted before anything is copied
            clean, _ = sanitize_gemini(parse_json_object(raw))
        except BadBody as e:
            call.finish()
            return error(400, "invalid_request_error", str(e))
        del raw
        payload = json.dumps(clean).encode()
        reserve = gemini_reserve(clean, model, len(payload))
        del clean  # only the encoded payload is held while the call is upstream
        if not call.take_global():  # the global slot only once the body is here
            call.finish()
            return too_many_inflight("global")
        if denied := call.admit(reserve):
            call.finish()
            return denied
    except BaseException:
        call.finish()
        raise
    params = {"alt": "sse"} if request.query_params.get("alt") == "sse" else {}
    headers = {"x-goog-api-key": GEMINI_KEY, "content-type": "application/json", "accept-encoding": "identity"}
    return await forward(call, GEMINI_URL.format(model=model, method=method), headers, params, payload,
                         stream=GEMINI_METHODS[method])


# --------------------------------------------------------------------------- shared lesson cache (ROADMAP 3.1, A08)
#
# GET /v1/lessons/{video_id}?schema=N serves only an approved lesson. On a miss an install claims one of its builds
# (POST /v1/lessons/{video_id}/build; the free tier gets FREE_LESSON_BUILDS_PER_MONTH new videos a month), builds,
# and uploads the result (PUT). An upload is a pending candidate for that video, schema and uploader: nobody else
# sees it until an operator approves it (POST /admin/lessons/{video_id}/approve), or LESSON_AUTO_APPROVE_N uploaders
# on different networks sent the very same lesson. Cache hits are free.

VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")  # YouTube video ids: the only lesson source the engine builds from
_BAD_VIDEO_ID = "video_id must be an 11-character YouTube video id."
RUN_COMMAND_RE = re.compile(r"(?:python3?|pytest|node|npm run) [A-Za-z0-9_./ -]+")
NOTEBOOK_RUN = "Run the cell (Shift+Enter)"  # what the engine writes as a notebook step's run_command: never run
PYTHON_MODULES_OK = frozenset({"pytest", "unittest", "venv", "flask", "streamlit"})  # python -m <one of these>
PYTHON_FLAGS_OK = frozenset({"-u", "-B", "-O"})
_REFUSED_ANYWHERE = ("--require", "--import", "--eval", "--print", "--loader", "--experimental-loader", "--inspect")
_PYTEST_REFUSED = ("-p", "-c", "--pyargs", "--rootdir", "--confcutdir")  # load plugins / config from elsewhere
_LIB_NAME_RE = re.compile(r"(?:@[a-z0-9][a-z0-9._-]{0,60}/)?[A-Za-z0-9][A-Za-z0-9._-]{0,80}(?:\[[A-Za-z0-9_,-]{1,80}\])?")
_LIB_VERSION_PART = r"[<>=!~^]{0,3}[0-9A-Za-z*][0-9A-Za-z.*+-]{0,30}"
_LIB_VERSION_RE = re.compile(rf"{_LIB_VERSION_PART}(?:,{_LIB_VERSION_PART}){{0,3}}")
_TOOL_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
_MAX_LESSON_STR = 20_000
_MAX_LESSON_DEPTH = 12

# The keys a shared lesson may carry: the engine's video draft (server/lesson/schema.py VIDEO_DRAFT_SCHEMA) and the
# step graph builder.assemble() makes from it. Anything else is refused, so nothing an engine might act on
# (a precision check's command, a workdir) passes unchecked.
LESSON_KEYS = frozenset({"title", "summary", "libraries", "files", "steps", "lesson", "sources"})
LESSON_META_KEYS = frozenset({"id", "title", "goal", "summary", "libraries"})
STEP_KEYS = frozenset({"start", "end", "title", "instructions", "file", "code", "run_command", "expected_output", "checks",
                       "targets", "explanations", "hints", "common_mistakes", "id", "index", "video", "precision_checks",
                       "sample_output", "solution", "setup", "requires"})
CHECK_KEYS = frozenset({"id", "type", "label", "app", "metric_pattern", "file", "pattern", "command", "metric", "op", "value",
                        "by_step", "trend", "window"})
CHECK_TYPES = frozenset({"screen_contains", "screen_absent", "metric_threshold", "metric_trend", "file_exists",
                         "file_contains", "command_exit_ok", "output_contains"})
TARGET_KEYS = frozenset({"app", "file", "match", "caption"})
EXPLANATION_KEYS = frozenset({"topic", "t", "sourceId"})
VIDEO_KEYS = frozenset({"sourceId", "start", "end"})
SOURCE_KEYS = frozenset({"id", "type", "url", "title"})


def _lesson_schema(schema) -> JSONResponse | int:
    """The schema version as an int, or the 400 to send."""
    if isinstance(schema, bool) or not isinstance(schema, (int, str)) or not str(schema).isdigit() or len(str(schema)) > 6:
        return error(400, "invalid_request_error", "schema must be a positive integer.")
    n = int(schema)
    if n not in LESSON_SCHEMAS:
        supported = ", ".join(str(s) for s in sorted(LESSON_SCHEMAS)) or "none"
        return error(400, "schema_unsupported", f"Lesson schema {n} is not supported here (supported: {supported}).")
    return n


def _ok_command(cmd) -> bool:
    """A command a lesson may suggest or a check may run: python, pytest, node or npm run with plain arguments.
    No shell metacharacters, no URLs (':' is not allowed at all), no parent directories, and nothing that runs code
    written on the command line itself or installs or serves anything: no python -c / -m pip / -m http.server (only
    -m pytest, unittest, venv, flask, streamlit), no node -e / --require / --import, no npx, no pytest -p / -c."""
    if cmd is None or cmd == "":
        return True
    if not isinstance(cmd, str) or len(cmd) > 300:
        return False
    cmd = cmd.strip()
    if cmd in ("pytest", NOTEBOOK_RUN):
        return True
    if not RUN_COMMAND_RE.fullmatch(cmd) or "//" in cmd or "www." in cmd.lower() or ".." in cmd:
        return False
    words = cmd.split()
    if "npx" in words or any(w.startswith(_REFUSED_ANYWHERE) for w in words):
        return False
    prog, args = words[0], words[1:]
    if prog == "npm":  # npm run <script>: a package.json script, by name
        return len(args) >= 2 and not args[1].startswith("-")
    if prog == "pytest":
        return _ok_pytest_args(args)
    i = 0
    if prog.startswith("python"):
        while i < len(args) and args[i] in PYTHON_FLAGS_OK:
            i += 1
        if i < len(args) and args[i] == "-m":
            module = args[i + 1] if i + 1 < len(args) else ""
            return module in PYTHON_MODULES_OK and (module != "pytest" or _ok_pytest_args(args[i + 2:]))
    return i < len(args) and not args[i].startswith("-")  # a script first: options after it are the script's own


def _ok_pytest_args(args: list[str]) -> bool:
    return not any(a.startswith(_PYTEST_REFUSED) for a in args)


def _ok_path(p) -> bool:
    """A file a lesson names: relative, inside the learner's folder (no '..', not absolute, no drive or scheme)."""
    if p is None or p == "":
        return True
    if not isinstance(p, str) or len(p) > 260 or "\x00" in p or ":" in p:
        return False
    if p.startswith(("/", "\\", "~")):
        return False
    return ".." not in re.split(r"[\\/]", p)


def _ok_source(s) -> bool:
    if isinstance(s, dict) and set(s) - SOURCE_KEYS:
        return False
    url = s.get("url") if isinstance(s, dict) else s
    return isinstance(url, str) and url.startswith("https://") and len(url) <= 2000 and not re.search(r"\s", url)


def _library_pairs(libs) -> list[tuple] | None:
    """[(name, version)] from the draft's [{name, version}] or the graph's {name: version}; None when malformed."""
    if libs is None:
        return []
    if isinstance(libs, dict):
        return list(libs.items())
    if isinstance(libs, list) and all(isinstance(x, dict) and not set(x) - {"name", "version"} for x in libs):
        return [(x.get("name"), x.get("version")) for x in libs]
    return None


def _ok_libraries(libs) -> bool:
    """The engine pip-installs lesson libraries (server/workspace/setup.py): plain package names and versions
    only. No URLs, no git+, no paths, no options."""
    pairs = _library_pairs(libs)
    if pairs is None or len(pairs) > 100:
        return False
    for name, version in pairs:
        if not isinstance(name, str) or not _LIB_NAME_RE.fullmatch(name):
            return False
        if version not in (None, "") and not (isinstance(version, str) and _LIB_VERSION_RE.fullmatch(version)):
            return False
    return True


def _walk_bounded(v, depth: int = 0) -> bool:
    """Every string bounded, nesting shallow, keys short, lists not huge."""
    if depth > _MAX_LESSON_DEPTH:
        return False
    if isinstance(v, str):
        return len(v) <= _MAX_LESSON_STR
    if isinstance(v, dict):
        return all(isinstance(k, str) and len(k) <= 100 and _walk_bounded(x, depth + 1) for k, x in v.items())
    if isinstance(v, list):
        return len(v) <= 1000 and all(_walk_bounded(x, depth + 1) for x in v)
    return v is None or isinstance(v, (bool, int, float))


def _items(v) -> list:
    return v if isinstance(v, list) else []


def _extra(d: dict, allowed: frozenset) -> str | None:
    extra = sorted(k for k in d if k not in allowed)
    return extra[0][:40] if extra else None


def _check_problem(c) -> str | None:
    if not isinstance(c, dict):
        return "checks must be objects"
    if key := _extra(c, CHECK_KEYS):
        return f"unknown check key {key!r}"
    if "type" in c and c["type"] not in CHECK_TYPES:
        return f"unknown check type {str(c['type'])[:40]!r}"
    if not _ok_path(c.get("file")):
        return "check files must be relative paths inside the project"
    if not _ok_command(c.get("command")):
        return "check commands must be plain python, pytest, node or npm run"
    return None


def _step_problem(s: dict) -> str | None:
    if key := _extra(s, STEP_KEYS):
        return f"unknown step key {key!r}"
    if not _ok_command(s.get("run_command")):
        return "run_command must be python, pytest, node or npm run with plain arguments"
    if not _ok_path(s.get("file")):
        return "file must be a relative path inside the project"
    for c in _items(s.get("checks")) + _items(s.get("precision_checks")):
        if why := _check_problem(c):
            return why
    for t in _items(s.get("targets")):
        if not isinstance(t, dict) or _extra(t, TARGET_KEYS) or not _ok_path(t.get("file")):
            return "targets must be {app, file, match, caption} with relative files"
    for e in _items(s.get("explanations")):
        if not isinstance(e, dict) or _extra(e, EXPLANATION_KEYS):
            return "explanations must be {topic, t, sourceId}"
    if "video" in s and (not isinstance(s["video"], dict) or _extra(s["video"], VIDEO_KEYS)):
        return "video must be {sourceId, start, end}"
    if not all(isinstance(r, str) and _TOOL_ID_RE.fullmatch(r) for r in _items(s.get("requires"))):
        return "requires must be tool ids"
    return None


def validate_lesson(lesson) -> str | None:
    """Why this uploaded lesson is refused, or None. Engines pip-install its libraries, run its commands and open
    its files on learners' Macs, so the shape matters as much as the size."""
    if not isinstance(lesson, dict):
        return "lesson must be an object with 1 to 300 steps."
    steps = lesson.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 300 or not all(isinstance(s, dict) for s in steps):
        return "lesson must be an object with 1 to 300 steps."
    if not _walk_bounded(lesson):
        return f"lesson has a string over {_MAX_LESSON_STR} characters or is nested too deep."
    if key := _extra(lesson, LESSON_KEYS):
        return f"unknown lesson key {key!r}."
    meta = lesson.get("lesson")
    if meta is not None and (not isinstance(meta, dict) or _extra(meta, LESSON_META_KEYS)):
        return f"lesson.lesson may only hold {', '.join(sorted(LESSON_META_KEYS))}."
    if not _ok_libraries(lesson.get("libraries")) or not _ok_libraries((meta or {}).get("libraries")):
        return "libraries must be plain package names with plain versions (no URLs, git+, paths or options)."
    if not all(_ok_path(f) for f in _items(lesson.get("files"))):
        return "lesson files must be relative paths inside the project (no '..', not absolute)."
    if not all(_ok_source(s) for s in _items(lesson.get("sources"))):
        return "lesson sources must be https URLs."
    for i, s in enumerate(steps, 1):
        if why := _step_problem(s):
            return f"step {i}: {why}."
    return None


def lesson_review(lesson) -> dict:
    """What a reviewer must see before approving a lesson: the libraries it installs, every command it suggests or
    runs, and the files it touches."""
    if not isinstance(lesson, dict):
        return {"libraries": [], "commands": [], "files": []}
    libs = (_library_pairs(lesson.get("libraries")) or []) + (_library_pairs((lesson.get("lesson") or {}).get("libraries")) or [])
    commands, files = [], list(_items(lesson.get("files")))
    for s in _items(lesson.get("steps")):
        if not isinstance(s, dict):
            continue
        commands.append(s.get("run_command"))
        files.append(s.get("file"))
        for c in _items(s.get("checks")) + _items(s.get("precision_checks")):
            if isinstance(c, dict):
                commands.append(c.get("command"))
                files.append(c.get("file"))
    def uniq(xs):
        return list(dict.fromkeys(x for x in xs if isinstance(x, str) and x))[:100]
    return {"libraries": uniq(f"{n} {v or ''}".strip() for n, v in libs if isinstance(n, str)),
            "commands": uniq(commands), "files": uniq(files)}


def lesson_disk_full() -> bool:
    """The database's disk is over LESSON_DISK_MAX_PCT: lesson uploads stop before the proxy runs out of room."""
    try:
        u = shutil.disk_usage(os.path.dirname(os.path.abspath(store.path)) or ".")
    except OSError:
        return False
    return u.total > 0 and u.used * 100 / u.total > LESSON_DISK_MAX_PCT


def _build_user(token_hash: str) -> str | None:
    """The Supabase user whose builds this install's count with (None: anonymous, the install's own count)."""
    link = store.get_link(token_hash)
    return link["user_id"] if link else None


def _build_quota(token_hash: str, user_id: str | None = None) -> dict:
    """New-lesson builds this month: this install's, or with `user_id` every install linked to that user together
    (distinct videos). cap 0 means no cap (the pro plan, or the cap turned off)."""
    row = store.get_token(token_hash) or {}
    cap = 0 if row.get("plan") == "pro" else max(FREE_LESSON_BUILDS_PER_MONTH, 0)
    return {"used": store.builds_in_month(token_hash, user_id=user_id), "cap": cap, "month": this_month(),
            "resets_at": _iso(_next_utc_month())}


@app.get("/v1/lessons/{video_id}")
async def get_lesson(video_id: str, request: Request):
    token_hash, denied = authenticate(request)
    if denied:
        return denied
    if not VIDEO_ID_RE.fullmatch(video_id):
        return error(400, "invalid_request_error", _BAD_VIDEO_ID)
    schema = _lesson_schema(request.query_params.get("schema", ""))
    if isinstance(schema, JSONResponse):
        return schema
    row = store.get_lesson(video_id, schema)
    if row is None:
        body = {"type": "error", "error": {"type": "lesson_not_cached", "status": "LESSON_NOT_CACHED", "code": 404,
                                           "message": "No shared lesson for this video yet.",
                                           "builds": _build_quota(token_hash, _build_user(token_hash))}}  # builds left
        return JSONResponse(body, status_code=404)
    request.state.model = "lesson-cache"
    # the stored body is a validated JSON object: splice it in rather than parse and re-encode it
    head = json.dumps({"video_id": video_id, "schema": schema, "created_at": round(row["created_at"])})[:-1]
    return Response(f'{head}, "lesson": {row["body"]}}}'.encode("utf-8"), media_type="application/json")


@app.post("/v1/lessons/{video_id}/build")
async def claim_lesson_build(video_id: str, request: Request):
    """Use one of this month's new-lesson builds for `video_id` (free for a video already claimed this month). The
    gate to the expensive build calls, so it needs a sign-in when REQUIRE_SIGNIN is on."""
    token_hash, denied = authenticate_model_call(request)
    if denied:
        return denied
    if not VIDEO_ID_RE.fullmatch(video_id):
        return error(400, "invalid_request_error", _BAD_VIDEO_ID)
    user_id = _build_user(token_hash)
    quota = _build_quota(token_hash, user_id)
    ok, used = store.claim_build(token_hash, video_id, quota["cap"], user_id=user_id)
    if not ok:
        return quota_error("miyagi_lesson_quota", "lesson_builds", used, quota["cap"], _next_utc_month(),
                           f"You've built your {quota['cap']} free lessons this month. "
                           "Lessons someone already built still open for free.")
    return {"ok": True, "builds": {**quota, "used": used}}


@app.put("/v1/lessons/{video_id}")
async def put_lesson(video_id: str, request: Request):
    token_hash, denied = authenticate(request)
    if denied:
        return denied
    if not VIDEO_ID_RE.fullmatch(video_id):
        return error(400, "invalid_request_error", _BAD_VIDEO_ID)
    if lesson_disk_full():
        log.error("lesson upload refused: the database disk is over %s%% full", LESSON_DISK_MAX_PCT)
        return error(507, "insufficient_storage", "The lesson cache is full right now. Your lesson still works on this Mac.")
    too_big = error(413, "request_too_large", f"Lesson over {MAX_LESSON_BYTES // 1024} KB.")
    raw_cap = 6 * MAX_LESSON_BYTES + 1024  # \uXXXX escapes (json.dumps' default) are up to 6x the stored UTF-8
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > raw_cap:
        return too_big
    raw = await read_body(request)
    if raw is None:
        return request_timeout()
    if len(raw) > raw_cap:
        return too_big
    data = _json_object(raw)
    if data is None:
        return error(400, "invalid_request_error", 'Body must be {"schema": N, "lesson": {...}}.')
    schema = _lesson_schema(data.get("schema"))
    if isinstance(schema, JSONResponse):
        return schema
    lesson = data.get("lesson")
    if why := validate_lesson(lesson):
        return error(400, "invalid_request_error", why)
    body = json.dumps(lesson, separators=(",", ":"), ensure_ascii=False)
    if len(body.encode("utf-8")) > MAX_LESSON_BYTES:  # the size we would store, after encoding
        return too_big
    if not store.has_build(token_hash, video_id):  # only an install that built this video may share it
        return error(403, "build_not_claimed", "Claim a build of this video (POST /v1/lessons/{video_id}/build) before sharing it.")
    ok, used = store.claim_lesson_put(token_hash, LESSON_PUTS_PER_DAY)
    if not ok:
        return quota_error("rate_limit_error", "lesson_uploads", used, LESSON_PUTS_PER_DAY, _next_utc_midnight(),
                           "This install has shared enough lessons for today.")
    digest = lesson_hash(lesson)
    full = store.put_candidate(video_id, schema, token_hash, body, digest, ip_net(client_ip(request)),
                               max_pending_bytes=LESSON_PENDING_MAX_BYTES, max_net_bytes=LESSON_PENDING_PER_NET_BYTES,
                               max_age_s=LESSON_PENDING_MAX_DAYS * 86400)
    if full:
        log.warning("lesson upload refused: %s pending-bytes bound reached",
                    "the total" if full == "pending_total" else "its network's")
        return error(507, "insufficient_storage", "Too many lessons are waiting for review right now. "
                     "Your lesson still works on this Mac.")
    approved = store.auto_approve(video_id, schema, digest, LESSON_AUTO_APPROVE_N)
    if approved:
        log.info("lesson %s schema %s auto-approved (%d matching uploads)", video_id, schema, LESSON_AUTO_APPROVE_N)
    return JSONResponse({"stored": True, "status": "approved" if approved else "pending", "video_id": video_id,
                         "schema": schema, "hash": digest[:16]}, status_code=201)


# --------------------------------------------------------------------------- product events: POST /v1/events
#
# The app (main/features/telemetry.ts, only while "Share crash reports and usage" is on) and the engine send
#   Authorization: Bearer <mi_ install token>
#   {"events": [{"name": "step_passed", "at": "<ISO time>", "props": {...}}, ...]}   (extra top-level fields ignored)
# at most EVENTS_MAX per request and EVENTS_MAX_BYTES of body. We keep counts only: per install, UTC day and event
# name, plus allowlisted scalar props (EVENT_PROP_KEYS) as counts per value or sums. Unknown names, other props
# (a crash's message included) and malformed events are dropped, never stored. 202 {"ok": true}; 401 bad token;
# 413 too big; 400 when the body is not that shape.

EVENTS_MAX = 50
EVENTS_MAX_BYTES = 32 * 1024
EVENTS_PER_DAY = _env_int("EVENTS_PER_DAY_PER_INSTALL", 2000)  # beyond it events are dropped (still 202)
# The app's list (app/src/main/features/telemetry/core.ts EVENT_NAMES).
EVENT_NAMES = frozenset(_env_list("EVENT_NAMES", "app_installed,onboarding_done,lesson_search,lesson_built,step_passed,"
                                  "step_failed_check,hint_used,lesson_completed,lesson_abandoned,cost_usd,crash"))
EVENT_PROP_KEYS = frozenset(_env_list("EVENT_PROP_KEYS", "kind,mode,reason,source,built_by,step_kind,level,cached,"
                                      "provider,model,usd,steps,minutes,seconds"))
_EVENT_WORD = re.compile(r"[A-Za-z0-9_.\- ]{1,40}")  # enum-like values only: never sentences, paths or quotes
_EVENT_DAYS_BACK = 2  # an event's own day is kept when it is this recent; older or future times count as today


def _event_day(at) -> str:
    today = datetime.now(UTC).date()
    try:
        t = datetime.fromisoformat(at) if isinstance(at, str) and len(at) <= 40 else None
    except ValueError:
        t = None
    if t is not None:
        d = (t if t.tzinfo else t.replace(tzinfo=UTC)).astimezone(UTC).date()
        if today - timedelta(days=_EVENT_DAYS_BACK) <= d <= today:
            return d.isoformat()
    return today.isoformat()


def _event_props(raw) -> dict:
    """Only allowlisted keys with a boolean, a finite number or a short enum-like string."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if k not in EVENT_PROP_KEYS:
            continue
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, (int, float)) and abs(v) < 1e9:  # NaN and inf fail this too
            out[k] = v
        elif isinstance(v, str) and _EVENT_WORD.fullmatch(v.strip()):
            out[k] = v.strip()
    return out


@app.post("/v1/events")
async def events(request: Request):
    token = presented_token(request)
    h = hash_token(token) if token and len(token) <= 200 else None
    row = store.get_token(h) if h else None
    if row is None or row["disabled"]:
        return error(401, "authentication_error", "Missing or invalid install token.")
    request.state.tok = h[:PREFIX_LEN]
    too_big = error(413, "request_too_large", f"At most {EVENTS_MAX} events and {EVENTS_MAX_BYTES // 1024} KB per request.")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > EVENTS_MAX_BYTES:
        return too_big
    raw = await read_body(request)
    if raw is None:
        return request_timeout()
    if len(raw) > EVENTS_MAX_BYTES:
        return too_big
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        data = None
    items = data.get("events") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return error(400, "invalid_request_error", 'Body must be {"events": [{"name", "at", "props"}, ...]}.')
    if len(items) > EVENTS_MAX:
        return too_big
    kept = [(_event_day(e.get("at")), e["name"], _event_props(e.get("props")))
            for e in items if isinstance(e, dict) and isinstance(e.get("name"), str) and e["name"] in EVENT_NAMES]
    store.add_events(h, kept, EVENTS_PER_DAY)
    return JSONResponse({"ok": True}, status_code=202)


# --------------------------------------------------------------------------- admin

def admin_ok(request: Request, token: str | None) -> bool:
    """The presented admin token matches (constant time). A miss is recorded against the client's IP bucket:
    ADMIN_LOCKOUT_FAILURES of them within an hour lock that bucket out of /admin (RateLimit). The log line names
    the bucket's keyed hash only (never the address), never what was presented."""
    if ADMIN_ENABLED and isinstance(token, str) and token and hmac.compare_digest(token.encode(), ADMIN_TOKEN.encode()):
        return True
    bucket = getattr(request.state, "ip_bucket", None) or ip_bucket(client_ip(request))
    n = admin_failures.record(bucket)
    log.warning("admin auth failed from network %s (%d in the last hour)", store.hash_net(bucket), n)
    return False


def require_admin(request: Request) -> JSONResponse | None:
    if not admin_ok(request, request.headers.get("x-admin-token")):
        return error(401, "authentication_error", "Admin token required (X-Admin-Token header).")
    return None


_PREFIX_RE = re.compile(r"[0-9a-f]{8,64}")
_BAD_PREFIX = "Prefix must be 8-64 lowercase hex characters of the token hash."


@app.get("/admin/usage")
async def admin_usage(request: Request, days: int = 30):
    if denied := require_admin(request):
        return denied
    return store.usage_report(max(1, min(days, 365)))


def _proxy_state() -> dict:
    return {"paused": store.paused(), "proxy_enabled_env": PROXY_ENABLED, "daily_usd_brake": DAILY_USD_CAP or None,
            "new_installs_today": store.new_installs_on(), "new_installs_per_day": NEW_INSTALLS_PER_DAY or None,
            "alert_daily_usd": ALERT_DAILY_USD or None, "alerts": bool(ALERT_WEBHOOK_URL)}


@app.get("/admin/proxy")
async def admin_proxy_state(request: Request):
    if denied := require_admin(request):
        return denied
    return _proxy_state()


@app.post("/admin/proxy/pause")
@app.post("/admin/proxy/resume")
async def admin_proxy_pause(request: Request):
    """The runtime kill switch: pause stops every /v1 route (503 proxy_disabled, what the engine shows as "paused")
    within one request, with no redeploy; resume undoes it. Persisted in SQLite (survives restarts and deploys).
    PROXY_ENABLED=false still wins: resume cannot turn on a proxy the environment turned off."""
    if denied := require_admin(request):
        return denied
    pause = request.url.path.endswith("/pause")
    store.set_paused(pause)
    log.warning("admin: proxy %s at runtime", "PAUSED" if pause else "resumed")
    return _proxy_state()


@app.post("/admin/alerts/test")
async def admin_test_alert(request: Request):
    """Send one test alert, to check that ALERT_WEBHOOK_URL reaches both founders. Deduped like every alert: once a
    UTC day (key "test")."""
    if denied := require_admin(request):
        return denied
    sent = alert("test", "miyagi-cloud: test alert. Alerts reach this channel.")
    return {"alerts": bool(ALERT_WEBHOOK_URL), "sent": sent}


@app.post("/admin/tokens/{prefix}/disable")
@app.post("/admin/tokens/{prefix}/enable")
async def admin_set_disabled(prefix: str, request: Request):
    if denied := require_admin(request):
        return denied
    if not _PREFIX_RE.fullmatch(prefix):
        return error(400, "invalid_request_error", _BAD_PREFIX)
    disable = request.url.path.endswith("/disable")
    matched = store.set_disabled(prefix, disable)
    if not matched:
        return error(404, "not_found_error", "No token hash starts with that prefix.")
    if len(matched) > 1:
        return error(409, "conflict", f"{len(matched)} tokens match; use a longer prefix.")
    log.info("admin: token %s %s", prefix[:PREFIX_LEN], "disabled" if disable else "enabled")
    return {"token": matched[0][:PREFIX_LEN], "disabled": disable}


class PlanBody(BaseModel):
    plan: str = Field(min_length=1, max_length=16)


@app.post("/admin/tokens/{prefix}/plan")
async def admin_set_plan(prefix: str, request: Request):
    """Move one install between the free tier (caps apply) and pro (no per-install caps)."""
    if denied := require_admin(request):
        return denied
    if not _PREFIX_RE.fullmatch(prefix):
        return error(400, "invalid_request_error", _BAD_PREFIX)
    body = await read_model(request, PlanBody)
    if isinstance(body, JSONResponse):
        return body
    if body.plan not in PLANS:
        return error(400, "invalid_request_error", f"plan must be one of: {', '.join(PLANS)}.")
    matched = store.set_plan(prefix, body.plan)
    if not matched:
        return error(404, "not_found_error", "No token hash starts with that prefix.")
    if len(matched) > 1:
        return error(409, "conflict", f"{len(matched)} tokens match; use a longer prefix.")
    log.info("admin: token %s plan=%s", prefix[:PREFIX_LEN], body.plan)
    return {"token": matched[0][:PREFIX_LEN], "plan": body.plan}


@app.get("/admin/lessons/pending")
async def admin_pending_lessons(request: Request):
    """Uploaded lessons nobody approved yet: video, schema, body hash (16 hex), uploader token prefix, size, and what
    a reviewer must read before approving: the libraries it installs, its commands and its files."""
    if denied := require_admin(request):
        return denied
    out = []
    for p in store.pending_lessons():
        try:
            review = lesson_review(json.loads(p.pop("body")))
        except ValueError:
            review = {"libraries": [], "commands": [], "files": [], "unreadable": True}
        out.append({**p, **review, "full": f"/admin/lessons/{p['video_id']}/candidates/{p['hash']}"})
    return {"pending": out}


_HASH_PREFIX_RE = re.compile(r"[0-9a-f]{8,64}")


@app.get("/admin/lessons/{video_id}/candidates/{hash_prefix}")
async def admin_lesson_candidate(video_id: str, hash_prefix: str, request: Request, schema: int | None = None):
    """The whole body of the candidates whose hash starts with `hash_prefix`: every instruction, code block,
    solution, hint and explanation learners would receive, to read before POST /admin/lessons/{video_id}/approve.
    The review summary (libraries, commands, files) comes with each."""
    if denied := require_admin(request):
        return denied
    if not VIDEO_ID_RE.fullmatch(video_id):
        return error(400, "invalid_request_error", _BAD_VIDEO_ID)
    if not _HASH_PREFIX_RE.fullmatch(hash_prefix):
        return error(400, "invalid_request_error", "hash must be 8-64 lowercase hex characters of the body hash.")
    rows = store.lesson_candidates(video_id, hash_prefix, schema)
    if not rows:
        return error(404, "not_found_error", "No candidate of that video has that hash.")
    out = []
    for r in rows:
        try:
            lesson = json.loads(r.pop("body"))
        except ValueError:
            lesson = None
        out.append({**r, **lesson_review(lesson), "lesson": lesson})
    return JSONResponse({"video_id": video_id, "candidates": out}, headers={"cache-control": "no-store"})


class ApproveBody(BaseModel):
    hash: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-f]+$")
    schema_: int | None = Field(default=None, alias="schema")


@app.post("/admin/lessons/{video_id}/approve")
async def admin_approve_lesson(video_id: str, request: Request):
    """Serve one candidate of this video, chosen by its body hash (prefix from /admin/lessons/pending)."""
    if denied := require_admin(request):
        return denied
    if not VIDEO_ID_RE.fullmatch(video_id):
        return error(400, "invalid_request_error", _BAD_VIDEO_ID)
    body = await read_model(request, ApproveBody)
    if isinstance(body, JSONResponse):
        return body
    groups = store.approve_lesson(video_id, body.hash, body.schema_)
    if not groups:
        return error(404, "not_found_error", "No candidate of that video has that hash.")
    if len(groups) > 1:
        return error(409, "conflict", f"{len(groups)} candidates match; use a longer hash or give the schema.")
    log.info("admin: approved lesson %s schema %s hash %s", video_id, groups[0]["schema"], groups[0]["body_hash"][:16])
    return {"video_id": video_id, "schema": groups[0]["schema"], "hash": groups[0]["body_hash"][:16], "status": "approved"}


@app.delete("/admin/lessons/by-uploader/{prefix}")
async def admin_delete_lessons_by_uploader(prefix: str, request: Request):
    """Drop every lesson (approved or pending) one install uploaded: the purge for an abusive uploader."""
    if denied := require_admin(request):
        return denied
    if not _PREFIX_RE.fullmatch(prefix):
        return error(400, "invalid_request_error", _BAD_PREFIX)
    n = store.delete_lessons_by_uploader(prefix)
    log.info("admin: deleted %d lesson(s) by uploader %s", n, prefix[:PREFIX_LEN])
    return {"uploader": prefix[:PREFIX_LEN], "deleted": n}


@app.delete("/admin/lessons/{video_id}")
async def admin_delete_lesson(video_id: str, request: Request):
    """Drop every candidate of a video (every schema, approved or not) so the next install builds it again."""
    if denied := require_admin(request):
        return denied
    if not VIDEO_ID_RE.fullmatch(video_id):
        return error(400, "invalid_request_error", _BAD_VIDEO_ID)
    n = store.delete_lessons(video_id)
    log.info("admin: deleted %d shared lesson(s)", n)
    return {"video_id": video_id, "deleted": n}


@app.get("/admin/deletions")
async def admin_deletions(request: Request):
    """Account deletions whose Supabase user is not deleted yet (their cloud data already is)."""
    if denied := require_admin(request):
        return denied
    return JSONResponse({"pending": store.deletion_requests(), "service_key": bool(SUPABASE_SERVICE_ROLE_KEY)},
                        headers={"cache-control": "no-store"})


@app.post("/admin/deletions/retry")
async def admin_retry_deletions(request: Request):
    """Retry every pending deletion: wipe again whatever the account linked since, then delete the Supabase user."""
    if denied := require_admin(request):
        return denied
    done = 0
    for r in store.deletion_requests():
        await run_in_threadpool(store.delete_account, None, r["user_id"])
        done += await finish_account_delete(r["user_id"]) == "deleted"
    left = store.deletion_requests()
    log.info("admin: retried account deletions: %d deleted, %d pending", done, len(left))
    return {"deleted": done, "pending": left}


_ADMIN_HEADERS = {"cache-control": "no-store", "x-frame-options": "DENY", "referrer-policy": "no-referrer",
                  "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"}
_STYLE = ("body{font:14px system-ui,sans-serif;margin:24px;color:#111;background:#fff}table{border-collapse:collapse;margin:8px 0 24px}"
          "td,th{border:1px solid #ccc;padding:4px 8px;text-align:right}th{background:#f3f3f3}td:first-child,th:first-child{text-align:left}"
          "code{font-size:13px}")


def _table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "<p>No usage yet.</p>"
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(r.get(c, '')))}</td>" for c in cols) + "</tr>" for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _page(inner: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html><head><meta charset=utf-8><title>miyagi-cloud admin</title>"
                        f"<style>{_STYLE}</style></head><body><h1>miyagi-cloud admin</h1>{inner}</body></html>", headers=_ADMIN_HEADERS)


_LOGIN = ("<form method=post action=/admin><label>Admin token <input type=password name=admin_token autocomplete=off "
          "autofocus></label> <button>Show usage</button></form>")


@app.get("/admin")
async def admin_page():
    return _page(_LOGIN)


ADMIN_FORM_MAX_BODY = SMALL_BODY_MAX  # the login form: one token field


@app.post("/admin")
async def admin_page_post(request: Request):
    if too_big := small_body_too_large(request, ADMIN_FORM_MAX_BODY):
        return too_big
    raw = await read_body(request)
    if raw is None:
        return request_timeout()
    if len(raw) > ADMIN_FORM_MAX_BODY:
        return error(413, "request_too_large", f"Request body over {ADMIN_FORM_MAX_BODY // 1024} KB.")
    form = parse_qs(raw.decode("utf-8", "replace"))  # urlencoded form, no multipart dependency
    if not admin_ok(request, (form.get("admin_token") or [""])[0]):
        return _page("<p>Wrong token.</p>" + _LOGIN)
    r = store.usage_report(30)
    t = r["total"]
    summary = (f"<p>Since {html.escape(r['since'])}: <b>{t['requests']}</b> requests, {t['input_tokens']} input / "
               f"{t['output_tokens']} output tokens, est. <b>${t['usd']}</b>. Tokens registered: {r['registered_tokens']} "
               f"({r['disabled_tokens']} disabled). Proxy enabled: {PROXY_ENABLED}. "
               f"Paused at runtime: <b>{r['paused']}</b> (POST /admin/proxy/pause or /resume).</p>"
               f"<p>Shared lessons: {r['lessons']['cached']} approved, {r['lessons']['pending']} pending review, "
               f"{r['lessons']['hits']} cache hits, {r['lessons']['builds_this_month']} new builds this month.</p>"
               f"<p>Est. spend today (UTC): <b>${r['usd_today']}</b>; alert line: "
               f"{'$' + str(ALERT_DAILY_USD) if ALERT_DAILY_USD > 0 else 'off'} (alerts {'on' if ALERT_WEBHOOK_URL else 'off'}); "
               f"global spend brake: {'$' + str(DAILY_USD_CAP) if DAILY_USD_CAP > 0 else 'off'}.</p>"
               f"<p>New installs today: {r['new_installs_today']} of "
               f"{NEW_INSTALLS_PER_DAY if NEW_INSTALLS_PER_DAY > 0 else 'no cap'}. Alerts sent today: "
               f"{html.escape(', '.join(r['alerts_today'])) or 'none'}.</p>"
               f"<p>Account deletions pending (Supabase user not deleted yet): <b>{len(store.deletion_requests())}</b> "
               f"(GET /admin/deletions, POST /admin/deletions/retry).</p>")
    cols = ["requests", "input_tokens", "output_tokens", "usd"]
    return _page(summary + "<h2>Per day</h2>" + _table(r["by_day"], ["day", "tokens", *cols])
                 + "<h2>Events per day</h2>" + _table(r["events"], ["day", "name", "count", "installs"])
                 + "<h2>Per install token (hash prefix)</h2>" + _table(r["by_token"], ["token", "disabled", *cols])
                 + "<h2>Per day, token and model</h2>" + _table(r["by_day_token_model"], ["day", "token", "provider", "model", *cols])
                 + "<p>Disable a token: <code>curl -X POST -H 'X-Admin-Token: …' $URL/admin/tokens/&lt;prefix&gt;/disable</code></p>")
