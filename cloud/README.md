# miyagi-cloud

A small API key proxy for the Miyagi desktop tutor. Users never paste API keys: every AI call
from the app goes through this server, which holds our Anthropic and Gemini keys as
environment variables, so all usage is billed to our account.

Each install registers once and gets an anonymous install token. The server stores only the
token's sha256 hash, checks the model allowlists and caps, forwards the call, and counts
requests and tokens per token per day.

Stack: Python 3.12, FastAPI, uvicorn, httpx, PyJWT, SQLite (stdlib). `app.py` (routes,
auth, forwarding, admin), `store.py` (the database seam) and `supabase_auth.py` (account links).

## Endpoints

| Route | Auth | What it does |
|---|---|---|
| `GET /healthz` | none | `{"ok": true, "version": ..., "proxy_enabled": ...}`. No secrets. |
| `POST /v1/install` | none, 10 per IP per hour (shared with `/v1/register`) | What the desktop app calls. Body `{app, os, arch}` (all optional, extra fields ignored) → `{token, token_id}`. `token` is `mi_` + 32 random bytes urlsafe (46 characters); `token_id` is the first 12 hex characters of its sha256, the same id the admin views and `/admin/tokens/{prefix}/disable` use. |
| `POST /v1/register` | same limit | Older form. Body `{install_id, app_version, platform}` → `{token, token_id}`, same token shape. |
| `POST /v1/anthropic/messages` | install token | Passthrough to `https://api.anthropic.com/v1/messages`. Also served at `/v1/anthropic/v1/messages` so the Anthropic SDK works with `base_url=<proxy>/v1/anthropic`. |
| `POST /v1/gemini/{model}:generateContent` and `:streamGenerateContent` | install token | Passthrough to `https://generativelanguage.googleapis.com/v1beta/models/{model}:...`. Also served at `/v1/gemini/v1beta/models/{model}:...` so `google-genai` works with `base_url=<proxy>/v1/gemini`. |
| `GET /admin/usage` | `X-Admin-Token` header | JSON usage report (see below). `?days=30` by default. |
| `GET /admin`, `POST /admin` | admin token typed into a form | The same report as HTML. The token is posted in the form body, never in the URL. |
| `POST /admin/tokens/{prefix}/disable` and `/enable` | `X-Admin-Token` header | Turn one install token off or on, by the first 8+ hex characters of its hash. |
| `POST /admin/tokens/{prefix}/plan` | `X-Admin-Token` header | Body `{"plan": "free"}` or `{"plan": "pro"}`. Pro installs have no free tier caps. |
| `GET /v1/lessons/{video_id}?schema=N` | install token | Shared lesson cache. 200 `{video_id, schema, created_at, lesson}` or 404 `lesson_not_cached` (its `error.builds` says how many free builds are left). Free. |
| `POST /v1/lessons/{video_id}/build` | install token | Use one of this month's new-lesson builds. 200 `{ok, builds: {used, cap, month, resets_at}}` or 429 `miyagi_lesson_quota`. |
| `PUT /v1/lessons/{video_id}` | install token | Body `{schema, lesson}`. Share a lesson this install built. 201, 403 `build_not_claimed`, 409 `lesson_exists`, 413, 400 `schema_unsupported`. |
| `DELETE /admin/lessons/{video_id}` | `X-Admin-Token` header | Drop a bad shared lesson (every schema). |

The install token is read from `Authorization: Bearer <token>`. SDKs pointed at the proxy send
their "API key" as `x-api-key` (Anthropic) or `x-goog-api-key` (Gemini), so those headers are
accepted too. The client's headers are never forwarded upstream; the proxy sets the upstream
key itself.

### What the Anthropic route enforces

- `model` must be in `ALLOWED_ANTHROPIC_MODELS`. Any model containing `opus` is always
  rejected, including in a `fallbacks` array or a tool's `model` (advisor).
- `max_tokens` is capped at `MAX_TOKENS_CAP`.
- `speed: "fast"` is rejected unless `ALLOW_FAST_MODE=true` (fast mode bills 2x). The engine
  already retries at standard speed when fast mode is refused.
