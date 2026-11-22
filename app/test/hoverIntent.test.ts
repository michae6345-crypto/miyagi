/** core/hoverIntent.ts, offline: the hover state machine (open delay, close grace, the shared-notch mute, the wheel stretch). */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import {
  cfgFor,
  HOVER_IDLE,
  hoverDeadline,
  hoverEnter,
  hoverLeave,
  hoverPoint,
  hoverTick,
  inCore,
  inHoverZone,
  MUTE_ENTER_MS,
  MUTE_EXIT_MS,
  peekOpen,
  STRETCH_IDLE,
  stretchScale,
  stretchWheel,
  type HoverState
} from '../src/renderer/src/core/hoverIntent'
import { COEXIST_HOVER, HOVER, inOtherOpenZone } from '../src/renderer/src/core/notchGeometry'

const normal = cfgFor(false)
const shared = cfgFor(true)
const notch = { x: 769.5, width: 189, height: 32 }

/** Advance to the next deadline, as the island's single timer does. */
function run(s: HoverState, cfg: typeof normal, until: number): HoverState {
  let t = s
  for (;;) {
    const at = hoverDeadline(t, cfg)
    if (at === undefined || at > until) return t
    t = hoverTick(t, at, cfg)
  }
}

describe('open timer', () => {
  test('light response at once; the peek opens at 150 ms normally', () => {
    const s = hoverEnter(HOVER_IDLE, 1000, normal)
    assert.equal(s.light, true)
    assert.equal(peekOpen(s), false)
    assert.equal(hoverDeadline(s, normal), 1000 + HOVER.openMs)
    assert.equal(HOVER.openMs, 150)
    assert.equal(HOVER.closeMs, 100)
    assert.equal(peekOpen(hoverTick(s, 1149, normal)), false)
    assert.equal(peekOpen(hoverTick(s, 1150, normal)), true)
  })
  test('with a shared notch it opens at 300 ms', () => {
    assert.equal(COEXIST_HOVER.openMs, 300)
    const s = hoverEnter(HOVER_IDLE, 0, shared)
    assert.equal(s.light, true)
    assert.equal(peekOpen(hoverTick(s, 299, shared)), false)
    assert.equal(peekOpen(hoverTick(s, 300, shared)), true)
  })
  test('leaving before it fires cancels the open', () => {
    const s = hoverLeave(hoverEnter(HOVER_IDLE, 0, normal), 100, normal)
    assert.equal(s.light, false)
    assert.equal(s.openAt, undefined)
    assert.equal(hoverDeadline(s, normal), undefined)
    assert.equal(peekOpen(run(s, normal, 10_000)), false)
  })
  test('the open re-checks at fire time: a stale timer does not open an island the pointer left', () => {
    const entered = hoverEnter(HOVER_IDLE, 0, normal)
    const left = { ...entered, inside: false }
    assert.equal(peekOpen(hoverTick(left, 200, normal)), false)
  })
})

describe('close grace', () => {
  const open = (cfg: typeof normal): HoverState => run(hoverEnter(HOVER_IDLE, 0, cfg), cfg, 1000)
  test('the peek closes after the grace', () => {
    const o = open(shared)
    const s = hoverLeave(o, 2000, shared)
    assert.equal(hoverDeadline(s, shared), 2000 + COEXIST_HOVER.closeMs)
    assert.equal(peekOpen(hoverTick(s, 2099, shared)), true)
    assert.equal(peekOpen(hoverTick(s, 2100, shared)), false)
  })
  test('re-entering within 100 ms cancels the close', () => {
    const o = open(shared)
    const left = hoverLeave(o, 2000, shared)
    const back = hoverEnter(left, 2099, shared)
    assert.equal(back.closeAt, undefined)
    assert.equal(peekOpen(run(back, shared, 10_000)), true)
  })
})

