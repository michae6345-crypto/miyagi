/**
 * The buddy's pointing branch, offline: features/buddy/marks.ts (the mark rules, the stroke's shape, the label's
 * place, the timing) and features/buddy/pointing.ts (what is shown and for how long, through the real bus).
 * The mark rules are Michael's features/annotate rules, number for number; the tests pin those numbers.
 */
import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import { dispatch, emitUi } from '../src/renderer/src/core/bus'
import { duration } from '../src/renderer/src/core/ui/motionTokens'
import {
  cleanLabel,
  createReach,
  DRAW,
  drawTime,
  fadeAt,
  FORK,
  forkFor,
  HOLD,
  holdFor,
  KEY_GRID,
  keyOf,
  LABEL,
  labelAt,
  MAX_MARKS,
  mergeMarks,
  REACH,
  reach,
  ribbon,
  RING,
  ringBox,
  SAME_PX,
  timeToDraw,
  validMarks,
  type Mark
} from '../src/renderer/src/features/buddy/marks'
import { annotate, fade, forget, pointAt, usePointing } from '../src/renderer/src/features/buddy/pointing'

const mark = (over: Partial<Mark> = {}): Mark => ({ x: 100, y: 500, w: 200, h: 20, why: 'point', ...over })
const shown = (): string[] => usePointing.getState().marks.map((m) => m.key)
/** The engine's event, as the feed hands it to the bus (the type is not in this branch's contract yet). */
const send = (type: string, payload: unknown = {}): void => dispatch({ type, payload } as never)

describe('the numbers shared with features/annotate', () => {
  test('3 marks, 6 s (1.5 to 30), a 12 px grid and 12 px of jitter, 280 ms of rest in a box 6 px bigger', () => {
    assert.equal(MAX_MARKS, 3)
    assert.deepEqual(HOLD, { base: 6000, min: 1500, max: 30_000 })
    assert.equal(KEY_GRID, 12)
    assert.equal(SAME_PX, 12)
    assert.deepEqual(REACH, { restMs: 280, pad: 6 })
  })
})

describe('validMarks / keyOf', () => {
  test('keeps what can be drawn and drops the rest', () => {
    const out = validMarks([mark({ id: 'a' }), null, 'x', mark({ w: 0 }), mark({ x: Number.NaN }), mark({ h: -4 }), { x: 1, y: 2 }, mark({ why: 'shout' as never })])
    assert.deepEqual(out.map(keyOf), ['id:a'])
  })
  test('not a list: nothing', () => {
    assert.deepEqual(validMarks(undefined), [])
    assert.deepEqual(validMarks({ marks: [] }), [])
  })
  test('one per id; a mark without an id is keyed by its kind and its box on the grid', () => {
    const out = validMarks([mark({ id: 'a' }), mark({ id: 'a', x: 900 }), mark(), mark({ x: 101 }), mark({ why: 'answer' })])
    assert.deepEqual(out.map(keyOf), ['id:a', 'point:p:8,42,17,2', 'answer:p:8,42,17,2'])
  })
  test(`at most ${MAX_MARKS}`, () => {
    assert.equal(validMarks(Array.from({ length: 9 }, (_, i) => mark({ id: `m${i}` }))).length, MAX_MARKS)
  })
  test('another display is another mark', () => {
    assert.notEqual(keyOf(mark()), keyOf(mark({ displayId: 2 })))
  })
})

describe('cleanLabel', () => {
  test('the first four words, no backticks, one line', () => {
    assert.equal(cleanLabel('  The   optimizer '), 'The optimizer')
    assert.equal(cleanLabel('Type `lr=1e-3` right in here now'), 'Type lr=1e-3 right in')
    assert.equal(cleanLabel('one\ntwo'), 'one two')
  })
  test('nothing to say: no label', () => {
    assert.equal(cleanLabel('   '), undefined)
    assert.equal(cleanLabel(undefined), undefined)
    assert.equal(cleanLabel(7), undefined)
  })
})

