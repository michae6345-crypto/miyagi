/**
 * Core (v2, W0-6): the ONE way out of the app to a browser, a mail client or System Settings. Every new
 * shell.openExternal goes through here (BUILD-PLAN Section 6).
 *
 *   safeOpenExternal(url)       https on an allowlisted host, or a plain mailto:; anything else is refused (false)
 *   safeOpenExternal({setup})   a setup card's Download or Open button: openSetupDownload's stricter list → SetupOpen
 *   openSetupDownload(url)      https on one of SETUP_PAGES (exact host + official download path; GitHub only as a
 *                               SETUP_GITHUB_REPOS repo page or its releases list) → opened; anything else is handed
 *                               back as copy-only text and never opened
 *   openEngineStats(url, port)  overview.ts's Stats link only: the local engine's /stats on its own port
 *   openLinkInBrowser(url)      the window-open handler only: any plain https link (no user, password or odd port)
 *   openSystemSettings(kind)    a fixed x-apple.systempreferences: URL from an enum, never a URL from a renderer
 *   debugFlagIn(argv)           the packaged-startup guard's test (index.ts): a debugger / remote-debugging switch
 *
 * Renderer: bridge.invoke('open:external', url) → boolean; bridge.invoke('open:external', {setup: url}) → SetupOpen.
 * System Settings only via permissions:open(kind) (main/permissions.ts), which calls openSystemSettings here.
 *
 * This file is the ONLY place that calls shell.openExternal: test/safeOpenGrep.test.ts fails on any other, except
 * features/player.ts (Adrian's A14).
 */
import { shell } from 'electron'
import type { PermissionKind } from '../../../shared/contracts/events'
import { SUPABASE_HOST } from './publicConfig'

/** https hosts the app may open (exact host or a subdomain of one). Keep it short; add a host with a reason. */
export const ALLOWED_HOSTS = [
  'youtube.com', // the tutorial the lesson follows, "Open in YouTube"
  'youtu.be',
  'miyagi.study', // our site, privacy page, pricing
  'code.visualstudio.com', // "Get VS Code" (onboarding)
  'marketplace.visualstudio.com', // the companion / Python / Jupyter extensions
  'console.anthropic.com', // Settings › Account: where to get a key (BYOK)
  'aistudio.google.com',
  'elevenlabs.io',
  'github.com', // the engine's install notes
  SUPABASE_HOST // Google sign-in's start page (features/auth.ts): the committed project only (main/publicConfig.ts)
] as const

/** System Settings panes, by kind. Fixed strings: nothing from a renderer is ever appended. */
export const SETTINGS_URL: Record<PermissionKind, string> = {
  screen: 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture',
  accessibility: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility',
  automation: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Automation'
}

const MAX_URL = 2048
const EMAIL = /^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$/

/**
 * Where a setup card's Download or Open button may send the learner (app-harden). A setup item's URL comes from the engine,
 * which may have taken it from a video description or a page Claude read: a prompt-injected "download fastcli.pkg"
 * (or a malicious PyPI / Go module page on an official host) must never open. So: an exact host (a "www." in front is
 * the same host, nothing else is) AND one of that host's official download pages. A path matches when it is that
 * page or under it by whole segments (/downloads matches /downloads/macos/, never /downloads-evil). '/' alone means
 * the home page only. Kept to the pages the engine's setup CATALOG (server/workspace/setup.py on integration/live)
 * links to, plus the usual installers. Cursor (in the CATALOG) is left out on purpose: miyagi never offers it.
 */