describe('shared notch: mute', () => {
  const inside = { x: notch.x + 90, y: 10 }
  const far = { x: notch.x + 600, y: 400 }
  test('geometry: core and the other app\'s open zone', () => {
    assert.equal(inCore(inside, notch), true)
    assert.equal(inCore({ x: notch.x - 1, y: 10 }, notch), false)
    assert.equal(inCore({ x: notch.x + 90, y: 32 }, notch), false)
    assert.equal(inOtherOpenZone({ x: 864 + 320, y: 190 }, notch), true)
    assert.equal(inOtherOpenZone({ x: 864 + 321, y: 100 }, notch), false)
    assert.equal(inOtherOpenZone({ x: 864, y: 191 }, notch), false)
  })
  test('mutes after 250 ms in the core and hides the peek', () => {
    let s = hoverEnter(HOVER_IDLE, 0, shared)
    s = hoverPoint(s, 0, shared, inside, notch)
    assert.equal(hoverDeadline(s, shared), 250)
    assert.equal(hoverTick(s, 249, shared).muted, false)
    const m = hoverTick(s, MUTE_ENTER_MS, shared)
    assert.equal(m.muted, true)
    assert.equal(peekOpen(m), false)
    assert.equal(m.light, false)
  })
  test('an open peek is hidden by the mute too', () => {
    let s = run(hoverEnter(HOVER_IDLE, 0, shared), shared, 400)
    assert.equal(peekOpen(s), true)
    s = hoverPoint(s, 500, shared, inside, notch)
    s = hoverTick(s, 750, shared)
    assert.equal(s.muted, true)
    assert.equal(peekOpen(s), false)
  })
  test('passing through the core quickly does not mute', () => {
    let s = hoverPoint(HOVER_IDLE, 0, shared, inside, notch)
    s = hoverPoint(s, 100, shared, { x: notch.x - 10, y: 10 }, notch)
    assert.equal(s.coreSince, undefined)
    assert.equal(hoverTick(s, 1000, shared).muted, false)
  })
  test('ends 150 ms after the pointer leaves the open zone', () => {
    let s = hoverPoint(HOVER_IDLE, 0, shared, inside, notch)
    s = hoverTick(s, 250, shared)
    assert.equal(s.muted, true)
    // Moving to an ear is still inside the other app's open zone: stay muted.
    s = hoverPoint(s, 300, shared, { x: notch.x - 20, y: 10 }, notch)
    assert.equal(s.farSince, undefined)
    assert.equal(hoverTick(s, 5000, shared).muted, true)
    s = hoverPoint(s, 6000, shared, far, notch)
    assert.equal(hoverDeadline(s, shared), 6000 + MUTE_EXIT_MS)
    assert.equal(hoverTick(s, 6149, shared).muted, true)
    assert.equal(hoverTick(s, 6150, shared).muted, false)
  })
  test('while muted, entering does not light or open; the peek springs back after the mute if still inside', () => {
    let s = hoverTick(hoverPoint(HOVER_IDLE, 0, shared, inside, notch), 250, shared)
    s = hoverEnter(s, 300, shared)
    assert.equal(s.light, false)
    assert.equal(s.openAt, undefined)
    s = hoverPoint(s, 400, shared, far, notch)
    s = hoverTick(s, 550, shared)
    assert.equal(s.muted, false)
    assert.equal(s.light, true)
    assert.equal(peekOpen(run(s, shared, 5000)), true)
  })
  test('no mute without a shared notch', () => {
    const s = hoverPoint(HOVER_IDLE, 0, normal, inside, notch)
    assert.equal(s.coreSince, undefined)
    assert.equal(hoverDeadline(s, normal), undefined)
  })
})

describe('shared notch: hover zones', () => {
  test('the ears and the strip under the notch trigger; the core does not', () => {
    assert.equal(inHoverZone({ x: notch.x - 10, y: 10 }, notch), true)
    assert.equal(inHoverZone({ x: notch.x + notch.width + 10, y: 10 }, notch), true)
    assert.equal(inHoverZone({ x: notch.x + 90, y: 40 }, notch), true)
    assert.equal(inHoverZone({ x: notch.x + 90, y: 10 }, notch), false)
    assert.equal(inHoverZone({ x: notch.x + 90, y: 60 }, notch), false)
    assert.equal(inHoverZone({ x: notch.x - 80, y: 10 }, notch), false)
  })
  test('an open island holds the pointer over its whole box', () => {
    const box = { x: 700, y: 0, w: 300, h: 100 }
    assert.equal(inHoverZone({ x: 720, y: 70 }, notch, box), true)
    assert.equal(inHoverZone({ x: 720, y: 70 }, notch), false)
  })
})

describe('wheel stretch', () => {
  test('scale = max(0.6, 1 + progress * 0.01); commits past 200', () => {
    let s = STRETCH_IDLE
    assert.equal(stretchScale(s), 1)
    let r = stretchWheel(s, 50)
    s = r.state
    assert.equal(stretchScale(s), 1.5)
    assert.equal(stretchScale({ progress: 200, committed: true }), 3)
    assert.equal(stretchScale({ progress: 20, committed: false }), 1.2)
    assert.equal(r.commit, false)
    r = stretchWheel(s, 160)
    assert.equal(r.commit, true)
    assert.equal(stretchWheel(r.state, 10).commit, false)
    assert.equal(stretchScale({ progress: -500, committed: false }), 0.6)
  })
})
