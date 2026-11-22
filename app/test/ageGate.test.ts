/**
 * age-delete fix round: a learner signed in BEFORE the age step existed (a stored session, no age.json) sees the step
 * once on the next launch, before anything else: main keeps the launch gate's login part closed until a result is on
 * file. Under 13 the gate stays closed and the session is kept (so the account can be deleted on the blocked screen).
 * Offline: a fake Supabase behind a stubbed fetch, a temp userData.
 */
import assert from 'node:assert/strict'
import { rmSync } from 'node:fs'
import { join } from 'node:path'
import { after, before, test } from 'node:test'
import agegate, { ageStepCleared } from '../src/main/features/agegate'
import auth, { accessToken, needsLogin } from '../src/main/features/auth'
import { gateView } from '../src/main/gate'
import { FakeCloud, FakeSupabase, makeHarness, stubFetch, writeSession, type Harness } from './harness'

const ALICE = { sub: 'user-alice', email: 'alice@example.com', name: 'Alice Test' }
let h: Harness
let restore: () => void

before(() => {
  const supa = new FakeSupabase()
  restore = stubFetch(supa, new FakeCloud())
  h = makeHarness()
  writeSession(h.dir, supa.session(ALICE, 3600)) // signed in on an earlier version: auth.bin, no age.json
  agegate.setup(h.ctx)
  auth.setup(h.ctx)
})
after(() => {
  h.close()
  restore()
})

test('signed in with no age result: the login is still needed and the gate stays closed', async () => {
  assert.ok(await accessToken(), 'the stored session loaded')
  assert.deepEqual(await h.invoke('auth:get'), { signedIn: true, name: 'Alice Test', email: 'alice@example.com', avatarInitial: 'A' })
  assert.equal(ageStepCleared(), false)
  assert.equal(needsLogin(), true)
  assert.equal(gateView().login, false, 'the flow opens on the login, where the age step comes first')
  assert.deepEqual(await h.invoke('auth:continue'), { next: 'none' }, 'Continue on "You are signed in" is refused')
  assert.equal(gateView().login, false)
})

test('under 13: the gate stays closed, the session is kept for Delete my account', async () => {
  await h.invoke('agegate:set', { blockedUntil: '2099-01-01' })
  assert.equal(needsLogin(), true)
  assert.equal(gateView().login, false)
  assert.ok(await accessToken(), 'still holds an access token: the blocked screen can delete the account')
  // A re-entry can't lift it.
  await h.invoke('agegate:set', { band: '18+', confirmed: '2026-11-21' })
  assert.equal(gateView().login, false)
})

test('a result on file opens the login part at once for a signed-in learner (no second sign-in)', async () => {
  rmSync(join(h.dir, 'age.json')) // as if the block had lapsed (or never was): the step answered 18+
  await h.invoke('agegate:set', { band: '18+', confirmed: '2026-11-21' })
  assert.equal(ageStepCleared(), true)
  assert.equal(needsLogin(), false)
  assert.equal(gateView().login, true, 'the gate re-reported on the age change')
})

test('the step only shows once: a relaunch with the result on file starts with the login open', async () => {
  const h2 = makeHarness()
  try {
    const supa = new FakeSupabase()
    writeSession(h2.dir, supa.session(ALICE, 3600))
    await h.invoke('agegate:set', { band: '18+', confirmed: '2026-11-21' })
    const { copyFileSync } = await import('node:fs')
    copyFileSync(join(h.dir, 'age.json'), join(h2.dir, 'age.json'))
    agegate.setup(h2.ctx)
    auth.setup(h2.ctx)
    assert.equal(needsLogin(), false)
    assert.equal(gateView().login, true)
  } finally {
    h2.close()
  }
})
