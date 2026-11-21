# reconnect

**Status:** fix round 1 done (typecheck, app suite and the main checks green, all offline; not run in Electron) · **Priority:** P0 · **Port:** none (no UI) · **Branch:** `michael/app-reconnect`

## Goal
ROADMAP 1.4, reconnect and recovery: a lost socket, an engine crash, a hung engine or a Mac that slept never leaves
dead UI, and never brings back an old lesson. The learner sees the calm "reconnecting" line, then the lesson they
started in this run (or nothing, if the engine lost it). Retry only shows after a real failure.

## Owns
- `app/src/main/respawn.ts` (RespawnBudget, superviseEngine), the engine half of `app/src/main/features/recover.ts`
- `app/test/reconnect.test.ts`, `app/test/fakes/scenarios.ts`, this brief
- Shared edits, minimal (see Core requests): `main/engine.ts`, `main/localEngine.ts`, `main/heartbeat.ts`,
  `main/freshStart.ts`, `test/setup.mjs`, `test/engineIsolation.test.ts`

## What changed
- **One heartbeat.** Integration's `heartbeat.ts` (ping 5 s, dead after 30 s, wake probe 8 s) is the only one; this
  lane's copy inside engine.ts is gone. New: a tick that fires 3+ beats late means the Mac slept, so it probes
  instead of dropping a healthy socket (a dead one is still caught within the probe window).
- **Held failures** (`EngineLink.holdFailures`). While localEngine is checking, installing, starting or respawning,
  refused connects are not counted (LinkInfo failures stays 0, the pill stays on "reconnecting"), and a waiting slow
  retry moves back to the 1 s one, so the new engine is picked up within about a second of it listening.
- **Respawn budget** (`respawn.ts`). The engine this app started dies mid-run: start it again after 0.5 s, 2 s, 5 s;
  at most 3 in 3 minutes, then the failure is reported with Retry. Only a spent, reported budget is refilled, when an
  engine answers again (the one Retry started, or one the user runs). An engine that connects and then crashes again
  keeps spending the same budget, so a crash loop on a replayed snapshot or a first step still ends in Retry.
  Retry while a respawn waits starts it at once. Quitting cancels a waiting respawn.
- **Hung engine** (`superviseEngine`). Ours, alive, `running`, but the link has been down 30 s while awake: restart
  it, from the same budget. The 30 s clock starts when the link goes down; the link reports "down" again on every
  failed attempt (each close, 1 s retry and 4 s handshake timeout), and those repeats leave the clock alone (before,
  they re-armed it, so a hung engine was never restarted). Still down 30 s after a restart and the new engine
  `running`: checked again, until the budget is spent. Never across a sleep (resume starts the clock again if the link
  is still down), never an engine this app did not start (Terminal, another build).
- **Wake.** index.ts already calls `engine.wake()` on resume, unlock and network back; recover.ts no longer does it a
  second time, it only pauses the hung verdict while asleep.
- **Fresh start across reconnects** (`freshStart.ts`). RunGuard keeps filtering on every connect. Fixed a gap: with a
  lesson of this run, a respawned engine replaying another save had its lesson.ready dropped, but its steps, checks
  and resume card passed under the run's id. A dropped foreign lesson.ready now clears the run's lesson.

## Decisions
- Kept integration's heartbeat timings (5 s / 30 s / 8 s) over this lane's (15 s / 45 s / 5 s): newer, and tuned with
  the island's watchdogs.
- No resume command: the session comes back through the engine's snapshot on connect (contract unchanged).

## Core requests
- `src/main/engine.ts` (app/CLAUDE.md lists it as core): additive only. A 4th optional constructor parameter
  `timings` (tests only; index.ts unchanged; fix round 1 adds `handshakeMs` to it, default HANDSHAKE_TIMEOUT_MS) and
  `holdFailures(on)`.
- `src/main/localEngine.ts` (core, as engine-isolation notes): `setRespawnPolicy`, `restartLocalEngine`,
  `localEngineChildAlive`, the respawn timer in the exit handler and Retry, `holdFailures` from `set()`.
- Not done here, still open from engine-isolation.md: `engine.hold(true|false)` (close and stop reconnecting while
  another engine holds the port).

## Test
`cd app && node --import tsx --import ./test/setup.mjs --test --test-force-exit test/reconnect.test.ts` (20 tests, a
loopback `ws` server stands in for the engine: no Electron, no engine, no network). The hung path is tested with a
real EngineLink against a loopback TCP server that accepts but never completes the WebSocket handshake
(`handshakeMs` 150, hungMs 1.5 s): the link reports "down" on every attempt, and the restart must still come once. The
fake-link hung tests send a single "down", so they could not catch the re-arming bug; that test, "repeated down
reports" and "a crash loop that reconnects each time" fail on the round-0 respawn.ts. Also `npx tsx
src/main/freshStart.check.ts` (760) and `npx tsx src/main/island-sync.check.ts`. The new "this run's lesson comes
back, a respawned engine's old lesson does not" case fails without the freshStart.ts fix.

## Notes
- Not run in Electron. On the Mac: start a lesson, `kill -9` the engine's Python; the pill should say reconnecting and
  come back within a few seconds, at most 3 times in 3 minutes, then "couldn't start" with Retry.
- The installed app pins `ORCH_AUTO_RESUME=0` (engine-isolation), so a respawned engine likely comes back without the
  lesson (not checked against the engine: its code is not on this branch). Then core/lesson.ts resets the screen 2 s
  after the reconnect: no dead UI, but the learner starts the lesson again.
