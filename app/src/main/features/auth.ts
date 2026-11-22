/**
 * Main-process feature: auth (first-run login; renderer: src/renderer/src/features/auth/).
 *
 * Google sign-in through Supabase Auth, the way Google allows it on desktop: the SYSTEM browser (never a webview),
 * OAuth 2.0 PKCE, and a one-shot loopback redirect on 127.0.0.1. Supabase holds the Google client secret; this app
 * only ever has the project URL and its publishable key (main/publicConfig.ts), which are public by design.
 *
 *   1. auth:google  → make a PKCE verifier + S256 challenge and a random state, listen once on
 *                     http://127.0.0.1:47217/auth/callback, open
 *                     <project>/auth/v1/authorize?provider=google&redirect_to=<callback>?state=…&code_challenge=… in the
 *                     browser (through safeOpen).
 *   2. The browser comes back to the loopback with ?state=…&code=…. A request whose state does not match this flow's is
 *      ignored (404) and does not end the flow; then we answer a small "you can close this tab" page.
 *   3. POST <project>/auth/v1/token?grant_type=pkce {auth_code, code_verifier} → session.
 *   4. The session (access + refresh token, name, email) is kept ONLY in userData/auth.bin, encrypted with safeStorage
 *      (login Keychain), exactly like the BYOK keys in settings.ts. Without safeStorage it lives for this run only.
 *   5. Refresh: a timer refreshes the access token ~5 min before it expires (grant_type=refresh_token, one request at a
 *      time: Supabase rotates the refresh token, so two in flight would burn it). Also on launch and on wake. A refresh
 *      token Supabase refuses (400/401) signs the learner out; a network failure retries with a backoff.
 *
 * The renderer only ever sees {name, email, avatarInitial}: never a token, a code or the session file.
 *
 * Handles (bridge.invoke):
 *   auth:get                → {signedIn: true, name?, email?, avatarInitial} | null
 *   auth:google ({mode})    → {ok:true, user} | {ok:false, reason: off|not-configured|port|timeout|denied|provider|cancelled|failed,
 *                             message?} (message: the plain-words why, from Google's / Supabase's error_description or the
 *                             refused exchange; the renderer shows it as is)
 *   auth:cancel             stop waiting for the browser → true
 *   auth:continue           the learner is done with the login (signed in, or "Continue without an account", which
 *                           is always offered). The guest choice lasts for this run only (memory, never a file): every
 *                           launch without a Google session starts at the login again. In the one-window flow (the
 *                           login is a screen of the home window) nothing opens and nothing closes: the flow moves on
 *                           by itself. Only the standalone login window (a fallback) hands over: home opens when setup
 *                           isn't done, then the login window closes
 *   auth:sign-out           revoke (best effort) and forget the session → true. The launch gate closes: the overlay
 *                           goes away and home returns to the login
 *
 * Launch gate (main/gate.ts, part 'login'; Michael Nov 21: "allow me to log in first, like it's just starting from
 * new"): open with a stored session, after a Google sign-in, after "Continue without an account" in this run, with
 * login switched off, or with MIYAGI_SKIP_LOGIN=1 (dev, tests). Closed on sign-out. An old userData/login.json (the
 * "decided" choice that used to skip the login forever) is ignored and never written.
 * Broadcast: feat:auth:changed  {name, email, avatarInitial} | null  (sign-in, refresh that changed the user, sign-out)
 *
 * Switch: LOGIN_ENABLED (common/flags.ts), off for one run with MIYAGI_LOGIN=0. Separate from v2Cloud (account.ts).
 *
 * Supabase dashboard, once: Authentication › Providers › Google on (client ID + secret from Google Cloud), and
 * Authentication › URL Configuration › Redirect URLs: exactly http://127.0.0.1:47217/auth/callback, no wildcard. That
 * entry is documentation more than a gate: Supabase Auth accepts ANY loopback-IP redirect_to (127.0.0.1 / ::1, any
 * port, any path) before it even reads the Redirect URLs list (supabase/auth internal/utilities/request.go,
 * IsRedirectURLValid: `net.ParseIP(host).IsLoopback()` returns true). So the list can't stop a local process from asking
 * for a code sent to its own loopback port. What protects the sign-in is PKCE S256 (a code is useless without this
 * flow's verifier, which never leaves main) plus our own state (192 random bits, constant-time compare).
 *
 * Callback rules (app-harden): only GET, only the exact path /auth/callback, only Host 127.0.0.1:47217, only the params
 * code, state, error, error_code and error_description (each once). A matching-state callback whose code is refused
 * (bad_code_verifier, flow_state_not_found, a junk code) or that carries an error does NOT end the flow: the tab says
 * why (with Try again), main broadcasts auth:attempt {reason, message}, and the listener stays until the 5-minute
 * timeout, which then answers with the last reason (or TIMEOUT_MESSAGE when nothing came back). The renderer ends its
 * "Waiting for Google…" on auth:attempt right away (R20), so Cancel on Google's page (a bare access_denied: reason
 * 'cancelled', CANCELLED_MESSAGE) never leaves the learner waiting; only Google's own not-a-tester wording gets the
 * tester message (explainCallbackError). At most 5 callbacks per flow, then 404; only a callback that passed
 * every check (this flow's state included) counts, so requests without the state can't use the turns up. On success
 * the listener lets go of 47217 when the response closes (finished or dropped by the browser). If 127.0.0.1:47217 is
 * still taken (EADDRINUSE) after ~3 s of retries, the sign-in stops with a plain reason and the browser never opens.
 * redirect_to is built only from constants and this flow's state (redirectTo), never from a request. PKCE only: no
 * implicit flow anywhere.
 *
 * UNVERIFIED in Electron (no live run in this package): the browser round trip, the token exchange and the refresh.
 */