export const SETUP_PAGES: Readonly<Record<string, readonly string[]>> = {
  'python.org': ['/downloads'], // CATALOG python: www.python.org/downloads/macos/
  'nodejs.org': ['/en/download', '/download'], // CATALOG node, npm
  'code.visualstudio.com': ['/download', '/docs/setup'], // CATALOG vscode
  'brew.sh': ['/'],
  'git-scm.com': ['/download', '/downloads', '/install'], // CATALOG git: git-scm.com/download/mac
  'rustup.rs': ['/'], // CATALOG rust
  'go.dev': ['/dl'], // CATALOG go: go.dev/dl/ (never go.dev/<module> or pkg.go.dev: that is anyone's code)
  'adoptium.net': ['/', '/temurin/releases'], // CATALOG java
  'docker.com': ['/products/docker-desktop'], // CATALOG docker
  'blender.org': ['/download'], // CATALOG blender
  'figma.com': ['/downloads'], // CATALOG figma
  'unity.com': ['/download'], // CATALOG unity
  'jupyter.org': ['/install'], // CATALOG jupyter
  // The engine's ipykernel row and the Jupyter family; never pypi.org/project/<anything>.
  'pypi.org': ['/project/ipykernel', '/project/jupyter', '/project/notebook', '/project/jupyterlab'],
  // CATALOG web apps: rows with install.method "open" (kind web_app). Claude's requirements may call any tool a web_app
  // with any https URL (setup.py), so the Open button comes through this list too, never straight to the engine.
  'platform.openai.com': ['/'],
  'chatgpt.com': ['/'],
  'app.botpress.cloud': ['/'],
  'zapier.com': ['/app/home'],
  'sheets.google.com': ['/']
}

/**
 * github.com only for these exact repos (a tool's own installer), and only as the repo page, /releases or
 * /releases/latest: never a release asset (/releases/download/…, a .pkg straight into Downloads), a tag, issues, a
 * wiki or files. A whole org is too wide: in an org of community repos (conda-forge's feedstocks) whoever becomes a
 * maintainer of one can publish a release. No CATALOG row links to GitHub; these are the usual installers.
 * Lowercase "org/repo".
 */
export const SETUP_GITHUB_REPOS = ['python/cpython', 'nodejs/node', 'nvm-sh/nvm', 'homebrew/brew', 'git-for-windows/git', 'astral-sh/uv', 'rust-lang/rustup'] as const

/**
 * A percent-encoded "/", "\" or "." in a path: the URL parser keeps it, but a server that decodes it first (nginx)
 * walks out of the allowed page (/downloads/..%2F..%2Fevil). An encoded "%" too, so a double-encoded %252e can't get
 * past a server that decodes twice. No real download page needs one.
 */
const ENCODED_TRAVERSAL = /%(?:2f|5c|2e|25)/i

function parse(raw: unknown): URL | undefined {
  if (typeof raw !== 'string' || raw.length > MAX_URL) return undefined
  try {
    return new URL(raw)
  } catch {
    return undefined
  }
}

/** path is page, or under it by whole segments. '/' is the home page only. */
const underPage = (path: string, page: string): boolean => (page === '/' ? path === '/' : path === page || path.startsWith(`${page}/`))

/**
 * Would a setup card's Download / Open button open this? Plain https on one of SETUP_PAGES, or one of
 * SETUP_GITHUB_REPOS' repo page, /releases or /releases/latest. A percent-encoded "/", "\", "." or "%" in the path is
 * refused, and so is any query or fragment: no setup page needs one, and on an allowlisted host or login page a
 * ?url= / #next= could redirect anywhere.
 */
