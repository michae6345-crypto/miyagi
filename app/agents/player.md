# player

**Status:** new · **Priority:** P0 · **Port:** 5182 · **Branch:** `adrian/player`

## Goal
The lesson's video, in our own window docked to the right 40% of the screen (draggable; remembers where you put it). It plays the current step's clip, **pauses itself at the end of the clip until the step's checks pass**, then resumes 400ms after `step.passed`. It follows the engine (`video.seek` / `video.pause` / `video.play`, plus video jumps from cards) and reports its position back. Chapter list = the lesson's steps, with status.

## Owns
- `app/src/renderer/src/features/player/`: window `player`, YouTube IFrame Player API, gating logic, chapters
- `app/src/main/features/player.ts`: create the window, dock it to the right 40%, save/restore bounds, show it on `lesson.ready`
- `app/mock/scenarios/player.json`: e.g. Back / Show me triggers

## Contract
- **In** (engine → app): `lesson.ready` (steps with `video {videoId, start, end}`), `step.started.video`, `step.passed`, `video.seek {t, play}`, `video.pause`, `video.play`; `core/lesson.video` = the current intent (also set by card video jumps)
- **Out** (app → engine): `video.state {t, playing}` every ~1s while playing and on every change

## Plugs in as
`windows: [{ route: 'player', stage: { x: 960, y: 40, w: 620, h: 860 } }]` + a main feature that creates the BrowserWindow

## Done when
- Plays the step clip, stops at `end`, shows a calm "Waiting for your checks" state, resumes 400ms after `step.passed`
- Back (⌥←) and Show me (⌥S) work via the engine's `video.seek`
- Chapters list the steps as done / current / locked
- Reports `video.state`
- Works in the browser stage with the mock

## Test
`npm run dev:web -- --port 5182` → `http://localhost:5182/?scenario=full` (or `?scenario=player` once you add `mock/scenarios/player.json`)

## Adrian's spec
_TBD: Adrian fills this in._

## Core requests
_None yet._

## Notes
- YouTube embeds can fail inside Electron when the page has no http(s) origin (error 153). Dev serves the renderer from http://localhost, which is fine; for the packaged build plan a custom `app://` protocol or set the Referer for youtube.com with `session.webRequest`. Pass `origin` in the player vars.
- The mock uses videoId `PINN_TUTORIAL_TBD` until the third teammate picks the real tutorial; use any public video id locally.
- The player window must not steal focus from the user's editor (`showInactive`, focusable only while hovered).
