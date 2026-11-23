/**
 * Push to talk speed, offline: the wake-word strip (features/ptt/wake.ts), the release tail's safety net with a fake clock
 * (features/ptt/tail.ts), and the store's seams for circle to ask (onPttDown, onPttPartial, the tail's final going out
 * once, the helper's late final not asked twice) with a fake Electron bridge.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'
import type { PttState } from '../src/common/pttState'
import { createTail, HELPER_TAIL_MAX_MS, meaningful, SAFETY_MS, type TailClock, type TailView } from '../src/renderer/src/features/ptt/tail'
import { stripWake } from '../src/renderer/src/features/ptt/wake'

describe('stripWake', () => {
  test('a greeting and miyagi go, the question stays (first letter up)', () => {
    assert.equal(stripWake('Hey Miyagi, what is this error?'), 'What is this error?')
    assert.equal(stripWake('hey miyagi what is this'), 'What is this')
    assert.equal(stripWake('OK miyagi. Explain this line'), 'Explain this line')
    assert.equal(stripWake('hi, miyagi: why'), 'Why')
    assert.equal(stripWake('Miyagi, how do I import numpy'), 'How do I import numpy')
    assert.equal(stripWake('  miyagi   what now'), 'What now')
    assert.equal(stripWake('Hey Mr. Miyagi, what is this'), 'What is this')
    assert.equal(stripWake('mi yagi what is this'), 'What is this')
  })
  test('only the wake word leaves nothing', () => {
    for (const t of ['Hey Miyagi', 'miyagi', 'Miyagi?', 'hey miyagi!', 'Hey Miyagi,']) assert.equal(stripWake(t), '')
  })
  test('miyagi later in the sentence, a possessive, or a longer word stays', () => {
    assert.equal(stripWake('what does miyagi do here'), 'what does miyagi do here')
    assert.equal(stripWake("Miyagi's answer was wrong"), "Miyagi's answer was wrong")
    assert.equal(stripWake('miyagistyle is a word'), 'miyagistyle is a word')
    assert.equal(stripWake('hey what is this'), 'hey what is this')
    assert.equal(stripWake('  plain question  '), 'plain question')
    assert.equal(stripWake(''), '')
  })
  test('meaningful looks past the wake word', () => {
    assert.equal(meaningful('Hey Miyagi'), false)
    assert.equal(meaningful('Hey Miyagi, why'), true)
    assert.equal(meaningful('a'), false)
  })
})

/** A clock the test moves by hand. */
function fakeClock(): TailClock & { tick(ms: number): void } {
  let now = 1000
  let timers: { at: number; fn: () => void; h: number }[] = []
  let next = 1
  return {
    now: () => now,
    set: (fn, ms) => {
      const h = next++
      timers.push({ at: now + ms, fn, h })
      return h
    },
    clear: (h) => void (timers = timers.filter((t) => t.h !== h)),
    tick(ms) {
      const end = now + ms
      for (;;) {
        const due = timers.filter((t) => t.at <= end).sort((a, b) => a.at - b.at)[0]
        if (!due) break
        timers = timers.filter((t) => t !== due)
        now = due.at
        due.fn()
      }
      now = end
    }
  }
}

const view = (phase: PttState['phase'], id: string | undefined, text = '', released = false): TailView => ({ phase, id, text, released })

