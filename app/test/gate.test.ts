/** The launch gate (common/gate.ts rules, main/gate.ts live state and gateCore), offline. */
import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, test } from 'node:test'
import { cleanGate, firstNeeded, gateOpen } from '../src/common/gate'
import { gateCore, gateIsOpen, gateView, onGate, resetGateForTests, setGatePart } from '../src/main/gate'

const SKIP = 'MIYAGI_SKIP_ONBOARDING'
let skipBefore: string | undefined

beforeEach(() => {
  skipBefore = process.env[SKIP]
  delete process.env[SKIP]
  resetGateForTests()
})
afterEach(() => {
  if (skipBefore === undefined) delete process.env[SKIP]
  else process.env[SKIP] = skipBefore
  resetGateForTests()
})

describe('gate rules (common/gate.ts)', () => {
  test('open only when login, consent and setup are all true', () => {
    assert.equal(gateOpen({ login: false, consent: false, setup: false }), false)
    assert.equal(gateOpen({ login: true, consent: false, setup: false }), false)
    assert.equal(gateOpen({ login: false, consent: true, setup: true }), false)
    assert.equal(gateOpen({ login: true, consent: false, setup: true }), false, 'setup put off without consent stays closed')
    assert.equal(gateOpen({ login: true, consent: true, setup: false }), false)
    assert.equal(gateOpen({ login: true, consent: true, setup: true }), true)
    assert.equal(gateOpen({ login: false, consent: false, setup: false }, true), true, 'forced')
  })

  test('firstNeeded: login, then consent, then setup', () => {
    assert.equal(firstNeeded({ login: false, consent: false, setup: false }), 'login')
    assert.equal(firstNeeded({ login: false, consent: true, setup: true }), 'login')
    assert.equal(firstNeeded({ login: true, consent: false, setup: false }), 'consent')
    assert.equal(firstNeeded({ login: true, consent: false, setup: true }), 'consent', 'a newer policy version asks again')
    assert.equal(firstNeeded({ login: true, consent: true, setup: false }), 'setup')
    assert.equal(firstNeeded({ login: true, consent: true, setup: true }), undefined)
  })

  test('cleanGate reads malformed input as closed', () => {
    const closed = { login: false, consent: false, setup: false, open: false }
    for (const raw of [undefined, null, 'open', 42, [], { open: 'yes' }, { login: 1, consent: 'yes', setup: 'true', open: 1 }]) {
      assert.deepEqual(cleanGate(raw), closed, JSON.stringify(raw))
    }
    assert.deepEqual(cleanGate({ login: true, consent: true, setup: true, open: true, profile: true }), { login: true, consent: true, setup: true, open: true })
  })
})

describe('live gate (main/gate.ts)', () => {
  test('starts closed', () => {
    assert.equal(gateIsOpen(), false)
    assert.deepEqual(gateView(), { login: false, consent: false, setup: false, open: false })
  })

  test('opens only when login, consent and setup are all reported, and listeners hear each change', () => {
    const heard: boolean[] = []
    onGate((open) => heard.push(open))
    setGatePart('login', true)
    assert.equal(gateIsOpen(), false)
    setGatePart('setup', true)
    assert.equal(gateIsOpen(), false, 'no consent yet')
    setGatePart('consent', true)
    assert.equal(gateIsOpen(), true)
    setGatePart('setup', true) // no change, no call
    assert.deepEqual(heard, [false, false, true])
  })

  test('a sign-out (login false) closes it again', () => {
    setGatePart('login', true)
    setGatePart('consent', true)
    setGatePart('setup', true)
    setGatePart('login', false)
    assert.equal(gateIsOpen(), false)
    assert.deepEqual(gateView(), { login: false, consent: true, setup: true, open: false })
  })

  test('MIYAGI_SKIP_ONBOARDING=1 forces it open', () => {
    process.env[SKIP] = '1'
    assert.equal(gateIsOpen(), true)
    assert.equal(gateView().open, true)
  })

  test('a listener that throws does not stop the others', () => {
    let ran = false
    onGate(() => {
      throw new Error('boom')
    })
    onGate(() => (ran = true))
    const err = console.error
    console.error = () => undefined
    try {
      setGatePart('login', true)
    } finally {
      console.error = err
    }
    assert.equal(ran, true)
  })
})

describe('gateCore (index.ts: the overlay and the launcher key follow the gate)', () => {
  const fake = () => {
    const log: string[] = []
    return {
      log,
      core: {
        overlay: { showInactive: () => log.push('show'), hide: () => log.push('hide'), isDestroyed: () => false },
        launcherKey: (on: boolean) => log.push(on ? 'key+' : 'key-'),
        closed: () => log.push('closed')
      }
    }
  }

  test('closed: nothing shows, no key; open: show and key; closed again: hide, key off, launcher closed', () => {
    const { log, core } = fake()
    gateCore(core)
    setGatePart('login', true)
    setGatePart('setup', true)
    assert.deepEqual(log, [], 'no overlay and no launcher key before consent')
    setGatePart('consent', true)
    assert.deepEqual(log, ['show', 'key+'])
    setGatePart('login', false)
    assert.deepEqual(log, ['show', 'key+', 'hide', 'key-', 'closed'])
  })

  test('forced open: shows at once', () => {
    process.env[SKIP] = '1'
    const { log, core } = fake()
    gateCore(core)
    assert.deepEqual(log, ['show', 'key+'])
  })
})
