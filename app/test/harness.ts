/**
 * Offline test harness: a fake Supabase Auth and a fake miyagi-cloud behind a stubbed global fetch (nothing leaves
 * this machine; only the auth loopback on 127.0.0.1 is reached for real), plus a fake MainContext.
 */
import { createHash } from 'node:crypto'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { MainContext } from '../src/main/context'
import { openListeners, safeStorage } from './fakes/electron'
import { SUPABASE_URL } from './fakes/publicConfig'

export const realFetch: typeof fetch = globalThis.fetch.bind(globalThis)
export const CLOUD = 'https://cloud.test'
export const PROJECT = SUPABASE_URL

const b64url = (b: Buffer | string): string => Buffer.from(b).toString('base64url')

/** A JWT-shaped string. sig 'good' is what the fake cloud accepts. Never a real token. */
export function makeJwt(claims: { sub: string; exp: number; aud?: string }, sig = 'good'): string {
  return `${b64url(JSON.stringify({ alg: 'ES256', typ: 'JWT' }))}.${b64url(JSON.stringify({ aud: 'authenticated', ...claims }))}.${sig}`
}
const nowSec = (): number => Math.floor(Date.now() / 1000)
export const challengeOf = (verifier: string): string => createHash('sha256').update(verifier).digest('base64url')

type Call = { method: string; url: string; headers: Record<string, string>; body: unknown }
type FakeUser = { sub: string; email: string; name: string }

function json(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/** Supabase Auth, the three endpoints auth.ts uses. */
export class FakeSupabase {
  calls: Call[] = []
  /** code → the PKCE challenge it was issued for, and who signs in. */
  codes = new Map<string, { challenge: string; user: FakeUser }>()
  refreshTokens = new Map<string, FakeUser>()
  /** Make the next pkce exchange answer this instead. */
  refuseExchange?: { status: number; body: unknown }
  /** 'network': the refresh request throws (offline). */
  refreshMode: 'ok' | 'network' = 'ok'
  private n = 0

  session(user: FakeUser, ttlSec = 3600): Record<string, unknown> {
    const refresh = `refresh-${++this.n}`
    this.refreshTokens.set(refresh, user)
    return {
      access_token: makeJwt({ sub: user.sub, exp: nowSec() + ttlSec }),
      refresh_token: refresh,
      expires_in: ttlSec,
      expires_at: nowSec() + ttlSec,
      user: { email: user.email, user_metadata: { full_name: user.name } }
    }
  }

  async handle(url: URL, call: Call): Promise<Response> {
    this.calls.push(call)
    if (call.headers.apikey !== 'sb_publishable_test') return json(401, { msg: 'no apikey' })
    const body = (call.body ?? {}) as Record<string, string>
    if (url.pathname === '/auth/v1/token' && url.searchParams.get('grant_type') === 'pkce') {
      if (this.refuseExchange) {
        const r = this.refuseExchange
        this.refuseExchange = undefined
        return json(r.status, r.body)
      }
      const issued = this.codes.get(body.auth_code)
      if (!issued || challengeOf(body.code_verifier ?? '') !== issued.challenge) return json(400, { error_code: 'bad_code_verifier', msg: 'code challenge does not match' })
      this.codes.delete(body.auth_code)
      return json(200, this.session(issued.user))
    }
    if (url.pathname === '/auth/v1/token' && url.searchParams.get('grant_type') === 'refresh_token') {
      if (this.refreshMode === 'network') throw new TypeError('fetch failed')
      const user = this.refreshTokens.get(body.refresh_token)
      if (!user) return json(400, { error_code: 'refresh_token_not_found', msg: 'Invalid Refresh Token' })
      this.refreshTokens.delete(body.refresh_token) // rotation: a refresh token works once
      return json(200, this.session(user))
    }
    if (url.pathname === '/auth/v1/logout') return new Response(null, { status: 204 })
    return json(404, {})
  }
}

/** miyagi-cloud: /v1/install and /v1/link per the contract (verification faked: sig 'good', exp in the future). */
export class FakeCloud {
  calls: Call[] = []
  installs = new Set<string>()
  links = new Map<string, string>() // install token → user id
  /** Answer /v1/link with this status (and the contract's body) instead of verifying. */
  linkStatus?: 401 | 403 | 404 | 503 | 500
  private n = 0

  async handle(url: URL, call: Call): Promise<Response> {
    this.calls.push(call)
    if (url.pathname === '/v1/install' && call.method === 'POST') {
      const token = `mi_testinstalltoken${String(++this.n).padStart(4, '0')}`
      this.installs.add(token)
      return json(200, { token, token_id: `tid${this.n}` })
    }
    if (url.pathname === '/v1/link' && call.method === 'POST') {
      if (this.linkStatus === 404) return json(404, { detail: 'Not Found' })
      if (this.linkStatus === 503) return json(503, { error: 'link_unavailable' })
      if (this.linkStatus === 500) return json(500, {})
      const install = /^Bearer (.+)$/.exec(call.headers.authorization ?? '')?.[1]
      if (this.linkStatus === 401 || !install || !this.installs.has(install)) return json(401, { error: 'bad_install_token' })
      const jwt = String((call.body as Record<string, unknown> | undefined)?.access_token ?? '')
      const [, payload, sig] = jwt.split('.')
      let claims: { sub?: string; exp?: number; aud?: string } = {}
      try {
        claims = JSON.parse(Buffer.from(payload ?? '', 'base64url').toString('utf8'))
      } catch {
        /* bad token */
      }
      if (this.linkStatus === 403 || sig !== 'good' || claims.aud !== 'authenticated' || !claims.sub || !claims.exp || claims.exp <= nowSec()) {
        return json(403, { error: 'bad_access_token' })
      }
      this.links.set(install, claims.sub)
      return json(200, { ok: true, user_id: claims.sub })
    }
    return json(404, {})
  }
}

/** Route every fetch to the fakes; the auth loopback (127.0.0.1) gets the real fetch. Returns the restore. */
export function stubFetch(supa: FakeSupabase, cloud: FakeCloud): () => void {
  const before = globalThis.fetch
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url)
    if (url.hostname === '127.0.0.1') return realFetch(input, init)
    const headers: Record<string, string> = {}
    new Headers(init?.headers).forEach((v, k) => (headers[k] = v))
    const raw = typeof init?.body === 'string' ? init.body : undefined
    const call: Call = { method: init?.method ?? 'GET', url: url.href, headers, body: raw ? JSON.parse(raw) : undefined }
    if (url.origin === PROJECT) return supa.handle(url, call)
    if (url.origin === CLOUD) return cloud.handle(url, call)
    throw new TypeError(`offline test: no route to ${url.origin}`)
  }) as typeof fetch
  return () => {
    globalThis.fetch = before
  }
}

