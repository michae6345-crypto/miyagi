/**
 * When the video may make sound (Michael, Nov 21: "Videos play in the background, with audio, when the video is not
 * even open"). Pure rules, no player, no DOM: store.ts asks these before it starts playback. Tests: policy.test.ts.
 *
 *   1. Nothing plays unseen. A play starts only while the player panel is on screen (Electron: main says the player
 *      window is shown; browser stage: the page is visible). Hiding it pauses.
 *   2. Only a live step rolls the video by itself. A replayed step (a reconnect, an engine restore, the engine log a
 *      window gets when it loads) cues its clip and waits for the learner's play.
 *   3. A live step that starts a moment before its window is shown (lesson.ready reveals the window while step.started
 *      is already on the wire) plays once the window shows, if that happens within DEFER_MS. Later, the learner presses
 *      play.
 *   4. Seek and pause intents are always followed (also unseen); play intents only while seen.
 */

/** Who asked for playback. */
export type PlayCause = 'learner' | 'step' | 'resume' | 'setup' | 'engine' | 'jump'

/**
 * Why the video is paused. 'gate' = we stopped at the step's end; 'engine' = video.pause; 'setup' = a setup card is
 * waiting (it starts once setup is done or skipped); 'hidden' = the panel isn't on screen (or was hidden while it
 * played); 'start' = cued for a replayed step, waiting for the learner's play.
 */
export type PausedBy = 'gate' | 'engine' | 'user' | 'ended' | 'setup' | 'hidden' | 'start'

/** How long after a step's start its window may still show and start it (the reveal race). */
export const DEFER_MS = 2500
/** Engine messages a window gets this soon after it loads are the engine log's replay, not live steps. */
export const BOOT_QUIET_MS = 3000

/** Is the player panel on screen? Electron: main's word about the player window. Browser stage: the page. */
export function panelVisible(o: { electron: boolean; windowShown: boolean; pageVisible: boolean }): boolean {
  return o.electron ? o.windowShown : o.pageVisible
}

/**
 * May this step.started roll the video by itself? Only a live step: not a replay (step.started.replay, an engine
 * restore announced by engine.hello.restored, or the log replay a window gets in its first BOOT_QUIET_MS), and not
 * while a setup card waits (that starts it later).
 */
export function stepStartPlays(o: { replay?: boolean; restoring: boolean; sinceBootMs: number; setupHold: boolean }): boolean {
  if (o.setupHold) return false
  if (o.replay || o.restoring) return false
  return o.sinceBootMs >= BOOT_QUIET_MS
}

/**
 * A play request: 'play' now, 'defer' (a live step whose window isn't shown yet: rule 3), or 'refuse' (stay paused,
 * as 'hidden'). Every cause needs the panel on screen.
 */
export function decidePlay(o: { visible: boolean; cause: PlayCause }): 'play' | 'defer' | 'refuse' {
  if (o.visible) return 'play'
  return o.cause === 'step' ? 'defer' : 'refuse'
}

/** The window just showed: start the deferred step now? Same step, still held only because it was hidden, in time. */
export function startDeferred(o: { deferredAt?: number; now: number; sameStep: boolean; pausedBy?: PausedBy }): boolean {
  if (o.deferredAt === undefined || !o.sameStep || o.pausedBy !== 'hidden') return false
  return o.now - o.deferredAt <= DEFER_MS
}

/**
 * step.passed's resume after the "Passed" beat: only if nothing chose to keep it paused. The learner's pause, the
 * lesson's end, a hidden panel, a replayed step the learner never started, and a waiting setup card all win.
 */
export function resumesAfterPass(o: { playing: boolean; pausedBy?: PausedBy; setupHold: boolean; pending?: boolean }): boolean {
  if (o.pending || o.playing || o.setupHold) return false
  return o.pausedBy !== 'user' && o.pausedBy !== 'ended' && o.pausedBy !== 'hidden' && o.pausedBy !== 'start'
}

/** The panel shows the plain play glyph (not a gate state) for these. */
export const showsPlayGlyph = (pausedBy?: PausedBy): boolean => pausedBy === 'user' || pausedBy === 'hidden' || pausedBy === 'start'
