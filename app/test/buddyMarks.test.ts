/**
 * The buddy's pointing branch, offline: features/buddy/marks.ts (the engine's marks cleaned, the stroke's shape, the
 * label's place, the timing) and features/buddy/pointing.ts (what is shown and for how long, through the real bus).
 */
import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import { dispatch, emitUi } from '../src/renderer/src/core/bus'
import { duration } from '../src/renderer/src/core/ui/motionTokens'
import { cleanLabel, cleanMarks, DRAW, drawTime, FORK, forkFor, HOLD, holdFor, JITTER_PX, LABEL, labelAt, MAX_MARKS, reach, RING, ringBox, settle, timeToDraw, type Mark } from '../src/renderer/src/features/buddy/marks'
import { annotate, clearMarks, found, usePointing } from '../src/renderer/src/features/buddy/pointing'

const mark = (over: Partial<Mark> = {}): Mark => ({ x: 100, y: 500, w: 200, h: 20, why: 'point', ...over })
const shown = (): string[] => usePointing.getState().marks.map((m) => m.key)
/** The engine's event, as the feed hands it to the bus (the type is not in this branch's contract yet). */
const send = (type: string, payload: unknown = {}): void => dispatch({ type, payload } as never)

describe('cleanMarks', () => {
  test('keeps what can be drawn and drops the rest', () => {
    const out = cleanMarks([mark({ id: 'a' }), null, 'x', mark({ w: 0 }), mark({ x: Number.NaN }), mark({ h: -4 }), { x: 1, y: 2 }])
    assert.deepEqual(out.map((m) => m.key), ['a'])
    assert.deepEqual(out[0].rect, { x: 100, y: 500, w: 200, h: 20 })
  })
  test('not a list: nothing', () => {
    assert.deepEqual(cleanMarks(undefined), [])
    assert.deepEqual(cleanMarks({ marks: [] }), [])
  })
  test('one per id, and a mark without an id is keyed by its place', () => {
    const out = cleanMarks([mark({ id: 'a' }), mark({ id: 'a', x: 900 }), mark(), mark(), mark({ why: 'answer' })])
    assert.deepEqual(out.map((m) => m.key), ['a', 'point:100,500,200,20', 'answer:100,500,200,20'])
  })
  test(`at most ${MAX_MARKS}`, () => {
    assert.equal(cleanMarks(Array.from({ length: 9 }, (_, i) => mark({ id: `m${i}` }))).length, MAX_MARKS)
  })
  test('an unknown why is a plain point', () => {
    assert.equal(cleanMarks([mark({ why: 'shout' as never })])[0].why, 'point')
  })
})

describe('cleanLabel', () => {
  test('four words at most, no backticks, one line', () => {
    assert.equal(cleanLabel('  The   optimizer '), 'The optimizer')
    assert.equal(cleanLabel('Type `lr=1e-3` right in here now'), 'Type lr=1e-3 right in…')
    assert.equal(cleanLabel('one\ntwo'), 'one two')
  })
  test('nothing to say: no label', () => {
    assert.equal(cleanLabel('   '), undefined)
    assert.equal(cleanLabel(undefined), undefined)
    assert.equal(cleanLabel(7), undefined)
  })
})

describe('holdFor', () => {
  test('the default, and the engine value kept within reason', () => {
    assert.equal(holdFor(undefined), HOLD.base)
    assert.equal(holdFor(0), HOLD.base)
    assert.equal(holdFor('3000'), HOLD.base)
    assert.equal(holdFor(3000), 3000)
    assert.equal(holdFor(5), HOLD.min)
    assert.equal(holdFor(9e9), HOLD.max)
  })
})

