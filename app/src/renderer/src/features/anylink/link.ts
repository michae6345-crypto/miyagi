/**
 * Any link (Nov 24, shared/contracts/ANY-LINK.md): the app side of "paste any link, get a lesson". Pure (no React, no
 * bridge, no stores), so tests import it directly and main could too.
 *
 *   parseWebLink(text)    a pasted / dropped http(s) link that is not YouTube (the launcher's youtube.ts keeps those):
 *                         an article, a docs page or a github.com repo. Bare text needs a clear web shape ("www.",
 *                         a path, or a common TLD) so a typed goal like "numpy.array" stays a goal.
 *   siteOf(url)           what the app shows for where a link goes: "docs.python.org", "github.com/pallets/flask".
 *   sameLink(a, b)        two spellings of one page (http / www. / a trailing slash / #part / utm_*), like the engine's
 *                         normalize_link_url, enough to match a link.preview to the link that asked for it.
 *   safeWebUrl(raw)       a URL the app may show and open (plain http(s), no user / password, no odd port, <= 2048).
 *   pageAction(preview)   what the card's one primary does: build, teach (not teachable), wait (still reading), none.
 *   lookupLine(error)     the calm line for a link.preview error.
 *
 * The app never loads anything from a pasted site (no favicon, no og:image): a page's picture is a neutral tile with
 * its kind's glyph (Card.tsx).
 */
import type { BuildSource, LinkPreview, LookupError } from '../../../../../../shared/contracts/events'

export type WebKind = 'web' | 'github'

export type WebLink = {
  /** The link as sent to the engine (link.get / learn_url): https added to bare text, otherwise as typed. */
  url: string
  /** The app's guess until the engine answers: github.com/<owner>/<repo>[/...] is "github", anything else "web". */
  kind: WebKind
  /** "docs.python.org", "github.com/pallets/flask". */
  site: string
}

const MAX_URL = 2048
/** Bare text (no scheme) reads as a link only with one of these TLDs, a "www." or a path. */
const COMMON_TLDS = new Set(['com', 'org', 'net', 'io', 'dev', 'ai', 'edu', 'gov', 'co', 'app', 'me', 'sh', 'so', 'info', 'tech', 'blog', 'page', 'site', 'xyz', 'uk', 'de', 'fr', 'ca', 'au', 'in', 'jp'])
const YOUTUBE = /(^|\.)(youtube\.com|youtube-nocookie\.com|youtu\.be)$/i
/** Hosts the engine refuses anyway (ANY-LINK.md "Fetch safely"): the app doesn't offer them as a page either. */
const LOCAL = /^(localhost|.*\.local|.*\.localhost|.*\.internal)$/i
const IP4 = /^\d{1,3}(\.\d{1,3}){3}$/
const TRACKING = /^(utm_.*|fbclid|gclid|mc_cid|mc_eid|ref|ref_src|igshid|si)$/i
/** github.com paths that are not a repo. */
const GITHUB_NOT_OWNER = new Set(['settings', 'orgs', 'topics', 'explore', 'marketplace', 'features', 'login', 'join', 'about', 'pricing', 'search', 'sponsors', 'notifications', 'new', 'trending', 'collections', 'events'])

function toUrl(raw: string): URL | undefined {
  try {
    return new URL(raw)
  } catch {
    return undefined
  }
}

const hostOf = (u: URL): string => u.hostname.toLowerCase().replace(/\.$/, '').replace(/^www\./, '')

/** github.com/<owner>/<repo> of a URL, lower case, ".git" dropped; undefined when the path isn't a repo. */
function githubRepo(u: URL): string | undefined {
  if (hostOf(u) !== 'github.com') return undefined
  const [owner = '', repo = ''] = u.pathname.split('/').filter(Boolean)
  if (!owner || !repo || GITHUB_NOT_OWNER.has(owner.toLowerCase())) return undefined
  return `${owner}/${repo.replace(/\.git$/i, '')}`.toLowerCase()
}

/** A URL the app may show and open: plain http(s), a dotted host, no user / password, the default port, not too long. */
export function safeWebUrl(raw: unknown): string | undefined {
  if (typeof raw !== 'string' || !raw || raw.length > MAX_URL || /\s/.test(raw)) return undefined
  const u = toUrl(raw)
  if (!u || (u.protocol !== 'https:' && u.protocol !== 'http:')) return undefined
  if (u.username || u.password) return undefined
  if (u.port && u.port !== (u.protocol === 'https:' ? '443' : '80')) return undefined
  const host = hostOf(u)
  if (!host.includes('.') || LOCAL.test(host) || IP4.test(host) || host.startsWith('[')) return undefined
  return u.href
}

/** Where a link goes, as the app shows it: the host without "www.", or github.com/<owner>/<repo> for a repo. */
export function siteOf(url: string | undefined): string | undefined {
  const u = url ? toUrl(url) : undefined
  if (!u) return undefined
  const repo = githubRepo(u)
  return repo ? `github.com/${repo}` : hostOf(u) || undefined
}

export function kindOf(url: string): WebKind {
  const u = toUrl(url)
  return u && githubRepo(u) ? 'github' : 'web'
}

