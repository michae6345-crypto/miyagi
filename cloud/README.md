# miyagi-cloud

A small API key proxy for the Miyagi desktop tutor. Users never paste API keys: every AI call
from the app goes through this server, which holds our Anthropic and Gemini keys as
environment variables, so all usage is billed to our account.

Each install registers once and gets an anonymous install token. The server stores only the
token's sha256 hash, rate limits every client, checks the model and request-body allowlists and the
caps, forwards the call, and counts requests, tokens and estimated dollars per token per day.

Stack: Python 3.12, FastAPI, uvicorn, httpx, PyJWT, SQLite (stdlib). `app.py` (middleware, routes,
auth, caps, forwarding, admin), `store.py` (the database seam) and `supabase_auth.py` (account links).
No other dependencies: the rate limiter is plain ASGI, not slowapi.

## Endpoints

| Route | Auth | What it does |
|---|---|---|
| `GET /healthz` | none, never rate limited | `{"ok": true, "version": ..., "proxy_enabled": ...}`. No secrets. |
| `POST /v1/install` | none; 20 per network per hour and 60 per day, shared with `/v1/register` | What the desktop app calls. Body `{app, os, arch}` (all optional, extra fields ignored) → `{token, token_id}`. `token` is `mi_` + 32 random bytes urlsafe (46 characters); `token_id` is the first 12 hex characters of its sha256, the same id the admin views and `/admin/tokens/{prefix}/disable` use. |
| `POST /v1/register` | same limits | Older form. Body `{install_id, app_version, platform}` → `{token, token_id}`, same token shape. |
| `POST /v1/link` | install token | Links the install to a Google-signed-in miyagi account. See "Accounts" below. |
| `POST /v1/anthropic/messages` (also `/v1/anthropic/v1/messages`) | install token | Messages API through our key, request body rebuilt from an allowlist (below). |
| `POST /v1/gemini/{model}:generateContent` and `:streamGenerateContent` (also under `/v1/gemini/v1beta/models/`) | install token | generateContent through our key, body rebuilt from an allowlist (below). |
| `GET /v1/lessons/{video_id}?schema=N` | install token | Shared lesson cache: an approved lesson, or 404 `lesson_not_cached` (its `error.builds` says how many free builds are left). Free. |
| `POST /v1/lessons/{video_id}/build` | install token | Use one of this month's new-lesson builds. 200 `{ok, builds: {used, cap, month, resets_at}}` or 429 `miyagi_lesson_quota`. |
| `PUT /v1/lessons/{video_id}` | install token | Body `{schema, lesson}`. Upload a lesson this install built, as a pending candidate. 201 `{stored, status: "pending" \| "approved", hash}`, 403 `build_not_claimed`, 400, 413, 429 `lesson_uploads`, 507 `insufficient_storage`. |
| `POST /v1/events` | install token | Product events, counts only. See "Product events" below. |
| `GET /admin/usage` | `X-Admin-Token` | JSON usage report. `?days=30` by default. |
| `GET /admin`, `POST /admin` | admin token typed into a form | The same report as HTML. The token is posted in the form body, never in the URL. |
| `POST /admin/tokens/{prefix}/disable` and `/enable` | `X-Admin-Token` | Turn one install token off or on, by the first 8+ hex characters of its hash. |
| `POST /admin/tokens/{prefix}/plan` | `X-Admin-Token` | Body `{"plan": "free"}` or `{"plan": "pro"}`. Pro installs skip the per-install caps. |
| `GET /admin/lessons/pending` | `X-Admin-Token` | Uploaded lessons waiting for review: video, schema, 16-hex body hash, uploader prefix, size, and what to read before approving: the `libraries` it installs, every `commands` entry it suggests or runs, its `files`, and `full`, the path of the whole body. |
| `GET /admin/lessons/{video_id}/candidates/{hash}` | `X-Admin-Token` | The whole body of the candidates whose body hash starts with `hash` (8+ hex; `?schema=N` optional): every instruction, code block, solution, hint and explanation learners would receive, plus the review summary. Read it before approving. |
| `POST /admin/lessons/{video_id}/approve` | `X-Admin-Token` | Body `{"hash": "<8+ hex of the body hash>", "schema": N?}`. Serve that candidate (replaces any approved one). |
| `DELETE /admin/lessons/by-uploader/{prefix}` | `X-Admin-Token` | Drop every lesson one install uploaded (approved or pending). |
| `DELETE /admin/lessons/{video_id}` | `X-Admin-Token` | Drop every candidate of a video (every schema). |

The install token is read from `Authorization: Bearer <token>`, or from `x-api-key` / `x-goog-api-key`,
which is where the engine's Anthropic and google-genai SDKs put it. The client's headers are never
forwarded upstream; the proxy sets the upstream key itself.

### What the Anthropic route enforces

