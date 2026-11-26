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
 *   4. Seek and pause intents are always followed (also unseen); play intents only while seen. An engine play intent
 *      (video.play, video.seek {play}) in a window's boot replay or an engine restore keeps its position but not its play.
 *   5. A replay of the lesson the player already holds (lesson.ready {replay}, same id) neither stops nor rewinds it:
 *      the step.started {replay} after it leaves a video inside its clip exactly as it is.
 *   6. Nothing plays to nobody (user test Nov 25: "the video keeps playing for no reason"): the screen locking or the
 *      Mac going to sleep pauses it as 'away'. Coming back never restarts it: the learner presses play. (Hiding or
 *      minimizing the panel is rule 1. A player merely covered by another window keeps playing: page visibility is not
 *      used, since the #287 layout can put windows over it.) A step's end still holds for its checks ('gate').
 *   7. The setup gate (setup.gate holds): the lesson's environment is still installing; the video waits as 'setup' and
 *      starts when the gate lets go, unless the screen locked or the Mac slept meanwhile (then the learner starts it).
 */

/** Who asked for playback. 'jump' = core seekVideo (a card's video link), in this window or relayed from another. */
export type PlayCause = 'learner' | 'step' | 'resume' | 'setup' | 'engine' | 'jump'

/**
 * Why the video is paused. 'gate' = we stopped at the step's end; 'engine' = video.pause; 'setup' = a setup card is
 * waiting (it starts once setup is done or skipped); 'hidden' = the panel isn't on screen (or was hidden while it
 * played); 'start' = cued for a replayed step, waiting for the learner's play; 'away' = the screen locked, the Mac slept
 * or the page went hidden (rule 6): only the learner starts it again.
 */
export type PausedBy = 'gate' | 'engine' | 'user' | 'ended' | 'setup' | 'hidden' | 'start' | 'away'

/** How long after a step's start its window may still show and start it (the reveal race). */
export const DEFER_MS = 2500
/** Engine messages a window gets this soon after it loads are the engine log's replay, not live steps. */
export const BOOT_QUIET_MS = 3000
/** Playing inside [end, end + GATE_ZONE_S) of the open step still counts as at its gate. */
export const GATE_ZONE_S = 3

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
 * May an engine video intent (video.play, or video.seek with play) start playback? Not while a window replays the engine
 * log it gets as it loads (the first BOOT_QUIET_MS: every video.seek and video.play since lesson.ready), and not during an
 * engine restore: both are stale intents nobody gave just now. Their seek position is still followed (rule 4, 5).
 */
export function engineIntentPlays(o: { sinceBootMs: number; restoring: boolean }): boolean {
  return !o.restoring && o.sinceBootMs >= BOOT_QUIET_MS
}

/**
 * lesson.ready: stop the last video and cue the new lesson's first clip? Not for a replay of the lesson the player already
 * holds (an engine reconnect or restore sends lesson.ready {replay} before step.started {replay}): stopping there would
 * pause the learner's video and rewind it to the first clip, and the step replay could not put it back (rule 5).
 */
export function lessonReadyResets(o: { replay?: boolean; sameLesson: boolean }): boolean {
  return !(o.replay === true && o.sameLesson)
}

/**
 * A replayed step.started: is the video already where this step wants it (same video, inside the step's clip or held
 * just past its end)? Then it stays exactly as it is, playing or paused. Otherwise the step's clip is cued.
 */
export function replayKeepsVideo(o: { sameVideo: boolean; t: number; start: number; end: number }): boolean {
  return o.sameVideo && o.t >= o.start - 1 && o.t < o.end + GATE_ZONE_S
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
  return o.pausedBy !== 'user' && o.pausedBy !== 'ended' && o.pausedBy !== 'hidden' && o.pausedBy !== 'start' && o.pausedBy !== 'away'
}

/** The panel shows the plain play glyph (not a gate state) for these. */
export const showsPlayGlyph = (pausedBy?: PausedBy): boolean =>
  pausedBy === 'user' || pausedBy === 'hidden' || pausedBy === 'start' || pausedBy === 'away'

/** Why nobody can watch right now (rule 6). */
export type AwaySignal = 'lock' | 'sleep'

/**
 * Rule 6: an away signal arrived. 'pause' when the video plays (or is about to: a deferred or wanted play), else
 * 'ignore'. Never 'resume': a return (unlock, wake, page visible) is not a play.
 */
export function onAway(o: { playing: boolean; wantPlay: boolean; signal: AwaySignal }): 'pause' | 'ignore' {
  return o.playing || o.wantPlay ? 'pause' : 'ignore'
}

/**
 * Rule 7 plus the setup card: does setup hold the video? A setup card waiting on the learner (cards/setupHold.ts) or
 * the setup gate holding (an install for this lesson is running, or failed and not waved through).
 */
export function setupHolds(o: { cardWaiting: boolean; gateHolds: boolean }): boolean {
  return o.cardWaiting || o.gateHolds
}

/**
 * Rule 7: setup let go. Start the clip only if setup is still why it's paused and nobody went away during the hold
 * (a lock or sleep while it installed: the learner may not be back, so they press play).
 */
export function releasePlays(o: { pausedBy?: PausedBy; awayDuringHold: boolean }): boolean {
  return o.pausedBy === 'setup' && !o.awayDuringHold
}
