/**
 * R20, the renderer half (features/auth/store.ts): the "Waiting for Google…" wait never outlives the sign-in.
 *
 *   Cancel here       the wait ends at once with a calm line, main is told (auth:cancel), Try again starts over
 *   Cancel at Google  main's feat:auth:attempt ends the wait at once with main's line (main keeps listening on purpose)
 *   timeout           main's plain line is shown as is
 *   came back         blur for >= 2 s then focus: after 1.5 s the wait ends ("Didn't finish in the browser?"); a real
 *                     sign-in landing inside that never flashes it; a quick glance back does nothing
 *   late answers      a failure that arrives after the wait ended never overwrites the line or a newer try; a late
 *                     success still signs in
 *   leaving           quiet (no line left behind), and it also ends a listener main kept up after the wait ended
 *
 * The renderer runs in Node: window.tut is a fake bridge (main), mock/scenarios a stub (bridge.ts imports it).
 * Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'

const dir = mkdtempSync(join(tmpdir(), 'signin-wait-'))
writeFileSync(join(dir, 'scenarios.mjs'), 'export const scenarios = {}')
const SCENARIOS = pathToFileURL(join(dir, 'scenarios.mjs')).href
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier)) return { url: SCENARIOS, shortCircuit: true }
    return next(specifier, context)
  }
})

// ---- a fake main -----------------------------------------------------------------------------------------------------
type Answer = { ok: boolean; reason?: string; message?: string; user?: unknown }
/** auth:google calls not answered yet, oldest first. auth:cancel answers the newest one 'cancelled', like main. */
const googles: ((a: Answer) => void)[] = []
const invoked: string[] = []
const feature = new Map<string, Set<(p?: unknown) => void>>()
const windowListeners = new Map<string, Set<() => void>>()
let focused = true

const tut = {
  platform: { os: 'darwin', keys: {}, pillTop: 0 },
  onEvent: () => () => {},
  onStatus: () => () => {},
  on: () => () => {},
  emit: () => {},
  ready: () => {},
  send: () => {},
  invoke: (channel: string): Promise<unknown> => {
    invoked.push(channel)
    if (channel === 'auth:google') return new Promise((resolve) => googles.push(resolve as (a: Answer) => void))
    if (channel === 'auth:cancel') {
      googles.pop()?.({ ok: false, reason: 'cancelled' })
      return Promise.resolve(true)
    }
    return Promise.resolve(null)
  },
  onFeature: (channel: string, cb: (p?: unknown) => void) => {
    if (!feature.has(channel)) feature.set(channel, new Set())
    feature.get(channel)!.add(cb)
    return () => feature.get(channel)!.delete(cb)
  }
}
const broadcast = (channel: string, payload?: unknown): void => feature.get(channel)?.forEach((cb) => cb(payload))
const fire = (ev: 'blur' | 'focus'): void => {
  focused = ev === 'focus'
  windowListeners.get(ev)?.forEach((fn) => fn())
}

const g = globalThis as Record<string, unknown>
g.window = {
  tut,
  addEventListener: (ev: string, fn: () => void) => {
    if (!windowListeners.has(ev)) windowListeners.set(ev, new Set())
    windowListeners.get(ev)!.add(fn)
  },
  removeEventListener: () => {}
}
g.document = { hasFocus: () => focused }
g.location = { hash: '', search: '', pathname: '/' }

const store = require('../src/renderer/src/features/auth/store') as typeof import('../src/renderer/src/features/auth/store')
const model = require('../src/renderer/src/features/auth/model') as typeof import('../src/renderer/src/features/auth/model')
const { useAuth, signInWith, cancelSignIn, leaveSignIn, signInOpen } = store
const { BACK_LINE, CANCELLED_LINE } = model

/** Let awaited invokes settle (a few microtask turns). */
const settle = async (): Promise<void> => {
  for (let i = 0; i < 5; i++) await Promise.resolve()
}
const state = (): { pending?: string; note?: string; user: unknown } => {
  const s = useAuth.getState()
  return { pending: s.pending, note: s.note, user: s.user }
}
const ALICE = { name: 'Alice Test', email: 'alice@example.com', avatarInitial: 'A' }
const CANCELLED_AT_GOOGLE = 'Sign-in was cancelled in the browser. Try again.'

beforeEach(() => {
  focused = true
  invoked.length = 0
})
afterEach(async () => {
  // Every test ends with nothing waiting and nobody signed in.
  for (const r of googles.splice(0)) r({ ok: false, reason: 'cancelled' })
  await settle()
  leaveSignIn()
  useAuth.setState({ user: null, note: undefined, pending: undefined })
})

