/**
 * Player state + the controller around the YouTube player. Pure module state, no React:
 * the Video component only lends it a DOM node (attachPlayer).
 *
 * Gating:
 *   step.started  → load/cue the step's clip at video.start and play
 *   t ≥ video.end → while the step isn't passed: pause at end ("Waiting for your checks")
 *   step.passed   → a 400ms "Passed" beat, then resume (unless the learner paused it themself)
 * Engine intent (core/lesson.video, set by video.seek / video.pause / video.play and by card video jumps):
 *   followed as-is. A seek past the gate is allowed (the engine asked for it); the gate only stops
 *   playback that runs into the end of the open step.
 * Reports video.state {t, playing} every second while playing and on every change.
 *
 * Electron: this module runs in every window (features are imported everywhere), but only the
 * player window hosts the YouTube player. Card video jumps happen in the overlay window, so other
 * windows relay them through main (player:intent → broadcast) to the player window.
 */
import { create } from 'zustand'
import type { VideoSegment } from '../../../../../../shared/contracts/events'
import { cmd } from '../../../../common/wire'
import { bridge, isElectron, registerWebHandler } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { describeYTError, loadYouTube, resolveVideoId, YTState, PLACEHOLDER_VIDEO_ID, type YTPlayer } from './youtube'

/** Why the video is paused. 'gate' = we stopped at the step's end; 'engine' = video.pause. */
export type PausedBy = 'gate' | 'engine' | 'user' | 'ended'

type PlayerState = {
  /** The YouTube player exists and answered onReady. */
  ready: boolean
  videoId?: string
  /** True when the lesson's id is the placeholder and we play the stand-in. */
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
  error?: string
}

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
  error: undefined
}

export const usePlayer = create<PlayerState>(() => ({ ...blank }))
const setUi = usePlayer.setState

export const RESUME_DELAY_MS = 400
/** Stop this close to the end: YouTube's time updates are ~250ms coarse. */
const GATE_EPS = 0.15
/** Playing inside [end, end + 3s) while the step is still open stops again (so ▶ at the gate can't sneak past). */
const GATE_ZONE = 3
const TICK_MS = 100
const REPORT_MS = 1000
const AUTOPLAY_GRACE_MS = 1500

