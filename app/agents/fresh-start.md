# fresh-start

**Status:** done, review round 2 applied (typechecked, Node check green; not run in Electron: offline lane, no app or engine started) · **Branch:** `michael/app-fresh-start`

## Goal
Every launch is a fresh start. Michael: "Every time I start miyagi, it opens up the stuff on the left and right, even
while the top is not working. It's like continuing a lesson. No, I need it to restart."

On launch no lesson surface opens (steps drawer, lesson panel, cards, player window, spotlight, the pill's lesson
state, the lesson keys). They open only for a lesson the learner starts or picks in this run: a typed goal or link,
a search result, Ready to run / Continue in Home or the launcher (library.start), or an explicit Continue (action resume).

## Root cause
The engine sends a full snapshot on every connect (`app/src/main/engine.ts:251`). After a restart it replays the
lesson it kept: `lesson.ready`, `step.started`, `check.updated`, cards (often a `resume` card), `status watching`,
`video.*`. Main relayed every event, with no notion of "this run", to:

1. every window: `app/src/main/index.ts:402` (`engine.onEvent` → `engine:event`), which also registers the lesson
   keys on `lesson.ready` (`index.ts:404`);
2. the replay log, replayed to each window on `ui:ready` (`index.ts:441`), so a window that loads late got it too;
3. main's own features: the player window shows on `lesson.ready` (`main/features/player.ts:132`, and
   `player.ts:135` from the log at start-up); the overlay is raised on lesson events (`main/features/overlay-raise.ts:77`).

In the renderers that `lesson.ready` then:
- opens the steps drawer (`renderer/src/features/drawer/store.ts:112`, "every lesson opens the steps drawer", merge
  5f04f998; video lessons put it on the LEFT, the player sits on the RIGHT: "the stuff on the left and right");
- fills the core lesson store, so the pill shows lesson state (`renderer/src/core/lesson.ts:250`);
- `step.started` restores the saved live network if it matches (`renderer/src/features/diagrams/store.ts:172`).

No renderer store restores a lesson from localStorage or prefs on its own: drawer side, `panelCollapsed` and the
saved live network only take effect once a lesson arrives. The single source was the engine's replayed lesson.

## Fix
- `app/src/main/freshStart.ts` (new, pure): `RunGuard`. Nothing is accepted at launch. A start command from this run
  (`learn`, `learn_url`, `build_lesson`, `library.start`, `action resume`, `action build` on this run's preflight card)
  makes the next `lesson.ready` this run's lesson (its id is kept). Lesson events (`lesson.ready/updated/building`,
  `step.*`, `check.updated`, `offtrack`, `spotlight`, `video.*`, `metric`, `screen.seen`, `lesson.paused/resumed`,
  lesson cards `resume/setup/preflight/step/where/hint/complete` or any card with a stepId, diagrams with a stepId,
  non-network blockers) pass only while this run has a lesson or one is on its way. Hello, search, library, progress,
  health, keys, errors, an answer card and `lesson.ended` always pass. `lesson.ended` (not `interrupted`) clears the
  run's lesson; an interrupted lesson's replay passes again because its id matches. `DEMO=1` is armed: a lesson is on
  its way at start and again after every `dev.reset` (the mock replays its scenario's `connect` segment).
- The pill never spins for a lesson this run doesn't have (`freshStart.ts:169`, review round 2). With no lesson,
  `status` thinking / busy pass only while a non-start `action` of this run (ask, explain, hint, diagram, retry ...)
  waits for its answer; the wait ends on a passing card, diagram, `error`, `status idle`, `end_lesson`, `dev.reset` or
  a new connection. An old lesson's watching / offtrack / passed are rewritten to `{state: 'idle'}`
  (`freshStart.ts:171`; dropped instead while a press waits, so its spinner stays). Before this, an old lesson's
  "Looking at your code" thinking passed and its watching was dropped, so `core/lesson.ts:353` kept the pill on that
  spinner for good ("the top is not working").
- The preflight card (`kind: 'preflight'`, no stepId) is a lesson card (`freshStart.ts:59`): the engine's snapshot
  of an old pick (`session.py` snapshot(), `pending_pick.card`) no longer shows at launch. It only ever follows this
  run's `learn` / `learn_url`, when a lesson is already on its way.
- The wait ("a lesson is on its way") ends on that lesson's `lesson.ready`, a failed build, `end_lesson` (the command
  or `action {kind: 'end_lesson'}`) or `dev.reset`. It survives a new engine connection (sleep / wake during a
  multi-minute build), but then it is "carried": only a fresh `lesson.ready` (no `replay: true`, or the run's own id)
  ends it (`freshStart.ts:146`), and of that connection's snapshot only `lesson.building` (the learner's build) passes,
  plus its thinking once the build is back. A start sent on the new connection (`action resume`, a `learn` or
  `library.start` of the lesson the engine already runs: all answered with a `replay: true` snapshot) ends the carry,
  so its replay passes. So an abandoned search or a `library.start` error can still never admit the old lesson an
  engine restart replays, and a long build no longer disappears after a socket drop.
