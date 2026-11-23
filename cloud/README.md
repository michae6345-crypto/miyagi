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
| `GET /healthz` | none, never rate limited | `{"ok": true, "version", "commit", "proxy_enabled", "paused", "db_ok", "gemini_enabled", "require_signin", "keys_configured": {"anthropic", "gemini"}}`. `commit` is `RENDER_GIT_COMMIT` (a hex SHA) or null; everything else is a boolean. Never a key, a path or a count. Always 200 while the process runs. |
| `POST /v1/install` | none; 20 per network per hour and 60 per day, shared with `/v1/register`; `NEW_INSTALLS_PER_DAY` (500) in all per UTC day | What the desktop app calls. Body `{app, os, arch}` (all optional, extra fields ignored) → `{token, token_id}`. `token` is `mi_` + 32 random bytes urlsafe (46 characters); `token_id` is the first 12 hex characters of its sha256, the same id the admin views and `/admin/tokens/{prefix}/disable` use. Past the daily new-install cap: 429 `miyagi_full` (see "Install minting"). |
| `POST /v1/register` | same limits | Older form. Body `{install_id, app_version, platform}` → `{token, token_id}`, same token shape. |
| `POST /v1/link` | install token | Links the install to a Google-signed-in miyagi account. See "Accounts" below. |
| `POST /v1/account/delete` | install token (+ the Supabase access token when signed in) | Deletes everything the cloud holds for the install and, signed in, for the whole account, then the Supabase auth user. See "Deleting an account". |
| `POST /v1/anthropic/messages` (also `/v1/anthropic/v1/messages`) | install token (linked, with `REQUIRE_SIGNIN=all`) | Messages API through our key, request body rebuilt from an allowlist (below). |
| `POST /v1/gemini/{model}:generateContent` and `:streamGenerateContent` (also under `/v1/gemini/v1beta/models/`) | install token (linked, with `REQUIRE_SIGNIN=all`) | **Off by default** (D1: Claude only): 403 `gemini_disabled`. With `ALLOWED_GEMINI_MODELS` set: generateContent through our key, body rebuilt from an allowlist (below). |
| `GET /v1/lessons/{video_id}?schema=N` | install token | Shared lesson cache: an approved lesson, or 404 `lesson_not_cached` (its `error.builds` says how many free builds are left). Free. |
| `POST /v1/lessons/{video_id}/build` | install token (linked, with `REQUIRE_SIGNIN=build` or `all`) | Use one of this month's new-lesson builds (per install, or per user when linked) and hold the video for `LESSON_CLAIM_TTL_S`. `?schema=N` optional. 200 `{ok, builds: {used, cap, month, resets_at}}`, 200 `{"held": true}` (another install is building it: nothing counted), or 429 `miyagi_lesson_quota`. |
| `PUT /v1/lessons/{video_id}` | install token | Body `{schema, lesson}`. Upload a lesson this install built, as a pending candidate. 201 `{stored, status: "pending" \| "approved", hash}`, 403 `build_not_claimed`, 400, 413, 429 `lesson_uploads`, 507 `insufficient_storage`. |
| `POST /v1/events` | install token | Product events, counts only. See "Product events" below. |
| `GET /admin/usage` | `X-Admin-Token` | JSON usage report. `?days=30` by default. |
| `POST /admin/proxy/pause` and `/resume` | `X-Admin-Token` | The runtime kill switch (see "Kill switches"). No body. Answers the state below. |
| `GET /admin/proxy` | `X-Admin-Token` | `{paused, proxy_enabled_env, daily_usd_brake, new_installs_today, new_installs_per_day, alert_daily_usd, alerts}`. |
| `POST /admin/alerts/test` | `X-Admin-Token` | Sends one test alert to `ALERT_WEBHOOK_URL` (once a UTC day, like every alert). `{alerts, sent}`. |
| `GET /admin`, `POST /admin` | admin token typed into a form | The same report as HTML. The token is posted in the form body, never in the URL. |
| `POST /admin/tokens/{prefix}/disable` and `/enable` | `X-Admin-Token` | Turn one install token off or on, by the first 8+ hex characters of its hash. |
| `POST /admin/tokens/{prefix}/plan` | `X-Admin-Token` | Body `{"plan": "free"}` or `{"plan": "pro"}`. Pro installs skip the per-install caps. |
| `GET /admin/lessons/pending` | `X-Admin-Token` | Uploaded lessons waiting for review: video, schema, 16-hex body hash, uploader prefix, size, and what to read before approving: the `libraries` it installs, every `commands` entry it suggests or runs, its `files`, and `full`, the path of the whole body. |
| `GET /admin/lessons/{video_id}/candidates/{hash}` | `X-Admin-Token` | The whole body of the candidates whose body hash starts with `hash` (8+ hex; `?schema=N` optional): every instruction, code block, solution, hint and explanation learners would receive, plus the review summary. Read it before approving. |
| `POST /admin/lessons/{video_id}/approve` | `X-Admin-Token` | Body `{"hash": "<8+ hex of the body hash>", "schema": N?}`. Serve that candidate (replaces any approved one). |
| `POST /admin/lessons/{video_id}/revoke` | `X-Admin-Token` | Body `{}` or `{"schema": N}`. Stop serving the approved lesson; it is never auto-approved again (see "Shared lesson cache"). `{video_id, revoked: [schemas], status}`. |
| `DELETE /admin/lessons/by-uploader/{prefix}` | `X-Admin-Token` | Drop every lesson one install uploaded (approved or pending). |
| `DELETE /admin/lessons/{video_id}` | `X-Admin-Token` | Drop every candidate of a video (every schema). |
| `GET /admin/deletions` | `X-Admin-Token` | Account deletions whose Supabase user is not deleted yet: `{pending: [{user_id, requested_day}], service_key}`. |
| `POST /admin/deletions/retry` | `X-Admin-Token` | Retry them all (wipes again whatever the account linked since, then deletes the Supabase user). `{deleted, pending}`. |

The install token is read from `Authorization: Bearer <token>`, or from `x-api-key` / `x-goog-api-key`,
which is where the engine's Anthropic and google-genai SDKs put it. The client's headers are never
forwarded upstream; the proxy sets the upstream key itself.

### What the Anthropic route enforces