/** Electron loads index.html#/player for the player window; the browser stage is one window that hosts everything. */
const route = location.hash.replace(/^#\/?/, '')
export const isHost = !isElectron || route === 'player'

// ---------------------------------------------------------------------------
// Lesson helpers
// ---------------------------------------------------------------------------

/** The current step's clip, if the step is still open (not passed). */
export function openSegment(): VideoSegment | undefined {
  const s = useLesson.getState()
  if (!s.stepId || s.passed.includes(s.stepId)) return undefined
  return s.stepVideo ?? s.steps.find((x) => x.id === s.stepId)?.video
}

function currentSegment(): VideoSegment | undefined {
  const s = useLesson.getState()
  return s.stepVideo ?? s.steps.find((x) => x.id === s.stepId)?.video
}

/**
 * The engine (or a card's video jump) sent us to/after the open step's end on purpose, e.g. Show me
 * at step 6 seeks to 14:30 where the tutorial shows the fix. The gate stands aside until the step
 * changes or the learner goes back into the clip.
 */
let excursion = false

/** Is time t at (or just past) the open step's end, with the gate holding? */
export function inGate(t: number): boolean {
  const seg = openSegment()
  return !excursion && !!seg && t >= seg.end - GATE_EPS && t < seg.end + GATE_ZONE
}

/** Engine/card seeks: past the gate = an excursion. Learner seeks (chapters, replay, timeline) never are. */
function setExcursion(t: number, fromEngine: boolean): void {
  const seg = openSegment()
  excursion = fromEngine && !!seg && t >= seg.end - GATE_EPS
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

const state = (): number => (yt && ready ? yt.getPlayerState() : YTState.UNSTARTED)
const isRolling = (st: number): boolean => st === YTState.PLAYING || st === YTState.BUFFERING
const notStarted = (st: number): boolean => st === YTState.CUED || st === YTState.UNSTARTED

/** Current position. A cued video reports 0, so fall back to where we cued it. */
function now(): number {
  if (!yt || !ready || notStarted(state())) return want.t
  return yt.getCurrentTime()
}

function sync(changed = false): void {
  const st = state()
  setUi({
    ready,
    t: now(),
    duration: yt && ready ? yt.getDuration() || 0 : 0,
    playing: isRolling(st),
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

/** Load the video if needed, go to t, then play or stay paused. */
function go(videoId: string | undefined, t: number, play: boolean): void {
  const id = resolveVideoId(videoId ?? want.videoId)
  want = { videoId: id, t, play }
  if (videoId !== undefined) setUi({ standIn: videoId === PLACEHOLDER_VIDEO_ID, error: undefined })
  if (!play) clearTimeout(autoplayTimer)
  if (!yt || !ready) return sync()
  if (id !== loadedId) {
    loadedId = id
    if (play) yt.loadVideoById({ videoId: id, startSeconds: t })
    else yt.cueVideoById({ videoId: id, startSeconds: t })
  } else if (!play && notStarted(state())) {
    yt.cueVideoById({ videoId: id, startSeconds: t }) // seekTo on a cued video would start playing it
  } else {
    yt.seekTo(t, true)
    if (play) yt.playVideo()
    else yt.pauseVideo()
  }
  if (play) watchAutoplay()
  sync(true)
}

function setPlay(play: boolean): void {
  want = { ...want, t: now(), play }
  if (!yt || !ready) return sync()
  if (play) {
    if (state() === YTState.ENDED) return sync()
    yt.playVideo()
    watchAutoplay()
  } else {
    clearTimeout(autoplayTimer)
    yt.pauseVideo()
  }
  sync(true)
}

/** Browsers block autoplay with sound without a user gesture: fall back to muted playback. */
function watchAutoplay(): void {
  clearTimeout(autoplayTimer)
  autoplayTimer = setTimeout(() => {
    if (!yt || !ready || !want.play || isRolling(state())) return
    yt.mute()
    yt.playVideo()
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

function tick(): void {
  if (!yt || !ready) return
  const t = now()
  const seg = openSegment()
  if (seg && isRolling(state()) && inGate(t)) return gate(seg.end)
  const s = usePlayer.getState()
  if (Math.abs(s.t - t) > 0.04 || !s.duration) sync()
}

function onStateChange(st: number): void {
  if (!yt) return
  // Our intent wins: seekTo on a cued video starts playback even when we wanted it paused.
  if (st === YTState.PLAYING && !want.play) return yt.pauseVideo()
  if (isRolling(st)) clearTimeout(autoplayTimer)
  if (st === YTState.ENDED) {
    want = { ...want, play: false }
    setUi({ pausedBy: openSegment() ? 'gate' : 'ended' })
  }
  sync(true)
}

/** The Video component lends a DOM node; returns the cleanup. */
export function attachPlayer(host: HTMLElement): () => void {
  let dead = false
  let destroy = (): void => {}
  const mount = document.createElement('div')
  mount.style.cssText = 'width:100%;height:100%'
  host.appendChild(mount)
  const inner = document.createElement('div')
  mount.appendChild(inner)

  loadYouTube()
    .then((YT) => {
      if (dead) return
      // Under file:// (packaged Electron) there's no http(s) origin to give YouTube: see player.md → Notes.
      const vars: Record<string, string | number> = { controls: 0, disablekb: 1, fs: 0, rel: 0, iv_load_policy: 3, playsinline: 1, enablejsapi: 1 }
      if (/^https?:$/.test(location.protocol)) vars.origin = location.origin
      const player = new YT.Player(inner, {
        width: '100%',
        height: '100%',
        playerVars: vars,
        events: {
          onReady: () => {
            if (dead) return
            yt = player
            ready = true
            loadedId = undefined
            if (want.videoId) go(want.videoId, want.t, want.play)
            else sync()
          },
          onStateChange: (e) => !dead && onStateChange(e.data),
          onError: (e) => !dead && setUi({ error: describeYTError(e.data) })
        }
      })
      destroy = () => player.destroy() // even before onReady
      tickTimer = setInterval(tick, TICK_MS)
      reportTimer = setInterval(() => report(true), REPORT_MS)
    })
    .catch((err: Error) => !dead && setUi({ error: err.message }))

  return () => {
    dead = true
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
    mount.remove()
    setUi({ ready: false, playing: false })
  }
}

// ---------------------------------------------------------------------------
// Commands (UI + engine)
// ---------------------------------------------------------------------------

export const player = {
  /**
   * Seek and play/pause. `by` says who paused it when play is false.
   * `fromEngine`: video.seek or a card's video jump (may take the video past the gate on purpose).
   */
  seek(t: number, play: boolean, by: PausedBy = 'user', fromEngine = false): void {
    clearTimeout(resumeTimer)
    setExcursion(t, fromEngine)
    setUi({ resuming: false, pausedBy: play ? undefined : by })
    go(undefined, t, play)
  },
  /** Returns false when the open step's gate holds the video. */
  play(): boolean {
    if (inGate(now())) return false
    setUi({ pausedBy: undefined })
    setPlay(true)
    return true
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
    if (seg) player.seek(seg.start, true)
  },
  unmute(): void {
    yt?.unMute()
    setUi({ muted: false })
  },
  /** Seek from the timeline: never past the open step's gate. */
  scrub(t: number): void {
    const seg = openSegment()
    const target = seg ? Math.min(t, seg.end) : t
    const keepPlaying = usePlayer.getState().playing && !inGate(target)
    player.seek(target, keepPlaying, seg && target >= seg.end - GATE_EPS ? 'gate' : 'user')
  }
}

// ---------------------------------------------------------------------------
// Engine + UI events
// ---------------------------------------------------------------------------

onMessage('lesson.ready', (p) => {
  clearTimeout(resumeTimer)
  setUi({ pausedBy: undefined, resuming: false, error: undefined, standIn: false, title: undefined })
  // Cue the first clip so the player is warm when the first step starts.
  const first = p.steps.find((s) => s.video)?.video
  if (first) go(first.videoId, first.start, false)
})

onMessage('step.started', (p) => {
  clearTimeout(resumeTimer)
  excursion = false
  setUi({ resuming: false, pausedBy: undefined })
  const seg = p.video ?? useLesson.getState().steps.find((x) => x.id === p.stepId)?.video
  if (!seg) return
  const t = now()
  const sameVideo = resolveVideoId(seg.videoId) === want.videoId
  // Already inside this clip (the previous step resumed straight into it): keep going, no jump.
  if (sameVideo && t >= seg.start - 1 && t < seg.end - GATE_EPS) {
    want = { ...want, videoId: resolveVideoId(seg.videoId) }
    setPlay(true)
  } else go(seg.videoId, seg.start, true)
})

onMessage('step.passed', (p) => {
  if (p.stepId !== useLesson.getState().stepId) return
  clearTimeout(resumeTimer)
  setUi({ resuming: true })
  resumeTimer = setTimeout(() => {
    const s = usePlayer.getState()
    setUi({ resuming: false })
    if (!s.playing && s.pausedBy !== 'user' && s.pausedBy !== 'ended') player.play()
  }, RESUME_DELAY_MS)
})

// Engine intent lives in core/lesson.video. video.pause/play keep the old t, so we need to know
// which message changed it: these set a flag, and the store subscription decides on a microtask
// (after every handler for this message has run, whatever order they were registered in).
let lastMsg: 'seek' | 'pause' | 'play' | undefined
onMessage('video.seek', () => void (lastMsg = 'seek'))
onMessage('video.pause', () => void (lastMsg = 'pause'))
onMessage('video.play', () => void (lastMsg = 'play'))

useLesson.subscribe((s, prev) => {
  if (s.video === prev.video || !s.video.at) return // at = 0: lesson.ready / reset blanking it
  queueMicrotask(followIntent)
})

function followIntent(): void {
  const v = useLesson.getState().video
  const kind = lastMsg ?? 'jump' // no engine message: something set it directly (a card's video jump)
  lastMsg = undefined
  if (!isHost) {
    // Electron, overlay/launcher window: hand card jumps to the player window via main.
    if (kind === 'jump') bridge.invoke('player:intent', { t: v.t, play: v.playing }).catch(() => {})
    return
  }
  if (kind === 'pause') player.pause('engine')
  else if (kind === 'play') player.play()
  else player.seek(v.t, v.playing, kind === 'seek' ? 'engine' : 'user', true)
}

if (isElectron && isHost) {
  bridge.onFeature('player:intent', (p) => {
    const v = p as { t: number; play: boolean }
    player.seek(v.t, v.play, 'user', true)
  })
}

onUi('reset', () => {
  clearTimeout(resumeTimer)
  excursion = false
  want = { ...want, play: false }
  if (yt && ready) yt.pauseVideo()
  setUi({ ...blank, ready: usePlayer.getState().ready })
})

// Browser stage: stand-ins for the main-process handlers (there's no window to move).
registerWebHandler('player:dock', () => undefined)
registerWebHandler('player:hover', () => undefined)

if (import.meta.env.DEV && isHost) Object.assign(window, { __player: { player, usePlayer, now } })