describe('holdFor / fadeAt', () => {
  test('the default, and the engine value kept within reason', () => {
    assert.equal(holdFor(undefined), HOLD.base)
    assert.equal(holdFor(0), HOLD.base)
    assert.equal(holdFor('3000'), HOLD.base)
    assert.equal(holdFor(3000), 3000)
    assert.equal(holdFor(5), HOLD.min)
    assert.equal(holdFor(9e9), HOLD.max)
  })
  test('the hold counts from the newest mark', () => {
    assert.equal(fadeAt([], 6000), undefined)
    assert.equal(fadeAt([{ born: 1000 }, { born: 4000 }], 6000), 10_000)
  })
})

describe('mergeMarks', () => {
  test('a known mark keeps its key, birth and place when it only jittered; a new one is born now', () => {
    const prev = mergeMarks([], [mark({ id: 'a' }), mark({ y: 700 })], [], 1000)
    const next = mergeMarks(prev, [mark({ id: 'a', x: 100 + SAME_PX }), mark({ y: 705 }), mark({ id: 'c', x: 900 })], [], 5000)
    assert.deepEqual(next.map((m) => m.born), [1000, 1000, 5000])
    assert.equal(next[0].rect, prev[0].rect)
    assert.equal(next[1].key, prev[1].key)
    assert.equal(next[1].rect, prev[1].rect)
  })
  test('a mark with an id that really moved takes the new place but is not born again', () => {
    const prev = mergeMarks([], [mark({ id: 'a' })], [], 1000)
    const next = mergeMarks(prev, [mark({ id: 'a', x: 400 })], [], 5000)
    assert.equal(next[0].rect.x, 400)
    assert.equal(next[0].born, 1000)
  })
  test('a mark that is gone is skipped, by id or (no id) by nearly the same box', () => {
    const drawn = mergeMarks([], [mark({ id: 'a' }), mark({ y: 700 })], [], 1000)
    const next = mergeMarks([], [mark({ id: 'a' }), mark({ y: 708 }), mark({ y: 300 })], drawn, 5000)
    assert.deepEqual(next.map((m) => m.rect.y), [300])
  })
  test('it carries the label (cut), the step and the ask', () => {
    const [m] = mergeMarks([], [mark({ id: 'a', label: 'one two three four five', stepId: 's2', askId: 'q1', displayId: 3 })], [], 1)
    assert.deepEqual({ label: m.label, stepId: m.stepId, askId: m.askId, displayId: m.displayId, id: m.id }, { label: 'one two three four', stepId: 's2', askId: 'q1', displayId: 3, id: 'a' })
  })
})

describe('createReach', () => {
  const box = [{ key: 'a', rect: { x: 100, y: 100, w: 100, h: 20 } }]
  const inside = { x: 150, y: 110 }
  const outside = { x: 400, y: 400 }

  test('coming in from outside and resting reaches the mark', () => {
    const r = createReach()
    assert.deepEqual(r.move(outside, box, 0), [])
    assert.deepEqual(r.move(inside, box, 100), [])
    assert.deepEqual(r.move(inside, box, 100 + REACH.restMs - 1), [])
    assert.deepEqual(r.move(inside, box, 100 + REACH.restMs), ['a'])
  })
  test('a pointer already resting there when the mark appears does not', () => {
    const r = createReach()
    assert.deepEqual(r.move(inside, box, 0), [])
    assert.deepEqual(r.move(inside, box, 5000), [])
  })
  test('passing through without resting does not', () => {
    const r = createReach()
    r.move(outside, box, 0)
    r.move(inside, box, 100)
    assert.deepEqual(r.move(outside, box, 200), [])
    assert.deepEqual(r.move(inside, box, 300), [])
    assert.deepEqual(r.move(inside, box, 300 + REACH.restMs), ['a'])
  })
  test(`the box counts ${REACH.pad} px bigger; a press inside it counts at once`, () => {
    const r = createReach()
    assert.deepEqual(r.press({ x: 100 - REACH.pad, y: 100 - REACH.pad }, box), ['a'])
    assert.deepEqual(r.press({ x: 100 - REACH.pad - 1, y: 110 }, box), [])
  })
})

