/**
 * Core (v2, W0-6): the ONE way out of the app to a browser, a mail client or System Settings. Every new
 * shell.openExternal goes through here (BUILD-PLAN Section 6).
 *
 *   safeOpenExternal(url)       https on an allowlisted host, or a plain mailto:; anything else is refused (false)
 *   openLinkInBrowser(url)      the window-open handler only: any plain https link (no user, password or odd port)
 *   openSystemSettings(kind)    a fixed x-apple.systempreferences: URL from an enum, never a URL from a renderer
 *
 * Renderer: bridge.invoke('open:external', url) → boolean. System Settings only via permissions:open(kind)
 * (main/permissions.ts), which calls openSystemSettings here.
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

/** Open an allowlisted URL in the default browser / mail client. false = refused or failed (never throws). */
export async function safeOpenExternal(raw: unknown): Promise<boolean> {
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
