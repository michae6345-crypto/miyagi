/** common/pttState.ts, offline: the one PTT state, stale-id dropping, release during start, empty, cancels, exits. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { active, PTT_REST, reducePtt, type PttInput, type PttState } from '../src/common/pttState'
import type { PttCancelReason } from '../src/main/pttProtocol'

/** Run events through the reducer; returns the last state and every final that came out. */
function run(events: PttInput[], from: PttState = PTT_REST): { s: PttState; finals: { id: string; text: string }[] } {
  let s = from
  const finals: { id: string; text: string }[] = []
  for (const e of events) {
    const r = reducePtt(s, e)
    s = r.state
    if (r.final) finals.push(r.final)
  }
  return { s, finals }
}
const down = (id: string): PttInput => ({ type: 'ptt', state: 'down', id })
const up = (id: string): PttInput => ({ type: 'ptt', state: 'up', id })
const listening = (id: string): PttInput => ({ type: 'listening', id })
const partial = (id: string, text: string): PttInput => ({ type: 'partial', id, text })
const final = (id: string, text: string): PttInput => ({ type: 'final', id, text })
const cancelled = (id: string, reason: PttCancelReason): PttInput => ({ type: 'cancelled', id, reason })

describe('the happy path', () => {
  test('down -> arming, listening -> listening with live text, up -> sending, final -> rest + the text once', () => {
    let { s } = run([down('a')])
    assert.equal(s.phase, 'arming')
    assert.equal(s.id, 'a')
    ;({ s } = run([listening('a'), partial('a', 'why does')], s))
    assert.equal(s.phase, 'listening')
    assert.equal(s.text, 'why does')
    ;({ s } = run([partial('a', 'why does the loss'), up('a')], s))
    assert.equal(s.phase, 'sending')
    assert.equal(s.text, 'why does the loss')
    const r = run([final('a', 'why does the loss go down')], s)
    assert.equal(r.s.phase, 'idle')
    assert.equal(r.s.id, undefined)
    assert.equal(r.s.text, '')
    assert.deepEqual(r.finals, [{ id: 'a', text: 'why does the loss go down' }])
  })

  test('a second final for the same id is spent: nothing is sent twice', () => {
    const r = run([down('a'), listening('a'), up('a'), final('a', 'one'), final('a', 'one')])
    assert.equal(r.finals.length, 1)
  })

  test('the final text is trimmed', () => {
    assert.deepEqual(run([down('a'), listening('a'), up('a'), final('a', '  hi  ')]).finals, [{ id: 'a', text: 'hi' }])
  })
})

describe('stale ids are dropped (a cancelled session can never speak)', () => {
  test('partial and final from an old id change nothing', () => {
    const base = run([down('a'), listening('a'), cancelled('a', 'esc'), down('b'), listening('b'), partial('b', 'fresh')]).s
    const r = run([partial('a', 'ghost'), final('a', 'ghost words'), listening('a'), up('a'), cancelled('a', 'timeout')], base)
    assert.equal(r.s.id, 'b')
    assert.equal(r.s.phase, 'listening')
    assert.equal(r.s.text, 'fresh')
    assert.equal(r.finals.length, 0)
  })

  test('events with no session at all are dropped', () => {
    const r = run([partial('z', 'x'), final('z', 'x'), up('z'), listening('z'), cancelled('z', 'short')])
    assert.equal(r.s.phase, 'idle')
    assert.equal(r.finals.length, 0)
  })

  test('a final after a cancel is dropped', () => {
    const r = run([down('a'), listening('a'), cancelled('a', 'keypress'), final('a', 'late')])
    assert.equal(r.finals.length, 0)
    assert.equal(r.s.phase, 'idle')
  })

  test('a new down replaces a session still in flight; the old id is stale from then on', () => {
    const r = run([down('a'), listening('a'), partial('a', 'old'), down('b'), final('a', 'old'), partial('b', 'new')])
    assert.equal(r.s.id, 'b')
    assert.equal(r.s.text, 'new')
    assert.equal(r.finals.length, 0)
  })
})

describe('release during the async start', () => {
  test('up while arming is remembered; the mic opening afterwards goes straight to sending', () => {
    let { s } = run([down('a'), up('a')])
    assert.equal(s.phase, 'arming')
    assert.equal(s.released, true)
    ;({ s } = run([listening('a')], s))
    assert.equal(s.phase, 'sending')
  })

  test('released before the mic opened, then a final: it is sent and the session ends', () => {
    const r = run([down('a'), up('a'), listening('a'), partial('a', 'quick one'), final('a', 'quick one')])
    assert.equal(r.s.phase, 'idle')
    assert.deepEqual(r.finals, [{ id: 'a', text: 'quick one' }])
  })

  test('released before the mic opened, helper cancels as too short: back to rest, nothing sent', () => {
    const r = run([down('a'), up('a'), cancelled('a', 'short')])
    assert.equal(r.s.phase, 'idle')
    assert.equal(r.s.lastCancel, 'short')
    assert.equal(r.finals.length, 0)
  })

  test('up for another id does not release this session', () => {
    const { s } = run([down('b'), up('a')])
    assert.equal(s.released, false)
    assert.equal(s.phase, 'arming')
  })
})