/** Every point the path names: [x, y] pairs, in order. The first is `from`; after the branch's cubic they are the loop. */
function points(d: string): Array<{ x: number; y: number }> {
  const nums = d.match(/-?\d+(\.\d+)?/g)!.map(Number)
  const out: Array<{ x: number; y: number }> = []
  for (let i = 0; i + 1 < nums.length; i += 2) out.push({ x: nums[i], y: nums[i + 1] })
  return out
}
/** The loop's on-curve points: the end point of each cubic after the first (the branch). */
function loop(d: string): Array<{ x: number; y: number }> {
  const all = points(d)
  const out: Array<{ x: number; y: number }> = []
  for (let i = 3; i < all.length; i += 3) out.push(all[i])
  return out
}

describe('reach', () => {
  const from = { x: 800, y: 16 }
  const targets = [
    { x: 100, y: 563, w: 380, h: 18 }, // a line of code, left of the bonsai
    { x: 1200, y: 300, w: 80, h: 28 }, // a button, right of it
    { x: 780, y: 420, w: 44, h: 44 }, // an icon straight below
    { x: 60, y: 60, w: 300, h: 220 }, // a big panel
    { x: 1500, y: 900, w: 6, h: 6 } // a dot in the far corner
  ]

  test('starts at the bonsai, heading down', () => {
    for (const t of targets) {
      const p = points(reach(from, t, 'k').d)
      assert.deepEqual(p[0], from)
      assert.equal(p[1].x, from.x)
      assert.ok(p[1].y > from.y)
    }
  })

  test('the loop goes round the target and never crosses it', () => {
    for (const t of targets) {
      const r = reach(from, t, 'k')
      const pts = loop(r.d)
      assert.equal(pts.length, RING.points + 1)
      for (const p of pts) {
        const inside = p.x > t.x && p.x < t.x + t.w && p.y > t.y && p.y < t.y + t.h
        assert.ok(!inside, `a loop point is inside the target ${JSON.stringify(t)}`)
      }
      // All four sides are visited: the loop really goes round.
      const cx = t.x + t.w / 2
      const cy = t.y + t.h / 2
      assert.ok(pts.some((p) => p.x < t.x) && pts.some((p) => p.x > t.x + t.w) && pts.some((p) => p.y < t.y) && pts.some((p) => p.y > t.y + t.h))
      // And it stays near it (never more than a ring's worth of slack past the loop's own box).
      const box = ringBox(t)
      for (const p of pts) assert.ok(Math.abs(p.x - cx) <= (box.w / 2) * 1.13 && Math.abs(p.y - cy) <= (box.h / 2) * 1.13)
    }
  })

  test('the end passes the start instead of meeting it', () => {
    for (const t of targets) {
      const r = reach(from, t, 'k')
      assert.ok(Math.hypot(r.tip.x - r.join.x, r.tip.y - r.join.y) > 3)
    }
  })

  test('turns away from the bonsai: clockwise for a mark to its right, the other way to its left', () => {
    assert.equal(reach(from, targets[1]).turn, 1)
    assert.equal(reach(from, targets[0]).turn, -1)
  })

  test('the same key always gives the same stroke; another key wobbles differently', () => {
    assert.equal(reach(from, targets[0], 'a').d, reach(from, targets[0], 'a').d)
    assert.notEqual(reach(from, targets[0], 'a').d, reach(from, targets[0], 'b').d)
  })

  test('length and split are sane', () => {
    for (const t of targets) {
      const r = reach(from, t, 'k')
      const straight = Math.hypot(r.join.x - from.x, r.join.y - from.y)
      assert.ok(r.split > 0 && r.split < 1)
      assert.ok(r.length * r.split >= straight - 1, 'the branch is at least the straight line')
      assert.ok(r.length * r.split < straight * 1.8, 'and not a detour')
    }
  })

  test('a one-word target still gets a loop you can see', () => {
    const b = ringBox({ x: 10, y: 10, w: 4, h: 4 })
    assert.ok(b.w >= RING.minW && b.h >= RING.minH)
  })

  test('one line of code: the loop stays in that line and does not strike through the lines around it', () => {
    // An 18 px line box in an 18 px line pitch: the lines above and below start 12 px from this one's middle.
    const line = { x: 100, y: 563, w: 380, h: 18 }
    const mid = line.y + line.h / 2
    for (const p of loop(reach(from, line, 'k').d)) assert.ok(Math.abs(p.y - mid) < 12, `the loop reaches ${Math.abs(p.y - mid).toFixed(1)} px from the line's middle`)
  })

  test('the branch meets the loop on the side facing the bonsai, not across the target', () => {
    for (const t of targets) {
      const r = reach(from, t, 'k')
      const cx = t.x + t.w / 2
      const cy = t.y + t.h / 2
      const far = Math.hypot(2 * cx - r.join.x - from.x, 2 * cy - r.join.y - from.y) // the point opposite the join
      assert.ok(Math.hypot(r.join.x - from.x, r.join.y - from.y) < far)
    }
  })

  test('a mark by a screen edge keeps its loop on screen and still goes round the target', () => {
    const screen = { x: 0, y: 0, w: 1600, h: 1000 }
    const edgy = [
      { x: 40, y: 714, w: 420, h: 85 }, // wide, 40 px from the left edge: an untouched loop would start off screen
      // A target needs a few px to the edge for a loop to pass outside it; closer than that the loop hugs it.
      { x: 12, y: 300, w: 44, h: 44 }, // a sidebar icon by the left edge
      { x: 700, y: 8, w: 60, h: 18 }, // a menu in the menu bar
      { x: 1500, y: 950, w: 90, h: 44 } // the bottom right corner
    ]
    // Left alone, the first one's loop runs off the left edge.
    assert.ok(loop(reach(from, edgy[0], 'k').d).some((p) => p.x < 0))
    for (const t of edgy) {
      const pts = loop(reach(from, t, 'k', undefined, screen).d)
      for (const p of pts) {
        assert.ok(p.x >= 0 && p.y >= 0 && p.x <= 1600 && p.y <= 1000, `off screen at ${p.x},${p.y} for ${JSON.stringify(t)}`)
        assert.ok(!(p.x > t.x && p.x < t.x + t.w && p.y > t.y && p.y < t.y + t.h), 'inside the target')
      }
    }
  })

  test('away from the edges the screen changes nothing', () => {
    const screen = { x: 0, y: 0, w: 1600, h: 1000 }
    assert.equal(reach(from, targets[1], 'k', undefined, screen).d, reach(from, targets[1], 'k').d)
  })

  test('it leaves along the heading it is given', () => {
    const r = reach({ x: 500, y: 300 }, targets[1], 'k', { x: 3, y: 4 })
    const p = points(r.d)
    const dx = p[1].x - p[0].x
    const dy = p[1].y - p[0].y
    assert.ok(Math.abs(dx / Math.hypot(dx, dy) - 0.6) < 0.01 && Math.abs(dy / Math.hypot(dx, dy) - 0.8) < 0.01)
  })
})

