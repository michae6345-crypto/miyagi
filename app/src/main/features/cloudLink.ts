/**
 * Main-process feature: link this Mac's anonymous miyagi-cloud install token to the signed-in learner. No renderer side.
 *
 * features/cloud.ts mints an anonymous install token (POST /v1/install) that the engine uses for the proxy.
 * features/auth.ts signs the learner in with Google through Supabase. This file ties the two together, so quotas and
 * history can follow the account across Macs:
 *
 *   POST <cloud>/v1/link
 *     Authorization: Bearer <mi_ install token>
 *     {"access_token": "<the Supabase access token (JWT)>"}
 *   200 {"ok": true, "user_id": "<jwt sub>"}   linked (idempotent: the same pair again is 200 too)
 *   401 {"error": "bad_install_token"}         403 {"error": "bad_access_token"}
 *   503 {"error": "link_unavailable"}          404: an older cloud without /v1/link
 *
 * Since Nov 24 (MIC-30) features/cloudSession.ts calls POST /v1/session first and this linker only on its 404 (an
 * older cloud). When it ran on its own (kept for reference):
 *   - right after each successful Google sign-in (auth.ts onSignedIn), always;
 *   - once on launch (a few seconds after start, never on the UI's path) and whenever the install token appears or
 *     changes (first mint, self-heal), only when a session exists and this install is not linked to that user yet.
 * The access token comes from auth.ts accessToken(), which refreshes an expiring session first. A token that is
 * still expired after that (the refresh failed, offline) is not sent.
 *
 * 200: userData/cloud-link.json = {userId, linkedAt, host, tokenId?}. Non-secret: never a token. A 404 is skipped
 * silently; anything else logs one line (status only, never a token or a body). Nothing is saved on a failure, so the
 * next launch tries again. Sign-out never unlinks and never touches cloud-link.json: the install keeps working
 * anonymously and stays linked on the cloud side; a different learner signing in links again.
 */
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { defineMainFeature } from '../context'
import type { InstallInfo } from './cloud'

const LINK_TIMEOUT_MS = 10_000
const USER_ID_RE = /^[A-Za-z0-9._:@-]{1,128}$/

/** What cloud-link.json holds. Never a token. */
export type LinkRecord = { userId: string; linkedAt: string; host: string; tokenId?: string }
export type LinkOutcome =
  | 'linked' // 200, saved
  | 'already' // linked to this learner before (launch check only)
  | 'no-install' // no install token yet (cloud off, or still minting)
  | 'signed-out'
  | 'expired' // the access token is expired and could not be refreshed
  | 'unsupported' // 404: the cloud is older than /v1/link
  | 'refused' // 401 / 403
  | 'failed' // 503, another status, a bad answer, offline, timeout

export type LinkerDeps = {
  fetch: typeof fetch
  /** A fresh Supabase access token, or undefined when signed out (auth.ts accessToken()). */
  accessToken: () => Promise<string | undefined>
  install: () => InstallInfo | undefined
  /** Where the record lives (userData/cloud-link.json). */
  file: string
  now?: () => number
  log?: (line: string) => void
  timeoutMs?: number
}

/** The JWT's sub and exp, read WITHOUT verifying it (only to compare with the record and skip a dead token). */
export function jwtClaims(jwt: string): { sub?: string; exp?: number } {
  const part = jwt.split('.')[1]
  if (!part || part.length > 8192) return {}
  try {
    const raw = JSON.parse(Buffer.from(part, 'base64url').toString('utf8')) as Record<string, unknown>
    return {
      sub: typeof raw.sub === 'string' ? raw.sub : undefined,
      exp: typeof raw.exp === 'number' && Number.isFinite(raw.exp) ? raw.exp : undefined
    }
  } catch {
    return {}
  }
}

