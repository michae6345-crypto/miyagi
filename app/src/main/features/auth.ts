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
 *   auth:google ({mode})    → {ok:true, user} | {ok:false, reason: off|not-configured|port|timeout|denied|cancelled|failed}
 *   auth:cancel             stop waiting for the browser → true
 *   auth:continue           the learner is done with the login (signed in, or "Continue without an account"): it never
 *                           shows on launch again; on the first run guided setup opens, then the login window closes
 *   auth:sign-out           revoke (best effort) and forget the session → true
 * Broadcast: feat:auth:changed  {name, email, avatarInitial} | null  (sign-in, refresh that changed the user, sign-out)
 *
 * Switch: LOGIN_ENABLED (common/flags.ts), off for one run with MIYAGI_LOGIN=0. Separate from v2Cloud (account.ts).
 *
 * Supabase dashboard, once: Authentication › Providers › Google on (client ID + secret from Google Cloud), and
 * Authentication › URL Configuration › Redirect URLs: http://127.0.0.1:47217/auth/callback** (the ** lets the ?state=…
 * query through; an exact entry without it makes Supabase fall back to the Site URL and the sign-in times out).
 *
 * UNVERIFIED in Electron (no live run in this package): the browser round trip, the token exchange and the refresh.
 */
import { powerMonitor, safeStorage, type BrowserWindow } from 'electron'
import { createHash, randomBytes, timingSafeEqual } from 'node:crypto'
import { existsSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs'
import { createServer, type Server } from 'node:http'
import { join } from 'node:path'
import { LOGIN_ENABLED } from '../../common/flags'
import { defineMainFeature } from '../context'
import { supabaseConfig } from '../publicConfig'
import { isAllowedUrl, openLinkInBrowser, safeOpenExternal } from '../safeOpen'

const PORT = 47217
const CALLBACK_PATH = '/auth/callback'
const REDIRECT = `http://127.0.0.1:${PORT}${CALLBACK_PATH}`
const WAIT_MS = 5 * 60_000
const FETCH_MS = 15_000
/** Refresh this long before the access token expires. */
const REFRESH_EARLY_MS = 5 * 60_000
const REFRESH_MIN_MS = 30_000
const RETRY_MS = [30_000, 60_000, 2 * 60_000, 5 * 60_000, 10 * 60_000]

type Config = { url: string; key: string }
type User = { name?: string; email?: string }
type Session = { access: string; refresh: string; expiresAt: number; user: User }
/** All the renderer ever gets about the learner. */
type PublicUser = { name?: string; email?: string; avatarInitial: string }
type Result = { ok: true; user: PublicUser } | { ok: false; reason: string }

/** First-run login is on (the build flag, and not switched off for this run). */
export const loginEnabled = (): boolean => LOGIN_ENABLED && process.env.MIYAGI_LOGIN !== '0'

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
  const expiresIn = typeof r.expires_in === 'number' && Number.isFinite(r.expires_in) ? r.expires_in : 3600
  const u = (r.user && typeof r.user === 'object' ? r.user : {}) as Record<string, unknown>
  const meta = (u.user_metadata && typeof u.user_metadata === 'object' ? u.user_metadata : {}) as Record<string, unknown>
  return {
    access,
    refresh,
    expiresAt: Date.now() + expiresIn * 1000,
    user: { name: str(meta.full_name, 80) ?? str(meta.name, 80), email: str(u.email, 254) }
  }
}

/** The avatar's letter: the name's first letter, else the email's, else "m". */
function initialOf(u: User): string {
  const ch = [...(u.name ?? u.email ?? '').trim()].find((c) => /\p{L}|\p{N}/u.test(c))
  return (ch ?? 'm').toLocaleUpperCase()
}
const publicUser = (u: User): PublicUser => ({ name: u.name, email: u.email, avatarInitial: initialOf(u) })

const PAGE = (title: string, line: string): string =>
  `<!doctype html><meta charset="utf-8"><title>${title}</title><body style="margin:0;height:100vh;display:grid;place-items:center;background:#1c1c1e;color:#fff;font:15px -apple-system,system-ui,sans-serif"><div style="text-align:center"><h1 style="font-size:22px;font-weight:600;margin:0 0 8px">${title}</h1><p style="margin:0;color:rgba(255,255,255,.6)">${line}</p></div>`

// ---- what onboarding.ts reads (first-run order: intro → login → setup → home) ------------------------------------

let signedIn = false
let decided = false
let afterLogin: (() => BrowserWindow | undefined) | undefined

/** The first run should show the login: it is on, nobody is signed in, and the learner hasn't chosen yet. */
export const needsLogin = (): boolean => loginEnabled() && !signedIn && !decided

