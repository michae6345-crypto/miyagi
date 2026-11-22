import assert from 'node:assert/strict'
import { test } from 'node:test'
import { CALM_MS, calmGate, isTyping, type Timers } from '../src/renderer/src/features/spotlight/calm'

/** Manual clock: timers fire only when advance() passes them. */
function clock(): { timers: Timers; advance: (ms: number) => void; pending: () => number } {
  let now = 0
  let id = 0
  const q = new Map<number, { at: number; fn: () => void }>()
  return {
    timers: {
      set: (fn, ms) => (q.set(++id, { at: now + ms, fn }), id),
      clear: (t) => void q.delete(t as number)
    },
    advance(ms) {
      now += ms
      for (const [k, v] of [...q]) if (v.at <= now && q.delete(k)) v.fn()
    },
    pending: () => q.size
  }
}

test('calm: closed until a step starts, then admits and fades after CALM_MS', () => {
  const c = clock()
  let fades = 0
  const g = calmGate(() => fades++, CALM_MS, c.timers)
  assert.equal(g.admit(), false)
  g.arm()
  assert.equal(g.admit(), true)
  g.shown()
  c.advance(CALM_MS - 1)
  assert.equal(fades, 0)
  c.advance(1)
  assert.equal(fades, 1)
  // the engine re-sends the same target: refused, so it never comes back by itself
  assert.equal(g.admit(), false)
})

test('calm: shown() is once per episode, re-sends do not extend the count', () => {
  const c = clock()
  let fades = 0
  const g = calmGate(() => fades++, 1000, c.timers)
  g.arm()
  g.shown()
  c.advance(600)
  g.shown()
  g.shown()
  c.advance(400)
  assert.equal(fades, 1)
})

test('calm: the first real keystroke fades a visible box and cancels the count', () => {
  const c = clock()
  let fades = 0
  const g = calmGate(() => fades++, 1000, c.timers)
  g.arm()
  g.keystroke() // nothing visible yet: no fade, gate stays open
  assert.equal(fades, 0)
  assert.equal(g.admit(), true)
  g.shown()
  g.keystroke()
  assert.equal(fades, 1)
  assert.equal(c.pending(), 0)
  assert.equal(g.admit(), false)
  g.keystroke()
  assert.equal(fades, 1)
})

test('calm: Not yet (arm) reopens the gate after a fade', () => {
  const c = clock()
  let fades = 0
  const g = calmGate(() => fades++, 1000, c.timers)
  g.arm()
  g.shown()
  c.advance(1000)
  assert.equal(g.admit(), false)
  g.arm() // offtrack
  assert.equal(g.admit(), true)
  g.shown()
  c.advance(1000)
  assert.equal(fades, 2)
})

test('calm: a pinned (Show me) box ignores the count and typing', () => {
  const c = clock()
  let fades = 0
  const g = calmGate(() => fades++, 1000, c.timers)
  g.arm()
  g.shown()
  g.arm(true) // Show me answered while the step-start box was up: the count stops
  assert.equal(c.pending(), 0)
  c.advance(10_000)
  g.keystroke()
  assert.equal(fades, 0)
  assert.equal(g.admit(), true)
})

test('calm: reset closes without a fade callback and drops the count', () => {
  const c = clock()
  let fades = 0
  const g = calmGate(() => fades++, 1000, c.timers)
  g.arm()
  g.shown()
  g.reset()
  c.advance(5000)
  assert.equal(fades, 0)
  assert.equal(g.admit(), false)
})

test('calm: only real typing counts as a keystroke', () => {
  assert.equal(isTyping({ key: 'a' }), true)
  assert.equal(isTyping({ key: 'Enter' }), true)
  assert.equal(isTyping({ key: 'Alt' }), false)
  assert.equal(isTyping({ key: 'e', altKey: true }), false)
  assert.equal(isTyping({ key: 'k', ctrlKey: true }), false)
  assert.equal(isTyping({ key: 's', metaKey: true }), false)
  assert.equal(isTyping({ key: 'Escape' }), false)
})
