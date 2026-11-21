# engine-isolation

**Status:** pass 1 done (typecheck + full app suite green; the installed app was not opened in this lane) · **Priority:** P0 · **Port:** none (no UI) · **Branch:** `michael/app-engine-isolation`

## Goal
Michael, on the installed app, every launch: "Right when it opens, it just opens up everything." One cause: the installed
miyagi and a dev setup (a dev engine in Terminal, or `npm run dev` with MIYAGI_AUTOSTART=1) shared one engine, one
lesson save, one pid file and one settings folder. The installed app found any engine on :8787 and silently used it
('external'), so a dev engine's lesson, VS Code and video came along. Now they can never share any of those, and the
engine the app starts can't be told to auto-resume or autostart.

## Owns
- `app/src/main/localEngine.ts`, `app/src/main/identity.ts` (Core files: see Core requests)
- `app/test/engineIsolation.test.ts`, this brief

## What changed
- **No silent adoption (localEngine.ts, pure `adoptExternal({packaged, mode, ours})`).** Port taken and
  `reclaimOwnLeftover()` says it isn't ours: `npm run dev` or engine mode dev still use it ('external', unchanged). The
  installed app (packaged, mode bundled) does not. It writes the holder to engine.log (lsof pid and command name, no
  command line, redacted), sets state `failed`, line "Another miyagi engine is running.", reason
  `port 8787 held by an engine this app did not start`, never stops the other engine, polls the port every 5 s and runs
  the start-up sequence again once it is free. The same rule covers the race where the app's own engine exits 1 because
  the port was taken. Restart re-checks. While holding, a link that reaches the other engine does not flip the state to
  'external'.
- **Pinned engine env (pure `enginePins`, `pythonEnv(env, home, python, port, packaged)`, `launcherEnv`).** Bundled
  Python and launcher runtimes both get `ORCH_AUTO_RESUME=0` and `ORCH_AUTOSTART=0` (hard in a built app, ignoring the
  inherited env; `npm run dev` keeps an explicit value, default 0) and an explicit `MIYAGI_STATE_DIR`
  (env, else `~/miyagi/state` for the installed app). The launcher used to get the bare env; on eng-fresh-launch the
  launcher script defaults `ORCH_AUTO_RESUME` to 1, so this pin is what keeps an app-started launcher engine fresh.
- **Pid file per build.** `run/app-engine.json` when packaged, `run/app-engine-dev.json` when not: a dev app with
  MIYAGI_AUTOSTART=1 can never reclaim or SIGTERM the installed app's engine, nor the reverse.
- **Settings folder per build (identity.ts, `userDataPath` / `isolateUserData`).** Before ready, a dev run sets
  userData to `<appData>/miyagi-dev`; the installed app keeps `<appData>/miyagi`; `MIYAGI_USER_DATA` wins in either.
  The dev app no longer writes prefs.json, onboarding.json, auth.bin, login.json, engine.json or the crash marker into
  the installed app's folder. Nothing on disk is moved or deleted (Michael's call).

## Decisions
- **Keep port 8787 for the packaged engine.** `vscode-ext/extension.js:770` posts VS Code events to
  `http://127.0.0.1:8787/vscode/event` (its default `engineUrl`), and `main/serve.ts`'s CSP allows connect-src and
  media-src only on :8787. Moving the packaged engine to another port would break lesson checks and media. Isolation
  is by ownership (pid file, command line, start time), not by port.
- **Dev engines started by this app save to `~/miyagi/state-dev`** (not packaged, no MIYAGI_STATE_DIR in env), the
  same folder lane launch-quiet uses for dev engines. The brief only fixed the packaged default (`~/miyagi/state`,
  unchanged); this keeps a dev app's engine out of the installed app's saves too.
- **MIYAGI_USER_DATA also wins in a built app.** A Finder launch has no shell env, so it only matters for tests or a
  deliberate second copy.

## Core requests
- `src/main/localEngine.ts` and `src/main/identity.ts` are Core files; this lane edits them with the integrator's
  brief. Additive: one optional 5th parameter on `setupLocalEngine` (`deps`, test fakes only; index.ts unchanged),
  new exports `adoptExternal`, `pidFileName`, `enginePins`, `launcherEnv`, `pythonEnv`, `ENGINE_HELD_LINE`,
  `HELD_POLL_MS`, `LocalEngineDeps`, and `userDataPath`, `isolateUserData`, `DEV_USER_DATA` in identity.ts.
- **engine.ts (not this lane):** EngineLink has no way to hold off. While localEngine says the port belongs to another
  engine, the link still connects to it (index.ts connects before whenReady). An engine started with another launch's
  token refuses it, but a dev engine without a token accepts it, so the renderer can still see that engine's events
  while the state reads failed. Ask: `engine.hold(true|false)` (close and don't reconnect while held), called from
  localEngine's hold() and stopHolding().
- **Renderer / onboarding (not this lane):** the `failed` state with `ENGINE_HELD_LINE` reuses the engine-failed
  surfaces; a calmer dedicated row ("Another miyagi engine is running." with no Copy details) would read better.

## Test
`cd app && node --import tsx --import ./test/setup.mjs --test --test-force-exit test/engineIsolation.test.ts`
(no engine, no lsof: spawn and the holder lookup are fakes; the "engine" on the port is a bare TCP listener the test
owns). The regression case ("ends in failed ... never external") fails on origin/michael/v2-integration with
`states: checking > external`.

## Notes
- Existing dev settings stay in `~/Library/Application Support/miyagi`; a dev run now starts from an empty
  `miyagi-dev` folder (first-run onboarding, signed out). Copy files across by hand if wanted.
- `MIYAGI_HOME` (`~/miyagi/engine`: src copy, BUNDLED marker, logs) is still shared by a dev app with
  MIYAGI_AUTOSTART=1 and the installed app. Only the pid file is per build, as briefed.
