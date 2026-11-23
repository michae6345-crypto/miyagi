/**
 * features/circle/store.ts end to end with a fake Electron bridge, offline: the early capture rides on the ask only
 * when it is ready for the very region asked about (and is released otherwise), answer.delta fills the answer card as
 * it streams ("Looking" until the first words, the final card replaces it), and an early annotate mark (why "answer")
 * for this ask stays drawn through the stream and the card.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'

// Vite-only modules (import.meta.glob scenarios, the feature registry, assets) resolve to small stand-ins.
const dir = mkdtempSync(join(tmpdir(), 'circle-wire-'))
const stub = (name: string, source: string): string => (writeFileSync(join(dir, name), source), pathToFileURL(join(dir, name)).href)
const EMPTY = stub('empty.mjs', 'export const scenarios = {}\nexport const defineFeature = (f) => f\nexport default ""')
// features/cards' panel routing (import.meta.glob, the drawer) is not under test: nothing is routed to a panel.
const PANEL = stub('panel.mjs', 'export const isRouted = () => false\nexport const panelShown = () => false')
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === './panel' && context.parentURL?.includes('/features/cards/store')) return { url: PANEL, shortCircuit: true }
    if (/(^|\/)mock\/scenarios$/.test(specifier) || (context.parentURL?.includes('/src/renderer/') && /(^|\/)registry$/.test(specifier))) return { url: EMPTY, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})

type Res = Record<string, unknown> | null
const sends: { type: string; payload: Record<string, unknown> }[] = []
const captureAsks: unknown[] = []
const releases: unknown[] = []
/** Each ptt:capture waits until the test settles it. */
const pending: ((r: Res) => void)[] = []
const g = globalThis as unknown as Record<string, unknown>
const noop = (): (() => void) => () => {}
const tut = {
  platform: { os: 'darwin', keys: { ptt: 'fn ⌃' }, pillTop: 0 },
  onEvent: noop,
  onStatus: noop,
  on: noop,
  onFeature: () => () => {},
  emit: () => {},
  ready: () => {},
  send: (m: { type: string; payload: Record<string, unknown> }) => void sends.push(m),
  invoke: (channel: string, arg?: unknown): Promise<unknown> => {
    if (channel === 'ptt:capture') {
      captureAsks.push(arg)
      return new Promise((resolve) => pending.push(resolve))
    }
    if (channel === 'ptt:capture-release') releases.push(arg)
    return Promise.resolve(null)
  }
}
g.window = { tut, devicePixelRatio: 2, innerWidth: 1440, innerHeight: 900, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
g.document = { documentElement: { dataset: { route: 'overlay' } }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined }, addEventListener: () => {}, hidden: false }
g.location = { search: '' }
g.innerWidth = 1440
g.innerHeight = 900

const { dispatch } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const { parseEngineMessage } = require('../src/common/wire') as typeof import('../src/common/wire')
const { useLesson } = require('../src/renderer/src/core/lesson') as typeof import('../src/renderer/src/core/lesson')
const { PTT_REST } = require('../src/common/pttState') as typeof import('../src/common/pttState')
const { usePtt } = require('../src/renderer/src/features/ptt/store') as typeof import('../src/renderer/src/features/ptt/store')
const { useAnnotate } = require('../src/renderer/src/features/annotate/store') as typeof import('../src/renderer/src/features/annotate/store')
const circle = require('../src/renderer/src/features/circle/store') as typeof import('../src/renderer/src/features/circle/store')
const { useCards } = require('../src/renderer/src/features/cards/store') as typeof import('../src/renderer/src/features/cards/store')
const { loopPoints } = require('../src/renderer/src/features/circle/geometry') as typeof import('../src/renderer/src/features/circle/geometry')
const { ASK_MAX_MS } = require('../src/renderer/src/features/circle/machine') as typeof import('../src/renderer/src/features/circle/machine')
const { useCircle, cancelCircle, circleOwnsCard, pointerDown, pointerMove, pointerUp, setLayout, captureState } = circle
const LAYOUT = { origin: { x: 0, y: 0 }, width: 1440, height: 900, displayId: 7, scaleFactor: 2 }

const ptt = (p: Partial<typeof PTT_REST>): void => usePtt.setState({ ptt: { ...PTT_REST, available: true, ...p } })
const k = (): string => useCircle.getState().state.k
const flush = (): Promise<void> => new Promise((done) => setImmediate(done))
const stroke = (x = 400, y = 300, w = 220, h = 120): void => {
  const pts = loopPoints(x, y, w, h)
  pointerDown(pts[0])
  for (const p of pts.slice(1)) pointerMove(p)
  pointerUp()
}
let n = 0
const hold = (): string => {
  const id = `w${++n}`
  ptt({ phase: 'arming', id })
  ptt({ phase: 'listening', id })
  return id
}
/** Keys up with nothing said: the ask goes out at once ("What is this?"). */
const letGo = (id: string): void => {
  ptt({ phase: 'sending', id, released: true })
  ptt({ phase: 'idle', lastCancel: 'empty' })
}
const ask = (): Record<string, unknown> => {
  const a = sends.filter((m) => m.type === 'action').at(-1)
  assert.ok(a, 'the ask went out')
  return a.payload
}
const ok = (id: string): Res => ({ ok: true, id, path: `/private/tmp/m/cap-0000000${id.slice(-1)}.jpg`, w: 600, h: 300, pxPerPoint: 2, rect: { x: 360, y: 260, w: 300, h: 150 }, displayId: 7, ms: 90 })
const delta = (askId: unknown, text: string, done?: boolean): void => dispatch({ type: 'answer.delta', payload: { askId, text, ...(done ? { done } : {}) } } as never)

