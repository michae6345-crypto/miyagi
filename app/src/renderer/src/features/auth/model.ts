/**
 * Feature: auth (first-run login). Types and the small pure helpers the views share.
 *
 * Nothing secret ever reaches the renderer: main keeps the session (safeStorage) and answers `auth:get` with a name
 * and an email only. No token, code or email goes into a URL, localStorage or a log.
 */
import { isElectron } from '../../bridge'

/**
 * The login surfaces exist at all: same switch as the account sheet (v2Cloud). On in the browser stage, or in a build
 * made with VITE_MIYAGI_V2_CLOUD=1. Main answers `{ok:false, reason:'off'}` unless MIYAGI_V2_CLOUD=1.
 */
export const authOn: boolean = !isElectron || import.meta.env.VITE_MIYAGI_V2_CLOUD === '1'

export type Mode = 'new' | 'returning'
export type Provider = 'google' | 'apple' | 'github'

export type User = { name?: string; email?: string }

/** Which providers are live. Only Google for now; the others are placeholders that send nothing. */
export const LIVE: Record<Provider, boolean> = { google: true, apple: false, github: false }
export const PROVIDER_LABEL: Record<Provider, string> = { google: 'Google', apple: 'Apple', github: 'GitHub' }

/** Main's answer to auth:google. */
export type SignInResult = { ok: true; user: User } | { ok: false; reason?: string }

/** The calm line for a failed sign-in, by main's reason. undefined = say nothing (the learner cancelled). */
export function reasonLine(reason?: string): string | undefined {
  switch (reason) {
    case 'cancelled':
      return undefined
    case 'off':
    case 'not-configured':
      return 'Google sign-in is not set up in this build yet.'
    case 'timeout':
      return 'The browser sign-in timed out. Try again.'
    case 'port':
      return 'Another app is using the sign-in port. Quit it and try again.'
    case 'denied':
      return 'Google sign-in was declined.'
    default:
      return 'Sign-in did not finish. Try again.'
  }
}

/** A plain, bounded copy of what came over IPC. */
export function cleanUser(raw: unknown): User | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  if (r.signedIn === false) return null
  const str = (v: unknown, max: number): string | undefined => (typeof v === 'string' && v.trim() ? v.trim().slice(0, max) : undefined)
  const user = { name: str(r.name, 80), email: str(r.email, 254) }
  return user.name || user.email ? user : null
}