describe('R20: the sign-in wait ends when the sign-in does', () => {
  test('Cancel in miyagi: the wait ends at once with a calm line, main is told, and Try again starts over', async () => {
    const p = signInWith('google')
    assert.equal(state().pending, 'google')
    cancelSignIn()
    assert.equal(state().pending, undefined, 'no waiting for main')
    assert.equal(state().note, CANCELLED_LINE)
    assert.ok(invoked.includes('auth:cancel'))
    await p
    assert.equal(state().note, CANCELLED_LINE, "main's late 'cancelled' answer changes nothing")
    void signInWith('google')
    assert.equal(state().pending, 'google', 'Try again works right away')
    assert.equal(state().note, undefined)
    assert.equal(invoked.filter((c) => c === 'auth:google').length, 2)
  })

  test('Cancel on Google’s page: main’s auth:attempt ends the wait at once; main is not told to stop', async () => {
    void signInWith('google')
    broadcast('auth:attempt', { reason: 'cancelled', message: CANCELLED_AT_GOOGLE })
    assert.deepEqual(state(), { pending: undefined, note: CANCELLED_AT_GOOGLE, user: null })
    assert.ok(!/tester/i.test(state().note ?? ''))
    assert.ok(!invoked.includes('auth:cancel'), "main keeps listening (the tab's Try again; a forged error can't end a real sign-in)")
    assert.equal(signInOpen(), true)
    // The learner finishes from the tab's Try again after all: a late success still signs in, and the line goes.
    googles.shift()!({ ok: true, user: ALICE })
    await settle()
    assert.deepEqual(state(), { pending: undefined, note: undefined, user: ALICE })
  })

  test('a late failure never overwrites the line shown or a newer try', async () => {
    void signInWith('google')
    broadcast('auth:attempt', { reason: 'failed', message: 'That sign-in expired or was already used. Try again.' })
    void signInWith('google') // Try again in miyagi: main replaces the old flow, which answers 'cancelled'
    googles.shift()!({ ok: false, reason: 'cancelled' })
    await settle()
    assert.equal(state().pending, 'google', 'the newer try is still waiting')
    assert.equal(state().note, undefined)
  })

  test('a timeout says plainly what happened', async () => {
    const p = signInWith('google')
    googles.shift()!({ ok: false, reason: 'timeout', message: 'No answer from Google after 5 minutes, so miyagi stopped waiting. Try again.' })
    await p
    assert.deepEqual(state(), { pending: undefined, note: 'No answer from Google after 5 minutes, so miyagi stopped waiting. Try again.', user: null })
  })

  test('an attempt broadcast reaches an idle window: nothing happens', () => {
    broadcast('auth:attempt', { reason: 'cancelled', message: CANCELLED_AT_GOOGLE })
    assert.deepEqual(state(), { pending: undefined, note: undefined, user: null })
  })

  test('reasonLine: a cancel always has a line; the denied fallback never says tester', () => {
    assert.equal(model.reasonLine('cancelled'), CANCELLED_LINE)
    assert.equal(model.reasonLine('cancelled', CANCELLED_AT_GOOGLE), CANCELLED_AT_GOOGLE)
    assert.doesNotMatch(model.reasonLine('denied'), /tester/i)
    assert.match(model.reasonLine('timeout'), /stopped waiting/)
  })
})

describe('R20: closing the browser tab (nothing comes back; the learner comes back to miyagi)', () => {
  beforeEach(() => mock.timers.enable({ apis: ['setTimeout', 'Date'] }))
  afterEach(() => mock.timers.reset())

  test('away 2 s or more, then back: after 1.5 s the wait ends with a calm line and Try again', async () => {
    void signInWith('google')
    fire('blur') // the browser came up
    mock.timers.tick(30_000)
    fire('focus') // the learner closed the tab and came back
    mock.timers.tick(1400)
    assert.equal(state().pending, 'google', 'a beat first: a real sign-in brings miyagi forward too')
    mock.timers.tick(100)
    assert.deepEqual(state(), { pending: undefined, note: BACK_LINE, user: null })
    assert.ok(!invoked.includes('auth:cancel'), 'main still listening: finishing in a still-open tab still signs in')
    googles.shift()!({ ok: true, user: ALICE })
    await settle()
    assert.deepEqual(state(), { pending: undefined, note: undefined, user: ALICE })
  })

  test('a real sign-in that brings miyagi forward never flashes the line', async () => {
    void signInWith('google')
    fire('blur')
    mock.timers.tick(20_000)
    fire('focus')
    googles.shift()!({ ok: true, user: ALICE })
    await settle()
    mock.timers.tick(5000)
    assert.deepEqual(state(), { pending: undefined, note: undefined, user: ALICE })
  })

  test('a quick glance back (under 2 s), or focus without a blur, keeps waiting', () => {
    void signInWith('google')
    fire('blur')
    mock.timers.tick(500)
    fire('focus')
    mock.timers.tick(5000)
    assert.equal(state().pending, 'google')
    fire('focus')
    mock.timers.tick(5000)
    assert.equal(state().pending, 'google')
  })

  test('back while the window has lost focus again: keeps waiting', () => {
    void signInWith('google')
    fire('blur')
    mock.timers.tick(10_000)
    fire('focus')
    fire('blur') // straight back to the browser
    mock.timers.tick(5000)
    assert.equal(state().pending, 'google')
  })
})

describe('R20: leaving the login', () => {
  test('mid-wait: quiet (no line left behind) and main is told', () => {
    void signInWith('google')
    leaveSignIn()
    assert.deepEqual(state(), { pending: undefined, note: undefined, user: null })
    assert.ok(invoked.includes('auth:cancel'))
  })

  test('after the wait ended but main still listens: main is told too', () => {
    void signInWith('google')
    broadcast('auth:attempt', { reason: 'cancelled', message: CANCELLED_AT_GOOGLE })
    assert.ok(!invoked.includes('auth:cancel'))
    leaveSignIn()
    assert.ok(invoked.includes('auth:cancel'))
  })

  test('nothing running: nothing is sent', () => {
    leaveSignIn()
    assert.deepEqual(invoked, [])
  })
})