import { powerMonitor, safeStorage, type BrowserWindow } from 'electron'
import { createHash, randomBytes, timingSafeEqual } from 'node:crypto'
import { existsSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs'
import { createServer, type Server } from 'node:http'
import { join } from 'node:path'
import { LOGIN_ENABLED } from '../../common/flags'
import { color } from '../../renderer/src/core/theme'
import { defineMainFeature } from '../context'
import { setGatePart } from '../gate'
import { ageStepCleared } from './agegate'
import { supabaseConfig } from '../publicConfig'
import { isAllowedUrl, openLinkInBrowser, safeOpenExternal } from '../safeOpen'

const PORT = 47217
const CALLBACK_PATH = '/auth/callback'
const CALLBACK_HOST = `127.0.0.1:${PORT}`
export const REDIRECT = `http://${CALLBACK_HOST}${CALLBACK_PATH}`
/** The one OAuth flow there is: PKCE (code + verifier). Never the implicit flow (tokens in a URL). */
export const FLOW_TYPE = 'pkce' as const
/** The query a callback may carry, each at most once. Anything else (access_token from an implicit flow, junk) → 404. */
const CALLBACK_PARAMS = new Set(['code', 'state', 'error', 'error_code', 'error_description'])
/** Callbacks one flow answers (the real one, a retry or two, a stray reload); the rest get 404. */
export const MAX_CALLBACKS = 5
export const WAIT_MS = 5 * 60_000
/**
 * A taken port is tried this many times, this far apart (~3 s), before the sign-in gives up with reason 'port'.
 * Mutable only for tests (the taken-port test holds 47217 for one try, so a parallel test file isn't starved).
 */
export const listenRetry = { tries: 20, ms: 150 }
const FETCH_MS = 15_000
/** Refresh this long before the access token expires. */
const REFRESH_EARLY_MS = 5 * 60_000
const REFRESH_MIN_MS = 30_000
const RETRY_MS = [30_000, 60_000, 2 * 60_000, 5 * 60_000, 10 * 60_000]

type Config = { url: string; key: string }
type User = { name?: string; email?: string }
/** project: the Supabase URL the session belongs to (a session is never sent to any other host). */
type Session = { access: string; refresh: string; expiresAt: number; project?: string; user: User }
/** A finished request: the body is read inside the timeout too (a stalled body can't hang a refresh). */
type Answer = { ok: boolean; status: number; body: unknown }
/** All the renderer ever gets about the learner. */
type PublicUser = { name?: string; email?: string; avatarInitial: string }
/** message: one plain sentence for the learner (what went wrong, what to do), shown in the app and the browser tab. */
type Result = { ok: true; user: PublicUser } | { ok: false; reason: string; message?: string }

/** First-run login is on (the build flag, and not switched off for this run). */
export const loginEnabled = (): boolean => LOGIN_ENABLED && process.env.MIYAGI_LOGIN !== '0'
/** Dev and tests: the login is skipped (the gate's login part is open). */
const skipLogin = (): boolean => process.env.MIYAGI_SKIP_LOGIN === '1'

function config(): Config | undefined {
  const { url, key } = supabaseConfig()
  if (!url || !key) return undefined
  try {
    const u = new URL(url)
    // https only, no credentials, port or path tricks: the browser is sent to this host and nowhere else.
    if (u.protocol !== 'https:' || u.username || u.password || u.port || u.pathname !== '/' || u.search || u.hash) return undefined
  } catch {
    return undefined
  }
  return { url, key }
}

const b64url = (b: Buffer): string => b.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

/** The only redirect_to there is: the constant callback and this flow's state. Never anything from a request. */
export const redirectTo = (state: string): string => `${REDIRECT}?state=${encodeURIComponent(state)}`

/**
 * Supabase's authorize URL for this flow, built from config and constants only. Throws unless it is a PKCE S256
 * request back to our constant callback (a guard against a later edit drifting to the implicit flow).
 */
export function authorizeUrl(projectUrl: string, state: string, challenge: string): string {
  const q = new URLSearchParams({ provider: 'google', redirect_to: redirectTo(state), code_challenge: challenge, code_challenge_method: 's256' })
  const url = `${projectUrl}/auth/v1/authorize?${q.toString()}`
  assertPkce(url)
  return url
}

/** The authorize URL is PKCE: an S256 challenge, our constant redirect, no response_type=token / implicit flow_type. */
export function assertPkce(url: string): void {
  const p = new URL(url).searchParams
  const redirect = p.get('redirect_to') ?? ''
  const ok =
    FLOW_TYPE === 'pkce' &&
    /^[A-Za-z0-9_-]{43,128}$/.test(p.get('code_challenge') ?? '') &&
    p.get('code_challenge_method') === 's256' &&
    !p.has('response_type') &&
    (!p.has('flow_type') || p.get('flow_type') === 'pkce') &&
    redirect.startsWith(`${REDIRECT}?state=`) &&
    new URL(redirect).origin + new URL(redirect).pathname === REDIRECT
  if (!ok) throw new Error('[auth] refusing a non-PKCE authorize URL')
}

/** Constant-time compare of the state that came back with the one this flow sent. */
function sameState(got: string | null, want: string): boolean {
  if (!got) return false
  const a = Buffer.from(got)
  const b = Buffer.from(want)
  return a.length === b.length && timingSafeEqual(a, b)
}

function str(v: unknown, max: number): string | undefined {
  return typeof v === 'string' && v.trim() ? v.trim().slice(0, max) : undefined
}

/** The pieces of Supabase's session answer we keep. Anything malformed → undefined. */
function toSession(raw: unknown): Session | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const r = raw as Record<string, unknown>
  const access = str(r.access_token, 8192)
  const refresh = str(r.refresh_token, 1024)
  if (!access || !refresh) return undefined
  // Absolute expiry: Supabase's expires_at (epoch seconds) when it is there, else now + expires_in. Saved absolute too,
  // so a relaunch hours later sees an expired token as expired (and refreshes it at once).
  const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined)
  const at = num(r.expires_at)
  const expiresIn = num(r.expires_in) ?? 3600
  const u = (r.user && typeof r.user === 'object' ? r.user : {}) as Record<string, unknown>
  const meta = (u.user_metadata && typeof u.user_metadata === 'object' ? u.user_metadata : {}) as Record<string, unknown>
  return {
    access,
    refresh,
    expiresAt: at !== undefined ? at * 1000 : Date.now() + expiresIn * 1000,
    project: str(r.project, 256),
    user: { name: str(meta.full_name, 80) ?? str(meta.name, 80), email: str(u.email, 254) }
  }
}