- `stream: true` is streamed through as SSE. `anthropic-beta`, `anthropic-version` and
  `?beta=true` are passed through so the SDK's beta calls (`server-side-fallback-...`) work.
- With `fallbacks: "default"`, Anthropic may answer on another model. Usage is recorded under
  the model the response names, so it shows up in the admin view.

### What the Gemini route enforces

- `{model}` must be in `ALLOWED_GEMINI_MODELS`; any other model gets a 404. The engine sends YouTube URLs as `file_uri`
  and never uploads files, so there is no upload endpoint.
- `?alt=sse` is passed through for streaming.

## Accounts: `POST /v1/link`

Links an install to the signed-in miyagi account so usage can be counted per user. Installs that never
link keep using the proxy exactly as before, and signing out in the app never unlinks.

```
POST /v1/link
Authorization: Bearer <mi_ install token from /v1/install>
{"access_token": "<Supabase user access token (JWT)>"}

200 {"ok": true, "user_id": "<jwt sub>"}   linked; re-linking the same pair is 200 and keeps the first linked_at
401 {"error": "bad_install_token"}         missing, unknown or disabled install token (checked first)
403 {"error": "bad_access_token"}          bad signature, expired, wrong aud or iss, unknown key, any other alg
503 {"error": "link_unavailable"}          the cloud cannot verify: no JWKS (and, for HS256, no secret)
```

The errors are the flat `{"error": kind}` shape, not the proxy's `{type, error: {...}}` shape. A link
from a different account on the same install replaces the user (one user per install). Like every `/v1`
route it answers 503 `proxy_disabled` while `PROXY_ENABLED=false`.

Verification (`supabase_auth.py`, PyJWT with the `cryptography` backend):

- ES256 and RS256 tokens are checked against `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`, fetched
  at most every 10 minutes. A failed refresh keeps the last good key set; with none at all the route
  answers 503 and retries the fetch after 30 s. An unknown `kid` triggers one refetch (at most once a
  minute) in case Supabase rotated its signing key.
- Legacy HS256 tokens are checked with `SUPABASE_JWT_SECRET` when it is set, else 503.
- Every token needs `aud == "authenticated"`, `iss == ${SUPABASE_URL}/auth/v1`, a future `exp` and a `sub`.
- `exp`, `iat` and `nbf` allow 30 s of clock skew (`LEEWAY_S`). The app links seconds after sign-in, so
  without it a Render clock slightly behind Supabase's would reject a fresh token as issued in the future.
- The access token is never logged or stored. The table `links (token_hash, user_id, linked_at)` holds
  the result; the request log line gains `user=<user_id>` for linked installs, and
  `/admin/usage` `by_token` rows carry `user_id` (null when unlinked).

Render env for this route (also in `render.yaml`):

| Name | Default | Notes |
|---|---|---|
| `SUPABASE_URL` | `https://wssdpsdbaqtnfhoyimit.supabase.co` | The Supabase project. JWKS URL and expected `iss` derive from it. |
| `SUPABASE_JWT_SECRET` | empty | Optional. Only for legacy HS256 access tokens; set it in the dashboard (`sync: false`). |

## Security

- Request bodies, prompts, screenshots, install tokens and keys are never logged. One line
  per request: method, path, status, latency, model, token counts, token-hash prefix.
  Uvicorn's access log is turned off because it would print query strings.
- Body size limit: `MAX_GEMINI_BODY_MB` (20) on `/v1/gemini/*`, `MAX_BODY_MB` (2) elsewhere,
  checked on `Content-Length` and while reading chunked bodies.
- No CORS: no `Access-Control-*` headers, and any `/v1` request carrying an `Origin` header
  is refused with 403.
- Upstream errors are passed through with our keys redacted. If a provider rejects our own
  key (401/403), the client gets a 502 instead, so an app never mistakes it for a bad install token.
- httpx timeouts: connect 10 s, write 60 s, read `UPSTREAM_READ_TIMEOUT_S` (300 s; a Gemini
  video watch can take minutes).
- The server refuses to start without `ADMIN_TOKEN`. Admin tokens are compared in constant time.
- No `/docs` or `/openapi.json`.