- `app/src/main/engine.ts` (core, small): `EngineLink` owns a `RunGuard`. `send()` reports a command to the guard only
  when it really leaves: right before `demo.handle(cmd)` (`engine.ts:188`) or `ws.send(msg)` on an OPEN socket
  (`engine.ts:193`). A `learn` / `library.start` sent offline (the launch window while localEngine starts, or an
  engine restart) is failed or dropped as before and arms nothing. ws `'open'` calls `run.connected()`
  (`engine.ts:255`). `dispatch()` runs `run.filter(e)` before the replay log and every listener (`engine.ts:311`):
  nothing, or the event, or the idle rewrite. So windows, the `ui:ready` replay, the player window, overlay raises and
  the lesson keys all see the same filtered stream. `index.ts` needed no change.
- Dev only: `MIYAGI_REPLAY_ON_CONNECT=1` (read in `engine.ts:98`) arms the guard on every connection, for
  `npm run dev:all` (mock/replay.ts plays a scenario's `connect` lesson on every connect). Run
  `MIYAGI_REPLAY_ON_CONNECT=1 npm run dev:all` (concurrently passes the env to the app); without it, a scenario whose
  `connect` segment plays a lesson shows nothing until a `learn` or `library.start`. `package.json` is core, so the
  script itself is unchanged (see Core requests). Never set it for the shipped app.
- Continue stays a quiet option: the Library / launcher Continue rows (`library.start`) still start a cached lesson.
  The engine's "Continue where you left off?" card no longer pops up at launch.

## Test
`npx tsx src/main/freshStart.check.ts` (from `app/`; Node only, no Electron, fake engines on 127.0.0.1): 287 passed,
0 failed. RunGuard cases: old replay dropped at launch for every lesson event type (now with a preflight card and a
thinking / busy status), neutral events pass, each start command lets its lesson in, interrupted / ended /
foreign-end / failed-build / dev.reset, DEMO and dev.reset, replay-on-connect, end_lesson ending the wait, the carried
wait (abandoned search, `library.start` error, a long build across a reconnect, a failed build after it, resume /
library.start / learn on the new connection admitting their replay), preflight, and the pill (an old lesson's thinking
then watching, watching then thinking, a snapshot ending on thinking, busy then passed: all leave it idle; a typed
question keeps its spinner until its answer). The real `EngineLink` (loaded through Vite SSR) against fake engines:
- launch: nothing of an old lesson reaches the listeners or `engine.log`, no thinking / busy either; after `learn` the
  new lesson does; a reconnect replaying the run's own lesson keeps it;
- offline: starts sent before the engine is up, or while it restarts, admit nothing; a `learn` that goes out but is
  never answered, then a restart: the old lesson stays out;
- carried: `build_lesson`, the socket drops, the engine stays up: its snapshot's `lesson.building` and the build's
  final `lesson.ready` reach the listeners and the log;
- `MIYAGI_REPLAY_ON_CONNECT=1`: a scenario's connect lesson shows; the same link without it keeps it out.
Each round-2 fix was checked to fail its cases when reverted (no preflight: 9 fail; dev.reset not re-armed: 4; thinking
always passing: 14; no idle rewrite: 1; old `connected()`: 11; replay allowed to end a carried wait: 28).

## Core requests
1. **engine.ts (applied, minimal):** the `RunGuard` hook in `EngineLink`: import, field, constructor (armed by DEMO or
   `MIYAGI_REPLAY_ON_CONNECT=1`), `this.run.command(cmd)` inside the demo branch and the `readyState === OPEN` branch of
   `send()` (only commands that really leave), `this.run.connected()` in ws `'open'`, and
   `const kept = this.run.filter(e); if (!kept) return; e = kept` in `dispatch()`. About 20 lines. Adrian: please keep
   it when merging; it is the only place every window, the replay log and main's features share.
2. **package.json (not applied, optional):** `dev:all` could run the app as `MIYAGI_REPLAY_ON_CONNECT=1 npm run dev`
   so lesson scenarios show without the env prefix. Until then use `MIYAGI_REPLAY_ON_CONNECT=1 npm run dev:all`.
3. No `index.ts`, `core/`, preload or common change.

## For the engine lane (claude/eng-no-auto-resume)
The app now ignores a replayed lesson it did not start, but the engine should also:
1. Not resume the last lesson on launch/connect: no `lesson.ready` / `step.started` / cards / `status watching` /
   `video.*` for a kept lesson unless the app asks. Set `engine.hello.restored` false on a fresh engine start.
2. Not run checks, timers, OCR or Claude calls for a kept lesson nobody resumed (the app no longer shows them, so
   they would only cost money).
3. Answer `action resume` (and `library.start` of a cached lesson) with a full fresh snapshot: `lesson.ready` first,
   then `step.started` and the current checks. The app only accepts a lesson after a start command; it does not
   re-dispatch the snapshot it dropped.
4. Keep `lesson.ended {reason: "interrupted"}` + the same lesson id on reconnect for a deploy mid-lesson: the app
   keeps the run's lesson through that.
5. Send `lesson.ended` with `lessonId` when it can, so an old lesson's end never clears the run's lesson.
6. Keep `replay: true` on every snapshot `lesson.ready` (session.py snapshot()) and never on a new lesson: after a
   reconnect the app lets a build's wait end only on a `lesson.ready` without it. A kept lesson's background
   `status` thinking / busy (with detail) no longer reaches the pill when the app has no lesson and no press waiting,
   and its watching / offtrack / passed reach it as idle, so the pill can't stick on an old spinner. Item 2 still
   matters: those statuses are model calls nobody asked for.

## Open
- Not verified in Electron (offline lane). Michael's next clean launch should show only the pill: no drawer, no
  player, no cards, no spinner until a lesson is started.
- If the engine answers `action resume` without a new `lesson.ready`, the app shows nothing (see engine item 3).
- A tiny race remains: a start that goes out in the milliseconds between ws `'open'` and the snapshot's old
  `lesson.ready` on the same connection would admit it (a start on the new connection may be answered by a replay,
  so a replay can't be refused then). The learner cannot send while offline, so this needs a click at the exact
  moment the engine connects; engine item 1 removes it.
- After a reconnect mid-build, the snapshot's first `status thinking` arrives before its `lesson.building` and is
  dropped; the build panel shows progress and the next thinking tick passes.
- A non-start press whose answer never comes (engine crash mid-ask) keeps letting thinking through until the next
  card, error, idle status or connection; the next connection always clears it.

## Review leftovers (round 3, not yet fixed)
1. **Blocking: the old lesson leaks between a start and this run's `lesson.ready`.** In `freshStart.ts`, `live()`
   is true whenever `pending && !carried`, and `filter()` passes every event (`if (this.live()) return e`) before
   any lesson check. After `learn` / `learn_url`, the kept lesson's `step.started`, offtrack, spotlight, hint / step /
   resume cards, `video.play`/`seek`, status watching and `check.updated` reach every window and the replay log, for
   the whole search, preflight and build. If the search is abandoned (launcher closed, nothing picked, search
   failed), `pending` stays true for the rest of the connection. Probe: `new RunGuard(); connected();
   command(learn)`, then spotlight, offtrack, hint card, resume card, video.play and step.started all pass; state
   stays `{pending:true, lessonId:undefined}`. Fix: split `live()` into "has this run's lesson" (lessonId set) and
   "start on its way" (pending, no lessonId). In the second state admit only pre-lesson traffic: `lesson.ready`,
   `lesson.building`, `search.*`, the preflight card, non-lesson cards, status thinking/busy/idle, error, and
   network/clear blockers. Keep dropping `step.*`, `check.updated`, offtrack, spotlight, `video.*`, metric,
   `screen.seen`, `lesson.paused/resumed`, `lesson.updated`, cards of kind resume/step/where/hint/complete or with a
   stepId, step diagrams, and old watching/offtrack/passed (rewritten to idle) until the run's own `lesson.ready`.
2. **Tests for 1** in `freshStart.check.ts`: (a) learn, then old step.started, offtrack, spotlight, hint card, resume
   card, video.play and status watching are dropped (watching becomes idle) while preflight, lesson.building and
   search rows pass; (b) abandoned learn, same events still dropped; (c) learn, new lesson.ready, then step.started
   passes. Plus one EngineLink case: the fake engine replays an old lesson on connect and keeps emitting its step
   events after `learn`; none reach listeners or engine.log before the new `lesson.ready`.
3. **Minor:** `RunGuard.command` sets `asking=true` for every non-start kind, including ones with no answer
   (voice_toggle, pick_another, download, open_in_browser, install). Then the old lesson's thinking passes and its
   watching is dropped instead of rewritten to idle: the round 2 stale spinner returns. Limit asking to ask,
   explain, diagram, hint, show_me, retry, check_step (or add a short timeout), with one case.
4. **Brief:** in Fix, explain the pre-ready window (only build and preflight traffic passes until this run's
   `lesson.ready`). Engine lane ask: stop the kept lesson's checks, timers and cards once `learn` / `learn_url`
   arrives, not only when the new `lesson.ready` lands.
