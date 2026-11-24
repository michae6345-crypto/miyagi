/**
 * Player state + the controller around the YouTube player. Pure module state, no React:
 * the Video component only lends it a DOM node (attachPlayer).
 *
 * Gating:
 *   step.started  → load/cue the step's clip at video.start (after a skipped intro) and play
 *   t ≥ video.end → while the step isn't passed: pause at end ("Waiting for your checks")
 *   step.passed   → a 400ms "Passed" beat, then resume (unless the learner paused it themself)
 *   step.passed {pending} → the next part of a long video is still building: no resume; the video
 *                   holds at the end of the passed clip ("Next part is still building") until the
 *                   engine starts the next step (after lesson.updated)
 * Engine intent (core/lesson.video, with `kind`: video.seek / video.pause / video.play, and 'jump'
 *   from core seekVideo, e.g. a card's video link): followed as-is. A seek past the gate is allowed
 *   (the engine asked for it); the gate only stops playback that runs into the end of the open step.
 * Reports video.state {t, playing} every second while playing and on every change.
 *
 * Electron: this module runs in every window (features are imported everywhere), but only the
 * player window hosts the YouTube player. core seekVideo reaches it through main (video:intent).
 * R33: the player itself lives in a framed host page on its own origin (frame.ts); this page never loads YouTube's API.
 *
 * Never unseen (policy.ts, Michael Nov 21): every play goes through admit(), which refuses it while the panel isn't on
 * screen (main's player:visible in Electron; the page's visibility on the stage). Hiding pauses. A replayed step cues its
 * clip without playing. A replay of the lesson already held neither stops nor rewinds it. An engine play intent in a window's
 * boot replay or an engine restore keeps its seek, not its play. One YouTube player at a time (attachPlayer tears down
 * the one before).
 */
import { create } from 'zustand'
import type { VideoSegment } from '../../../../../../shared/contracts/events'
import { cmd, type Payload } from '../../../../common/wire'
import { bridge, isElectron, registerWebHandler } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { useCards } from '../cards/store'
import { setupWaiting } from '../cards/setupHold'
import { decidePlay, engineIntentPlays, GATE_ZONE_S, lessonReadyResets, panelVisible, replayKeepsVideo, resumesAfterPass, startDeferred, stepStartPlays, type PausedBy, type PlayCause } from './policy'
import { FramePlayer } from './frame'
import { describeYTError, isYouTubeId, resolveVideoId, YTState, type YTPlayer } from './youtube'

export type { PausedBy } from './policy'

type PlayerState = {
  /** The YouTube player exists and answered onReady. */
  ready: boolean
  videoId?: string
  /** True when the lesson's video id isn't a real YouTube id and we play the stand-in. */
  standIn: boolean
  title?: string
  t: number
  duration: number
  /** Playing or buffering. */
  playing: boolean
  pausedBy?: PausedBy
  /** step.passed just landed: the 400ms "Passed" beat before the video resumes. */
  resuming: boolean
  /** Autoplay with sound was blocked, so we play muted until the learner unmutes. */
  muted: boolean
  /** The learner's volume, 0-100 (saved). */
  volume: number
  /** The learner's playback speed (saved): 0.75x to 2x, for learners who want to go fast (Michael, Nov 15). */
  rate: number
  error?: string
}

/** The speed chip cycles through these. */
export const RATES = [1, 1.25, 1.5, 2, 0.75] as const
export const PREF_KEY = 'miyagi.player.prefs'
function savedPrefs(): { volume: number; rate: number } {
  try {
    const v = JSON.parse(localStorage.getItem(PREF_KEY) ?? '{}') as { volume?: unknown; rate?: unknown }
    const volume = typeof v.volume === 'number' && v.volume >= 0 && v.volume <= 100 ? Math.round(v.volume) : 100
    const rate = typeof v.rate === 'number' && (RATES as readonly number[]).includes(v.rate) ? v.rate : 1
    return { volume, rate }
  } catch {
    return { volume: 100, rate: 1 }
  }
}
function savePrefs(): void {
  const { volume, rate } = usePlayer.getState()
  try {
    localStorage.setItem(PREF_KEY, JSON.stringify({ volume, rate }))
  } catch {
    // storage unavailable: the settings hold for this session only
  }
}
const prefs = savedPrefs()

const blank: PlayerState = {
  ready: false,
  videoId: undefined,
  standIn: false,
  title: undefined,
  t: 0,
  duration: 0,
  playing: false,
  pausedBy: undefined,
  resuming: false,
  muted: false,
  volume: prefs.volume,
  rate: prefs.rate,
  error: undefined
}

