/**
 * Main-process feature (v2, W0-5 / DISTRIBUTION-PLAN section 1): the anonymous install token for miyagi-cloud, the
 * hosted proxy every AI call goes through (so usage is billed to us, visible and stoppable). No renderer side.
 *
 *   1. The proxy's host: DEFAULT_CLOUD_URL (our hosted miyagi-cloud), so a fresh download needs no setup. Env
 *      MIYAGI_CLOUD_URL overrides it (https; http only for 127.0.0.1 / localhost in dev; a trailing /v1 is dropped);
 *      MIYAGI_CLOUD_URL=off (or 0 / false) = off: no network call at all (BYOK and the engine's own .env keep working).
 *   2. First run with a URL and no token: POST <host>/v1/install {app, os, arch} → {token, token_id}. One attempt per
 *      launch at start, again on an engine connect at most every RETRY_MS, or on cloud:retry.
 *   3. The token ("mi_" + random) is kept in userData/install.bin, encrypted with safeStorage (login Keychain on the
 *      Mac), exactly like the BYOK keys (features/settings.ts). No secure storage → memory for this run only.
 *   4. It reaches the engine only inside config.keys (miyagiToken + miyagiCloud), via EngineLink.setCloud: memory
 *      only, never logged, never on a command line, never sent to a renderer. miyagiCloud is the proxy's API root,
 *      `<host>/v1` (cloudApiRoot), the form server/config.py expects: it appends /anthropic and /gemini to it.
 *   5. Self-heal: when the proxy no longer knows the token (a 401, e.g. its database was reset) the engine sends
 *      `cloud.token_invalid` (EngineLink.onCloudTokenInvalid). The token is dropped (memory and install.bin) and one new
 *      one is minted, then handed to the engine as in 4. At most one heal per HEAL_MS (a failed mint counts too; a
 *      fresh token that is rejected again waits for the window to end), so it never loops. A config.status with cloud
 *      "ok" cancels a heal still waiting (a late token_invalid about the token just replaced). A disabled install (403)
 *      sends no token_invalid: config.status.cloud says "unauthorized" and onboarding shows it.
 *
 *   6. installToken() / onInstallToken(): the token for features/cloudLink.ts (POST /v1/link ties it to the signed-in
 *      Supabase user). Main process only.
 *
 * Handles: cloud:get → CloudView (no token), cloud:retry → CloudView. Broadcasts feat:cloud CloudView.
 */
