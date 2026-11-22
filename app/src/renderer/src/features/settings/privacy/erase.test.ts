/**
 * Delete account, the renderer's flow: the server goes first, nothing else runs when it can't be reached, and the
 * sign-out is awaited and checked.
 *   cd app && node --import tsx --test src/renderer/src/features/settings/privacy/erase.test.ts
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { DeleteResult, KeysView } from '../keys'
import { deleteAccount } from './erase'

const keys = { keys: {}, secure: true } as unknown as KeysView
const keysGone: DeleteResult = { ok: true, keys, signIn: true }

/** A fake bridge.invoke: each channel answers with a value, or throws when the answer is an Error. */
function fake(answers: Record<string, unknown>): { invoke: (c: string, p?: unknown) => Promise<unknown>; calls: [string, unknown][] } {
  const calls: [string, unknown][] = []
  const invoke = async (c: string, p?: unknown): Promise<unknown> => {
    calls.push([c, p])
    const a = answers[c]
    if (a instanceof Error) throw a
    return a
  }
  return { invoke, calls }
}

test('server unreachable: offline, and nothing else is called (nothing deleted, still signed in)', async () => {
  const f = fake({ 'account:delete': { ok: false, reason: 'unreachable' }, 'settings:delete': keysGone, 'auth:sign-out': true })
  assert.deepEqual(await deleteAccount(f.invoke, { lessons: true }), { step: 'offline', local: true, signedOut: false })
  assert.deepEqual(f.calls, [['account:delete', { lessons: true }]])
})

test('an IPC failure or a junk answer is offline too', async () => {
  for (const a of [new Error('ipc'), undefined, null, 'ok', { ok: true }, { ok: true, account: 'gone' }]) {
    const f = fake({ 'account:delete': a })
    assert.equal((await deleteAccount(f.invoke, { lessons: false })).step, 'offline')
    assert.equal(f.calls.length, 1)
  }
})

test('deleted: then the keys and the sign-out, in that order; lessons passed through as asked', async () => {
  const f = fake({ 'account:delete': { ok: true, account: 'deleted', local: true }, 'settings:delete': keysGone, 'auth:sign-out': true })
  const r = await deleteAccount(f.invoke, { lessons: false })
  assert.deepEqual(r, { step: 'done', account: 'deleted', local: true, deleted: keysGone, signedOut: true })
  assert.deepEqual(
    f.calls.map((c) => c[0]),
    ['account:delete', 'settings:delete', 'auth:sign-out']
  )
  assert.deepEqual(f.calls[0][1], { lessons: false })
})

test('pending: the local wipe is done, the step says the account goes later', async () => {
  const f = fake({ 'account:delete': { ok: true, account: 'pending', local: true }, 'settings:delete': keysGone, 'auth:sign-out': true })
  const r = await deleteAccount(f.invoke, { lessons: false })
  assert.equal(r.step, 'pending')
  assert.equal(r.account, 'pending')
})

test('signed out already (account none) is done', async () => {
  const f = fake({ 'account:delete': { ok: true, account: 'none', local: true }, 'settings:delete': keysGone, 'auth:sign-out': true })
  assert.equal((await deleteAccount(f.invoke, { lessons: false })).step, 'done')
})

test('leftovers on this Mac and a failed sign-out are reported, never hidden', async () => {
  const f = fake({ 'account:delete': { ok: true, account: 'deleted', local: false }, 'settings:delete': new Error('x'), 'auth:sign-out': new Error('y') })
  const r = await deleteAccount(f.invoke, { lessons: true })
  assert.equal(r.step, 'done')
  assert.equal(r.local, false)
  assert.equal(r.signedOut, false)
  assert.equal(r.deleted, undefined)
})

test('the lessons option is strictly opt-in: anything but true is false', async () => {
  const f = fake({ 'account:delete': { ok: false } })
  await deleteAccount(f.invoke, { lessons: 'yes' as unknown as boolean })
  assert.deepEqual(f.calls[0][1], { lessons: false })
})
