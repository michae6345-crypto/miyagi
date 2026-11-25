/**
 * Any link: the link.get → link.preview round trip for pages (ANY-LINK.md). One store shared by the launcher and the
 * notch's drop zone (each window has its own copy: the store is per renderer, the engine answers either).
 *
 *   askLink(url)      link.get {url, reqId} once per link (a repeat paste reuses the answer); only when the engine
 *                     lists "link.any" and link.get in engine.hello. For a paste, a drop or Enter.
 *   askLinkSoon(url)  the same for a link being typed: asked only once it has settled for LINK_SETTLE_MS, and a newer
 *                     link replaces the waiting one, so typing a URL key by key sends one link.get, not one per prefix
 *                     (each link.get is a page fetch, a robots.txt fetch and a model call on the engine).
 *   usePreview(url)   the latest answer for that link: the fast pending one (title and site), then the full one.
 *
 * A preview is matched to the link that asked by its reqId, else by the link itself (url or finalUrl, compared with
 * sameLink). Every field is checked and capped before it is kept: the engine read it off someone's web page.
 */
import { create } from 'zustand'
import type { LINK_ANY_CAPABILITY, LessonTool, LinkKind, LinkPreview, LookupError } from '../../../../../../shared/contracts/events'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage } from '../../core/bus'
import { canSend, useCapability } from '../../core/lesson'
import { linkKey, safeWebUrl } from './link'

/** events.ts LINK_ANY_CAPABILITY (a type-only import: the app takes no values from the contract file). */
const LINK_ANY: typeof LINK_ANY_CAPABILITY = 'link.any'

type State = {
  /** linkKey → the preview kept for it. */
  previews: Record<string, LinkPreview>
  /** linkKey → the reqId that asked. */
  asked: Record<string, string>
  /** A link dropped on the notch (its preview card replaces Continue until it starts or is dismissed). */
  dropped?: string
}

export const useAnyLink = create<State>(() => ({ previews: {}, asked: {} }))

/** Does this engine take any http(s) link (link.get previews and learn_url builds)? */
export const useLinkAny = (): boolean => {
  const any = useCapability(LINK_ANY)
  const get = useCapability('link.get')
  return any && get
}
export const canLinkAny = (): boolean => canSend(LINK_ANY) && canSend('link.get')

let seq = 0

/** How many links the store remembers (asked and their previews); the oldest go first. */
export const MAX_LINKS = 24

/** Ask the engine about a page once (repeat calls are free). false when this engine can't. */
export function askLink(url: string): boolean {
  const key = linkKey(url)
  if (!key || !canLinkAny()) return false
  const s = useAnyLink.getState()
  if (s.asked[key] && !s.previews[key]?.error) return true
  // A link that failed (offline, busy) is asked again on the next paste.
  const reqId = `any-${Date.now().toString(36)}-${++seq}`
  // Newest last (re-asking moves a link to the end), then only the newest MAX_LINKS stay, plus the dropped link.
  const asked = Object.entries(s.asked).filter(([k]) => k !== key)
  asked.push([key, reqId])
  const dropped = linkKey(s.dropped)
  const kept = new Set(asked.slice(-MAX_LINKS).map(([k]) => k))
  if (dropped && s.asked[dropped]) kept.add(dropped)
  useAnyLink.setState({
    asked: Object.fromEntries(asked.filter(([k]) => kept.has(k))),
    previews: Object.fromEntries(Object.entries(s.previews).filter(([k]) => k !== key && kept.has(k)))
  })
  bridge.send(cmd('link.get', { url, reqId }))
  return true
}

/** How long a typed link must stay unchanged before it is asked about. */
export const LINK_SETTLE_MS = 500
let settle: ReturnType<typeof setTimeout> | undefined

/**
 * A link being typed: ask about it once it has stayed the same for LINK_SETTLE_MS. Each call replaces the link
 * waiting before it (older prefixes are never sent); undefined just cancels. A link already asked is not asked again.
 */
export function askLinkSoon(url: string | undefined): void {
  clearTimeout(settle)
  settle = undefined
  const key = linkKey(url)
  if (!url || !key) return
  const s = useAnyLink.getState()
  if (s.asked[key] && !s.previews[key]?.error) return
  settle = setTimeout(() => {
    settle = undefined
    askLink(url)
  }, LINK_SETTLE_MS)
}

