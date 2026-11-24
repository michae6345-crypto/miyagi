/**
 * MIC-17 (app side), features/signincard: the cloud refused a lesson build claim (server/lesson/cloud_cache.py
 * on_notice) and the app says so calmly.
 *
 *   parseNotice    a bounded, typed copy of the engine's {reason, status, resets_at?}; junk is dropped
 *   classify       401 signin_required = the sign-in card; any other 401 / a 403 = nothing; every 429 = a cap line
 *   formatReset    the reset time in the learner's local time: today, tomorrow, or a date; none when past or bad
 *   capLine        one line per limit kind (anon_daily_cap, user_daily_cap and the older caps), 12 words or fewer
 *   store          cloud.notice and error{notice} both land; the error's pill line is dropped; a signed-in learner
 *                  gets no card; Esc closes only the surface on the island; signing in closes the card
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

const dir = mkdtempSync(join(tmpdir(), 'signincard-'))
writeFileSync(join(dir, 'scenarios.mjs'), 'export const scenarios = {}')
const SCENARIOS = pathToFileURL(join(dir, 'scenarios.mjs')).href
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier)) return { url: SCENARIOS, shortCircuit: true }
    return next(specifier, context)
  }
})

const invoked: string[] = []
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
    invoke: (channel: string): Promise<unknown> => {
      invoked.push(channel)
      // A sign-in that never answers in this test: the card must not close on its own.
      if (channel === 'auth:google') return new Promise(() => {})
      return Promise.resolve(null)
    },
    onFeature: () => () => {}
  },
  addEventListener: () => {},
  removeEventListener: () => {}
}
g.document = { hasFocus: () => true }
g.location = { hash: '', search: '', pathname: '/' }

const N = require('../src/renderer/src/features/signincard/notice') as typeof import('../src/renderer/src/features/signincard/notice')
const { parseNotice, classify, capKind, formatReset, capLine, SIGNIN } = N

const LA = { timeZone: 'America/Los_Angeles', locale: 'en-US' }
const NOW = new Date('2026-11-24T18:00:00Z') // 10:00 AM in Los Angeles
const words = (s: string): number => s.trim().split(/\s+/).length

describe('parseNotice', () => {
  test('the engine dict, as on_notice sends it', () => {
    assert.deepEqual(parseNotice({ reason: 'signin_required', status: 401 }), { reason: 'signin_required', status: 401 })
    assert.deepEqual(parseNotice({ reason: 'anon_daily_cap', status: 429, resets_at: '2026-11-25T00:00:00Z' }), {
      reason: 'anon_daily_cap',
      status: 429,
      resetsAt: '2026-11-25T00:00:00Z'
    })
  })
  test('resetsAt is accepted too; a bad or oversized time is dropped, not the notice', () => {
    assert.equal(parseNotice({ reason: 'user_daily_cap', status: 429, resetsAt: '2026-11-25T00:00:00Z' })?.resetsAt, '2026-11-25T00:00:00Z')
    assert.equal(parseNotice({ reason: 'user_daily_cap', status: 429, resets_at: 'tomorrow' })?.resetsAt, undefined)
    assert.equal(parseNotice({ reason: 'user_daily_cap', status: 429, resets_at: '2026-11-25T00:00:00Z'.padEnd(60, ' ') })?.resetsAt, undefined)
  })
  test('a status-only reason (the engine falls back to the HTTP status) and a junk reason', () => {
    assert.deepEqual(parseNotice({ reason: '429', status: 429 }), { reason: '429', status: 429 })
    assert.deepEqual(parseNotice({ reason: '<b>hi</b>', status: '429' }), { reason: '429', status: 429 })
  })
  test('junk is null', () => {
    for (const raw of [null, undefined, 'x', 3, [], {}, { reason: 'x' }, { reason: 'x', status: 200 }, { reason: 'x', status: 500 }, { status: 4.5 }])
      assert.equal(parseNotice(raw), null, JSON.stringify(raw))
  })
})

describe('classify', () => {
  test('401 signin_required is the sign-in card', () => {
    assert.deepEqual(classify({ reason: 'signin_required', status: 401 }), { kind: 'signin' })
  })
  test('any other 401, and 403, get no UI (the token heal and config.status own those)', () => {
    assert.equal(classify({ reason: '401', status: 401 }), null)
    assert.equal(classify({ reason: 'unknown_token', status: 401 }), null)
    assert.equal(classify({ reason: 'install_disabled', status: 403 }), null)
  })
  test('every 429 is a cap, told apart by limit', () => {
    const cases: Array<[string, string]> = [
      ['anon_daily_cap', 'anon'],
      ['user_daily_cap', 'user'],
      ['daily_requests', 'daily'],
      ['daily_spend', 'daily'],
      ['daily_usd', 'global'],
      ['lesson_builds', 'builds'],
      ['miyagi_lesson_quota', 'builds'],
      ['ip_hourly', 'rate'],
      ['token_hourly', 'rate'],
      ['some_new_hourly', 'rate'],
      ['new_installs', 'full'],
      ['429', 'other'],
      ['brand_new_cap', 'other']
    ]
    for (const [reason, cap] of cases) {
      assert.equal(capKind(reason), cap, reason)
      assert.deepEqual(classify({ reason, status: 429 }), { kind: 'cap', cap }, reason)
    }
  })
})

describe('formatReset (local time)', () => {
  test('later today: "at 4:00 PM" (UTC midnight seen from Los Angeles)', () => {
    assert.equal(formatReset('2026-11-25T00:00:00Z', NOW, LA), 'at 4:00 PM')
  })
  test('the next local day: "tomorrow at ..."', () => {
    assert.equal(formatReset('2026-11-25T17:30:00Z', NOW, LA), 'tomorrow at 9:30 AM')
  })
  test('further out: a date', () => {
    assert.equal(formatReset('2026-12-01T00:00:00Z', NOW, LA), 'on Nov 30')
  })
  test('the same instant is a different day in another zone', () => {
    // 00:00Z is 9:00 AM on the 25th in Tokyo, whose "now" is already 3:00 AM on the 25th.
    assert.equal(formatReset('2026-11-25T00:00:00Z', NOW, { timeZone: 'Asia/Tokyo', locale: 'en-US' }), 'at 9:00 AM')
    assert.equal(formatReset('2026-11-25T00:00:00Z', NOW, { timeZone: 'UTC', locale: 'en-US' }), 'tomorrow at 12:00 AM')
  })
  test('the system zone by default (no throw, a time)', () => {
    assert.match(formatReset('2026-11-25T00:00:00Z', NOW) ?? '', /^(at|tomorrow at|on) /)
  })
  test('none for a missing, bad or past time', () => {
    assert.equal(formatReset(undefined, NOW, LA), null)
    assert.equal(formatReset('soon', NOW, LA), null)
    assert.equal(formatReset('2026-11-24T17:00:00Z', NOW, LA), null)
    assert.equal(formatReset(NOW.toISOString(), NOW, LA), null)
  })
})

describe('capLine', () => {
  const at = '2026-11-25T00:00:00Z'
  test('the example line', () => {
    assert.equal(capLine({ reason: 'user_daily_cap', status: 429, resetsAt: at }, NOW, LA), "You've used today's free help. It resets at 4:00 PM.")
  })
  test('anon and user are told apart', () => {
    assert.equal(capLine({ reason: 'anon_daily_cap', status: 429, resetsAt: at }, NOW, LA), "You've used today's free guest help. It resets at 4:00 PM.")
  })
  test('the other kinds', () => {
    assert.equal(capLine({ reason: 'daily_requests', status: 429, resetsAt: at }, NOW, LA), "You've used today's free help. It resets at 4:00 PM.")
    assert.equal(capLine({ reason: 'daily_usd', status: 429, resetsAt: at }, NOW, LA), "miyagi is at today's limit. It resets at 4:00 PM.")
    assert.equal(capLine({ reason: 'lesson_builds', status: 429, resetsAt: '2026-12-01T00:00:00Z' }, NOW, LA), "You've used this month's new lessons. More on Nov 30.")
    assert.equal(capLine({ reason: 'ip_hourly', status: 429, resetsAt: '2026-11-24T18:05:00Z' }, NOW, LA), 'Too many requests just now. Try again at 10:05 AM.')
    assert.equal(capLine({ reason: 'new_installs', status: 429, resetsAt: at }, NOW, LA), 'miyagi is full today. Try again at 4:00 PM.')
    assert.equal(capLine({ reason: '429', status: 429, resetsAt: at }, NOW, LA), "You've reached a limit for now. Try again at 4:00 PM.")
  })
  test('without a reset time the line still reads', () => {
    assert.equal(capLine({ reason: 'user_daily_cap', status: 429 }, NOW, LA), "You've used today's free help. It resets soon.")
    assert.equal(capLine({ reason: 'ip_hourly', status: 429 }, NOW, LA), 'Too many requests just now. Try again later.')
  })
  test('brand: 12 words or fewer, lowercase miyagi, no exclamation marks, even with the longest time', () => {
    const kinds = ['anon_daily_cap', 'user_daily_cap', 'daily_requests', 'daily_usd', 'lesson_builds', 'ip_hourly', 'new_installs', '429']
    for (const reason of kinds)
      for (const resetsAt of [undefined, '2026-11-25T17:30:00Z', '2026-12-01T00:00:00Z']) {
        const line = capLine({ reason, status: 429, resetsAt }, NOW, LA)
        assert.ok(words(line) <= 12, `${line} (${words(line)} words)`)
        assert.ok(!line.includes('Miyagi') && !line.includes('!'), line)
      }
    assert.ok(words(`${SIGNIN.title}. ${SIGNIN.body}`) <= 12)
  })
})

describe('store', () => {
  const { dispatch, emitUi } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
  const { useLesson, notify } = require('../src/renderer/src/core/lesson') as typeof import('../src/renderer/src/core/lesson')
  const { useAuth } = require('../src/renderer/src/features/auth/store') as typeof import('../src/renderer/src/features/auth/store')
  const S = require('../src/renderer/src/features/signincard/store') as typeof import('../src/renderer/src/features/signincard/store')
  const { useSignInCard, receive, setVisible, signIn } = S
  const fresh = (): void => {
    emitUi('reset')
    useAuth.setState({ user: null, pending: undefined, note: undefined })
  }
  const send = (type: string, payload: unknown): void => dispatch({ type, payload } as Parameters<typeof dispatch>[0])

  test('cloud.notice 401 signin_required raises the card; Not now via Esc closes it once it is on the island', () => {
    fresh()
    send('cloud.notice', { reason: 'signin_required', status: 401 })
    assert.ok(useSignInCard.getState().signin)
    emitUi('dismiss') // not on the island yet (a higher card): Esc is for that one
    assert.ok(useSignInCard.getState().signin)
    setVisible('signin', true)
    emitUi('dismiss')
    assert.equal(useSignInCard.getState().signin, undefined)
  })

  test('cloud.notice is a known wire frame (not dropped) and a 429 cap reaches the cap line', () => {
    fresh()
    const { parseEngineMessage } = require('../src/common/wire') as typeof import('../src/common/wire')
    const frame = { type: 'cloud.notice', payload: { reason: 'lesson_builds', status: 429, resets_at: '2026-12-01T00:00:00Z' } }
    const msg = parseEngineMessage(JSON.stringify(frame))
    assert.deepEqual(msg, frame)
    dispatch(msg!)
    assert.equal(useSignInCard.getState().cap?.kind, 'builds')
    assert.equal(useSignInCard.getState().signin, undefined)
  })

  test('the error fallback: the notice lands and the generic pill line goes', async () => {
    fresh()
    send('error', { message: 'Sign in to build new lessons.', notice: { reason: 'signin_required', status: 401 } })
    assert.ok(useSignInCard.getState().signin)
    await new Promise((r) => setTimeout(r, 0))
    assert.ok(!useLesson.getState().notices.some((n) => n.id === 'engine-error'))
  })

  test('a plain engine error is left alone', async () => {
    fresh()
    send('error', { message: 'Something else' })
    await new Promise((r) => setTimeout(r, 0))
    assert.equal(useSignInCard.getState().signin, undefined)
    assert.ok(useLesson.getState().notices.some((n) => n.id === 'engine-error'))
  })

  test('a signed-in learner gets no card; a token 401 gets nothing', () => {
    fresh()
    useAuth.setState({ user: { avatarInitial: 'S' } })
    assert.equal(receive({ reason: 'signin_required', status: 401 }), null)
    useAuth.setState({ user: null })
    assert.equal(receive({ reason: '401', status: 401 }), null)
    assert.equal(useSignInCard.getState().signin, undefined)
  })

  test('Sign in starts the Google flow; a sign-in that lands closes the card and says so', () => {
    fresh()
    receive({ reason: 'signin_required', status: 401 })
    invoked.length = 0
    signIn()
    assert.deepEqual(invoked, ['auth:google'])
    assert.ok(useSignInCard.getState().signin, 'still up while the browser is out')
    useAuth.setState({ user: { name: 'Sam', avatarInitial: 'S' } })
    assert.equal(useSignInCard.getState().signin, undefined)
    assert.ok(useLesson.getState().notices.some((n) => n.id === 'signincard-done'))
    notify('x') // keep the queue moving for later tests
  })

  test('a cap sets one line with the local reset time, and Esc closes it when shown', () => {
    fresh()
    assert.equal(receive({ reason: 'user_daily_cap', status: 429, resets_at: '2026-11-25T00:00:00Z' }, NOW), 'cap')
    assert.match(useSignInCard.getState().cap?.line ?? '', /^You've used today's free help\. It resets /)
    assert.equal(useSignInCard.getState().cap?.kind, 'user')
    setVisible('cap', true)
    emitUi('dismiss')
    assert.equal(useSignInCard.getState().cap, undefined)
  })
})
