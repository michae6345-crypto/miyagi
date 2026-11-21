# eng-cloud-client (E-cloud: cloud client + cost guards)

**Status:** done, pushed, not merged · **Branch:** `claude/eng-cloud-client` (from `origin/integration/live`) · **Engine only** (no app files, no port)

## Goal
Every Claude and Gemini call can go through the miyagi cloud proxy (`claude/eng-proxy`, `cloud/`) with the app's anonymous install token, so a downloaded miyagi needs no API keys and all spend is ours to see and stop. A key the learner types in Settings (bring-your-own-key) still works and always goes straight to its provider. Plus BUILD-PLAN E4: Opus is opt-in only, and the refusal fallback never lands on an Opus nobody opted into.

## What changed (server/)
- `config.py`
  - `KEY_ENV["miyagiToken"] = "MIYAGI_CLOUD_TOKEN"`; cloud URL from `config.keys.miyagiCloud`, else env `MIYAGI_CLOUD_URL` (https only; plain http only for localhost).
  - `mode(provider)`: `byok | cloud | env | missing` (Settings key > cloud > .env). `get_key()` returns the cloud token for anthropic/gemini in cloud mode. `key_source()` gains `"cloud"`. `cloud_status()`: `ok | missing | off`.
  - `anthropic_kwargs(role, key=None)`: `{api_key, base_url}`. Cloud token: `base_url = <cloud>/anthropic` plus `x-miyagi-role`. Any other key: `base_url = https://api.anthropic.com` set explicitly, so a direct key can never follow `ANTHROPIC_BASE_URL` to the proxy.
  - `gemini_kwargs(role, key=None)` / `gemini_http_options()`: `HttpOptions(base_url=<cloud>/gemini)` for the token. `gemini_text_ok()`: false through the cloud (video only).
  - `cloud_error(exc)` -> `miyagi_paused | miyagi_quota | miyagi_auth`, card copy in `CLOUD_ERRORS`.
  - Cost guards: `guard_model()` (Opus / Fable / Mythos become Sonnet unless `MIYAGI_ALLOW_OPUS=1`, and never through the cloud), `fallback_kwargs()` (Sonnet 5.5 keeps `fallbacks: "default"`, whose only documented target is Claude Sonnet 5; an opted-in Opus keeps "default"; anything else gets none).
  - `safe_env(base=None, **extra)`: environment copy without provider keys, the cloud token/URL, `ANTHROPIC_*`, `GEMINI_*`, `GOOGLE_API*`, `BRIGHTDATA_*`, `ELEVENLABS_*`, `TIGER_*`.
- `orchestrator/main.py` `apply_keys`: cloud mode puts the token in `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` and sets `ANTHROPIC_BASE_URL=<cloud>/anthropic` (net for a missed constructor); otherwise removes it. `config.status` gains `miyagiToken` and `cloud`.
- Client sites now built from `anthropic_kwargs()`: `coach/llm.py` (covers coach/scene), `lesson/claude.py`, `screen/describe.py`, `screen/target.py`, `finder/claude.py`, `diagrams/build.py`, `workspace/scaffold.py`. Re-grepped `Anthropic(`: no other constructor in server/.
- Gemini: `lesson/gemini.py` client from `gemini_kwargs()`; `adapt_checks` hands the text-only pass to Claude Haiku in cloud mode. `finder/env.py` drops the cloud token as the finder's Gemini key, so the finder scores with Claude (`FINDER_GEMINI_FALLBACK` already defaults to 0).
- Errors: proxy 503 `miyagi_paused`, 429 `miyagi_quota`, 401 (cloud mode) map to plain text in `coach/llm.py` (`CoachLLMError` kind `"cloud"`), `screen/describe.py` (`DescribeError` reason = the code), `lesson/claude.py` (no rate-limit retries on a quota stop), `diagrams/build.py`.
- E4: `screen/describe.py` `COACH_MODEL` default is now `claude-sonnet-5-5` (was Opus). Guard applied in `coach/llm.py` (`model_for`, `structured_call`, `warm`), `coach/selection.py`, `diagrams/build.py`, `workspace/scaffold.py`, `lesson/claude.py` (keeps `LESSON_ALLOW_OPUS=1` as its opt-in). `coach/llm.warm()` skips `models.retrieve` through the cloud (the proxy forwards `/v1/messages` only).
- `tests/test_cloud_config.py`: offline tests (base URL plus token in cloud mode, direct key in BYOK mode, guard, fallback, safe_env, cloud errors). Not run with pytest (rule); its functions were exercised by hand, all 9 pass.

