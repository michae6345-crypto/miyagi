/**
 * On-screen coach (Nov 24): the step's text and keys beside the loop. Pure rules (marks.ts cleanText / cleanKeys /
 * mergeMarks / timedMarks) and placement (geometry.ts textSpot). Offline, no window:
 * `node --import tsx --test src/renderer/src/features/annotate/text.test.ts`
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { BRANCH_CLEAR, buddyPath, hashSeed, lineHitsRect, ringBox, ringFor, segmentHitsRect, textSpot, TEXT_EDGE, type Rect } from './geometry'
import { cleanKeys, cleanText, DEFAULT_HOLD_MS, fadeAt, mergeMarks, timedMarks, type Annotation } from './marks'

/** Keycap labels as the engine spells them on a Mac (engine data, not app copy). */
const SHIFT_A = '\u21e7A'
const CMD_S = '\u2318S'

/** An Annotation with the coach's fields (contract Nov 24), before they reach the contract on this branch. */
const mark = (m: Annotation & { text?: unknown; keys?: unknown }): Annotation => m

describe('coach text and keys', () => {
  it('cuts the text to 12 words and drops what is not text', () => {
    assert.equal(cleanText('  Add   a torus from the Add menu '), 'Add a torus from the Add menu')
    const long = 'one two three four five six seven eight nine ten eleven twelve thirteen fourteen'
    assert.equal(cleanText(long), 'one two three four five six seven eight nine ten eleven twelve')
    assert.equal(cleanText(long)!.split(' ').length, 12)
    assert.equal(cleanText('   '), undefined)
    assert.equal(cleanText(42), undefined)
    assert.equal(cleanText(undefined), undefined)
  })
  it('keeps at most 3 keys, strings only, 1 to 12 characters each', () => {
    assert.deepEqual(cleanKeys([SHIFT_A]), [SHIFT_A])
    assert.deepEqual(cleanKeys(['Tab', 7, null, 'G', { k: 1 }, 'Numpad 1', 'X']), ['Tab', 'G', 'Numpad 1'])
    assert.deepEqual(cleanKeys(['', '   ', 'a key label far too long', 'S']), ['S'])
    assert.equal(cleanKeys([1, 2]), undefined)
    assert.equal(cleanKeys(CMD_S), undefined)
    assert.equal(cleanKeys(undefined), undefined)
  })

  const a = { id: 'os-1', x: 600, y: 400, w: 120, h: 30, why: 'point' as const }
  it('mergeMarks carries text and keys; a re-send updates them without a new birth or key', () => {
    const first = mergeMarks([], [mark({ ...a, text: 'Add a torus from the Add menu', keys: [SHIFT_A, 5] })], [], 1000)
    assert.equal(first[0].text, 'Add a torus from the Add menu')
    assert.deepEqual(first[0].keys, [SHIFT_A])
    const again = mergeMarks(first, [mark({ ...a, x: a.x + 3, text: 'Pick Torus in the Mesh list', keys: [SHIFT_A] })], [], 2500)
    assert.equal(again[0].text, 'Pick Torus in the Mesh list')
    assert.equal(again[0].born, 1000, 'same birth: the stroke does not redraw')
    assert.equal(again[0].key, first[0].key)
    assert.deepEqual(again[0].rect, first[0].rect, 'a re-read a few points off keeps the drawn box')
    const plain = mergeMarks(again, [a], [], 3000)
    assert.equal(plain[0].text, undefined, 'a re-send without text drops it')
    assert.equal(plain[0].born, 1000)
  })
  it('a mark with no id keeps text across a jittered re-send too', () => {
    const { id: _id, ...noId } = a
    const first = mergeMarks([], [mark({ ...noId, text: 'Click here' })], [], 1000)
    const again = mergeMarks(first, [mark({ ...noId, y: noId.y + 4, text: 'Click here now' })], [], 2000)
    assert.equal(again[0].key, first[0].key)
    assert.equal(again[0].born, 1000)
    assert.equal(again[0].text, 'Click here now')
  })
  it('text and keys belong to point marks only; keys need text', () => {
    const m = mergeMarks([], [mark({ ...a, why: 'answer', text: 'Not for answers', keys: [CMD_S] })], [], 1000)
    assert.equal(m[0].text, undefined)
    assert.equal(m[0].keys, undefined)
    const k = mergeMarks([], [mark({ ...a, keys: [CMD_S] })], [], 1000)
    assert.equal(k[0].keys, undefined)
  })
  it('only marks without text are timed', () => {
    const marks = mergeMarks([], [mark({ ...a, text: 'Stay here' }), { ...a, id: 'os-2', x: 100 }], [], 1000)
    assert.deepEqual(
      timedMarks(marks).map((m) => m.id),
      ['os-2']
    )
    assert.equal(fadeAt(timedMarks(marks.slice(0, 1)), DEFAULT_HOLD_MS), undefined, 'a text mark alone: no fade time')
    assert.equal(fadeAt(timedMarks(marks), DEFAULT_HOLD_MS), 1000 + DEFAULT_HOLD_MS)
  })
})

