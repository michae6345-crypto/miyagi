# telemetry

**Status:** adopted and finished (crash reports + lesson counts, off by default). Matches the miyagi-cloud `POST /v1/events` contract. Unit and reporter tests pass offline; not run in Electron and never sent to the real cloud (offline lane). · **Priority:** P2 · **Branch:** `claude/telemetry`

## Goal
ROADMAP 1.6 (crash reporting) and 1.7 (usage analytics) without a vendor SDK. One switch in Settings › Privacy, **"Share crash reports and usage", off by default for everyone**. Nothing leaves the Mac before the learner turns it on, and nothing before the launch gate opens (signed in or guest, setup done or put off).

## Wire contract (miyagi-cloud, added by the cloud lane)
```
POST <cloud host>/v1/events
Authorization: Bearer <mi_ install token>
Content-Type: application/json
{"events": [{"name": str, "at": iso, "props": {str: str | number | bool}}]}    at most 50 events, at most 32 KB
202 {"ok": true}
```
- The host is the one that minted the install token (`cloud.ts installToken().host`), so the token only goes back where it came from. No token (cloud off, not minted yet, healing): events wait in memory (capped at 200), nothing is sent.
- 2xx sent. **404 / 410 (an older cloud without the route): dropped silently, nothing more is queued or sent this run.** 400 / 413 / 422: that batch is dropped. 401, 403, 429, 5xx, offline: kept, retried with backoff (30 s doubling, 30 min cap).
- Only `{"events": [...]}` is sent: no extra top-level fields. Redirects are refused. Response bodies are never read or logged.

## What is sent
| Event | When | Props |
|---|---|---|
| `app_installed` | once per Mac, the first time sharing is on | `app_version`, `os`, `arch` |
| `onboarding_done` | once, setup finished | none |
| `lesson_built` | `lesson.ready` for a new lesson (not a replay, not the same id again) | `steps`, `built_by`, `mode` (contract enums only) |
| `step_passed` | `step.passed`, once per step, never a skip | `already` |
| `step_failed_check` | the step judge's "Not yet" card (`source: judge`, `verdict: not_done`) | none |
| `hint_used` | a `hint` card | none |
| `lesson_completed` | the `complete` card | `passed`, `skipped`, `total`, `minutes` |
| `lesson_abandoned` | `lesson.ended` before `complete` | `reason` (a snake_case word, else `other`) |
| `crash` | each new line of `userData/errors/errors.json` | `kind`, `message` (scrubbed), `app_version` |

Lesson counts are read in main from the engine events it already receives (`EngineLink.onEvent`): the engine does not need to send anything.

**Never sent:** screen text, code, file paths, file names of the learner's files, URLs, emails, keys or tokens, lesson titles, step text, card bodies, lesson ids. `scrubCrash` runs `errors/scrub.ts` (keys, `mi_` tokens, emails, home folders), drops anything quoted, replaces URLs with `[url]` and every path with `[path]`; only miyagi's own bundled script keeps its file name (`app:index.js:12:5`, recognised by `app.asar` or `out/main|preload|renderer`). Other string props must be short enum-like words; a key-shaped word is dropped.

## Crash feed
- Off: the queue is dropped and the crash mark moves to the end of the log, so turning sharing on later never sends older crashes.
- The first time ever on, or turned on during a run: the feed starts from that tick (lines logged before stay on this Mac).
- Renderer uncaught errors and unhandled rejections now reach the log too (`errors/report.ts` → `errors:renderer`, at most 20 per launch, scrubbed in the renderer and again before sending).

## Owns
- `app/src/main/features/telemetry.ts`: `createReporter(deps)` (testable, injected fetch / token / switch / gate) and the feature that wires it (tick 5 s after launch, then every 15 s; `engine.onEvent` for lesson counts).
- `app/src/main/features/telemetry/core.ts`: pure: endpoint, `scrubCrash`, `cleanProps`, `usageEvent`, `resultFor`, the `Batcher` (50 events / 32 KB per request).
- `app/test/telemetryCore.test.ts`, `app/test/telemetry.test.ts`.
- `app/src/renderer/src/features/errors/report.ts` and the `errors:renderer` handle in `app/src/main/features/errors.ts` (errors lane files, a small addition).
- The "Help improve miyagi" group in `settings/sections/Privacy.tsx`.

## Switches
- `prefs.shareTelemetry` (default `false`), read live from `prefs.json` every tick. Delete my data resets it to off.
- `MIYAGI_TELEMETRY=off` (or `0`, `false`, `no`): off for a run, whatever the switch says.
- State: `userData/telemetry/state.json` `{installed, onboarding, crashMark}` (0600); flags are saved only once sent.

## Checks
```bash
cd app && npm run typecheck
node --import tsx --import ./test/setup.mjs --test --test-force-exit test/telemetryCore.test.ts test/telemetry.test.ts
```

## Core requests
1. **`common/prefs.ts`** (done, minimal): `shareTelemetry: boolean`, default `false`, sanitized. Already on this branch.
2. **Withdrawn:** the earlier `EngineLink.setTelemetry` in `engine.ts` (folding `telemetry: "on"` into `config.keys`) is removed. No engine reads it, and re-sending `config.keys` on every toggle was a side effect with no consumer. The app now counts lesson milestones itself. If the engine ever sends its own events (cost, search), it needs this back, plus a contract field.
3. `cloud.ts`: none. The lane uses integration's `installToken(): InstallInfo` as is.

## Notes and open questions
- Not run in Electron and nothing sent to the real cloud. Needs one Mac check with the cloud lane's `/v1/events` deployed: turn sharing on, wait 15 s, see `202`.
- `prefs.crashReports` ('ask' / 'always' / 'never', the local crash-report card) and the hidden `usageCounts` are separate older prefs. `shareTelemetry` does not read them. Michael may want one switch.
- The privacy page on the web (if any) should list these events.