import { safeStorage } from 'electron'
import { existsSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { defineMainFeature } from '../context'

export type CloudPhase = 'off' | 'minting' | 'ok' | 'failed'
/** What a renderer may see: never the token. */
export type CloudView = { state: CloudPhase; configured: boolean; secure: boolean; hasToken: boolean }

const TOKEN_RE = /^mi_[A-Za-z0-9_-]{16,128}$/
const TOKEN_ID_RE = /^[A-Za-z0-9_-]{1,64}$/
const MINT_TIMEOUT_MS = 10_000
const RETRY_MS = 5 * 60_000
/** Self-heal backoff (cloud.token_invalid): at most one heal per this long, whatever its outcome. */
export const HEAL_MS = 5 * 60_000

type Stored = { token: string; tokenId?: string; url: string }

/** Our hosted proxy: what a fresh download talks to when MIYAGI_CLOUD_URL is not set. */
export const DEFAULT_CLOUD_URL = 'https://miyagi-cloud.onrender.com'
const OFF_RE = /^(off|0|false|no)$/i

/**
 * The proxy's host: env MIYAGI_CLOUD_URL, else DEFAULT_CLOUD_URL; undefined (off) for `off` / `0` / `false` / `no` or
 * a URL that fails the checks. No trailing slash and no trailing /v1 (the API root form is accepted too).
 */
export function cloudUrl(raw = process.env.MIYAGI_CLOUD_URL): string | undefined {
  const t = raw?.trim() || DEFAULT_CLOUD_URL
  if (OFF_RE.test(t)) return undefined
  try {
    const u = new URL(t)
    const local = u.hostname === '127.0.0.1' || u.hostname === 'localhost'
    if (u.username || u.password || u.search || u.hash) return undefined
    if (u.protocol !== 'https:' && !(u.protocol === 'http:' && local)) return undefined
    return `${u.origin}${u.pathname.replace(/\/+$/, '').replace(/\/v1$/, '')}`
  } catch {
    return undefined
  }
}

/** What the engine gets as config.keys.miyagiCloud: the proxy's API root (server/config.py cloud_url()). */
export const cloudApiRoot = (host: string): string => `${host}/v1`

export type Healer = { invalid(): void; cancel(): void; dispose(): void }
export type HealerOptions = {
  windowMs?: number
  now?: () => number
  /** Run `fn` after `ms`; returns what cancels it. Default: an unref'd setTimeout. */
  schedule?: (fn: () => void, ms: number) => () => void
}

const timeout = (fn: () => void, ms: number): (() => void) => {
  const t = setTimeout(fn, ms)
  t.unref?.()
  return () => clearTimeout(t)
}

/**
 * The self-heal's backoff, apart from the mint (so it runs without Electron). invalid(): the engine said
 * cloud.token_invalid. It heals at once unless a heal started less than `windowMs` ago (whatever came of it); then a
 * single heal waits for the window to end, so a fresh token the proxy rejects too never mints again sooner. Every
 * invalid() while a heal runs or waits is absorbed. cancel(): drop a waiting heal. features/cloud.ts calls it when a
 * config.status with cloud "ok" arrives: the engine took a token it accepts, so a token_invalid that landed late (about
 * the token a heal just replaced, e.g. answering a reconnect's config.keys) must not throw the new one away.
 */
export function createHealer(heal: () => Promise<void>, opts: HealerOptions = {}): Healer {
  const windowMs = opts.windowMs ?? HEAL_MS
  const now = opts.now ?? Date.now
  const schedule = opts.schedule ?? timeout
  let last: number | undefined
  let running = false
  let waiting: (() => void) | undefined
  const run = (): void => {
    waiting = undefined
    last = now()
    running = true
    heal()
      .catch(() => undefined)
      .finally(() => {
        running = false
      })
  }
  const cancel = (): void => {
    waiting?.()
    waiting = undefined
  }
  return {
    invalid() {
      if (running || waiting) return
      const wait = last === undefined ? 0 : last + windowMs - now()
      if (wait <= 0) return run()
      waiting = schedule(run, wait)
    },
    cancel,
    dispose: cancel
  }
}

/** The install token this Mac holds right now and the proxy that minted it. Main process only (features/cloudLink.ts). */
export type InstallInfo = { token: string; tokenId?: string; host: string }
let current: InstallInfo | undefined
const installListeners = new Set<() => void>()

/** The current install token, or undefined (off, not minted yet, or being replaced). Never to a renderer or a log. */
export const installToken = (): InstallInfo | undefined => current

/** Called whenever the install token appears or changes (first mint, self-heal). Returns what unsubscribes. */
export function onInstallToken(fn: () => void): () => void {
  installListeners.add(fn)
  return () => installListeners.delete(fn)
}

function setInstall(next: InstallInfo | undefined): void {
  if (next?.token === current?.token && next?.host === current?.host) return
  current = next
  for (const fn of installListeners) {
    try {
      fn()
    } catch {
      console.warn('[cloud] an install-token listener failed')
    }
  }
}

function secureStorage(): boolean {
  if (!safeStorage.isEncryptionAvailable()) return false
  if (process.platform === 'linux' && safeStorage.getSelectedStorageBackend() === 'basic_text') return false
  return true
}

export default defineMainFeature({
  id: 'cloud',
  setup(ctx) {
    const url = cloudUrl()
    const secure = secureStorage()
    const file = join(ctx.app.getPath('userData'), 'install.bin')
    let stored: Stored | undefined
    let state: CloudPhase = url ? 'failed' : 'off'
    let lastTry = 0
    let inFlight: Promise<void> | undefined

    const view = (): CloudView => ({ state, configured: !!url, secure, hasToken: !!stored })
    const publish = (): void => ctx.broadcast('cloud', view())
    const apply = (): void => {
      ctx.engine.setCloud(stored && url ? { miyagiToken: stored.token, miyagiCloud: cloudApiRoot(url) } : undefined)
      setInstall(stored && url ? { token: stored.token, tokenId: stored.tokenId, host: url } : undefined)
      state = !url ? 'off' : stored ? 'ok' : state
      publish()
    }

    if (url && secure && existsSync(file)) {
      try {
        const raw = JSON.parse(safeStorage.decryptString(readFileSync(file))) as Partial<Stored>
        // A token belongs to the proxy that minted it: a different URL mints a new one.
        if (typeof raw.token === 'string' && TOKEN_RE.test(raw.token) && raw.url === url) stored = { token: raw.token, tokenId: raw.tokenId, url }
      } catch {
        console.warn('[cloud] install.bin could not be read; a new token will be minted') // never the error: it can quote the input
      }
    }

    const persist = (): void => {
      if (!secure || !stored) return
      try {
        const tmp = `${file}.tmp`
        writeFileSync(tmp, safeStorage.encryptString(JSON.stringify(stored)), { mode: 0o600 })
        renameSync(tmp, file)
      } catch {
        console.warn('[cloud] could not save install.bin; kept for this run')
      }
    }

    const mint = (): Promise<void> => {
      if (!url || stored) return Promise.resolve()
      if (inFlight) return inFlight
      lastTry = Date.now()
      state = 'minting'
      publish()
      inFlight = (async () => {
        const abort = new AbortController()
        const timer = setTimeout(() => abort.abort(), MINT_TIMEOUT_MS)
        try {
          const res = await fetch(`${url}/v1/install`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ app: ctx.app.getVersion(), os: process.getSystemVersion?.() ?? '', arch: process.arch }),
            signal: abort.signal,
            redirect: 'error'
          })
          if (!res.ok) throw new Error(`status ${res.status}`)
          const body = (await res.json()) as { token?: unknown; token_id?: unknown }
          if (typeof body.token !== 'string' || !TOKEN_RE.test(body.token)) throw new Error('bad token shape')
          stored = { token: body.token, tokenId: typeof body.token_id === 'string' && TOKEN_ID_RE.test(body.token_id) ? body.token_id : undefined, url }
          persist()
          state = 'ok'
        } catch (err) {
          state = 'failed'
          // Only the reason's class, never a body or the token.
          console.warn('[cloud] could not get an install token:', err instanceof Error && err.name === 'AbortError' ? 'timeout' : 'request failed')
        } finally {
          clearTimeout(timer)
          inFlight = undefined
          apply()
        }
      })()
      return inFlight
    }

    /** Self-heal: forget the token the proxy no longer knows (memory and install.bin) and mint one new one. */
    const heal = async (): Promise<void> => {
      if (!url) return
      if (inFlight) return inFlight // already getting a token
      console.warn('[cloud] the proxy does not know this install token; getting a new one') // never the token
      stored = undefined
      try {
        rmSync(file, { force: true })
      } catch {
        console.warn('[cloud] could not remove install.bin')
      }
      await mint()
    }
    const healer = createHealer(heal)
    ctx.engine.onCloudTokenInvalid(() => healer.invalid())
    // The engine answers each config.keys with config.status; cloud "ok" means it holds a token the proxy accepts.
    ctx.engine.onEvent((e) => {
      if (e.type === 'config.status' && e.payload.cloud === 'ok') healer.cancel()
    })

    apply()
    void mint()
    // An engine (re)connect is a good moment to try again, but not more often than RETRY_MS.
    ctx.engine.onOpen(() => {
      if (url && !stored && Date.now() - lastTry > RETRY_MS) void mint()
    })

    ctx.handle('cloud:get', () => view())
    ctx.handle('cloud:retry', async () => {
      await mint()
      return view()
    })
  }
})