/** The avatar's letter: the name's first letter, else the email's, else "m". */
function initialOf(u: User): string {
  const ch = [...(u.name ?? u.email ?? '').trim()].find((c) => /\p{L}|\p{N}/u.test(c))
  return (ch ?? 'm').toLocaleUpperCase()
}
const publicUser = (u: User): PublicUser => ({ name: u.name, email: u.email, avatarInitial: initialOf(u) })

/** Text from a URL or a server answer, made safe to show: printable, one line, bounded. */
function plain(v: unknown, max = 200): string | undefined {
  if (typeof v !== 'string') return undefined
  // eslint-disable-next-line no-control-regex
  const s = v.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim()
  return s ? s.slice(0, max) : undefined
}

const escapeHtml = (s: string): string => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

const NOT_ALLOWED = "This Google account isn't allowed yet. Ask to be added as a tester, or continue without an account."
/** Cancel on Google's page (R20): calm, no blame, no tester talk. Ends in "Try again." (the app shows a Try again link). */
export const CANCELLED_MESSAGE = 'Sign-in was cancelled in the browser. Try again.'
const ADMIN_BLOCKED = 'Your school or work account blocks this sign-in. Use a personal Google account, or continue without an account.'
/** The 5-minute wait ran out with nothing back from the browser (a closed tab, a Google page that never redirected). */
export const TIMEOUT_MESSAGE = `No answer from Google after ${WAIT_MS / 60_000} minutes, so miyagi stopped waiting. Try again.`
/**
 * Google's own "this account is not on the app's test-user list" wording (an unverified app in Testing: "can only be
 * accessed by developer-approved testers", "The developer hasn't given you access to this app"). Only this wording,
 * carried in error_description, earns the tester message: a bare access_denied is what Google sends when the learner
 * presses Cancel (OAuth 2.0: the resource owner denied the request).
 */
const NOT_A_TESTER = /\btesters?\b|\btest users?\b|not completed the google verification|(?:hasn.t|has not) given you access/i
/** A Workspace admin (a school account, an internal-only app) blocks the app: Google's error codes for that. */
const ADMIN_CODES = new Set(['admin_policy_enforced', 'org_internal'])

