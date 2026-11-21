"""miyagi-cloud: the API key proxy for the Miyagi desktop tutor.

Every user's AI calls come here with an anonymous install token. We hold the Anthropic and
Gemini keys, enforce model allowlists and caps, forward the call, and count usage per token.

Logs carry method, path, status, latency, model, token counts and the token-hash prefix only:
never bodies, prompts, screenshots, tokens or keys.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import sys
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from store import PREFIX_LEN, Store, open_store

VERSION = "0.1.0"
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


ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
if len(ADMIN_TOKEN) < 4:
    raise SystemExit("miyagi-cloud: ADMIN_TOKEN is not set. Refusing to start without an admin token.")

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
PROXY_ENABLED = _env_bool("PROXY_ENABLED", True)
ALLOWED_ANTHROPIC = _env_list("ALLOWED_ANTHROPIC_MODELS", "claude-sonnet-5-5,claude-haiku-5-5")
ALLOWED_GEMINI = _env_list("ALLOWED_GEMINI_MODELS", "gemini-3.8-flash")
MAX_TOKENS_CAP = int(os.environ.get("MAX_TOKENS_CAP", "4096"))
ALLOW_FAST_MODE = _env_bool("ALLOW_FAST_MODE", False)  # speed:"fast" bills 2x
ANTHROPIC_VERSION = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")
MAX_BODY = int(float(os.environ.get("MAX_BODY_MB", "2")) * 1024 * 1024)
MAX_GEMINI_BODY = int(float(os.environ.get("MAX_GEMINI_BODY_MB", "20")) * 1024 * 1024)
REGISTER_PER_HOUR = int(os.environ.get("REGISTER_LIMIT_PER_HOUR", "10"))
PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS", "1"))  # Render's load balancer appends the client IP
TIMEOUT = httpx.Timeout(connect=10.0, read=float(os.environ.get("UPSTREAM_READ_TIMEOUT_S", "300")), write=60.0, pool=10.0)

if not ANTHROPIC_KEY or not GEMINI_KEY:
    log.warning("missing upstream key(s): anthropic=%s gemini=%s (those routes return 503)",
                "set" if ANTHROPIC_KEY else "MISSING", "set" if GEMINI_KEY else "MISSING")

# USD per 1M tokens (input, output). Estimates for the admin view, not billing.
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


def estimate_usd(model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0) -> float:
    pin, pout = PRICES.get(model, DEFAULT_PRICE)
    plain = max(inp - cache_read - cache_write, 0)
    return (plain * pin + cache_read * pin * 0.1 + cache_write * pin * 1.25 + out * pout) / 1_000_000


# --------------------------------------------------------------------------- app + middleware

store: Store
http: httpx.AsyncClient


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global store, http
    store = open_store()
    http = httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False)
    log.info("miyagi-cloud %s up: db=%s proxy_enabled=%s", VERSION, store.path, PROXY_ENABLED)
    yield
    await http.aclose()


class BodyTooLarge(Exception):
    pass


class Guard:
    """Pure ASGI middleware: kill switch, no browser origins on /v1, body size limit, one log line per request.

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
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}

        async def send_logged(msg):
            if msg["type"] == "http.response.start":
                status[0] = msg["status"]
            await send(msg)

        try:
            if path.startswith("/v1/") and not PROXY_ENABLED:
                return await error(503, "proxy_disabled", "Miyagi cloud AI is paused by the operators. Try again later.")(scope, receive, send_logged)
            if path.startswith("/v1/") and "origin" in headers:
                return await error(403, "forbidden", "Browser origins are not allowed.")(scope, receive, send_logged)
            limit = MAX_GEMINI_BODY if path.startswith("/v1/gemini/") else MAX_BODY
            declared = headers.get("content-length", "")
            if declared.isdigit() and int(declared) > limit:
                return await error(413, "request_too_large", f"Request body over {limit // (1024 * 1024)} MB.")(scope, receive, send_logged)
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
                    await error(413, "request_too_large", f"Request body over {limit // (1024 * 1024)} MB.")(scope, receive, send_logged)
        finally:
            extra = "".join(f" {k}={state[k]}" for k in ("model", "tokens_in", "tokens_out", "tok") if state.get(k) is not None)
            log.info("%s %s %s %dms%s", scope["method"], path, status[0] or 500, (time.monotonic() - start) * 1000, extra)