describe('textSpot', () => {
  const size = { width: 1440, height: 900 }
  const tb = { w: 240, h: 36 }
  const hits = (p: { x: number; y: number }, r: Rect, b = tb): boolean => p.x < r.x + r.w && p.x + b.w > r.x && p.y < r.y + r.h && p.y + b.h > r.y
  const cases: Record<string, Rect> = {
    centre: { x: 660, y: 430, w: 120, h: 40 },
    'right edge': { x: 1360, y: 300, w: 64, h: 32 },
    'bottom edge': { x: 40, y: 852, w: 1360, h: 32 },
    'bottom right corner': { x: 1370, y: 850, w: 54, h: 34 },
    'top left corner': { x: 4, y: 4, w: 60, h: 28 },
    'left edge': { x: 0, y: 500, w: 40, h: 40 },
    'small icon': { x: 700, y: 120, w: 12, h: 12 }
  }
  for (const [name, target] of Object.entries(cases)) {
    for (const box of [tb, { w: 280, h: 50 }, { w: 120, h: 36 }]) {
      it(`at the ${name} (${box.w}x${box.h}): not over the target or the loop, 16 pt inside the display`, () => {
        const ring = ringFor(target)
        const p = textSpot(ring, target, size, box)
        assert.ok(!hits(p, target, box), 'covers the target')
        assert.ok(!hits(p, ringBox(ring), box), 'covers the loop')
        assert.ok(p.x >= TEXT_EDGE && p.y >= TEXT_EDGE, 'top / left edge')
        assert.ok(p.x + box.w <= size.width - TEXT_EDGE && p.y + box.h <= size.height - TEXT_EDGE, 'right / bottom edge')
      })
    }
  }
  it('flips: right first, left at the right edge, above a bottom bar, below a top bar', () => {
    const at = (t: Rect): string => textSpot(ringFor(t), t, size, tb).side
    assert.equal(at(cases.centre), 'right')
    assert.equal(at(cases['right edge']), 'left')
    assert.equal(at(cases['bottom edge']), 'above')
    assert.equal(at({ x: 40, y: 20, w: 1360, h: 28 }), 'below')
  })
  it('sits beside the loop with a gap, centered on its line', () => {
    const t = cases.centre
    const ring = ringFor(t)
    const p = textSpot(ring, t, size, tb)
    assert.equal(p.x, ring.cx + ring.rx + 8)
    assert.equal(p.y, ring.cy - tb.h / 2)
    assert.ok(p.fits)
  })
  it('when no side fits, it still leaves the target uncovered, stays inside, and covers the least of the loop', () => {
    // A small display: the loop leaves no full side for the box.
    const small = { width: 420, height: 160 }
    const t = { x: 150, y: 60, w: 120, h: 40 }
    const ring = ringFor(t)
    const p = textSpot(ring, t, small, tb)
    assert.equal(p.fits, false)
    assert.ok(!hits(p, t), 'covers the target')
    assert.ok(p.x >= TEXT_EDGE && p.y >= TEXT_EDGE && p.x + tb.w <= small.width - TEXT_EDGE && p.y + tb.h <= small.height - TEXT_EDGE)
  })
  it('keeps clear of the buddy line, and still of the target, the loop and the edges', () => {
    for (const island of [{ x: 720, y: 30 }, { x: 200, y: 30 }, { x: 1300, y: 30 }]) {
      for (const [name, target] of Object.entries(cases)) {
        const path = buddyPath(island, target, hashSeed(name))
        const p = textSpot(path.ring, target, size, tb, path.branch)
        const at = `${name} from ${island.x}`
        if (p.fits) assert.ok(!lineHitsRect(path.branch, { ...p, ...tb }, BRANCH_CLEAR), `${at}: on the line`)
        assert.ok(!hits(p, target), `${at}: covers the target`)
        assert.ok(!hits(p, ringBox(path.ring)), `${at}: covers the loop`)
        assert.ok(p.x >= TEXT_EDGE && p.y >= TEXT_EDGE && p.x + tb.w <= size.width - TEXT_EDGE && p.y + tb.h <= size.height - TEXT_EDGE, `${at}: edges`)
      }
    }
  })
  it('slides along a bottom bar off the line that comes down to it', () => {
    const t = cases['bottom edge']
    const island = { x: 720, y: 30 }
    const path = buddyPath(island, t, 1)
    const plain = textSpot(path.ring, t, size, tb)
    assert.ok(lineHitsRect(path.branch, { ...plain, ...tb }), 'without the line, the box sits on it (the case is real)')
    const p = textSpot(path.ring, t, size, tb, path.branch)
    assert.equal(p.side, 'above')
    assert.equal(p.y, plain.y)
    assert.ok(!lineHitsRect(path.branch, { ...p, ...tb }, BRANCH_CLEAR))
  })
  it('segment and rect: crossing, inside, beside', () => {
    const r = { x: 10, y: 10, w: 20, h: 20 }
    assert.ok(segmentHitsRect({ x: 0, y: 20 }, { x: 40, y: 20 }, r))
    assert.ok(segmentHitsRect({ x: 15, y: 15 }, { x: 16, y: 16 }, r))
    assert.ok(!segmentHitsRect({ x: 0, y: 0 }, { x: 40, y: 0 }, r))
    assert.ok(!segmentHitsRect({ x: 0, y: 40 }, { x: 40, y: 50 }, r))
  })
  it('is pure: same input, same spot', () => {
    const t = cases['right edge']
    assert.deepEqual(textSpot(ringFor(t), t, size, tb), textSpot(ringFor(t), t, size, tb))
  })
})
