// Main's grab zones with another notch app present (coexist), and the open-zone mute.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { COEXIST_HOVER, EAR_W, GRAB, createOtherOpenMute, inOtherOpenZone, withinGrab } from '../src/renderer/src/core/notchGeometry'

// Display at x 0, top 0. Notch 189x32 at x 769.5 (16-inch MacBook Pro).
const notch = { x: 769.5, width: 189, height: 32 }
const d = { notch: true, displayTop: 0, margin: 12 }
const rest = { x: notch.x, y: 0, w: notch.width, h: notch.height }
const ears = { x: notch.x - EAR_W, y: 0, w: notch.width + 2 * EAR_W, h: notch.height }
const co = { coexist: true, notch }

test('coexist: the notch core is not grabbed, with the island at rest or with ears', () => {
  for (const r of [rest, ears]) {
    assert.equal(withinGrab({ x: 860, y: 10 }, r, d, co), false)
    assert.equal(withinGrab({ x: notch.x, y: 0 }, r, d, co), false)
    assert.equal(withinGrab({ x: notch.x + notch.width, y: 31 }, r, d, co), false)
  }
})

test('coexist: the ears are grabbed', () => {
  assert.equal(withinGrab({ x: notch.x - 10, y: 10 }, ears, d, co), true)
  assert.equal(withinGrab({ x: notch.x - EAR_W, y: 10 }, ears, d, co), true)
  assert.equal(withinGrab({ x: notch.x + notch.width + 10, y: 10 }, ears, d, co), true)
  assert.equal(withinGrab({ x: notch.x - EAR_W - GRAB.side - 1, y: 10 }, ears, d, co), false)
})

test('coexist: the 12 pt strip under the notch is grabbed, and no more', () => {
  assert.equal(withinGrab({ x: 860, y: 32 }, rest, d, co), true)
  assert.equal(withinGrab({ x: 860, y: 32 + GRAB.below }, rest, d, co), true)
  assert.equal(withinGrab({ x: 860, y: 32 + GRAB.below + 1 }, rest, d, co), false)
})

test('coexist: never above the display top', () => {
  assert.equal(withinGrab({ x: notch.x - 10, y: -5 }, ears, d, co), false)
})

test('coexist false (or no opts): unchanged, +-6 sides, 12 below, never above', () => {
  for (const o of [undefined, { coexist: false, notch }]) {
    assert.equal(withinGrab({ x: 860, y: 10 }, rest, d, o), true)
    assert.equal(withinGrab({ x: notch.x - GRAB.side, y: 10 }, rest, d, o), true)
    assert.equal(withinGrab({ x: notch.x - GRAB.side - 1, y: 10 }, rest, d, o), false)
    assert.equal(withinGrab({ x: notch.x + notch.width + GRAB.side, y: 10 }, rest, d, o), true)
    assert.equal(withinGrab({ x: notch.x + notch.width + GRAB.side + 1, y: 10 }, rest, d, o), false)
    assert.equal(withinGrab({ x: 860, y: 31 + GRAB.below }, rest, d, o), true)
    assert.equal(withinGrab({ x: 860, y: 32 + GRAB.below + 1 }, rest, d, o), false)
    assert.equal(withinGrab({ x: 860, y: -5 }, rest, d, o), false)
  }
})

test('coexist does not change a card below the menu bar', () => {
  const card = { x: 100, y: 200, w: 200, h: 100 }
  assert.equal(withinGrab({ x: 88, y: 250 }, card, d, co), true)
  assert.equal(withinGrab({ x: 87, y: 250 }, card, d, co), false)
})

test('hover timings while sharing the notch', () => {
  assert.deepEqual({ ...COEXIST_HOVER }, { openMs: 300, closeMs: 100 })
})

test('inOtherOpenZone: notch centre +-320, y 0..190', () => {
  const cx = notch.x + notch.width / 2
  assert.equal(inOtherOpenZone({ x: cx, y: 0 }, notch), true)
  assert.equal(inOtherOpenZone({ x: cx - 320, y: 190 }, notch), true)
  assert.equal(inOtherOpenZone({ x: cx + 320, y: 100 }, notch), true)
  assert.equal(inOtherOpenZone({ x: cx + 321, y: 100 }, notch), false)
  assert.equal(inOtherOpenZone({ x: cx - 321, y: 100 }, notch), false)
  assert.equal(inOtherOpenZone({ x: cx, y: 191 }, notch), false)
  assert.equal(inOtherOpenZone({ x: cx, y: -1 }, notch), false)
})

test('open mute: starts after 250 ms in the core, ends 150 ms after leaving the open zone', () => {
  const m = createOtherOpenMute()
  const core = { x: 860, y: 10 }
  const cx = notch.x + notch.width / 2
  assert.equal(m.step(1000, core, notch), false)
  assert.equal(m.step(1249, core, notch), false)
  assert.equal(m.step(1250, core, notch), true)
  // still inside the open zone (below the core): stays muted
  assert.equal(m.step(1300, { x: cx, y: 150 }, notch), true)
  assert.equal(m.step(3000, { x: cx, y: 150 }, notch), true)
  // leaves the zone
  assert.equal(m.step(3100, { x: cx, y: 400 }, notch), true)
  assert.equal(m.step(3249, { x: cx, y: 400 }, notch), true)
  assert.equal(m.step(3250, { x: cx, y: 400 }, notch), false)
})

test('open mute: a pass through the core shorter than 250 ms never mutes; re-entering the zone resets the 150 ms', () => {
  const m = createOtherOpenMute()
  assert.equal(m.step(1000, { x: 860, y: 10 }, notch), false)
  assert.equal(m.step(1100, { x: 860, y: 60 }, notch), false) // out of the core
  assert.equal(m.step(1300, { x: 860, y: 10 }, notch), false) // dwell restarts
  assert.equal(m.step(1550, { x: 860, y: 10 }, notch), true)
  assert.equal(m.step(1600, { x: 100, y: 500 }, notch), true)
  assert.equal(m.step(1700, { x: 860, y: 100 }, notch), true) // back in the zone: timer reset
  assert.equal(m.step(1800, { x: 100, y: 500 }, notch), true)
  assert.equal(m.step(1950, { x: 100, y: 500 }, notch), false)
})