describe('empty and cancelled', () => {
  test('an empty or whitespace final sends nothing and goes straight back to rest', () => {
    for (const text of ['', '   ']) {
      const r = run([down('a'), listening('a'), up('a'), final('a', text)])
      assert.equal(r.s.phase, 'idle')
      assert.equal(r.s.lastCancel, 'empty')
      assert.equal(r.finals.length, 0)
    }
  })

  test('every cancel reason returns to rest and keeps the reason', () => {
    for (const reason of ['esc', 'keypress', 'short', 'empty', 'timeout', 'disabled'] as const) {
      const { s } = run([down('a'), listening('a'), partial('a', 'x'), cancelled('a', reason)])
      assert.equal(s.phase, 'idle', reason)
      assert.equal(s.text, '', reason)
      assert.equal(s.id, undefined, reason)
      assert.equal(s.lastCancel, reason)
    }
  })

  test('a new hold forgets the last cancel', () => {
    assert.equal(run([down('a'), cancelled('a', 'short'), down('b')]).s.lastCancel, undefined)
  })
})

describe('errors, exits and resets', () => {
  test('an error ends the session and carries its code; mic_denied also marks the permission', () => {
    const { s } = run([down('a'), listening('a'), { type: 'error', code: 'mic_denied', message: '' }])
    assert.equal(s.phase, 'error')
    assert.equal(s.code, 'mic_denied')
    assert.equal(s.id, undefined)
    assert.equal(s.perms.mic, 'denied')
    assert.equal(active(s), false)
  })

  test('input_denied marks input; other codes leave permissions alone', () => {
    assert.equal(run([{ type: 'error', code: 'input_denied', message: '' }]).s.perms.input, 'denied')
    assert.deepEqual(run([{ type: 'error', code: 'no_stt', message: '' }]).s.perms, PTT_REST.perms)
  })

  test('clear-error goes back to rest, and only from the error phase', () => {
    assert.equal(run([{ type: 'error', code: 'tap_failed', message: '' }, { type: 'clear-error' }]).s.phase, 'idle')
    const mid = run([down('a'), listening('a')]).s
    assert.equal(run([{ type: 'clear-error' }], mid).s.phase, 'listening')
  })

  test('the helper exiting mid-session releases everything and marks it unavailable', () => {
    const { s } = run([{ type: 'ready', stt: 'sfspeech', locale: 'en-US', chord: 'fn+control' }, down('a'), listening('a'), partial('a', 'x'), { type: 'exit' }])
    assert.equal(s.phase, 'idle')
    assert.equal(s.available, false)
    assert.equal(s.id, undefined)
  })

  test('reset (hard cap, disconnect) is back to rest from any phase, and keeps availability', () => {
    for (const evs of [[down('a')], [down('a'), listening('a')], [down('a'), listening('a'), up('a')]] as PttInput[][]) {
      const s = run([{ type: 'ready', stt: 'speechanalyzer', locale: 'en-US', chord: 'fn+control' }, ...evs, { type: 'reset' }]).s
      assert.equal(s.phase, 'idle')
      assert.equal(s.available, true)
    }
  })

  test('after any terminal event a new hold works', () => {
    for (const end of [cancelled('a', 'esc'), final('a', 'hi'), { type: 'exit' }, { type: 'reset' }] as PttInput[]) {
      const r = run([down('a'), listening('a'), end, down('b'), listening('b'), up('b'), final('b', 'again')])
      assert.equal(r.finals.at(-1)?.text, 'again')
    }
  })
})

describe('ready and perm', () => {
  test('ready makes it available; perm updates the rows without touching a session', () => {
    const { s } = run([down('a'), { type: 'ready', stt: 'speechanalyzer', locale: 'en-US', chord: 'fn+control' }, { type: 'perm', mic: 'granted', input: 'granted', assets: 'installed' }])
    assert.equal(s.available, true)
    assert.equal(s.phase, 'arming')
    assert.deepEqual(s.perms, { mic: 'granted', input: 'granted', assets: 'installed' })
  })
  test('a perm without assets keeps the last assets value', () => {
    const { s } = run([{ type: 'perm', mic: 'granted', input: 'granted', assets: 'missing' }, { type: 'perm', mic: 'granted', input: 'granted' }])
    assert.equal(s.perms.assets, 'missing')
  })
})
