/** core/islandRest.ts, offline: what the island is at rest (the persistent ear), a shared notch, the seam, the shadow. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import type { NotchLayout } from '../src/common/notch'
import { coexistOf, coreCut, coreMask, HOVER_SCALE, islandPlan, NOTCH_SHADOW, NOTCH_SPRING, restViewFor, seamRect, shadowFor, stickyNotch } from '../src/renderer/src/core/islandRest'
import { EAR_W, earsSize, restSize } from '../src/renderer/src/core/notchGeometry'

const nm = { width: 189, height: 32 }
const real: NotchLayout = { hasNotch: true, x: 769.5, width: 189, height: 32, place: 'notch' }

describe('rest view', () => {
  test('a connected engine keeps the persistent ear; a loaded lesson too', () => {
    assert.equal(restViewFor({ connected: true, lessonLoaded: false }), 'ears')
    assert.equal(restViewFor({ connected: false, lessonLoaded: true }), 'ears')
  })
  test('cold and empty is just the notch; landing shows the ears; words drop a line', () => {
    assert.equal(restViewFor({ connected: false, lessonLoaded: false }), 'rest')
    assert.equal(restViewFor({ connected: false, lessonLoaded: false, landing: true }), 'ears')
    assert.equal(restViewFor({ connected: true, lessonLoaded: true, wantsDrop: true }), 'drop')
  })
  test('the ear is narrow: the notch plus an ear each side', () => {
    assert.equal(EAR_W, 36)
    assert.deepEqual(earsSize(real), { w: 189 + 72, h: 32 })
    assert.deepEqual(restSize(real), { w: 189, h: 32 })
  })
})

const plan = (over: Partial<Parameters<typeof islandPlan>[0]> = {}) => islandPlan({ nm, coexist: false, view: 'ears', open: false, hovering: false, w: 189 + 72, h: 32, ...over })

describe('plan at rest', () => {
  test('resting with the engine connected draws both ears, outside the core', () => {
    const p = plan()
    assert.ok(p.ears)
    assert.deepEqual(p.ears.left, { x: 0, y: 0, w: 36, h: 32 })
    assert.deepEqual(p.ears.right, { x: 36 + 189, y: 0, w: 36, h: 32 })
    assert.equal(p.ears.left.x + p.ears.left.w <= 36, true)
    assert.equal(p.ears.right.x >= 36 + 189, true)
  })
  test('no ears when it is bare notch', () => {
    assert.equal(plan({ view: 'rest', w: 189 }).ears, undefined)
  })
  test('shared notch: the core band is cut, and no ear touches it', () => {
    const p = plan({ coexist: true })
    assert.deepEqual(p.cut, { x0: 36, x1: 36 + 189, y1: 32 })
    assert.ok(p.ears)
    assert.ok(p.ears.left.x + p.ears.left.w <= p.cut.x0)
    assert.ok(p.ears.right.x >= p.cut.x1)
    // At bare rest the whole shape is the core: everything is cut.
    const bare = plan({ coexist: true, view: 'rest', w: 189 })
    assert.deepEqual(bare.cut, { x0: 0, x1: 189, y1: 32 })
    assert.equal(plan({ coexist: false }).cut, undefined)
  })
  test('the core mask keeps everything below the core row and everything outside it', () => {
    const m = coreMask(coreCut(261, nm))
    assert.ok(m.includes('black 36px, transparent 36px, transparent 225px, black 225px'))
    assert.ok(m.includes('0 0 / 100% 32px no-repeat'))
    assert.ok(m.includes('0 32px / 100% 100% no-repeat'))
  })
  test('the seam is inside the window, inset by the top radius', () => {
    const p = plan()
    assert.ok(p.seam.top >= 0)
    assert.equal(p.seam.left, p.radii.top)
    assert.equal(p.seam.width, 261 - 2 * p.radii.top)
    assert.equal(seamRect(100, 6).top, 0)
    assert.equal(seamRect(4, 6).width, 0)
  })
  test('no shadow at rest; shadow while open or hovering', () => {
    assert.equal(plan().shadow, 'none')
    assert.equal(shadowFor(false, false), 'none')
    assert.equal(plan({ hovering: true }).shadow, NOTCH_SHADOW)
    assert.equal(plan({ open: true, view: 'drop' }).shadow, NOTCH_SHADOW)
    assert.ok(NOTCH_SHADOW.includes('0 0 6px') && NOTCH_SHADOW.includes('0.7'))
  })
  test('open radii for the peek, closed otherwise', () => {
    assert.equal(plan().radii.top, 6)
    assert.equal(plan({ open: true, view: 'drop' }).radii.top, 19)
  })
})

describe('springs', () => {
  test('open ~224/24, close critically damped, hover lean', () => {
    assert.equal(NOTCH_SPRING.open.stiffness, 224)
    assert.equal(NOTCH_SPRING.open.damping, 24)
    assert.ok(Math.abs(NOTCH_SPRING.close.damping - 2 * Math.sqrt(NOTCH_SPRING.close.stiffness)) < 0.5)
    assert.equal(NOTCH_SPRING.hover.duration, 0.38)
    assert.ok(HOVER_SCALE > 1 && HOVER_SCALE < 1.1)
  })
})

describe('layout flags', () => {
  test('coexist is read as a flag only', () => {
    assert.equal(coexistOf({ ...real, coexist: true }), true)
    assert.equal(coexistOf(real), false)
    assert.equal(coexistOf(undefined), false)
  })
  test('a notched display never loses its notch for a moment (full screen)', () => {
    assert.equal(stickyNotch({ notch: real }, undefined), real)
    const broken = { ...real, height: 0 }
    assert.equal(stickyNotch({ notch: broken }, real), real)
    assert.equal(stickyNotch({ notch: broken }, undefined), undefined)
    // below, or a display with no notch: never a fake one.
    assert.equal(stickyNotch({ notch: { ...real, place: 'below' } }, real), undefined)
    assert.equal(stickyNotch({ notch: { ...broken, hasNotch: false } }, real), undefined)
  })
})
