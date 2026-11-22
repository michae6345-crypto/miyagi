/**
 * Feature: auth (first-run login). Types and the small pure helpers the views share.
 *
 * Nothing secret ever reaches the renderer: main keeps the session (safeStorage) and answers `auth:get` with
 * {name, email, avatarInitial} only. No token, code or email goes into a URL, localStorage or a log.
 */
import { LOGIN_ENABLED } from '../../../../common/flags'

/** The login exists at all (common/flags.ts LOGIN_ENABLED; main also honors MIYAGI_LOGIN=0). Separate from v2Cloud. */
export const authOn: boolean = LOGIN_ENABLED

export type Mode = 'new' | 'returning'
export type Provider = 'google' | 'apple' | 'github'

export type User = { name?: string; email?: string; avatarInitial: string }

/** Which providers are live. Only Google for now; the others are placeholders that send nothing. */
export const LIVE: Record<Provider, boolean> = { google: true, apple: false, github: false }
export const PROVIDER_LABEL: Record<Provider, string> = { google: 'Google', apple: 'Apple', github: 'GitHub' }

/** Fixed pages the login links to (open:external, allowlisted miyagi.study). Nothing is ever appended. */
export const LEGAL = { terms: 'https://miyagi.study/terms', privacy: 'https://miyagi.study/privacy' } as const

/** Main's answer to auth:google. */
export type SignInResult = { ok: true; user: unknown } | { ok: false; reason?: string; message?: string }

/** The learner pressed Cancel (or Esc) in miyagi while the browser was open. */
export const CANCELLED_LINE = 'Sign-in cancelled.'
/** The learner came back to miyagi mid-wait (closed the browser tab, gave up): the wait ends, the sign-in may still land. */
export const BACK_LINE = "Didn't finish in the browser? Try again."

/**
 * The line for a failed sign-in. Main's message (the plain-words why: Google's / Supabase's error, the refused
 * exchange, Cancel on Google's page, the timeout) wins; else a line by main's reason. Always a line: a cancel says so
 * calmly, and the Try again under it starts over.
 */
export function reasonLine(reason?: string, message?: unknown): string {
  const m = typeof message === 'string' ? message.replace(/\s+/g, ' ').trim().slice(0, 240) : ''
  if (m) return m
  switch (reason) {
    case 'cancelled':
      return CANCELLED_LINE
    case 'off':
    case 'not-configured':
      return 'Google sign-in is not set up yet. Continue without an account.'
    case 'timeout':
      return 'No answer from Google, so miyagi stopped waiting. Try again.'
    case 'port':
      return 'Sign-in could not start. Try again, or continue without an account.'
    case 'denied':
      // Main sends the tester line itself, and only for Google's own not-a-tester error (R20). Without it: neutral.
      return "This Google account can't sign in yet. Try another, or continue without an account."
    case 'provider':
      return 'Google sign-in is not set up correctly yet. Continue without an account for now.'
    default:
      return 'Sign-in did not finish. Try again.'
  }
}

/** A plain, bounded copy of what came over IPC: {name, email, avatarInitial}, nothing else. */
export function cleanUser(raw: unknown): User | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  if (r.signedIn === false) return null
  const str = (v: unknown, max: number): string | undefined => (typeof v === 'string' && v.trim() ? v.trim().slice(0, max) : undefined)
  const name = str(r.name, 80)
  const email = str(r.email, 254)
  if (!name && !email) return null
  const initial = [...(str(r.avatarInitial, 4) ?? name ?? email ?? 'm')][0].toLocaleUpperCase()
  return { name, email, avatarInitial: initial }
}
