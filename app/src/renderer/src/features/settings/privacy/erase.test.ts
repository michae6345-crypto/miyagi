/**
 * Delete my data, the renderer's flow: which step the row shows, and that sign-out is awaited and checked.
 *   cd app && node --import tsx --test src/renderer/src/features/settings/privacy/erase.test.ts
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { DeleteResult, KeysView } from '../keys'
import { eraseData, eraseStep } from './erase'

const keys = { keys: {}, secure: true } as unknown as KeysView
const ok: DeleteResult = { ok: true, keys, signIn: true }

/** A fake bridge.invoke: each channel answers with a value, or throws when the answer is an Error. */
function fake(answers: Record<string, unknown>): { invoke: (c: string) => Promise<unknown>; calls: string[] } {
  const calls: string[] = []
  const invoke = async (c: string): Promise<unknown> => {
    calls.push(c)
    const a = answers[c]
    if (a instanceof Error) throw a
    return a
  }
  return { invoke, calls }
}

test('eraseStep: ok false or no answer is failed', () => {
  assert.equal(eraseStep({ ok: false }, true), 'failed')
  assert.equal(eraseStep(undefined, true), 'failed')
  assert.equal(eraseStep(null, false), 'failed')
})

test('eraseStep: a sign-in file that stayed, or a sign-out that failed, is partial', () => {
  assert.equal(eraseStep({ ok: true, signIn: false }, true), 'partial')
  assert.equal(eraseStep({ ok: true, signIn: true }, false), 'partial')
  assert.equal(eraseStep({ ok: true }, false), 'partial')
})

test('eraseStep: files gone and signed out is done', () => {
  assert.equal(eraseStep({ ok: true, signIn: true }, true), 'done')
  assert.equal(eraseStep({ ok: true }, true), 'done')
})

test('eraseData: ok false is failed, and nothing signs out', async () => {
  const f = fake({ 'settings:delete': { ok: false, keys }, 'auth:sign-out': true })
  assert.deepEqual(await eraseData(f.invoke), { step: 'failed', signedOut: false })
  assert.deepEqual(f.calls, ['settings:delete'])
})

test('eraseData: a delete that throws is failed', async () => {
  const f = fake({ 'settings:delete': new Error('ipc'), 'auth:sign-out': true })
  assert.equal((await eraseData(f.invoke)).step, 'failed')
  assert.deepEqual(f.calls, ['settings:delete'])
})

test('eraseData: signIn false is partial (still signs out the session)', async () => {
  const f = fake({ 'settings:delete': { ...ok, signIn: false }, 'auth:sign-out': true })
  const r = await eraseData(f.invoke)
  assert.equal(r.step, 'partial')
  assert.equal(r.signedOut, true)
  assert.deepEqual(f.calls, ['settings:delete', 'auth:sign-out'])
})

test('eraseData: a sign-out that throws or answers other than true is partial', async () => {
  for (const answer of [new Error('ipc'), false, undefined, { ok: true }]) {
    const r = await eraseData(fake({ 'settings:delete': ok, 'auth:sign-out': answer }).invoke)
    assert.equal(r.step, 'partial', String(answer))
    assert.equal(r.signedOut, false)
    assert.equal(r.deleted, ok) // the keys did go: the caller still applies them
  }
})

test('eraseData: deleted and signed out is done', async () => {
  const f = fake({ 'settings:delete': ok, 'auth:sign-out': true })
  assert.deepEqual(await eraseData(f.invoke), { step: 'done', deleted: ok, signedOut: true })
})
