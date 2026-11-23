/**
 * Buddy draws: geometry and mark rules (geometry.ts, marks.ts). Offline, no window:
 * `npx tsx --test src/renderer/src/features/annotate/geometry.test.ts`
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { BRANCH_REACH, branchControls, buddyPath, drawSeconds, hashSeed, islandAnchor, isDrawable, labelSpot, labelWidth, loopPoints, onOverlay, ringAngleToward, ringFor, rng, toOverlay } from './geometry'
import { cleanLabel, createReach, DEFAULT_HOLD_MS, fadeAt, holdFor, keyOf, knownKey, MAX_HOLD_MS, MAX_MARKS, mergeMarks, MIN_HOLD_MS, REACH_MS, sameMarkKeys, validMarks, type DrawMark, type Known } from './marks'

const box = { x: 100, y: 563, w: 380, h: 18 }

describe('seeds', () => {
  it('hashSeed is stable and differs by input', () => {
    assert.equal(hashSeed('id:a'), hashSeed('id:a'))
    assert.notEqual(hashSeed('id:a'), hashSeed('id:b'))
  })
  it('rng is deterministic per seed and stays in [0, 1)', () => {
    const a = rng(7)
    const b = rng(7)
    for (let i = 0; i < 50; i++) {
      const v = a()
      assert.equal(v, b())
      assert.ok(v >= 0 && v < 1)
    }
  })
})

describe('multi-display offset', () => {
  it('maps global screen points into the overlay window', () => {
    assert.deepEqual(toOverlay(box, { x: 0, y: 0 }), box)
    // An overlay on a display left of the primary: its origin is negative.
    assert.deepEqual(toOverlay({ x: -1200, y: 40, w: 100, h: 20 }, { x: -1440, y: 0 }), { x: 240, y: 40, w: 100, h: 20 })
    // A display above the primary.
    assert.deepEqual(toOverlay({ x: 10, y: -500, w: 10, h: 10 }, { x: 0, y: -900 }), { x: 10, y: 400, w: 10, h: 10 })
  })
  it('draws only what is mostly on this display', () => {
    const size = { width: 1440, height: 900 }
    assert.ok(onOverlay({ x: 10, y: 10, w: 100, h: 20 }, size))
    assert.ok(!onOverlay({ x: 1500, y: 10, w: 100, h: 20 }, size)) // on the display to the right
    assert.ok(!onOverlay({ x: 1400, y: 10, w: 100, h: 20 }, size)) // only 40% here
    assert.ok(onOverlay({ x: 1380, y: 10, w: 100, h: 20 }, size)) // 60% here
  })
  it('rejects boxes that cannot be drawn', () => {
    assert.ok(isDrawable(box))
    assert.ok(!isDrawable({ x: 0, y: 0, w: 0, h: 10 }))
    assert.ok(!isDrawable({ x: NaN, y: 0, w: 10, h: 10 }))
    assert.ok(!isDrawable(undefined))
  })
})

describe('island anchor', () => {
  it('starts at the island bottom middle, tucked under its edge', () => {
    assert.deepEqual(islandAnchor({ x: 700, y: 0, w: 200, h: 32 }, { centerX: 0, restBottom: 0 }), { x: 800, y: 30 })
  })
  it('falls back to the notch when the island has no size yet', () => {
    assert.deepEqual(islandAnchor({ x: 0, y: 0, w: 0, h: 0 }, { centerX: 720, restBottom: 32 }), { x: 720, y: 30 })
    assert.deepEqual(islandAnchor(undefined, { centerX: 720, restBottom: 32 }), { x: 720, y: 30 })
  })
})

describe('the ring', () => {
  const inside = (r: ReturnType<typeof ringFor>, x: number, y: number): boolean => ((x - r.cx) / r.rx) ** 2 + ((y - r.cy) / r.ry) ** 2 <= 1 + 1e-9
  for (const b of [box, { x: 10, y: 10, w: 40, h: 40 }, { x: 0, y: 0, w: 8, h: 8 }, { x: 0, y: 0, w: 1400, h: 16 }, { x: 0, y: 0, w: 30, h: 300 }]) {
    it(`contains every corner of ${b.w}x${b.h} (up to the height cap)`, () => {
      const r = ringFor(b)
      assert.equal(r.cx, b.x + b.w / 2)
      assert.equal(r.cy, b.y + b.h / 2)
      assert.ok(r.rx >= b.w / 2 && r.ry >= b.h / 2)
      // The cap keeps a page-wide line from growing a huge loop; everything else holds its corners.
      if (b.w < 1000) for (const [x, y] of [[b.x, b.y], [b.x + b.w, b.y], [b.x, b.y + b.h], [b.x + b.w, b.y + b.h]]) assert.ok(inside(r, x, y), `corner ${x},${y}`)
      assert.ok(r.ry <= Math.max(b.h / 2, 18) * 3.2 + 1e-9 || r.ry === Math.max(18, b.h / 2 + 8))
    })
  }
  it('gives a tiny icon a loop a finger could point at', () => {
    const r = ringFor({ x: 0, y: 0, w: 4, h: 4 })
    assert.ok(r.rx >= 18 && r.ry >= 18)
  })
})

describe('the loop', () => {
  const ring = ringFor(box)
  it('is the same line for the same seed, and another for another seed', () => {
    assert.deepEqual(loopPoints(ring, 0.3, 42), loopPoints(ring, 0.3, 42))
    assert.notDeepEqual(loopPoints(ring, 0.3, 42), loopPoints(ring, 0.3, 43))
  })
  it('wobbles only a little around the ring and ends a bit outside where it began', () => {
    const pts = loopPoints(ring, -Math.PI / 2, 9)
    for (const p of pts) {
      const k = Math.hypot((p.x - ring.cx) / ring.rx, (p.y - ring.cy) / ring.ry)
      assert.ok(k > 0.9 && k < 1.16, `radius share ${k}`)
    }
    const k0 = Math.hypot((pts[0].x - ring.cx) / ring.rx, (pts[0].y - ring.cy) / ring.ry)
    const kN = Math.hypot((pts.at(-1)!.x - ring.cx) / ring.rx, (pts.at(-1)!.y - ring.cy) / ring.ry)
    assert.ok(kN > k0, 'the end sits outside the start, so the ends cross like a hand-drawn loop')
  })
})

describe('the buddy path', () => {
  const from = { x: 800, y: 30 }
  it('starts at the island and meets the loop on the side facing it', () => {
    const p = buddyPath(from, box, 1)
    assert.match(p.d, /^M800 30 C/)
    assert.ok(p.d.startsWith('M800 30'))
    assert.ok(p.loop.startsWith(`M${Math.round(p.join.x * 10) / 10} ${Math.round(p.join.y * 10) / 10}`))
    // The join is on the half of the ring that faces the island (above and right of the box's center here).
    const t = ringAngleToward(p.ring, from)
    assert.ok(Math.sin(t) < 0, 'faces up, toward the island')
    assert.ok(p.join.y < p.ring.cy)
  })
  it('is deterministic (a re-sent mark draws the same line)', () => {
    assert.equal(buddyPath(from, box, 5).d, buddyPath(from, box, 5).d)
  })
  it('measures the stroke so the draw time scales, within bounds', () => {
    const p = buddyPath(from, box, 1)
    assert.ok(p.branchLength > 500 && p.loopLength > 900)
    assert.ok(drawSeconds(0) >= 0.55 && drawSeconds(1e6) <= 1.2)
    assert.ok(drawSeconds(p.branchLength + p.loopLength) > drawSeconds(200))
  })
  it('arrives along the loop without hooking back past the join', () => {
    // A far target: the last control point reaches back from the join at most BRANCH_REACH, so the curve does not swing
    // past the join and hook back into the loop (a J over the text above it).
    const join = { x: 300, y: 560 }
    const heading = { x: 1, y: 0 }
    const [, c2] = branchControls({ x: 900, y: 30 }, join, heading, 1)
    assert.ok(Math.hypot(c2.x - join.x, c2.y - join.y) <= BRANCH_REACH + 1e-9)
  })
  it('has no NaN even when the target sits right under the island', () => {
    const p = buddyPath({ x: 50, y: 30 }, { x: 30, y: 20, w: 40, h: 20 }, 3)
    assert.ok(!p.d.includes('NaN'))
  })
})

describe('the label', () => {
  const size = { width: 1440, height: 900 }
  const w = labelWidth('Start here')
  it('sits beside the loop on the circled line, not over the lines under it', () => {
    const r = ringFor(box)
    const s = labelSpot(r, size, w)
    assert.equal(s.align, 'start')
    assert.ok(s.x > r.cx + r.rx)
    assert.ok(s.y < r.cy && s.y + 22 > r.cy, 'centered on the circled line')
  })
  it('goes left of the loop when the right side has no room', () => {
    const r = ringFor({ x: 1200, y: 300, w: 200, h: 18 })
    const s = labelSpot(r, size, w)
    assert.equal(s.align, 'end')
    assert.ok(s.x < r.cx - r.rx && s.x - w >= 12)
  })
  it('falls back under the loop, or over it near the bottom, when neither side fits', () => {
    const r = ringFor({ x: 20, y: 300, w: 1400, h: 18 })
    const s = labelSpot(r, size, w)
    assert.ok(s.align === 'center' && !s.above && s.y > r.cy + r.ry)
    const low = ringFor({ x: 20, y: 860, w: 1400, h: 20 })
    const t = labelSpot(low, size, w)
    assert.ok(t.above && t.y < low.cy - low.ry)
  })
  it('stays on screen', () => {
    const s = labelSpot(ringFor({ x: -40, y: 300, w: 30, h: 20 }), size, w)
    assert.ok(s.x >= 12)
    const wide = labelSpot(ringFor({ x: -10, y: 300, w: 1460, h: 20 }), size, w)
    assert.ok(wide.x - w / 2 >= 12 && wide.x + w / 2 <= size.width - 12)
  })
})

describe('marks', () => {
  const a = { x: 100, y: 563, w: 380, h: 18, why: 'point' as const }
  it('keeps only drawable marks with a known why, de-duplicated, at most a few', () => {
    const list = [a, { ...a }, { ...a, w: 0 }, { ...a, why: 'nope' }, null, { x: 1, y: 1, w: 9, h: 9, why: 'answer' }, { x: 40, y: 1, w: 9, h: 9, why: 'answer' }, { x: 80, y: 1, w: 9, h: 9, why: 'answer' }]
    const v = validMarks(list)
    assert.equal(v.length, MAX_MARKS)
    assert.deepEqual(validMarks('x'), [])
  })
  it('knows a mark again by id, or (no id) by nearly the same box', () => {
    assert.equal(keyOf({ ...a, id: 'm1' }), 'id:m1')
    assert.notEqual(keyOf(a), keyOf({ ...a, why: 'answer' }))
    const drawn = mergeMarks([], [a], [], 1000)
    // An OCR re-read a few points off is the same mark: same key, same birth, no redraw.
    const again = mergeMarks(drawn, [{ ...a, x: a.x + 3, y: a.y - 2 }], [], 2000)
    assert.equal(again[0].key, drawn[0].key)
    assert.equal(again[0].born, 1000)
    assert.equal(again[0].rect, drawn[0].rect, 'keeps the drawn box (no twitch)')
    assert.equal(knownKey({ ...a, why: 'answer' }, drawn), undefined)
    assert.equal(knownKey({ ...a, x: a.x + 40 }, drawn), undefined)
    // Gone (reached or timed out) stays gone for a jittered re-send too.
    assert.deepEqual(mergeMarks([], [{ ...a, x: a.x + 5 }], drawn, 3000), [])
  })
  it('replaces the drawn set, keeps the birth of a known mark, and skips gone ones', () => {
    const first = mergeMarks([], [{ ...a, id: 'm1' }, { ...a, id: 'm2', x: 600 }], [], 1000)
    assert.deepEqual(first.map((m) => m.born), [1000, 1000])
    const again = mergeMarks(first, [{ ...a, id: 'm1' }, { ...a, id: 'm3', x: 900 }], [], 2000)
    assert.deepEqual(again.map((m) => [m.key, m.born]), [['id:m1', 1000], ['id:m3', 2000]])
    const gone = mergeMarks(again, [{ ...a, id: 'm1' }], [again[0]], 3000)
    assert.deepEqual(gone, [])
  })
  it('a re-sent mark does not restart the hold: re-sent at 2 s and 4 s, it is still gone by 6 s', () => {
    // The store's timeline (store.ts show): merge, then fade at fadeAt(drawn, hold). A fake clock, no timers.
    const m = { ...a, id: 'm1' }
    let drawn: DrawMark[] = []
    let deadline: number | undefined
    const send = (now: number, list = [m]): void => {
      drawn = mergeMarks(drawn, list, [], now)
      deadline = fadeAt(drawn, DEFAULT_HOLD_MS)
    }
    send(0)
    send(2000)
    assert.equal(deadline, 6000)
    send(4000)
    assert.equal(deadline, 6000)
    assert.ok(deadline! <= 6000, 'faded by 6 s')
    // A new mark is a new thing to look at: the hold counts from its birth.
    send(5000, [m, { ...a, id: 'm2', x: 700 }])
    assert.equal(deadline, 11_000)
    assert.equal(fadeAt([], DEFAULT_HOLD_MS), undefined)
  })
  it('an explicit ask (Show me) draws a reached box again', () => {
    const reached: Known[] = mergeMarks([], [a], [], 1000)
    assert.deepEqual(mergeMarks([], [a], reached, 2000), [], 'reached: skipped')
    // Show me on the same box (a few points off): it is the same mark, so forget it as gone and draw it new.
    const again = { ...a, x: a.x + 4 }
    const keys = sameMarkKeys(again, reached)
    assert.deepEqual(keys, [reached[0].key])
    const left = reached.filter((k) => !keys.includes(k.key))
    const drawn = mergeMarks([], [again], left, 3000)
    assert.equal(drawn.length, 1)
    assert.equal(drawn[0].born, 3000)
    assert.deepEqual(sameMarkKeys({ ...a, x: a.x + 60 }, reached), [], 'another box is not this one')
  })
  it('trims a label to 4 words', () => {
    assert.equal(cleanLabel('  the   optimizer line here now '), 'the optimizer line here')
    assert.equal(cleanLabel(''), undefined)
    assert.equal(cleanLabel(3), undefined)
  })
  it('holds for holdMs within bounds, else 6 s', () => {
    assert.equal(holdFor(undefined), DEFAULT_HOLD_MS)
    assert.equal(DEFAULT_HOLD_MS, 6000)
    assert.equal(holdFor(-5), DEFAULT_HOLD_MS)
    assert.equal(holdFor(10), MIN_HOLD_MS)
    assert.equal(holdFor(1e9), MAX_HOLD_MS)
    assert.equal(holdFor(4000), 4000)
  })
})

describe('reach (the learner went there)', () => {
  const boxes = [{ key: 'k', rect: { x: 100, y: 100, w: 50, h: 20 } }]
  it('needs the pointer to come in from outside and rest a moment', () => {
    const r = createReach()
    // Already resting inside when drawn (the learner just circled it): never fades on its own.
    assert.deepEqual(r.move({ x: 120, y: 110 }, boxes, 0), [])
    assert.deepEqual(r.move({ x: 121, y: 110 }, boxes, 5000), [])
    // Out, then in, then rest.
    assert.deepEqual(r.move({ x: 400, y: 400 }, boxes, 5100), [])
    assert.deepEqual(r.move({ x: 120, y: 110 }, boxes, 5200), [])
    assert.deepEqual(r.move({ x: 122, y: 111 }, boxes, 5200 + REACH_MS - 1), [])
    assert.deepEqual(r.move({ x: 123, y: 111 }, boxes, 5200 + REACH_MS), ['k'])
  })
  it('a pass straight through does not count', () => {
    const r = createReach()
    r.move({ x: 0, y: 0 }, boxes, 0)
    r.move({ x: 120, y: 110 }, boxes, 10)
    r.move({ x: 400, y: 110 }, boxes, 100)
    assert.deepEqual(r.move({ x: 120, y: 110 }, boxes, 1000), [])
  })
  it('a click inside counts at once', () => {
    const r = createReach()
    assert.deepEqual(r.press({ x: 104, y: 98 }, boxes), ['k']) // within the pad
    assert.deepEqual(r.press({ x: 10, y: 10 }, boxes), [])
  })
})