describe('settle', () => {
  test('a re-sent mark that only jittered keeps its old place; one that moved takes the new one', () => {
    const prev = cleanMarks([mark({ id: 'a' }), mark({ id: 'b' })])
    const next = cleanMarks([mark({ id: 'a', x: 100 + JITTER_PX, y: 497 }), mark({ id: 'b', x: 100 + JITTER_PX + 1 }), mark({ id: 'c', x: 0 })])
    const out = settle(prev, next)
    assert.deepEqual(out[0].rect, prev[0].rect)
    assert.equal(out[1].rect.x, 100 + JITTER_PX + 1)
    assert.equal(out[2].rect.x, 0)
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
    clearMarks()
  })
  afterEach(() => {
    clearMarks()
    mock.timers.reset()
  })

  test('an annotate from the engine shows its marks; the next one replaces them', () => {
    send('annotate', { marks: [mark({ id: 'a', label: 'Here' })] })
    assert.deepEqual(shown(), ['a'])
    assert.equal(usePointing.getState().marks[0].label, 'Here')
    send('annotate', { marks: [mark({ id: 'b' }), mark({ id: 'c', x: 700 })] })
    assert.deepEqual(shown(), ['b', 'c'])
  })

  test('they fade after holdMs, or the default', () => {
    annotate({ marks: [mark({ id: 'a' })], holdMs: 2000 })
    mock.timers.tick(1999)
    assert.deepEqual(shown(), ['a'])
    mock.timers.tick(1)
    assert.deepEqual(shown(), [])
    annotate({ marks: [mark({ id: 'a' })] })
    mock.timers.tick(HOLD.base - 1)
    assert.deepEqual(shown(), ['a'])
    mock.timers.tick(1)
    assert.deepEqual(shown(), [])
  })

  test('a re-send keeps the circle where it is and starts the hold again', () => {
    annotate({ marks: [mark({ id: 'a' })], holdMs: 2000 })
    const first = usePointing.getState().marks[0].rect
    mock.timers.tick(1500)
    annotate({ marks: [mark({ id: 'a', x: 103 })], holdMs: 2000 })
    assert.equal(usePointing.getState().marks[0].rect, first)
    mock.timers.tick(1500)
    assert.deepEqual(shown(), ['a'])
    mock.timers.tick(500)
    assert.deepEqual(shown(), [])
  })

  test('clear, an empty list, a new step and the lesson ending all take them away', () => {
    for (const end of [() => send('annotate', { clear: true }), () => send('annotate', { marks: [] }), () => send('step.started', { stepId: 's2' }), () => send('step.passed', { stepId: 's1' }), () => send('lesson.ended', {}), () => emitUi('reset')]) {
      annotate({ marks: [mark({ id: 'a' })] })
      assert.deepEqual(shown(), ['a'])
      end()
      assert.deepEqual(shown(), [])
    }
  })

  test('a payload that is not an annotate changes nothing', () => {
    annotate({ marks: [mark({ id: 'a' })] })
    for (const bad of [null, 'clear', 7, {}, { marks: 'all' }, { clear: 'yes' }]) annotate(bad)
    assert.deepEqual(shown(), ['a'])
  })

  test('found: the circle leaves soon, and the engine re-sending it does not bring it back', () => {
    annotate({ marks: [mark({ id: 'a' })], holdMs: 20_000 })
    found()
    found() // more pointer moves on the mark change nothing
    mock.timers.tick(HOLD.found - 1)
    assert.deepEqual(shown(), ['a'])
    mock.timers.tick(1)
    assert.deepEqual(shown(), [])
    annotate({ marks: [mark({ id: 'a' })] })
    assert.deepEqual(shown(), [], 'the same mark stays gone')
    annotate({ marks: [mark({ id: 'a' }), mark({ id: 'b', x: 700 })] })
    assert.deepEqual(shown(), ['a', 'b'], 'a different set shows')
  })

  test('found never makes a mark stay longer than the engine asked', () => {
    annotate({ marks: [mark({ id: 'a' })], holdMs: HOLD.min })
    mock.timers.tick(HOLD.min - 200)
    found()
    mock.timers.tick(200)
    assert.deepEqual(shown(), [])
  })

  test('Esc sends them away without claiming the event, and a new step forgets that', () => {
    annotate({ marks: [mark({ id: 'a' })] })
    assert.equal(emitUi('dismiss'), false)
    assert.deepEqual(shown(), [])
    annotate({ marks: [mark({ id: 'a' })] })
    assert.deepEqual(shown(), [])
    send('step.started', { stepId: 's2' })
    annotate({ marks: [mark({ id: 'a' })] })
    assert.deepEqual(shown(), ['a'])
  })

  test('the lean goes back to upright with the marks', () => {
    annotate({ marks: [mark({ id: 'a' })] })
    usePointing.setState({ lean: -0.6 }) // the layer sets this
    send('annotate', { clear: true })
    assert.equal(usePointing.getState().lean, 0)
  })
})
