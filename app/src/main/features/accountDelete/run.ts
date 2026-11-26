/**
 * Delete account, the order of the two parts (accountDelete.ts wires it to Electron; tests drive it with fakes):
 *
 *   1. the server (accountDelete/server.ts). A refusal or no answer: {ok: false}, and nothing on this Mac is touched.
 *   2. this Mac (the wipe, the browser storage, the built-in lessons put back). Once it has started, the answer is
 *      always ok: a step that throws counts as something left behind (local false), never as "nothing was deleted".
 *
 * A cloud with no delete route (404) still gets here: account 'email', this Mac is wiped and the renderer tells the
 * learner to email support@miyagi.study to remove the account (settings/privacy/facts.ts DELETE.email).
 */
import type { AccountOutcome, ServerResult } from './server'

export type DeleteAccountResult = { ok: true; account: AccountOutcome; local: boolean } | { ok: false; reason: 'unreachable' | 'account' | 'busy' }

export type RunDeps = {
  server: () => Promise<ServerResult>
  /** Wipe this Mac; true when nothing was left behind. */
  local: () => Promise<boolean>
  log?: (line: string) => void
}

export async function runDelete(d: RunDeps): Promise<DeleteAccountResult> {
  const log = d.log ?? ((l: string) => console.warn(l))
  const server = await d.server().catch((): ServerResult => ({ ok: false, reason: 'unreachable' }))
  if (!server.ok) return { ok: false, reason: server.reason }
  const local = await d.local().catch(() => {
    log('[account-delete] the local wipe stopped part way')
    return false
  })
  return { ok: true, account: server.account, local }
}