describe('ribbon (a stroke of varying width)', () => {
  const from = { x: 800, y: 16 }
  const r = reach(from, { x: 100, y: 563, w: 380, h: 18 }, 'k')
  /** The outline's corner points, in order. */
  const corners = (d: string): Array<{ x: number; y: number }> => {
    const nums = d.match(/-?\d+(\.\d+)?/g)!.map(Number)
    const out: Array<{ x: number; y: number }> = []
    for (let i = 0; i + 1 < nums.length; i += 2) out.push({ x: nums[i], y: nums[i + 1] })
    return out
  }

  test('the spine runs from the bonsai to the tip, and its shares run from 0 to 1', () => {
    assert.deepEqual(r.spine[0], from)
    assert.equal(r.spine.length, r.at.length)
    assert.equal(r.at[0], 0)
    assert.ok(Math.abs(r.at[r.at.length - 1] - 1) < 1e-9)
    for (let i = 1; i < r.at.length; i++) assert.ok(r.at[i] >= r.at[i - 1])
    const tip = r.spine[r.spine.length - 1]
    assert.ok(Math.hypot(tip.x - r.tip.x, tip.y - r.tip.y) < 0.5)
  })

  test('a closed outline, as wide as asked: thick at the tree, thin at the loop', () => {
    const d = ribbon(r, (t) => (t < r.split ? 4 : 2))
    assert.ok(d.startsWith('M') && d.endsWith('Z'))
    const pts = corners(d)
    // The first and the last corner are the two sides of the stroke at the bonsai; the middle two, at the tip.
    const root = Math.hypot(pts[0].x - pts[pts.length - 1].x, pts[0].y - pts[pts.length - 1].y)
    const mid = pts.length / 2
    const tip = Math.hypot(pts[mid - 1].x - pts[mid].x, pts[mid - 1].y - pts[mid].y)
    assert.ok(Math.abs(root - 4) < 0.3, `root ${root}`)
    assert.ok(Math.abs(tip - 2) < 0.3, `tip ${tip}`)
  })

  test('it comes to a point at the head and the tail of what is showing', () => {
    const pts = corners(ribbon(r, () => 3, [0.2, 0.6], { head: 20, tail: 20 }))
    const mid = pts.length / 2
    assert.ok(Math.hypot(pts[0].x - pts[pts.length - 1].x, pts[0].y - pts[pts.length - 1].y) < 0.2, 'the tail is a point')
    assert.ok(Math.hypot(pts[mid - 1].x - pts[mid].x, pts[mid - 1].y - pts[mid].y) < 0.2, 'the head is a point')
  })

  test('nothing showing, or nothing of the part asked for: no outline', () => {
    assert.equal(ribbon(r, () => 3, [0.5, 0.5]), '')
    assert.equal(ribbon(r, () => 3, [r.split, 1], undefined, [0, r.split]), '', 'the branch part of a stroke that is only its loop')
    assert.notEqual(ribbon(r, () => 3, [r.split, 1], undefined, [r.split, 1]), '')
  })
})

