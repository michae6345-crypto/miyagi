/**
 * Feature: settings. Delete account, the renderer's flow (Privacy.tsx shows its step). Pure apart from `invoke`, so
 * erase.test.ts drives it with a fake bridge. (It replaced Delete my data, which only reached this Mac.)
 *   1. main `account:delete {lessons}` asks miyagi-cloud first (main/features/accountDelete.ts). Unreachable: nothing
 *      was deleted anywhere, the row says so and offers Try again.
 *   2. Only then, main wiped this Mac (userData, logs, the engine's caches and state; ~/miyagi/lessons when ticked).
 *   3. `settings:delete` drops the keys still in settings.ts's memory and on the engine (keys.bin is gone already).
 *   4. `auth:sign-out`, awaited: the session in auth.ts's memory goes, so its refresh can't write auth.bin back.
 *   5. `account:restart` (the caller, after the line has shown): a built app starts again from the first-run screen.
 * Tokens never come here: main holds the install token and the Supabase session.
 */
import type { DeleteResult } from '../keys'

/**
 * done: the account and this Mac's data are gone. pending: this Mac's are, the account goes within 30 days.
 * offline: the server couldn't be reached. refused: signed in, and the server couldn't delete the account (401 after a
 * refresh). In both of those nothing was deleted anywhere.
 */
export type EraseStep = 'done' | 'pending' | 'offline' | 'refused'
export type AccountOutcome = 'deleted' | 'none' | 'pending'

export type Erase = {
  step: EraseStep
  /** main's account answer (done or pending only). */
  account?: AccountOutcome
  /** false: something on this Mac couldn't be removed (main logs which, never the path). */
  local: boolean
  /** settings:delete's answer: the caller applies the empty keys and resets the prefs. */
  deleted?: DeleteResult
  /** auth:sign-out answered true: the caller clears the signed-in user in this window. */
  signedOut: boolean
}

/** bridge.invoke, wrapped (it is a method: pass `(c, p) => bridge.invoke(c, p)`, not the bare reference). */
type Invoke = (channel: string, payload?: unknown) => Promise<unknown>

type MainAnswer = { ok: true; account: AccountOutcome; local: boolean } | { ok: false; reason: string }

function clean(raw: unknown): MainAnswer | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const r = raw as Record<string, unknown>
  if (r.ok !== true) return { ok: false, reason: typeof r.reason === 'string' ? r.reason : 'unreachable' }
  const account = r.account === 'deleted' || r.account === 'pending' || r.account === 'none' ? r.account : undefined
  return account ? { ok: true, account, local: r.local === true } : undefined
}

export async function deleteAccount(invoke: Invoke, opts: { lessons: boolean }): Promise<Erase> {
  const r = clean(await invoke('account:delete', { lessons: opts.lessons === true }).catch(() => undefined))
  if (!r?.ok) return { step: r?.reason === 'account' ? 'refused' : 'offline', local: true, signedOut: false }
  const deleted = (await invoke('settings:delete').catch(() => undefined)) as DeleteResult | undefined
  const signedOut = await invoke('auth:sign-out').then(
    (v) => v === true,
    () => false
  )
  return { step: r.account === 'pending' ? 'pending' : 'done', account: r.account, local: r.local, deleted: deleted?.ok ? deleted : undefined, signedOut }
}
