/**
 * The account session with miyagi-cloud (MIC-30, app side), apart from Electron so test/cloudSession.test.ts drives it
 * with a fake fetch. features/cloudSession.ts wires it to auth.ts, cloud.ts and the renderer.
 *
 *   POST <cloud>/v1/session
 *     Authorization: Bearer <mi_ install token>
 *     {"access_token": "<the Supabase access token (JWT)>"}
 *   200 {account: {id, email_verified}, plan, caps: {daily_usd, used_usd, tokens, used_tokens, resets_at}, linked: true,
 *        signin_mode: "off" | "build" | "all"}      (an older draft said "0" for off: read as "off")
 *   401 bad_install_token   → re-mint the install token through cloud.ts's self-heal, then retry once
 *   403 bad_access_token    → refresh the Supabase session once, then retry once (403 too_many_installs: no retry)
 *   503 / 5xx / offline     → keep the cached answer, try again with a backoff (30 s, 2 min, 10 min, 30 min)
 *   404                     → an older cloud without the route: POST /v1/link instead (cloudLink.ts createLinker)
 *   451 region_unavailable  → the cloud's region block: 'region', final (no heal, no re-mint, no backoff retry)
 *
 * The answer is cached in memory and in userData/session.json: {plan, caps, signinMode, linked, fetchedAt}. Never a
 * token, never the email, never the account id. Calls run one after another; sync() never throws. Log lines carry a
 * status at most, never a token or a body.
 */
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import type { InstallInfo } from '../cloud'
import type { LinkOutcome } from '../cloudLink'

export type SigninMode = 'off' | 'build' | 'all'
export type Plan = 'free' | 'pro'
/** Today's caps and use, for the signed-in learner (every install of theirs together). null cap = no cap. */
export type Caps = { dailyUsd: number | null; usedUsd: number; tokens: number | null; usedTokens: number; resetsAt?: string }
/** What session.json holds (and the memory cache). Never a token, an email or an account id. */
export type SessionRecord = { plan?: Plan; caps?: Caps; signinMode: SigninMode; linked: boolean; fetchedAt: string }

export type SessionOutcome =
  | 'ok' // 200, cached
  | 'legacy' // 404: linked through /v1/link (an older cloud)
  | 'fresh' // fetched moments ago for this install: nothing sent
  | 'no-install'
  | 'signed-out'
  | 'expired' // the access token is expired and could not be refreshed
  | 'refused' // 401 / 403 after the one retry, or too_many_installs
  | 'region' // 451 region_unavailable: not retried, nothing re-minted
  | 'failed' // 503, another status, a bad answer, offline, timeout: cache kept, retry scheduled

export type SessionDeps = {
  fetch: typeof fetch
  /** A fresh Supabase access token, or undefined when signed out (auth.ts accessToken()). */
  accessToken: () => Promise<string | undefined>
  /** Refresh the Supabase session now, once (auth.ts refreshedAccessToken()). */
  refreshAccessToken: () => Promise<string | undefined>
  install: () => InstallInfo | undefined
  /** Re-mint the install token through cloud.ts's self-heal; true once a new token is in. */
  heal: () => Promise<boolean>
  /** POST /v1/link (cloudLink.ts createLinker), for a cloud that answers 404. */
  legacyLink: () => Promise<LinkOutcome>
  /** userData/session.json */
  file: string
  /** The cache changed (a 200, a legacy link, a sign-out). */
  onChange?: (r: SessionRecord | undefined) => void
  now?: () => number
  log?: (line: string) => void
  timeoutMs?: number
  /** Run fn after ms; returns what cancels it. Default: an unref'd setTimeout. */
  schedule?: (fn: () => void, ms: number) => () => void
}

const TIMEOUT_MS = 10_000
/** A non-forced sync within this long of the last 200 for the same install sends nothing. */
export const FRESH_MS = 60_000
export const BACKOFF_MS = [30_000, 2 * 60_000, 10 * 60_000, 30 * 60_000] as const
const MAX_USD = 1_000_000
const MAX_TOKENS = 1e12

const finite = (v: unknown, max: number): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= max ? v : undefined)
const iso = (v: unknown): string | undefined => (typeof v === 'string' && v.length <= 40 && !Number.isNaN(Date.parse(v)) ? v : undefined)

export function signinModeOf(v: unknown): SigninMode {
  return v === 'build' ? 'build' : v === 'all' ? 'all' : 'off' // "off", "0", anything else: off (the cloud's own rule)
}