export const usePlayer = create<PlayerState>(() => ({ ...blank }))
const setUi = usePlayer.setState

export const RESUME_DELAY_MS = 400
/** Stop this close to the end: YouTube's time updates are ~250ms coarse. */
const GATE_EPS = 0.15
/** Playing inside [end, end + 3s) while the step is still open stops again (so ▶ at the gate can't sneak past). */
const GATE_ZONE = GATE_ZONE_S
const TICK_MS = 100
const REPORT_MS = 1000
const AUTOPLAY_GRACE_MS = 1500
/** Shown under "The video didn’t load" (Player.tsx ErrorState, with Try again): calm, no jargon (QA Q12). */
const LOAD_ERROR = 'Check your connection, then try again.'

/** Electron loads index.html#/player for the player window; the browser stage is one window that hosts everything. */
const route = location.hash.replace(/^#\/?/, '')
export const isHost = !isElectron || route === 'player'

// ---------------------------------------------------------------------------
// On screen? (policy.ts rule 1)
// ---------------------------------------------------------------------------

/**
 * Electron: what main last said about the player window (player:visible). Starts false: a window created hidden reports
 * document.visibilityState 'visible' anyway, so the page can't tell. The browser stage: the page's own visibility.
 */
let windowShown = false
const pageVisible = (): boolean => typeof document === 'undefined' || document.visibilityState !== 'hidden'
const visibleNow = (): boolean => panelVisible({ electron: isElectron, windowShown, pageVisible: pageVisible() })

/** A live step's play that arrived while the window wasn't shown yet (policy.ts rule 3). */
let deferred: { stepId?: string; at: number } | undefined
/**
 * engine.hello {restored} (or a lesson.ready {replay}): the step.started that follows is the restored lesson's, not a
 * live start (policy.ts rule 2). Until that step.started, a lesson.ended, or RESTORE_WINDOW_MS, whichever comes first.
 */
let restoringUntil = 0
const RESTORE_WINDOW_MS = 8000
const restoring = (): boolean => performance.now() < restoringUntil
/**
 * How long this window has been up, for the boot replay rule. Electron only: main replays its engine log into every window
 * that loads (index.ts ui:ready). The browser stage's mock starts a lesson right away, live.
 */
const sinceBoot = (): number => (isElectron ? performance.now() : Number.POSITIVE_INFINITY)
/**
 * The lesson the player last cued (lesson.ready's id), so a lesson.ready {replay} of the same lesson leaves the video
 * alone (policy.ts rule 5). Kept across a reconnect's reset (that lesson may come back); cleared by a real end.
 */
let heldLesson: string | undefined

// ---------------------------------------------------------------------------
// Lesson helpers
// ---------------------------------------------------------------------------

/** The current step's clip, if the step is still open (not passed). */
export function openSegment(): VideoSegment | undefined {
  const s = useLesson.getState()
  if (!s.stepId || s.passed.includes(s.stepId)) return undefined
  return s.stepVideo ?? s.steps.find((x) => x.id === s.stepId)?.video ?? undefined
}

function currentSegment(): VideoSegment | undefined {
  const s = useLesson.getState()
  return s.stepVideo ?? s.steps.find((x) => x.id === s.stepId)?.video ?? undefined
}

/**
 * Where playback must hold, if anywhere:
 *   'checks'   the open step's end (its checks haven't passed yet)
 *   'building' the passed step's end, while the next part of a long video is still building (pendingNext)
 */
export function holdPoint(): { end: number; why: 'checks' | 'building' } | undefined {
  const s = useLesson.getState()
  const seg = currentSegment()
  if (!s.stepId || !seg) return undefined
  if (!s.passed.includes(s.stepId)) return { end: seg.end, why: 'checks' }
  if (s.pendingNext) return { end: seg.end, why: 'building' }
  return undefined
}

/**
 * The engine (or a card's video jump) sent us to/after the open step's end on purpose, e.g. Show me
 * at step 6 seeks to 14:30 where the tutorial shows the fix. The gate stands aside until the step
 * changes or the learner goes back into the clip.
 */
let excursion = false

/** Is time t at (or just past) the hold point, with the gate holding? */
export function inGate(t: number): boolean {
  const h = holdPoint()
  return !excursion && !!h && t >= h.end - GATE_EPS && t < h.end + GATE_ZONE
}

/** Engine/card seeks: past the gate = an excursion. Learner seeks (chapters, replay, timeline) never are. */
function setExcursion(t: number, fromEngine: boolean): void {
  const h = holdPoint()
  excursion = fromEngine && !!h && t >= h.end - GATE_EPS
}

/**
 * The preflight card's buildPlan.skippedIntro: a talk-only intro the build skipped. A clip that starts
 * inside it (chapter 1, usually) starts at its end instead. Only for the same video.
 */
let skippedIntro: { videoId?: string; start: number; end: number } | undefined

/** Where a step's clip really starts: after a skipped intro, if it starts inside one. */
export function clipStart(seg: VideoSegment): number {
  const k = skippedIntro
  if (!k || (k.videoId && resolveVideoId(k.videoId) !== resolveVideoId(seg.videoId))) return seg.start
  return seg.start >= k.start && seg.start < k.end && seg.end > k.end ? k.end : seg.start
}

// ---------------------------------------------------------------------------
// Controller
// ---------------------------------------------------------------------------

let yt: YTPlayer | undefined
let ready = false
let loadedId: string | undefined
/** What we want the player to do; applied when it's ready. */
let want: { videoId?: string; t: number; play: boolean } = { t: 0, play: false }
let tickTimer: ReturnType<typeof setInterval> | undefined
let reportTimer: ReturnType<typeof setInterval> | undefined
let autoplayTimer: ReturnType<typeof setTimeout> | undefined
let resumeTimer: ReturnType<typeof setTimeout> | undefined
let lastReport = ''
/** When we last asked for a video (load/cue) and when YouTube last showed one (cued/playing/paused). */
let requestedAt = 0
let goodAt = 0

const state = (): number => (yt && ready ? yt.getPlayerState() : YTState.UNSTARTED)
const isRolling = (st: number): boolean => st === YTState.PLAYING || st === YTState.BUFFERING
const notStarted = (st: number): boolean => st === YTState.CUED || st === YTState.UNSTARTED

/** Current position. A cued video reports 0, so fall back to where we cued it. */
function now(): number {
  if (!yt || !ready || notStarted(state())) return want.t
  const ct = yt.getCurrentTime()
  return Number.isFinite(ct) ? ct : want.t
}

function sync(changed = false): void {
  const st = state()
  setUi({
    ready,
    t: now(),
    duration: yt && ready ? yt.getDuration() || 0 : 0,
    // Buffering after we asked for a pause (a seek, then video.pause) is not "playing" for the UI or the engine.
    playing: st === YTState.PLAYING || (st === YTState.BUFFERING && want.play),
    videoId: want.videoId,
    title: (yt && ready && yt.getVideoData?.()?.title) || usePlayer.getState().title
  })
  if (changed) report()
}

/** video.state {t, playing}: on every change, and every second while playing (deduped). */
function report(periodic = false): void {
  if (!isHost || !yt || !ready) return
  const s = usePlayer.getState()
  const payload = { t: Math.round(s.t * 10) / 10, playing: s.playing }
  const key = `${payload.t}|${payload.playing}`
  if (key === lastReport && !periodic) return
  if (periodic && !payload.playing) return
  lastReport = key
  bridge.send(cmd('video.state', payload))
}

/**
 * Every play starts here: refused (paused as 'hidden') while the panel isn't on screen. A live step's play is deferred
 * for a moment instead (its window is being revealed).
 */
function admit(cause: PlayCause): boolean {
  const d = decidePlay({ visible: visibleNow(), cause })
  if (d === 'play') {
    deferred = undefined
    return true
  }
  deferred = d === 'defer' ? { stepId: useLesson.getState().stepId, at: performance.now() } : undefined
  clearTimeout(resumeTimer)
  setUi({ pausedBy: 'hidden', resuming: false })
  return false
}

/** Load the video if needed, go to t, then play or stay paused. */
function go(videoId: string | undefined, t: number, play: boolean, cause: PlayCause = 'learner'): void {
  if (play && !admit(cause)) play = false
  const id = resolveVideoId(videoId ?? want.videoId)
  want = { videoId: id, t, play }
  if (videoId !== undefined) setUi({ standIn: !isYouTubeId(videoId), error: undefined })
  if (!play) clearTimeout(autoplayTimer)
  if (!yt || !ready) return sync()
  if (id !== loadedId) {
    loadedId = id
    requestedAt = performance.now()
    if (play) yt.loadVideoById({ videoId: id, startSeconds: t })
    else yt.cueVideoById({ videoId: id, startSeconds: t })
  } else {
    // If seekTo starts a cued video anyway, onStateChange pauses it again (want.play is false).
    yt.seekTo(t, true)
    if (play) yt.playVideo()
    else yt.pauseVideo()
  }
  if (play) watchAutoplay()
  sync(true)
}

/**
 * Start playback at want.t. Checked against the live player: from a cued/unstarted video,
 * playVideo() alone ignores the cue position and starts at 0, and seekTo() alone doesn't start it.
 * seekTo(t) then playVideo() plays from t.
 */
function startFromWant(): void {
  if (!yt) return
  if (notStarted(state())) yt.seekTo(want.t, true)
  yt.playVideo()
}

function setPlay(play: boolean, cause: PlayCause = 'learner'): void {
  if (play && !admit(cause)) play = false
  want = { ...want, t: now(), play }
  if (!yt || !ready) return sync()
  if (play) {
    if (state() === YTState.ENDED) return sync()
    startFromWant()
    watchAutoplay()
  } else {
    clearTimeout(autoplayTimer)
    yt.pauseVideo()
  }
  sync(true)
}

/** The learner's volume and speed onto the YouTube player (on ready, and each time playback starts: a new clip can reset the rate). */
function applyPrefs(): void {
  if (!yt || !ready) return
  const { volume, rate } = usePlayer.getState()
  try {
    yt.setVolume(volume)
    if (yt.getPlaybackRate() !== rate) yt.setPlaybackRate(rate)
  } catch {
    // an older player without these calls: leave YouTube's defaults
  }
}

/** Browsers block autoplay with sound without a user gesture: fall back to muted playback. */
function watchAutoplay(): void {
  clearTimeout(autoplayTimer)
  autoplayTimer = setTimeout(() => {
    if (!yt || !ready || !want.play || isRolling(state())) return
    if (!visibleNow()) return hideStop()
    yt.mute()
    startFromWant()
    setUi({ muted: true })
  }, AUTOPLAY_GRACE_MS)
}

/** Stop at the open step's end and wait for its checks. */
function gate(end: number): void {
  if (!yt) return
  want = { ...want, t: end, play: false }
  clearTimeout(autoplayTimer)
  yt.pauseVideo()
  yt.seekTo(end, true)
  setUi({ pausedBy: 'gate' })
  sync(true)
}

/**
 * Where the lesson's video ends for us: the last step's clip end (Michael's desktop test 12). Past it YouTube shows its
 * end screen with a suggested video, which invites the learner to leave. Only once the last step is the current one.
 */
function lessonEnd(): number | undefined {
  const s = useLesson.getState()
  const withVideo = s.steps.filter((x) => x.video)
  const last = withVideo[withVideo.length - 1]
  if (!last?.video || s.stepId !== last.id) return undefined
  if (resolveVideoId(last.video.videoId) !== loadedId) return undefined
  return last.video.end
}

/** Stop at the lesson's end, before YouTube's end screen: paused like 'ended'. */
function stopAtEnd(end: number): void {
  if (!yt) return
  want = { ...want, t: end, play: false }
  clearTimeout(autoplayTimer)
  yt.pauseVideo()
  setUi({ pausedBy: 'ended' })
  sync(true)
}

/** The panel left the screen while the video played (or was about to): pause it, as 'hidden'. */
function hideStop(): void {
  deferred = undefined
  want = { ...want, t: now(), play: false }
  clearTimeout(autoplayTimer)
  clearTimeout(resumeTimer)
  if (yt && ready) yt.pauseVideo()
  setUi({ pausedBy: 'hidden', resuming: false })
  sync(true)
}

function tick(): void {
  if (!yt || !ready) return
  // Belt and braces: whatever started it, nothing rolls while the panel is off screen.
  if (isRolling(state()) && !visibleNow()) return hideStop()
  const t = now()
  const h = holdPoint()
  if (h && isRolling(state()) && inGate(t)) return gate(h.end)
  const e = h ? undefined : lessonEnd()
  if (e !== undefined && !excursion && isRolling(state()) && t >= e - GATE_EPS && t < e + GATE_ZONE) return stopAtEnd(e)
  const s = usePlayer.getState()
  if (Math.abs(s.t - t) > 0.04 || !s.duration) sync()
}

/**
 * The empty player raises error 2 ("invalid id"), sometimes after our first cue. So error 2 only
 * counts if no video showed up since we asked for one, 2.5s later. Other errors show at once.
 */
function onError(code: number): void {
  if (code !== 2) return setUi({ error: describeYTError(code) })
  if (requestedAt && goodAt >= requestedAt) return
  setTimeout(() => {
    if (yt && ready && requestedAt && goodAt < requestedAt) setUi({ error: describeYTError(code) })
  }, 2500)
}

function onStateChange(st: number): void {
  if (!yt) return
  if (isRolling(st) || st === YTState.CUED || st === YTState.PAUSED) {
    goodAt = performance.now()
    if (usePlayer.getState().error) setUi({ error: undefined })
  }
  // Our intent wins: seekTo on a cued video starts playback even when we wanted it paused.
  if (st === YTState.PLAYING && !want.play) return yt.pauseVideo()
  // And it never plays unseen (YouTube's own autoplay after a load included).
  if (st === YTState.PLAYING && !visibleNow()) return hideStop()
  if (isRolling(st)) clearTimeout(autoplayTimer)
  if (st === YTState.PLAYING) applyPrefs()
  if (st === YTState.ENDED) {
    want = { ...want, play: false }
    setUi({ pausedBy: holdPoint() ? 'gate' : 'ended' })
  }
  sync(true)
}

/** The live attachment's teardown: a second Video (a remount, the stage's exit animation) replaces the first. */
let releaseCurrent: (() => void) | undefined

/**
 * The Video component lends a DOM node; returns the cleanup. One YouTube player at a time: attaching tears down the one
 * before, so two can never make sound together. Only the host window (the player window; the stage) gets one.
 */
export function attachPlayer(host: HTMLElement): () => void {
  if (!isHost) return () => undefined
  releaseCurrent?.()
  let dead = false
  let destroy = (): void => {}
  const mount = document.createElement('div')
  mount.style.cssText = 'width:100%;height:100%'
  host.appendChild(mount)
  const inner = document.createElement('div')
  inner.style.cssText = 'width:100%;height:100%'
  mount.appendChild(inner)

  // R33: YouTube's API runs in the host page, framed from its own origin (frame.ts), never in this page with the bridge.
  // The host makes the quiet embed (Michael's desktop test 9: no controls, rel 0, no cards, no keyboard, no fullscreen).
  // A paused embed still draws its title bar and "More videos" strip: the panel's gate states cover the frame
  // (Player.tsx GlassScrim cover).
  bridge
    .invoke<string | undefined>('player:host')
    .then((url) => {
      if (dead) return
      if (!url) throw new Error(LOAD_ERROR)
      // Created empty, then everything goes through go(). (Creating it with a videoId and re-cueing
      // on ready races YouTube's own first cue: the clip then starts at 0 instead of the step start.)
      const player = new FramePlayer(inner, url, {
        onReady: () => {
          if (dead) return
          yt = player
          ready = true
          applyPrefs()
          loadedId = undefined
          if (want.videoId) go(want.videoId, want.t, want.play)
          else sync()
        },
        onStateChange: (st) => !dead && onStateChange(st),
        onError: (code) => !dead && onError(code),
        onFail: () => !dead && setUi({ error: LOAD_ERROR })
      })
      destroy = () => player.destroy() // even before onReady
      tickTimer = setInterval(tick, TICK_MS)
      reportTimer = setInterval(() => report(true), REPORT_MS)
    })
    .catch(() => !dead && setUi({ error: LOAD_ERROR }))

  const release = (): void => {
    if (dead) return
    dead = true
    if (releaseCurrent === release) releaseCurrent = undefined
    clearInterval(tickTimer)
    clearInterval(reportTimer)
    clearTimeout(autoplayTimer)
    try {
      destroy()
    } catch {
      /* already gone */
    }
    yt = undefined
    ready = false
    loadedId = undefined
    // Gone with its panel: a later player starts paused, never with this one's "play".
    want = { ...want, play: false }
    deferred = undefined
    mount.remove()
    setUi({ ready: false, playing: false })
  }
  releaseCurrent = release
  return release
}

// ---------------------------------------------------------------------------
// Commands (UI + engine)
// ---------------------------------------------------------------------------

export const player = {
  /**
   * Seek and play/pause. `by` says who paused it when play is false.
   * `fromEngine`: video.seek or a card's video jump (may take the video past the gate on purpose).
   * `cause`: who asked for the play ('jump' for a card's video jump; default 'engine' when fromEngine, else 'learner').
   */
  seek(t: number, play: boolean, by: PausedBy = 'user', fromEngine = false, cause?: PlayCause): void {
    clearTimeout(resumeTimer)
    setExcursion(t, fromEngine)
    setUi({ resuming: false, pausedBy: play ? undefined : by })
    go(undefined, t, play, cause ?? (fromEngine ? 'engine' : 'learner'))
  },
  /** Returns false when the open step's gate holds the video, or the panel isn't on screen. */
  play(cause: PlayCause = 'learner'): boolean {
    if (inGate(now())) return false
    setUi({ pausedBy: undefined })
    setPlay(true, cause)
    return want.play
  },
  pause(by: PausedBy = 'user'): void {
    setUi({ pausedBy: by })
    setPlay(false)
  },
  toggle(): void {
    if (usePlayer.getState().playing) player.pause('user')
    else player.play()
  },
  /** Back to the start of the current step's clip. */
  replayStep(): void {
    const seg = currentSegment()
    if (seg) player.seek(clipStart(seg), true)
  },
  unmute(): void {
    yt?.unMute()
    setUi({ muted: false })
  },
  /** The volume slider: 0 mutes, anything above unmutes. Saved for the next lesson. */
  setVolume(v: number): void {
    const volume = Math.max(0, Math.min(100, Math.round(v)))
    setUi({ volume, muted: volume === 0 })
    if (yt && ready) {
      yt.setVolume(volume)
      if (volume === 0) yt.mute()
      else yt.unMute()
    }
    savePrefs()
  },
  /** The speaker button: mute, or back to the last volume (at least a little, so it's audible). */
  toggleMute(): void {
    const s = usePlayer.getState()
    if (s.muted || s.volume === 0) {
      const volume = s.volume || 60
      yt?.unMute()
      yt?.setVolume(volume)
      setUi({ muted: false, volume })
      savePrefs()
    } else {
      yt?.mute()
      setUi({ muted: true })
    }
  },
  /** The speed chip: the next rate in RATES. Saved for the next lesson. */
  cycleRate(): void {
    const cur = usePlayer.getState().rate
    const i = (RATES as readonly number[]).indexOf(cur)
    const rate = RATES[(i + 1) % RATES.length]
    setUi({ rate })
    try {
      yt?.setPlaybackRate(rate)
    } catch {
      // not supported: the chip still shows the choice, applied on the next play
    }
    savePrefs()
  },
  /** Seek from the timeline: never past the open step's gate. */
  scrub(t: number): void {
    const h = holdPoint()
    const target = h ? Math.min(t, h.end) : t
    const keepPlaying = usePlayer.getState().playing && !inGate(target)
    player.seek(target, keepPlaying, h && target >= h.end - GATE_EPS ? 'gate' : 'user')
  }
}

// ---------------------------------------------------------------------------
// Engine + UI events
// ---------------------------------------------------------------------------

onMessage('lesson.ready', (p) => {
  if (p.replay === true) restoringUntil = performance.now() + RESTORE_WINDOW_MS
  // A replay of the lesson this player holds (a reconnect, an engine restore): no stop, no rewind to the first clip. The
  // step.started {replay} after it decides (it leaves a video inside its step's clip as it is). core/lesson's gate
  // usually drops such a lesson.ready before it gets here; this covers the reconnect whose snapshot came after the hold.
  const sameLesson = !!heldLesson && heldLesson === p.lesson.id
  heldLesson = p.lesson.id
  if (!lessonReadyResets({ replay: p.replay, sameLesson })) return
  clearTimeout(resumeTimer)
  // A new lesson stops the last one's video first: a "Just teach me" lesson has no clip to cue, and its window hides.
  deferred = undefined
  want = { ...want, play: false }
  clearTimeout(autoplayTimer)
  if (yt && ready) yt.pauseVideo()
  // Cue the first clip so the player is warm when the first step starts (go() sets standIn).
  const first = p.steps.find((s) => s.video)?.video
  setUi({ pausedBy: undefined, resuming: false, error: undefined, title: undefined, ...(first ? {} : { standIn: false }) })
  if (first) go(first.videoId, clipStart(first), false)
})

// The preflight card (before the build) says whether part 1 skips a talk-only intro.
onMessage('card', (p) => {
  if (p.kind !== 'preflight' || !p.preflight) return
  const k = p.preflight.buildPlan?.skippedIntro
  skippedIntro = k ? { videoId: p.preflight.videoId, start: k.start, end: k.end } : undefined
})

// engine.hello {restored}: this connect resumed a lesson the engine kept. Its step.started is not a live start.
onMessage('engine.hello', (p) => {
  restoringUntil = p.restored === true ? performance.now() + RESTORE_WINDOW_MS : 0
})
onMessage('lesson.ended', (p) => {
  restoringUntil = 0
  // An engine deploy ("interrupted") comes back with the same lesson; any other end is final.
  if ((p.reason as string | undefined) !== 'interrupted') heldLesson = undefined
})

onMessage('step.started', (p) => {
  clearTimeout(resumeTimer)
  excursion = false
  // Only a live step rolls the video by itself: a replay (reconnect, restore, a window's first engine log) cues it.
  const live = stepStartPlays({ replay: p.replay, restoring: restoring(), sinceBootMs: sinceBoot(), setupHold })
  const replayed = !live && !setupHold
  restoringUntil = 0
  if (!replayed) deferred = undefined
  // A setup card still waiting: cue the clip and hold it (it starts when setup is done or skipped).
  if (!replayed) setUi({ resuming: false, pausedBy: setupHold ? 'setup' : undefined })
  else setUi({ resuming: false })
  const seg = p.video ?? useLesson.getState().steps.find((x) => x.id === p.stepId)?.video
  if (!seg) return
  const t = now()
  const sameVideo = resolveVideoId(seg.videoId) === want.videoId
  const start = clipStart(seg)
  // A replay of the step on screen (inside its clip, or held at its end): leave the video exactly as it is.
  if (replayed && replayKeepsVideo({ sameVideo, t, start, end: seg.end })) return
  // Already inside this clip (the previous step resumed straight into it): keep going, no jump.
  if (!replayed && sameVideo && t >= start - 1 && t < seg.end - GATE_EPS) {
    want = { ...want, videoId: resolveVideoId(seg.videoId) }
    if (live) setPlay(true, 'step')
    return
  }
  go(seg.videoId, start, live, 'step')
  // Cued for a replayed step: the play glyph, and the learner starts it.
  if (replayed) setUi({ pausedBy: 'start' })
})

onMessage('step.passed', (p) => {
  if (p.stepId !== useLesson.getState().stepId) return
  clearTimeout(resumeTimer)
  if (p.skipped) return // skipped, not passed: no "Passed" beat; step.started seeks to the next clip
  setUi({ resuming: true })
  resumeTimer = setTimeout(() => {
    const s = usePlayer.getState()
    setUi({ resuming: false })
    // The next part of a long video is still building: keep the video where it is (if it's still
    // playing it holds at this clip's end). The engine starts the next step after lesson.updated.
    if (resumesAfterPass({ playing: s.playing, pausedBy: s.pausedBy, setupHold, pending: p.pending })) player.play('resume')
  }, RESUME_DELAY_MS)
})

// Engine intent lives in core/lesson.video; `kind` says what changed it (seek / pause / play from the
// engine, jump from core seekVideo, which also reaches this window from the others in Electron).
useLesson.subscribe((s, prev) => {
  if (s.video === prev.video || !s.video.at || !isHost) return // at = 0: lesson.ready / reset blanking it
  const v = s.video
  // video.pause while a setup card waits: still the setup hold (no "Waiting for your checks"; it starts after setup).
  // Seek and pause always; play only while the panel is on screen (admit() keeps it paused as 'hidden' otherwise).
  if (v.kind === 'pause') return player.pause(setupHold ? 'setup' : 'engine')
  // An engine intent in this window's boot replay (main replays the engine log into a window that loads) or an engine
  // restore is stale: keep its position, drop its play (the learner presses play). A card's jump is a live click.
  const plays = v.kind === 'jump' || engineIntentPlays({ sinceBootMs: sinceBoot(), restoring: restoring() })
  if (v.kind === 'play') {
    if (plays) player.play('engine')
    else if (!usePlayer.getState().playing) setUi({ pausedBy: 'start' })
    return
  }
  const play = v.playing && plays
  const by: PausedBy = v.playing && !play ? 'start' : v.kind === 'seek' ? 'engine' : 'user'
  player.seek(v.t, play, by, true, v.kind === 'jump' ? 'jump' : 'engine')
})

// The lesson is gone (End, an interrupted lesson that never came back, an engine restart with no lesson): the player
// window hides (Michael's desktop test 9: the empty panel stayed open after End). Main also hides it on lesson.ended.
// The browser stage's panel already leaves with the lesson (StagePlayer).
if (isElectron && isHost)
  useLesson.subscribe((s, prev) => {
    if (prev.lesson && !s.lesson) bridge.invoke('player:hide').catch(() => undefined)
  })

onUi('reset', (payload) => {
  clearTimeout(resumeTimer)
  clearTimeout(autoplayTimer)
  deferred = undefined
  // A reconnect (or an engine deploy) may bring the same lesson back: keep knowing it (policy.ts rule 5).
  const reason = (payload as { reason?: string } | undefined)?.reason
  if (reason !== 'reconnect' && reason !== 'interrupted') heldLesson = undefined
  excursion = false
  setupHold = false
  skippedIntro = undefined
  // Keep where it was (not the last cue): if a reconnect's reset remounts the panel, it comes back at this position.
  want = { ...want, t: now(), play: false }
  if (yt && ready) yt.pauseVideo()
  setUi({ ...blank, ready: usePlayer.getState().ready })
})

// ---------------------------------------------------------------------------
// Hold during setup (Michael's desktop test 9: the video autoplayed to 0:44 while "Set up first" was waiting)
// ---------------------------------------------------------------------------

/**
 * A setup card waiting on the learner ("Set up first": Install / Open VS Code / Skip). The passing note that ends
 * setup ("matplotlib installed ✓", no buttons) is not one. Smart setup (Nov 22): only when the card says
 * setup.holdVideo is true; without the field (an older engine), any setup card with buttons. Setup is a companion:
 * "This lesson uses AutoCAD" waits beside the video while it plays.
 */
export { setupWaiting }

/** The card lands < 1 s after step.started: a hold this early in the clip goes back to its start. */
const SETUP_REWIND_S = 5
let setupHold = false

/** on: pause (back to the clip's start if it only just began). off: play, if the setup hold is still why it's paused. */
function holdForSetup(on: boolean): void {
  if (on === setupHold) return
  setupHold = on
  if (on) {
    clearTimeout(resumeTimer)
    const seg = openSegment()
    const start = seg ? clipStart(seg) : undefined
    const t = now()
    const back = start !== undefined && t >= start - 1 && t - start < SETUP_REWIND_S ? start : t
    setUi({ resuming: false, pausedBy: 'setup' })
    go(undefined, back, false)
    return
  }
  // Done or skipped. Not if something else paused it meanwhile (the learner, the gate, the end, a hidden panel).
  if (usePlayer.getState().pausedBy === 'setup') player.play('setup')
}

/**
 * Where it's decided: the cards' window (the overlay in Electron; the one stage window in the browser), since only
 * there do Skip, ✕ and the card's own timers close it. The player window hears it through main (player:setup, relayed
 * to every window). It also follows its own copy of the cards store, which sees every card the engine sends (the
 * "installed ✓" note that ends setup), in case the relay is missing.
 */
const cardsWindow = !isElectron || route === 'overlay' || route === ''
if (cardsWindow)
  useCards.subscribe((s, prev) => {
    const on = setupWaiting(s.card)
    if (on === setupWaiting(prev.card)) return
    if (isHost) holdForSetup(on)
    else bridge.invoke('player:setup', on).catch(() => undefined)
  })
if (isElectron && isHost) {
  bridge.onFeature('player:setup', (on) => holdForSetup(on === true))
  useCards.subscribe((s, prev) => {
    const on = setupWaiting(s.card)
    if (on !== setupWaiting(prev.card)) holdForSetup(on)
  })
}

// ---------------------------------------------------------------------------
// The panel shows or hides (policy.ts rules 1 and 3)
// ---------------------------------------------------------------------------

/** Hidden: pause. Shown: start a live step's deferred play if it's still in time; anything else waits for the learner. */
function onVisibility(): void {
  if (!isHost) return
  if (!visibleNow()) {
    const s = usePlayer.getState()
    if (want.play || s.playing) hideStop()
    return
  }
  const d = deferred
  deferred = undefined
  const late = startDeferred({ deferredAt: d?.at, now: performance.now(), sameStep: !!d && d.stepId === useLesson.getState().stepId, pausedBy: usePlayer.getState().pausedBy })
  if (late) player.play('step')
}

if (isElectron && isHost) {
  // Main says when the player window shows or hides (lesson.ready, End, a "Just teach me" lesson, player:hide).
  bridge.onFeature('player:visible', (on) => {
    windowShown = on === true
    onVisibility()
  })
  bridge
    .invoke('player:visible')
    .then((on) => {
      windowShown = on === true
      onVisibility()
    })
    .catch(() => undefined)
}
if (!isElectron && typeof document !== 'undefined') document.addEventListener('visibilitychange', onVisibility)

// Browser stage: stand-ins for the main-process handlers (there's no window to move).
registerWebHandler('player:dock', () => undefined)
registerWebHandler('player:hover', () => undefined)
registerWebHandler('player:visible', () => pageVisible())
// The stage's Vite server serves the host page itself (vite.web.config.ts), on the stage's own origin.
registerWebHandler('player:host', () => `${location.origin}/player-host.html`)

if (import.meta.env.DEV && isHost) Object.assign(window, { __player: { player, usePlayer, now, yt: () => yt } })