describe('forkFor', () => {
  const from = { x: 800, y: 16 }
  const trunk = reach(from, { x: 100, y: 563, w: 380, h: 18 }, 'trunk')

  test('a mark beside the trunk forks off it, part of the way along, heading the way the trunk goes', () => {
    const fork = forkFor(trunk, { x: 514, y: 474, w: 156, h: 34 })
    assert.ok(fork)
    assert.ok(fork.t >= FORK.min && fork.t <= FORK.max)
    // The fork point is on the trunk: between the bonsai and the loop.
    assert.ok(fork.at.y > from.y && fork.at.y < trunk.join.y)
    // Heading down and to the left, like the trunk there.
    assert.ok(fork.heading.y > 0 && fork.heading.x < 0)
  })

  test('a mark behind the trunk (the other side of the bonsai, near the top) gets its own branch', () => {
    assert.equal(forkFor(trunk, { x: 1400, y: 40, w: 80, h: 24 }), undefined)
  })
})

describe('drawTime', () => {
  test('a line drawing itself, longer for a longer reach, capped', () => {
    assert.equal(drawTime(0), duration.draw)
    assert.ok(drawTime(600) > drawTime(200))
    assert.equal(drawTime(99999), DRAW.max)
  })
  test('timeToDraw: ease.out draws most of a stroke early, and it is monotone from 0 to 1', () => {
    assert.ok(timeToDraw(0) < 0.001)
    assert.ok(timeToDraw(1) > 0.999)
    assert.ok(timeToDraw(0.5) < 0.25, 'half the stroke is drawn in the first quarter of the time')
    let last = 0
    for (let s = 0.05; s <= 1; s += 0.05) {
      const t = timeToDraw(s)
      assert.ok(t >= last)
      last = t
    }
  })
})

