/**
 * Main-process feature: auth (first-run login; renderer: src/renderer/src/features/auth/).
 *
 * Google sign-in through Supabase Auth, the way Google allows it on desktop: the SYSTEM browser (never a webview),
 * OAuth 2.0 PKCE, and a one-shot loopback redirect on 127.0.0.1. Supabase holds the Google client secret; this app
 * only ever has the project URL and its publishable (anon) key, which are public by design.
 *
 *   1. auth:google  → make a PKCE verifier + S256 challenge and a random state, listen once on
 *                     http://127.0.0.1:47217/auth/callback, open
 *                     <project>/auth/v1/authorize?provider=google&redirect_to=<callback>?state=…&code_challenge=… in the
 *                     browser (through safeOpen).
 *   2. The browser comes back to the loopback with ?state=…&code=…. A request whose state does not match this flow's is
 *      ignored (404) and does not end the flow; then we answer a small "you can close this tab" page.
 *   3. POST <project>/auth/v1/token?grant_type=pkce {auth_code, code_verifier} → session.
 *   4. The session (access + refresh token, name, email) is kept in userData/auth.bin, encrypted with safeStorage
 *      (login Keychain), exactly like the BYOK keys in settings.ts. The renderer only ever gets {name, email}.
 *
 * Handles (bridge.invoke):
 *   auth:get                → {signedIn, name?, email?} | null
 *   auth:google ({mode})    → {ok:true, user} | {ok:false, reason: off|not-configured|port|timeout|denied|cancelled|failed}
 *   auth:cancel             stop waiting for the browser → true
 *   auth:sign-out           revoke (best effort) and forget the session → true
 *
 * Config (never secrets): MAIN_VITE_SUPABASE_URL and MAIN_VITE_SUPABASE_ANON_KEY at build time (electron-vite), or
 * MIYAGI_SUPABASE_URL / MIYAGI_SUPABASE_ANON_KEY in the environment for a dev run. Every handler answers
 * {ok:false, reason:'off'} / null unless MIYAGI_V2_CLOUD=1, like the account sheet.
 *
 * Supabase dashboard, once: Authentication › Providers › Google on (client ID + secret from Google Cloud), and
 * Authentication › URL Configuration › Redirect URLs: http://127.0.0.1:47217/auth/callback** (the ** lets the ?state=…
 * query through; an exact entry without it makes Supabase fall back to the Site URL and the sign-in times out).
 *
 * Follow-up (DISTRIBUTION-PLAN): tie the anonymous install token (cloud.ts, POST /v1/install) to the signed-in user
 * on miyagi-cloud. Not done here.
 *
 * UNVERIFIED in Electron (cost freeze; no live run in this package): the browser round trip and token exchange.
 */
import { safeStorage } from 'electron'
import { createHash, randomBytes, timingSafeEqual } from 'node:crypto'
import { existsSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs'
import { createServer, type Server } from 'node:http'
import { join } from 'node:path'
import { defineMainFeature } from '../context'
import { openLinkInBrowser } from '../safeOpen'
import { v2CloudOn } from './account'

const PORT = 47217
const CALLBACK_PATH = '/auth/callback'
const REDIRECT = `http://127.0.0.1:${PORT}${CALLBACK_PATH}`
const WAIT_MS = 5 * 60_000
const FETCH_MS = 15_000

type Config = { url: string; key: string }
type User = { name?: string; email?: string }
type Session = { access: string; refresh: string; expiresAt: number; user: User }
type Result = { ok: true; user: User } | { ok: false; reason: string }

function config(): Config | undefined {
  const env = import.meta.env as Record<string, string | undefined>
  const url = (env.MAIN_VITE_SUPABASE_URL ?? process.env.MIYAGI_SUPABASE_URL ?? '').trim().replace(/\/+$/, '')
  const key = (env.MAIN_VITE_SUPABASE_ANON_KEY ?? process.env.MIYAGI_SUPABASE_ANON_KEY ?? '').trim()
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

const PAGE = (title: string, line: string): string =>
  `<!doctype html><meta charset="utf-8"><title>${title}</title><body style="margin:0;height:100vh;display:grid;place-items:center;background:#1c1c1e;color:#fff;font:15px -apple-system,system-ui,sans-serif"><div style="text-align:center"><h1 style="font-size:22px;font-weight:600;margin:0 0 8px">${title}</h1><p style="margin:0;color:rgba(255,255,255,.6)">${line}</p></div>`

export default defineMainFeature({
  id: 'auth',
  setup(ctx) {
    const file = join(ctx.app.getPath('userData'), 'auth.bin')
    const secure = safeStorage.isEncryptionAvailable() && !(process.platform === 'linux' && safeStorage.getSelectedStorageBackend() === 'basic_text')
    let session: Session | undefined

    if (secure && existsSync(file)) {
      try {
        session = toSession(JSON.parse(safeStorage.decryptString(readFileSync(file))))
      } catch {
        console.warn('[auth] auth.bin could not be read; signed out') // never the error itself
      }
    }

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
      const ctl = new AbortController()
      const t = setTimeout(() => ctl.abort(), FETCH_MS)
      try {
        const res = await fetch(`${cfg.url}/auth/v1/token?grant_type=pkce`, {
          method: 'POST',
          headers: { apikey: cfg.key, 'Content-Type': 'application/json' },
          body: JSON.stringify({ auth_code: code, code_verifier: verifier }),
          signal: ctl.signal
        })
        if (!res.ok) {
          console.warn('[auth] token exchange failed:', res.status)
          return undefined
        }
        return toSession(await res.json())
      } catch {
        console.warn('[auth] token exchange failed (network)')
        return undefined
      } finally {
        clearTimeout(t)
      }
    }

    function google(): Promise<Result> {
      if (!v2CloudOn()) return Promise.resolve({ ok: false, reason: 'off' })
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
            session = s
            persist()
            if (process.platform === 'darwin') ctx.app.focus({ steal: true })
            f?.finish({ ok: true, user: s.user })
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
          // Built here from config only; nothing from a renderer is appended. Through safeOpen's plain-https gate
          // (no credentials, no odd port). Core request: safeOpenExternal once the Supabase host is on its allowlist.
          void openLinkInBrowser(`${cfg.url}/auth/v1/authorize?${q.toString()}`).then((ok) => {
            if (!ok && flow?.server === server) stopFlow({ ok: false, reason: 'failed' })
          })
        })
      })
    }

    ctx.handle('auth:get', () => (v2CloudOn() && session ? { signedIn: true, ...session.user } : null))
    ctx.handle('auth:google', () => google())
    ctx.handle('auth:cancel', () => {
      stopFlow({ ok: false, reason: 'cancelled' })
      return true
    })
    ctx.handle('auth:sign-out', () => {
      const cfg = config()
      const s = session
      session = undefined
      persist()
      if (cfg && s) {
        // Best effort: revoke the refresh token server-side. Never blocks sign-out.
        fetch(`${cfg.url}/auth/v1/logout`, { method: 'POST', headers: { apikey: cfg.key, Authorization: `Bearer ${s.access}` } }).catch(() => undefined)
      }
      return true
    })
    ctx.app.on('before-quit', () => stopFlow({ ok: false, reason: 'cancelled' }))
  }
})
