# fresh-start

**Status:** done, review rounds 2 and 3 applied (typechecked, Node check green; not run in Electron: offline lane, no app or engine started) · **Branch:** `michael/app-fresh-start`

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
  makes the next `lesson.ready` this run's lesson (its id is kept). Lesson events (`lesson.updated`, `step.*`,
  `check.updated`, `offtrack`, `spotlight`, `video.*`, `metric`, `screen.seen`, `lesson.paused/resumed`, lesson cards
  `resume/setup/preflight/step/where/hint/complete` or any card with a stepId, diagrams with a stepId, non-network
  blockers) pass only once this run has its lesson (its `lesson.ready` arrived). Hello, search, library, progress,
  health, keys, errors, an answer card and `lesson.ended` always pass.
- **The pre-ready window (review round 3).** Between a start and this run's `lesson.ready` ("a start on its way":
  pending, no lessonId) only the new lesson's build traffic passes: `lesson.building`, this run's preflight card,
  search rows, status thinking / busy / idle, errors, network / clear blockers and the `lesson.ready` itself. The kept
  lesson's `step.started`, checks, offtrack, spotlight, hint / step / resume / where cards, step diagrams, `video.*`,
  pause, metric and `lesson.updated` stay out, and its watching / offtrack / passed reach the pill as idle
  (`freshStart.ts` filter(): `if (this.lessonId) return e`, then `opening`). Before, `live()` was true for
  `pending && !carried`, so all of that passed for the whole search, preflight and build.
- **An abandoned start expires**, so the old lesson stays filtered for the rest of the run: a `learn` search ends
  with `search.done` (nothing picked, or the search failed: the engine sends `error` then `search.done`; a pick is
  `build_lesson` / `learn_url`, a start of its own; `pick_another` makes the pick's wait a search again, and the
  engine's re-sent `search.done` ends it); a `library.start` answered with `error` before any build progress; and no
  sign of life (start, search row, `lesson.building`, which the engine ticks at least once a second) for
  `OPEN_TTL_MS` (2 min), or `PICK_TTL_MS` (30 min) after this run's preflight card while the learner reads it (Build
  later is a start again). A reconnect gives a carried build `OPEN_TTL_MS` again. `learn` modes `lesson` / `demo`
  build at once and are not searches. Armed runs (DEMO, replay-on-connect) never expire. The clock is injectable
  (`new RunGuard(armed, now)`); `engine.ts` is unchanged.
