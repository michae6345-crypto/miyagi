/**
 * features/circle, offline and pure: the early capture's timing rules (capture.ts) and the streamed answer's assembly
 * (machine.ts, answer.delta). No bridge, no timers: the capture's promises are settled by hand.
 */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import type { ScreenRegion } from '../../shared/contracts/events'
import type { CaptureResult } from '../src/main/pttProtocol'
import { createCaptureTracker, sameRegion } from '../src/renderer/src/features/circle/capture'
import { ASK_MAX_MS, IDLE, shown, step, type CircleState, type Ctx } from '../src/renderer/src/features/circle/machine'

// ---- the capture ----

const REGION: ScreenRegion = { x: 100, y: 200, w: 300, h: 120, displayId: 7, scale: 2 }
const okFor = (id: string): CaptureResult => ({ ok: true, id, path: `/private/tmp/miyagi/cap-${id.replace('cap-', 'abcdef0')}.jpg`, w: 690, h: 276, pxPerPoint: 2, rect: { x: 55, y: 182, w: 345, h: 138 }, displayId: 7, ms: 120 })
const fail = (id: string): CaptureResult => ({ ok: false, id, error: 'timeout', message: 'The capture took too long.' })

/** A fake main: each capture waits until the test settles it. */
function rig(): { t: ReturnType<typeof createCaptureTracker>; asked: ScreenRegion[]; released: string[]; settle: (i: number, r: CaptureResult | Error) => Promise<void> } {
  const asked: ScreenRegion[] = []
  const released: string[] = []
  const pending: { resolve: (r: CaptureResult) => void; reject: (e: Error) => void }[] = []
  const t = createCaptureTracker({
    capture: (region) => {
      asked.push(region)
      return new Promise<CaptureResult>((resolve, reject) => pending.push({ resolve, reject }))
    },
    release: (id) => void released.push(id)
  })
  const settle = async (i: number, r: CaptureResult | Error): Promise<void> => {
    if (r instanceof Error) pending[i].reject(r)
    else pending[i].resolve(r)
    await new Promise((done) => setImmediate(done))
  }
  return { t, asked, released, settle }
}

describe('the early capture', () => {
  test('settled ok before release, same region: it goes with the ask, and nothing is released', async () => {
    const { t, asked, released, settle } = rig()
    t.begin(REGION)
    assert.deepEqual(asked, [REGION], 'asked at once, at the stroke')
    assert.equal(t.peek(), 'pending')
    await settle(0, okFor('cap-1'))
    assert.equal(t.peek(), 'ok')
    const cap = t.take({ ...REGION, scale: 1 }) // the scale is not part of what was captured
    assert.deepEqual(cap, { path: '/private/tmp/miyagi/cap-abcdef01.jpg', w: 690, h: 276, rect: { x: 55, y: 182, w: 345, h: 138 }, displayId: 7 })
    assert.deepEqual(released, [], 'the engine deletes a sent file')
    assert.equal(t.peek(), 'none')
    assert.equal(t.take(REGION), undefined, 'a capture goes with one ask only')
  })

  test('still pending at release: no capture, release never waits, and the late file is released', async () => {
    const { t, released, settle } = rig()
    t.begin(REGION)
    assert.equal(t.take(REGION), undefined)
    await settle(0, okFor('cap-2'))
    assert.deepEqual(released, ['cap-2'])
  })

  test('the region changed after the capture (another stroke not yet done, a moved window): not sent, released', async () => {
    const { t, released, settle } = rig()
    t.begin(REGION)
    await settle(0, okFor('cap-3'))
    assert.equal(t.take({ ...REGION, w: REGION.w + 40 }), undefined)
    assert.deepEqual(released, ['cap-3'])
    t.begin(REGION)
    await settle(1, okFor('cap-4'))
    assert.equal(t.take({ ...REGION, displayId: 8 }), undefined, 'another display is another region')
    assert.deepEqual(released, ['cap-3', 'cap-4'])
  })

  test('only the newest counts: a newer stroke releases the older ok, and an older one settling late is released', async () => {
    const { t, asked, released, settle } = rig()
    const wider = { ...REGION, w: 360 }
    t.begin(REGION)
    await settle(0, okFor('cap-5'))
    t.begin(wider)
    assert.deepEqual(released, ['cap-5'], 'the older ok one goes as the newer starts')
    t.begin({ ...wider, h: 150 })
    await settle(1, okFor('cap-6')) // the middle one settles after the newest began: stale
    assert.deepEqual(released, ['cap-5', 'cap-6'])
    await settle(2, okFor('cap-7'))
    assert.equal(asked.length, 3)
    assert.ok(t.take({ ...wider, h: 150 }), 'the newest goes with the ask')
    assert.deepEqual(released, ['cap-5', 'cap-6'])
  })

  test('a failure (an error answer or a thrown invoke) is no capture, and nothing to release', async () => {
    const { t, released, settle } = rig()
    t.begin(REGION)
    await settle(0, fail('cap-8'))
    assert.equal(t.peek(), 'failed')
    assert.equal(t.take(REGION), undefined)
    t.begin(REGION)
    await settle(1, new Error('untrusted sender'))
    assert.equal(t.peek(), 'failed')
    assert.equal(t.take(REGION), undefined)
    const sync = createCaptureTracker({
      capture: () => {
        throw new Error('no web handler')
      },
      release: (id) => void released.push(id)
    })
    sync.begin(REGION)
    assert.equal(sync.peek(), 'failed')
    assert.deepEqual(released, [])
  })

  test('drop (Esc, offline, a new hold) releases an ok capture now, and a pending one when it settles', async () => {
    const { t, released, settle } = rig()
    t.begin(REGION)
    await settle(0, okFor('cap-9'))
    t.drop()
    assert.deepEqual(released, ['cap-9'])
    t.begin(REGION)
    t.drop()
    await settle(1, okFor('cap-10'))
    assert.deepEqual(released, ['cap-9', 'cap-10'])
    assert.equal(t.peek(), 'none')
  })

  test('sameRegion: points and display, not scale', () => {
    assert.ok(sameRegion(REGION, { ...REGION, scale: 1 }))
    assert.ok(!sameRegion(REGION, { ...REGION, x: 101 }))
  })
})

