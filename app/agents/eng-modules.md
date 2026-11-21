# eng-modules (E1)

**Status:** done, pushed, not wired (E2 wires it) · **Branch:** `claude/eng-modules` (from `origin/integration/live`) · **Lane:** engine

## Goal
Four new engine modules that hold the data behind the v2 screens: setup health (onboarding checklist, Settings > Permissions), the lesson library (Home-Library, Home-LessonDetail), progress (Prog-Progress-Window), and a change-only system status poller (offline / back online, AI busy, health changes). Pure functions plus one small poller. No model calls, no paid APIs, no prompts.

## Owns (new files only)
- `server/orchestrator/health.py`
- `server/lesson/library.py`
- `server/sessions/progress.py`
- `server/orchestrator/system_status.py`
- `app/agents/eng-modules.md` (this brief)

## Contract (payload shapes these modules produce; W0-1 should match them)
- **`health`** (`GET /health`, reply to `health.get`, change-only from the poller): `{items: HealthItem[], ready: number, total: number}`
  - `HealthItem {id: "screen" | "accessibility" | "companion" | "engine" | "keys"; state: "ok" | "missing" | "unknown"; required: boolean; fix?: "permission.open" | "install_companion" | "get_vscode" | "keys"; kind?: "screen" | "accessibility"; running?: boolean; version?: string}`
  - `ready` / `total` count required rows only (screen, accessibility, companion, engine: "2 of 4 ready"). `keys` is informational (`required: false`).
  - `unknown` = the probe couldn't tell; the app draws it gray, never as missing.
- **`library`** (`GET /library`, reply to `library.list`): `{items: LibraryItem[], continue: ContinueItem[]}`
  - `LibraryItem {id; lessonId; title; mode: "video" | "lesson"; steps: number; tools: ("vscode" | "jupyter" | "terminal")[]; source: {kind: "video", title?, url?, videoId?, creator?} | {kind: "text"}; estMinutes?; builtBy?; curated?: true; updatedAt?: number (epoch s)}`
  - `ContinueItem {lessonId; title; mode; stepIndex?; stepCount?; stepTitle?; lastActiveAt?; libraryId?}` (libraryId only when the lesson is in the library, so Continue needs no build)
- **`library.item`** (`GET /library/{id}`, reply to `library.get`): `{item: LibraryDetail}`; 404 / no reply when the id is bad or missing
  - `LibraryDetail = LibraryItem & {overview?; outcome?; stepList: {n, title, check?}[]; libraries?: string[]; prerequisites?: string[]}`
- **`progress`** (`GET /progress`, reply to `progress.get`): `ProgressPayload | null` (null = nothing yet, the app shows empty states)
  - `ProgressPayload {skills: SkillTrack[]; completed: {lessonId, title, finishedAt?, result?: {passed?, skipped?, total?}, libraryId?}[]; inProgress: {lessonId, title, mode, stepIndex?, stepCount?, passed?, skipped?, stepTitle?, lastActiveAt?, libraryId?}[]}`
  - `SkillTrack {track; mastered: number; total: number; skills: {id, label, state: "mastered" | "practicing" | "not_started"}[]}`
  - No week minutes, streak or review list: those are deferred (no scheduler), so the fields are absent, never zero.