The upstream JSON is rebuilt from allowlisted keys only. Kept: `model`, `messages`, `system`,
`max_tokens` (capped at `MAX_TOKENS_CAP`, 32000: what the lesson builder asks for), `temperature`, `top_p`, `top_k`, `stop_sequences`, `stream`,
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

Streaming has no buffering on our side: each upstream chunk goes to the client as it arrives (`StreamingResponse`;
`Guard` and `RateLimit` are pure ASGI), with `Cache-Control: no-cache` and `X-Accel-Buffering: no` so a proxy on
the way does not hold chunks back either. The caps, the in-flight slots, the kill switch and the usage count apply
to a stream exactly as to a plain call; a stream settles on its `message_delta` / `message_stop` usage.
`tests/test_stream.py` proves it offline: the client reads the first event while the mock upstream still holds the
rest, through the ASGI stack and through a real uvicorn socket on 127.0.0.1.

Every call goes out on one process-wide httpx client that keeps idle upstream connections open for
`UPSTREAM_KEEPALIVE_S` (90 s), so a question reuses the TLS connection the last call (or a warm-up) opened. It
speaks HTTP/2 when the `h2` package is installed (it is not in `requirements.txt`, so production uses HTTP/1.1
keep-alive).

**Prompt-cache warm-up.** `max_tokens: 0` with `stream: false` is allowed: Anthropic runs the prefill (writing the
cache at the `cache_control` breakpoint) and answers `content: []` with usage. Its reservation is the input alone
and it settles at the cache write (a ~700-token system prompt on Sonnet is about $0.002), so it fits under every
cap. `max_tokens: 0` with `stream: true` is a 400 here before any upstream call (Anthropic refuses it too).

### What the Gemini route enforces

- **Off by default.** The founders' D1 decision is Claude only at launch (Gemini's terms are 18+, miyagi's gate
  is 13+), so `ALLOWED_GEMINI_MODELS` is empty in code and `none` in `render.yaml`, and every Gemini call gets
  403 `gemini_disabled` ("Gemini is off on this proxy. miyagi uses Claude."), before the body is read and with
  nothing counted. Its type is not `permission_error`, so the engine does not take it for a disabled install, and
  a 403 makes the engine mark Gemini unavailable instead of walking its fallback models (a 404 would). `/healthz`
  says `gemini_enabled: false`. It stays configurable: set `ALLOWED_GEMINI_MODELS` (and `GEMINI_API_KEY`) to bring
  Gemini back, for example through Vertex AI once an adult-held account exists.
- With Gemini on, `{model}` must be in `ALLOWED_GEMINI_MODELS`; any other model gets a 404 (Google's own reply for
  an unknown model, so the engine skips to its next fallback at once).
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
| Per install token | `RATE_LIMIT_PER_TOKEN_PER_HOUR` | 2400 | Above a normal lesson's busiest hour (scene looks alone are up to 720 an hour, plus the judge, screen picks, coach cards and events); 600 stopped real lessons. `/v1/anthropic/*`, `/v1/gemini/*`, `/v1/lessons/*`, `/v1/events`, counted per token instead of per IP, but only when the presented token (Bearer, `x-api-key` or `x-goog-api-key`) is a known, enabled one. A missing or unknown token counts against the IP, so guessing tokens is IP-limited, and a school behind one IP is not limited to 100 calls. |
| Admin per IP | `ADMIN_RATE_LIMIT_PER_IP_PER_HOUR` | 20 | Every `/admin*` request (on top of the IP limit). |
| Admin lockout | `ADMIN_LOCKOUT_FAILURES` | 5 | Wrong admin tokens (header or form) from one IP within an hour. Then every `/admin*` request from that IP gets 429 `admin_lockout`, the right token included, until the oldest of those failures is an hour old. Each failure logs a WARNING with the network's keyed hash (`n1:...`), never the IP or what was presented. Holds even with `RATE_LIMIT_ENABLED=0`. |

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
and clock hour), so a deploy does not reset it. The bucket is stored as its keyed hash, never the address, and a
row for clock hour H is deleted once the current hour passes H + 48 (at most 49 hours):

| Env | Default | |
|---|---|---|
| `REGISTER_LIMIT_PER_HOUR` | 20 | Per client network per clock hour: IPv4 the address, IPv6 its `/MINT_IPV6_PREFIX` (48). Schools and offices share one IP. |
| `REGISTER_LIMIT_PER_DAY` | 60 | Per client network over the last 24 clock hours. |
| `MINT_IPV6_PREFIX` | 48 | ISPs hand one home a /56 or a /48, so counting mints by /64 would give one user 256 to 65536 buckets. |
| `GLOBAL_MINTS_WARN_PER_HOUR` | 500 | Every network together: a WARNING once an hour from here on. |
| `GLOBAL_MINTS_PER_HOUR` | 2000 | Every network together: new installs get 429 `install_global` until the next hour. |
| `NEW_INSTALLS_PER_DAY` | 500 | Every network together, per UTC day (D13). 0 = off. See below. |

**The daily new-install cap (D13).** Instead of a fixed spend breaker, which would trip on a good launch day and
stop every learner, the number of new installs per UTC day is capped. The count lives in SQLite (table
`install_days`), checked and counted in the same transaction as the per-network limits, so restarts, deploys and
parallel mints cannot pass it, and a mint the per-network limit refuses is not counted. Installs already minted
keep working all day. Past the cap, `/v1/install` and `/v1/register` answer:

```json
{"type": "error", "error": {"type": "miyagi_full", "status": "MIYAGI_FULL", "code": 429,
  "message": "miyagi is full today, try tomorrow.", "limit": "new_installs", "resets_at": "2026-11-22T00:00:00Z"}}
```

with `retry-after` (seconds to UTC midnight) and `x-should-retry: false`. No counts: the route is public. The app
shows the message as is (R01 step 8). The `installs_full` alert fires when the cap is reached (see "Alerts").

Each anonymous token row keeps the keyed hash of the network it was minted from (`tokens.mint_net`; linking or
deleting the install drops it, and `MINT_NET_RETAIN_DAYS` can drop it sooner), and `ANON_DAILY_USD_PER_NETWORK` (5.00)
caps the estimated spend of every *unlinked* install minted from one network together per UTC day (429
`miyagi_quota`, `limit: daily_spend`, `scope: network`). Without it one IPv4 address could mint 60 installs a day
x `FREE_DAILY_USD` = $120 a day. A school behind one address shares
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
using the proxy with the anonymous caps (unless `REQUIRE_SIGNIN` is `build` or `all`, see "Sign-in required"), and signing out in the
app never unlinks.

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
  result; the request log line gains `linked=1` for linked installs (never the user id), and `/admin/usage`
  `by_token` rows carry `user_id` (null when unlinked).