/** A bounded caps copy, or undefined when the shape is wrong. */
export function cleanCaps(raw: unknown): Caps | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const r = raw as Record<string, unknown>
  const usedUsd = finite(r.used_usd ?? r.usedUsd, MAX_USD)
  const usedTokens = finite(r.used_tokens ?? r.usedTokens, MAX_TOKENS)
  if (usedUsd === undefined || usedTokens === undefined) return undefined
  const cap = (v: unknown, max: number): number | null => {
    const n = finite(v, max)
    return n !== undefined && n > 0 ? n : null
  }
  const c: Caps = { dailyUsd: cap(r.daily_usd ?? r.dailyUsd, MAX_USD), usedUsd, tokens: cap(r.tokens, MAX_TOKENS), usedTokens: Math.floor(usedTokens) }
  const at = iso(r.resets_at ?? r.resetsAt)
  if (at) c.resetsAt = at
  return c
}

/** The cloud's 200, as the record (exactly the fields we keep), or undefined when it is not a session answer. */
export function recordOf(body: unknown, fetchedAt: string): SessionRecord | undefined {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return undefined
  const b = body as Record<string, unknown>
  if (b.linked !== true) return undefined
  const rec: SessionRecord = { plan: b.plan === 'pro' ? 'pro' : 'free', signinMode: signinModeOf(b.signin_mode), linked: true, fetchedAt }
  const caps = cleanCaps(b.caps)
  if (caps) rec.caps = caps
  return rec
}

/** session.json as written by this file; anything else (or a field we never write) is dropped. */
export function readSession(file: string): SessionRecord | undefined {
  if (!existsSync(file)) return undefined
  try {
    const r = JSON.parse(readFileSync(file, 'utf8')) as Record<string, unknown>
    const fetchedAt = iso(r.fetchedAt)
    if (!fetchedAt || typeof r.linked !== 'boolean') return undefined
    const rec: SessionRecord = { signinMode: signinModeOf(r.signinMode), linked: r.linked, fetchedAt }
    if (r.plan === 'free' || r.plan === 'pro') rec.plan = r.plan
    const caps = cleanCaps(r.caps)
    if (caps) rec.caps = caps
    return rec
  } catch {
    return undefined
  }
}

function writeSession(file: string, r: SessionRecord): boolean {
  try {
    const tmp = `${file}.tmp`
    const out: SessionRecord = { signinMode: r.signinMode, linked: r.linked, fetchedAt: r.fetchedAt }
    if (r.plan) out.plan = r.plan
    if (r.caps) out.caps = r.caps
    writeFileSync(tmp, JSON.stringify(out), { mode: 0o600 })
    renameSync(tmp, file)
    return true
  } catch {
    return false
  }
}

/** The JWT's exp, read WITHOUT verifying it (only to skip a dead token). */
function jwtExp(jwt: string): number | undefined {
  const part = jwt.split('.')[1]
  if (!part || part.length > 8192) return undefined
  try {
    const exp = (JSON.parse(Buffer.from(part, 'base64url').toString('utf8')) as Record<string, unknown>).exp
    return typeof exp === 'number' && Number.isFinite(exp) ? exp : undefined
  } catch {
    return undefined
  }
}

const timeout = (fn: () => void, ms: number): (() => void) => {
  const t = setTimeout(fn, ms)
  t.unref?.()
  return () => clearTimeout(t)
}

export type SessionClient = {
  /** force: send even when the last answer is fresh (after a sign-in, on launch). Never throws. */
  sync(opts?: { force?: boolean }): Promise<SessionOutcome>
  /** The cached answer (memory, read from session.json at start). */
  current(): SessionRecord | undefined
  /** Signed out: stop retrying; keep only what is not the account's (the sign-in mode and the link). */
  signedOut(): void
  dispose(): void
}

type Answer = { status: number; body: unknown } | 'offline' | 'timeout'