## Checks run
- `python -m py_compile` on every changed file: OK.
- `python -I` import of all 12 changed modules with every key env var empty: OK.
- Offline routing script (clients built, never called): cloud mode routes every site to `<cloud>/anthropic` with the token, Gemini to `<cloud>/gemini`, finder Gemini off, `LESSON_ALLOW_OPUS=1` still Sonnet through the cloud; a Settings key goes to `https://api.anthropic.com` and `ANTHROPIC_BASE_URL` is cleared.
- No paid calls, no pytest, running engine on :8787 untouched.

## For Michael
- **Gemini video model (not changed, as asked):** `lesson/gemini.py` `DEFAULT_MODEL = "gemini-4-hydrogen"` (video pass), `DEFAULT_FAST_MODEL = "gemini-3.8-flash"` (per-step detail), fallbacks `gemini-3.7-flash, gemini-3.6-flash, gemini-3.5-flash`. The proxy's `ALLOWED_GEMINI_MODELS` must list whichever you pick; with the Flash-only default allowlist, the hydrogen video pass is refused and the build falls back to the next model / Claude.
- New opt-in: `MIYAGI_ALLOW_OPUS=1` (coach, screen, diagrams, workspace). `COACH_MODEL_DIAGNOSE=claude-opus-5-5` alone now runs on Sonnet.

## Core requests
1. **`shared/contracts/events.ts` (Adrian, `contract:` commit + email):** `config.keys` gains `miyagiToken?: string; miyagiCloud?: string`; `KeyState` gains `"cloud"`; `KeyStatusEvent["config.status"]` gains `miyagiToken: KeyState; cloud: "ok" | "missing" | "off"`. The Python model (`ConfigKeys`, `extra="allow"`) already passes the new fields through, so the engine works before this lands.
2. **`orchestrator/session.py` `_ask_failed_card` (E3 lane):** when the error text contains `miyagi_paused` / `miyagi_quota` / `miyagi_auth`, use `server.config.CLOUD_ERRORS[code]` as the body (title "miyagi is paused" / "Today's limit reached" / "Couldn't verify this Mac") and keep Try again only for `miyagi_paused`. Today these fall to "Claude couldn't answer".
3. **`safe_env()` call sites (E2 / E3 lanes):** `orchestrator/session.py:7118` ("Run it for me": `env = dict(os.environ)`), `workspace/setup.py:593`, `workspace/core.py:328`, `workspace/editor.py` (VS Code launch: its terminals inherit the engine env, keys included). Replace the env with `server_config.safe_env(...)`.
4. **`coach/tests/test_coach.py:1147-1150` (`test_models_by_purpose`):** an Opus override now needs `MIYAGI_ALLOW_OPUS=1`; set it in the test (or assert Sonnet without it).
5. **App (`michael/app-cloud-token`):** send `miyagiToken` and `miyagiCloud` in `config.keys` on every connect; show `config.status.cloud`.
6. **Proxy (`claude/eng-proxy`):** forward `x-miyagi-role` into the usage log; accept `fallbacks: "default"` with `server-side-fallback-2026-07-01` (Sonnet 5.5 falls back to `claude-sonnet-5`, which the price table needs); answer refusals with body `{"type": "miyagi_paused" | "miyagi_quota"}` (top level or under `error.type`, both are read).

## Notes
- `ANTHROPIC_AUTH_TOKEN` or an `ant auth` profile on a dev Mac is not sent through the proxy: every client passes `api_key` explicitly, which the SDK prefers.
- `finder/core.py` (in E4's list) needed no change: `FINDER_GEMINI_FALLBACK` already defaults to 0, and in cloud mode the finder gets no Gemini key at all.