## Kill switches

- `PROXY_ENABLED=false` makes every `/v1` route return 503 with
  "Miyagi cloud AI is paused by the operators. Try again later." `/healthz` and `/admin` keep working.
- Disable one install: `curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" $URL/admin/tokens/<prefix>/disable`
  (take the prefix from `/admin/usage`). Its calls then get 403.

## Shared lesson cache (ROADMAP 3.1)

Lesson builds are the expensive call (Gemini watching a whole video), and many learners open the same
videos. The engine (`server/lesson/cloud_cache.py`, only when `miyagiCloud` is configured) does:

1. `GET /v1/lessons/{video_id}?schema=N`. A hit is used as the video draft and costs nothing.
2. On a miss, `POST /v1/lessons/{video_id}/build` to use one of the install's builds. A 429 here stops the
   build with a calm card; any other failure (network, 5xx) lets the engine build locally as before.
3. After a good build, `PUT /v1/lessons/{video_id}` with `{schema, lesson}`.

Rules:

- `video_id` is an 11-character YouTube id. `schema` is the engine's draft format version (an integer in
  `MIN_LESSON_SCHEMA`..`MAX_LESSON_SCHEMA`); each version is cached separately, and raising
  `MIN_LESSON_SCHEMA` retires drafts written by older engines.
- Upload size is capped at `MAX_LESSON_KB` (512). The lesson must be a JSON object with 1 to 300 `steps`.
- Only an install that claimed a build of the video may upload it, and the first upload wins (409 after),
  so one install cannot overwrite a lesson others already use. An operator removes a bad one with
  `DELETE /admin/lessons/{video_id}`; the engine also validates whatever it downloads and builds locally
  when a cached lesson does not parse.

## Free tier caps (ROADMAP 3.7)

Installs start on the `free` plan. `pro` (set with `/admin/tokens/{prefix}/plan`) has no caps. A cap set to 0
is off.

| Cap | Env | Default | Counted |
|---|---|---|---|
| New lesson builds per UTC month | `FREE_LESSON_BUILDS_PER_MONTH` | 3 | Distinct videos claimed with `POST /v1/lessons/{id}/build`. Cache hits and rebuilding an already claimed video are free. |
| Coach calls per UTC day | `FREE_COACH_CALLS_PER_DAY` | 60 | Forwarded AI calls carrying `x-miyagi-role: coach` (the engine sets it, `server/config.py` `anthropic_kwargs(role=...)`). |
| All AI calls per UTC day | `FREE_DAILY_REQUESTS` | 0 (off) | Every forwarded call. A backstop. |

Over a cap the proxy answers 429 with `x-should-retry: false` (the SDKs then do not retry), `retry-after`, and:

```json
{"type": "error", "error": {"type": "miyagi_quota", "status": "MIYAGI_QUOTA", "code": 429,
  "message": "That's all the coach help for today. It comes back tomorrow.",
  "limit": "coach_calls", "used": 60, "cap": 60, "resets_at": "2026-11-22T00:00:00Z"}}
```

