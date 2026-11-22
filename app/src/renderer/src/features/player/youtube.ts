/**
 * YouTube IFrame Player API: the few types and helpers we use (no @types package needed).
 * https://developers.google.com/youtube/iframe_api_reference
 *
 * R33: the API itself never loads in our pages. It runs in the player host page (main/playerHost.page.js), framed from
 * its own origin; frame.ts is the YTPlayer the store drives over postMessage.
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
  setVolume(v: number): void
  getVolume(): number
  setPlaybackRate(rate: number): void
  getPlaybackRate(): number
  destroy(): void
  getVideoData?(): { video_id?: string; title?: string; author?: string }
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
      return 'YouTube won’t play this video here'
    default:
      return `YouTube error ${code}`
  }
}
