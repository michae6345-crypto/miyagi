/**
 * The YouTube player, out of our page (R33). YouTube's IFrame API never runs here, next to the bridge: it runs in the
 * host page (main/playerHost.ts + playerHost.page.js), which we frame from its own loopback origin. FramePlayer is the
 * YTPlayer the store drives, over postMessage to that frame:
 *
 *   - commands go to the frame's window, to the host's origin only
 *   - only messages from that window, from that origin, are read; every field is checked before it's kept
 *   - the getters answer from the last state the host sent (it sends on every event and every change, at most every
 *     100 ms), like YouTube's own API answers from what its embed last sent. While playing, the time runs on from the
 *     last report (at most 1 s), so the gate's 100 ms tick sees it move.
 *
 * The iframe is sandboxed: scripts and its own origin (YouTube checks it), no popups, no top navigation, no forms.
 * Main also locks its navigation (features/player.ts).
 */
import { YTState, isYouTubeId, type YTPlayer } from './youtube'

export type FrameEvents = {
  onReady(): void
  onStateChange(state: number): void
  onError(code: number): void
  /** The host page couldn't load YouTube's API (offline?), or never answered. */
  onFail(): void
}

type Info = { state: number; t: number; at: number; duration: number; rate: number; volume: number; muted: boolean; title: string; videoId: string }

const STATES = new Set<number>(Object.values(YTState))
/** No ready from the host page this long after we framed it: say so (a late ready still recovers: its cue clears the error). */
const READY_TIMEOUT_MS = 20_000
/** While playing, the time runs on from the last report, but never more than this past it. */
const EXTRAPOLATE_MAX_MS = 1000

const finite = (v: unknown, lo: number, hi: number): v is number => typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi

export class FramePlayer implements YTPlayer {
  private readonly frame: HTMLIFrameElement
  private readonly origin: string
  private info: Info = { state: YTState.UNSTARTED, t: 0, at: 0, duration: 0, rate: 1, volume: 100, muted: false, title: '', videoId: '' }
  private ready = false
  private dead = false
  private timeout: ReturnType<typeof setTimeout> | undefined

  constructor(
    el: HTMLElement,
    url: string,
    private readonly events: FrameEvents
  ) {
    this.origin = new URL(url).origin
    const f = document.createElement('iframe')
    f.title = 'Tutorial video'
    f.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-presentation')
    f.allow = 'autoplay; encrypted-media; picture-in-picture'
    f.referrerPolicy = 'no-referrer'
    f.style.cssText = 'display:block;width:100%;height:100%;border:0'
    f.src = url
    this.timeout = setTimeout(() => !this.ready && !this.dead && this.events.onFail(), READY_TIMEOUT_MS)
    this.frame = f
    window.addEventListener('message', this.onMessage)
    el.appendChild(f)
  }

  private readonly onMessage = (e: MessageEvent): void => {
    if (this.dead || e.source !== this.frame.contentWindow || e.origin !== this.origin) return
    const m = e.data as { miyagiPlayer?: unknown; ev?: unknown; data?: unknown; info?: unknown } | null
    if (!m || typeof m !== 'object' || m.miyagiPlayer !== 1) return
    if (m.info) this.take(m.info)
    switch (m.ev) {
      case 'ready':
        if (this.ready) return
        this.ready = true
        clearTimeout(this.timeout)
        this.events.onReady()
        return
      case 'state':
        if (typeof m.data === 'number' && STATES.has(m.data)) this.events.onStateChange(m.data)
        return
      case 'error':
        if (Number.isInteger(m.data)) this.events.onError(m.data as number)
        return
      case 'fail':
        clearTimeout(this.timeout)
        this.events.onFail()
        return
      default:
        return
    }
  }

  /** Keep what the host reported, field by field, only when it's the right kind of value. */
  private take(raw: unknown): void {
    if (!raw || typeof raw !== 'object') return
    const r = raw as Record<string, unknown>
    const i = { ...this.info, at: Date.now() }
    if (typeof r.state === 'number' && STATES.has(r.state)) i.state = r.state
    if (finite(r.t, 0, 1e6)) i.t = r.t
    if (finite(r.duration, 0, 1e6)) i.duration = r.duration
    if (finite(r.rate, 0.25, 2)) i.rate = r.rate
    if (finite(r.volume, 0, 100)) i.volume = r.volume
    if (typeof r.muted === 'boolean') i.muted = r.muted
    if (typeof r.title === 'string') i.title = r.title.slice(0, 300)
    if (typeof r.videoId === 'string') i.videoId = isYouTubeId(r.videoId) ? r.videoId : ''
    this.info = i
  }

  private post(op: string, args: Record<string, unknown> = {}): void {
    if (this.dead) return
    this.frame.contentWindow?.postMessage({ miyagiPlayer: 1, op, ...args }, this.origin)
  }

  playVideo(): void {
    this.post('play')
  }
  pauseVideo(): void {
    this.post('pause')
  }
  seekTo(seconds: number): void {
    this.post('seek', { t: seconds })
  }
  loadVideoById(o: { videoId: string; startSeconds?: number }): void {
    this.post('load', { videoId: o.videoId, t: o.startSeconds ?? 0 })
  }
  cueVideoById(o: { videoId: string; startSeconds?: number }): void {
    this.post('cue', { videoId: o.videoId, t: o.startSeconds ?? 0 })
  }
  getCurrentTime(): number {
    const i = this.info
    if (i.state !== YTState.PLAYING) return i.t
    const t = i.t + (Math.min(Date.now() - i.at, EXTRAPOLATE_MAX_MS) / 1000) * i.rate
    return i.duration > 0 ? Math.min(t, i.duration) : t
  }
  getDuration(): number {
    return this.info.duration
  }
  getPlayerState(): number {
    return this.info.state
  }
  mute(): void {
    this.info = { ...this.info, muted: true }
    this.post('mute')
  }
  unMute(): void {
    this.info = { ...this.info, muted: false }
    this.post('unmute')
  }
  isMuted(): boolean {
    return this.info.muted
  }
  setVolume(v: number): void {
    this.info = { ...this.info, volume: v }
    this.post('volume', { v })
  }
  getVolume(): number {
    return this.info.volume
  }
  setPlaybackRate(rate: number): void {
    this.info = { ...this.info, rate }
    this.post('rate', { rate })
  }
  getPlaybackRate(): number {
    return this.info.rate
  }
  getVideoData(): { video_id?: string; title?: string } {
    return { video_id: this.info.videoId || undefined, title: this.info.title || undefined }
  }
  destroy(): void {
    if (this.dead) return
    this.dead = true
    clearTimeout(this.timeout)
    window.removeEventListener('message', this.onMessage)
    this.frame.remove()
  }
}
