/**
 * Delete account, the server part: ask miyagi-cloud to delete this install and the signed-in account. Apart from
 * Electron (tests drive it with a fake fetch). The contract (miyagi-cloud, PR #241):
 *
 *   POST <cloud>/v1/account/delete
 *     Authorization: Bearer <mi_ install token>          (features/cloud.ts, never a renderer)
 *     {"access_token": "<Supabase access token>"}        or {} when signed out (features/auth.ts accessToken())
 *   200 {"install": true | false, "account": "deleted" | "none" | "pending"}   (a valid access token deletes the
 *        account even when the install token is unknown: install false)
 *   401  no valid JWT. Signed out: the install is already gone, success. Signed in: refresh the session once and
 *        send again; still 401 (or no session after the refresh): the account could not be deleted ('account').
 *   403 {"error": "bad_access_token"}  refresh once and send again; still refused, or no session after the refresh:
 *        send {} (a signed-out delete: the install goes, the account is not touched)
 *   anything else, offline, a timeout: unreachable.
 * On any failure the caller deletes nothing on this Mac.
 *
 * No install token: signed out, there is nothing of this Mac's on the server ('none', go on with the local part);
 * signed in, there is no Bearer to send ('account'). Logs carry the status only, never a token.
 */
import type { InstallInfo } from '../cloud'

export type AccountOutcome = 'deleted' | 'none' | 'pending'
export type ServerResult =
  | {
      ok: true
      account: AccountOutcome
      /** how the server answered */
      via: 'deleted' | 'install-gone' | 'no-install'
      /** the server knew this install (false: only the account went) */
      install?: boolean
      /** the access token was refused, so the account was not part of it */
      signedOutRetry?: boolean
    }
  | { ok: false; reason: 'unreachable' | 'account' }

export type ServerDeps = {
  fetch: typeof fetch
  install: () => InstallInfo | undefined
  /** A fresh access token, undefined when signed out (auth.ts accessToken). */
  accessToken: () => Promise<string | undefined>
  /** Refresh now and return the new token (auth.ts refreshedAccessToken). */
  refreshedAccessToken: () => Promise<string | undefined>
  timeoutMs?: number
  log?: (line: string) => void
}

const TIMEOUT_MS = 15_000
const OUTCOMES: readonly AccountOutcome[] = ['deleted', 'none', 'pending']

type Answer = { status: number; body: Record<string, unknown> } | undefined

export async function deleteOnServer(d: ServerDeps): Promise<ServerResult> {
  const log = d.log ?? ((l: string) => console.warn(l))
  const install = d.install()
  const access = await d.accessToken().catch(() => undefined)
  if (!install) {
    if (access) {
      log('[account-delete] no install token while signed in: nothing deleted')
      return { ok: false, reason: 'account' }
    }
    return { ok: true, account: 'none', via: 'no-install' }
  }

  const post = async (token: string | undefined): Promise<Answer> => {
    const abort = new AbortController()
    const timer = setTimeout(() => abort.abort(), d.timeoutMs ?? TIMEOUT_MS)
    try {
      const res = await d.fetch(`${install.host}/v1/account/delete`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${install.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(token ? { access_token: token } : {}),
        signal: abort.signal,
        redirect: 'error'
      })
      const body = (await res.json().catch(() => undefined)) as unknown
      return { status: res.status, body: body && typeof body === 'object' ? (body as Record<string, unknown>) : {} }
    } catch (err) {
      log(`[account-delete] could not reach the cloud: ${err instanceof Error && err.name === 'AbortError' ? 'timeout' : 'request failed'}`)
      return undefined
    } finally {
      clearTimeout(timer)
    }
  }
  const badAccess = (a: Answer): boolean => a?.status === 403 && a.body.error === 'bad_access_token'

  let a = await post(access)
  let signedOutRetry = false
  if (access && (a?.status === 401 || badAccess(a))) {
    const was401 = a?.status === 401
    const fresh = await d.refreshedAccessToken().catch(() => undefined)
    if (fresh) a = await post(fresh)
    if (!a) return { ok: false, reason: 'unreachable' }
    if (was401 ? !fresh || a.status === 401 : a.status === 401) {
      // Signed in and still no valid JWT: the account can't be deleted now. Nothing else is done.
      log('[account-delete] the access token is still refused (401): nothing deleted')
      return { ok: false, reason: 'account' }
    }
    if (!was401 && (!fresh || badAccess(a))) {
      log('[account-delete] access token refused: deleting this install only')
      signedOutRetry = true
      a = await post(undefined)
    }
  }

  if (!a) return { ok: false, reason: 'unreachable' }
  const retried = signedOutRetry ? { signedOutRetry } : {}
  // Only a signed-out call (or the signed-out retry) gets here with a 401: the install is already gone.
  if (a.status === 401) return { ok: true, account: 'none', via: 'install-gone', ...retried }
  const account = OUTCOMES.find((o) => o === a.body.account)
  if (a.status === 200 && a.body.ok !== false && account) {
    return { ok: true, account, via: 'deleted', ...(a.body.install === false ? { install: false } : {}), ...retried }
  }
  log(`[account-delete] the cloud refused (status ${a.status}): nothing deleted`)
  return { ok: false, reason: 'unreachable' }
}