/**
 * What an OAuth error that came back on the loopback means, in plain words. Supabase sends Google's error (and its
 * own) as ?error=…&error_code=…&error_description=… (also in the #fragment, which never reaches this server).
 *
 * access_denied is three different things (R20): Google's Cancel (no error_code, no tester wording) → 'cancelled';
 * Google's not-a-tester error (its description says so) → 'denied' with the tester message; Supabase's own refusals
 * (error_code signup_disabled, user_banned, provider_email_needs_verification) → 'failed' with Supabase's description.
 */
export function explainCallbackError(error: string | null, errorCode: string | null, description: string | null): { reason: string; message: string } {
  // "Unable to exchange external code: 4/0A…": Supabase appends the start of Google's code; never show that part.
  const desc = plain(description)?.replace(/^(Unable to exchange external code)\b.*$/i, '$1')
  const code = plain(errorCode, 80)
  if ((error && ADMIN_CODES.has(error)) || (code && ADMIN_CODES.has(code))) return { reason: 'denied', message: ADMIN_BLOCKED }
  if (error === 'access_denied' || code === 'access_denied') {
    if (desc && NOT_A_TESTER.test(desc)) return { reason: 'denied', message: NOT_ALLOWED }
    if (!code || code === 'access_denied') return { reason: 'cancelled', message: CANCELLED_MESSAGE }
  }
  if (desc && /unable to exchange external code/i.test(desc)) {
    // Supabase could not trade Google's code for a Google token: the Google client secret (or client ID) saved in
    // Supabase's Google provider does not match the Google Cloud OAuth client.
    return { reason: 'provider', message: 'Google sign-in is not set up correctly yet (Supabase could not finish the Google step). Continue without an account for now.' }
  }
  const what = desc ?? plain(errorCode, 80) ?? plain(error, 80)
  if (!what) return { reason: 'failed', message: 'Google did not send a sign-in code back. Try again, or continue without an account.' }
  return { reason: 'failed', message: `Sign-in failed: ${what.replace(/[.\s]+$/, '')}. Try again, or continue without an account.` }
}

/** What a refused code exchange (POST /token?grant_type=pkce) means, in plain words. */
function explainExchange(res: Answer | undefined): string {
  if (!res) return 'miyagi could not reach the sign-in server. Check your connection and try again.'
  const b = (res.body && typeof res.body === 'object' ? res.body : {}) as Record<string, unknown>
  const code = plain(b.error_code, 80)
  if (code === 'flow_state_not_found' || code === 'flow_state_expired' || code === 'bad_code_verifier') {
    return 'That sign-in expired or was already used. Try again.'
  }
  const what = plain(b.msg, 160) ?? plain(b.error_description, 160) ?? plain(b.message, 160) ?? code ?? `error ${res.status}`
  return `The sign-in server refused the sign-in: ${what.replace(/[.\s]+$/, '')}. Try again, or continue without an account.`
}

/**
 * The "back to miyagi" tab in the system browser. Everything shown is HTML-escaped; the app window's theme colors.
 * retry: this flow's own authorize URL (built by authorizeUrl from constants), shown as "Try again" after a failure.
 */
const PAGE = (title: string, line: string, retry?: string): string =>
  `<!doctype html><meta charset="utf-8"><title>${escapeHtml(title)}</title><body style="margin:0;height:100vh;display:grid;place-items:center;background:${color.window};color:${color.text};font:15px -apple-system,system-ui,sans-serif"><div style="text-align:center;max-width:520px;padding:0 24px"><h1 style="font-size:22px;font-weight:600;margin:0 0 8px">${escapeHtml(title)}</h1><p style="margin:0;color:${color.label}">${escapeHtml(line)}</p>${retry ? `<p style="margin:16px 0 0"><a href="${escapeHtml(retry)}" style="color:${color.text}">Try again</a></p>` : ''}</div>`
/** Callback answers close their connection, so a quick retry never reuses a socket to the last flow's listener. */
const PAGE_HEADERS = {
  'Content-Type': 'text/html; charset=utf-8',
  'Cache-Control': 'no-store',
  'Referrer-Policy': 'no-referrer',
  'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'",
  Connection: 'close'
} as const

// ---- what onboarding.ts reads (first-run order: intro → login → setup → home) ------------------------------------

let signedIn = false
/** "Continue without an account" (or Continue after a sign-in) in THIS run. Memory only: never saved. */
let decided = false
let afterLogin: (() => BrowserWindow | undefined) | undefined

/** The login should show: it is on, not skipped, nobody is signed in, and the learner hasn't chosen in this run. */
export const needsLogin = (): boolean => loginEnabled() && !skipLogin() && !signedIn && !decided

/** Tell the launch gate whether the login is through. */
const report = (): void => setGatePart('login', !needsLogin())

/**
 * onboarding.ts: what opens when the learner is done with the login. In the one-window flow it returns undefined (no
 * 'auth' window is open; the home window's flow carries on by itself). Only for the standalone login window, a
 * fallback, it opens a window (home, while setup isn't done) and returns it, so the login window closes only once that
 * one is showing (no gap with no window).
 */
export function onLoginDone(fn: () => BrowserWindow | undefined): void {
  afterLogin = fn
}