`type` is `miyagi_quota` for the daily caps (the engine's existing `cloud_error()` reads it) and
`miyagi_lesson_quota` for the monthly build cap. `limit` is `lesson_builds`, `coach_calls` or
`daily_requests`; the app can show `message` as is.

## Rate limit hooks

`check_quota(token_hash, role)` in `app.py` runs before every forwarded call and applies the free tier
caps above. Requests are counted per token and day in `usage.requests` and per role in `role_usage`.

## Admin view

`GET /admin/usage` with `X-Admin-Token` returns:

- `total`: requests, input and output tokens, estimated USD over the window
- `by_token`: the same per token-hash prefix (12 hex characters), with `disabled`
- `by_day`: the same per UTC day, with the number of active tokens
- `by_day_token_model`: per day, token, provider and model
- `lessons`: shared lessons cached, cache hits, bytes, and new builds this month

USD is an estimate from the `PRICES` table in `app.py` (Anthropic list prices; the Gemini rows
are placeholders to check against Google's pricing). Override or add models with
`PRICES_JSON='{"model": [input_per_mtok, output_per_mtok]}'`.

Open `/admin` in a browser, paste the admin token into the form, and it shows the same tables.

## Environment variables

| Name | Default | Notes |
|---|---|---|
| `ADMIN_TOKEN` | none (required) | Render generates it (`generateValue: true`). |
| `ANTHROPIC_API_KEY` | none | Set in the Render dashboard (`sync: false`). Missing: Anthropic routes return 503. |
| `GEMINI_API_KEY` | none | Set in the Render dashboard (`sync: false`). Missing: Gemini routes return 503. |
| `PROXY_ENABLED` | `true` | `false` turns off every `/v1` route. |
| `ALLOWED_ANTHROPIC_MODELS` | `claude-sonnet-5-5,claude-haiku-5-5` | Comma-separated. Opus is rejected regardless. |
| `ALLOWED_GEMINI_MODELS` | `gemini-3.8-flash` | Comma-separated. See the engine note below. |
| `MAX_TOKENS_CAP` | `4096` | Upper bound on Anthropic `max_tokens`. |
| `DB_PATH` | `/var/data/miyagi.db` if `/var/data` exists, else `./miyagi.db` | SQLite file. |
| `MAX_BODY_MB` / `MAX_GEMINI_BODY_MB` | `2` / `20` | Request size limits. |
| `REGISTER_LIMIT_PER_HOUR` | `10` | Registrations per client IP per hour (in memory). |
| `TRUSTED_PROXY_HOPS` | `1` | Which `X-Forwarded-For` entry (from the right) is the client IP. |
| `ALLOW_FAST_MODE` | `false` | Allow Anthropic `speed: "fast"`. |
| `ANTHROPIC_VERSION` | `2023-06-01` | Used when the client sends no `anthropic-version`. |
| `UPSTREAM_READ_TIMEOUT_S` | `300` | httpx read timeout. |
| `PRICES_JSON` | empty | Price table overrides for the USD estimate. |
| `FREE_LESSON_BUILDS_PER_MONTH` | `3` | New lesson builds per free install per UTC month. 0 = no cap. |
| `FREE_COACH_CALLS_PER_DAY` | `60` | Coach calls per free install per UTC day. 0 = no cap. |
| `FREE_DAILY_REQUESTS` | `0` | All forwarded AI calls per free install per UTC day. 0 = no cap. |
| `MAX_LESSON_KB` | `512` | Largest shared lesson upload. |
| `MIN_LESSON_SCHEMA` / `MAX_LESSON_SCHEMA` | `1` / `99` | Lesson schema versions the cache accepts. |
| `UPSTREAM_ANTHROPIC_URL` / `UPSTREAM_GEMINI_URL` | the real APIs | For local tests against a mock only. Never set in production. |

## Deploy on Render

`render.yaml` is a Blueprint for one web service: `rootDir: cloud`, Python runtime, starter
plan, health check on `/healthz`, a 1 GB disk at `/var/data` for the SQLite file. Render looks
for `render.yaml` at the repo root, so when creating the Blueprint set its file path to
`cloud/render.yaml`. After the first deploy, set `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` in
the dashboard and read the generated `ADMIN_TOKEN` there.

A service with a disk runs as a single instance, which is also what the in-memory
registration limit assumes.

## Run locally

```sh
cd cloud
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
ADMIN_TOKEN=test ANTHROPIC_API_KEY=fake GEMINI_API_KEY=fake .venv/bin/uvicorn app:app --port 8790
curl -s localhost:8790/healthz
```

Tests (no network, no real keys; needs `pytest` in the venv): `.venv/bin/python -m pytest tests -q`.

## Moving to Postgres (Supabase)

All SQL lives in `store.py`. Write a `PostgresStore` with the same methods (`add_token`,
`get_token`, `set_disabled`, `set_plan`, `count_request`, `add_tokens`, `requests_today`, `count_role`,
`role_requests_today`, `get_lesson`, `put_lesson`, `delete_lessons`, `builds_in_month`, `has_build`,
`claim_build`, `usage_report`)
and return it from `open_store()` when `DATABASE_URL` is set. The tables port as they are.

## How the app uses it

1. On first launch the app (`app/src/main/features/cloud.ts`) calls `POST <host>/v1/install`
   and keeps the returned `mi_` token in the Keychain (safeStorage). The host defaults to
   `https://miyagi-cloud.onrender.com`; `MIYAGI_CLOUD_URL` overrides it, `off` turns it off.
2. The app sends the engine `config.keys {miyagiToken: <token>, miyagiCloud: "<host>/v1"}`. The
   engine (`server/config.py`) uses `<host>/v1/anthropic` as the Anthropic SDK `base_url` and
   `<host>/v1/gemini` (api_version v1beta) for google-genai, with the token as the API key.
3. A 401 means the token is unknown: register again. A 403 means the install was disabled. A
   503 `proxy_disabled` means the operators paused the proxy.

## Engine integration

Not done in this branch. In the run-live engine (`server/`), these are the places that must
use `MIYAGI_CLOUD_URL` and the install token instead of a user's key:

**Key lookup**

- `server/config.py` `get_key(name)`: when `MIYAGI_CLOUD_URL` is set, return the install
  token for `"anthropic"` and `"gemini"` (registering on first use), and have `key_source()`
  report `cloud`. `KEY_ENV` and `set_app_keys()` keep working for Bright Data and ElevenLabs,
  which the proxy does not cover.
- Everything that already goes through `get_key` then gets the token for free:
  `server/orchestrator/main.py` `apply_keys()` (calls `set_app_keys`),
  `server/orchestrator/modules.py` `search()`, `build_lesson()` (passes `api_key=get_key("gemini")`)
  and `prefetch_preflight()`, and `server/coach/llm.py` `get_key()`.

**Where the Anthropic client is created** (each needs `base_url=f"{MIYAGI_CLOUD_URL}/v1/anthropic"`,
and `api_key=<install token>`, which the SDK sends as `x-api-key`):

- `server/lesson/claude.py` `client()` (`AsyncAnthropic`; the key comes from `set_api_key()`,
  called by `server/lesson/builder.py` `_build_lesson_impl()`)
- `server/coach/llm.py` `get_client()`
- `server/finder/claude.py` `client(key)`
- `server/screen/describe.py` `Describer._get_client()`. Its `COACH_MODEL` defaults to
  `claude-opus-5-5`, which the proxy rejects: change the default to `claude-sonnet-5-5`.
- `server/screen/target.py` `_client_for(api_key)`
- `server/diagrams/build.py` `_get_client()`
- `server/workspace/scaffold.py` `make_client()` (sync `Anthropic`)

**Where Gemini is called** (each needs `genai.Client(api_key=<install token>,
http_options=types.HttpOptions(base_url=f"{MIYAGI_CLOUD_URL}/v1/gemini"))`; the SDK then calls
`/v1/gemini/v1beta/models/{model}:generateContent` with the token as `x-goog-api-key`):

- `server/lesson/gemini.py` `client()` and `set_api_key()`; the calls go through
  `_generate_json()` (`watch_video`, `step_detail`, `adapt_checks`)
- `server/finder/gemini.py` `client(key)`; the calls go through `_json()` (`plan`, `score`, `skim`)

**Models to allowlist.** The engine's Gemini defaults are `gemini-4-hydrogen` (video watch,
`LESSON_MODEL`), `gemini-3.8-flash` (`LESSON_FAST_MODEL`), the fallbacks
`gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash` (`LESSON_FALLBACK_MODELS`) and
`gemini-3.1-flash-lite,gemini-3.5-flash-lite` (finder). With the default allowlist only
`gemini-3.8-flash` passes, so either add the others to `ALLOWED_GEMINI_MODELS` or point the
engine's model env vars at allowed models. A model that is not allowed gets a 404
(`NOT_FOUND`), the same reply Google gives for an unknown model, so the engine's
`_classify()` skips straight to its next fallback model. With the defaults, the video watch
chain (`gemini-4-hydrogen` then the 3.7/3.6/3.5 flash fallbacks) has no allowed model and
fails, so allowlist at least one of them before pointing the engine at the proxy.