export function readRecord(file: string): LinkRecord | undefined {
  if (!existsSync(file)) return undefined
  try {
    const r = JSON.parse(readFileSync(file, 'utf8')) as Partial<LinkRecord>
    if (typeof r.userId !== 'string' || typeof r.linkedAt !== 'string' || typeof r.host !== 'string') return undefined
    return { userId: r.userId, linkedAt: r.linkedAt, host: r.host, tokenId: typeof r.tokenId === 'string' ? r.tokenId : undefined }
  } catch {
    return undefined
  }
}

function writeRecord(file: string, r: LinkRecord): boolean {
  try {
    const tmp = `${file}.tmp`
    writeFileSync(tmp, JSON.stringify(r), { mode: 0o600 })
    renameSync(tmp, file)
    return true
  } catch {
    return false
  }
}

export type Linker = {
  /** force: link even when the record says this install is linked to this learner (after a sign-in). Never throws. */
  link(opts?: { force?: boolean }): Promise<LinkOutcome>
}

/** The link itself, apart from Electron (tests drive it with a fake fetch). Calls run one after another. */
export function createLinker(deps: LinkerDeps): Linker {
  const now = deps.now ?? Date.now
  const log = deps.log ?? ((line: string) => console.warn(line))
  const timeoutMs = deps.timeoutMs ?? LINK_TIMEOUT_MS
  let queue: Promise<unknown> = Promise.resolve()

  async function once(force: boolean): Promise<LinkOutcome> {
    const install = deps.install()
    if (!install) return 'no-install'
    const access = await deps.accessToken()
    if (!access) return 'signed-out'
    const { sub, exp } = jwtClaims(access)
    if (exp !== undefined && exp * 1000 <= now()) return 'expired'
    if (!force) {
      const rec = readRecord(deps.file)
      if (rec && sub && rec.userId === sub && rec.host === install.host && rec.tokenId === install.tokenId) return 'already'
    }

    const abort = new AbortController()
    const timer = setTimeout(() => abort.abort(), timeoutMs)
    let status: number
    let body: unknown
    try {
      const res = await deps.fetch(`${install.host}/v1/link`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${install.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_token: access }),
        signal: abort.signal,
        redirect: 'error'
      })
      status = res.status
      body = await res.json().catch(() => undefined)
    } catch (err) {
      log(`[cloud-link] could not reach the cloud: ${err instanceof Error && err.name === 'AbortError' ? 'timeout' : 'request failed'}; will retry next launch`)
      return 'failed'
    } finally {
      clearTimeout(timer)
    }

    if (status === 404) return 'unsupported' // an older cloud: quietly, again next launch
    if (status === 401 || status === 403) {
      log(`[cloud-link] link refused (${status === 401 ? 'install token' : 'access token'}); will retry next launch`)
      return 'refused'
    }
    const b = (body && typeof body === 'object' ? body : {}) as Record<string, unknown>
    const userId = typeof b.user_id === 'string' && USER_ID_RE.test(b.user_id) ? b.user_id : undefined
    if (status !== 200 || b.ok !== true || !userId) {
      log(`[cloud-link] link failed (status ${status}); will retry next launch`)
      return 'failed'
    }
    if (!writeRecord(deps.file, { userId, linkedAt: new Date(now()).toISOString(), host: install.host, tokenId: install.tokenId })) {
      log('[cloud-link] linked, but could not save cloud-link.json')
    }
    return 'linked'
  }

  return {
    link(opts = {}) {
      const run = queue.then(() => once(!!opts.force)).catch((): LinkOutcome => 'failed')
      queue = run
      return run
    }
  }
}

/**
 * The triggers (sign-in, launch, a new install token) moved to features/cloudSession.ts (Nov 24, MIC-30): it calls
 * POST /v1/session and uses this linker only when the cloud answers 404 (an older cloud). This feature registers
 * nothing, so /v1/link is never sent twice.
 */
export default defineMainFeature({
  id: 'cloudLink',
  setup() {}
})
