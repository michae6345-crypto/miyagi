/**
 * Feature: launcher. "Paste a YouTube link → skip search": recognise a YouTube video URL.
 * Accepts watch?v=, youtu.be/, shorts/, live/, embed/ (with or without https://, www., m.).
 * Returns null for anything else (playlists without a video, channels, plain text…).
 */
export type YouTubeLink = {
  /** Normalised https URL, sent as learn_url {url}. */
  url: string
  videoId: string
  /** Start time from ?t= / ?start=, in seconds. */
  start?: number
}

const HOST = /^(?:www\.|m\.|music\.)?(?:youtube\.com|youtube-nocookie\.com|youtu\.be)$/i
const VIDEO_ID = /^[\w-]{11}$/

export function parseYouTube(text: string): YouTubeLink | null {
  const raw = text.trim()
  if (!raw || /\s/.test(raw)) return null
  let u: URL
  try {
    u = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`)
  } catch {
    return null
  }
  if (!HOST.test(u.hostname)) return null

  let id: string | null = null
  if (/youtu\.be$/i.test(u.hostname)) id = u.pathname.split('/')[1] ?? null
  else if (u.pathname === '/watch') id = u.searchParams.get('v')
  else id = u.pathname.match(/^\/(?:shorts|live|embed|v)\/([^/?#]+)/)?.[1] ?? null
  if (!id || !VIDEO_ID.test(id)) return null

  return { url: u.toString(), videoId: id, start: seconds(u.searchParams.get('t') ?? u.searchParams.get('start')) }
}

/** "90", "90s", "1m30s", "1h2m3s" → seconds. */
function seconds(t: string | null): number | undefined {
  if (!t) return
  if (/^\d+s?$/.test(t)) return Number.parseInt(t, 10) || undefined
  const m = t.match(/^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$/)
  if (!m) return
  const s = Number(m[1] ?? 0) * 3600 + Number(m[2] ?? 0) * 60 + Number(m[3] ?? 0)
  return s || undefined
}

/** YouTube's public thumbnail for a video id (320×180). */
export const thumbnailFor = (videoId: string): string => `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg`
