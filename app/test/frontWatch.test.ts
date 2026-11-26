/**
 * main/features/front-app.ts watchFront: the front app is read when it changes (an activation notification), not with
 * two lsappinfo processes every second (perf lane, Nov 25), and no read overlaps another.
 */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { setTimeout as sleep } from 'node:timers/promises'
import { watchFront } from '../src/main/features/front-app'

type Opts = { subscribe?: boolean; readMs?: number; fail?: boolean; lagMs?: number }
function harness(o: Opts = {}): { reads: () => number; fire: () => void; stop: () => void; gaveUp: () => boolean; unsubscribed: () => boolean; overlapped: () => boolean } {
  let reads = 0
  let inFlight = 0
  let overlapped = false
  let fire: () => void = () => undefined
  let gaveUp = false
  let unsubscribed = false
  const stop = watchFront({
    read: async () => {
      reads += 1
      inFlight += 1
      if (inFlight > 1) overlapped = true
      await sleep(o.readMs ?? 1)
      inFlight -= 1
      if (o.fail) throw new Error('lsappinfo: not found')
    },
    subscribe: (fn) => {
      if (o.subscribe === false) return undefined
      fire = fn
      return () => void (unsubscribed = true)
    },
    pollMs: 30,
    safetyMs: 10_000,
    lagMs: o.lagMs,
    maxFails: 3,
    onGiveUp: () => void (gaveUp = true)
  })
  return { reads: () => reads, fire: () => fire(), stop, gaveUp: () => gaveUp, unsubscribed: () => unsubscribed, overlapped: () => overlapped }
}

describe('front app watch', () => {
  test('with the notification: one read at start, then only when the front app changes', async () => {
    const h = harness()
    await sleep(120)
    assert.equal(h.reads(), 1) // no 1 s (here 30 ms) clock
    h.fire()
    await sleep(20)
    assert.equal(h.reads(), 2)
    h.stop()
    assert.equal(h.unsubscribed(), true)
  })

  test('without it: the old poll', async () => {
    const h = harness({ subscribe: false })
    await sleep(140)
    h.stop()
    assert.ok(h.reads() >= 3, `polled ${h.reads()} times`)
  })

  test('a burst of changes during a read is one more read, never two at once', async () => {
    const h = harness({ readMs: 30 })
    await sleep(5) // the first read is running
    h.fire()
    h.fire()
    h.fire()
    await sleep(100)
    h.stop()
    assert.equal(h.reads(), 2)
    assert.equal(h.overlapped(), false)
  })

  test('lsappinfo failing: gives up after maxFails and stops reading', async () => {
    const h = harness({ subscribe: false, fail: true })
    await sleep(200)
    const n = h.reads()
    assert.equal(h.gaveUp(), true)
    assert.equal(n, 3)
    h.fire()
    await sleep(50)
    assert.equal(h.reads(), n)
  })

  test('stopped: triggers do nothing', async () => {
    const h = harness()
    await sleep(10)
    h.stop()
    h.fire()
    await sleep(20)
    assert.equal(h.reads(), 1)
  })

  test('each trigger reads again a moment later (Launch Services can lag the notification)', async () => {
    const h = harness({ lagMs: 40 })
    await sleep(10)
    h.fire()
    await sleep(15)
    assert.equal(h.reads(), 2)
    await sleep(60)
    assert.equal(h.reads(), 3)
    // a burst of triggers is one lagged read, not one each
    h.fire()
    h.fire()
    await sleep(80)
    h.stop()
    assert.ok(h.reads() <= 6, `read ${h.reads()} times`)
  })
})