/**
 * A pasted or dropped link to a page (not YouTube). null for plain text, a YouTube link, a local or private address,
 * or a link with credentials. With "https://" (or "http://") any dotted host counts; bare text needs a "www.", a path
 * or a common TLD, so typed goals with a dot ("numpy.array", "node.js") stay goals.
 */
export function parseWebLink(text: string): WebLink | null {
  const raw = text.trim()
  if (!raw || /\s/.test(raw) || raw.length > MAX_URL) return null
  const schemed = /^https?:\/\//i.test(raw)
  if (!schemed && /^[a-z][a-z0-9+.-]*:/i.test(raw) && !/^[^/:]+:\d/.test(raw)) return null // mailto:, file:, javascript:…
  const url = safeWebUrl(schemed ? raw : `https://${raw}`)
  const u = url ? toUrl(url) : undefined
  if (!url || !u) return null
  const host = hostOf(u)
  if (YOUTUBE.test(host)) return null
  if (!schemed) {
    const tld = host.split('.').pop() ?? ''
    const pathy = /^[^/]+\/./.test(raw)
    if (!/^www\./i.test(raw) && !pathy && !COMMON_TLDS.has(tld)) return null
    if (!/^[a-z]{2,24}$/.test(tld)) return null
  }
  return { url, kind: githubRepo(u) ? 'github' : 'web', site: siteOf(url) ?? host }
}

/**
 * The comparison form of a link (the app's side of the engine's normalize_link_url): https, host without "www.",
 * no fragment, no tracking parameters (the rest sorted), no trailing slash, github owner / repo lower case.
 */
export function linkKey(url: string | undefined): string | undefined {
  const u = url ? toUrl(url.trim()) : undefined
  if (!u || (u.protocol !== 'https:' && u.protocol !== 'http:')) return undefined
  const params = [...u.searchParams.entries()].filter(([k]) => !TRACKING.test(k)).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
  const query = params.length ? `?${new URLSearchParams(params).toString()}` : ''
  const repo = githubRepo(u)
  let path = u.pathname.replace(/\/{2,}/g, '/')
  if (repo) {
    const rest = path.split('/').filter(Boolean).slice(2)
    path = `/${repo}${rest.length ? `/${rest.join('/')}` : ''}`
  }
  if (path.length > 1) path = path.replace(/\/$/, '')
  return `https://${hostOf(u)}${path || '/'}${query}`
}

export const sameLink = (a: string | undefined, b: string | undefined): boolean => {
  const ka = linkKey(a)
  return !!ka && ka === linkKey(b)
}

/** What the card's one primary does, and the words on it. */
export type PageAction =
  | { kind: 'build'; label: string }
  | { kind: 'teach'; label: string; goal: string }
  | { kind: 'wait'; label: string }
  | { kind: 'none'; label: '' }

/**
 * ANY-LINK.md launcher behaviour: teachable → Build lesson (Start lesson when it is already built: `cached`); not
 * teachable → "Just teach me" on the page's title; an error → nothing; no answer yet (or only the fast pending one)
 * → wait. `teachLabel`: the launcher's own name for "Just teach me" (parts.HOW_LABEL.lesson), so one action has one name.
 */
export function pageAction(p: Pick<LinkPreview, 'pending' | 'teachable' | 'error' | 'cached' | 'title'> | undefined, teachLabel = 'Just teach me'): PageAction {
  if (p?.error) return { kind: 'none', label: '' }
  if (!p || p.teachable === undefined) return { kind: 'wait', label: 'Reading the page…' }
  if (p.teachable) return { kind: 'build', label: p.cached ? 'Start lesson' : 'Build lesson' }
  return p.title ? { kind: 'teach', label: teachLabel, goal: p.title } : { kind: 'none', label: '' }
}

/** The calm line for a page that can't be read (LookupError), in the launcher's voice. */
export const LOOKUP_LINE: Record<LookupError, string> = {
  not_found: 'miyagi couldn’t open that page.',
  private: 'That page is private.',
  unsupported: 'miyagi can’t read this kind of link.',
  offline: 'miyagi is offline. Try again when it connects.',
  too_long: 'That page is too long for one lesson.',
  busy: 'miyagi is busy. Try again in a moment.',
  unknown: 'That didn’t work. Try again.',
  blocked: 'That site won’t let miyagi read it.'
}

export const lookupLine = (e: LookupError | undefined): string => (e && Object.prototype.hasOwnProperty.call(LOOKUP_LINE, e) ? LOOKUP_LINE[e] : LOOKUP_LINE.unknown)

/** "Web page" / "GitHub repo": the card's kind word. */
export const KIND_LABEL: Record<WebKind, string> = { web: 'Web page', github: 'GitHub repo' }

/** "About 10 min". */
export const minutesText = (m: number | undefined): string | undefined => (m && m > 0 ? `About ${Math.round(m)} min` : undefined)

/** Is this BuildSource a page (web / github) with a URL the app may open? */
export function pageSource(s: BuildSource | undefined | null): (BuildSource & { kind: WebKind; url: string }) | undefined {
  if (!s || (s.kind !== 'web' && s.kind !== 'github')) return undefined
  const url = safeWebUrl(s.url)
  return url ? { ...s, kind: s.kind, url } : undefined
}