- **Only presses the engine answers wait (review round 3).** `asking` is set for `action` ask, explain, diagram,
  hint, show_me, retry and check_step only. voice_toggle, pick_another, download, open_in_browser, install, back,
  confirm, undo and the other fire-and-forget kinds no longer let an old lesson's thinking through (the round 2 stale
  spinner could come back through them). `lesson.ended` (not `interrupted`) clears the
  run's lesson; an interrupted lesson's replay passes again because its id matches. `DEMO=1` is armed: a lesson is on
  its way at start and again after every `dev.reset` (the mock replays its scenario's `connect` segment).
- The pill never spins for a lesson this run doesn't have (filter(), status branch, review round 2). With no lesson,
  `status` thinking / busy pass only while a start is on its way or an answered `action` (ask, explain, hint, diagram ...)
  waits for its answer; the wait ends on a passing card, diagram, `error`, `status idle`, `end_lesson`, `dev.reset` or
  a new connection. An old lesson's watching / offtrack / passed are rewritten to `{state: 'idle'}`
  (dropped instead while a press waits, so its spinner stays). Before this, an old lesson's
  "Looking at your code" thinking passed and its watching was dropped, so `core/lesson.ts:353` kept the pill on that
  spinner for good ("the top is not working").
- The preflight card (`kind: 'preflight'`, no stepId) is a lesson card (`LESSON_CARDS`): the engine's snapshot
  of an old pick (`session.py` snapshot(), `pending_pick.card`) no longer shows at launch. It only ever follows this
  run's pick (`learn_url`, `build_lesson`), while that start is on its way (the one lesson card the pre-ready window admits).
- The wait ("a lesson is on its way") ends on that lesson's `lesson.ready`, a failed build, the expiry above, `end_lesson` (the command
  or `action {kind: 'end_lesson'}`) or `dev.reset`. It survives a new engine connection (sleep / wake during a
  multi-minute build), but then it is "carried": only a fresh `lesson.ready` (no `replay: true`, or the run's own id)
  ends it (filter(), `lesson.ready` branch), and of that connection's snapshot only `lesson.building` (the learner's build) passes,
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
`env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY npx tsx src/main/freshStart.check.ts` (from `app/`; Node only, no
Electron, fake engines on 127.0.0.1): 755 passed, 0 failed. RunGuard cases: old replay dropped at launch for every
lesson event type (with a preflight card and a thinking / busy status), neutral events pass, each start command lets
its lesson in, interrupted / ended / foreign-end / failed-build / dev.reset, DEMO and dev.reset, replay-on-connect,
end_lesson ending the wait, the carried wait (abandoned search, `library.start` error, a long build across a
reconnect, a failed build after it, resume / library.start / learn on the new connection admitting their replay),
preflight, and the pill (an old lesson's thinking then watching, watching then thinking, a snapshot ending on
thinking, busy then passed: all leave it idle; a typed question keeps its spinner until its answer). Round 3:
- the pre-ready window, for each start (`learn`, `learn` mode lesson, `learn_url`, `build_lesson`, `library.start`,
  `action resume`): the kept lesson's step.started, check.updated, offtrack, spotlight, hint (with and without a
  stepId) / resume / step / where cards, video.play / seek, step diagram, lesson.updated / paused, step.passed,
  metric and a lesson blocker are dropped, before and during the build; watching and offtrack statuses arrive as
  idle; search rows, this run's preflight card, the build's thinking, lesson.building, errors and network blockers
  pass; after this run's lesson.ready the same events pass;
- abandoned starts: search over with nothing picked, a failed search (error, search.done), `pick_another` then its
  re-sent search.done, a `library.start` error, the `OPEN_TTL_MS` timeout (build progress keeps it alive), the
  preflight card's `PICK_TTL_MS`: afterwards the kept lesson's events, its lesson.ready and a stray build stay out;
  a pick after search.done, a pick before it (a late search.done), "Just teach me", a learn that builds at once and
  a learn_url preflight error all keep their wait; a reconnect gives a carried build time again; DEMO never expires;
- asking: voice_toggle, pick_another, download, open_in_browser, install, install_all, skip_setup, open_editor, back,
  confirm, undo and card.closed wait for nothing (an old thinking stays out, watching rests the pill); ask, explain,
  diagram, hint, show_me, retry and check_step wait.

The real `EngineLink` (loaded through Vite SSR) against fake engines:
- launch: nothing of an old lesson reaches the listeners or `engine.log`, no thinking / busy either; after `learn` the
  new lesson does; a reconnect replaying the run's own lesson keeps it;
- open start (round 3): the engine replays an old lesson on connect and keeps sending its steps, checks, cards,
  video, spotlight and watching after `learn`: none reach the listeners or `engine.log` before the new
  `lesson.ready`; its `lesson.building` does; then the new lesson and its own step;
- offline: starts sent before the engine is up, or while it restarts, admit nothing; a `learn` that goes out but is
  never answered, then a restart: the old lesson stays out;
- carried: `build_lesson`, the socket drops, the engine stays up: its snapshot's `lesson.building` and the build's
  final `lesson.ready` reach the listeners and the log;