describe('labelAt', () => {
  const bounds = { x: 0, y: 32, w: 1600, h: 880 }
  const size = { w: 120, h: 26 }
  test('beside the loop on the side away from the bonsai, centered on it', () => {
    const ring = { x: 400, y: 400, w: 200, h: 60 }
    assert.deepEqual(labelAt(ring, size, bounds, 'right'), { x: 600 + LABEL.gap, y: 417, side: 'right' })
    assert.deepEqual(labelAt(ring, size, bounds, 'left'), { x: 400 - LABEL.gap - 120, y: 417, side: 'left' })
  })
  test('no room on that side: below, then the bonsai side (under the loop top, clear of the branch), and above last', () => {
    const atRight = { x: 1380, y: 400, w: 200, h: 60 }
    assert.equal(labelAt(atRight, size, bounds, 'right').side, 'below')
    const bottomRight = { x: 1380, y: 840, w: 200, h: 60 }
    const near = labelAt(bottomRight, size, bounds, 'right')
    assert.equal(near.side, 'left')
    assert.ok(near.y >= bottomRight.y + LABEL.under)
    // A flat loop: a label on the bonsai's side starts under the loop's top edge, where the branch runs in.
    const flat = { x: 1380, y: 860, w: 200, h: 22 }
    const under = labelAt(flat, size, bounds, 'right')
    assert.equal(under.side, 'left')
    assert.equal(under.y, flat.y + LABEL.under)
    // Nothing beside or below it fits: above.
    const wide = { x: 20, y: 860, w: 1560, h: 40 }
    assert.equal(labelAt(wide, size, bounds, 'right').side, 'above')
  })
  test('always fully on screen', () => {
    for (const ring of [{ x: -50, y: 0, w: 80, h: 40 }, { x: 1560, y: 890, w: 80, h: 40 }, { x: 0, y: 32, w: 1600, h: 880 }]) {
      for (const prefer of ['left', 'right'] as const) {
        const p = labelAt(ring, size, bounds, prefer)
        assert.ok(p.x >= LABEL.edge && p.x + size.w <= 1600 - LABEL.edge, `x ${p.x}`)
        assert.ok(p.y >= 32 + LABEL.edge && p.y + size.h <= 912 - LABEL.edge, `y ${p.y}`)
      }
    }
  })
})