export function isSetupDownloadUrl(raw: unknown): boolean {
  const u = parse(raw)
  // href, not search/hash: those read '' for a bare '?' or '#', which href keeps.
  if (!u || !isPlainHttps(u) || /[?#]/.test(u.href) || ENCODED_TRAVERSAL.test(u.pathname)) return false
  const host = u.hostname.toLowerCase().replace(/^www\./, '')
  if (host === 'github.com') {
    // One trailing slash is the same page. After the repo: nothing, releases or releases/latest; anything else is refused.
    const [, org = '', repo = '', ...rest] = u.pathname.replace(/(.)\/$/, '$1').split('/')
    if (!(SETUP_GITHUB_REPOS as readonly string[]).includes(`${org}/${repo}`.toLowerCase())) return false
    const tail = rest.join('/')
    return tail === '' || tail === 'releases' || tail === 'releases/latest'
  }
  const pages = Object.prototype.hasOwnProperty.call(SETUP_PAGES, host) ? SETUP_PAGES[host] : undefined
  return !!pages && pages.some((p) => underPage(u.pathname, p))
}

/**
 * What a setup card's Download button got. opened: in the browser. Else refused: not on the setup list (copy: the URL
 * to show as text with a Copy button, plain https only; absent = nothing worth showing), or failed (refused: false):
 * on the list, but the system could not open it (the button stays, so the learner can try again).
 */
export type SetupOpen = { opened: true } | { opened: false; refused: true; copy?: string } | { opened: false; refused: false }

/**
 * A setup card's Download or Open button. On the setup list → the default browser. Anything else is never opened: a plain
 * https URL comes back as copy-only text (the card shows it with a Copy button); any other string comes back empty.
 */
export async function openSetupDownload(raw: unknown): Promise<SetupOpen> {
  if (!isSetupDownloadUrl(raw)) {
    console.warn('[safeOpen] a setup download is not on the setup list; shown as text, not opened')
    const u = parse(raw)
    return u && isPlainHttps(u) ? { opened: false, refused: true, copy: u.href } : { opened: false, refused: true }
  }
  try {
    await shell.openExternal(new URL(raw as string).href, { activate: true })
    return { opened: true }
  } catch {
    return { opened: false, refused: false }
  }
}

/** Is this a URL safeOpenExternal (the open:external IPC) would open? */
export function isAllowedUrl(raw: unknown): boolean {
  if (typeof raw !== 'string' || raw.length > MAX_URL) return false
  let u: URL
  try {
    u = new URL(raw)
  } catch {
    return false
  }
  if (u.protocol === 'mailto:') {
    // A plain address and at most a subject: never a body or cc built from a page.
    // A malformed % sequence (mailto:a%E0@b.co) makes decodeURIComponent throw: refuse it, never throw from here
    // (this runs inside the window-open handler).
    try {
      const keys = [...u.searchParams.keys()]
      return EMAIL.test(decodeURIComponent(u.pathname)) && keys.every((k) => k === 'subject')
    } catch {
      return false
    }
  }
  if (!isPlainHttps(u)) return false
  const host = u.hostname.toLowerCase()
  return ALLOWED_HOSTS.some((h) => host === h || host.endsWith(`.${h}`))
}

function isPlainHttps(u: URL): boolean {
  return u.protocol === 'https:' && !u.username && !u.password && (!u.port || u.port === '443')
}

/**
 * The overview footer's Stats link (features/overview.ts only, never the open:external IPC): the local engine's own
 * /stats page on this Mac's loopback, on the engine's port only, that exact path, nothing else (no user, query or
 * fragment). An engine on another host is refused.
 */
export function isEngineStatsUrl(raw: unknown, port: number): boolean {
  const u = parse(raw)
  if (!u || (u.protocol !== 'http:' && u.protocol !== 'https:') || u.username || u.password || u.search || u.hash) return false
  const at = Number(u.port || (u.protocol === 'https:' ? 443 : 80))
  return ['localhost', '127.0.0.1', '[::1]'].includes(u.hostname) && u.pathname === '/stats' && at === port
}

/** overview.ts's Stats link: opens only what isEngineStatsUrl(url, port) accepts. false = refused or failed. */
export async function openEngineStats(raw: unknown, port: number): Promise<boolean> {
  if (!isEngineStatsUrl(raw, port)) {
    console.warn('[safeOpen] refused a Stats link that is not the local engine')
    return false
  }
  try {
    await shell.openExternal(new URL(raw as string).href, { activate: true })
    return true
  } catch {
    return false
  }
}

/**
 * The window-open handler's test (a learner clicking a link in our own page: setup download rows, card and
 * off-track citations, drawer sources). Any plain https URL: no username, no password, no port other than 443.
 * Every other scheme is refused, except a plain mailto that isAllowedUrl accepts. The open:external IPC stays on
 * isAllowedUrl (strict allowlist): that channel takes a string from renderer code, not from a learner's click.
 */
export function isBrowserLink(raw: unknown): boolean {
  if (typeof raw !== 'string' || raw.length > MAX_URL) return false
  let u: URL
  try {
    u = new URL(raw)
  } catch {
    return false
  }
  if (u.protocol === 'mailto:') return isAllowedUrl(raw)
  return isPlainHttps(u)
}

/** Open a clicked link (window.open / target=_blank) in the default browser. false = refused or failed (never throws). */
export async function openLinkInBrowser(raw: unknown): Promise<boolean> {
  if (!isBrowserLink(raw)) {
    console.warn('[safeOpen] refused a link that is not plain https')
    return false
  }
  try {
    await shell.openExternal(new URL(raw as string).href, { activate: true })
    return true
  } catch {
    return false
  }
}

/**
 * Open an allowlisted URL in the default browser / mail client. false = refused or failed (never throws).
 * {setup: url} (a setup card's Download or Open button) is checked against the stricter setup list instead and answers with
 * openSetupDownload's SetupOpen (so the card can tell "not on the list" from "the browser didn't open").
 */
export function safeOpenExternal(raw: string): Promise<boolean>
export function safeOpenExternal(raw: { setup: unknown }): Promise<SetupOpen>
export function safeOpenExternal(raw: unknown): Promise<boolean | SetupOpen>
export async function safeOpenExternal(raw: unknown): Promise<boolean | SetupOpen> {
  if (raw && typeof raw === 'object' && 'setup' in raw) return openSetupDownload((raw as { setup: unknown }).setup)
  if (!isAllowedUrl(raw)) {
    console.warn('[safeOpen] refused a URL that is not on the allowlist')
    return false
  }
  try {
    await shell.openExternal(new URL(raw as string).href, { activate: true })
    return true
  } catch {
    return false
  }
}

/** Open one System Settings pane (macOS). false on other platforms or an unknown kind. */
export async function openSystemSettings(kind: unknown): Promise<boolean> {
  if (process.platform !== 'darwin' || typeof kind !== 'string' || !Object.prototype.hasOwnProperty.call(SETTINGS_URL, kind)) return false
  try {
    await shell.openExternal(SETTINGS_URL[kind as PermissionKind])
    return true
  } catch {
    return false
  }
}

/** Push to talk's two Privacy panes (not PermissionKinds: the engine never asks for them). Fixed strings, like SETTINGS_URL. */
export const PTT_SETTINGS_URL = {
  mic: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone',
  input: 'x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent'
} as const

/** Open the Microphone or Input Monitoring pane (macOS). false on other platforms or an unknown kind. */
export async function openPttSettings(kind: unknown): Promise<boolean> {
  if (process.platform !== 'darwin' || (kind !== 'mic' && kind !== 'input')) return false
  try {
    await shell.openExternal(PTT_SETTINGS_URL[kind])
    return true
  } catch {
    return false
  }
}

// ---- the packaged-startup guard (index.ts) --------------------------------------------------------------------
// Here with the other "what may leave or enter the app" checks, so it is a pure function a test can import without
// starting the app.

/**
 * Switches a packaged build refuses to start with (index.ts quits before any window or engine). Node's inspector
 * flags are also off by fuse (electron-builder.yml enableNodeCliInspectArguments); Chromium's --remote-debugging-*
 * and --js-flags are covered by no fuse, so this check is their only stop.
 */
export const DEBUG_SWITCHES = [
  'inspect',
  'inspect-brk',
  'inspect-brk-node', // Electron's: break in Node's own bootstrap
  'inspect-wait', // Node 22
  'inspect-port',
  'inspect-publish-uid',
  'debug', // Node's older spellings of the same inspector
  'debug-brk',
  'debug-port',
  'remote-debugging-port',
  'remote-debugging-pipe',
  'remote-debugging-address',
  'js-flags'
] as const

/**
 * The first debug switch in argv (its name), or undefined. Matches --x, --x=…, -x and -x=… in any case (Chromium
 * also takes one dash and lowercases switches on Windows, where /x works too), anywhere in argv, also after "--".
 */
export function debugFlagIn(argv: readonly unknown[], windows = process.platform === 'win32'): string | undefined {
  const re = windows ? /^(?:-{1,2}|\/)([A-Za-z][A-Za-z0-9-]*)(?:=|$)/ : /^-{1,2}([A-Za-z][A-Za-z0-9-]*)(?:=|$)/
  for (const a of argv) {
    if (typeof a !== 'string') continue
    const name = re.exec(a)?.[1]?.toLowerCase()
    if (name && (DEBUG_SWITCHES as readonly string[]).includes(name)) return name
  }
  return undefined
}