- **System status events** (poller, sent only on change):
  - `blocker {kind: "network"}` after 2 failed probes in a row; `blocker {kind: "network", clear: true}` on the next good one
  - `status {state: "busy", retryInS}` after `mark_busy(s)`; when busy ends, `status <restore_status()>` (the session's own state)
  - `health {...}` when the rows change (`health.same`)

## Security (BUILD-PLAN section 6, E1 rows)
- Library ids must match `^[A-Za-z0-9_-]{1,64}$` and resolve (symlinks followed) to a regular `.json` file directly inside the cache dir (`builder.CACHE_DIR`, `MIYAGI_LIBRARY_DIR` overrides). `raw/` drafts, subfolders and symlinks that leave the dir are refused.
- Every payload is built from allowlisted fields, then `library.scrub()`: drops `workdir`, `path`, `cwd`, `keys`, `token`..., drops any string holding an absolute or home path, removes `sk-ant-`, `AIza`, `postgres://`, `xi-` key text. No graph `workdir` ever leaves the engine.
- Health probes never prompt: `CGPreflightScreenCaptureAccess` (never Request), `AXIsProcessTrusted` (never WithOptions), a folder listing of `~/.vscode/extensions` for `miyagi.companion-*`, the companion's own 0.3 s `/state` scan on 127.0.0.1. No subprocess.
- The network probe is a bare TCP connect to `MIYAGI_NET_PROBE` (default `api.anthropic.com:443`, no bytes sent, no API call); `MIYAGI_NET_PROBE=0` turns it off.

## Checks run
- `python -m py_compile` on the four files: green.
- `python -I -c "import ..."` for each module with `ANTHROPIC_API_KEY= GEMINI_API_KEY= BRIGHTDATA_API_KEY= TIGER_DATABASE_URL=` (run-live venv, worktree first on `sys.path`): green.
- An offline smoke script in the scratchpad (not a test suite, no network, injected probes, temp state dir): library listing over the real cache (7 items, one per video, no paths in the JSON), traversal and symlink ids refused, scrub, progress from a saved NN lesson and from fake history, health rows and counts, the poller's change-only sends (one blip is not offline, busy, restore, health off).

## Core requests
1. **W0-1 contract:** add the shapes above (`HealthItem`, `LibraryItem`, `LibraryDetail`, `ContinueItem`, `ProgressPayload`, `SkillTrack`, `blocker {kind:"network", clear?}`, `status {state:"busy", retryInS}`), all fields optional where marked.
2. **E2 wiring** (`main.py` / `hub.py`):
   - `GET /health` and `health.get` → `await asyncio.to_thread(health.snapshot)` (or `await system_status.refresh_health()` once the poller exists; it updates the snapshot without a duplicate send).
   - `GET /library` → `library.listing()`; `GET /library/{id}` → `library.item(id)` or 404 with fixed text; `library.list` / `library.get` reply with the same.
   - `library.start {id}` → `library.load_graph(id)`, then start the lesson from that graph with zero model calls. The graph's `lesson.workdir` is someone else's path: prepare a fresh lesson folder, never trust it.
   - `GET /progress` and `progress.get` → `progress.progress()` (null allowed).
   - One `SystemStatus(emit=<hub broadcast>, restore_status=lambda: {"state": session.status})` per engine: `start()` on startup, `replay()` sent to each newly connected app, `stop()` on shutdown. `watch_health(False)` is available if E2 wants health sampling only while onboarding or settings is open.
3. **E4 (cost guards / llm):** on a provider 429 / overloaded answer call `system_status.mark_busy(retry_after_s)` and `clear_busy()` on the next success; on a connect error `note_network(False)`.
4. **E3 (`sessions/store.record_completed`):** store the lesson's `skillMap` and `result {passed, skipped, total}` on each history entry. `progress.py` reads both; until then finished lessons show with no skills (never invented).
5. **A3 / A4 (app):** prefer `main/permissions.ts` for the Screen Recording and Accessibility rows (the engine's probe answers for whatever process macOS holds responsible, Terminal for an external engine); use the engine's `companion` and `engine` rows.
6. **A6 (app):** the library copy must not claim cross-user sharing; `source.creator` is only present when the cache has a channel name (today it does not, so no "by" line).

## Notes
- Library dedupes by video id (text lessons by title), newest cache file wins, and skips provisional or incomplete long-video builds.
- `estMinutes` comes only from the lesson itself (`lesson.build.estMinutes`, else the sum of every step's `estMinutes`); video lessons have none today.
- The poller's pure parts (`settle_network`, `changes`, `retry_in`) take the clock as an argument, so E2 can unit-test them later without sockets.
