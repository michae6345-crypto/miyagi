# eng-cost (E-cost: dollars per lesson, cheap models, prompt caching)

**Status:** rescued, review round 1 fixed, pushed, not merged · **Branch:** `claude/eng-cost` (from `origin/integration/live`, live merged in again for round 1) · **Engine only** (no app files, no port)

## Goal
ROADMAP 3.3, 3.4 and 3.8: a hard dollar number per built lesson and per lesson session, no Opus by default anywhere, and prompt caching on lesson building and screen calls, with the cache hit rate in the logs.

## What changed (server/)
- `lesson/cost.py`
  - Price table `PRICES` (USD per 1M tokens: input, output, cache read). Anthropic rows match the published rates (Opus 5.5 4/20/0.20, Sonnet 5.5 2/10/0.10, Sonnet 5 2/10/0.20, Haiku 5.5 0.10/0.50/0.01). Gemini rows match the cloud's placeholder table (`cloud/app.py`). A dated id falls back to its base row, then to a family row (opus, fable, mythos, sonnet, haiku, flash-lite, flash, gemini), then `DEFAULT_PRICE`. Cache writes bill at 1.25x input. Anthropic web searches add `WEB_SEARCH_USD` ($0.01 each, from `usage.server_tool_use.web_search_requests`). `MIYAGI_PRICES_JSON='{"model": [in, out, cache_read]}'` overrides or adds rows (model ids are case-insensitive; parsed once per value); a bad value is ignored with a warning.
  - `add_tokens` / `record_usage` / `record_gemini` keep tokens, cache reads and writes, and dollars per model in the build counter (`build.cost` in a graph has `cost_usd`, per-model `usd` and `cache_hit_rate`) and in one process-wide session tally with `by_source`. `record_usage` never raises.
  - Sources: `lesson` (the learner's build), `prebuild` (speculative builds, `cost.start("prebuild")`), `coach` (coach calls, the scene look every ~5 s, the cache warm-up), `screen` (describe, target picks), `diagrams`, `workspace` (starter files, requirements), `finder`, `preflight`. A build's calls take the build counter's source unless the caller names one.
  - `build_scope(counter, kind=...)` wraps every build (video, prebuild, text) and emits `build_cost` once however it ends, with `outcome` ok / failed / cancelled (a prebuild that `prebuild.cancel()` stops is "cancelled"). A failed or cancelled build's dollars stay in the session total (they were paid) but move to `by_source["<source>_<outcome>"]`, so the next lesson's own build can be told apart.
  - `session_start(lesson_id)` / `session_end(reason)` name, log and emit `session_cost`, then start a fresh tally.
  - Event hook: `register_event_handler(fn)` / `emit_event(name, props)`. A no-op until the telemetry lane registers a handler (PostHog). A handler that raises is logged and never breaks a model call.
- `lesson/claude.py`: the system prompt is one cached block; prompt-described JSON moves the schema (sorted keys) into that cached block so per-step calls share a prefix. Usage, cache fields and dollars recorded through `cost.record_usage`.
- `lesson/gemini.py`: `record_usage` (via `cost.record_gemini`) splits Gemini's implicit cache hits out of the prompt count. **`DEFAULT_MODEL` is unchanged** (`gemini-4-hydrogen`), see Questions.
- `lesson/builder.py`, `lesson/textlesson.py`, `lesson/prebuild.py`: every build runs in `cost.build_scope`; text builds always start a fresh counter; prebuild counters carry source `prebuild`.
- `screen/describe.py`: system prompt as a cached block; each call's dollars recorded (`source="screen"`).
- `screen/target.py`, `coach/scene.py`: their own `PRICE_IN` / `PRICE_OUT` copies are gone; dollars come from `cost.usd` through `cost.record_usage` (target: `screen`, scene: `coach`). A refused or unusable look is counted too.
- `coach/llm.py`: `structured_call` records a call's dollars right after it returns, before the refusal, max_tokens, no-text and bad-JSON checks (all billed). The cache warm-up calls are recorded (they pay cache writes). New `llm.record_cost` / `llm.usd` helpers. Model choice is unchanged (Haiku by default, Sonnet for diagnose, Opus only with an explicit override plus `MIYAGI_ALLOW_OPUS=1` and no cloud).
- `diagrams/build.py` (Sonnet), `workspace/scaffold.py`, `workspace/setup.py`, `finder/claude.py`, `finder/gemini.py`, `preflight/core.py`: each call recorded with its source, before any refusal check.
- `orchestrator/session.py`: loading a lesson calls `session_start`; ending one calls `session_end(reason)`. Both are wrapped so they can never block a lesson.

## Checks run (offline, `env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY`)
- `py_compile` on every changed .py file: OK.
- `server/lesson/tests/test_cost.py`: 24 passed (16 from the rescue plus 8 for review round 1: case-insensitive overrides, failed / cancelled / no-call builds, one build_cost per video build with its lesson id, prebuild source, refused and max_tokens coach calls counted, scene on the shared table, diagrams and finder counted, web search fees). Fake clients only, no API reached.
- `pytest server/screen server/coach server/lesson server/diagrams server/finder server/preflight server/workspace server/orchestrator`: 1168 passed, 5 skipped, 5 failed, all known pre-existing (`test_session.py` ws x4, `test_vscode_ext::test_engine_route_records_events`).
- `pytest server` (whole engine): 1380 passed, 1 skipped, 12 failed. Ten are on the known pre-existing list (test_tiger x2, test_session ws x4, test_t8_replay x3, test_vscode_ext x1). The other two, `screen/tests/test_errors.py::test_no_permission_raises_and_never_uses_fixture` and `screen/tests/test_fixtures.py::test_live_capture_is_primary_full_frame_points`, touch the live screen capture; the log showed "display asleep" and "primary display not in SCShareableContent" during that run, and both pass on a re-run (alone and with the whole screen suite). No file they cover was changed.

## Questions for Michael
1. **Gemini video model.** The stalled lane changed `server/lesson/gemini.py` `DEFAULT_MODEL` from `gemini-4-hydrogen` to `gemini-3.8-flash` (ROADMAP 3.3 says "Change DEFAULT_MODEL to Flash"; hydrogen is about 4x the price, and the miyagi cloud only allows `gemini-3.8-flash`, so a cloud user already gets a refused or fallback call on hydrogen). Dropped here on purpose. Switch it?
2. **Opus constants.** ROADMAP 3.3 says "Remove OPUS from server/coach/llm.py and lesson/claude.py". This branch keeps `llm.OPUS` and `claude.OPUS_MODEL`, reachable only with an explicit override plus `MIYAGI_ALLOW_OPUS=1` / `LESSON_ALLOW_OPUS=1` and never through the cloud. So no Opus by default anywhere, but not removed. Remove them outright (and the opt-ins), together with the triage `"opus"` route rename below?

## Open issues
- `coach/triage.py` still names a route `"opus"` (ROADMAP 3.3 asks to rename it). It only routes to the diagnose card, which runs on Sonnet; the rename touches about 36 references across coach and tests, so it is left for a follow-up (see Question 2).
- Haiku 5.5 long context: Anthropic bills Haiku 5.5 at $0.50 / $2.50 per 1M above 100K prompt tokens; the table charges the flat $0.10 / $0.50. No miyagi call is near 100K today (scene ~2.5K, coach a few K), so a call that crosses it would read low.
- Calls the tally cannot see: hedged Gemini finder requests that lose the race are cancelled before they return usage (only the winner is counted); a call that errors out (timeout, 5xx) returns no usage. Both may still be billed.
- Not token-billed and not in the tally: ElevenLabs voice (`coach/voice.py`, voice is off for now), the YouTube Data API.
- A build that fails before any lesson loads never reaches `session_end` (only a loaded lesson ends a session), so its dollars ride into the next lesson's `session_cost`, tagged `lesson_failed` / `prebuild_cancelled` in `by_source`. `session_cost.cost_usd` is the session's full spend including those; subtract the `_failed` / `_cancelled` / `prebuild` sources for "this lesson only".
- `cloud/app.py` `estimate_usd` prices cache reads at 0.1x input for every model, so its Sonnet 5.5 rows read 0.20 where the published rate is 0.10, and it has no Opus row. The engine table is right; the cloud should take the cache-read column (not in this lane).
- PostHog sending of `build_cost` / `session_cost` is the telemetry lane's job: it only needs `cost.register_event_handler`.
- Per completed lesson (ROADMAP 3.8): `session_cost` carries `reason`, so "completed" sessions can be filtered once events reach PostHog.

## Core requests
_None._ No app files touched.
