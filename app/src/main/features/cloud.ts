/**
 * Main-process feature (v2, W0-5 / DISTRIBUTION-PLAN section 1): the anonymous install token for miyagi-cloud, the
 * hosted proxy every AI call goes through (so usage is billed to us, visible and stoppable). No renderer side.
 *
 *   1. The proxy's base URL: env MIYAGI_CLOUD_URL (https; http only for 127.0.0.1 / localhost in dev). Unset = off:
 *      no network call at all (BYOK and the engine's own .env keep working). Nothing is minted until a proxy exists.
 *   2. First run with a URL and no token: POST <url>/v1/install {app, os, arch} → {token, token_id}. One attempt per
 *      launch at start, again on an engine connect at most every RETRY_MS, or on cloud:retry.
 *   3. The token ("mi_" + random) is kept in userData/install.bin, encrypted with safeStorage (login Keychain on the
 *      Mac), exactly like the BYOK keys (features/settings.ts). No secure storage → memory for this run only.
 *   4. It reaches the engine only inside config.keys (miyagiToken + miyagiCloud), via EngineLink.setCloud: memory
 *      only, never logged, never on a command line, never sent to a renderer.
 *
 * Handles: cloud:get → CloudView (no token), cloud:retry → CloudView. Broadcasts feat:cloud CloudView.
 */
import { safeStorage } from 'electron'
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { defineMainFeature } from '../context'

export type CloudPhase = 'off' | 'minting' | 'ok' | 'failed'
/** What a renderer may see: never the token. */
export type CloudView = { state: CloudPhase; configured: boolean; secure: boolean; hasToken: boolean }

const TOKEN_RE = /^mi_[A-Za-z0-9_-]{16,128}$/
const TOKEN_ID_RE = /^[A-Za-z0-9_-]{1,64}$/
const MINT_TIMEOUT_MS = 10_000
const RETRY_MS = 5 * 60_000

type Stored = { token: string; tokenId?: string; url: string }

/** The proxy base URL from the environment, or undefined (off). Trailing slashes dropped; nothing else accepted. */
export function cloudUrl(raw = process.env.MIYAGI_CLOUD_URL): string | undefined {
  const t = raw?.trim()
  if (!t) return undefined
  try {
    const u = new URL(t)
    const local = u.hostname === '127.0.0.1' || u.hostname === 'localhost'
    if (u.username || u.password || u.search || u.hash) return undefined
    if (u.protocol !== 'https:' && !(u.protocol === 'http:' && local)) return undefined
    return `${u.origin}${u.pathname.replace(/\/+$/, '')}`
  } catch {
    return undefined
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
      ctx.engine.setCloud(stored && url ? { miyagiToken: stored.token, miyagiCloud: url } : undefined)
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