- `MIYAGI_REPLAY_ON_CONNECT=1`: a scenario's connect lesson shows; the same link without it keeps it out.
Each round-2 fix was checked to fail its cases when reverted (no preflight: 9 fail; dev.reset not re-armed: 4; thinking
always passing: 14; no idle rewrite: 1; old `connected()`: 11; replay allowed to end a carried wait: 28). Round 3, each
reverted once: old `live()` (everything passes while pending): 257 fail; no search.done expiry: 10; no library.start
error expiry: 2; no timeout: 3; asking for every action kind: 30; no reconnect grace for a carried build: 1; no
preflight `PICK_TTL_MS`: 1. Also green: `npm run typecheck` and the app's `node --test test/*.test.ts` (29 pass).

## Core requests
1. **engine.ts (applied, minimal):** the `RunGuard` hook in `EngineLink`: import, field, constructor (armed by DEMO or
   `MIYAGI_REPLAY_ON_CONNECT=1`), `this.run.command(cmd)` inside the demo branch and the `readyState === OPEN` branch of
   `send()` (only commands that really leave), `this.run.connected()` in ws `'open'`, and
   `const kept = this.run.filter(e); if (!kept) return; e = kept` in `dispatch()`. About 20 lines. Adrian: please keep
   it when merging; it is the only place every window, the replay log and main's features share.
2. **package.json (not applied, optional):** `dev:all` could run the app as `MIYAGI_REPLAY_ON_CONNECT=1 npm run dev`
   so lesson scenarios show without the env prefix. Until then use `MIYAGI_REPLAY_ON_CONNECT=1 npm run dev:all`.
3. No `index.ts`, `core/`, preload or common change. Round 3 changed only `freshStart.ts` and its check (engine.ts
   untouched: `new RunGuard(armed)` uses the default clock).

## For the engine lane (claude/eng-no-auto-resume, claude/eng-fresh-launch)
The app now ignores a replayed lesson it did not start, but the engine should also (item 1 is merged to
integration/live as `claude/eng-fresh-launch`: a fresh engine no longer auto-resumes at launch, so the kept-lesson
case mainly matters for an engine started by hand or a deploy restart):
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
7. (Round 3) Stop the kept lesson's checks, timers, judge cards and statuses as soon as `learn` / `learn_url` /
   `build_lesson` / `library.start` arrives, not only when the new `lesson.ready` lands. The app drops them in that
   window, but its thinking / busy do pass then (the build's own statuses look the same), so the pill may show the old
   lesson's "Looking at your code" during a search or build. `learn` (video) and `_pick` already end a running graph
   (`end_lesson("new lesson")`); `library.start` and `action resume` of another lesson should too, if they do not already.
8. (Round 3) Send a lesson's `setup` card after its `lesson.ready` (session.py `_offer_editor` already runs after it):
   in the pre-ready window the app admits only the preflight card of the lesson cards.
9. (Round 3) Keep `search.done` the end of every `learn` search (also after an error) and re-send it on
   `pick_another`: the app ends a search's wait on it, so a learn whose search leads nowhere never admits a later
   lesson. Keep the build ticker (`lesson.building` at least once a second): a start with no sign of life for 2 min
   expires in the app.

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
- A press whose answer never comes (engine crash mid-ask) keeps letting thinking through until the next card, error,
  idle status or connection; the next connection always clears it.
- While a start is on its way, a kept lesson's thinking / busy can pass (see engine item 7).
- The expiry is lazy (checked on the next event, command or `state()`), with no timer; a build silent for over
  `OPEN_TTL_MS` (2 min, the engine ticks once a second) or a preflight card left for over `PICK_TTL_MS` (30 min) is
  treated as abandoned: its late `lesson.ready` would be dropped (Build again on the card is a new start).

## Review leftovers (round 3): fixed
1. Blocking leak between a start and this run's `lesson.ready`: fixed (Fix: the pre-ready window; abandoned starts
   expire).
2. Tests (a) learn then old events dropped, (b) abandoned search, (c) the new lesson's own events after its ready,
   and the EngineLink case: added (Test, round 3).
3. `asking` only for answered kinds (ask, explain, diagram, hint, show_me, retry, check_step): fixed, with cases.
4. Brief: Fix and the engine-lane asks (items 7 to 9) updated.