export type Harness = {
  ctx: MainContext
  dir: string
  invoke: (channel: string, ...args: unknown[]) => Promise<unknown>
  broadcasts: [string, unknown][]
  /** before-quit: stops timers and a pending flow. Then removes the temp userData. */
  close: () => void
}

/** A fake MainContext around a fresh temp userData folder. */
export function makeHarness(): Harness {
  const dir = mkdtempSync(join(tmpdir(), 'miyagi-test-'))
  const handlers = new Map<string, (...a: unknown[]) => unknown>()
  const broadcasts: [string, unknown][] = []
  const quits: (() => void)[] = []
  const app = {
    getPath: () => dir,
    getVersion: () => '0.0.0-test',
    whenReady: () => Promise.resolve(),
    focus: () => undefined,
    on: (ev: string, fn: () => void) => {
      if (ev === 'before-quit') quits.push(fn)
    }
  }
  const engine = { setCloud: () => undefined, onCloudTokenInvalid: () => undefined, onEvent: () => undefined, onOpen: () => undefined }
  const ctx = {
    app,
    engine,
    broadcast: (c: string, p: unknown) => broadcasts.push([c, p]),
    handle: (c: string, fn: (...a: unknown[]) => unknown) => handlers.set(c, fn),
    appWindow: () => undefined
  } as unknown as MainContext
  return {
    ctx,
    dir,
    broadcasts,
    invoke: async (c, ...a) => {
      const fn = handlers.get(c)
      if (!fn) throw new Error(`no handler ${c}`)
      return fn(...a)
    },
    close: () => {
      for (const q of quits) q()
      rmSync(dir, { recursive: true, force: true })
    }
  }
}

/** Write userData/auth.bin the way auth.ts does (the fake safeStorage). */
export function writeSession(dir: string, s: Record<string, unknown>, project = PROJECT): void {
  const raw = { ...s, project }
  writeFileSync(join(dir, 'auth.bin'), safeStorage.encryptString(JSON.stringify(raw)))
}

/** Start auth:google and wait until it asks to open the browser. */
export async function startGoogle(h: Harness): Promise<{ result: Promise<unknown>; authorize: URL; callback: URL; state: string; challenge: string }> {
  const asked = new Promise<string>((resolve) => {
    const fn = (u: string): void => {
      openListeners.delete(fn)
      resolve(u)
    }
    openListeners.add(fn)
  })
  const result = h.invoke('auth:google')
  const authorize = new URL(await asked)
  const callback = new URL(authorize.searchParams.get('redirect_to') ?? '')
  return { result, authorize, callback, state: callback.searchParams.get('state') ?? '', challenge: authorize.searchParams.get('code_challenge') ?? '' }
}

/** The browser coming back to the loopback with these query params added. */
export async function hitCallback(callback: URL, params: Record<string, string>, override?: { state?: string; path?: string }): Promise<{ status: number; text: string }> {
  const u = new URL(callback.href)
  if (override?.path) u.pathname = override.path
  if (override?.state !== undefined) u.searchParams.set('state', override.state)
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v)
  const res = await realFetch(u, { headers: { Connection: 'close' } })
  return { status: res.status, text: await res.text() }
}

export const until = async (cond: () => boolean, ms = 3000): Promise<void> => {
  const end = Date.now() + ms
  while (!cond()) {
    if (Date.now() > end) throw new Error('timed out waiting')
    await new Promise((r) => setTimeout(r, 10))
  }
}
