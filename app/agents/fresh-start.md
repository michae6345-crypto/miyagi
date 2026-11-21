# fresh-start

**Status:** done (typechecked, Node check green; not run in Electron: offline lane, no app or engine started) · **Branch:** `michael/app-fresh-start`

## Goal
Every launch is a fresh start. Michael: "Every time I start miyagi, it opens up the stuff on the left and right, even
while the top is not working. It's like continuing a lesson. No, I need it to restart."

On launch no lesson surface opens (steps drawer, lesson panel, cards, player window, spotlight, the pill's lesson
state, the lesson keys). They open only for a lesson the learner starts or picks in this run: a typed goal or link,
a search result, Ready to run / Continue in Home or the launcher (library.start), or an explicit Continue (action resume).

## Root cause
The engine sends a full snapshot on every connect (`app/src/main/engine.ts:244`). After a restart it replays the
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
  (`learn`, `learn_url`, `build_lesson`, `library.start`, `action resume`) makes the next `lesson.ready` this run's
  lesson (its id is kept). Lesson events (`lesson.ready/updated/building`, `step.*`, `check.updated`, `offtrack`,
  `spotlight`, `video.*`, `metric`, `screen.seen`, `lesson.paused/resumed`, lesson cards `resume/setup/step/where/hint`
  or any card with a stepId, diagrams with a stepId, `status` watching/offtrack/passed, non-network blockers) pass only
  while this run has a lesson or one is on its way. Hello, search, library, progress, health, keys, errors, an answer
  card and `lesson.ended` always pass. `lesson.ended` (not `interrupted`) clears the run's lesson; an interrupted
  lesson's replay passes again because its id matches. A failed build ends the wait. `DEMO=1` starts armed.
- `app/src/main/engine.ts` (core, 8 lines): `EngineLink` owns a `RunGuard`; `send()` reports each command that
  actually goes out; `dispatch()` drops what the guard refuses before the replay log and every listener. So windows,
  the `ui:ready` replay, the player window, overlay raises and the lesson keys all see the same filtered stream.
  `index.ts` needed no change.
- Continue stays a quiet option: the Library / launcher Continue rows (`library.start`) still start a cached lesson.
  The engine's "Continue where you left off?" card no longer pops up at launch.

## Test
`npx tsx src/main/freshStart.check.ts` (from `app/`; Node only, no Electron, a fake engine on 127.0.0.1):
RunGuard cases (old replay dropped at launch for every lesson event type, neutral events pass, each start command
lets its lesson in, interrupted/ended/foreign-end/failed-build/dev.reset/DEMO) plus the real `EngineLink` (loaded
through Vite SSR) against a fake engine that replays an old lesson on connect: nothing of it reaches the listeners
or `engine.log`; after `learn` the new lesson does; a reconnect replaying the run's own lesson keeps it.
With the guard removed from `dispatch()` the check fails (verified).

## Core requests
1. **engine.ts (applied, minimal):** the 8-line `RunGuard` hook in `EngineLink` (import, field, constructor,
   `this.run.command(cmd)` after the v2 capability check in `send()`, `if (!this.run.admit(e)) return` in
   `dispatch()`). Adrian: please keep it when merging; it is the only place every window, the replay log and main's
   features share.
2. No `index.ts`, `core/`, preload or common change.

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

## Open
- Not verified in Electron (offline lane). Michael's next clean launch should show only the pill: no drawer, no
  player, no cards until a lesson is started.
- If the engine answers `action resume` without a new `lesson.ready`, the app shows nothing (see engine item 3).
- A `learn` that never produces a lesson (search abandoned) leaves the guard waiting; a stale replay arriving after
  that would pass. Rare (needs a reconnect replay in that window); the engine fix removes it.