describe('pointing (the annotate event)', () => {
  beforeEach(() => {
    mock.timers.enable({ apis: ['setTimeout', 'Date'] })
    forget()
  })
  afterEach(() => {
    forget()
    pointAt()
    mock.timers.reset()
  })

  test('an annotate from the engine shows its marks; the next one replaces them', () => {
    send('annotate', { marks: [mark({ id: 'a', label: 'Here' })] })
    assert.deepEqual(shown(), ['id:a'])
    assert.equal(usePointing.getState().marks[0].label, 'Here')
    send('annotate', { marks: [mark({ id: 'b' }), mark({ id: 'c', x: 700 })] })
    assert.deepEqual(shown(), ['id:b', 'id:c'])
  })

  test('they fade after holdMs, or the default 6 s', () => {
    annotate({ marks: [mark({ id: 'a' })], holdMs: 2000 })
    mock.timers.tick(1999)
    assert.deepEqual(shown(), ['id:a'])
    mock.timers.tick(1)
    assert.deepEqual(shown(), [])
    annotate({ marks: [mark({ id: 'b' })] })
    mock.timers.tick(HOLD.base - 1)
    assert.deepEqual(shown(), ['id:b'])
    mock.timers.tick(1)
    assert.deepEqual(shown(), [])
  })

  test('a re-send keeps the circle where it is and does NOT start the hold again; a new mark does', () => {
    annotate({ marks: [mark({ id: 'a' })], holdMs: 2000 })
    const first = usePointing.getState().marks[0].rect
    mock.timers.tick(1500)
    annotate({ marks: [mark({ id: 'a', x: 103 })], holdMs: 2000 })
    assert.equal(usePointing.getState().marks[0].rect, first)
    mock.timers.tick(499)
    assert.deepEqual(shown(), ['id:a'])
    mock.timers.tick(1)
    assert.deepEqual(shown(), [], 'gone 2 s after it was born, not 2 s after the re-send')

    annotate({ marks: [mark({ id: 'b' })], holdMs: 2000 })
    mock.timers.tick(1500)
    annotate({ marks: [mark({ id: 'b' }), mark({ id: 'c', x: 700 })], holdMs: 2000 })
    mock.timers.tick(1999)
    assert.deepEqual(shown(), ['id:b', 'id:c'], 'the new mark moved the deadline for the set')
    mock.timers.tick(1)
    assert.deepEqual(shown(), [])
  })

  test('a mark that faded stays gone for the step, however it went', () => {
    const ways: Array<[string, () => void]> = [
      ['timed out', () => mock.timers.tick(HOLD.base)],
      ['engine clear', () => send('annotate', { clear: true })],
      ['reached', () => fade(['id:a'])],
      ['Esc', () => void emitUi('dismiss')]
    ]
    for (const [name, go] of ways) {
      forget()
      annotate({ marks: [mark({ id: 'a' })] })
      go()
      assert.deepEqual(shown(), [], name)
      annotate({ marks: [mark({ id: 'a' })] })
      assert.deepEqual(shown(), [], `${name}: the same mark re-sent stays gone`)
      annotate({ marks: [mark({ id: 'a' }), mark({ id: 'b', x: 700 })] })
      assert.deepEqual(shown(), ['id:b'], `${name}: another mark shows, the gone one does not`)
    }
  })

  test('reaching one mark leaves the others, and their hold keeps running', () => {
    annotate({ marks: [mark({ id: 'a' }), mark({ id: 'b', x: 700 })], holdMs: 3000 })
    mock.timers.tick(1000)
    fade(['id:a'])
    assert.deepEqual(shown(), ['id:b'])
    mock.timers.tick(2000)
    assert.deepEqual(shown(), [])
  })

  test('a new circle-to-ask starts fresh', () => {
    annotate({ marks: [mark({ id: 'a', why: 'answer', askId: 'q1' })] })
    fade()
    annotate({ marks: [mark({ id: 'a', why: 'answer', askId: 'q1' })] })
    assert.deepEqual(shown(), [])
    annotate({ marks: [mark({ id: 'a', why: 'answer', askId: 'q2' })] })
    assert.deepEqual(shown(), ['id:a'])
  })

  test('a new step keeps only the marks sent for it and forgets what was gone; a replayed step changes nothing', () => {
    annotate({ marks: [mark({ id: 'a', stepId: 's1' }), mark({ id: 'b', x: 700, stepId: 's2' })] })
    send('step.started', { stepId: 's1', replay: true })
    assert.deepEqual(shown(), ['id:a', 'id:b'])
    send('step.started', { stepId: 's2' })
    assert.deepEqual(shown(), ['id:b'])
    mock.timers.tick(HOLD.base)
    assert.deepEqual(shown(), [], 'the kept mark gets a fresh default hold')
    send('step.started', { stepId: 's3' })
    annotate({ marks: [mark({ id: 'b', x: 700 })] })
    assert.deepEqual(shown(), ['id:b'], 'gone last step, drawable again this step')
  })

  test('step.passed, the lesson ending, a new lesson and a reset clear everything and remember nothing', () => {
    for (const end of [() => send('step.passed', { stepId: 's1' }), () => send('lesson.ended', {}), () => send('lesson.ready', {}), () => void emitUi('reset')]) {
      annotate({ marks: [mark({ id: 'a' })] })
      end()
      assert.deepEqual(shown(), [])
      annotate({ marks: [mark({ id: 'a' })] })
      assert.deepEqual(shown(), ['id:a'])
      forget()
    }
  })

  test('an empty list takes the marks away without holding it against them', () => {
    annotate({ marks: [mark({ id: 'a' })] })
    send('annotate', { marks: [] })
    assert.deepEqual(shown(), [])
    annotate({ marks: [mark({ id: 'a' })] })
    assert.deepEqual(shown(), ['id:a'])
  })

  test('a payload that is not an annotate changes nothing', () => {
    annotate({ marks: [mark({ id: 'a' })] })
    for (const bad of [null, 'clear', 7, {}, { holdMs: 5 }]) annotate(bad)
    assert.deepEqual(shown(), ['id:a'])
  })

  test('Esc never claims the event, so cards still close', () => {
    annotate({ marks: [mark({ id: 'a' })] })
    assert.equal(emitUi('dismiss'), false)
  })

  test('pointAt: the pose another layer asks for, and its end', () => {
    const box = { x: 10, y: 20, w: 30, h: 40 }
    pointAt(box)
    assert.equal(usePointing.getState().pose, box)
    pointAt()
    assert.equal(usePointing.getState().pose, undefined)
  })
})
