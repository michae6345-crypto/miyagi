/** core/islandState.ts, offline: every extended state without an owner collapses, and acting twice is harmless. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import {
  IDLE_HOVER_MS,
  isExtendedSize,
  isPillMode,
  ORPHAN_HOVER_GRACE_MS,
  OWNERLESS_GRACE_MS,
  resolveMode,
  watchdogStep,
  WATCH_REST,
  type WatchInput
} from '../src/renderer/src/core/islandState'
import { pill } from '../src/renderer/src/core/theme'

const card = { id: 'card', width: 352 }
const idle = { id: 'idle' }
const base = (over: Partial<WatchInput>): WatchInput => ({
  mode: idle,
  size: { w: 120, h: pill.height },
  hover: false,
  pointerIn: false,
  lastActivity: 0,
  now: 0,
  ...over
})

describe('resolveMode', () => {
  test('the first active mode wins, none = -1', () => {
    assert.equal(resolveMode([false, true, true]), 1)
    assert.equal(resolveMode([false, false]), -1)
    assert.equal(resolveMode([]), -1)
  })
  test('pill vs card', () => {
    assert.equal(isPillMode(undefined), true)
    assert.equal(isPillMode(idle), true)
    assert.equal(isPillMode(card), false)
    assert.equal(isExtendedSize({ w: 352, h: 200 }), true)
    assert.equal(isExtendedSize({ w: 200, h: pill.height }), false)
  })
})

describe('watchdogStep', () => {
  test('a pill at rest does nothing', () => {
    const r = watchdogStep(WATCH_REST, base({ now: 10_000 }))
    assert.deepEqual(r.action, { resetSize: false, clearHover: false })
  })

  test('a card with an owner is left alone however long it stays', () => {
    let s = WATCH_REST
    for (let t = 0; t <= 60_000; t += 500) {
      const r = watchdogStep(s, base({ mode: card, size: { w: 352, h: 200 }, now: t, lastActivity: t }))
      s = r.state
      assert.equal(r.action.resetSize, false)
    }
  })

  test('card-sized with no mode, or only a pill mode, collapses after the grace, not before', () => {
    for (const mode of [undefined, idle]) {
      let s = WATCH_REST
      let acted = -1
      for (let t = 1000; t <= 5000; t += 500) {
        const r = watchdogStep(s, base({ mode, size: { w: 352, h: 200 }, now: t, lastActivity: t }))
        s = r.state
        if (r.action.resetSize) {
          acted = t
          break
        }
      }
      assert.ok(acted >= 1000 + OWNERLESS_GRACE_MS, `acted at ${acted}`)
      assert.ok(acted > 0)
    }
  })

  test('a card claimed again mid-grace restarts the clock (a mode swap is not a fault)', () => {
    let s = watchdogStep(WATCH_REST, base({ mode: undefined, size: { w: 352, h: 200 }, now: 1000 })).state
    s = watchdogStep(s, base({ mode: card, size: { w: 352, h: 200 }, now: 1500 })).state
    assert.equal(s.ownerlessSince, 0)
    const r = watchdogStep(s, base({ mode: undefined, size: { w: 352, h: 200 }, now: 1700 }))
    assert.equal(r.action.resetSize, false)
  })

  test('acting is idempotent: after the reset the next tick does nothing', () => {
    const first = watchdogStep({ ownerlessSince: 1, orphanSince: 0 }, base({ mode: undefined, size: { w: 352, h: 200 }, now: 1 + OWNERLESS_GRACE_MS }))
    assert.equal(first.action.resetSize, true)
    const second = watchdogStep(first.state, base({ mode: undefined, size: { w: 120, h: pill.height }, now: 5000 }))
    assert.equal(second.action.resetSize, false)
  })

  test('hover with the pointer gone collapses after the orphan grace', () => {
    const a = watchdogStep(WATCH_REST, base({ hover: true, pointerIn: false, now: 1000, lastActivity: 1000 }))
    assert.equal(a.action.clearHover, false)
    const b = watchdogStep(a.state, base({ hover: true, pointerIn: false, now: 1000 + ORPHAN_HOVER_GRACE_MS, lastActivity: 1000 }))
    assert.equal(b.action.clearHover, true)
  })

  test('hover with the pointer on it stays while it moves, collapses once it has been still for IDLE_HOVER_MS', () => {
    const live = watchdogStep(WATCH_REST, base({ hover: true, pointerIn: true, now: 100_000, lastActivity: 99_000 }))
    assert.equal(live.action.clearHover, false)
    const stale = watchdogStep(WATCH_REST, base({ hover: true, pointerIn: true, now: 100_000, lastActivity: 100_000 - IDLE_HOVER_MS }))
    assert.equal(stale.action.clearHover, true)
  })

  test('no hover, no hover action', () => {
    const r = watchdogStep(WATCH_REST, base({ hover: false, now: 1e9, lastActivity: 0 }))
    assert.equal(r.action.clearHover, false)
  })
})
