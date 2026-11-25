/**
 * MIC-30 (app side), the renderer half: features/session (what crosses IPC, the caps line) and the sign-in card's
 * signin_mode hook in features/signincard.
 *
 *   cleanSession    a bounded copy of session:get / feat:session: unknown fields dropped (never a token or an email),
 *                   numbers finite, plan and caps only while signed in
 *   capsLine        "$0.42 of $3.00 today · resets 4:00 PM" in the learner's local time; tomorrow; no cap; past times
 *   promptsOnBuild  "build" / "all" and a guest → the card at the start of a build; "off", signed in or linked → not
 *   signincard      the first lesson.building of a build raises the card once; "off" waits for the cloud's notice
 *
 * Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { pathToFileURL } from 'node:url'

const dir = mkdtempSync(join(tmpdir(), 'session-'))
writeFileSync(join(dir, 'scenarios.mjs'), 'export const scenarios = {}')
const SCENARIOS = pathToFileURL(join(dir, 'scenarios.mjs')).href
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier)) return { url: SCENARIOS, shortCircuit: true }
    return next(specifier, context)
  }
})

const g = globalThis as Record<string, unknown>
g.window = {
  tut: {
    platform: { os: 'darwin', keys: {}, pillTop: 0 },
    onEvent: () => () => {},
    onStatus: () => () => {},
    on: () => () => {},
    emit: () => {},
    ready: () => {},
    send: () => {},
    invoke: (): Promise<unknown> => Promise.resolve(null),
    onFeature: () => () => {}
  },
  addEventListener: () => {},
  removeEventListener: () => {}
}
g.document = { hasFocus: () => true }
g.location = { hash: '', search: '', pathname: '/' }

const M = require('../src/renderer/src/features/session/model') as typeof import('../src/renderer/src/features/session/model')
const { cleanSession, capsLine, resetLabel, promptsOnBuild, planLabel, money } = M

const LA = { timeZone: 'America/Los_Angeles', locale: 'en-US' }
const BERLIN = { timeZone: 'Europe/Berlin', locale: 'en-US' }
const NOW = new Date('2026-11-24T18:00:00Z') // 10:00 AM in Los Angeles, 7:00 PM in Berlin
const MIDNIGHT = '2026-11-25T00:00:00Z' // the cloud's resets_at: the next UTC midnight
const caps = { dailyUsd: 3, usedUsd: 0.42, tokens: 20000000, usedTokens: 183000, resetsAt: MIDNIGHT }

describe('cleanSession (IPC)', () => {
  test('a signed-in view comes through as is', () => {
    const v = { signedIn: true, linked: true, signinMode: 'build', plan: 'free', caps, fetchedAt: '2026-11-24T17:59:00.000Z' }
    assert.deepEqual(cleanSession(v), v)
  })
  test('unknown fields are dropped: never a token, an email or an account id', () => {
    const raw = { signedIn: true, linked: true, signinMode: 'off', plan: 'pro', caps: { ...caps, token: 'mi_x' }, email: 'a@b.co', access_token: 'eyJ.x.y', account: { id: 'u1' } }
    const v = cleanSession(raw)
    const s = JSON.stringify(v)
    for (const leak of ['mi_', '@', 'eyJ', 'u1', 'account', 'email']) assert.ok(!s.includes(leak), leak)
  })
  test('signed out: plan and caps are dropped even if sent', () => {
    assert.deepEqual(cleanSession({ signedIn: false, linked: false, signinMode: 'all', plan: 'pro', caps }), { signedIn: false, linked: false, signinMode: 'all' })
  })
  test('junk is bounded: modes, numbers, dates, shapes', () => {
    assert.equal(cleanSession(null), null)
    assert.equal(cleanSession('session'), null)
    assert.equal(cleanSession([1]), null)
    assert.equal(cleanSession({ signinMode: '0' })?.signinMode, 'off')
    assert.equal(cleanSession({ signedIn: 'yes' })?.signedIn, false)
    assert.equal(cleanSession({ signedIn: true, caps: { ...caps, usedUsd: NaN } })?.caps, undefined)
    assert.equal(cleanSession({ signedIn: true, caps: { ...caps, usedUsd: -1 } })?.caps, undefined)
    assert.equal(cleanSession({ signedIn: true, caps: { ...caps, dailyUsd: 1e9 } })?.caps?.dailyUsd, null)
    assert.equal(cleanSession({ signedIn: true, caps: { ...caps, resetsAt: 'soon' } })?.caps?.resetsAt, undefined)
    assert.equal(cleanSession({ signedIn: true, plan: 'enterprise' })?.plan, undefined)
    assert.equal(cleanSession({ fetchedAt: 'x'.repeat(50) })?.fetchedAt, undefined)
  })
})

describe('capsLine', () => {
  test('the example line, local time', () => {
    assert.equal(capsLine(caps, NOW, LA), '$0.42 of $3.00 today · resets 4:00 PM')
  })
  test('ahead of UTC the reset is tomorrow morning', () => {
    assert.equal(capsLine(caps, NOW, BERLIN), '$0.42 of $3.00 today · resets tomorrow 1:00 AM')
  })
  test('no daily cap (Pro, or the cap off): only what was used, no reset', () => {
    assert.equal(capsLine({ ...caps, dailyUsd: null, usedUsd: 1.5 }, NOW, LA), '$1.50 used today')
  })
  test('a past or missing reset time: the use alone; over the cap never reads above it', () => {
    assert.equal(capsLine({ ...caps, resetsAt: '2026-11-24T00:00:00Z' }, NOW, LA), '$0.42 of $3.00 today')
    assert.equal(capsLine({ ...caps, resetsAt: undefined }, NOW, LA), '$0.42 of $3.00 today')
    assert.equal(capsLine({ ...caps, usedUsd: 3.07 }, NOW, LA), '$3.00 of $3.00 today · resets 4:00 PM')
  })
  test('nothing to show: null; calm copy (no exclamation, short)', () => {
    assert.equal(capsLine(undefined, NOW, LA), null)
    const line = capsLine(caps, NOW, LA) ?? ''
    assert.ok(!line.includes('!'))
    assert.ok(line.split(/\s+/).length <= 12)
  })
  test('helpers', () => {
    assert.equal(money(0), '$0.00')
    assert.equal(money(0.005), '$0.01')
    assert.equal(money(12.3), '$12.30')
    assert.equal(planLabel('pro'), 'Pro plan')
    assert.equal(planLabel(undefined), 'Free plan')
    assert.equal(resetLabel('2026-11-27T00:00:00Z', NOW, LA), 'Nov 26')
  })
})

describe('promptsOnBuild', () => {
  const guest = (mode: 'off' | 'build' | 'all') => ({ signedIn: false, linked: false, signinMode: mode })
  test('"build" and "all" prompt a guest; "off" never does', () => {
    assert.equal(promptsOnBuild(guest('build'), false), true)
    assert.equal(promptsOnBuild(guest('all'), false), true)
    assert.equal(promptsOnBuild(guest('off'), false), false)
  })
  test('signed in, or an install linked before (sign-out never unlinks), or no data: no card', () => {
    assert.equal(promptsOnBuild(guest('build'), true), false)
    assert.equal(promptsOnBuild({ ...guest('build'), linked: true }, false), false)
    assert.equal(promptsOnBuild(null, false), false)
  })
})

describe('signincard at the start of a build', () => {
  const { dispatch, emitUi } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
  const { useAuth } = require('../src/renderer/src/features/auth/store') as typeof import('../src/renderer/src/features/auth/store')
  const { useSession } = require('../src/renderer/src/features/session/store') as typeof import('../src/renderer/src/features/session/store')
  const { useSignInCard } = require('../src/renderer/src/features/signincard/store') as typeof import('../src/renderer/src/features/signincard/store')
  const send = (type: string, payload: unknown): void => dispatch({ type, payload } as Parameters<typeof dispatch>[0])
  const building = (): void => send('lesson.building', { message: 'Reading the video', progress: 0.1, stage: 'transcript' })
  const fresh = (mode: 'off' | 'build' | 'all', signedIn = false, linked = false): void => {
    emitUi('reset')
    useAuth.setState({ user: signedIn ? { name: 'Sam', email: 's@x.co', avatarInitial: 'S' } : null })
    useSession.setState({ view: { signedIn, linked, signinMode: mode }, loaded: true })
  }

  test('"build": a guest gets the card as the build starts, once per build', () => {
    fresh('build')
    building()
    assert.ok(useSignInCard.getState().signin)
    useSignInCard.setState({ signin: undefined }) // Not now
    building() // the same build's heartbeat
    assert.equal(useSignInCard.getState().signin, undefined)
    send('lesson.ready', { lesson: { id: 'l', title: 't', sources: [] }, steps: [] })
    building() // the next build
    assert.ok(useSignInCard.getState().signin)
  })
  test('"all" too; a failed build ends it, so the next one asks again', () => {
    fresh('all')
    building()
    assert.ok(useSignInCard.getState().signin)
    useSignInCard.setState({ signin: undefined })
    send('lesson.building', { message: '', progress: 0, failed: true })
    building()
    assert.ok(useSignInCard.getState().signin)
  })
  test('"off": nothing until the cloud says so (the notice path still works)', () => {
    fresh('off')
    building()
    assert.equal(useSignInCard.getState().signin, undefined)
    send('cloud.notice', { reason: 'signin_required', status: 401 })
    assert.ok(useSignInCard.getState().signin)
  })
  test('signed in, or a linked install: no card at the build start', () => {
    fresh('build', true, true)
    building()
    assert.equal(useSignInCard.getState().signin, undefined)
    fresh('build', false, true)
    building()
    assert.equal(useSignInCard.getState().signin, undefined)
  })
})
