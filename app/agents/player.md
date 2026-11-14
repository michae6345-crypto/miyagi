# player

**Status:** v1 built (pass 1) · works in the browser stage · Electron window written + typechecked + builds, **not run** (Windows SAC) · **Priority:** P0 · **Port:** 5182 · **Branch:** `adrian/player`

### Pass 1: what works (checked in the stage, `?scenario=full`)
- **Gating:** on `step.started` it loads/cues the step's clip at `video.start` and plays. When playback reaches `video.end` while the step is open it pauses, snaps to `end` and shows a calm **"Waiting for your checks"** state (check dots, "2 of 3 pass", **Replay step**). Play is refused at the gate (the play button turns into a lock). Checked: stopped at 869.8s → 870.0, reported `{t: 870, playing: false}`.
- **Resume:** `step.passed` → a green "Passed" beat → plays again **~400ms** later (measured 403–408ms), unless the learner paused it. Into the next step's clip with no jump.
- **Engine intent:** `video.seek` / `video.pause` / `video.play` and card video jumps (`core/lesson.video`) are followed. **Back (⌥←)** at steps 4 and 6 → `video.seek` to the step start (`mock/scenarios/player.json`). **Show me (⌥S)** at step 6 seeks to 870 = the step's end: engine/card seeks past the gate are an "excursion" and play through.
- **`video.state {t, playing}`**: on every change and every ~1s while playing (seen on the wire).
- **Chapters:** the steps as done (green check) / current (moving bars while playing) / locked (lock, dimmed, not clickable). Click a done/current chapter to replay it. A chapter timeline under the video: one segment per step, played part filled, a ring at the open step's gate. Scrubbing never goes past the gate.
- **Stand-in video:** any video id that isn't a real 11-character YouTube id (the mock's placeholder, for instance) plays `STAND_IN_VIDEO_ID` (`features/player/youtube.ts`, 3Blue1Brown "But what is a neural network?", 18:40, so the mock's times fit). The panel says it's a stand-in. Nothing in the player is lesson-specific: titles, chapters, times and check labels all come from the engine's data (generality rule).
- **Rebased** onto the updated `adrian/shell` (launcher out of the notch, `tigerUrl`); re-checked in the stage afterwards (step 4 waits, resumes from 6:12 ~400ms after the pass).
- Screenshots: `agents/shots/player-stage.png` (whole stage, spotlight + caption over the player), `player-waiting.png`, `player-offtrack.png`, `player-passed.png` (the 400ms beat, staged by setting the state), `player-playing.png`. Close-ups hide the spotlight dim so the panel is readable; the real composite dims the player like Electron will.

### Left / next
- Electron: docking, header drag, bounds restore, no focus steal, autoplay, `player:intent` relay: all unverified (needs the Mac).
- The off-track card (centered under the pill, up to 520 wide) covers ~90px of the player's left edge in both the stage and Electron. Pass 2: dock a bit narrower, or shift cards.
- No volume/speed controls, no fullscreen; the YouTube iframe takes no clicks (everything goes through our controls so the gate can't be skipped).

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
`windows: [{ route: 'player', Component: PlayerWindow }]` (Electron) + `overlayLayers: [{ id: 'player', z: 5 }]` (**browser stage only**; renders nothing in Electron) + `src/main/features/player.ts` (creates the BrowserWindow).

Why not `stage: {…}`: the Stage paints every window **above** the whole overlay, so a player window at x ≥ 960 hid the right edge of the cards (and their ✕) and sat outside the spotlight dim. As a z 5 overlay layer it sits under the spotlight (10), drawer (40), island/cards (50) and shortcut bar (60), the same order as Electron (player window at 'floating', overlay at 'screen-saver'). Switch back once the Stage honors window `z` (Core request 1). Both use the same dock rect (`features/player/dock.ts`): right 40% of the work area, inset 8px, ending 112px above the bottom so the shortcut bar doesn't cover the chapters. Stage: x 968, y 40, 624×840.

## Done when
- Plays the step clip, stops at `end`, shows a calm "Waiting for your checks" state, resumes 400ms after `step.passed`
- Back (⌥←) and Show me (⌥S) work via the engine's `video.seek`
- Chapters list the steps as done / current / locked
- Reports `video.state`
- Works in the browser stage with the mock

## Test
`npm run dev:web -- --port 5182` → `http://localhost:5182/?scenario=full` (`?scenario=player` alone has only the Back triggers, no lesson). Ctrl+K → type anything → Enter → Enter. The player slides in on the right at step 4. Then: ⌥← Back (steps 4, 6), ⌥S Show me (4, 6), ⌥E Explain → the card's video jump, Apply fix at step 6. HUD Reset restarts.
In the mock, the engine sends `video.pause` right after every `step.started`, so you see the waiting state at once and the clip never runs to its end by itself. To watch the end-of-clip gate: press ⌥← (the clip plays to its end: 3.6 min at step 4, 1.8 min at step 6), or in the console at step 6: `__player.player.seek(866, true)` (stops at 870 four seconds later). `window.__player` exists only in dev.

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
1. **Stage z-order** (`dev/Stage.tsx`): render windows with `z < 0` before the `<Overlay>`, and make the stage's overlay root pass clicks through except over `[data-hit]` (as Electron's click-through does), so a window under the overlay stays clickable. Then the player goes back to `windows: [{ route: 'player', stage: dockRect, z: -1 }]` and drops its stage overlay layer. *Workaround in place:* the z 5 overlay layer above.
2. **Card video jumps don't cross windows in Electron.** Cards set `useLesson.video` in the overlay window; the player lives in its own window with its own store. *Workaround in place:* in any non-player window the player's store relays a direct (non-engine) change of `lesson.video` through `bridge.invoke('player:intent')` → main → `ctx.broadcast('player:intent')` → player window. Cleaner: a core `seekVideo(t, play)` in `core/lesson.ts` that sets the store and broadcasts to every window.
3. **Say what changed `lesson.video`.** `video.pause` / `video.play` keep the last seek's `t`, so a follower can't tell "seek to 372" from "pause" or from a card jump to the same `t`. *Workaround:* the player flags the last `video.*` message and decides on a microtask. Ask: add `kind: 'seek' | 'pause' | 'play' | 'jump'` to `lesson.video`.
4. **`overlay.bounds` should include the player window.** Otherwise the engine's screen reader reads the tutorial's code in the video as if it were the learner's editor. In the stage the panel is marked `data-ui`, so it's already reported there. In Electron, main knows the window's bounds: merge feature-window rects into the overlay's report (e.g. `ctx.reportBounds(win)`).
5. **Packaged build: YouTube error 153** (see Notes). Needs a core change in how windows load (`src/main/index.ts` `createWindow`).

## Notes
- **Electron + YouTube origin (error 153).** YouTube now refuses IFrame embeds whose page sends no http(s) Referer/origin and shows "Error 153: video player configuration error". `npm run dev` loads the renderer from `http://localhost:5173` (fine: the player passes `origin: location.origin`). The **packaged** app loads `file://…/index.html`, whose origin is opaque, so the embed fails, and postMessage between the IFrame API and our page can't target a `file://` origin either. Under `file://` the player omits `origin` and shows "YouTube refused the embed" if error 153 comes back. **Suggested core fix:** serve the renderer from a privileged custom scheme instead of `file://`:
  `protocol.registerSchemesAsPrivileged([{ scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true } }])` before `ready`, then `protocol.handle('app', (req) => net.fetch(pathToFileURL(join(__dirname, '../renderer', new URL(req.url).pathname)).toString()))` and `win.loadURL('app://tut/index.html#/<route>')`. `location.origin` becomes `app://tut`, which the player passes as `origin`. If YouTube still wants an http(s) referrer, also set one for its requests: `session.defaultSession.webRequest.onBeforeSendHeaders({ urls: ['https://www.youtube.com/*', 'https://*.youtube.com/*'] }, (d, cb) => cb({ requestHeaders: { ...d.requestHeaders, Referer: 'https://<our site>/' } }))`. Until then the demo should run with `npm run dev` (or `DEMO=1 npm run dev`), not the packaged `.app`.
- **YouTube quirks found (checked against the live player in the stage):** from a cued video, `playVideo()` ignores the cue's `startSeconds` and starts at 0, and `seekTo()` alone doesn't start playback; `seekTo(t)` then `playVideo()` plays from t. An empty player (no videoId) raises error 2 ("invalid id"), sometimes after our first cue, so error 2 only counts if no video shows up within 2.5s. Creating the player *with* a videoId and re-cueing on ready races YouTube's own first cue (the clip started at 0), so it's created empty.
- **Gate rules** (`features/player/store.ts`): stops within 0.15s of `end` (YouTube's time updates are ~250ms coarse); playing inside `[end, end + 3s)` while the step is open stops again. Engine/card seeks to or past the gate are allowed to play (Show me at step 6 seeks to its end, 14:30). Learner seeks (chapters, Replay, timeline) never pass the gate. `step.started` while already inside the new clip keeps playing (no jump).
- **Autoplay:** the Electron window sets `autoplayPolicy: 'no-user-gesture-required'`. In a browser, if playback hasn't started 1.5s after we asked, it retries muted and shows "Sound off · Unmute".
- **Clicks:** the iframe has `pointer-events: none`; a transparent button over it toggles play/pause through our controller, so the gate can't be skipped and YouTube's title/logo links can't open windows. Main also denies `window.open` (opens https links in the browser instead).
- **Focus:** created `focusable: false`, shown with `showInactive()` on `lesson.ready`, `setFocusable(true)` only while the pointer is over it (`player:hover`). Level `'floating'`: above normal windows, below the overlay. Bounds saved to `userData/player-bounds.json` on move/resize; restored only if they still land on a display; the header's dock button (`player:dock`) snaps back.
- `lesson.video.playing` is the engine's *intent*, not real playback. If a feature wants the real state (e.g. the off-track card's "Video paused" chip), read `usePlayer` from `features/player/store.ts` (read-only).
- The mock uses a placeholder video id until the third teammate picks the real tutorial; any real id from the engine is used as-is.
- **"Born from the notch island" rule:** the player isn't an island surface. It's the docked panel from Michael's handoff (right 40%, draggable, remembers its position), so it slides in from the right on `lesson.ready` in the stage and is shown in place in Electron. If Adrian wants it to grow out of the island too, that's a pass-2 call (in Electron it's a separate window, so it can't morph from the overlay's island; it could fade/scale in from its top edge).
- Dev server note: the desktop app caps dev servers per folder, and other sessions held all 5 slots, so this pass ran `npm run dev:web -- --port 5182 --strictPort` in the background and opened the URL directly.