## Sign-in required: `REQUIRE_SIGNIN`

A mode, **off by default** (`0` in code and `render.yaml`). The app offers "Continue without an account" and the
privacy policy says signing in is optional, so turning it on is a product decision, not a deploy detail.

| Value | Build routes (`POST /v1/lessons/{id}/build`) | Runtime model calls (`/v1/anthropic`, `/v1/gemini`) for a guest |
|---|---|---|
| `0` / `off` (default; an unknown value too, logged) | open | open, `FREE_DAILY_USD` per install |
| `build` | linked installs only | open, **`ANON_DAILY_USD`** (0.50) per install per UTC day: 429 `miyagi_quota` with `limit: "anon_daily_cap"`, `scope: "install"`, `unit: "usd"`, `resets_at` and "You've used today's free guest help. Sign in to keep going, or come back tomorrow." |
| `all` (or `1`) | linked installs only | linked installs only |

Linked users keep `LINKED_DAILY_USD` and `LINKED_DAILY_TOKENS` in every mode, and `ANON_DAILY_USD_PER_NETWORK` still
pools a network's guests. The cloud cannot tell a build's model calls from runtime ones (`x-miyagi-role` is set by
the client), so in `build` mode a guest who skips the build claim and calls the builder's prompts directly is held by
`ANON_DAILY_USD` (about one small build), not refused.

A gated route answers, for an install that is not linked to a Supabase user (the `links` table, written by
`POST /v1/link`):

```
401 {"error": "signin_required", "message": "Sign in to keep using miyagi."}      x-should-retry: false
```

after the token checks (a missing or unknown token is still 401 `authentication_error`, a disabled install 403) and
before anything else: no cap is read, no slot taken, no body read. The flat shape is the one `/v1/link` uses.

| Route | Spends money | `build` | `all` |
|---|---|---|---|
| `POST /v1/anthropic/messages`, `/v1/anthropic/v1/messages` | yes (our Anthropic key) | open (guest cap) | linked only |
| `POST /v1/gemini/...` (both paths, both methods) | yes when Gemini is on (off today: 403 `gemini_disabled`) | open (guest cap) | linked only (checked before `gemini_disabled`) |
| `POST /v1/lessons/{id}/build` (the only route that starts a new build) | it gates a lesson build (20-35 model calls) | linked only | linked only |
| `GET /v1/lessons/{id}` | no (a cache read) | open | open |
| `PUT /v1/lessons/{id}` | no (needs a build claimed first, which is gated) | open | open |
| `/v1/install`, `/v1/register`, `/v1/link`, `/v1/account/delete`, `/v1/events`, `/healthz`, `/admin*` | no | open | open |

`pro` installs are not exempt: an operator who wants a demo Mac to work signed out links it or leaves the flag off.
`/healthz` says `require_signin: "off" | "build" | "all"`, so the app can ask for a sign-in up front.

**Before setting `build` or `all`.**

- Engine: on `integration/live` `server/config.py` `_classify_cloud` reads every cloud 401 as an unknown install token
  (`miyagi_auth`, `cloud.token_invalid`), and the app then mints a new install, which is a guest too: each refused
  call would burn a mint until the per-network mint limit stops it. It must read `error == "signin_required"` first,
  never re-mint for it, and hand it to the app as "sign in needed"; and show the `anon_daily_cap` 429 (type
  `miyagi_quota`) as a sign-in prompt rather than "come back tomorrow" only.
- App: show a sign-in prompt at build time (`build`), or before any lesson (`all`), and keep "Continue without an
  account" only for what still works signed out.
- Privacy policy: say that building a lesson needs an account (`build`), or that using miyagi does (`all`). A Blueprint sync writes `render.yaml`'s `"0"` back over
a dashboard value: change `render.yaml` too when the flag goes on.

## Deleting an account: `POST /v1/account/delete`

```
POST /v1/account/delete
Authorization: Bearer <mi_ install token>
{"access_token": "<Supabase user access token (JWT)>"}    signed in
{}                                                       signed out (an empty body or "access_token": null too)

200 {"ok": true, "install": true | false, "account": "deleted" | "none" | "pending"}
                                      install: whether the Bearer token was a live install (now deleted)
401 {"error": "bad_install_token"}    ONLY when there is no valid access token AND the install token is missing,
                                      unknown or disabled (e.g. a repeated signed-out call): the app treats it as
                                      already deleted
403 {"error": "bad_access_token"}     live install token but an invalid access token: nothing deleted
400 {"error": "bad_request"}          live install token, body not a JSON object: nothing deleted
413                                   body over 16 KB (the /v1/link cap)
503 {"error": "delete_unavailable"}   the JWT cannot be verified right now (no JWKS): nothing deleted, retry
```

Same install-token check, body cap and JWT verifier as `/v1/link`; rate limited per client IP like it.

- Signed in: every row tied to the user id and to every install linked to it, plus the calling install, then the
  Supabase auth user (`DELETE ${SUPABASE_URL}/auth/v1/admin/users/{id}` with `SUPABASE_SERVICE_ROLE_KEY`; a 404
  counts as deleted). `account` is `"deleted"`. A valid access token is enough on its own: with the install token
  missing, unknown or disabled (an earlier signed-out delete, a wiped install file) the account and every linked
  install are still deleted, and `install` is `false`.
- Signed out: the calling install's rows only. `account` is `"none"`.
- Without the key, or when Supabase fails: the cloud data is deleted anyway, the user id goes into
  `deletion_requests (user_id, requested_day)`, the `account_delete_pending` alert fires (no user id in it), and
  `account` is `"pending"`. `GET /admin/deletions` lists them, `POST /admin/deletions/retry` retries.

Rows deleted: `tokens`, `links`, `usage`, `builds`, `role_usage`, `events`, `event_props`, `event_intake`,
`lesson_puts`, the install's `alerts_sent` keys, `moved_usage` rows naming the user (`from_user`), and the
installs' pending `lesson_candidates` with their network hash. `install_days` and `mints` hold no install or user.
Kept, with nothing pointing back at anyone:

