# video-quiet

**Status:** built, typechecked, unit-tested (policy.test.ts, 19 pass). **Not run** in Electron or the stage: offline-only lane, no video playback allowed. **Branch:** `michael/app-video-quiet` (from `michael/v2-integration` 5f04f998).

Michael, Nov 21: "Videos play in the background, with audio, when the video is not even open."

## Root cause (lines are on `origin/michael/v2-integration` 5f04f998)

The player had no idea whether it was on screen, and every step start rolled the video with sound.

1. **The player window plays while hidden.** `src/main/features/player.ts:64` creates it `show: false` with `autoplayPolicy: 'no-user-gesture-required'` (`:77`), and it lives for the whole app. Main hides it on End, on a "Just teach me" lesson (`:131`) and on `player:hide`, but the renderer never heard about it. Electron reports `document.visibilityState === 'visible'` for a window created with `show: false`, so the page couldn't tell on its own either.
2. **Every `step.started` autoplays, replays included.** `features/player/store.ts:557` `go(seg.videoId, start, !setupHold)`. Main replays its whole engine log into every window that loads (`src/main/index.ts:441`, on `ui:ready`), and the engine sends a snapshot on each connect or restore. So launching miyagi with a kept lesson, or an engine reconnect, started the video out loud, even when the learner had paused it.
3. **Play intents ran in a window not showing the player.** `store.ts:582` (`video.play`) and the `jump` seek with `playing: true` (`:583`, fed by core `seekVideo` through the relay at `src/main/index.ts:447`) played with no visibility check. Same for the pass resume (`:571`), the end of setup (`:633`) and the muted autoplay fallback (`:294`).
4. **Switching lessons didn't stop the old video.** `store.ts:528` (`lesson.ready`) only cued the new first clip. A "Just teach me" lesson has none, so the last clip played on in the window main had just hidden.
5. **Two players could exist.** `attachPlayer` (`store.ts:375`) kept one module-level `yt` with no owner: a second attach (the stage's exit animation overlapping a new panel) left the first iframe playing, and the old cleanup cleared the new one's timers. The cleanup (`:420`) also kept `want.play`, so the next player's `onReady` (`:407`) started playing on its own.

## Fix

- **`features/player/policy.ts`** (pure rules, tested in `policy.test.ts`):
  - `panelVisible`: Electron trusts main's word about the window; the stage follows the page.
  - `decidePlay`: every play needs the panel on screen. A live step that lands just before its window shows is deferred; anything else is refused.
  - `stepStartPlays`: only a live step rolls the video. These only cue: `step.started.replay`, an `engine.hello {restored}` (or `lesson.ready {replay}`) within 8 s, the first 3 s of an Electron window's life (the log replay), and a waiting setup card.
  - `startDeferred`: once the window shows, a deferred step starts if it's the same step, still paused as `hidden`, and within 2.5 s.
  - `resumesAfterPass`: never resumes what the learner paused, the lesson end, a hidden panel, or a replayed step nobody started.
- **`features/player/store.ts`:** `admit(cause)` gates `go()` and `setPlay()`. If refused, the video pauses as `hidden`. Hiding the window pauses it (`hideStop`), and so do the tick and `onStateChange` safety nets: nothing rolls unseen, whatever started it. Showing the window starts only a deferred live step; anything else waits for the learner's ▶. A replayed step leaves a video already inside its clip as it is; otherwise it cues and shows the play glyph (`pausedBy: 'start'`). `lesson.ready` pauses the last video first. `attachPlayer` is single-instance and host-only, and a torn-down player drops its pending play. Seek and pause intents are still followed while hidden.
- **`src/main/features/player.ts`** (the player feature's own main file): broadcasts `feat:player:visible` on show, hide, minimize and restore, and again a beat after a reveal. It also answers `player:visible`.
- **`Player.tsx`:** `hidden` and `start` show the plain play glyph (`showsPlayGlyph`). No new copy.

## Checks

- `npm run typecheck`: pass.
- `npx tsx --test src/renderer/src/features/player/policy.test.ts`: 19 pass, 0 fail. The repo has no vitest; `node:test` runs offline through tsx.
- Brand lint on the changed lines: no hex, no em dashes, no banned words, no `dangerouslySetInnerHTML`, no new copy.

## Core request (optional, not needed for the fix)

- `src/main/index.ts:447` relays `video:intent` to every other window. Only the player window hosts a player, so main could send it to the player route alone. The renderer already ignores play intents while hidden and in non-host windows, so this is tidiness, not a fix.
- The boot replay rule (3 s) stands in for a missing flag. If main marked its `ui:ready` log replay (e.g. `{replayed: true}` on each event, or a `ui:replay-done` signal), the player could drop the timer.

## Open

- Unverified in Electron: whether macOS fires `show` for `showInactive()`. The 300 ms and 1200 ms re-tells after `reveal()` cover it either way.
- The engine half of "don't resume the last lesson on launch" is `claude/eng-no-auto-resume`. This lane only makes sure a resumed lesson never starts the video by itself.