The upstream JSON is rebuilt from allowlisted keys only. Kept: `model`, `messages`, `system`,
`max_tokens` (capped at `MAX_TOKENS_CAP`), `temperature`, `top_p`, `top_k`, `stop_sequences`, `stream`,
`thinking` (`type`, `display`, and `budget_tokens` below `max_tokens` and at most `MAX_TOKENS_CAP`),
`tool_choice`, `tools`, plus two the engine needs: `output_config` (`effort` and a `json_schema` `format`
only: the coach's structured outputs) and `fallbacks` (`"default"`, which the engine sends with Sonnet; for
Sonnet 5.5 the API's documented targets are Sonnet 5 only, or a list of allowed non-Opus models). Every other
key (`metadata`, `inference_geo`, `task_budget`, ...) is dropped. Refused with 400:

- `model` outside `ALLOWED_ANTHROPIC_MODELS`; any Opus model in any model-like field at any depth (a tool's
  advisor `model`, `fallbacks`, `fallback_model`, ...); any other model-like top-level field that does not name
  an allowed model.
- `mcp_servers`, `container`, `service_tier`, `context_management`.
- Tools other than client tools (no `type`, or `type: "custom"`; forwarded as `name`, `description`,
  `input_schema`, `strict`, `cache_control`): `web_search_*`, `web_fetch_*`, `code_execution_*`, `bash_*`,
  `computer_*`, `text_editor_*`, `memory_*`, `mcp_toolset`, advisor and the rest. `ANTHROPIC_SERVER_TOOLS`
  (`web_search`, `web_fetch`) re-allows the two web tools, with `max_uses` capped at `SERVER_TOOL_MAX_USES` and
  every use counted at $0.01 in the caps. `web_fetch` always goes upstream with a `max_content_tokens` of at most
  `WEB_FETCH_MAX_CONTENT_TOKENS` (20000), sent even when the client sends none: a fetched page is billed as input.
- A `source` whose `type` is `url` or `file`, and `container_upload` blocks, anywhere under `messages` or `system`:
  every nested object and list is walked (a tool result's content, a document's `source.content`, a search
  result's content), only a `tool_use` block's `input` (the model's own JSON) is skipped, and content nested
  deeper than 32 levels is refused rather than left unchecked. Anthropic would fetch those on our account. Base64
  images and documents are fine.
- A `cache_control` that is not `{"type": "ephemeral"}`. Its `ttl` is dropped unless it is `"5m"` (in content,
  `system` and tools alike): a 1-hour cache write bills 2x input, against the 1.25x the caps price a cache write at.
  A usage block that still reports `ephemeral_1h_input_tokens` is settled at 2x for those tokens.
- `anthropic-beta` values outside `ANTHROPIC_BETAS` (default `server-side-fallback-2026-07-01`, the only one
  the engine sends).
- `speed: "fast"` unless `ALLOW_FAST_MODE=true` (fast mode bills 2x; the engine retries at standard speed).

`stream: true` is streamed through as SSE. Usage is recorded under the model the response names (a server-side
fallback may answer on Sonnet 5), never an Opus id.

### What the Gemini route enforces

- `{model}` must be in `ALLOWED_GEMINI_MODELS`; any other model gets a 404 (Google's own reply for an
  unknown model, so the engine skips to its next fallback at once).
- The body is rebuilt from `contents`, `systemInstruction`, `safetySettings`, `toolConfig`
  (`functionCallingConfig`), `tools` (`functionDeclarations` only: `googleSearch`, `codeExecution`, `urlContext`
  and every other tool are refused) and `generationConfig` (`temperature`, `topP`, `topK`, `stopSequences`,
  `responseMimeType`, `responseSchema`, `responseJsonSchema`, `mediaResolution`, `candidateCount` forced to 1,
  `maxOutputTokens` clamped to `GEMINI_MAX_OUTPUT_TOKENS` and sent even when the client sends none,
  `thinkingConfig.thinkingBudget` clamped to `GEMINI_MAX_THINKING_TOKENS`). Parts keep `text`, `inlineData`,
  `fileData`, `videoMetadata` (`startOffset`, `endOffset`, and `fps` clamped to `GEMINI_MAX_FPS`, 2), function
  calls and function responses (rebuilt as `{id, name, response}`).
- `fileData`, `file_data`, `fileUri` or `file_uri` anywhere in a part other than its validated top-level
  `fileData` (a `functionCall`'s args, a `videoMetadata`, ...) is refused, and so is any `functionResponse.parts`
  (Gemini 3's multimodal function responses carry `file_data` / `inline_data` the model would read). A video
  window whose `endOffset` is before its `startOffset`, or an `fps` that is not a positive number, is refused.
- Thinking and the output clamp: the engine (`lesson/gemini.py` `_generate_json`, `finder/gemini.py`) sends
  `responseJsonSchema` and neither `maxOutputTokens` nor a `thinkingConfig`, so the model's dynamic thinking
  applies. On Gemini 2.5 and later thinking tokens count against `maxOutputTokens`, so the clamp has to leave the
  JSON answer room after the thinking: `GEMINI_MAX_OUTPUT_TOKENS` defaults to 32768 (Flash's dynamic thinking tops
  out at 24576, which leaves at least 8192 for the answer; the model's own default is about 64k). With the old 8192
  a long lesson-window draft could come back cut off or empty (`MAX_TOKENS`), `json.loads` failed and the engine
  retried. We chose the higher clamp over inserting a `thinkingBudget` (Gemini 3 prefers `thinkingLevel`, and a
  budget nobody checked offline could make video lessons worse). The reservation holds the whole clamp at the
  output price, thinking included, and the real `thoughtsTokenCount` is billed when the call settles. A
  `thinkingBudget` a client does send is clamped to `GEMINI_MAX_THINKING_TOKENS` (2048).
- Shape bounds, checked before anything is copied (400 past them): at most 500 `contents`, 2000 parts in all
  (system instruction included), 256 `functionDeclarations` and 32 `safetySettings`, and `JSON_MAX_OBJECTS`
  (50000) JSON objects in the body, counted while it is parsed.
- `cachedContent` is refused.
- `fileData.fileUri` must be `https://www.youtube.com/watch?v=<11 chars>` or `https://youtu.be/<11 chars>`
  (extra query parameters such as `&t=42s` are dropped; the canonical watch URL is forwarded). Files API
  uploads, `gs://` paths and every other host are refused.
- `?alt=sse` is passed through for streaming. Bodies are capped at `MAX_GEMINI_BODY_MB` (2): the engine sends
  a YouTube `fileData` part and a prompt, never inline video or screenshots (no `inline_data` or `from_bytes` in
  `server/` on `integration/live`), so its requests are well under 1 MB. It was 8: one 8 MB body of empty objects
  from a freshly minted token took the process from about 100 MB to 1.3 GB before the caps refused it.

### Upstream errors

A provider error that is about our account never reaches the client verbatim; the provider's text is logged
on the server (keys redacted) and the client gets a fixed message:

| Upstream | Client gets |
|---|---|
| 401, 403 | 502 `upstream_auth_error` (so the app never mistakes it for a bad install token) |
| 402, or a 400/429 about credit, billing or quota | 503 `upstream_unavailable` |
| 429 | 429 in the provider's own shape (`rate_limit_error` / `RESOURCE_EXHAUSTED`), "busy, try again", with its `retry-after`. The provider shape matters: the engine reads a proxy-shaped 429 `rate_limit_error` as "today's limit" |
| 529, 503 | 529 (Anthropic) or 503 (Gemini) `overloaded`, fixed message |
| other 5xx | the same status, fixed message |
| other 4xx (a malformed request) | passed through, keys redacted |

## Rate limits

`class RateLimit` in `app.py` is pure ASGI middleware, registered directly before `Guard`:

```python
app.add_middleware(RateLimit)
app.add_middleware(Guard)
```

Starlette makes the last-added middleware the outermost, so `Guard` runs first (kill switch, browser-origin
block, admin-off switch, body size limit) and writes the log line for every 429 `RateLimit` sends (with
`rl=<limit>`). Per hour, as a sliding window (the current hourly window plus the previous one, weighted by
how much of it still overlaps: O(1) per key):

| Limit | Env | Default | Counts |
|---|---|---|---|
| Per client IP | `RATE_LIMIT_PER_IP_PER_HOUR` | 100 | Every `/v1/*` and `/admin*` request. `/healthz` is never limited. |
| Per install token | `RATE_LIMIT_PER_TOKEN_PER_HOUR` | 600 | `/v1/anthropic/*`, `/v1/gemini/*`, `/v1/lessons/*`, `/v1/events`, counted per token instead of per IP, but only when the presented token (Bearer, `x-api-key` or `x-goog-api-key`) is a known, enabled one. A missing or unknown token counts against the IP, so guessing tokens is IP-limited, and a school behind one IP is not limited to 100 calls. |
| Admin per IP | `ADMIN_RATE_LIMIT_PER_IP_PER_HOUR` | 20 | Every `/admin*` request (on top of the IP limit). |
| Admin lockout | `ADMIN_LOCKOUT_FAILURES` | 5 | Wrong admin tokens (header or form) from one IP within an hour. Then every `/admin*` request from that IP gets 429 `admin_lockout`, the right token included, until the oldest of those failures is an hour old. Each failure logs a WARNING with the IP, never what was presented. Holds even with `RATE_LIMIT_ENABLED=0`. |

`RATE_LIMIT_ENABLED=1` (the default) turns the limiter on. Over a limit the answer is a 429 in `error()`'s shape:

```json
{"type": "error", "error": {"type": "rate_limit_error", "status": "RATE_LIMIT_ERROR", "code": 429,
  "message": "Too many requests from this network. Try again in a few minutes.",
  "limit": "ip_hourly", "resets_at": "2026-11-21T19:04:00Z"}}
```

`limit` is `ip_hourly`, `token_hourly`, `admin` or `admin_lockout` (and `install_hourly`, `install_daily` or
`install_global` from the install limit below). `Retry-After` is in seconds (at least 1), and
`x-should-retry: false` is added when the wait is over 60 s so the SDKs do not retry on their own. The engine
(`server/config.py` `cloud_error()`) reads a proxy-shaped 429 `rate_limit_error` as `miyagi_quota` and shows
its card instead of retrying in a loop.

**Known engine gap (follow-up, does not block this PR).** On `integration/live`, `_classify_cloud` maps *every*
proxy-shaped 429 `rate_limit_error` to `miyagi_quota` with a TTL until UTC midnight. So an hourly `ip_hourly` or
`token_hourly` 429 makes the app say "You've reached today's limit. It resets tomorrow." until midnight, although
it clears within the hour. The engine should read `error.limit`: `ip_hourly`, `token_hourly` and `install_*` are
transient (TTL = `Retry-After`); only the daily caps (`type: miyagi_quota`) last until midnight. Engine ticket to
open: "cloud_error: treat error.limit ip_hourly / token_hourly / install_* as transient (TTL retry-after)".

The client IP is the `X-Forwarded-For` entry at position `-TRUSTED_PROXY_HOPS` (1: Render's load balancer
appends the address it saw). Entries further left are whatever the client wrote and are never trusted; with
fewer entries than hops, or an invalid entry, the socket peer is used. Ports are stripped and addresses are
validated. `CLIENT_IP_HEADER` (for example `cf-connecting-ip` behind Cloudflare) is used instead, only when
set. **Warning:** anyone who can reach the `onrender.com` origin directly can send that header with any value
they like, so set it only once the origin accepts traffic from that proxy alone. IPv6 clients are counted by
their /64 (one home or phone gets a whole /64); IPv4 by the full address.

Memory is bounded: at most `RATE_LIMIT_MAX_KEYS` (200000) keys. Expired keys are swept at most once a
minute, and when the table is still full a new key evicts the key with the oldest window.

**Per process, per instance.** The counters live in the process's memory: a deploy resets them, and two
instances would each allow the full amount. Today the service is one Render starter instance (a service with
a disk runs one instance), so that is the real limit. The install limit and every cap below live in SQLite and
survive deploys.

**Release gate: check the hop count on staging before this reaches production.** If Render (or Cloudflare in
front of it) adds more than one entry, `TRUSTED_PROXY_HOPS=1` picks a proxy's address: every learner lands in a
few proxy buckets, and the 100/h IP limit then blocks `/v1/install` and `/v1/link` for everyone. On its first
request after a start (and once more on the first request that carries the header, if the first had none) the
service logs at INFO how many `X-Forwarded-For` entries it saw and what kind of address the chosen entry is, never
the addresses themselves:

    first request: 1 X-Forwarded-For entry (TRUSTED_PROXY_HOPS=1); the chosen entry is a global address

Steps: deploy to staging, call `/v1/install` once from a normal connection, and read the Render log.

- `a global address` with 1 entry: right. Ship.
- `a Cloudflare address (wrong hop count)` or `a private or reserved address (likely a proxy: wrong hop count)`,
  or a count of 2 or more from a plain request: a proxy sits in front. Set `TRUSTED_PROXY_HOPS` to the count (or
  `CLIENT_IP_HEADER`, with the warning above) and check again.
- Then restart and repeat with `curl -H 'X-Forwarded-For: 1.2.3.4' .../v1/install`: the count must go up by one
  and the kind must stay `a global address` (the client's own entries are on the left and never used).

### Install minting

`/v1/install` and `/v1/register` mint tokens. Their limit lives in SQLite (table `mints`, per network bucket
and clock hour, rows older than two days pruned), so a deploy does not reset it:

| Env | Default | |
|---|---|---|
| `REGISTER_LIMIT_PER_HOUR` | 20 | Per client network per clock hour: IPv4 the address, IPv6 its `/MINT_IPV6_PREFIX` (48). Schools and offices share one IP. |
| `REGISTER_LIMIT_PER_DAY` | 60 | Per client network over the last 24 clock hours. |
| `MINT_IPV6_PREFIX` | 48 | ISPs hand one home a /56 or a /48, so counting mints by /64 would give one user 256 to 65536 buckets. |
| `GLOBAL_MINTS_WARN_PER_HOUR` | 500 | Every network together: a WARNING once an hour from here on. |
| `GLOBAL_MINTS_PER_HOUR` | 2000 | Every network together: new installs get 429 `install_global` until the next hour. |

Each token row keeps the network it was minted from (`tokens.mint_net`), and `ANON_DAILY_USD_PER_NETWORK` (5.00)
caps the estimated spend of every *unlinked* install minted from one network together per UTC day (429
`miyagi_quota`, `limit: daily_spend`, `scope: network`). Without it one IPv4 address could mint 60 installs a day
x `FREE_DAILY_USD` = $60, past the $25 `DAILY_USD_CAP` that stops everyone. A school behind one address shares
those $5 while anonymous; signed-in learners count per account instead. Tokens minted before this version have
no network and only their own caps.

## Calls in flight

`PER_TOKEN_INFLIGHT` (10) calls per install token and `GLOBAL_INFLIGHT` (80) in total may be with a provider
at once. One more gets a 429 with type `concurrency_limit_error` (not `rate_limit_error`, so the engine treats
it as transient), `limit: inflight_token | inflight_global` and `Retry-After: 1`.

**Why 10 per install, and not 4.** Counted from the engine on `integration/live`: `server/lesson/claude.py` runs
up to 4 Claude calls at once (`CONCURRENCY`), `server/lesson/progressive.py` watches 3 Gemini windows in parallel
(`PARALLEL_WINDOWS`) while the learner already works, and the coach's scene looks, judge, screen picks and
diagrams run alongside: about 9-10 at the peak. Several of those never retry a 429 (the scene look and diagrams
use `max_retries=0`, the finder's Gemini `attempts=1`), and a 429 on a Gemini window makes `builder.py` treat it as
"quota" and fall back to the transcript, so long-video lessons get worse. 4 would cut real lessons; 10 does not.

The two slots are taken at different times. The per-install slot is taken after authentication and a read-only
check of the caps, before the request body is read, so one install cannot open more bodies than its slots. The
global slot is taken only once the body has arrived and passed the allowlist, so slow uploads cannot hold the
slots every other install needs. The body must arrive within `BODY_READ_TIMEOUT_S` (20 s; every route that reads a
body), else 408 `request_timeout` and the slot is released. Both slots are released in a `finally` when the call
ends: a JSON response, an upstream error, a cancelled read, the end of a stream, or a client that hangs up
mid-stream. Oversized bodies are refused on `Content-Length` before any of this (`Guard`).

**Body bytes in memory.** The AI routes need a `Content-Length` (411 `length_required` without one; the SDKs
always send it). Together with the per-install slot, that many bytes are held against `MAX_INFLIGHT_BODY_MB`
(64) for every install together and `MAX_INFLIGHT_BODY_PER_IP_MB` (16) per client network (IPv4 address, IPv6
/48: the mint bucket), from before the body is read until the call ends. Past either: 429
`concurrency_limit_error` with `limit: inflight_bytes | inflight_bytes_network` and `Retry-After: 1`. Without it,
bodies dripped in over 20 s were bounded only by tokens x `PER_TOKEN_INFLIGHT`, and minting gives 60 tokens per
IPv4 a day. Only the encoded upstream payload is kept while a call is with the provider (the parsed body is
dropped first), and parsing itself stops at `JSON_MAX_OBJECTS`, so the memory one request can take is bounded
too (a 2 MB body of empty objects peaks at about 8 MB instead of 55 MB). `/v1/link` takes at most 16 KB and the
admin login form 4 KB.

One install at its busiest (about 10 calls, a few with a 1280-wide JPEG screenshot of 200-400 KB) holds 2-3 MB,
so 16 MB per network covers a household or a few learners. A classroom behind one IPv4 address can pass it at
peaks and get short 429s (the SDKs retry them, but the scene look and diagrams use max_retries=0): raise
`MAX_INFLIGHT_BODY_PER_IP_MB` toward `MAX_INFLIGHT_BODY_MB` if schools report it.

## Accounts: `POST /v1/link`

Links an install to the signed-in miyagi account so its caps are counted per user. Installs that never link keep
using the proxy with the anonymous caps, and signing out in the app never unlinks.

```
POST /v1/link
Authorization: Bearer <mi_ install token from /v1/install>
{"access_token": "<Supabase user access token (JWT)>"}

200 {"ok": true, "user_id": "<jwt sub>"}   linked; re-linking the same pair is 200 and keeps the first linked_at
401 {"error": "bad_install_token"}         missing, unknown or disabled install token (checked first)
403 {"error": "bad_access_token"}          not a valid Google sign-in for this project (below)
403 {"error": "too_many_installs"}         the user already has LINK_MAX_INSTALLS_PER_USER (10) other installs
503 {"error": "link_unavailable"}          the cloud cannot verify: no JWKS
```

The errors are the flat `{"error": kind}` shape, not the proxy's `{type, error: {...}}` shape. A link from a
different account on the same install replaces the user (one user per install). Relinking never moves spend
between caps: what the install had used that UTC day stays counted against the user it leaves, or, on its first
link, against its mint network's anonymous pool (`ANON_DAILY_USD_PER_NETWORK`), through the table `moved_usage`.
The new user's sum sees the install's whole day too. Without this, moving spent installs onto a spare Google
account reset `LINKED_DAILY_USD`, and linking a spent anonymous install freed its network's pool. Like every `/v1`
route it answers 503 `proxy_disabled` while `PROXY_ENABLED=false`.

Verification (`supabase_auth.py`, PyJWT with the `cryptography` backend):

- ES256 and RS256 tokens are checked against `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`, fetched at most
  every 10 minutes. A failed refresh keeps the last good key set; with none at all the route answers 503 and
  retries the fetch after 30 s. An unknown `kid` triggers one refetch (at most once a minute).
- HS256 is accepted only when `SUPABASE_ALLOW_HS256=1` and `SUPABASE_JWT_SECRET` is set. By default only the
  JWKS keys count, and an HS256 token gets 403.
- Every token needs `aud == "authenticated"`, `iss == ${SUPABASE_URL}/auth/v1`, a future `exp`, a `sub`,
  `role == "authenticated"`, `is_anonymous` not true, and a Google sign-in: `app_metadata.provider == "google"`
  or `"google"` in `app_metadata.providers`. Supabase's Email provider is enabled with sign-ups allowed, so an
  email/password or anonymous account is otherwise a free source of linked caps. `app_metadata` is written by
  Supabase Auth only; `user_metadata` is editable by the user and is never read.
- `exp`, `iat` and `nbf` allow 30 s of clock skew (`LEEWAY_S`).
- The access token is never logged or stored. The table `links (token_hash, user_id, linked_at)` holds the
  result; the request log line gains `user=<user_id>` for linked installs, and `/admin/usage` `by_token` rows
  carry `user_id` (null when unlinked).

## Free tier caps (ROADMAP 3.7, A01)

`x-miyagi-role` (coach, lesson, screen, finder, diagram, workspace) is a label for the usage log and the coach
cap only: every forwarded call counts against the daily caps whatever its role, and a call without one counts
the same. Installs start on the `free` plan. A cap set to 0 is off.

| Cap | Env | Default | Counted |
|---|---|---|---|
| All AI calls, anonymous install, per UTC day | `FREE_DAILY_REQUESTS` | 300 | Every forwarded call of an unlinked install. |
| Estimated USD, anonymous install, per UTC day | `FREE_DAILY_USD` | 1.00 | The same calls' estimated cost. |
| Estimated USD, every anonymous install of one network, per UTC day | `ANON_DAILY_USD_PER_NETWORK` | 5.00 | See "Install minting". |
| All AI calls, linked user, per UTC day | `LINKED_DAILY_REQUESTS` | 1000 | Every install linked to the same Supabase user, together. |
| Estimated USD, linked user, per UTC day | `LINKED_DAILY_USD` | 3.00 | The same, in dollars. |
| Coach calls per UTC day | `FREE_COACH_CALLS_PER_DAY` | 60 | An extra cap on `x-miyagi-role: coach`, anonymous and linked installs. |
| New lesson builds per UTC month | `FREE_LESSON_BUILDS_PER_MONTH` | 3 | Distinct videos claimed with `POST /v1/lessons/{id}/build`. Cache hits and rebuilding a claimed video are free. |
| Spend kill switch, every install, per UTC day | `DAILY_USD_CAP` | 25 | See "Kill switches". |

`pro` (set with `/admin/tokens/{prefix}/plan`) skips the per-install and per-user caps; the kill switch still applies.

**Why these defaults, and not 100 calls / $0.25 (anonymous) and 300 / $1.50 (linked).** Counted from the
engine on `integration/live`: building a new lesson is roughly 20-35 calls (Gemini watches the video in parts,
`step_detail` per step, the Claude lesson and adapt passes, workspace setup, diagrams, the finder's searches)
and $0.20-0.50. Following it for 30-60 minutes adds 100-200 more: Haiku scene looks every ~5 s while the screen
changes (`server/orchestrator/scene_watch.py`, role coach), the judge (at most every 20 s, role coach), screen
target picks (up to 6 a minute, role screen) and coach cards. So one normal lesson is about 150-250 calls and
$0.30-0.60: 100 calls or $0.25 would stop a learner in the middle of their first lesson. 300 / $1.00 covers one
full lesson with room for retries; 1000 / $3.00 covers three or four lessons a day for a signed-in learner.

**Reservations.** When a call is admitted, its likely worst-case cost is reserved in the same transaction that
checks and counts it, input included (a large prompt with `max_tokens: 1` is not free):

- Input: the forwarded JSON's bytes / 3 at the input price (real text is nearer 4 bytes a token, so this errs
  high), with each base64 image at 5000 tokens instead of its bytes. Anthropic adds what the allowed server tools
  may pull in: `max_content_tokens` per `web_fetch` use and 8000 tokens per `web_search` use. Gemini adds each
  YouTube part: with a window (an end offset after its start: the engine's windows), its seconds x (fps x 258
  tokens a frame, 70 at `MEDIA_RESOLUTION_LOW`, + 32 audio tokens), fps 1 when unset and at most `GEMINI_MAX_FPS`
  (2); without one (no end, an unparseable offset, or an end equal to the start), a whole video:
  `GEMINI_VIDEO_RESERVE_TOKENS` (300000, about 30 minutes at the engine's 0.5 fps), scaled up by the part's rate
  when it is above 0.5 fps. Each part, and the call's whole input, is capped at `GEMINI_CONTEXT_TOKENS` (1048576):
  no call can bill more input than the context.
- Output: Anthropic `max_tokens` (after the cap; thinking is inside it); Gemini the clamped `maxOutputTokens`
  (thinking is inside it too), at the output price. Plus $0.01 per allowed server-tool use.

When the call ends the reservation is swapped for the real cost read from the response, but only when the
response's final usage was seen: Anthropic's `message_delta` / `message_stop` event, Gemini's last chunk (a
`finishReason` with its `usageMetadata`), or a whole non-stream body with its usage object. The events are parsed
as JSON, so model text (always inside escaped strings) cannot fake one. A call that ends without its final usage
(the client hung up, the upstream stream dropped, a non-stream read was cancelled, a read timeout after the
request was sent) keeps its whole reservation, or the observed cost when that is higher: the provider bills the
prefill either way. Before this, a streamed call whose client hung up before the final event settled at $0, so one
install could spend real money all day while its caps and `DAILY_USD_CAP` never moved. Only a provider that was
never reached (connect error) or that refused the call (any non-200, which is not billed) drops the reservation.
The log line shows `held=<usd>` for a held call. Parallel calls therefore cannot all slip under a USD cap: with 80
calls in flight, the caps are passed by at most about one call's estimation error, not by a whole wave. A refused
call is not counted.

The settled price follows the model that answered (a server-side fallback may answer on another model): the
requested model or a dated variant of it at its own price, another known non-Opus model at its own price, and
Opus or any model without a `PRICES` entry at the higher of its entry and the default ($2 / $10 per million),
never below the requested model's.

Over a cap the proxy answers 429 with `x-should-retry: false`, `retry-after`, and:

```json
{"type": "error", "error": {"type": "miyagi_quota", "status": "MIYAGI_QUOTA", "code": 429,
  "message": "You've reached today's limit. It resets tomorrow.",
  "limit": "daily_requests", "used": 300, "cap": 300, "resets_at": "2026-11-22T00:00:00Z", "scope": "install"}}
```

`type` is `miyagi_quota` for the daily caps (the engine's `cloud_error()` reads it) and `miyagi_lesson_quota`
for the monthly build cap. `limit` is `daily_requests`, `daily_spend` (both with `scope: install | account`),
`coach_calls`, `daily_usd` (the kill switch; `used` and `cap` are dollars there) or `lesson_builds`.

## Security

- Request bodies, prompts, screenshots, install tokens, admin tokens and keys are never logged. One line per
  request: method, path, status, latency, model, token counts, token-hash prefix, and `rl=` for a rate-limit 429.
  Uvicorn's access log is turned off because it would print query strings.
- Body size limit: `MAX_GEMINI_BODY_MB` (2) on `/v1/gemini/*`; 4 KB on `/v1/install`, `/v1/register` and every
  `/admin` route; 16 KB on `/v1/link`; 32 KB on `/v1/events`; `MAX_BODY_MB` (2) elsewhere. `Guard` checks it on
  `Content-Length` and while reading chunked bodies, before any route buffers the body, and the small routes read
  their body under `BODY_READ_TIMEOUT_S` (408 after) and validate it themselves instead of through a FastAPI body
  parameter (which read up to 2 MB with no time limit before the handler ran). Body bytes in memory are bounded in
  total and per network (Calls in flight), and parsing stops at `JSON_MAX_OBJECTS`.
- No CORS: no `Access-Control-*` headers, and any `/v1` request carrying an `Origin` header is refused with 403.
- Admin token (A22): `ADMIN_TOKEN` must be at least 32 characters, with at least 12 distinct characters, and
  not a well-known value (`test`, `admin`, `changeme`, `password`, `admin-test`, ...). A weak or missing one does
  not stop the server (production would go down on a merge): it logs an ERROR at startup and every `/admin*`
  route answers 503 `admin_disabled` until it is replaced. Admin tokens are compared in constant time, and the
  lockout above stops guessing.
- No `/docs` or `/openapi.json`.

## Kill switches

- `PROXY_ENABLED=false` makes every `/v1` route return 503 with
  "Miyagi cloud AI is paused by the operators. Try again later." `/healthz` and `/admin` keep working.
- Disable one install: `curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" $URL/admin/tokens/<prefix>/disable`
  (take the prefix from `/admin/usage`). Its calls then get 403.
- `DAILY_USD_CAP` (dollars): once the estimated spend of every install together (in-flight reservations
  included) reaches it in the current UTC day, every forwarded AI call, pro installs included, gets the 429
  `miyagi_quota` above with `limit: "daily_usd"` until UTC midnight. Cache reads, build claims and events keep
  working. Unset or empty means 25 (fail closed); only an explicit `0` turns it off. `/admin` shows today's
  estimate.

## Shared lesson cache (ROADMAP 3.1, A08)

Lesson builds are the expensive call, and many learners open the same videos. The flow:

1. `GET /v1/lessons/{video_id}?schema=N`. An approved lesson is used as the video draft and costs nothing.
2. On a miss, `POST /v1/lessons/{video_id}/build` uses one of the install's builds. A 429 here stops the
   build with a calm card; any other failure lets the engine build locally.
3. After a good build, `PUT /v1/lessons/{video_id}` with `{schema, lesson}`. The upload is a **pending
   candidate** for that video, schema and uploader. Nobody, the uploader included, is served it until an
   operator approves it: `GET /admin/lessons/pending`, read the whole candidate at its `full` path
   (`GET /admin/lessons/{video_id}/candidates/{hash}`: the pending list shows only libraries, commands and files,
   and the instructions are free text that could tell learners to paste anything), then
   `POST /admin/lessons/{video_id}/approve` with the candidate's `hash`. There is no first-writer-wins and no 409: a second uploader is never blocked by the first.
   `LESSON_AUTO_APPROVE_N` (default 0 = off) approves automatically once N uploads with the identical normalized
   lesson (sorted keys) came from N different install tokens on N different networks (IPv4 /24, IPv6 /48).
4. A bad uploader's lessons go with `DELETE /admin/lessons/by-uploader/{prefix}`; one video's with
   `DELETE /admin/lessons/{video_id}`.

Rules:

- `video_id` is an 11-character YouTube id. `schema` must be in `LESSON_SCHEMAS` (default `1`): no engine branch
  uploads lessons yet, so 1 is the only draft version in use. Add the next version there when the engine ships it.
- `MAX_LESSON_KB` (128): the lesson is stored as UTF-8 JSON (`ensure_ascii=False`) and its size is checked after
  encoding, so `\uXXXX` escapes on the wire neither dodge the limit nor inflate what is stored.
- Validation (engines pip-install a lesson's libraries, run its commands and open its files on learners' Macs; do
  this before `LESSON_AUTO_APPROVE_N` is ever turned on, and it backs up admin review):
  - 1 to 300 steps, all objects; every string at most 20000 characters, nesting at most 12 deep.
  - Only the keys of the engine's video draft (`server/lesson/schema.py` `VIDEO_DRAFT_SCHEMA`) and the step graph
    `builder.assemble()` makes from it. Top level: `title`, `summary`, `libraries`, `files`, `steps`, `lesson`
    (`id`, `title`, `goal`, `summary`, `libraries`), `sources`. Steps: the draft's step keys plus `id`, `index`,
    `video`, `precision_checks`, `sample_output`, `solution`, `setup`, `requires`. Checks (`checks` and
    `precision_checks`): the draft's check keys plus `id`, and `type` one of the engine's check types. Any other key
    is refused, so nothing an engine acts on passes unchecked.
  - `libraries` (`[{name, version}]` or `{name: version}`): plain package names (`[A-Za-z0-9._-]`, an optional
    `@scope/` and `[extras]`) and plain versions (`18.x`, `>=1.3,<2`): no URLs, `git+`, paths, spaces or options.
  - `run_command` and every check `command`: `^(python3?|pytest|node|npm run) [A-Za-z0-9_./ -]+$` (or `pytest`
    alone, or the engine's notebook text `Run the cell (Shift+Enter)`), with no `//`, `www.` or `..`, and nothing
    that runs code written on the command line or installs or serves anything: python takes a script first
    (after `-u`/`-B`/`-O`) or `-m` with only `pytest`, `unittest`, `venv`, `flask` or `streamlit` (no `-c`,
    `-m pip`, `-m http.server`); node takes a script first (no `-e`, `--require`, `--import`, `--inspect`); `npm run`
    a script name; no `npx`; pytest without `-p`, `-c`, `--pyargs` or `--rootdir`.
  - `file`, `files`, `targets[].file` and check files: relative paths inside the project (no `..`, not absolute,
    no `~`, no drive letter). `sources`: `https://` URLs.
- Only an install that claimed a build of the video may upload it, at most `LESSON_PUTS_PER_DAY` (10) uploads per
  install per UTC day (429 `lesson_uploads`).
- Pending storage is bounded so minted tokens cannot fill the disk (each fresh token can park 3 x 128 KB, and
  minting gives 60 tokens per IPv4 a day): pending candidates older than `LESSON_PENDING_MAX_DAYS` (14) are dropped
  on the next upload, and an upload that would take the pending bytes past `LESSON_PENDING_PER_NET_MB` (8) for its
  uploader network (IPv4 /24, IPv6 /48) or past `LESSON_PENDING_MAX_MB` (128) in total gets 507
  `insufficient_storage`. Approved lessons do not count, and re-uploading replaces the uploader's own candidate.
- Uploads stop with 507 `insufficient_storage` while the database disk is over `LESSON_DISK_MAX_PCT` (85) percent
  full, so the cache can never fill the disk the proxy needs.
- Lessons cached by the earlier first-upload-wins version become pending candidates on startup: none of them is
  served until reviewed.

## Product events: `POST /v1/events`

The app (`main/features/telemetry.ts`, only while "Share crash reports and usage" is on) and the engine
send product events with the install token:

```
POST /v1/events
Authorization: Bearer <mi_ install token>
{"events": [{"name": "step_passed", "at": "2026-11-21T18:02:11.000Z", "props": {"step_kind": "code"}}]}

202 {"ok": true}            taken (unknown names and malformed events inside are dropped, still 202)
401 authentication_error    missing, unknown or disabled install token
413 request_too_large       more than 50 events, or a body over 32 KB
400 invalid_request_error   not JSON, or no "events" list
```

Extra top-level fields (the app sends `source`, `app`, `platform`) are ignored. Nothing is stored as sent:

- `events (token_hash, day, name, count)`: one counter per install, UTC day and event name. Names outside
  `EVENT_NAMES` (default: the app's list in `telemetry/core.ts`) are dropped.
- `event_props (token_hash, day, name, key, value, count, total)`: only keys in `EVENT_PROP_KEYS`. A boolean
  or a short enum-like string (`[A-Za-z0-9_. -]`, up to 40 characters) is counted per value; a number is
  summed (`value` is empty, `total` holds the sum). Every other prop, a crash's `message` included, is dropped.
- `day` is the event's own `at` when it is today or up to 2 days back, else the day it arrived.
- At most `EVENTS_PER_DAY_PER_INSTALL` (2000) events per install and UTC day are kept; the rest get 202 and
  are dropped, so a client never retries them.

`/admin/usage` has `events` (per day and name: count and installs), and `/admin` an "Events per day" table.

## Admin view

`GET /admin/usage` with `X-Admin-Token` returns:

- `total`: requests, input and output tokens, estimated USD over the window
- `by_token`: the same per token-hash prefix (12 hex characters), with `disabled` and `user_id`
- `by_day`: the same per UTC day, with the number of active tokens
- `by_day_token_model`: per day, token, provider and model
- `lessons`: approved (`cached`) and `pending` lessons, cache hits, bytes, and new builds this month
- `usd_today`: estimated spend so far this UTC day, every install together, reservations included (what
  `DAILY_USD_CAP` reads)
- `events`: product events per UTC day and name, with how many installs sent them

USD is an estimate from the `PRICES` table in `app.py` (Anthropic list prices; the Gemini rows are placeholders
to check against Google's pricing). Override or add models with
`PRICES_JSON='{"model": [input_per_mtok, output_per_mtok]}'`.

Open `/admin` in a browser, paste the admin token into the form, and it shows the same tables.

## Environment variables

| Name | Default | Notes |
|---|---|---|
| `ADMIN_TOKEN` | none | 32+ characters, 12+ distinct. Render generates it (`generateValue: true`). Weak or missing: `/admin*` answers 503. |
| `ANTHROPIC_API_KEY` | none | Dashboard only (`sync: false`). Missing: Anthropic routes return 503. |
| `GEMINI_API_KEY` | none | Dashboard only (`sync: false`). Missing: Gemini routes return 503. |
| `PROXY_ENABLED` | `true` | `false` turns off every `/v1` route. |
| `ALLOWED_ANTHROPIC_MODELS` | `claude-sonnet-5-5,claude-haiku-5-5` | Comma-separated. Opus is rejected regardless. |
| `ALLOWED_GEMINI_MODELS` | `gemini-3.8-flash` | Comma-separated. See the engine note below. |
| `MAX_TOKENS_CAP` | `4096` | Upper bound on Anthropic `max_tokens` and `thinking.budget_tokens`. |
| `ANTHROPIC_BETAS` | `server-side-fallback-2026-07-01` | `anthropic-beta` values forwarded; any other is refused. |
| `ANTHROPIC_SERVER_TOOLS` | empty | `web_search` and/or `web_fetch` to allow those server tools (see below). |
| `SERVER_TOOL_MAX_USES` | `5` | Cap on an allowed server tool's `max_uses`. |
| `WEB_FETCH_MAX_CONTENT_TOKENS` | `20000` | `max_content_tokens` sent with every `web_fetch` (the client's, at most this). |
| `GEMINI_MAX_OUTPUT_TOKENS` | `32768` | Clamp on (and default for) `generationConfig.maxOutputTokens`, thinking included (What the Gemini route enforces). |
| `GEMINI_MAX_THINKING_TOKENS` | `2048` | Clamp on a `thinkingConfig.thinkingBudget` a client sends. |
| `GEMINI_VIDEO_RESERVE_TOKENS` | `300000` | Input held for a YouTube part without an end offset. |
| `GEMINI_MAX_FPS` | `2` | `videoMetadata.fps` is clamped to this before forwarding and reserving. |
| `GEMINI_CONTEXT_TOKENS` | `1048576` | The most input one Gemini call is reserved at (the model context). |
| `ALLOW_FAST_MODE` | `false` | Allow Anthropic `speed: "fast"`. |
| `ANTHROPIC_VERSION` | `2023-06-01` | Used when the client sends no `anthropic-version`. |
| `MAX_BODY_MB` / `MAX_GEMINI_BODY_MB` | `2` / `2` | Request size limits. |
| `MAX_INFLIGHT_BODY_MB` / `MAX_INFLIGHT_BODY_PER_IP_MB` | `64` / `16` | AI-call body bytes held in memory at once, in total / per client network. 0 = off. |
| `JSON_MAX_OBJECTS` | `50000` | JSON objects a request body may hold (counted while parsing). |
| `RATE_LIMIT_ENABLED` | `1` | The in-memory rate limiter (`RateLimit`). |
| `RATE_LIMIT_PER_IP_PER_HOUR` | `100` | Every `/v1/*` and `/admin*` request per client IP. |
| `RATE_LIMIT_PER_TOKEN_PER_HOUR` | `600` | AI, lesson and event calls per known install token. |
| `ADMIN_RATE_LIMIT_PER_IP_PER_HOUR` | `20` | `/admin*` requests per client IP. |
| `ADMIN_LOCKOUT_FAILURES` | `5` | Wrong admin tokens per IP per hour before the lockout. |
| `RATE_LIMIT_MAX_KEYS` | `200000` | Bound on the limiter's memory. |
| `ADMIN_FAILURE_MAX_KEYS` | `20000` | Bound on the admin-failure table (a tuple of at most 5 times per IP bucket: a few MB). |
| `TRUSTED_PROXY_HOPS` | `1` | Which `X-Forwarded-For` entry (from the right) is the client IP. |
| `CLIENT_IP_HEADER` | empty | A header to read the client IP from instead (for example `cf-connecting-ip`). Forgeable by anyone who reaches the origin directly. |
| `REGISTER_LIMIT_PER_HOUR` / `REGISTER_LIMIT_PER_DAY` | `20` / `60` | Installs minted per client network (SQLite). |
| `MINT_IPV6_PREFIX` | `48` | The IPv6 prefix mints and the per-network spend ceiling count by. |
| `GLOBAL_MINTS_WARN_PER_HOUR` / `GLOBAL_MINTS_PER_HOUR` | `500` / `2000` | Installs minted per hour, every client together: warn / refuse. |
| `PER_TOKEN_INFLIGHT` / `GLOBAL_INFLIGHT` | `10` / `80` | AI calls in flight per install / in total. |
| `BODY_READ_TIMEOUT_S` | `20` | Seconds a request body may take to arrive (408 after). |
| `FREE_DAILY_REQUESTS` / `FREE_DAILY_USD` | `300` / `1.00` | Anonymous install caps per UTC day. 0 = off. |
| `ANON_DAILY_USD_PER_NETWORK` | `5.00` | Every anonymous install minted from one network together, per UTC day. 0 = off. |
| `LINKED_DAILY_REQUESTS` / `LINKED_DAILY_USD` | `1000` / `3.00` | Linked user caps per UTC day, all their installs. 0 = off. |
| `FREE_COACH_CALLS_PER_DAY` | `60` | Coach calls per install per UTC day. 0 = off. |
| `FREE_LESSON_BUILDS_PER_MONTH` | `3` | New lesson builds per free install per UTC month. 0 = off. |
| `DAILY_USD_CAP` | `25` when unset or empty | Spend kill switch in dollars, every install together. Only `0` turns it off. |
| `LINK_MAX_INSTALLS_PER_USER` | `10` | Installs one Supabase user may link. |
| `SUPABASE_URL` | `https://wssdpsdbaqtnfhoyimit.supabase.co` | JWKS URL and expected `iss` derive from it. |
| `SUPABASE_ALLOW_HS256` | empty (off) | `1` to accept legacy HS256 tokens (needs `SUPABASE_JWT_SECRET`). |
| `SUPABASE_JWT_SECRET` | empty | Only with `SUPABASE_ALLOW_HS256=1`. Dashboard only. |
| `EVENTS_PER_DAY_PER_INSTALL` | `2000` | Events kept per install per UTC day. 0 = no cap. |
| `EVENT_NAMES` | the app's 11 names | Comma-separated event names `/v1/events` counts. |
| `EVENT_PROP_KEYS` | `kind,mode,reason,source,built_by,step_kind,level,cached,provider,model,usd,steps,minutes,seconds` | Prop keys kept (as counts or sums). |
| `MAX_LESSON_KB` | `128` | Largest shared lesson, measured as stored (UTF-8). |
| `LESSON_SCHEMAS` | `1` | Comma-separated lesson schema versions the cache accepts. |
| `LESSON_PUTS_PER_DAY` | `10` | Lesson uploads per install per UTC day. |
| `LESSON_AUTO_APPROVE_N` | `0` (off) | Auto-approve after N identical uploads from N tokens on N networks. |
| `LESSON_DISK_MAX_PCT` | `85` | Lesson uploads stop above this disk usage. |
| `LESSON_PENDING_MAX_DAYS` | `14` | Pending (unreviewed) uploads older than this are dropped. |
| `LESSON_PENDING_MAX_MB` / `LESSON_PENDING_PER_NET_MB` | `128` / `8` | Pending upload bytes in total / per uploader network (IPv4 /24, IPv6 /48); past either, 507. |
| `DB_PATH` | `/var/data/miyagi.db` if `/var/data` exists, else `./miyagi.db` | SQLite file. |
| `UPSTREAM_READ_TIMEOUT_S` | `300` | httpx read timeout (a Gemini video watch can take minutes). |
| `PRICES_JSON` | empty | Price table overrides for the USD estimate. |
| `UPSTREAM_ANTHROPIC_URL` / `UPSTREAM_GEMINI_URL` | the real APIs | For local tests against a mock only. Never set in production. |

**Server tools and the engine's finder.** The engine's finder (`server/finder/claude.py`, Haiku with
`web_search_20250305`) and text lessons (`server/lesson/textlesson.py`, `web_search` and `web_fetch`) send
server tools through the cloud. With `ANTHROPIC_SERVER_TOOLS` empty (the code default) those calls get 400;
`render.yaml` sets `web_search,web_fetch` so they keep working, with `max_uses` capped and every search counted
in the caps. Set it empty in the dashboard to turn web search through the cloud off.

## Deploy on Render

`render.yaml` is a Blueprint for one web service: `rootDir: cloud`, Python runtime, starter plan, health check
on `/healthz`, a 1 GB disk at `/var/data` for the SQLite file. Render looks for `render.yaml` at the repo root,
so when creating the Blueprint set its file path to `cloud/render.yaml`. Every new variable has its default in
`render.yaml` (and in code). After the first deploy, set `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` in the
dashboard.

A service with a disk runs as a single instance, which is what the in-memory rate limiter and in-flight counts
assume (see "Rate limits": per process, per instance).

### Render env Michael must set (dashboard, service miyagi-cloud, Environment)

Secrets (never in the repo; `sync: false` in `render.yaml`):

| Name | Value | Why |
|---|---|---|
| `ANTHROPIC_API_KEY` | the production Anthropic key | Anthropic routes answer 503 without it. |
| `GEMINI_API_KEY` | the production Gemini key | Gemini routes answer 503 without it. |
| `DAILY_USD_CAP` | a dollar figure, or leave unset for 25 | `sync: false`: the value lives only in the dashboard. |
| `SUPABASE_JWT_SECRET` | only if `SUPABASE_ALLOW_HS256=1` | Not needed: access tokens are verified against the JWKS. |

Check `ADMIN_TOKEN`: Render generates a long random value (`generateValue: true`), which passes. If someone set it
by hand to something short, `/admin` now answers 503 and the log says why; replace it with the output of
`python -c 'import secrets;print(secrets.token_urlsafe(32))'`.

Before this version reaches production (`claude/eng-proxy`), on staging: pass the release gate in "Rate limits"
(the `X-Forwarded-For` count and kind line), and check that the defaults in "Free tier caps" fit what you want to
give away. Merging into `claude/eng-proxy-next` does not need it.

## Run locally

```sh
cd cloud
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
ADMIN_TOKEN=$(python -c 'import secrets;print(secrets.token_urlsafe(32))') ANTHROPIC_API_KEY=fake GEMINI_API_KEY=fake \
  .venv/bin/uvicorn app:app --port 8790
curl -s localhost:8790/healthz
```

Tests (no network, no real keys; needs `pytest` in the venv): `.venv/bin/python -m pytest tests -q`. The
`/v1/link` tests skip when PyJWT is not installed.

## Moving to Postgres (Supabase)

All SQL lives in `store.py`. Write a `PostgresStore` with the same methods (`add_token`, `get_token`,
`set_disabled`, `set_plan`, `count_request`, `add_tokens`, `requests_today`, `count_role`,
`role_requests_today`, `admit_call`, `settle`, `usd_today`, `usd_today_for`, `mint_check`, `get_lesson`,
`put_candidate`, `lesson_candidates`, `approve_lesson`, `auto_approve`, `pending_lessons`, `delete_lessons`,
`delete_lessons_by_uploader`, `claim_lesson_put`, `builds_in_month`, `has_build`, `claim_build`, `add_events`,
`event_counts`, `event_props_rows`, `link_user`, `link_user_capped`, `get_link`, `usage_report`; `admit_call`,
`settle`, `mint_check`, `put_candidate`, `link_user_capped` and `add_events` need one transaction with a row lock) and return it
from `open_store()` when `DATABASE_URL` is set. The tables port as they are.

## How the app and the engine use it

1. On first launch the app (`app/src/main/features/cloud.ts`) calls `POST <host>/v1/install` and keeps the
   returned `mi_` token in the Keychain (safeStorage). The host defaults to `https://miyagi-cloud.onrender.com`;
   `MIYAGI_CLOUD_URL` overrides it, `off` turns it off.
2. The app sends the engine `config.keys {miyagiToken: <token>, miyagiCloud: "<host>/v1"}`. The engine
   (`server/config.py` `anthropic_kwargs()` / `gemini_kwargs()`) points its Anthropic and google-genai clients at
   `<host>/v1/anthropic` and `<host>/v1/gemini` (api_version v1beta) with the token as the key, and tags each call
   with `x-miyagi-role`.
3. A 401 means the token is unknown: the app mints a new one. A 403 means the install was disabled. A 503
   `proxy_disabled` means the operators paused the proxy. A 429 `miyagi_quota` (or a proxy-shaped
   `rate_limit_error`) shows the "today's limit" card.

**Models to allowlist.** The engine's Gemini defaults are `gemini-4-hydrogen` (video watch, `LESSON_MODEL`),
`gemini-3.8-flash` (`LESSON_FAST_MODEL`) and the fallbacks `gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash`.
With the default allowlist only `gemini-3.8-flash` passes; a model that is not allowed gets a 404 and the
engine skips to its next fallback, so the video watch needs at least one of its chain allowlisted.
