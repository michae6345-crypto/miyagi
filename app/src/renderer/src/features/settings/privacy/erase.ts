/**
 * Feature: settings. Delete my data, the renderer's flow (Privacy.tsx shows its step). Pure apart from `invoke`,
 * so erase.test.ts drives it with a fake bridge.
 *   1. main `settings:delete` removes keys.bin, auth.bin and login.json (main/features/settings/erase.ts);
 *   2. only if that worked, main `auth:sign-out` forgets the session in memory and revokes it (auth.ts → true).
 * Step 2 must be awaited and checked: if it fails, auth.ts still holds the session and its refresh timer would write
 * auth.bin back, so the row must not say "Deleted from this Mac".
 */
import type { DeleteResult } from '../keys'

/** done: all gone. partial: keys and settings went, the sign-in did not. failed: nothing was removed. */
export type EraseStep = 'done' | 'partial' | 'failed'

export type Erase = {
  step: EraseStep
  /** main's answer when the files went (ok: true): the caller applies the empty keys and resets the prefs. */
  deleted?: DeleteResult
  /** auth:sign-out answered true: the caller clears the signed-in user in this window. */
  signedOut: boolean
}

/** bridge.invoke, wrapped (it is a method: pass `(c) => bridge.invoke(c)`, not the bare reference). */
type Invoke = (channel: string) => Promise<unknown>

/** The step to show, from main's delete answer and whether the sign-out was confirmed. */
export function eraseStep(r: Pick<DeleteResult, 'ok' | 'signIn'> | null | undefined, signedOut: boolean): EraseStep {
  if (!r?.ok) return 'failed'
  return r.signIn === false || !signedOut ? 'partial' : 'done'
}

export async function eraseData(invoke: Invoke): Promise<Erase> {
  const r = (await invoke('settings:delete').catch(() => undefined)) as DeleteResult | null | undefined
  if (!r?.ok) return { step: 'failed', signedOut: false }
  const signedOut = await invoke('auth:sign-out').then(
    (v) => v === true,
    () => false
  )
  return { step: eraseStep(r, signedOut), deleted: r, signedOut }
}