/**
 * onboarding.ts: what opens when the learner is done with the login on the first run (guided setup). Return the window
 * it opened, so the login window closes only once that one is showing (no gap with no window).
 */
export function onLoginDone(fn: () => BrowserWindow | undefined): void {
  afterLogin = fn
}

let currentAccess: (() => Promise<string | undefined>) | undefined
/**
 * A fresh access token (refreshed first when it is about to expire), or undefined when signed out. Main process only.
 *
 * TODO(cloud-link), the seam for linking the anonymous miyagi-cloud install token to this user. Not implemented:
 *   - cloud.ts mints an anonymous install token (POST /v1/install) and the engine uses it for the proxy.
 *   - Later: after a sign-in (and once per launch while signed in), cloud.ts calls accessToken() and sends
 *     POST /v1/install/link {Authorization: Bearer <install token>, X-Supabase-JWT: <accessToken()>}; miyagi-cloud
 *     verifies the JWT against the project's JWKS and attaches the install to auth.users.id, so quotas and history
 *     follow the account across Macs. Sign-out does not unlink (the install keeps working anonymously).
 *   - Never send the JWT to the engine or a renderer; never log it.
 */
export function accessToken(): Promise<string | undefined> {
  return currentAccess ? currentAccess() : Promise.resolve(undefined)
}