describe("the release tail's safety net (fake clock)", () => {
  test('released with words and no final from the helper: the last partial goes out SAFETY_MS after the last new text', () => {
    const clock = fakeClock()
    const out: { id: string; text: string }[] = []
    const tail = createTail((f) => out.push(f), { clock })
    tail.observe(view('arming', 'a'))
    clock.tick(260)
    tail.observe(view('listening', 'a'))
    tail.observe(view('listening', 'a', 'why does'))
    clock.tick(900)
    tail.observe(view('sending', 'a', 'why does the loss', true)) // the keys came up
    clock.tick(120)
    tail.observe(view('sending', 'a', 'why does the loss go down', true)) // a partial during the tail: the timer restarts
    clock.tick(SAFETY_MS - 1)
    tail.observe(view('sending', 'a', 'why does the loss go down', true)) // the same text again does not restart it
    assert.deepEqual(out, [], 'not before the tail')
    clock.tick(1)
    assert.deepEqual(out, [{ id: 'a', text: 'why does the loss go down' }])
    const t = tail.timing()
    assert.equal(t?.via, 'tail')
    assert.equal(t?.releaseToFinalMs, 120 + SAFETY_MS)
    assert.equal(t?.finalAt! - t?.downAt!, 260 + 900 + 120 + SAFETY_MS)
    clock.tick(5000)
    assert.equal(out.length, 1, 'once')
  })

  test("the helper's final first: the tail stays quiet and the timing says helper", () => {
    const clock = fakeClock()
    const out: unknown[] = []
    const tail = createTail((f) => out.push(f), { clock })
    tail.observe(view('arming', 'b'))
    tail.observe(view('listening', 'b', 'how do I'))
    clock.tick(500)
    tail.observe(view('sending', 'b', 'how do I import', true))
    clock.tick(80)
    const t = tail.final('b', 'helper')
    tail.observe(view('idle', undefined))
    clock.tick(1000)
    assert.deepEqual(out, [])
    assert.equal(t?.via, 'helper')
    assert.equal(t?.releaseToFinalMs, 80)
  })

  test('no words yet (the recognizer was still starting): the tail waits for the helper', () => {
    const clock = fakeClock()
    const out: unknown[] = []
    const tail = createTail((f) => out.push(f), { clock })
    tail.observe(view('arming', 'c'))
    clock.tick(300)
    tail.observe(view('arming', 'c', '', true)) // released while the mic was opening
    clock.tick(40)
    tail.observe(view('sending', 'c', '', true))
    clock.tick(SAFETY_MS * 3)
    assert.deepEqual(out, [])
    assert.equal(tail.timing()?.upAt, 1300, 'the release is timed from the key-up, not from sending')
    tail.final('c', 'helper')
    assert.equal(tail.timing()?.releaseToFinalMs, 40 + SAFETY_MS * 3)
  })

  test('only a wake word so far is not worth sending', () => {
    const clock = fakeClock()
    const out: unknown[] = []
    const tail = createTail((f) => out.push(f), { clock })
    tail.observe(view('arming', 'w'))
    tail.observe(view('sending', 'w', 'Hey Miyagi', true))
    clock.tick(SAFETY_MS)
    assert.deepEqual(out, [])
  })

  test('a cancel or a new hold stops the timer', () => {
    const clock = fakeClock()
    const out: { id: string; text: string }[] = []
    const tail = createTail((f) => out.push(f), { clock })
    tail.observe(view('sending', 'd', 'first words', true))
    tail.observe(view('idle', undefined)) // cancelled
    clock.tick(SAFETY_MS)
    tail.observe(view('sending', 'e', 'other words', true))
    tail.observe(view('arming', 'f')) // a new hold before the tail ran out
    clock.tick(SAFETY_MS)
    assert.deepEqual(out, [])
  })

  test("the net is never shorter than the helper's worst case plus slack, whatever is asked; paused, it never sends", () => {
    assert.ok(SAFETY_MS >= HELPER_TAIL_MAX_MS + 400)
    const clock = fakeClock()
    const out: unknown[] = []
    const tail = createTail((f) => out.push(f), { clock, tailMs: 300 })
    tail.observe(view('sending', 'g', 'what is this', true))
    clock.tick(SAFETY_MS - 1)
    assert.equal(out.length, 0, 'a short tailMs is raised to SAFETY_MS')
    clock.tick(1)
    assert.equal(out.length, 1)
    const paused = createTail((f) => out.push(f), { clock })
    paused.pause(true)
    paused.observe(view('sending', 'h', 'what is this', true))
    clock.tick(SAFETY_MS * 2)
    assert.equal(out.length, 1)
  })

  // The helper's own tail: the final the moment it comes (about 65 ms), else its cap: 1000 ms, up to HELPER_TAIL_MAX_MS
  // after a cold-start flush. Its final reaches the renderer some ms later; it must win, not the last partial the
  // renderer already has.
  for (const helperMs of [65 + 20, 1000 + 20, HELPER_TAIL_MAX_MS + 20]) {
    test(`the helper's final at ${helperMs} ms after release (its tail + 20 ms of IPC) wins over the net`, () => {
      const clock = fakeClock()
      const out: { id: string; text: string }[] = []
      const tail = createTail((f) => out.push(f), { clock })
      tail.observe(view('arming', 'r'))
      tail.observe(view('listening', 'r', 'why does the'))
      clock.tick(700)
      tail.observe(view('sending', 'r', 'why does the loss', true)) // the keys came up; the last partial lacks the end
      clock.tick(helperMs)
      assert.deepEqual(out, [], 'the net has not fired')
      const t = tail.final('r', 'helper') // the helper's final, with the last words
      tail.observe(view('idle', undefined))
      clock.tick(SAFETY_MS * 2)
      assert.deepEqual(out, [], 'and never does for this hold')
      assert.equal(t?.via, 'helper')
      assert.equal(t?.releaseToFinalMs, helperMs)
    })
  }

  // A cold start: the recognizer gets ready after the release, so the helper's tail (counted from then) can end well
  // past SAFETY_MS after the key-up. Its first partial is the sign it is ready; the net counts from that.
  test("a cold start: the recognizer is ready 1000 ms after release, the helper's final at 2050 ms still wins", () => {
    const clock = fakeClock()
    const out: { id: string; text: string }[] = []
    const tail = createTail((f) => out.push(f), { clock })
    tail.observe(view('arming', 'k'))
    clock.tick(300)
    tail.observe(view('listening', 'k'))
    clock.tick(800)
    tail.observe(view('sending', 'k', '', true)) // the keys came up: t = 0, no words yet
    clock.tick(1000)
    tail.observe(view('sending', 'k', 'what does this', true)) // the recognizer is ready: its first partial
    clock.tick(900) // t = 1900: SAFETY_MS after the key-up, where the old net fired
    assert.deepEqual(out, [], 'the net does not fire SAFETY_MS after the key-up')
    clock.tick(150) // t = 2050: the helper's final (ready + its cap + IPC), with the last words
    const t = tail.final('k', 'helper')
    tail.observe(view('idle', undefined))
    clock.tick(SAFETY_MS * 2)
    assert.deepEqual(out, [], 'the partial was never routed, so the dedupe keeps the helper final')
    assert.equal(t?.via, 'helper')
    assert.equal(t?.releaseToFinalMs, 2050)
  })

  test('a cold start with no final from the helper: the net fires SAFETY_MS after the last partial, past the helper cap', () => {
    const clock = fakeClock()
    const out: { id: string; text: string }[] = []
    const tail = createTail((f) => out.push(f), { clock })
    tail.observe(view('arming', 'm'))
    tail.observe(view('listening', 'm'))
    tail.observe(view('sending', 'm', '', true)) // t = 0
    clock.tick(1000)
    tail.observe(view('sending', 'm', 'what does', true)) // ready at t = 1000: the helper cap ends by 1000 + HELPER_TAIL_MAX_MS
    clock.tick(200)
    tail.observe(view('sending', 'm', 'what does this do', true))
    clock.tick(SAFETY_MS - 1)
    assert.deepEqual(out, [])
    assert.ok(clock.now() - tail.timing()!.upAt! > 1000 + HELPER_TAIL_MAX_MS, "already past the helper's latest final")
    clock.tick(1)
    assert.deepEqual(out, [{ id: 'm', text: 'what does this do' }])
    assert.equal(tail.timing()?.releaseToFinalMs, 1200 + SAFETY_MS)
  })
})

