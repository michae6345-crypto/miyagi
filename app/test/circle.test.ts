/** features/circle, offline: ink to box, box to screen points, the card's place, and the circle-to-ask state machine. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { addPoint, bounds, clampBox, fromRegion, inkPath, loopPoints, MIN_INK, placeCard, strokeBox, toOverlay, toRegion, type Pt } from '../src/renderer/src/features/circle/geometry'
import { ANSWER_MS, ARMED_MAX_MS, ASK_MAX_MS, DEFAULT_ASK, IDLE, interactive, step, WORDS_WAIT_MS, type CircleEvent, type CircleState, type Ctx } from '../src/renderer/src/features/circle/machine'

const loop = (x: number, y: number, w: number, h: number): Pt[] => loopPoints(x, y, w, h)

describe('stroke to box', () => {
  test('bounds of a loop, padded, inside the overlay', () => {
    const pts: Pt[] = [{ x: 100, y: 200 }, { x: 300, y: 180 }, { x: 260, y: 320 }, { x: 110, y: 300 }]
    assert.deepEqual(bounds(pts), { x: 100, y: 180, w: 200, h: 140 })
    assert.deepEqual(strokeBox([pts], 1600, 1000, 6), { x: 94, y: 174, w: 212, h: 152 })
  })
  test('several strokes make one box', () => {
    assert.deepEqual(strokeBox([[{ x: 10, y: 10 }, { x: 40, y: 40 }], [{ x: 200, y: 5 }, { x: 210, y: 60 }]], 1000, 1000, 0), { x: 10, y: 5, w: 200, h: 55 })
  })
  test('a click or a dot is not a circle', () => {
    assert.equal(strokeBox([[{ x: 50, y: 50 }]], 1000, 1000), undefined)
    assert.equal(strokeBox([[{ x: 50, y: 50 }, { x: 50 + MIN_INK - 1, y: 52 }]], 1000, 1000), undefined)
    assert.equal(strokeBox([], 1000, 1000), undefined)
  })
  test('a line counts when it is long enough on one side', () => {
    assert.ok(strokeBox([[{ x: 50, y: 50 }, { x: 150, y: 51 }]], 1000, 1000))
  })
  test('ink at the screen edge stays on the overlay', () => {
    const b = strokeBox([[{ x: -20, y: 2 }, { x: 60, y: 90 }]], 800, 600, 6)!
    assert.equal(b.x, 0)
    assert.equal(b.y, 0)
    assert.ok(b.x + b.w <= 800 && b.y + b.h <= 600)
  })
  test('non-finite points are ignored', () => {
    assert.deepEqual(bounds([{ x: NaN, y: 1 }, { x: 5, y: 6 }]), { x: 5, y: 6, w: 0, h: 0 })
  })
  test('a still hand adds no points', () => {
    const s = [{ x: 10, y: 10 }]
    assert.equal(addPoint(s, { x: 10.5, y: 10.5 }), s)
    assert.equal(addPoint(s, { x: 20, y: 10 }).length, 2)
  })
})

describe('box to screen points', () => {
  test('the window origin is added and the far edges round outward', () => {
    assert.deepEqual(toRegion({ x: 10.4, y: 20.6, w: 100.2, h: 50.1 }, { x: 0, y: 0 }, 2, 69733382), { x: 10, y: 20, w: 101, h: 51, displayId: 69733382, scale: 2 })
  })
  test('a second display left of the primary has a negative origin', () => {
    const r = toRegion({ x: 100, y: 50, w: 200, h: 100 }, { x: -1920, y: -120 }, 1, 2)
    assert.deepEqual(r, { x: -1820, y: -70, w: 200, h: 100, displayId: 2, scale: 1 })
    assert.deepEqual(fromRegion(r, { x: -1920, y: -120 }), { x: 100, y: 50, w: 200, h: 100 })
  })
  test('unknown display and a bad scale fall back to 0 and 1', () => {
    const r = toRegion({ x: 0, y: 0, w: 10, h: 10 }, { x: 0, y: 0 }, 0, undefined)
    assert.equal(r.displayId, 0)
    assert.equal(r.scale, 1)
  })
  test("the browser stage's CSS scale is undone", () => {
    assert.deepEqual(toOverlay(300, 200, { left: 100, top: 50 }, 2), { x: 400, y: 300 })
  })
})

describe('ink path', () => {
  test('empty, a dot, a line, a curve', () => {
    assert.equal(inkPath([]), '')
    assert.match(inkPath([{ x: 1, y: 2 }]), /^M1 2/)
    assert.equal(inkPath([{ x: 1, y: 2 }, { x: 3, y: 4 }]), 'M1 2L3 4')
    const d = inkPath(loop(100, 100, 200, 100))
    assert.match(d, /^M[\d.]+ [\d.]+Q/)
    assert.ok(!d.includes('NaN'))
  })
})

describe('clamping and the card place', () => {
  const area = { w: 1440, h: 900 }
  test('clampBox keeps a box inside and shrinks one that is too big', () => {
    assert.deepEqual(clampBox({ x: -10, y: 880, w: 50, h: 50 }, { x: 0, y: 0, w: 1440, h: 900 }), { x: 0, y: 850, w: 50, h: 50 })
    assert.deepEqual(clampBox({ x: 5, y: 5, w: 3000, h: 50 }, { x: 0, y: 0, w: 1440, h: 900 }), { x: 0, y: 5, w: 1440, h: 50 })
  })
  test('right of the circle when it fits', () => {
    const p = placeCard({ x: 200, y: 300, w: 200, h: 100 }, { w: 300, h: 140 }, area)
    assert.equal(p.side, 'right')
    assert.equal(p.x, 200 + 200 + 14)
    assert.equal(p.y, 300 + 50 - 70)
  })
  test('left when the right edge is too close', () => {
    const p = placeCard({ x: 1200, y: 300, w: 200, h: 100 }, { w: 300, h: 140 }, area)
    assert.equal(p.side, 'left')
    assert.equal(p.x, 1200 - 14 - 300)
  })
  test('below when the circle is nearly screen wide', () => {
    const p = placeCard({ x: 40, y: 100, w: 1360, h: 200 }, { w: 300, h: 140 }, area)
    assert.equal(p.side, 'below')
  })
  test('always inside the screen edges, even when no side fits', () => {
    for (const box of [{ x: 0, y: 0, w: 1440, h: 900 }, { x: 1400, y: 880, w: 40, h: 20 }, { x: 0, y: 0, w: 20, h: 20 }, { x: 600, y: 860, w: 300, h: 40 }]) {
      const card = { w: 300, h: 220 }
      const p = placeCard(box, card, area)
      assert.ok(p.x >= 16 && p.y >= 16, JSON.stringify({ box, p }))
      assert.ok(p.x + card.w <= area.w - 16 && p.y + card.h <= area.h - 16, JSON.stringify({ box, p }))
    }
  })
})

describe('the state machine', () => {
  const run = () => {
    let now = 1000
    let n = 0
    let s: CircleState = IDLE
    const asks: { askId: string; text: string }[] = []
    const out: { claimed: boolean[]; timedOut: number } = { claimed: [], timedOut: 0 }
    const ctx = (): Ctx => ({ now, width: 1440, height: 900, newId: () => `a${++n}` })
    const go = (e: CircleEvent): CircleState => {
      const r = step(s, e, ctx())
      s = r.state
      if (r.ask) asks.push({ askId: r.ask.askId, text: r.ask.text })
      out.claimed.push(!!r.claimed)
      if (r.timedOut) out.timedOut++
      return s
    }
    const drawLoop = (): void => {
      const pts = loop(400, 300, 200, 120)
      go({ t: 'down', p: pts[0] })
      for (const p of pts.slice(1)) go({ t: 'move', p })
      go({ t: 'up' })
    }
    return { go, drawLoop, asks, out, get s() { return s }, wait: (ms: number) => (now += ms) }
  }

  test('a hold arms the circle and makes the overlay interactive; nothing else does', () => {
    const m = run()
    assert.equal(interactive(m.s), false)
    m.go({ t: 'ptt', phase: 'arming', id: 's1' })
    assert.equal(m.s.k, 'armed')
    assert.equal(interactive(m.s), true)
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    assert.equal(m.s.k, 'armed')
  })

  test('draw, speak, release: one ask with the words, and push to talk does not route them', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.drawLoop()
    m.go({ t: 'ptt', phase: 'sending', id: 's1' })
    assert.equal(m.s.k, 'sealed')
    assert.equal(interactive(m.s), false)
    m.go({ t: 'final', id: 's1', text: 'what does this do' })
    assert.equal(m.out.claimed.at(-1), true)
    assert.deepEqual(m.asks, [{ askId: 'a1', text: 'what does this do' }])
    assert.equal(m.s.k, 'asking')
    m.go({ t: 'ptt', phase: 'idle' })
    assert.equal(m.asks.length, 1)
  })

  test('the final can come before the state change', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.drawLoop()
    m.go({ t: 'final', id: 's1', text: 'and this?' })
    assert.equal(m.out.claimed.at(-1), true)
    assert.equal(m.asks.length, 0)
    m.go({ t: 'ptt', phase: 'idle' })
    assert.deepEqual(m.asks.map((a) => a.text), ['and this?'])
  })

  test('nothing said: "What is this?"', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.drawLoop()
    m.go({ t: 'ptt', phase: 'idle', lastCancel: 'empty' })
    assert.deepEqual(m.asks.map((a) => a.text), [DEFAULT_ASK])
  })

  test('over with no final in time: "What is this?" after the wait', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.drawLoop()
    m.go({ t: 'ptt', phase: 'idle' })
    assert.equal(m.s.k, 'sealed')
    m.wait(WORDS_WAIT_MS - 1)
    m.go({ t: 'tick' })
    assert.equal(m.asks.length, 0)
    m.wait(2)
    m.go({ t: 'tick' })
    assert.deepEqual(m.asks.map((a) => a.text), [DEFAULT_ASK])
  })

  test('a hold with no ink is plain push to talk', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.go({ t: 'final', id: 's1', text: 'just a question' })
    assert.equal(m.out.claimed.at(-1), false)
    m.go({ t: 'ptt', phase: 'idle' })
    assert.equal(m.s.k, 'idle')
    assert.equal(m.asks.length, 0)
  })

  test('a click (no real circle) is plain push to talk too', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.go({ t: 'down', p: { x: 10, y: 10 } })
    m.go({ t: 'up' })
    m.go({ t: 'ptt', phase: 'sending', id: 's1' })
    assert.equal(m.s.k, 'idle')
  })

  test('Esc cancels at every stage and the overlay lets go', () => {
    for (const at of ['armed', 'sealed', 'asking', 'answered'] as const) {
      const m = run()
      m.go({ t: 'ptt', phase: 'listening', id: 's1' })
      m.drawLoop()
      if (at !== 'armed') m.go({ t: 'ptt', phase: 'sending', id: 's1' })
      if (at === 'asking' || at === 'answered') m.go({ t: 'final', id: 's1', text: 'x' })
      if (at === 'answered') m.go({ t: 'answer', askId: 'a1', answer: { body: 'y' } })
      assert.equal(m.s.k, at)
      m.go({ t: 'cancel' })
      assert.equal(m.s.k, 'idle')
      assert.equal(interactive(m.s), false)
    }
  })

  test("push to talk's Esc drops the circle", () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.drawLoop()
    m.go({ t: 'ptt', phase: 'idle', lastCancel: 'esc' })
    assert.equal(m.s.k, 'idle')
    assert.equal(m.asks.length, 0)
  })

  test('an error drops the hold', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.drawLoop()
    m.go({ t: 'ptt', phase: 'error' })
    assert.equal(m.s.k, 'idle')
  })

  test('blur gives the mouse back; the ink waits for the words', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.drawLoop()
    m.go({ t: 'blur' })
    assert.equal(interactive(m.s), false)
    assert.equal(m.s.k, 'sealed')
    m.go({ t: 'final', id: 's1', text: 'what is it' })
    assert.deepEqual(m.asks.map((a) => a.text), ['what is it'])
  })

  test('blur with no ink: back to rest', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.go({ t: 'blur' })
    assert.equal(m.s.k, 'idle')
  })

  test('the 8 s cap gives the mouse back, even mid-stroke', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.go({ t: 'down', p: { x: 100, y: 100 } })
    m.go({ t: 'move', p: { x: 300, y: 200 } })
    m.wait(ARMED_MAX_MS - 1)
    m.go({ t: 'tick' })
    assert.equal(interactive(m.s), true)
    m.wait(1)
    m.go({ t: 'tick' })
    assert.equal(interactive(m.s), false)
    // Moves after the cap draw nothing.
    m.go({ t: 'move', p: { x: 900, y: 800 } })
    assert.equal(m.s.k, 'sealed')
    if (m.s.k === 'sealed') assert.ok(m.s.box.x + m.s.box.w < 900)
  })

  test('the answer is matched by askId; another askId is ignored', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.drawLoop()
    m.go({ t: 'ptt', phase: 'idle', lastCancel: 'empty' })
    m.go({ t: 'answer', askId: 'other', answer: { body: 'no' } })
    assert.equal(m.s.k, 'asking')
    m.go({ t: 'answer', askId: 'a1', answer: { title: 'T', body: 'yes' } })
    assert.equal(m.s.k, 'answered')
    if (m.s.k === 'answered') assert.deepEqual(m.s.answer, { title: 'T', body: 'yes' })
  })

  test('an older engine (no askId) answers in the island; the ink goes', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.drawLoop()
    m.go({ t: 'ptt', phase: 'idle', lastCancel: 'empty' })
    m.go({ t: 'answer', answer: { body: 'plain' } })
    assert.equal(m.s.k, 'idle')
  })

  test('no answer in time: the ink goes and the store is told', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.drawLoop()
    m.go({ t: 'ptt', phase: 'idle', lastCancel: 'short' })
    m.wait(ASK_MAX_MS)
    m.go({ t: 'tick' })
    assert.equal(m.s.k, 'idle')
    assert.equal(m.out.timedOut, 1)
  })

  test('an answer goes by itself after a while, and a new hold replaces it', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m.drawLoop()
    m.go({ t: 'ptt', phase: 'idle', lastCancel: 'empty' })
    m.go({ t: 'answer', askId: 'a1', answer: { body: 'b' } })
    m.go({ t: 'ptt', phase: 'arming', id: 's2' })
    assert.equal(m.s.k, 'armed')
    if (m.s.k === 'armed') assert.equal(m.s.strokes.length, 0)

    const m2 = run()
    m2.go({ t: 'ptt', phase: 'listening', id: 's1' })
    m2.drawLoop()
    m2.go({ t: 'ptt', phase: 'idle', lastCancel: 'empty' })
    m2.go({ t: 'answer', askId: 'a1', answer: { body: 'b' } })
    m2.wait(ANSWER_MS)
    m2.go({ t: 'tick' })
    assert.equal(m2.s.k, 'idle')
  })

  test('a stale final from another session changes nothing', () => {
    const m = run()
    m.go({ t: 'ptt', phase: 'listening', id: 's2' })
    m.drawLoop()
    m.go({ t: 'ptt', phase: 'sending', id: 's2' })
    m.go({ t: 'final', id: 's1', text: 'ghost' })
    assert.equal(m.out.claimed.at(-1), false)
    assert.equal(m.s.k, 'sealed')
  })

  test('pointer input outside a hold draws nothing', () => {
    const m = run()
    m.go({ t: 'down', p: { x: 1, y: 1 } })
    m.go({ t: 'move', p: { x: 100, y: 100 } })
    assert.equal(m.s.k, 'idle')
  })
})