beforeEach(() => {
  mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'], now: 2_000_000 })
  ptt({ phase: 'idle' })
  cancelCircle()
  useLesson.setState({ connected: true })
  setLayout(LAYOUT)
  sends.length = 0
  captureAsks.length = 0
  releases.length = 0
  pending.length = 0
})
afterEach(() => {
  cancelCircle()
  ptt({ phase: 'idle' })
  mock.timers.reset()
})

describe('the early capture on the wire', () => {
  test('a stroke done while held asks at once; settled before release, it rides on the ask', async () => {
    const id = hold()
    stroke()
    assert.equal(captureAsks.length, 1, 'asked as the stroke closed, keys still held')
    assert.equal(k(), 'armed')
    pending[0](ok('cap-1'))
    await flush()
    letGo(id)
    const a = ask()
    const region = a.region as Record<string, number>
    assert.deepEqual(captureAsks[0], region, 'captured exactly the region asked about')
    assert.deepEqual(a.capture, { path: '/private/tmp/m/cap-00000001.jpg', w: 600, h: 300, rect: { x: 360, y: 260, w: 300, h: 150 }, displayId: 7 })
    assert.deepEqual(releases, [])
  })

  test('not settled at release: the ask goes at once without it; the late file is released', async () => {
    const id = hold()
    stroke()
    letGo(id)
    assert.equal(ask().capture, undefined)
    pending[0](ok('cap-2'))
    await flush()
    assert.deepEqual(releases, ['cap-2'])
  })

  test('a second stroke widens the circle: the newest capture counts, the older is released', async () => {
    const id = hold()
    stroke()
    pending[0](ok('cap-3'))
    await flush()
    stroke(380, 280, 300, 160)
    assert.deepEqual(releases, ['cap-3'])
    assert.equal(captureAsks.length, 2)
    pending[1](ok('cap-4'))
    await flush()
    letGo(id)
    assert.equal((ask().capture as { path: string }).path, '/private/tmp/m/cap-00000004.jpg')
  })

  test('keys up mid-stroke: the region differs from the capture, so none is sent and it is released', async () => {
    const id = hold()
    stroke()
    pending[0](ok('cap-5'))
    await flush()
    const more = loopPoints(700, 500, 200, 100)
    pointerDown(more[0])
    for (const p of more.slice(1)) pointerMove(p) // no pointer up: the keys come up first
    letGo(id)
    assert.equal(ask().capture, undefined)
    assert.deepEqual(releases, ['cap-5'])
  })

  test('a failed capture: the ask goes without it, nothing released', async () => {
    const id = hold()
    stroke()
    pending[0]({ ok: false, id: 'cap-6', error: 'screen_denied', message: 'x' })
    await flush()
    letGo(id)
    assert.equal(ask().capture, undefined)
    assert.deepEqual(releases, [])
  })

  test('Esc after a capture: released, no ask', async () => {
    hold()
    stroke()
    pending[0](ok('cap-7'))
    await flush()
    cancelCircle()
    assert.deepEqual(releases, ['cap-7'])
    assert.equal(sends.filter((m) => m.type === 'action').length, 0)
    assert.equal(captureState(), 'none')
  })

  test('offline as the hold seals: no ask, the capture is released', async () => {
    const id = hold()
    stroke()
    pending[0](ok('cap-8'))
    await flush()
    useLesson.setState({ connected: false })
    letGo(id)
    assert.equal(sends.filter((m) => m.type === 'action').length, 0)
    assert.deepEqual(releases, ['cap-8'])
  })
})