let currentAccess: (() => Promise<string | undefined>) | undefined
/**
 * A fresh access token (refreshed first when it is about to expire), or undefined when signed out. Main process only.
 * features/cloudLink.ts sends it to miyagi-cloud (POST /v1/link) to tie this Mac's install token to the learner.
 * Never send it to the engine or a renderer; never log it.
 */
export function accessToken(): Promise<string | undefined> {
  return currentAccess ? currentAccess() : Promise.resolve(undefined)
}

let currentRefresh: (() => Promise<string | undefined>) | undefined
/**
 * age-delete lane: refresh the session now, once, and return the new access token (undefined: signed out, or the
 * refresh failed). features/accountDelete.ts calls it when miyagi-cloud says 403 bad_access_token. Main only.
 */
export function refreshedAccessToken(): Promise<string | undefined> {
  return currentRefresh ? currentRefresh() : Promise.resolve(undefined)
}

let signedInHook: (() => void) | undefined
/** features/cloudLink.ts: runs right after each successful Google sign-in (the session is stored by then). */
export function onSignedIn(fn: () => void): void {
  signedInHook = fn
}

export default defineMainFeature({
  id: 'auth',
  setup(ctx) {
    const file = join(ctx.app.getPath('userData'), 'auth.bin')
    const secure = safeStorage.isEncryptionAvailable() && !(process.platform === 'linux' && safeStorage.getSelectedStorageBackend() === 'basic_text')
    let session: Session | undefined
    // Every launch starts undecided (an old login.json is never read): only a stored session skips the login.
    decided = false
    if (secure && existsSync(file)) {
      try {
        session = toSession(JSON.parse(safeStorage.decryptString(readFileSync(file))))
      } catch {
        console.warn('[auth] auth.bin could not be read; signed out') // never the error itself
      }
      // A session made for another Supabase project (or saved without one) is never sent anywhere: dropped, unsent.
      if (session && session.project !== config()?.url) {
        console.warn('[auth] saved session is for another project; signed out')
        session = undefined
        try {
          unlinkSync(file)
        } catch {
          /* gone already */
        }
      }
    }
    signedIn = !!session
    report()

    const persist = (): void => {
      try {
        if (!session) {
          if (existsSync(file)) unlinkSync(file)
          return
        }
        if (!secure) return // kept for this run only
        const raw = { access_token: session.access, refresh_token: session.refresh, expires_at: Math.floor(session.expiresAt / 1000), project: session.project, user: { email: session.user.email, user_metadata: { full_name: session.user.name } } }
        const tmp = `${file}.tmp`
        writeFileSync(tmp, safeStorage.encryptString(JSON.stringify(raw)), { mode: 0o600 })
        renameSync(tmp, file)
      } catch {
        console.warn('[auth] could not write auth.bin')
      }
    }

    /** The learner is through the login for this run (memory only), and the gate hears it. */
    const decide = (): void => {
      decided = true
      report()
    }

    const announce = (): void => ctx.broadcast('auth:changed', session ? publicUser(session.user) : null)

    // ---- the session: set, refresh, forget ----------------------------------------------------------------------
    let refreshTimer: ReturnType<typeof setTimeout> | undefined
    let refreshing: Promise<boolean> | undefined
    let failures = 0

    const schedule = (ms?: number): void => {
      clearTimeout(refreshTimer)
      refreshTimer = undefined
      if (!session) return
      const wait = ms ?? Math.max(REFRESH_MIN_MS, session.expiresAt - Date.now() - REFRESH_EARLY_MS)
      refreshTimer = setTimeout(() => void refresh(), wait)
    }

    const setSession = (s: Session | undefined): void => {
      const before = session ? JSON.stringify(publicUser(session.user)) : ''
      session = s
      signedIn = !!s
      failures = 0
      persist()
      schedule()
      if ((s ? JSON.stringify(publicUser(s.user)) : '') !== before) announce()
    }

    /** POST to the project; headers AND body within FETCH_MS. undefined = network failure or timeout. */
    async function post(cfg: Config, path: string, body?: unknown, bearer?: string): Promise<Answer | undefined> {
      const ctl = new AbortController()
      const t = setTimeout(() => ctl.abort(), FETCH_MS)
      try {
        const headers: Record<string, string> = { apikey: cfg.key, 'Content-Type': 'application/json' }
        if (bearer) headers.Authorization = `Bearer ${bearer}`
        const res = await fetch(`${cfg.url}${path}`, { method: 'POST', headers, body: body === undefined ? undefined : JSON.stringify(body), signal: ctl.signal })
        const json: unknown = await res.json().catch(() => undefined)
        return { ok: res.ok, status: res.status, body: json }
      } catch {
        return undefined
      } finally {
        clearTimeout(t)
      }
    }

    /** A new session from a refresh token (the project's own URL kept on it). */
    const viaRefresh = (cfg: Config, token: string): Promise<Answer | undefined> => post(cfg, '/auth/v1/token?grant_type=refresh_token', { refresh_token: token })
    const withProject = (s: Session | undefined, cfg: Config): Session | undefined => (s ? { ...s, project: cfg.url } : undefined)

    /** One refresh at a time (the refresh token rotates). true = the session is fresh. */
    function refresh(): Promise<boolean> {
      if (refreshing) return refreshing
      const s = session
      const cfg = config()
      if (!s || !cfg || s.project !== cfg.url) return Promise.resolve(false)
      refreshing = (async () => {
        const res = await viaRefresh(cfg, s.refresh)
        if (session !== s) return !!session // signed out (or in again) meanwhile: that wins
        if (res?.ok) {
          const next = withProject(toSession(res.body), cfg)
          if (next) {
            // The refresh answer carries the user too; keep what we had if it doesn't.
            setSession({ ...next, user: next.user.name || next.user.email ? next.user : s.user })
            return true
          }
        }
        if (res && (res.status === 400 || res.status === 401)) {
          // Supabase refused the refresh token (revoked, already used, user deleted): signed out, calmly.
          console.warn('[auth] session ended (refresh refused):', res.status)
          setSession(undefined)
          return false
        }
        // Offline or a server hiccup: keep the session and try again later.
        console.warn('[auth] refresh failed; will retry', res ? res.status : '(network)')
        schedule(RETRY_MS[Math.min(failures, RETRY_MS.length - 1)])
        failures++
        return false
      })().finally(() => {
        refreshing = undefined
      })
      return refreshing
    }

    currentRefresh = async () => ((await refresh()) ? session?.access : undefined)
    currentAccess = async () => {
      if (!session) return undefined
      if (session.expiresAt - Date.now() < 60_000) await refresh()
      return session?.access
    }

    // A session from an earlier run: refresh now if it is (nearly) expired, else when it is due.
    if (session) schedule(session.expiresAt - Date.now() < REFRESH_EARLY_MS ? 0 : undefined)
    void ctx.app.whenReady().then(() => {
      // A Mac asleep past the timer: refresh on wake when it is due.
      powerMonitor.on('resume', () => {
        if (session && session.expiresAt - Date.now() < REFRESH_EARLY_MS) void refresh()
      })
    })

    // ---- one browser round trip at a time --------------------------------------------------------------------
    /**
     * The running sign-in. Set BEFORE the listener is up, so a cancel right after the click is never lost, and kept
     * while the code is exchanged, so Cancel / Esc / closing the window still win then (the answer is dropped unused).
     * callbacks: callbacks with this flow's state so far (MAX_CALLBACKS). last: the latest failed attempt's reason, which the
     * timeout answers with.
     */
    type Flow = {
      server: Server
      finish: (r: Result) => void
      aborted: boolean
      exchanging: boolean
      callbacks: number
      last?: { reason: string; message: string }
    }
    let flow: Flow | undefined
    /** Settles once the last flow's listener has let go of the port, so a quick second click never meets EADDRINUSE. */
    let released: Promise<void> = Promise.resolve()

    const closeServer = (server: Server): void => {
      if (server.listening) {
        const gone = new Promise<void>((r) => server.close(() => r()))
        // Never wait long on it: a stuck socket must not block the next sign-in.
        released = Promise.race([gone, new Promise<void>((r) => setTimeout(r, 1000).unref?.())])
      }
      server.closeAllConnections()
    }

    const stopFlow = (r: Result): void => {
      const f = flow
      flow = undefined
      if (!f) return
      f.aborted = true
      closeServer(f.server)
      f.finish(r)
    }

    /** The code → session. A failure carries the plain-words reason (never a token or the code). */
    async function exchange(cfg: Config, code: string, verifier: string): Promise<{ session: Session } | { message: string }> {
      const res = await post(cfg, `/auth/v1/token?grant_type=${FLOW_TYPE}`, { auth_code: code, code_verifier: verifier })
      if (!res || !res.ok) {
        const b = (res?.body && typeof res.body === 'object' ? res.body : {}) as Record<string, unknown>
        console.warn('[auth] token exchange failed:', res ? res.status : '(network)', plain(b.error_code, 80) ?? '', plain(b.msg, 160) ?? '')
        return { message: explainExchange(res) }
      }
      const session = withProject(toSession(res.body), cfg)
      if (!session) {
        console.warn('[auth] token exchange answered without a usable session')
        return { message: 'The sign-in server sent back an incomplete session. Try again.' }
      }
      return { session }
    }

    /** The sign-in page, through the strict allowlist for our own project; a dev-run override still gets the https gate. */
    const openAuthorize = (url: string): Promise<boolean> => (isAllowedUrl(url) ? safeOpenExternal(url) : openLinkInBrowser(url))

    /** Why the listener could not start, in plain words. */
    const portMessage = (err: unknown): string =>
      (err as NodeJS.ErrnoException | undefined)?.code === 'EADDRINUSE'
        ? `Another app on this Mac is using port ${PORT}, which miyagi needs to receive the Google sign-in. Quit it (or another copy of miyagi) and try again, or continue without an account.`
        : 'miyagi could not get ready to receive the Google sign-in on this Mac. Try again, or continue without an account.'

    function google(): Promise<Result> {
      if (!loginEnabled()) return Promise.resolve({ ok: false, reason: 'off' })
      const cfg = config()
      if (!cfg) return Promise.resolve({ ok: false, reason: 'not-configured' })
      stopFlow({ ok: false, reason: 'cancelled' }) // a second click restarts the flow

      const verifier = b64url(randomBytes(48))
      const challenge = b64url(createHash('sha256').update(verifier).digest())
      // Our own state, carried in redirect_to: Supabase keeps the query and appends ?code=… to it. Only the request
      // that brings it back can end this flow (a page or local process probing the port cannot). 24 bytes = 192 bits.
      const state = b64url(randomBytes(24))
      // Built here from config and constants only; nothing from a renderer or a request is ever appended.
      const authorize = authorizeUrl(cfg.url, state, challenge)

      return new Promise<Result>((resolve) => {
        let timer: ReturnType<typeof setTimeout> | undefined
        const server = createServer((req, res) => {
          const deny = (status = 404): void => void res.writeHead(status, { Connection: 'close' }).end()
          // The raw request target, not a parsed URL: "//host/auth/callback" or "/auth/./callback" never count as ours.
          const target = req.url ?? ''
          const at = target.indexOf('?')
          if ((at < 0 ? target : target.slice(0, at)) !== CALLBACK_PATH) return deny() // favicon, probes: not callbacks
          if (req.method !== 'GET' || req.headers.host !== CALLBACK_HOST || flow !== f || f.exchanging) return deny()
          let q: URLSearchParams
          try {
            q = new URLSearchParams(at < 0 ? '' : target.slice(at + 1))
          } catch {
            return deny(400) // a malformed request line must never throw in main
          }
          const keys = [...q.keys()]
          if (keys.some((k) => !CALLBACK_PARAMS.has(k)) || new Set(keys).size !== keys.length) return deny()
          if (!sameState(q.get('state'), state)) return deny()
          // Counted only now, after every check: a request without this flow's state (a local process, an <img> on a
          // web page, a DNS-rebinding page with another Host) is a cheap 404 that can't use up the real callback's turns.
          if (++f.callbacks > MAX_CALLBACKS) return deny()

          // Bring miyagi forward with the outcome, not just the browser tab.
          const focusApp = (): void => {
            if (process.platform === 'darwin') ctx.app.focus({ steal: true })
          }
          /**
           * A failed attempt: the tab says why (with Try again), the app hears it, and the flow keeps listening. The
           * renderer (features/auth/store.ts) stops showing "Waiting for Google…" the moment auth:attempt arrives, so a
           * Cancel on Google's page ends the wait at once; this listener staying up only keeps the tab's Try again
           * working and a forged error from ending a real sign-in.
           */
          const failed = (why: { reason: string; message: string }): void => {
            f.last = why
            ctx.broadcast('auth:attempt', why)
            try {
              res.writeHead(200, PAGE_HEADERS).end(PAGE(why.reason === 'cancelled' ? 'Sign-in cancelled' : 'Sign-in did not finish', why.message, authorize))
            } catch {
              /* the browser went away */
            }
          }

          const code = q.get('code')
          if (!code) {
            // Google or Supabase said no: say why, in plain words, in the tab AND in miyagi. Not the end of the flow: a
            // forged error callback can't stop a real sign-in, and the learner can try again from the tab.
            const why = explainCallbackError(q.get('error'), q.get('error_code'), q.get('error_description'))
            console.warn('[auth] sign-in came back without a code:', plain(q.get('error'), 80) ?? '(no error)', plain(q.get('error_code'), 80) ?? '', plain(q.get('error_description'))?.replace(/^(Unable to exchange external code)\b.*$/i, '$1') ?? '')
            return failed(why)
          }
          // The tab waits for the exchange, so it can say whether it worked.
          f.exchanging = true
          void exchange(cfg, code, verifier).then((r) => {
            f.exchanging = false
            if (f.aborted || flow !== f) {
              // Cancelled meanwhile: the answer is dropped, nothing is stored.
              try {
                res.writeHead(200, PAGE_HEADERS).end(PAGE('Sign-in cancelled', 'miyagi stopped waiting for this sign-in. Start again from miyagi.'))
              } catch {
                /* the listener is closed already */
              }
              return
            }
            // A refused code (junk, already used, another verifier) is not the end: the real callback may still come.
            if (!('session' in r)) return failed({ reason: 'failed', message: r.message })
            flow = undefined
            // Let go of 47217 once the page is flushed (closeAllConnections would cut it off mid-write), or at once if
            // the browser already dropped the request during the exchange: 'close' fires on finish AND on abort (end's
            // callback never runs after an abort, which used to keep the port for the rest of the run). A short
            // fallback timer covers a response that neither finishes nor closes.
            const release = (): void => closeServer(server)
            res.once('close', release)
            setTimeout(release, 2000).unref?.()
            try {
              res.writeHead(200, PAGE_HEADERS).end(PAGE('Back to miyagi', 'You can close this tab. You are signed in to miyagi.'))
            } catch {
              /* the browser went away */
            }
            if (res.destroyed || req.socket.destroyed) release()
            focusApp()
            const s = r.session
            setSession(s)
            decide() // the gate's login part opens
            signedInHook?.() // cloudLink.ts: link this Mac's install token to the learner (async, never in the way)
            f.finish({ ok: true, user: publicUser(s.user) })
          })
        })
        const f: Flow = {
          server,
          aborted: false,
          exchanging: false,
          callbacks: 0,
          finish: (r) => {
            clearTimeout(timer)
            resolve(r)
          }
        }
        flow = f

        let tries = 0
        server.on('error', (err) => {
          if (server.listening) return // an error on a live listener (a bad socket) is not a listen failure
          // A port still held for a moment (our own last listener closing, a test, a quick restart): try again briefly.
          if ((err as NodeJS.ErrnoException).code === 'EADDRINUSE' && ++tries < listenRetry.tries && !f.aborted) {
            setTimeout(() => {
              if (!f.aborted) server.listen(PORT, '127.0.0.1')
            }, listenRetry.ms)
            return
          }
          // Still taken (another app or another miyagi on 47217), or any other listen failure: stop here, plainly, and
          // never open the browser (Google would send the code to whoever holds the port).
          if (f.aborted) return // cancelled meanwhile: that already answered
          console.warn('[auth] could not listen on the sign-in port:', (err as NodeJS.ErrnoException).code ?? 'error')
          if (flow === f) flow = undefined
          f.aborted = true
          closeServer(server)
          f.finish({ ok: false, reason: 'port', message: portMessage(err) })
        })
        // After the last flow's listener let go of the port (a second click right after the first).
        void released.then(() => {
          if (f.aborted) return // cancelled before the listener was up: nothing opens
          server.once('listening', () => {
            if (f.aborted) return closeServer(server) // cancelled while it came up: nothing opens
            timer = setTimeout(() => {
              // The last failed attempt's reason, if there was one (a timeout after "access denied" says that).
              if (flow === f) stopFlow(f.last ? { ok: false, ...f.last } : { ok: false, reason: 'timeout', message: TIMEOUT_MESSAGE })
            }, WAIT_MS)
            void openAuthorize(authorize).then((ok) => {
              if (!ok && flow === f) stopFlow({ ok: false, reason: 'failed' })
            })
          })
          server.listen(PORT, '127.0.0.1')
        })
      })
    }

    /** Best effort, after a sign-out: revoke this session on Supabase (an expired access token is refreshed first). */
    async function revoke(cfg: Config, s: Session): Promise<void> {
      let access = s.access
      if (s.expiresAt - Date.now() < 30_000) {
        const r = await viaRefresh(cfg, s.refresh)
        const fresh = r?.ok ? toSession(r.body) : undefined
        if (!fresh) return // refused already: nothing left to revoke
        access = fresh.access
      }
      await post(cfg, '/auth/v1/logout?scope=local', undefined, access)
    }

    ctx.handle('auth:get', () => (loginEnabled() && session ? { signedIn: true, ...publicUser(session.user) } : null))
    // age-delete lane: no sign-in and no guest path before the age step (main/features/agegate.ts).
    ctx.handle('auth:google', () => (ageStepCleared() ? google() : { ok: false, reason: 'age', message: 'Answer the birthday question first.' }))
    ctx.handle('auth:cancel', () => {
      stopFlow({ ok: false, reason: 'cancelled' })
      return true
    })
    ctx.handle('auth:continue', () => {
      if (!ageStepCleared()) return { next: 'none' }
      decide()
      const login = ctx.appWindow('auth')
      const next = afterLogin?.()
      const close = (): void => {
        if (login && !login.isDestroyed()) login.close()
      }
      // Close the login once setup is showing (no moment with no window), or right away when nothing opened.
      if (next && !next.isDestroyed() && next !== login && !next.isVisible()) {
        next.once('show', close)
        setTimeout(close, 2000)
      } else close()
      return { next: next ? 'setup' : 'none' }
    })
    ctx.handle('auth:sign-out', () => {
      const cfg = config()
      const s = session
      setSession(undefined)
      // Back to the login: the gate closes (the overlay goes, home shows the login), unless login is off or skipped.
      decided = false
      report()
      // Best effort: revoke this session server-side. Never blocks sign-out, never logs a token.
      if (cfg && s && s.project === cfg.url) void revoke(cfg, s).catch(() => undefined)
      return true
    })
    ctx.app.on('before-quit', () => {
      stopFlow({ ok: false, reason: 'cancelled' })
      clearTimeout(refreshTimer)
    })
  }
})