export function createSessionClient(deps: SessionDeps): SessionClient {
  const now = deps.now ?? Date.now
  const log = deps.log ?? ((line: string) => console.warn(line))
  const timeoutMs = deps.timeoutMs ?? TIMEOUT_MS
  const schedule = deps.schedule ?? timeout
  let cached = readSession(deps.file)
  /** The install the last 200 was for (memory only: a token id, never the token). */
  let fetchedFor: { host: string; tokenId?: string; at: number } | undefined
  let failures = 0
  let retry: (() => void) | undefined
  let queue: Promise<unknown> = Promise.resolve()
  let disposed = false

  const save = (r: SessionRecord | undefined): void => {
    cached = r
    if (r && !writeSession(deps.file, r)) log('[session] could not save session.json')
    deps.onChange?.(r)
  }

  const cancelRetry = (): void => {
    retry?.()
    retry = undefined
  }
  const backoff = (): void => {
    cancelRetry()
    if (disposed) return
    const ms = BACKOFF_MS[Math.min(failures, BACKOFF_MS.length - 1)]
    failures++
    retry = schedule(() => {
      retry = undefined
      void client.sync({ force: true })
    }, ms)
  }

  async function post(install: InstallInfo, access: string): Promise<Answer> {
    const abort = new AbortController()
    const timer = setTimeout(() => abort.abort(), timeoutMs)
    try {
      const res = await deps.fetch(`${install.host}/v1/session`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${install.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_token: access }),
        signal: abort.signal,
        redirect: 'error'
      })
      const body: unknown = await res.json().catch(() => undefined)
      return { status: res.status, body }
    } catch (err) {
      return err instanceof Error && err.name === 'AbortError' ? 'timeout' : 'offline'
    } finally {
      clearTimeout(timer)
    }
  }

  const errorKind = (body: unknown): string | undefined => {
    const e = body && typeof body === 'object' ? (body as Record<string, unknown>).error : undefined
    return typeof e === 'string' ? e : undefined
  }

  async function once(force: boolean): Promise<SessionOutcome> {
    let install = deps.install()
    if (!install) return 'no-install'
    let access = await deps.accessToken()
    if (!access) return 'signed-out'
    const exp = jwtExp(access)
    if (exp !== undefined && exp * 1000 <= now()) return 'expired'
    if (!force && cached && fetchedFor && fetchedFor.host === install.host && fetchedFor.tokenId === install.tokenId && now() - fetchedFor.at < FRESH_MS) return 'fresh'

    let healed = false
    let refreshed = false
    for (;;) {
      const a = await post(install, access)
      if (a === 'offline' || a === 'timeout') {
        log(`[session] could not reach the cloud: ${a === 'timeout' ? 'timeout' : 'request failed'}; will retry`)
        backoff()
        return 'failed'
      }
      if (a.status === 451 || errorKind(a.body) === 'region_unavailable') {
        failures = 0
        cancelRetry()
        log('[session] not available in this region; not retrying')
        return 'region'
      }
      if (a.status === 404) {
        const linked = await deps.legacyLink()
        failures = 0
        cancelRetry()
        if (linked === 'linked' || linked === 'already') {
          // An older cloud: linked, but no plan or caps to show. The sign-in mode we last heard stays.
          save({ signinMode: cached?.signinMode ?? 'off', linked: true, fetchedAt: new Date(now()).toISOString() })
        }
        return 'legacy'
      }
      if (a.status === 401 && !healed) {
        healed = true
        const ok = await deps.heal().catch(() => false)
        const next = ok ? deps.install() : undefined
        if (next) {
          install = next
          continue
        }
        log('[session] install token refused and could not be replaced; will retry')
        backoff()
        return 'refused'
      }
      if (a.status === 403 && errorKind(a.body) === 'bad_access_token' && !refreshed) {
        refreshed = true
        const fresh = await deps.refreshAccessToken().catch(() => undefined)
        if (fresh) {
          access = fresh
          continue
        }
        log('[session] access token refused and the session could not be refreshed')
        return 'refused'
      }
      if (a.status === 401 || a.status === 403) {
        log(`[session] session refused (${a.status === 401 ? 'install token' : errorKind(a.body) === 'too_many_installs' ? 'too many installs' : 'access token'})`)
        return 'refused'
      }
      const rec = a.status === 200 ? recordOf(a.body, new Date(now()).toISOString()) : undefined
      if (!rec) {
        log(`[session] session failed (status ${a.status}); keeping the last answer, will retry`)
        backoff()
        return 'failed'
      }
      failures = 0
      cancelRetry()
      fetchedFor = { host: install.host, tokenId: install.tokenId, at: now() }
      save(rec)
      return 'ok'
    }
  }

  const client: SessionClient = {
    sync(opts = {}) {
      if (disposed) return Promise.resolve('failed')
      const run = queue.then(() => once(!!opts.force)).catch((): SessionOutcome => 'failed')
      queue = run
      return run
    },
    current: () => cached,
    signedOut() {
      cancelRetry()
      failures = 0
      fetchedFor = undefined
      if (!cached) return
      // The plan and today's use are the account's: gone with it. The mode is the cloud's; the link stays on the cloud
      // side (sign-out never unlinks, cloudLink.ts).
      const kept: SessionRecord = { signinMode: cached.signinMode, linked: cached.linked, fetchedAt: cached.fetchedAt }
      // Delete my data removes session.json before it signs out: memory only then, never written back.
      if (existsSync(deps.file)) save(kept)
      else {
        cached = kept
        deps.onChange?.(kept)
      }
    },
    dispose() {
      disposed = true
      cancelRetry()
    }
  }
  return client
}
