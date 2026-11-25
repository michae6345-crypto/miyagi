/** core/notchGeometry.ts, offline: islandBottom / islandTop, the notch path, the sizes, the hit-zone clamp, the watchdog in the notch. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import type { NotchLayout } from '../src/common/notch'
import {
  EAR_W,
  GRAB,
  gradientOn,
  islandBottomAt,
  islandTopAt,
  isOpenView,
  notchClip,
  notchOf,
  notchPath,
  notchSize,
  PEEK,
  NOTCH_RADII,
  radiiFor,
  SHORT_OPEN_H,
  viewWith,
  withinGrab
} from '../src/renderer/src/core/notchGeometry'
import { hud } from '../src/renderer/src/core/theme'
import { NO_ACTION, OWNERLESS_GRACE_MS, WATCH_REST, watchdogStep } from '../src/renderer/src/core/islandState'

const real: NotchLayout = { hasNotch: true, x: 267.5, width: 189, height: 32, place: 'notch' }
const below: NotchLayout = { ...real, place: 'below' }

describe('islandTop / islandBottom', () => {
  test('in the notch: the display top and the notch bottom', () => {
    assert.equal(islandTopAt({ notch: real }, 40), 0)
    assert.equal(islandBottomAt({ notch: real }, 40), 32)
  })
  test('below the menu bar: exactly the old pill (pillTop, pillTop + 34)', () => {
    assert.equal(islandTopAt({ notch: below }, 40), 40)
    assert.equal(islandBottomAt({ notch: below }, 40), 74)
    assert.equal(islandBottomAt({ notch: below }, 8), 42)
  })
  test('no notch layout, or a broken one, behaves as below', () => {
    assert.equal(islandBottomAt({}, 40), 74)
    assert.equal(notchOf({ notch: { ...real, width: 0 } }), undefined)
    assert.equal(notchOf({ notch: { ...real, x: NaN } }), undefined)
    assert.equal(notchOf(undefined), undefined)
  })
})

describe('notchPath', () => {
  test('closed notch, no strip: concave ears at the top, convex corners at the bottom', () => {
    assert.equal(notchPath(200, 32, 6, 14), 'M0 0 L200 0 L200 0 Q194 0 194 6 L194 18 Q194 32 180 32 L20 32 Q6 32 6 18 L6 6 Q6 0 0 0 Z')
  })
  test('the seam strip shifts the shape down and the path stays closed', () => {
    const d = notchPath(200, 32, 6, 14, 1)
    assert.ok(d.startsWith('M0 0 L200 0 L200 1 Q194 1 194 7'))
    assert.ok(d.endsWith('Q6 1 0 1 Z'))
  })
  test('open radii: top 19, bottom 24', () => {
    const d = notchPath(300, 120, 19, 24)
    assert.ok(d.includes('Q281 0 281 19'))
    assert.ok(d.includes('Q281 120 257 120'))
  })
  test('radii are clamped to what fits (a notch smaller than its radii never draws loops)', () => {
    const d = notchPath(20, 10, 19, 24)
    assert.ok(!/NaN|-/.test(d), d)
    const nums = d.match(/-?\d+(\.\d+)?/g)!.map(Number)
    assert.ok(nums.every((n) => n >= 0 && n <= 20))
  })
  test('clip wraps it in path()', () => {
    assert.ok(notchClip(200, 32, 6, 14).startsWith("path('M0 0"))
  })
})

describe('notchSize', () => {
  test('rest is the notch rect, ears widen by an ear each side at the same height', () => {
    assert.deepEqual(notchSize(real, 'pill', 'rest', undefined, undefined), { w: 189, h: 32 })
    assert.deepEqual(notchSize(real, 'pill', 'ears', undefined, { w: 999, h: 99 }), { w: 189 + 2 * EAR_W, h: 32 })
  })
  test('a drop is the notch row plus the content row, at least the peek wide', () => {
    assert.deepEqual(notchSize(real, 'pill', 'drop', undefined, { w: 190, h: 34 }), { w: PEEK.w, h: 66 + PEEK.pad })
    assert.deepEqual(notchSize(real, 'pill', 'drop', undefined, { w: 380, h: 34 }), { w: 380 + 38 + 2 * NOTCH_RADII.peek.taper, h: 66 + PEEK.pad })
    assert.deepEqual(notchSize(real, 'pill', 'drop', undefined, undefined), { w: PEEK.w, h: 32 + PEEK.drop })
  })
  test('a card keeps its width and grows down from the notch; an empty one is the notch', () => {
    assert.deepEqual(notchSize(real, 'card', 'drop', 340, { w: 340, h: 180 }), { w: 340 + 38 + 2 * NOTCH_RADII.open.taper, h: 212 })
    assert.deepEqual(notchSize(real, 'card', 'drop', 340, { w: 340, h: 0 }), { w: 189, h: 32 })
    assert.deepEqual(notchSize(real, 'card', 'drop', 340, undefined), { w: 189, h: 32 })
  })
})

describe('views', () => {
  test('hover opens a peek over rest and ears only', () => {
    assert.equal(viewWith('rest', true), 'drop')
    assert.equal(viewWith('ears', true), 'drop')
    assert.equal(viewWith('ears+drop', true), 'ears+drop')
    assert.equal(viewWith('rest', false), 'rest')
  })
  test('open radii for the peek, drops and cards; closed for rest and ears', () => {
    assert.equal(isOpenView('card', 'rest'), true)
    assert.equal(isOpenView('pill', 'drop'), true)
    assert.equal(isOpenView('pill', 'ears'), false)
    assert.equal(isOpenView('pill', 'rest'), false)
  })
})

describe('withinGrab (main hit zone)', () => {
  const d = { notch: true, displayTop: 0, margin: 12 }
  const island = { x: 267, y: -1, w: 189, h: 32 } // the shape's box includes the 1 px strip
  test('the notch rect and 6 pt either side', () => {
    assert.equal(withinGrab({ x: 300, y: 10 }, island, d), true)
    assert.equal(withinGrab({ x: 267 - GRAB.side, y: 10 }, island, d), true)
    assert.equal(withinGrab({ x: 267 - GRAB.side - 1, y: 10 }, island, d), false)
    assert.equal(withinGrab({ x: 267 + 189 + GRAB.side, y: 10 }, island, d), true)
    assert.equal(withinGrab({ x: 267 + 189 + GRAB.side + 1, y: 10 }, island, d), false)
  })
  test('12 pt below it, never above it or in the menu bar beside the notch', () => {
    assert.equal(withinGrab({ x: 300, y: 31 + GRAB.below }, island, d), true)
    assert.equal(withinGrab({ x: 300, y: 31 + GRAB.below + 1 }, island, d), false)
    // a menu item well left of the notch stays clickable
    assert.equal(withinGrab({ x: 200, y: 10 }, island, d), false)
    assert.equal(withinGrab({ x: 300, y: -5 }, island, d), false)
  })
  test('other rects keep the 12 pt margin all round, and below the menu bar nothing changes', () => {
    const card = { x: 100, y: 200, w: 50, h: 50 }
    assert.equal(withinGrab({ x: 88, y: 188 }, card, d), true)
    assert.equal(withinGrab({ x: 87, y: 188 }, card, d), false)
    const pill = { x: 300, y: 40, w: 200, h: 34 }
    const old = { notch: false, displayTop: 0, margin: 12 }
    assert.equal(withinGrab({ x: 288, y: 28 }, pill, old), true)
    assert.equal(withinGrab({ x: 300, y: 27 }, pill, old), false)
    assert.equal(withinGrab({ x: 300, y: 86 }, pill, old), true)
  })
  test('a rect at the top of a display that is not at 0 uses that display top', () => {
    const r = { x: 1000, y: 1080, w: 189, h: 32 }
    assert.equal(withinGrab({ x: 1100, y: 1075 }, r, { notch: true, displayTop: 1080, margin: 12 }), false)
    assert.equal(withinGrab({ x: 1100, y: 1085 }, r, { notch: true, displayTop: 1080, margin: 12 }), true)
  })
})

describe('watchdog in the notch', () => {
  const at = (size: { w: number; h: number }, extra: object) => ({ mode: { id: 'idle' }, size, hover: false, pointerIn: false, lastActivity: 0, now: 0, restH: 32, ...extra })
  test('rest and ears (32 tall) are never extended', () => {
    const r = watchdogStep(WATCH_REST, at({ w: 261, h: 32 }, {}))
    assert.equal(r.action, NO_ACTION)
  })
  test('a drop with no owner collapses back to the notch rect after the grace', () => {
    let s = WATCH_REST
    let r = watchdogStep(s, at({ w: 300, h: 66 }, { now: 1000 }))
    s = r.state
    assert.equal(r.action, NO_ACTION)
    r = watchdogStep(s, at({ w: 300, h: 66 }, { now: 1000 + OWNERLESS_GRACE_MS }))
    assert.equal(r.action.resetSize, true)
  })
  test('a pill-sized mode that asked for a drop (peek, its own line) is not ownerless', () => {
    const r = watchdogStep(WATCH_REST, at({ w: 300, h: 66 }, { dropOk: true, now: 5000 }))
    assert.equal(r.action, NO_ACTION)
    assert.equal(r.state.ownerlessSince, 0)
  })
})

test('a short open shape uses the gentler peek radii (no trapezoid), a tall one the open radii', () => {
  assert.deepEqual(radiiFor(true, 74), NOTCH_RADII.peek)
  assert.deepEqual(radiiFor(true, 194), NOTCH_RADII.open)
  assert.deepEqual(radiiFor(false, 74), NOTCH_RADII.closed)
  assert.deepEqual(radiiFor(true), NOTCH_RADII.open)
})

test('an open shape leans in: its bottom edge is narrower than its top by the taper each side; taper 0 is the old path', () => {
  assert.equal(notchPath(200, 32, 6, 14, 0, 0), notchPath(200, 32, 6, 14))
  const d = notchPath(600, 190, 19, 24, 0, 16)
  // bottom straight edge runs from x = 19 + 16 + 24 to 600 - 19 - 16 - 24
  assert.match(d, /L59 190 /)
  assert.ok(d.includes('Q565 190 541 190'))
})

test('the open shape keeps slanted sides (Michael, Nov 25): taper > 0, the side leans in from under the ear', () => {
  const { top, bottom, taper } = NOTCH_RADII.open
  assert.ok(taper > 0, 'open taper must never be 0 (no straight sides)')
  assert.ok(NOTCH_RADII.peek.taper > 0)
  assert.equal(NOTCH_RADII.closed.taper, 0)
  const d = notchPath(600, 190, top, bottom, 0, taper)
  // The side starts under the ear at x = 600 - top and leans in toward the bottom corner, whose control point sits
  // `taper` further in: a diagonal, not a vertical line.
  assert.ok(d.includes(`Q${600 - top} 0 ${600 - top} ${top}`))
  const side = d.match(new RegExp(`L([\\d.]+) ${190 - bottom} Q${600 - top - taper} 190 `))
  assert.ok(side, d)
  assert.ok(Number(side[1]) < 600 - top - taper / 2, 'the side leans in by at least half the taper above the corner')
  assert.ok(d.includes(`L${top + taper + bottom} 190 `))
})

describe('the pastel green gradient', () => {
  test('only the open, tall island paints it; closed and the short peek stay plain black', () => {
    assert.equal(gradientOn(true, 194), true)
    assert.equal(gradientOn(true, SHORT_OPEN_H), true)
    assert.equal(gradientOn(true, 74), false)
    assert.equal(gradientOn(false, 194), false)
    assert.equal(gradientOn(false, 32), false)
  })
  const stops = [...hud.notchGradient.matchAll(/rgba\((\d+),(\d+),(\d+),([\d.]+)\) (\d+)%/g)].map((m) => ({ rgb: [+m[1], +m[2], +m[3]], a: +m[4], at: +m[5] }))
  test('black at the top (melts into the hardware notch), a pastel mint at the bottom, never fading back', () => {
    assert.match(hud.notchGradient, /^linear-gradient\(180deg,/)
    assert.ok(stops.length >= 3)
    assert.equal(stops[0].at, 0)
    assert.equal(stops[stops.length - 1].at, 100)
    for (const s of stops.filter((x) => x.at <= 35)) assert.equal(s.a, 0)
    for (let i = 1; i < stops.length; i++) assert.ok(stops[i].a >= stops[i - 1].a && stops[i].at > stops[i - 1].at)
    const last = stops[stops.length - 1]
    assert.ok(last.a >= 0.2 && last.a <= 0.45)
    // pastel: every channel high, green the strongest
    assert.ok(Math.min(...last.rgb) >= 140 && last.rgb[1] === Math.max(...last.rgb))
  })
  test('white text and the muted white (60%) keep >= 4.5:1 on the brightest stop over the notch black', () => {
    const lin = (c: number): number => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }
    const lum = ([r, g, b]: number[]): number => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    const over = (fg: number[], a: number, bg: number[]): number[] => fg.map((c, i) => c * a + bg[i] * (1 - a))
    const ratio = (x: number[], y: number[]): number => { const [l1, l2] = [lum(x), lum(y)].sort((p, q) => q - p); return (l1 + 0.05) / (l2 + 0.05) }
    const last = stops[stops.length - 1]
    const bg = over(last.rgb, last.a, [0, 0, 0])
    assert.ok(ratio([255, 255, 255], bg) >= 4.5)
    assert.ok(ratio(over([255, 255, 255], 0.6, bg), bg) >= 4.5)
  })
})