// ---- the store, with a fake Electron bridge ----

const dir = mkdtempSync(join(tmpdir(), 'ptt-stream-'))
const stub = (name: string, source: string): string => (writeFileSync(join(dir, name), source), pathToFileURL(join(dir, name)).href)
const EMPTY = stub('empty.mjs', 'export const scenarios = {}\nexport const defineFeature = (f) => f\nexport default ""')
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier) || (context.parentURL?.includes('/src/renderer/') && /(^|\/)registry$/.test(specifier))) return { url: EMPTY, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})

const sends: { type: string; payload: Record<string, unknown> }[] = []
const features = new Map<string, (p: unknown) => void>()
const g = globalThis as unknown as Record<string, unknown>
const noop = (): (() => void) => () => {}
g.window = {
  tut: {
    platform: { os: 'darwin', keys: { ptt: 'fn ⌃' }, pillTop: 0 },
    onEvent: noop,
    onStatus: noop,
    on: noop,
    onFeature: (channel: string, cb: (p: unknown) => void) => (features.set(channel, cb), () => features.delete(channel)),
    emit: () => {},
    ready: () => {},
    send: (m: { type: string; payload: Record<string, unknown> }) => void sends.push(m),
    invoke: () => Promise.resolve(null)
  },
  devicePixelRatio: 2,
  innerWidth: 1440,
  innerHeight: 900,
  addEventListener: () => {},
  removeEventListener: () => {},
  matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} })
}
g.document = { documentElement: { dataset: { route: 'overlay' } }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined }, addEventListener: () => {}, hidden: false }
g.location = { search: '' }

const { useLesson } = require('../src/renderer/src/core/lesson') as typeof import('../src/renderer/src/core/lesson')
const { PTT_REST } = require('../src/common/pttState') as typeof import('../src/common/pttState')
const store = require('../src/renderer/src/features/ptt/store') as typeof import('../src/renderer/src/features/ptt/store')

const state = (phase: PttState['phase'], id: string | undefined, text = '', released = false): PttState => ({ ...PTT_REST, available: true, phase, id, text, released })
const feat = (channel: string, payload: unknown): void => features.get(channel)!(payload)
const asks = (): string[] => sends.filter((m) => m.type === 'action' && m.payload.kind === 'ask').map((m) => String(m.payload.text))