export default defineMainFeature({
  id: 'auth',
  setup(ctx) {
    const file = join(ctx.app.getPath('userData'), 'auth.bin')
    /** Non-secret: only that the learner made their choice at the login (signed in, or went on without an account). */
    const choiceFile = join(ctx.app.getPath('userData'), 'login.json')
    const secure = safeStorage.isEncryptionAvailable() && !(process.platform === 'linux' && safeStorage.getSelectedStorageBackend() === 'basic_text')
    let session: Session | undefined

    if (existsSync(choiceFile)) {
      try {
        decided = (JSON.parse(readFileSync(choiceFile, 'utf8')) as { decided?: unknown })?.decided === true
      } catch {
        console.warn('[auth] login.json could not be read')
      }
    }
    if (secure && existsSync(file)) {
      try {
        session = toSession(JSON.parse(safeStorage.decryptString(readFileSync(file))))
      } catch {
        console.warn('[auth] auth.bin could not be read; signed out') // never the error itself
      }
    }
    signedIn = !!session

    const persist = (): void => {
      try {
        if (!session) {
          if (existsSync(file)) unlinkSync(file)
          return
        }
        if (!secure) return // kept for this run only
        const raw = { access_token: session.access, refresh_token: session.refresh, expires_in: Math.max(0, Math.round((session.expiresAt - Date.now()) / 1000)), user: { email: session.user.email, user_metadata: { full_name: session.user.name } } }
        const tmp = `${file}.tmp`
        writeFileSync(tmp, safeStorage.encryptString(JSON.stringify(raw)), { mode: 0o600 })
        renameSync(tmp, file)
      } catch {
        console.warn('[auth] could not write auth.bin')
      }
    }

    const decide = (): void => {
      if (decided) return
      decided = true
      try {
        const tmp = `${choiceFile}.tmp`
        writeFileSync(tmp, JSON.stringify({ decided: true, at: new Date().toISOString() }), { mode: 0o600 })
        renameSync(tmp, choiceFile)
      } catch {
        console.warn('[auth] could not save login.json')
      }
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

    async function post(cfg: Config, path: string, body: unknown): Promise<Response | undefined> {
      const ctl = new AbortController()
      const t = setTimeout(() => ctl.abort(), FETCH_MS)
      try {
        return await fetch(`${cfg.url}${path}`, {
          method: 'POST',
          headers: { apikey: cfg.key, 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: ctl.signal
        })
      } catch {
        return undefined
      } finally {
        clearTimeout(t)
      }
    }

    /** One refresh at a time (the refresh token rotates). true = the session is fresh. */
    function refresh(): Promise<boolean> {
      if (refreshing) return refreshing
      const s = session
      const cfg = config()
      if (!s || !cfg) return Promise.resolve(false)
      refreshing = (async () => {
        const res = await post(cfg, '/auth/v1/token?grant_type=refresh_token', { refresh_token: s.refresh })
        if (session !== s) return !!session // signed out (or in again) meanwhile: that wins
        if (res?.ok) {
          const next = await res.json().then(toSession, () => undefined)
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
    let flow: { server: Server; finish: (r: Result) => void } | undefined

    const stopFlow = (r: Result): void => {
      const f = flow
      flow = undefined
      if (!f) return
      f.server.close()
      f.finish(r)
    }

    async function exchange(cfg: Config, code: string, verifier: string): Promise<Session | undefined> {
      const res = await post(cfg, '/auth/v1/token?grant_type=pkce', { auth_code: code, code_verifier: verifier })
      if (!res) {
        console.warn('[auth] token exchange failed (network)')
        return undefined
      }
      if (!res.ok) {
        console.warn('[auth] token exchange failed:', res.status)
        return undefined
      }
      return res.json().then(toSession, () => undefined)
    }

    /** The sign-in page, through the strict allowlist for our own project; an overridden project still gets the https gate. */
    const openAuthorize = (url: string): Promise<boolean> => (isAllowedUrl(url) ? safeOpenExternal(url) : openLinkInBrowser(url))

    function google(): Promise<Result> {
      if (!loginEnabled()) return Promise.resolve({ ok: false, reason: 'off' })
      const cfg = config()
      if (!cfg) return Promise.resolve({ ok: false, reason: 'not-configured' })
      stopFlow({ ok: false, reason: 'cancelled' }) // a second click restarts the flow

      const verifier = b64url(randomBytes(48))
      const challenge = b64url(createHash('sha256').update(verifier).digest())
      // Our own state, carried in redirect_to: Supabase keeps the query and appends ?code=… to it. Only the request
      // that brings it back can end this flow (a page or local process probing the port cannot).
      const state = b64url(randomBytes(24))

      return new Promise<Result>((resolve) => {
        let timer: ReturnType<typeof setTimeout> | undefined
        const finish = (r: Result): void => {
          clearTimeout(timer)
          resolve(r)
        }

        const server = createServer((req, res) => {
          let u: URL
          try {
            u = new URL(req.url ?? '/', REDIRECT)
          } catch {
            res.writeHead(400).end() // a malformed request line must never throw in main
            return
          }
          if (req.method !== 'GET' || u.pathname !== CALLBACK_PATH || flow?.server !== server || !sameState(u.searchParams.get('state'), state)) {
            res.writeHead(404).end()
            return
          }
          const code = u.searchParams.get('code')
          const error = u.searchParams.get('error')
          res.writeHead(200, {
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'no-store',
            'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'"
          })
          if (!code) {
            res.end(PAGE('Sign-in did not finish', 'You can close this tab and try again in miyagi.'))
            stopFlow({ ok: false, reason: error === 'access_denied' ? 'denied' : 'failed' })
            return
          }
          // Not "signed in" yet: the code is exchanged after this page is sent, and miyagi shows the result.
          res.end(PAGE('Back to miyagi', 'You can close this tab. miyagi finishes signing you in.'))
          const f = flow
          flow = undefined
          server.close()
          void exchange(cfg, code, verifier).then((s) => {
            if (!s) return f?.finish({ ok: false, reason: 'failed' })
            setSession(s)
            decide()
            // TODO(cloud-link): link the install token to this user here (see accessToken() above). Not implemented.
            if (process.platform === 'darwin') ctx.app.focus({ steal: true })
            f?.finish({ ok: true, user: publicUser(s.user) })
          })
        })

        server.once('error', () => {
          if (flow?.server === server) flow = undefined
          finish({ ok: false, reason: 'port' })
        })
        server.listen(PORT, '127.0.0.1', () => {
          flow = { server, finish }
          timer = setTimeout(() => stopFlow({ ok: false, reason: 'timeout' }), WAIT_MS)
          const q = new URLSearchParams({ provider: 'google', redirect_to: `${REDIRECT}?state=${state}`, code_challenge: challenge, code_challenge_method: 's256' })
          // Built here from config only; nothing from a renderer is appended.
          void openAuthorize(`${cfg.url}/auth/v1/authorize?${q.toString()}`).then((ok) => {
            if (!ok && flow?.server === server) stopFlow({ ok: false, reason: 'failed' })
          })
        })
      })
    }

    ctx.handle('auth:get', () => (loginEnabled() && session ? { signedIn: true, ...publicUser(session.user) } : null))
    ctx.handle('auth:google', () => google())
    ctx.handle('auth:cancel', () => {
      stopFlow({ ok: false, reason: 'cancelled' })
      return true
    })
    ctx.handle('auth:continue', () => {
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
      if (cfg && s) {
        // Best effort: revoke this session's refresh token server-side. Never blocks sign-out, never logs a token.
        fetch(`${cfg.url}/auth/v1/logout?scope=local`, { method: 'POST', headers: { apikey: cfg.key, Authorization: `Bearer ${s.access}` } }).catch(() => undefined)
      }
      return true
    })
    ctx.app.on('before-quit', () => {
      stopFlow({ ok: false, reason: 'cancelled' })
      clearTimeout(refreshTimer)
    })
  }
})