/** Ask now (a paste, a drop, Enter on a typed link): cancels any typed link still waiting. */
export function askLinkNow(url: string): boolean {
  askLinkSoon(undefined)
  return askLink(url)
}

export function usePreview(url: string | undefined): LinkPreview | undefined {
  const key = linkKey(url)
  return useAnyLink((s) => (key ? s.previews[key] : undefined))
}

export function dropLink(url: string | undefined): void {
  useAnyLink.setState({ dropped: url })
}

// ---- checking an answer ---------------------------------------------------------------------------------------------

const KINDS: readonly LinkKind[] = ['video', 'playlist', 'unsupported', 'web', 'github']
const ERRORS: readonly LookupError[] = ['not_found', 'private', 'unsupported', 'offline', 'too_long', 'busy', 'unknown', 'blocked']
const TOOLS: readonly LessonTool[] = ['vscode', 'jupyter', 'terminal', 'excel']
/** A path anywhere in a string (a home folder) is never shown. */
const PATHY = /\/(Users|home|private|var|tmp|opt)\/|~\/|[A-Za-z]:\\/

function str(v: unknown, max: number): string | undefined {
  if (typeof v !== 'string') return undefined
  const s = v.replace(/\s+/g, ' ').trim()
  if (!s || PATHY.test(s)) return undefined
  return s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s
}

/** A link.preview payload → the fields the app shows, checked. undefined when it has no usable url. */
export function cleanPreview(v: unknown): LinkPreview | undefined {
  if (!v || typeof v !== 'object') return undefined
  const o = v as Record<string, unknown>
  const url = typeof o.url === 'string' && o.url.length <= 2048 ? o.url : undefined
  const kind = KINDS.includes(o.kind as LinkKind) ? (o.kind as LinkKind) : undefined
  if (!url || !kind) return undefined
  const t = o.teach && typeof o.teach === 'object' ? (o.teach as Record<string, unknown>) : undefined
  const teach = t ? { steps: t.steps === true, code: t.code === true } : undefined
  const mins = typeof o.estMinutes === 'number' && Number.isFinite(o.estMinutes) && o.estMinutes > 0 && o.estMinutes <= 600 ? Math.round(o.estMinutes) : undefined
  const grows = Array.isArray(o.grows)
    ? o.grows
        .map((g) => (g && typeof g === 'object' ? str((g as { label?: unknown }).label, 40) : undefined))
        .filter((l): l is string => !!l)
        .slice(0, 4)
        .map((label) => ({ label }))
    : undefined
  return {
    url,
    reqId: typeof o.reqId === 'string' ? o.reqId : undefined,
    kind,
    pending: o.pending === true,
    title: str(o.title, 140),
    site: str(o.site, 80),
    author: str(o.author, 60),
    estMinutes: mins,
    teachable: typeof o.teachable === 'boolean' ? o.teachable : teach ? teach.steps || teach.code : undefined,
    teach,
    why: str(o.why, 140),
    tools: Array.isArray(o.tools) ? [...new Set(o.tools.filter((x): x is LessonTool => TOOLS.includes(x as LessonTool)))] : undefined,
    grows: grows?.length ? grows : undefined,
    cached: o.cached === true,
    finalUrl: safeWebUrl(o.finalUrl),
    error: ERRORS.includes(o.error as LookupError) ? (o.error as LookupError) : undefined
  }
}

onMessage('link.preview', (raw) => {
  const p = cleanPreview(raw)
  if (!p) return
  const s = useAnyLink.getState()
  // The link that asked: its reqId first, else the link itself (or where it ended after redirects).
  const byReq = p.reqId ? Object.entries(s.asked).find(([, r]) => r === p.reqId)?.[0] : undefined
  const key = byReq ?? [linkKey(p.url), linkKey(p.finalUrl)].find((k) => !!k && k in s.asked)
  if (!key) return
  const prev = s.previews[key]
  // A late fast answer never replaces the full one.
  if (prev && !prev.pending && p.pending) return
  useAnyLink.setState({ previews: { ...s.previews, [key]: prev && p.pending ? { ...prev, ...p } : p } })
})

// A dropped link's card has done its job once a lesson starts building (from it or from anything else).
onMessage('lesson.building', () => {
  if (useAnyLink.getState().dropped) useAnyLink.setState({ dropped: undefined })
})
