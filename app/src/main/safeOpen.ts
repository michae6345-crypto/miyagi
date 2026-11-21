/**
 * Core (v2, W0-6): the ONE way out of the app to a browser, a mail client or System Settings. Every new
 * shell.openExternal goes through here (BUILD-PLAN Section 6).
 *
 *   safeOpenExternal(url)       https on an allowlisted host, or a plain mailto:; anything else is refused (false)
 *   safeOpenExternal({setup})   a setup card's Download button: openSetupDownload's stricter list (below)
 *   openSetupDownload(url)      https on SETUP_HOSTS (GitHub only under SETUP_GITHUB_ORGS) → opened; anything else is
 *                               handed back as copy-only text and never opened
 *   openLinkInBrowser(url)      the window-open handler only: any plain https link (no user, password or odd port)
 *   openSystemSettings(kind)    a fixed x-apple.systempreferences: URL from an enum, never a URL from a renderer
 *   debugFlagIn(argv)           the packaged-startup guard's test (index.ts): a debugger / remote-debugging switch
 *
 * Renderer: bridge.invoke('open:external', url | {setup: url}) → boolean. System Settings only via
 * permissions:open(kind) (main/permissions.ts), which calls openSystemSettings here.
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
 * Where a setup card's Download button may send the learner (app-harden). A setup item's URL comes from the engine,
 * which may have taken it from a video description or a page Claude read: a prompt-injected "download fastcli.pkg"
 * must never open. Exact host or a subdomain of one. Kept to the official download pages the engine's setup CATALOG
 * (server/workspace/setup.py on integration/live) links to, plus the usual installers. Cursor (in the CATALOG) is left
 * out on purpose: miyagi never offers it.
 */
export const SETUP_HOSTS = [
  'python.org', // www.python.org/downloads
  'nodejs.org',
  'code.visualstudio.com',
  'brew.sh',
  'git-scm.com',
  'rustup.rs', // CATALOG rust
  'go.dev', // CATALOG go
  'adoptium.net', // CATALOG java
  'docker.com', // CATALOG docker
  'blender.org', // CATALOG blender
  'figma.com', // CATALOG figma
  'unity.com', // CATALOG unity
  'jupyter.org', // CATALOG jupyter
  'pypi.org', // the engine's ipykernel row
  'platform.openai.com', // CATALOG web apps (their "open" rows go through the engine; listed in case a row downloads)
  'chatgpt.com',
  'app.botpress.cloud',
  'zapier.com',
  'sheets.google.com'
] as const

/** github.com only under these orgs (github.com/<org>/…): a tool's own releases, never any repo. Lowercase. */
export const SETUP_GITHUB_ORGS = ['python', 'nodejs', 'nvm-sh', 'homebrew', 'git-for-windows', 'microsoft', 'astral-sh', 'rust-lang', 'golang', 'jupyter', 'conda-forge', 'adoptium', 'docker'] as const

function parse(raw: unknown): URL | undefined {
  if (typeof raw !== 'string' || raw.length > MAX_URL) return undefined
  try {
    return new URL(raw)
  } catch {
    return undefined
  }
}

const onHost = (host: string, list: readonly string[]): boolean => list.some((h) => host === h || host.endsWith(`.${h}`))

/** Would a setup card's Download button open this? Plain https on SETUP_HOSTS, or github.com/<known org>/… */
export function isSetupDownloadUrl(raw: unknown): boolean {
  const u = parse(raw)
  if (!u || !isPlainHttps(u)) return false
  const host = u.hostname.toLowerCase()
  if (host === 'github.com' || host === 'www.github.com') {
    const org = (u.pathname.split('/')[1] ?? '').toLowerCase()
    return (SETUP_GITHUB_ORGS as readonly string[]).includes(org)
  }
  return onHost(host, SETUP_HOSTS)
}

/** copy: the URL to show as text with a Copy button (plain https only); absent = nothing worth showing. */
export type SetupOpen = { opened: true } | { opened: false; copy?: string }

/**
 * A setup card's Download button. On the setup list → the default browser. Anything else is never opened: a plain
 * https URL comes back as copy-only text (the card shows it with a Copy button); any other string comes back empty.
 */
export async function openSetupDownload(raw: unknown): Promise<SetupOpen> {
  if (!isSetupDownloadUrl(raw)) {
    console.warn('[safeOpen] a setup download is not on the setup list; shown as text, not opened')
    const u = parse(raw)
    return u && isPlainHttps(u) ? { opened: false, copy: u.href } : { opened: false }
  }
  try {
    await shell.openExternal(new URL(raw as string).href, { activate: true })
    return { opened: true }
  } catch {
    return { opened: false }
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
 * The overview footer's Stats link (features/overview.ts): the local engine's own /stats page, http on this Mac's
 * loopback, any port, that exact path, nothing else (no user, query or fragment). An engine on another host is refused.
 */
export function isEngineStatsUrl(raw: unknown): boolean {
  const u = parse(raw)
  if (!u || (u.protocol !== 'http:' && u.protocol !== 'https:') || u.username || u.password || u.search || u.hash) return false
  return ['localhost', '127.0.0.1', '[::1]'].includes(u.hostname) && u.pathname === '/stats'
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
 * {setup: url} (a setup card's Download button) is checked against the stricter setup list instead (openSetupDownload).
 */
export async function safeOpenExternal(raw: unknown): Promise<boolean> {
  if (raw && typeof raw === 'object' && 'setup' in raw) return (await openSetupDownload((raw as { setup: unknown }).setup)).opened
  if (!isAllowedUrl(raw) && !isEngineStatsUrl(raw)) {
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
export const DEBUG_SWITCHES = ['inspect', 'inspect-brk', 'inspect-port', 'inspect-publish-uid', 'remote-debugging-port', 'remote-debugging-pipe', 'remote-debugging-address', 'js-flags'] as const

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
