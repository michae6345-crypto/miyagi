/**
 * YouTube IFrame Player API: loader + the few types we use (no @types package needed).
 * https://developers.google.com/youtube/iframe_api_reference
 */

/**
 * Plays when the lesson's video id isn't a real YouTube id (the mock and the engine use a placeholder
 * until the tutorial is picked). One place to change it. Any real, embeddable public video works;
 * this one is 18:40 long, so the mock's step times (0–18:40) fit.
 */
export const STAND_IN_VIDEO_ID = 'aircAruvnKk'

/** YouTube video ids are 11 characters of [A-Za-z0-9_-]. Anything else is a placeholder. */
export function isYouTubeId(id: string | undefined): id is string {
  return !!id && /^[\w-]{11}$/.test(id)
}

export function resolveVideoId(id: string | undefined): string {
  return isYouTubeId(id) ? id : STAND_IN_VIDEO_ID
}

export const YTState = { UNSTARTED: -1, ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3, CUED: 5 } as const

export type YTPlayer = {
  playVideo(): void
  pauseVideo(): void
  seekTo(seconds: number, allowSeekAhead: boolean): void
  loadVideoById(o: { videoId: string; startSeconds?: number }): void
  cueVideoById(o: { videoId: string; startSeconds?: number }): void
  getCurrentTime(): number
  getDuration(): number
  getPlayerState(): number
  mute(): void
  unMute(): void
  isMuted(): boolean
  destroy(): void
  getVideoData?(): { video_id?: string; title?: string; author?: string }
}

type YTEvent = { target: YTPlayer; data: number }

export type YTOptions = {
  width?: string | number
  height?: string | number
  videoId?: string
  host?: string
  playerVars?: Record<string, string | number>
  events?: {
    onReady?: (e: YTEvent) => void
    onStateChange?: (e: YTEvent) => void
    onError?: (e: YTEvent) => void
  }
}

type YTNamespace = { Player: new (el: HTMLElement, opts: YTOptions) => YTPlayer }

declare global {
  interface Window {
    YT?: YTNamespace
    onYouTubeIframeAPIReady?: () => void
  }
}

let loading: Promise<YTNamespace> | undefined

/** Loads https://www.youtube.com/iframe_api once. */
export function loadYouTube(): Promise<YTNamespace> {
  if (window.YT?.Player) return Promise.resolve(window.YT)
  loading ??= new Promise<YTNamespace>((resolve, reject) => {
    const prev = window.onYouTubeIframeAPIReady
    window.onYouTubeIframeAPIReady = () => {
      prev?.()
      resolve(window.YT!)
    }
    const s = document.createElement('script')
    s.src = 'https://www.youtube.com/iframe_api'
    s.async = true
    s.onerror = () => {
      loading = undefined
      reject(new Error('Could not load the YouTube player (offline?)'))
    }
    document.head.appendChild(s)
  })
  return loading
}

/** YouTube's onError codes → a short, human message. */
export function describeYTError(code: number): string {
  switch (code) {
    case 2:
      return 'Invalid video id'
    case 5:
      return 'This video can’t play here'
    case 100:
      return 'Video not found or private'
    case 101:
    case 150:
      return 'The owner doesn’t allow embedding'
    case 153:
      return 'YouTube refused the embed (no page origin; see player.md)'
    default:
      return `YouTube error ${code}`
  }
}