// ---- the streamed answer ----

let now = 1_000
const ctx = (): Ctx => ({ now, width: 1440, height: 900, newId: () => 'never' })
const asking = (askId = 'a1'): CircleState => ({ k: 'asking', session: 's1', askId, since: now, strokes: [[{ x: 10, y: 10 }]], box: { x: 0, y: 0, w: 50, h: 50 }, text: 'What is this?' })
const feedAll = (s: CircleState, ...ds: { askId: string; text: string; done?: boolean }[]): CircleState => ds.reduce((st, d) => step(st, { t: 'delta', ...d }, ctx()).state, s)

describe('the streamed answer (answer.delta)', () => {
  test('pieces add up in arrival order; leading space is not shown', () => {
    const s = feedAll(asking(), { askId: 'a1', text: ' Each pass' }, { askId: 'a1', text: ' runs the model.' })
    assert.equal(s.k, 'asking')
    assert.equal(shown(s), 'Each pass runs the model.')
    assert.equal(s.k === 'asking' && s.stream?.done, false)
  })

  test('nothing yet, or only space: still "Looking" (nothing shown)', () => {
    assert.equal(shown(asking()), '')
    assert.equal(shown(feedAll(asking(), { askId: 'a1', text: '  ' })), '')
    const s0 = asking()
    assert.equal(feedAll(s0, { askId: 'a1', text: '' }), s0, 'an empty piece that is not the last changes nothing')
  })

  test('another askId is dropped (an older ask, a closed one)', () => {
    const s0 = asking('a2')
    const s = feedAll(s0, { askId: 'a1', text: 'old words' })
    assert.equal(s, s0)
    assert.equal(shown(s), '')
  })

  test('done ends the stream: its own text counts, anything after it is dropped', () => {
    const s = feedAll(asking(), { askId: 'a1', text: 'One.' }, { askId: 'a1', text: ' Two.', done: true }, { askId: 'a1', text: ' Three.' })
    assert.equal(shown(s), 'One. Two.')
    assert.equal(s.k === 'asking' && s.stream?.done, true)
    const empty = feedAll(asking(), { askId: 'a1', text: 'One.' }, { askId: 'a1', text: '', done: true })
    assert.equal(shown(empty), 'One.')
  })

  test('out of order with the card: the card replaces the stream, and a delta after the card is dropped', () => {
    const streamed = feedAll(asking(), { askId: 'a1', text: 'Draft words' })
    const answered = step(streamed, { t: 'answer', askId: 'a1', answer: { title: 'T', body: 'Clean words.' } }, ctx()).state
    assert.equal(answered.k, 'answered')
    assert.equal(answered.k === 'answered' && answered.answer.body, 'Clean words.')
    assert.equal(feedAll(answered, { askId: 'a1', text: ' late' }), answered)
  })

  test('a delta before the ask is on screen (armed, sealed, idle) is dropped', () => {
    const armed: CircleState = { k: 'armed', session: 's1', since: now, strokes: [], down: false }
    assert.equal(feedAll(armed, { askId: 'a1', text: 'x' }), armed)
    assert.equal(feedAll(IDLE, { askId: 'a1', text: 'x' }), IDLE)
  })

  test('Esc or a new hold drops the stream', () => {
    const streamed = feedAll(asking(), { askId: 'a1', text: 'Words' })
    assert.equal(step(streamed, { t: 'cancel' }, ctx()).state, IDLE)
    const next = step(streamed, { t: 'ptt', phase: 'listening', id: 's2' }, ctx()).state
    assert.equal(next.k, 'armed')
    assert.equal(shown(next), '')
  })

  test('the ask timeout counts from the newest words, and words with no card become the answer', () => {
    const start = now
    let s = feedAll(asking(), { askId: 'a1', text: 'Half an answer' })
    now = start + ASK_MAX_MS - 10
    s = feedAll(s, { askId: 'a1', text: ', more' })
    now = start + ASK_MAX_MS + 10
    assert.equal(step(s, { t: 'tick' }, ctx()).state.k, 'asking', 'still streaming: no timeout')
    now = start + 2 * ASK_MAX_MS
    const r = step(s, { t: 'tick' }, ctx())
    assert.equal(r.state.k, 'answered')
    assert.equal(r.timedOut, undefined, 'no "No answer yet" over words already shown')
    assert.equal(r.state.k === 'answered' && r.state.answer.body, 'Half an answer, more')
    now = start
    const silent = asking()
    now = start + ASK_MAX_MS
    const t = step(silent, { t: 'tick' }, ctx())
    assert.equal(t.state, IDLE)
    assert.equal(t.timedOut, true)
    now = 1_000
  })
})