describe('the streamed answer on the wire', () => {
  test('answer.delta is a known event (common/wire KNOWN)', () => {
    assert.deepEqual(parseEngineMessage(JSON.stringify({ type: 'answer.delta', payload: { askId: 'a', text: 'Hi' } })), { type: 'answer.delta', payload: { askId: 'a', text: 'Hi' } })
  })

  test('deltas fill the card for this ask only; the final card replaces them; Esc drops it', () => {
    const id = hold()
    stroke()
    letGo(id)
    const askId = ask().askId as string
    delta('someone-else', 'Not this.')
    delta(askId, 'Each pass')
    delta(askId, ' runs the model.')
    const s = useCircle.getState().state
    assert.equal(s.k, 'asking')
    assert.equal(s.k === 'asking' && s.stream?.text, 'Each pass runs the model.')
    dispatch({ type: 'card', payload: { kind: 'answer', askId, title: 'Loop', body: 'Clean.' } } as never)
    const a = useCircle.getState().state
    assert.equal(a.k === 'answered' && a.answer.body, 'Clean.')
    delta(askId, ' late')
    assert.equal(useCircle.getState().state, a, 'a delta after the card is dropped')
    cancelCircle()
    assert.equal(k(), 'idle')
  })

  test('closed mid-stream (the X): the late final card is the circle\'s still, and the island does not show it', () => {
    useCards.setState({ card: undefined })
    const id = hold()
    stroke()
    letGo(id)
    const askId = ask().askId as string
    delta(askId, 'Each pass')
    cancelCircle() // the card's X, with the first words on screen
    assert.equal(k(), 'idle')
    const card = { kind: 'answer', askId, title: 'Loop', body: 'Each pass runs the model.' }
    assert.equal(circleOwnsCard(card as never), true)
    dispatch({ type: 'card', payload: card } as never)
    assert.equal(useCards.getState().card, undefined, 'not shown again in the island')
    assert.equal(k(), 'idle', 'and not on the circle either')
  })

  test('a new hold mid-stream: the old ask\'s late card is swallowed too; other cards still show', () => {
    useCards.setState({ card: undefined })
    const first = hold()
    stroke()
    letGo(first)
    const askId = ask().askId as string
    delta(askId, 'Half')
    hold()
    assert.equal(k(), 'armed')
    dispatch({ type: 'card', payload: { kind: 'answer', askId, title: 'Old', body: 'Old words.' } } as never)
    assert.equal(useCards.getState().card, undefined)
    assert.equal(circleOwnsCard({ kind: 'answer', askId: 'never-asked', body: 'x' } as never), false, 'an ask the circle never made is not its')
    dispatch({ type: 'card', payload: { kind: 'answer', askId: 'never-asked', title: 'Other', body: 'Shown.' } } as never)
    assert.equal(useCards.getState().card?.body, 'Shown.')
    useCards.setState({ card: undefined })
  })

  test('the ask timed out with no words: its late card is swallowed', () => {
    useCards.setState({ card: undefined })
    const id = hold()
    stroke()
    letGo(id)
    const askId = ask().askId as string
    mock.timers.tick(ASK_MAX_MS + 500)
    assert.equal(k(), 'idle')
    dispatch({ type: 'card', payload: { kind: 'answer', askId, title: 'Late', body: 'Late.' } } as never)
    assert.equal(useCards.getState().card, undefined)
  })

  test('a malformed delta (no askId) is ignored', () => {
    const id = hold()
    stroke()
    letGo(id)
    const before = useCircle.getState().state
    delta(undefined, 'x')
    assert.equal(useCircle.getState().state, before)
  })

  test('an early answer mark for this ask is drawn before any words and stays through the stream and the card', () => {
    const id = hold()
    stroke()
    letGo(id)
    const askId = ask().askId as string
    dispatch({ type: 'annotate', payload: { marks: [{ x: 420, y: 320, w: 160, h: 40, why: 'answer', askId }] } } as never)
    assert.equal(useAnnotate.getState().marks.length, 1, 'drawn while "Looking"')
    delta(askId, 'Words.')
    delta(askId, '', true)
    dispatch({ type: 'card', payload: { kind: 'answer', askId, title: 'T', body: 'Words.' } } as never)
    assert.equal(useAnnotate.getState().marks.length, 1, 'the stream and the card leave the mark alone')
    assert.equal(useAnnotate.getState().marks[0].askId, askId)
  })

  describe('the layer', () => {
    const React = require('react') as typeof import('react')
    g.React = React
    const { renderToStaticMarkup } = require('react-dom/server') as typeof import('react-dom/server')
    const { CircleView } = require('../src/renderer/src/features/circle/Layer') as typeof import('../src/renderer/src/features/circle/Layer')
    const render = (): string => renderToStaticMarkup(React.createElement(CircleView, { state: useCircle.getState().state, layout: { ...LAYOUT, notch: undefined, workArea: { x: 0, y: 32, width: 1440, height: 868 } } as never }))

    test('"Looking" until the first words, then the card with the words so far, then the final card', () => {
      const id = hold()
      stroke()
      letGo(id)
      const askId = ask().askId as string
      let html = render()
      assert.match(html, /data-part="circle-looking"/)
      assert.doesNotMatch(html, /data-part="circle-answer"/)
      delta(askId, '  ')
      assert.match(render(), /data-part="circle-looking"/, 'space alone is not words')
      delta(askId, 'Each pass runs')
      html = render()
      assert.doesNotMatch(html, /data-part="circle-looking"/)
      assert.match(html, /data-part="circle-answer"/)
      assert.match(html, /data-streaming=""/)
      assert.match(html, /aria-busy="true"/)
      assert.match(html, />Each pass runs</)
      delta(askId, '.', true)
      assert.doesNotMatch(render(), /data-streaming/, 'done: no longer busy')
      dispatch({ type: 'card', payload: { kind: 'answer', askId, title: 'The loop', body: 'Final words.' } } as never)
      html = render()
      assert.match(html, />Final words\.</)
      assert.match(html, />The loop</)
      assert.doesNotMatch(html, /Each pass runs/)
    })
  })
})
