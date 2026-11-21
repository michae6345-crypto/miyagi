# eng-cost (E-cost: dollars per lesson, cheap models, prompt caching)

**Status:** rescued and finished, pushed, not merged · **Branch:** `claude/eng-cost` (from `origin/integration/live`) · **Engine only** (no app files, no port)

## Goal
ROADMAP 3.3, 3.4 and 3.8: a hard dollar number per built lesson and per lesson session, no Opus by default anywhere, and prompt caching on lesson building and screen calls, with the cache hit rate in the logs.

## What changed (server/)
- `lesson/cost.py`
  - Price table `PRICES` (USD per 1M tokens: input, output, cache read). Anthropic rows match the published rates (Opus 5.5 4/20/0.20, Sonnet 5.5 2/10/0.10, Sonnet 5 2/10/0.20, Haiku 5.5 0.10/0.50/0.01). Gemini rows match the cloud's placeholder table (`cloud/app.py`). A dated id falls back to its base row, then to a family row (opus, fable, mythos, sonnet, haiku, flash-lite, flash, gemini), then `DEFAULT_PRICE`. Cache writes bill at 1.25x input. `MIYAGI_PRICES_JSON='{"model": [in, out, cache_read]}'` overrides or adds rows; a bad value is ignored with a warning.
  - `add_tokens` / `record_usage` keep tokens, cache reads and writes, and dollars per model in the build counter (`build.cost` in a graph now has `cost_usd`, per-model `usd` and `cache_hit_rate`) and in one process-wide session tally (`by_source`: lesson, coach, screen).
  - `finish_build` logs a build's dollars and emits `build_cost`. `session_start(lesson_id)` / `session_end(reason)` name, log and emit `session_cost`, then start a fresh tally.
  - Event hook: `register_event_handler(fn)` / `emit_event(name, props)`. A no-op until the telemetry lane registers a handler (PostHog). A handler that raises is logged and never breaks a model call.
- `lesson/claude.py`: the system prompt is one cached block; prompt-described JSON moves the schema (sorted keys) into that cached block so per-step calls share a prefix. Usage, cache fields and dollars recorded through `cost.record_usage`.
- `lesson/gemini.py`: `record_usage` splits Gemini's implicit cache hits out of the prompt count. **`DEFAULT_MODEL` is unchanged** (`gemini-4-hydrogen`), see Questions.
- `lesson/textlesson.py`, `lesson/builder.py`: research calls recorded the same way; text and video builds call `finish_build`.
- `screen/describe.py`: system prompt as a cached block; each call's dollars recorded (`source="screen"`).
- `coach/llm.py`: each coach call's dollars recorded (`source="coach"`). Model choice is unchanged (Haiku by default, Sonnet for diagnose, Opus only with an explicit override plus `MIYAGI_ALLOW_OPUS=1` and no cloud).
- `orchestrator/session.py`: loading a lesson calls `session_start`; ending one calls `session_end(reason)`. Both are wrapped so they can never block a lesson.

## Checks run (offline, `env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY`)
- `py_compile` on every changed .py file: OK.
- `pytest server/lesson/tests server/coach/tests server/screen server/orchestrator`: 910 passed, 5 failed, all pre-existing (`test_session.py` ws tests x4, `test_t10_layout`).
- `pytest server` (whole engine): 1348 passed, 1 skipped, 11 failed, all on the known pre-existing list (test_tiger x2, test_session ws x4, test_t10_layout, test_t8_replay x3, test_vscode_ext::test_engine_route_records_events). `test_coach::test_models_by_purpose` was on that list and now passes.
- New `server/lesson/tests/test_cost.py` (16 tests, fake clients only, no API reached).

## Questions for Michael
1. **Gemini video model.** The stalled lane changed `server/lesson/gemini.py` `DEFAULT_MODEL` from `gemini-4-hydrogen` to `gemini-3.8-flash` (ROADMAP 3.3 says "Change DEFAULT_MODEL to Flash"; hydrogen is about 4x the price, and the miyagi cloud only allows `gemini-3.8-flash`, so a cloud user already gets a refused or fallback call on hydrogen). Dropped here on purpose. Switch it?

## Open issues
- `coach/triage.py` still names a route `"opus"` (ROADMAP 3.3 asks to rename it). It only routes to the diagnose card, which runs on Sonnet; the rename touches about 36 references across coach and tests, so it is left for a follow-up.
- `cloud/app.py` `estimate_usd` prices cache reads at 0.1x input for every model, so its Sonnet 5.5 rows read 0.20 where the published rate is 0.10, and it has no Opus row. The engine table is right; the cloud should take the cache-read column (not in this lane).
- PostHog sending of `build_cost` / `session_cost` is the telemetry lane's job: it only needs `cost.register_event_handler`.
- Per completed lesson (ROADMAP 3.8): `session_cost` carries `reason`, so "completed" sessions can be filtered once events reach PostHog.

## Core requests
_None._ No app files touched.