- An approved shared lesson the install uploaded stays served: its `uploader` becomes `deleted-<random>` and its
  network is cleared. It holds only the lesson built from a public video, reviewed by an operator, and other
  learners use it; deleting it would make the next learner pay for a rebuild and would not remove anything about
  the person.
- Today's spend of the deleted installs is folded into the day's total row (`token_hash = '*'`), so the spend
  alerts and `DAILY_USD_CAP` still see what today cost; an anonymous install's spend today also stays against its
  mint network's hash (`moved_usage`, pruned after 2 days), so delete-and-re-mint cannot reset
  `ANON_DAILY_USD_PER_NETWORK`. Older usage rows are deleted outright.

## Data we keep

The server never stores an IP address or prefix: client networks are stored only as a keyed hash
(`n1:` + 24 hex of HMAC-SHA256 under `NET_HASH_KEY`, else a key derived from `ADMIN_TOKEN`), which groups requests
from one network for the limits below and cannot be turned back into an address without the server's key. Databases
from before this version are converted on startup. Per-install rows are pruned at startup and every hour
(`PRUNE_EVERY_S`): rows older than `RETAIN_DAYS` (35, never less) are folded into per-day totals with no install
(`token_hash = '*'`) or deleted.

| Table: columns | Why | How long |
|---|---|---|
| `tokens`: token_hash, install_id (= the token prefix; the client's own id is not kept), app_version, platform, created_at, disabled, plan | Authenticate the install; plan and disable switch; app version and OS to know which clients still call before an API change | Until the install deletes itself (or an operator disables it) |
| `tokens.mint_net` (keyed hash) | `ANON_DAILY_USD_PER_NETWORK`: one network cannot multiply the free cap by minting installs | While the install is anonymous: dropped on link or delete, or after `MINT_NET_RETAIN_DAYS` when set |
| `links`: token_hash, user_id, linked_at | Per-account caps | Until account delete |
| `usage`: token_hash, day, provider, model, requests, tokens, usd | Daily dollar caps, spend alerts, the admin view | 35 days per install, then folded into per-day totals |
| `role_usage`: token_hash, day, role, requests | The admin view's role label | 35 days |
| `builds`: token_hash, month, video_id, created_at | The monthly build cap; only a builder may upload that lesson | 35 days |
| `events`, `event_props`: token_hash, day, name, (key, value), count, total | Product counts (allowlisted names and enum-like props) | 35 days per install, then folded into per-day totals |
| `event_intake`: token_hash, day, taken | `EVENTS_PER_DAY_PER_INSTALL` | 2 days |
| `moved_usage`: token_hash, day, from_user, from_net (keyed hash), requests, usd | Relinking cannot reset a cap | 2 days |
| `lesson_puts`: token_hash, day, n | `LESSON_PUTS_PER_DAY` | 2 days |
| `lesson_candidates`: video_id, schema, uploader, body, bytes, body_hash, net (keyed hash), status, created_at, hits | The shared lesson cache and its review | Pending: `LESSON_PENDING_MAX_DAYS` (14). Approved: kept; `net` cleared on approval, `uploader` scrubbed on account delete. Revoked: kept until deleted by an operator or the uploader's account delete |
| `lesson_revocations`: video_id, schema, revoked_at | Revoked videos are never auto-approved again | Kept |
| `lesson_claims`: video_id, schema, token_hash, claimed_at, expires_at | One install builds a video at a time | Until released or expired (`LESSON_CLAIM_TTL_S`), pruned hourly; deleted with the install |
| `lessons` | Legacy first-upload cache, emptied into `lesson_candidates` on startup | Empty |
| `mints`: bucket (keyed hash), hour, n | Mint limits per network | At most 49 hours |
| `install_days`: day, n | `NEW_INSTALLS_PER_DAY` (a count, no install) | Kept (one row a day) |
| `alerts_sent`: day, key (`token:<prefix>` names an install) | One alert per key a day | 2 days |
| `settings`: key, value | The runtime pause | Kept |
| `deletion_requests`: user_id, requested_day | Finish a deletion Supabase refused | Until the Supabase user is deleted |

Logs: method, path, status, latency, model, token counts, the 12-hex token-hash prefix and `linked=1`. Never a
token, an access token, a user id, a body or an IP address. Alerts carry dollar amounts, counts and at most the
12-hex install prefix.

## Free tier caps (ROADMAP 3.7, A01)

Every cap keys on the install token or the signed-in user (or the anonymous installs of one mint network), in
dollars counted on the server from the usage table: estimated cost, in-flight reservations included. The
`x-miyagi-role` header (coach, scene, lesson, screen, finder, diagram, workspace) is set by the client, so it is
only a label: it shows in the log line (`role=`) and is counted per install in `role_usage` for the usage view,
and no cap reads it. Changing it can neither lift nor move a cap. Installs start on the `free` plan. A cap set to
0 is off.

| Cap | Env | Default | Counted |
|---|---|---|---|
| Estimated USD, anonymous install, per UTC day | `FREE_DAILY_USD` | 2.00 | Every forwarded call of an unlinked install. |
| Estimated USD, every anonymous install of one network, per UTC day | `ANON_DAILY_USD_PER_NETWORK` | 5.00 | See "Install minting". |
| Estimated USD, linked user, per UTC day | `LINKED_DAILY_USD` | 3.00 | Every install linked to the same Supabase user, together. |
| Tokens (input, cache reads and writes included, plus output), linked user, per UTC day | `LINKED_DAILY_TOKENS` | 20000000 | Every install linked to the same user, together. A backstop under `LINKED_DAILY_USD` in case a `PRICES` entry is wrong: a heavy day of lessons is a few million tokens. Counted from settled usage, not reserved, so parallel calls can pass it by about `PER_TOKEN_INFLIGHT` calls; relinking an install moves its tokens with it (dollars stay put through `moved_usage`). |
| AI calls, anonymous install / linked user, per UTC day | `FREE_DAILY_REQUESTS` / `LINKED_DAILY_REQUESTS` | 0 (off) | Optional request counts on the same scopes. Off: a count stops a normal lesson (scene looks alone are up to 720 Haiku calls an hour) and says little about cost. Set only as an extra abuse brake, far above a lesson. |
| New lesson builds per UTC month | `FREE_LESSON_BUILDS_PER_MONTH` | 3 | Distinct videos claimed with `POST /v1/lessons/{id}/build`: per anonymous install, or per linked user across all their installs (so linking more Macs does not multiply it). Cache hits and rebuilding a claimed video are free. |
| New installs per UTC day, every network | `NEW_INSTALLS_PER_DAY` | 500 | See "Install minting". |
| Global spend brake, every install, per UTC day | `DAILY_USD_CAP` | off | An abuse brake only. See "Kill switches". |

`pro` (set with `/admin/tokens/{prefix}/plan`) skips the per-install and per-user caps; the global brake, when set,
still applies.

**Why $2.00 for an anonymous install.** About 3x one lesson (D13; Area C estimates ~$0.50), and above one build's
peak reservation: the lesson builder runs up to 4 Claude calls at once (`LESSON_CLAUDE_CONCURRENCY`), and each
holds its `max_tokens` at the output price while in flight, about $0.35 for a 32000-token Sonnet call, so four
hold about $1.40. Under the old $1.00 the third parallel call of a fresh install's first build was refused. Set the
final figure from a measured lesson (R01 step 1).

**How a lesson spends (why no request counts by default).** Counted from the
engine on `integration/live`: building a new lesson is roughly 20-35 calls (Gemini watches the video in parts,
`step_detail` per step, the Claude lesson and adapt passes, workspace setup, diagrams, the finder's searches)
and $0.20-0.50. Following it for 30-60 minutes adds 100-200 more: Haiku scene looks every ~5 s while the screen
changes (`server/orchestrator/scene_watch.py`, role coach), the judge (at most every 20 s, role coach), screen
target picks (up to 6 a minute, role screen) and coach cards. So one normal lesson is about 150-250 calls and
$0.30-0.60 by this count, and the scene watcher alone can send 720 calls in a busy hour. A cap of 100 calls,
300 calls or $0.25 stops a learner in the middle of their first lesson; dollars track what the calls cost.

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

A signed-in user's own daily caps (`LINKED_DAILY_USD`, `LINKED_DAILY_TOKENS`, `LINKED_DAILY_REQUESTS`) answer in the
same shape with their own `limit` and message, plus `unit` (`usd`, `tokens` or `requests`; `used` and `cap` are in it):

```json
{"type": "error", "error": {"type": "miyagi_quota", "status": "MIYAGI_QUOTA", "code": 429,
  "message": "You've used today's free help. It resets at midnight UTC.", "limit": "user_daily_cap",
  "unit": "usd", "used": 3.0, "cap": 3.0, "resets_at": "2026-11-22T00:00:00Z", "scope": "account"}}
```

The type stays `miyagi_quota` so the engine shows its limit card (a flat `{"error": "user_daily_cap"}` body would
not be recognised). These caps sit on top of the global brake: `DAILY_USD_CAP`, when set, is checked first.

`type` is `miyagi_quota` for the daily caps (the engine's `cloud_error()` reads it) and `miyagi_lesson_quota`
for the monthly build cap. `limit` is `daily_requests`, `daily_spend` (`scope: install | network`),
`user_daily_cap` (`scope: account`), `anon_daily_cap` (`scope: install`, `REQUIRE_SIGNIN=build` only), `daily_usd` (the global brake; `used` and `cap` are dollars there) or
`lesson_builds`. The old `coach_calls`
cap is gone. New installs over the daily cap get their own type, `miyagi_full` (see "Install minting").

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

- **Runtime pause, no redeploy:** `curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" $URL/admin/proxy/pause`. The flag
  is a row in SQLite (table `settings`), read by `Guard` on every `/v1` request, so the next request after the POST
  is refused, and it survives restarts and deploys. Every `/v1` route then answers 503 `proxy_disabled`
  ("Miyagi cloud AI is paused by the operators. Try again later."), which the engine shows as "miyagi is paused".
  `/healthz` (`paused: true`) and `/admin` keep working. `.../admin/proxy/resume` undoes it; `GET /admin/proxy`
  shows it. The routes use the usual admin auth (`X-Admin-Token`, constant-time compare, the admin rate limit and
  lockout); with a weak `ADMIN_TOKEN` they answer 503 like every admin route. Kept for abuse, not demand.
- `PROXY_ENABLED=false` (env, needs a deploy) does the same and wins over the runtime flag: resume cannot turn on
  a proxy the environment turned off.
- Disable one install: `curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" $URL/admin/tokens/<prefix>/disable`
  (take the prefix from `/admin/usage`). Its calls then get 403.
- `DAILY_USD_CAP` (dollars), the global spend brake: **an abuse brake, off by default** (unset, empty or 0). When
  set, once the estimated spend of every install together (in-flight reservations included) reaches it in the
  current UTC day, every forwarded AI call, pro installs included, gets the 429 `miyagi_quota` above with
  `limit: "daily_usd"` until UTC midnight, and the `brake` alert fires. Cache reads, build claims and events keep
  working. A fixed breaker trips on a good launch day and shuts everyone out (D13: at about $70 a day per 1,000
  monthly users, a $100 breaker shuts out a busy launch), so demand is handled by the daily new-install cap and the
  alerts, and the hard stop is the provider's prepaid balance with auto-reload off (R02). If you set it, set it
  far above `ALERT_DAILY_USD`. `/admin` shows today's estimate.

## Alerts

Set `ALERT_WEBHOOK_URL` to a Discord or Slack incoming-webhook URL (https; dashboard only, it is a secret and is
never logged). Discord URLs get `{"content": ...}`, every other host `{"text": ...}`. Unset (or not https): no
alerts, and nothing is written. Each alert fires at most once per UTC day: the first claim of its key in the
`alerts_sent` table wins, across restarts and processes, so a deploy never repeats one. Alerts are sent from a
background thread (one retry), and a failed send never affects a call. `POST /admin/alerts/test` sends a test
alert, to check the channel reaches both founders' phones.

| Key | Fires when | Env |
|---|---|---|
| `spend_50`, `spend_80`, `spend_100` | today's estimated spend, every install together, passes 50 / 80 / 100% of the daily alert line (checked after calls settle, at most every 10 s) | `ALERT_DAILY_USD` (25; 0 = off) |
| `token:<id>` | one install token's estimated spend today passes the line for one install (its 12-hex id, as in `/admin`) | `ALERT_TOKEN_DAILY_USD` (3x `FREE_DAILY_USD`, so 6.00; 0 = off) |
| `installs_full` | the daily new-install cap is reached | `NEW_INSTALLS_PER_DAY` |
| `mints_high` | new installs in one hour reach the warning line | `GLOBAL_MINTS_WARN_PER_HOUR` |
| `brake` | the global spend brake is reached (only when `DAILY_USD_CAP` is set) | `DAILY_USD_CAP` |

Setting up the webhook and Render's own alerts (deploy failures, health check, 5xx) step by step: `ALERTS.md`.

The alert line is a D13 decision; 25 keeps the old breaker's number as a warning instead of a stop. A daily
check from outside the service (R01 step 6: a cron that reads `/admin/usage` and pings a dead-man's switch) is
still to do, so a silent service is noticed too.

## Shared lesson cache (ROADMAP 3.1, A08)

Lesson builds are the expensive call, and many learners open the same videos. The flow:

1. `GET /v1/lessons/{video_id}?schema=N`. An approved lesson is used as the video draft and costs nothing.
2. On a miss, `POST /v1/lessons/{video_id}/build` uses one of the install's builds and **claims the video** for
   `LESSON_CLAIM_TTL_S` (600 s). While that claim is unexpired, another install's claim answers
   `200 {"held": true}` without counting a build: the engine (`server/lesson/cloud_cache.py`) then polls the GET for
   up to 12 s and builds locally if nothing arrives. The claimer's own repeat claim is `ok` again and does not extend
   its claim. A claim is released by the claimer's PUT of that video and schema (whatever its outcome), by any stored
   upload of it, by expiry (expired claims are ignored and pruned hourly) and by the claimer's account delete. The
   engine sends no `?schema=`, so its claim holds every schema of the video. Claims are kept per token hash only
   (table `lesson_claims`). A 429 here stops the build with a calm card; any other failure lets the engine build locally.
3. After a good build, `PUT /v1/lessons/{video_id}` with `{schema, lesson}`. The upload is a **pending
   candidate** for that video, schema and uploader. Nobody, the uploader included, is served it until an
   operator approves it: `GET /admin/lessons/pending`, read the whole candidate at its `full` path
   (`GET /admin/lessons/{video_id}/candidates/{hash}`: the pending list shows only libraries, commands and files,
   and the instructions are free text that could tell learners to paste anything), then
   `POST /admin/lessons/{video_id}/approve` with the candidate's `hash`. There is no first-writer-wins and no 409: a second uploader is never blocked by the first.
   `LESSON_AUTO_APPROVE_VALIDATED` (`1` in `render.yaml`) approves an upload at once when it passes the server-side
   lesson checks (below) and the video and schema neither serve a lesson yet nor were revoked; any problem leaves it
   pending, with the problems listed in the PUT answer (`problems`) and in `/admin/lessons/pending`.
   `LESSON_AUTO_APPROVE_N` (default 0 = off) approves automatically once N uploads with the identical normalized
   lesson (sorted keys) came from N different install tokens on N different networks (IPv4 /24, IPv6 /48).
4. Pull a served lesson with `POST /admin/lessons/{video_id}/revoke` (body `{}` for every schema, or
   `{"schema": N}`): it stops being served, its candidate becomes `revoked`, and the video and schema go into
   `lesson_revocations`, so no upload for them is auto-approved again, whoever sends it (an operator's approve still
   serves one). A bad uploader's lessons go with `DELETE /admin/lessons/by-uploader/{prefix}`; every candidate of one
   video with `DELETE /admin/lessons/{video_id}` (the revocation stays).

**Server-side lesson checks (`lesson_safety.py`).** A port of the engine's `validate_untrusted_lesson`
(`server/lesson/schema.py` on `integration/live`), where every repair the engine would make is a problem: path rules
(`rel_problem`: no NUL, backslash, drive, absolute, `~` or `..`; a step file or notebook never inside `.git/`,
`.vscode/`, `.venv/`, `venv/`, `node_modules/`, `.idea/`, `.github/`, `.devcontainer/`), the regex shape checks
(`lesson_patterns.py`, a vendored copy of the static half of `server/safety/patterns.py`: length, compiles, no
catastrophic or polynomial backtracking), at most 24 checks per list, 24 targets per step and 400 patterns per lesson,
https sources and no `lesson.workdir`. Commands and libraries are already held to a stricter allowlist by the upload
validation. Not ported (it needs the learner's Mac): the regex worker's run-time deadline, the on-disk
stays-inside-the-folder check and the home-folder workdir rules; the engine still applies them on load.

Rules:

- `video_id` is an 11-character YouTube id. `schema` must be in `LESSON_SCHEMAS` (default `1`). It is the engine's
  `LESSON_SCHEMA_VERSION` (`server/lesson/schema.py`, 1 today): **add every new engine `LESSON_SCHEMA_VERSION` to
  `LESSON_SCHEMAS` (code default and `render.yaml`) before that engine ships**, or its GETs and PUTs get 400
  `schema_unsupported` and every learner builds locally. Keep the old version listed while old engines are out.
- The cache key is video id + schema only. There is no fingerprint of the learner's folder (workdir) in it on purpose:
  the shared form carries no workdir, and the engine adapts a downloaded lesson to the learner's folder when it
  loads it (`cloud_cache.restore` and `validate_untrusted_lesson`).
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

## Activation funnel: `POST /v1/funnel`

The app (`app/src/main/features/funnel.ts`) sends the first time each milestone happened on that Mac, only while
"Share crash reports and usage" is on, the launch gate is open and the install is linked to a signed-in learner:

```
POST /v1/funnel
Authorization: Bearer <mi_ install token>
{"milestones": [{"name": "first_launch", "at": "2026-11-22T10:00:00Z"}, ...]}     at most 6 items, 2 KB
→ 202 {"ok": true}     401 bad token     413 too big     400 not that shape
```

Milestones, in order: `first_launch`, `signed_in`, `permissions_granted`, `lesson_started`, `step_passed`,
`lesson_finished`. The table `funnel` keeps the earliest time per install and name: names and times only, the user
comes from `links`. Unknown names and unreadable times are dropped; a future time counts as now, one older than 400
days is dropped. Deleted with the account (`delete_account`: the calling install and, signed in, every install linked
to that user). Retention: `prune()` counts a row whose `first_at` is older than 35 days into `funnel_daily` (UTC day,
name, installs; no install) and deletes it, like the other per-install rows. No IP, network hash, user id or token is
stored in either table, and the route logs none. Download is not a milestone (count it on the site or
release side; `tokens` is every first launch).

`GET /admin/funnel?days=N` (admin token): installs per step, share of the first step and the median seconds from the
step before, for installs whose first launch is within N days (0 = all). Postgres version of the table:
`migrations/20261122_funnel.sql` (not applied); dashboard queries: `sql/funnel.sql`.

## Admin view

`GET /admin/usage` with `X-Admin-Token` returns:

- `total`: requests, input and output tokens, estimated USD over the window
- `by_token`: the same per token-hash prefix (12 hex characters), with `disabled` and `user_id`
- `by_day`: the same per UTC day, with the number of active tokens
- `by_day_token_model`: per day, token, provider and model
- `lessons`: approved (`cached`) and `pending` lessons, cache hits, bytes, and new builds this month
- `usd_today`: estimated spend so far this UTC day, every install together, reservations included (what the
  spend alerts and `DAILY_USD_CAP` read)
- `new_installs_today`, `paused` (the runtime pause), `alerts_today` (the alert keys sent today)
- `events`: product events per UTC day and name, with how many installs sent them

`/admin` also shows how many account deletions are pending (see "Deleting an account").

USD is an estimate from the `PRICES` table in `app.py` (Anthropic list prices; the Gemini rows are placeholders
to check against Google's pricing). Override or add models with
`PRICES_JSON='{"model": [input_per_mtok, output_per_mtok]}'`.

Open `/admin` in a browser, paste the admin token into the form, and it shows the same tables.

## Environment variables

| Name | Default | Notes |
|---|---|---|
| `ADMIN_TOKEN` | none | 32+ characters, 12+ distinct. Render generates it (`generateValue: true`). Weak or missing: `/admin*` answers 503. |
| `ANTHROPIC_API_KEY` | none | Dashboard only (`sync: false`). Missing: Anthropic routes return 503. |
| `GEMINI_API_KEY` | none | Dashboard only (`sync: false`). Leave unset while Gemini is off (D1). With Gemini on and no key: Gemini routes return 503. |
| `PROXY_ENABLED` | `true` | `false` turns off every `/v1` route (needs a deploy; `POST /admin/proxy/pause` is the runtime switch). |
| `ALLOWED_ANTHROPIC_MODELS` | `claude-sonnet-5-5,claude-haiku-5-5` | Comma-separated. Opus is rejected regardless. |
| `ALLOWED_GEMINI_MODELS` | empty (Gemini off; `render.yaml`: `none`) | Comma-separated. Empty or `none`: every Gemini call gets 403 `gemini_disabled` (D1: Claude only). Set a list to bring Gemini back. |
| `MAX_TOKENS_CAP` | `32000` | Upper bound on Anthropic `max_tokens` and `thinking.budget_tokens`. The lesson builder asks for 32000; the dollar caps bound spend. |
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
| `RATE_LIMIT_PER_TOKEN_PER_HOUR` | `2400` | AI, lesson and event calls per known install token (above a lesson's busiest hour). |
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
| `FREE_DAILY_USD` | `2.00` | Anonymous install cap in estimated USD per UTC day. 0 = off. |
| `FREE_DAILY_REQUESTS` / `LINKED_DAILY_REQUESTS` | `0` / `0` (off) | Optional request counts per UTC day (install / user). |
| `ANON_DAILY_USD_PER_NETWORK` | `5.00` | Every anonymous install minted from one network together, per UTC day. 0 = off. |
| `LINKED_DAILY_USD` | `3.00` | Linked user cap in estimated USD per UTC day, all their installs. 0 = off. |
| `LINKED_DAILY_TOKENS` | `20000000` | Linked user cap in tokens (input + output) per UTC day, all their installs. 0 = off. |
| `REQUIRE_SIGNIN` | `0` (off) | `build`: build claims need an install linked to a Supabase user (401 `signin_required`), guests capped at `ANON_DAILY_USD`; `all` (or `1`): every money route does. See "Sign-in required". |
| `ANON_DAILY_USD` | `0.50` | A guest install's runtime calls in USD per UTC day, only with `REQUIRE_SIGNIN=build` (429 `anon_daily_cap`). |
| `LESSON_AUTO_APPROVE_VALIDATED` | `0` in code, `1` in `render.yaml` | Approve an uploaded lesson once it passes the server-side lesson checks (`lesson_safety.py`). See "Shared lesson cache". |
| `NEW_INSTALLS_PER_DAY` | `500` | New installs per UTC day, every network together; past it 429 `miyagi_full`. 0 = off. |
| `FREE_LESSON_BUILDS_PER_MONTH` | `3` | New lesson builds per free install per UTC month. 0 = off. |
| `DAILY_USD_CAP` | off (unset, empty or `0`) | Global spend brake in dollars, every install together: an abuse brake, never a low value. |
| `ALERT_WEBHOOK_URL` | empty (no alerts) | Discord or Slack incoming webhook, https. A secret: dashboard only. |
| `ALERT_DAILY_USD` | `25` | The daily alert line: alerts at 50, 80 and 100%. 0 = off. |
| `ALERT_TOKEN_DAILY_USD` | 3x `FREE_DAILY_USD` | One install's spend today past this alerts. 0 = off. |
| `RENDER_GIT_COMMIT` | set by Render | The deployed commit, shown on `/healthz` (a hex SHA only). Never set by hand. |
| `LINK_MAX_INSTALLS_PER_USER` | `10` | Installs one Supabase user may link. |
| `SUPABASE_URL` | `https://wssdpsdbaqtnfhoyimit.supabase.co` | JWKS URL and expected `iss` derive from it. |
| `SUPABASE_ALLOW_HS256` | empty (off) | `1` to accept legacy HS256 tokens (needs `SUPABASE_JWT_SECRET`). |
| `SUPABASE_JWT_SECRET` | empty | Only with `SUPABASE_ALLOW_HS256=1`. Dashboard only. |
| `SUPABASE_SERVICE_ROLE_KEY` | empty | The Supabase secret (service_role) key: `/v1/account/delete` deletes the auth user with it. Dashboard only (`sync: false`); trimmed like the upstream keys. Unset: deletions are `"pending"`. |
| `NET_HASH_KEY` | derived from `ADMIN_TOKEN` | The key network hashes use. Optional; changing it (or `ADMIN_TOKEN` without it) regroups networks once. |
| `RETAIN_DAYS` | `35` | Per-install rows older than this are folded into per-day totals or deleted. Never below 35. |
| `PRUNE_EVERY_S` | `3600` | How often the prune runs (also at startup). |
| `MINT_NET_RETAIN_DAYS` | `0` (keep while anonymous) | Drop an anonymous install's mint network hash this many days after minting; that install is then capped per install only. |
| `EVENTS_PER_DAY_PER_INSTALL` | `2000` | Events kept per install per UTC day. 0 = no cap. |
| `EVENT_NAMES` | the app's 11 names | Comma-separated event names `/v1/events` counts. |
| `EVENT_PROP_KEYS` | `kind,mode,reason,source,built_by,step_kind,level,cached,provider,model,usd,steps,minutes,seconds` | Prop keys kept (as counts or sums). |
| `MAX_LESSON_KB` | `128` | Largest shared lesson, measured as stored (UTF-8). |
| `LESSON_SCHEMAS` | `1` | Comma-separated lesson schema versions the cache accepts. |
| `LESSON_PUTS_PER_DAY` | `10` | Lesson uploads per install per UTC day. |
| `LESSON_CLAIM_TTL_S` | `600` | How long a build claim holds its video (others get `{"held": true}`). 0 = no claims. |
| `LESSON_AUTO_APPROVE_N` | `0` (off) | Auto-approve after N identical uploads from N tokens on N networks. |
| `LESSON_DISK_MAX_PCT` | `85` | Lesson uploads stop above this disk usage. |
| `LESSON_PENDING_MAX_DAYS` | `14` | Pending (unreviewed) uploads older than this are dropped. |
| `LESSON_PENDING_MAX_MB` / `LESSON_PENDING_PER_NET_MB` | `128` / `8` | Pending upload bytes in total / per uploader network (IPv4 /24, IPv6 /48); past either, 507. |
| `DB_PATH` | `/var/data/miyagi.db` if `/var/data` exists, else `./miyagi.db` | SQLite file. |
| `UPSTREAM_READ_TIMEOUT_S` | `300` | httpx read timeout (a Gemini video watch can take minutes). |
| `UPSTREAM_KEEPALIVE_S` | `90` | How long an idle upstream connection stays open for reuse (httpx's own default is 5 s). |
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
| `GEMINI_API_KEY` | leave unset (Gemini is off, D1) | R02 step 3: with Claude only, unset the key instead of capping it. Set it again only with `ALLOWED_GEMINI_MODELS`. |
| `DAILY_USD_CAP` | leave unset (the brake is off), or a figure far above the alert line | `sync: false`. Delete any old low value (a value of 25 left from before would stop everyone on a busy day). |
| `ALERT_WEBHOOK_URL` | a Discord or Slack incoming-webhook URL | `sync: false`. Unset: no alerts. |
| `SUPABASE_JWT_SECRET` | only if `SUPABASE_ALLOW_HS256=1` | Not needed: access tokens are verified against the JWKS. |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase project `wssdpsdbaqtnfhoyimit` › Settings › API keys › the secret (service_role) key | `POST /v1/account/delete` deletes the Supabase auth user with it. Without it every signed-in deletion is `"pending"` (see `/admin/deletions`). |

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
`event_counts`, `event_props_rows`, `link_user`, `link_user_capped`, `get_link`, `usage_report`, `get_setting`,
`set_setting`, `paused`, `set_paused`, `ping`, `new_installs_on`, `claim_alert`, `alerts_on`; `admit_call`,
`settle`, `mint_check`, `put_candidate`, `link_user_capped` and `add_events` need one transaction with a row lock,
and `claim_alert` an insert that only one caller wins) and return it
from `open_store()` when `DATABASE_URL` is set. The tables port as they are. The lesson cache tables are already
written out as Postgres DDL in `migrations/supabase/0001_lesson_cache.sql` (own schema, RLS on, no policies, service
role only). It is a file only: nothing applies it.

## How the app and the engine use it

1. On first launch the app (`app/src/main/features/cloud.ts`) calls `POST <host>/v1/install` and keeps the
   returned `mi_` token in the Keychain (safeStorage). The host defaults to `https://miyagi-cloud.onrender.com`;
   `MIYAGI_CLOUD_URL` overrides it, `off` turns it off.
2. The app sends the engine `config.keys {miyagiToken: <token>, miyagiCloud: "<host>/v1"}`. The engine
   (`server/config.py` `anthropic_kwargs()` / `gemini_kwargs()`) points its Anthropic and google-genai clients at
   `<host>/v1/anthropic` and `<host>/v1/gemini` (api_version v1beta) with the token as the key, and tags each call
   with `x-miyagi-role`.
3. A 401 `authentication_error` means the token is unknown: the app mints a new one. A 401 `signin_required` (only
   with `REQUIRE_SIGNIN` `build` or `all`) means the install must be linked to an account first: show sign-in, never mint. A 403 `permission_error` means the install was
   disabled. A 503 `proxy_disabled` means the operators paused the proxy. A 429 `miyagi_quota` (or a proxy-shaped
   `rate_limit_error`) shows the "today's limit" card. A 429 `miyagi_full` from `/v1/install` means today's
   new-install cap is reached: show its message ("miyagi is full today, try tomorrow.") and try again after
   `resets_at`. A 403 `gemini_disabled` means Gemini is off on the proxy: use Claude.

**Models to allowlist, if Gemini comes back.** Gemini is off by default (D1). The engine's Gemini defaults are `gemini-4-hydrogen` (video watch, `LESSON_MODEL`),
`gemini-3.8-flash` (`LESSON_FAST_MODEL`) and the fallbacks `gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash`.
With `ALLOWED_GEMINI_MODELS=gemini-3.8-flash` only that model passes; a model that is not allowed gets a 404 and
the engine skips to its next fallback, so the video watch needs at least one of its chain allowlisted (R03 step 4:
`gemini-4-hydrogen`, with 3.8-flash and 3.6-flash as fallbacks; 3.5 and 3.7 flash are retired).