describe('ptt store: the seams and the tail (fake Electron bridge)', () => {
  beforeEach(() => {
    mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'], now: 50_000 })
    sends.length = 0
    useLesson.setState({ connected: true, lesson: { id: 'l', title: 'L' } as never, stepId: 's1' })
    store.receive(PTT_REST)
  })
  afterEach(() => {
    store.receive(PTT_REST)
    mock.timers.reset()
  })

  test('main broadcasts reach onPttDown and onPttPartial (wake word dropped, other holds ignored); unsubscribe works', () => {
    const downs: string[] = []
    const parts: string[] = []
    const offD = store.onPttDown((d) => downs.push(d.id))
    const offP = store.onPttPartial((p) => parts.push(`${p.id}:${p.text}`))
    store.receive(state('arming', 'k1'))
    feat('ptt:down', { id: 'k1' })
    store.receive(state('listening', 'k1', 'Hey Miyagi, what'))
    feat('ptt:partial', { id: 'k1', text: 'Hey Miyagi, what' })
    feat('ptt:partial', { id: 'old', text: 'ghost words' })
    feat('ptt:partial', { id: 'k1', text: 42 })
    offD()
    offP()
    feat('ptt:down', { id: 'k2' })
    feat('ptt:partial', { id: 'k1', text: 'after unsubscribe' })
    assert.deepEqual(downs, ['k1'])
    assert.deepEqual(parts, ['k1:What'])
  })

  test('released and no final from the helper: the net asks the last partial once, SAFETY_MS after the key-up; a late final is not asked again', () => {
    store.receive(state('arming', 'm1'))
    store.receive(state('listening', 'm1', 'hey miyagi why does the loss'))
    mock.timers.tick(800)
    store.receive(state('sending', 'm1', 'hey miyagi why does the loss go down', true))
    mock.timers.tick(SAFETY_MS - 1)
    assert.deepEqual(asks(), [])
    mock.timers.tick(1)
    assert.deepEqual(asks(), ['Why does the loss go down'])
    assert.equal(store.usePtt.getState().owned, false, 'the island lets go at once')
    assert.equal(store.pttTiming()?.via, 'tail')
    assert.equal(store.pttTiming()?.releaseToFinalMs, SAFETY_MS)
    // The helper's final for the same hold, later: no second ask, and the island does not claim it again.
    store.receive(state('sending', 'm1', 'hey miyagi why does the loss go down', true))
    assert.equal(store.usePtt.getState().owned, false)
    feat('ptt:final', { id: 'm1', text: 'Hey Miyagi, why does the loss go down?' })
    store.receive(PTT_REST)
    assert.deepEqual(asks(), ['Why does the loss go down'])
  })

  test("the helper's final inside the tail wins and is asked once, wake word dropped", () => {
    store.receive(state('arming', 'n1'))
    store.receive(state('listening', 'n1', 'miyagi what is'))
    store.receive(state('sending', 'n1', 'miyagi what is', true))
    mock.timers.tick(90)
    feat('ptt:final', { id: 'n1', text: 'Miyagi, what is this?' })
    store.receive(PTT_REST)
    mock.timers.tick(1000)
    assert.deepEqual(asks(), ['What is this?'])
    assert.equal(store.pttTiming()?.via, 'helper')
    assert.equal(store.pttTiming()?.releaseToFinalMs, 90)
  })

  test("the helper's final at its worst-case tail + 20 ms wins: its words are asked, not the last partial", () => {
    store.receive(state('arming', 'q1'))
    store.receive(state('listening', 'q1', 'why is my tensor'))
    mock.timers.tick(900)
    store.receive(state('sending', 'q1', 'why is my tensor flow', true))
    mock.timers.tick(HELPER_TAIL_MAX_MS + 20)
    assert.deepEqual(asks(), [], 'the net is still waiting')
    feat('ptt:final', { id: 'q1', text: 'Why is my TensorFlow loss NaN?' })
    store.receive(PTT_REST)
    mock.timers.tick(SAFETY_MS * 2)
    assert.deepEqual(asks(), ['Why is my TensorFlow loss NaN?'])
    assert.equal(store.pttTiming()?.via, 'helper')
  })

  test('saying only the wake word asks nothing', () => {
    store.receive(state('arming', 'p1'))
    store.receive(state('sending', 'p1', 'Hey Miyagi', true))
    mock.timers.tick(SAFETY_MS * 2)
    feat('ptt:final', { id: 'p1', text: 'Hey Miyagi.' })
    store.receive(PTT_REST)
    assert.deepEqual(asks(), [])
  })
})