app = FastAPI(title="miyagi-cloud", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(Guard)  # no CORSMiddleware on purpose: no browser origins


def error(status: int, kind: str, message: str) -> JSONResponse:
    """One error shape both SDKs can read: Anthropic's {type, error:{type,message}} plus Google's code/status."""
    return JSONResponse({"type": "error", "error": {"type": kind, "status": kind.upper(), "code": status, "message": message}},
                        status_code=status)


# --------------------------------------------------------------------------- auth + quota hooks

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def presented_token(request: Request) -> str:
    """Bearer token; SDKs pointed at the proxy may instead send it as x-api-key / x-goog-api-key."""
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return (request.headers.get("x-api-key") or request.headers.get("x-goog-api-key") or "").strip()


def authenticate(request: Request) -> tuple[str | None, JSONResponse | None]:
    token = presented_token(request)
    if not token or len(token) > 200:
        return None, error(401, "authentication_error", "Missing or invalid install token. Register at /v1/register.")
    h = hash_token(token)
    row = store.get_token(h)
    if row is None:
        return None, error(401, "authentication_error", "Unknown install token. Register again at /v1/register.")
    request.state.tok = h[:PREFIX_LEN]
    if row["disabled"]:
        return None, error(403, "permission_error", "This install has been disabled.")
    return h, None


def check_quota(token_hash: str) -> tuple[bool, str]:
    """Hook for per-token limits. Always allows for now.

    TODO: read store.requests_today(token_hash) (and usd) and return (False, reason) over a daily cap.
    """
    return True, ""


def admit(request: Request, token_hash: str, provider: str, model: str) -> JSONResponse | None:
    ok, why = check_quota(token_hash)
    if not ok:
        return error(429, "rate_limit_error", why or "Daily limit reached for this install.")
    store.count_request(token_hash, provider, model)
    return None


_register_hits: dict[str, deque] = defaultdict(deque)


def client_ip(request: Request) -> str:
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if hops and PROXY_HOPS > 0:
        return hops[-min(PROXY_HOPS, len(hops))]
    return request.client.host if request.client else "unknown"


def register_allowed(ip: str) -> bool:
    now, hits = time.time(), _register_hits[ip]
    while hits and hits[0] < now - 3600:
        hits.popleft()
    if len(hits) >= REGISTER_PER_HOUR:
        return False
    hits.append(now)
    if len(_register_hits) > 50_000:  # keep memory bounded
        for k in [k for k, v in _register_hits.items() if not v][:10_000]:
            _register_hits.pop(k, None)
    return True


# --------------------------------------------------------------------------- usage sniffing

_USAGE_RE = re.compile(r'"(input_tokens|output_tokens|cache_read_input_tokens|cache_creation_input_tokens|'
                       r'promptTokenCount|candidatesTokenCount|thoughtsTokenCount|cachedContentTokenCount)"\s*:\s*(\d+)')
_MODEL_RE = re.compile(r'"(?:model|modelVersion)"\s*:\s*"([A-Za-z0-9._\-]{1,80})"')


class Usage:
    """Reads token counts out of a response as it streams by (JSON or SSE). Last value of each field wins,
    which matches both APIs: Anthropic's message_delta and Gemini's final chunk carry cumulative totals."""

    def __init__(self) -> None:
        self.fields: dict[str, int] = {}
        self.model: str | None = None
        self._tail = ""

    def feed(self, chunk: bytes) -> None:
        text = self._tail + chunk.decode("latin-1")
        for name, n in _USAGE_RE.findall(text):
            self.fields[name] = int(n)
        if self.model is None and (m := _MODEL_RE.search(text)):
            self.model = m.group(1)
        self._tail = text[-256:]

    def record(self, request: Request, token_hash: str, provider: str, requested_model: str) -> None:
        f = self.fields
        model = requested_model
        if provider == "anthropic":
            if self.model and self.model.startswith("claude-"):
                model = self.model  # a server-side fallback may have answered on another model
            cr, cw = f.get("cache_read_input_tokens", 0), f.get("cache_creation_input_tokens", 0)
            inp, out = f.get("input_tokens", 0) + cr + cw, f.get("output_tokens", 0)
        else:
            cr, cw = f.get("cachedContentTokenCount", 0), 0
            inp, out = f.get("promptTokenCount", 0), f.get("candidatesTokenCount", 0) + f.get("thoughtsTokenCount", 0)
        request.state.model, request.state.tokens_in, request.state.tokens_out = model, inp, out
        if inp or out:
            store.add_tokens(token_hash, provider, model, inp, out, estimate_usd(model, inp, out, cr, cw))


# --------------------------------------------------------------------------- forwarding

def _redact(body: bytes) -> bytes:
    for key in (ANTHROPIC_KEY, GEMINI_KEY):
        if key:
            body = body.replace(key.encode(), b"[redacted]")
    return body


def upstream_error(status: int, body: bytes) -> Response:
    """Pass the provider's error through (redacted), except our own credential failures."""
    if status in (401, 403):
        log.error("upstream rejected our credentials (status %s)", status)
        return error(502, "upstream_auth_error", "The AI provider rejected the proxy's credentials. The operators have been notified.")
    return Response(_redact(body)[:20_000], status_code=status, media_type="application/json")


PASS_HEADERS = ("content-type", "request-id", "retry-after", "x-request-id")


async def forward(request: Request, token_hash: str, provider: str, model: str, url: str,
                  headers: dict, params: dict, body: bytes, stream: bool) -> Response:
    usage = Usage()
    req = http.build_request("POST", url, headers=headers, params=params, content=body)
    try:
        resp = await http.send(req, stream=True)
    except httpx.HTTPError as e:
        log.warning("upstream %s unreachable: %s", provider, type(e).__name__)
        return error(502, "upstream_unreachable", f"Could not reach the {provider} API. Try again.")
    out_headers = {k: v for k, v in resp.headers.items() if k.lower() in PASS_HEADERS}

    if resp.status_code != 200 or not stream:
        try:
            content = await resp.aread()
        except httpx.HTTPError as e:
            log.warning("upstream %s read failed: %s", provider, type(e).__name__)
            return error(502, "upstream_unreachable", f"The {provider} API connection dropped. Try again.")
        finally:
            await resp.aclose()
        if resp.status_code != 200:
            request.state.model = model
            return upstream_error(resp.status_code, content)
        usage.feed(content)
        usage.record(request, token_hash, provider, model)
        return Response(content, status_code=200, headers=out_headers)

    async def relay():
        try:
            async for chunk in resp.aiter_bytes():
                usage.feed(chunk)
                yield chunk
        except httpx.HTTPError as e:
            log.warning("upstream %s stream dropped: %s", provider, type(e).__name__)
        finally:
            await resp.aclose()
            usage.record(request, token_hash, provider, model)

    out_headers["cache-control"] = "no-cache"
    return StreamingResponse(relay(), status_code=200, headers=out_headers)


async def read_json(request: Request) -> tuple[dict | None, bytes]:
    raw = await request.body()
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None, raw
    return (data if isinstance(data, dict) else None), raw


def _opus(model) -> bool:
    return isinstance(model, str) and "opus" in model.lower()


# --------------------------------------------------------------------------- routes

@app.get("/healthz")
async def healthz():
    return {"ok": True, "version": VERSION, "proxy_enabled": PROXY_ENABLED}


class RegisterBody(BaseModel):
    install_id: str = Field(min_length=1, max_length=128)
    app_version: str = Field(min_length=1, max_length=64)
    platform: str = Field(min_length=1, max_length=32)


@app.post("/v1/register")
async def register(body: RegisterBody, request: Request):
    if not register_allowed(client_ip(request)):
        return error(429, "rate_limit_error", "Too many registrations from this network. Try again later.")
    token = secrets.token_urlsafe(32)
    h = hash_token(token)
    store.add_token(h, body.install_id, body.app_version, body.platform)
    request.state.tok = h[:PREFIX_LEN]
    return {"token": token}


@app.post("/v1/anthropic/messages")
@app.post("/v1/anthropic/v1/messages")  # so the Anthropic SDK works with base_url=<proxy>/v1/anthropic
async def anthropic_messages(request: Request):
    token_hash, denied = authenticate(request)
    if denied:
        return denied
    if not ANTHROPIC_KEY:
        return error(503, "upstream_not_configured", "Anthropic is not configured on this proxy.")
    body, _ = await read_json(request)
    if body is None:
        return error(400, "invalid_request_error", "Body must be a JSON object.")
    model = body.get("model")
    request.state.model = model if isinstance(model, str) else None
    if _opus(model) or model not in ALLOWED_ANTHROPIC:
        return error(400, "invalid_request_error", f"Model not allowed on this proxy. Allowed: {', '.join(ALLOWED_ANTHROPIC)}.")
    fallbacks = body.get("fallbacks")
    if isinstance(fallbacks, list) and any(_opus(f.get("model")) for f in fallbacks if isinstance(f, dict)):
        return error(400, "invalid_request_error", "Opus fallbacks are not allowed on this proxy.")
    if any(isinstance(t, dict) and _opus(t.get("model")) for t in body.get("tools") or []):
        return error(400, "invalid_request_error", "Opus tools (advisor) are not allowed on this proxy.")
    if body.get("speed") == "fast" and not ALLOW_FAST_MODE:
        return error(400, "invalid_request_error", "speed=fast (fast mode) is not enabled on this proxy.")
    mt = body.get("max_tokens")
    if not isinstance(mt, int) or isinstance(mt, bool) or mt < 0:
        return error(400, "invalid_request_error", "max_tokens must be a non-negative integer.")
    body["max_tokens"] = min(mt, MAX_TOKENS_CAP)
    if denied := admit(request, token_hash, "anthropic", model):
        return denied

    headers = {"x-api-key": ANTHROPIC_KEY, "content-type": "application/json",
               "anthropic-version": ANTHROPIC_VERSION, "accept-encoding": "identity"}
    client_version = request.headers.get("anthropic-version", "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", client_version):
        headers["anthropic-version"] = client_version  # the SDK knows which response shapes it parses
    if beta := request.headers.get("anthropic-beta"):
        headers["anthropic-beta"] = beta[:500]
    params = {"beta": "true"} if request.query_params.get("beta") == "true" else {}
    return await forward(request, token_hash, "anthropic", model, ANTHROPIC_URL, headers, params,
                         json.dumps(body).encode(), stream=body.get("stream") is True)


GEMINI_METHODS = {"generateContent": False, "streamGenerateContent": True}
_GEMINI_MODEL_RE = re.compile(r"[a-z0-9][a-z0-9.\-]{0,63}")


@app.post("/v1/gemini/{target}")
@app.post("/v1/gemini/v1beta/models/{target}")  # so google-genai works with base_url=<proxy>/v1/gemini
async def gemini(target: str, request: Request):
    token_hash, denied = authenticate(request)
    if denied:
        return denied
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
    raw = await request.body()
    try:
        if not isinstance(json.loads(raw), dict):
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        return error(400, "invalid_request_error", "Body must be a JSON object.")
    if denied := admit(request, token_hash, "gemini", model):
        return denied
    params = {"alt": "sse"} if request.query_params.get("alt") == "sse" else {}
    headers = {"x-goog-api-key": GEMINI_KEY, "content-type": "application/json", "accept-encoding": "identity"}
    return await forward(request, token_hash, "gemini", model, GEMINI_URL.format(model=model, method=method),
                         headers, params, raw, stream=GEMINI_METHODS[method])


# --------------------------------------------------------------------------- admin

def admin_ok(token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(token.encode(), ADMIN_TOKEN.encode())


@app.get("/admin/usage")
async def admin_usage(request: Request, days: int = 30):
    if not admin_ok(request.headers.get("x-admin-token")):
        return error(401, "authentication_error", "Admin token required (X-Admin-Token header).")
    return store.usage_report(max(1, min(days, 365)))


@app.post("/admin/tokens/{prefix}/disable")
@app.post("/admin/tokens/{prefix}/enable")
async def admin_set_disabled(prefix: str, request: Request):
    if not admin_ok(request.headers.get("x-admin-token")):
        return error(401, "authentication_error", "Admin token required (X-Admin-Token header).")
    if not re.fullmatch(r"[0-9a-f]{8,64}", prefix):
        return error(400, "invalid_request_error", "Prefix must be 8-64 lowercase hex characters of the token hash.")
    disable = request.url.path.endswith("/disable")
    matched = store.set_disabled(prefix, disable)
    if not matched:
        return error(404, "not_found_error", "No token hash starts with that prefix.")
    if len(matched) > 1:
        return error(409, "conflict", f"{len(matched)} tokens match; use a longer prefix.")
    log.info("admin: token %s %s", prefix[:PREFIX_LEN], "disabled" if disable else "enabled")
    return {"token": matched[0][:PREFIX_LEN], "disabled": disable}


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


@app.post("/admin")
async def admin_page_post(request: Request):
    form = parse_qs((await request.body()).decode("utf-8", "replace"))  # urlencoded form, no multipart dependency
    if not admin_ok((form.get("admin_token") or [""])[0]):
        return _page("<p>Wrong token.</p>" + _LOGIN)
    r = store.usage_report(30)
    t = r["total"]
    summary = (f"<p>Since {html.escape(r['since'])}: <b>{t['requests']}</b> requests, {t['input_tokens']} input / "
               f"{t['output_tokens']} output tokens, est. <b>${t['usd']}</b>. Tokens registered: {r['registered_tokens']} "
               f"({r['disabled_tokens']} disabled). Proxy enabled: {PROXY_ENABLED}.</p>")
    cols = ["requests", "input_tokens", "output_tokens", "usd"]
    return _page(summary + "<h2>Per day</h2>" + _table(r["by_day"], ["day", "tokens", *cols])
                 + "<h2>Per install token (hash prefix)</h2>" + _table(r["by_token"], ["token", "disabled", *cols])
                 + "<h2>Per day, token and model</h2>" + _table(r["by_day_token_model"], ["day", "token", "provider", "model", *cols])
                 + "<p>Disable a token: <code>curl -X POST -H 'X-Admin-Token: …' $URL/admin/tokens/&lt;prefix&gt;/disable</code></p>")
