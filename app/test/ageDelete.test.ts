/**
 * age-delete lane (agents/age-delete.md), so the standard app command runs the tests that live next to their code:
 * the age maths, the age record on disk, Delete account's server outcomes, its erase list and wipe, its renderer flow.
 * Plus the main features wired together on a fake context: the step can't be skipped over IPC.
 */
import '../src/renderer/src/features/agegate/age.test'
import '../src/main/features/agegate/store.test'
import '../src/main/features/accountDelete/server.test'
import '../src/main/features/accountDelete/wipe.test'
// settings/privacy/erase.test.ts (Delete account's renderer flow) runs from test/privacy.test.ts.

import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { after, before, test } from 'node:test'
import agegate, { ageStepCleared } from '../src/main/features/agegate'
import auth, { needsLogin } from '../src/main/features/auth'
import { makeHarness, type Harness } from './harness'

let h: Harness
before(() => {
  h = makeHarness()
  agegate.setup(h.ctx)
  auth.setup(h.ctx)
})
after(() => h.close())

test('main: no Google sign-in and no guest path before the age step', async () => {
  assert.equal(ageStepCleared(), false)
  const g = (await h.invoke('auth:google', { mode: 'new' })) as { ok: boolean; reason?: string }
  assert.equal(g.ok, false)
  assert.equal(g.reason, 'age')
  assert.deepEqual(await h.invoke('auth:continue'), { next: 'none' })
  assert.equal(needsLogin(), true, 'the guest choice was refused')
})

test('main: a block can’t be lifted over IPC; the file holds only the result', async () => {
  const blocked = { blockedUntil: '2099-01-01' }
  assert.deepEqual(await h.invoke('agegate:set', blocked), blocked)
  assert.deepEqual(await h.invoke('agegate:set', { band: '18+', confirmed: '2026-11-21', birth: '1990-01-01' }), blocked)
  assert.equal(ageStepCleared(), false)
  const text = readFileSync(join(h.dir, 'age.json'), 'utf8')
  assert.deepEqual(JSON.parse(text), blocked)
  assert.ok(h.broadcasts.some(([c]) => c === 'agegate'))
})

test('main: a band on file clears the step (the guest path opens)', async () => {
  // A fresh file (the block above can't be lifted, by design): what Delete account's wipe leaves.
  const { rmSync } = await import('node:fs')
  rmSync(join(h.dir, 'age.json'))
  assert.deepEqual(await h.invoke('agegate:get'), null)
  const r = (await h.invoke('agegate:set', { band: '13-17', confirmed: '2026-11-21' })) as { band: string }
  assert.equal(r.band, '13-17')
  assert.equal(ageStepCleared(), true)
  assert.ok(existsSync(join(h.dir, 'age.json')))
  await h.invoke('auth:continue')
  assert.equal(needsLogin(), false, 'the guest choice went through')
})
