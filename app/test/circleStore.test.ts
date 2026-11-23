/**
 * features/circle/store.ts with a fake Electron bridge, offline: the overlay's mouse goes back (ui:emit
 * 'overlay:interactive' false, once) on every way out, and the re-say interval and the state ticker stop after each.
 * Also: no ask while the engine link is down, other cards' 'dismiss' leaves the circle alone, "away" never starts
 * during a hold or under the answer, late words are not asked again, the store is inert with no layer, the region's
 * scale is the display's, and nothing the circle layer reports as miyagi's own UI (data-ui / data-hit) covers the circle.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'

// Vite-only modules (import.meta.glob scenarios, the feature registry, assets) resolve to small stand-ins.
const dir = mkdtempSync(join(tmpdir(), 'circle-store-'))
const stub = (name: string, source: string): string => (writeFileSync(join(dir, name), source), pathToFileURL(join(dir, name)).href)
const EMPTY = stub('empty.mjs', 'export const scenarios = {}\nexport const defineFeature = (f) => f\nexport default ""')
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier) || (context.parentURL?.includes('/src/renderer/') && /(^|\/)registry$/.test(specifier))) return { url: EMPTY, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})

// The fake bridge: what the overlay says to main (emit) and to the engine (send).
const emits: { signal: string; payload: unknown }[] = []
const sends: { type: string; payload: Record<string, unknown> }[] = []
const invokes: { channel: string; arg: unknown }[] = []
const features: Record<string, (p?: unknown) => void> = {}
const g = globalThis as unknown as Record<string, unknown>
const noop = (): (() => void) => () => {}
const tut = {
  platform: { os: 'darwin', keys: { ptt: 'fn ⌃' }, pillTop: 0 },
  onEvent: noop,
  onStatus: noop,
  on: noop,
  onFeature: (signal: string, cb: (p?: unknown) => void) => ((features[signal] = cb), () => {}),
  emit: (signal: string, payload?: unknown) => void emits.push({ signal, payload }),
  ready: () => {},
  send: (m: { type: string; payload: Record<string, unknown> }) => void sends.push(m),
  invoke: (channel: string, arg?: unknown) => (invokes.push({ channel, arg }), Promise.resolve(null))
}
g.window = { tut, devicePixelRatio: 2, innerWidth: 1440, innerHeight: 900, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
g.document = { documentElement: { dataset: { route: 'overlay' } }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined }, addEventListener: () => {}, hidden: false }
g.location = { search: '' }
g.innerWidth = 1440
g.innerHeight = 900

const { dispatch, emitUi } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const { useLesson } = require('../src/renderer/src/core/lesson') as typeof import('../src/renderer/src/core/lesson')
const { PTT_REST } = require('../src/common/pttState') as typeof import('../src/common/pttState')
const { usePtt } = require('../src/renderer/src/features/ptt/store') as typeof import('../src/renderer/src/features/ptt/store')
const { useFront, AWAY_MS } = require('../src/renderer/src/features/shortcut-bar/front') as typeof import('../src/renderer/src/features/shortcut-bar/front')
const { routeFinal } = require('../src/renderer/src/features/ptt/store') as typeof import('../src/renderer/src/features/ptt/store')
const circle = require('../src/renderer/src/features/circle/store') as typeof import('../src/renderer/src/features/circle/store')
const { ARMED_MAX_MS } = require('../src/renderer/src/features/circle/machine') as typeof import('../src/renderer/src/features/circle/machine')
const { loopPoints } = require('../src/renderer/src/features/circle/geometry') as typeof import('../src/renderer/src/features/circle/geometry')

const { useCircle, cancelCircle, pointerDown, pointerMove, pointerUp, setLayout, layerGone, timersRunning, OFFLINE, LEASE_MS } = circle
const LAYOUT = { origin: { x: 0, y: 0 }, width: 1440, height: 900, displayId: 7 }

/** What the overlay said about the mouse: a lease ({on: true, leaseMs}) counts as true. */
const mouse = (): boolean[] =>
  emits.filter((e) => e.signal === 'overlay:interactive').map((e) => (e.payload && typeof e.payload === 'object' ? !!(e.payload as { on: boolean }).on : !!e.payload))
const awayOn = (): number => invokes.filter((i) => i.channel === 'overlay:away' && i.arg === true).length
/** A lesson is on and a non-lesson app (a browser) is in front: the away count runs, the real way (main's broadcast). */
const elsewhere = (): void => {
  useLesson.setState({ lesson: { id: 'l1', title: 'A lesson' } as never })
  features['front:app']({ known: true, name: 'Google Chrome', bundle: 'com.google.Chrome', aliases: ['google chrome'], miyagi: false, lesson: false })
}
const falses = (): number => mouse().filter((on) => !on).length
const ptt = (p: Partial<typeof PTT_REST>): void => usePtt.setState({ ptt: { ...PTT_REST, available: true, ...p } })
const k = (): string => useCircle.getState().state.k
const draw = (): void => {
  const pts = loopPoints(400, 300, 220, 120)
  pointerDown(pts[0])
  for (const p of pts.slice(1)) pointerMove(p)
  pointerUp()
}
let n = 0
/** A new hold, held a moment (the re-say interval runs). */
const hold = (): string => {
  const id = `s${++n}`
  ptt({ phase: 'arming', id })
  ptt({ phase: 'listening', id })
  mock.timers.tick(650)
  return id
}
/** The mouse went back exactly once, nothing more is said afterwards, and no timer is left running. */
const handedBack = (label: string): void => {
  assert.equal(falses(), 1, `${label}: click-through said once`)
  assert.equal(mouse().at(-1), false, `${label}: the last word is click-through`)
  const said = emits.length
  mock.timers.tick(ARMED_MAX_MS * 2)
  assert.equal(emits.length, said, `${label}: nothing said after`)
  assert.deepEqual(timersRunning(), { reassert: false, ticker: false }, `${label}: timers stopped`)
  assert.equal(k(), 'idle', label)
}

beforeEach(() => {
  mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'], now: 1_000_000 })
  ptt({ phase: 'idle' })
  cancelCircle()
  useLesson.setState({ connected: true })
  useFront.setState({ away: false })
  setLayout(LAYOUT)
  emits.length = 0
  sends.length = 0
  invokes.length = 0
})
afterEach(() => {
  cancelCircle()
  ptt({ phase: 'idle' })
  features['front:app']?.({ known: false, lesson: true })
  useLesson.setState({ lesson: undefined })
  mock.timers.reset()
})

describe('the mouse goes back once on every way out', () => {
  test('a hold takes the mouse and re-says it while held', () => {
    hold()
    assert.equal(k(), 'armed')
    assert.ok(mouse().filter(Boolean).length >= 3, 'said again every REASSERT_MS')
    assert.equal(falses(), 0)
    assert.deepEqual(timersRunning(), { reassert: true, ticker: true })
  })

  test('keys up', () => {
    const id = hold()
    ptt({ phase: 'sending', id, released: true })
    handedBack('keys up')
  })

  test('keys up while push to talk is still arming', () => {
    const id = `s${++n}`
    ptt({ phase: 'arming', id })
    mock.timers.tick(650)
    assert.equal(k(), 'armed')
    ptt({ phase: 'arming', id, released: true })
    handedBack('released while arming')
  })

  test("push to talk's Esc", () => {
    hold()
    ptt({ phase: 'idle', lastCancel: 'esc' })
    handedBack('ptt esc')
  })

  test("push to talk's error", () => {
    const id = hold()
    ptt({ phase: 'error', id: undefined, code: 'mic_denied' as never })
    void id
    handedBack('ptt error')
  })

  test('the 8 s cap, through the ticker', () => {
    hold()
    mock.timers.tick(ARMED_MAX_MS)
    assert.equal(falses(), 1)
    ptt({ phase: 'idle' })
    handedBack('8 s cap')
  })

  test('the lesson ends', () => {
    hold()
    dispatch({ type: 'lesson.ended', payload: {} } as never)
    handedBack('lesson.ended')
  })

  test('the engine link drops', () => {
    hold()
    useLesson.setState({ connected: false })
    handedBack('engine disconnect')
  })

  test("the answer card's X (circle drawn, asked, answered)", () => {
    const id = hold()
    draw()
    ptt({ phase: 'sending', id, released: true })
    assert.equal(falses(), 1, 'click-through as the keys come up')
    ptt({ phase: 'idle', lastCancel: 'empty' })
    const ask = sends.find((m) => m.type === 'action')
    assert.ok(ask, 'the ask went out')
    assert.equal(ask.payload.text, 'What is this?')
    assert.equal(ask.payload.source, 'circle')
    assert.equal((ask.payload.region as { displayId: number }).displayId, 7)
    dispatch({ type: 'card', payload: { kind: 'answer', askId: ask.payload.askId, title: 't', body: 'b' } } as never)
    assert.equal(k(), 'answered')
    assert.deepEqual(timersRunning(), { reassert: false, ticker: true })
    cancelCircle() // what the X does
    handedBack("card's X")
  })
})

describe('around the ask', () => {
  test('engine link down as the hold seals: no ask, the ink goes, the pill says so', () => {
    useLesson.setState({ connected: false })
    const id = hold()
    draw()
    ptt({ phase: 'idle', lastCancel: 'empty' })
    void id
    assert.equal(sends.filter((m) => m.type === 'action').length, 0)
    assert.equal(useLesson.getState().notice?.text, OFFLINE)
    assert.ok(OFFLINE.split(/\s+/).length <= 12)
    handedBack('offline')
  })

  test("another card's close ('dismiss') leaves the answer up", () => {
    const id = hold()
    draw()
    ptt({ phase: 'idle', lastCancel: 'empty' })
    void id
    const ask = sends.find((m) => m.type === 'action')!
    dispatch({ type: 'card', payload: { kind: 'answer', askId: ask.payload.askId, body: 'b' } } as never)
    emitUi('dismiss')
    assert.equal(k(), 'answered')
  })

  test('late words (after "What is this?" went) are not routed again as a plain ask', () => {
    const id = hold()
    draw()
    ptt({ phase: 'idle' }) // over, words maybe on the way
    mock.timers.tick(2000) // none in time: "What is this?"
    assert.equal(sends.filter((m) => m.type === 'action').length, 1)
    assert.equal(k(), 'asking')
    assert.equal(routeFinal({ id, text: 'what does this do' }), 'none', 'claimed while asking')
    const ask = sends.find((m) => m.type === 'action')!
    dispatch({ type: 'card', payload: { kind: 'answer', askId: ask.payload.askId, body: 'b' } } as never)
    assert.equal(sends.filter((m) => m.type === 'action').length, 1, 'no second ask')
    assert.equal(k(), 'answered')
  })

  test("the region's scale is the display's scaleFactor (not devicePixelRatio, which has page zoom)", () => {
    setLayout({ ...LAYOUT, scaleFactor: 1.5 })
    hold()
    draw()
    ptt({ phase: 'idle', lastCancel: 'empty' })
    const ask = sends.find((m) => m.type === 'action')!
    assert.equal((ask.payload.region as { scale: number }).scale, 1.5)
    setLayout(LAYOUT)
  })

  test('taking the mouse is a lease main can drop; giving it back is a plain false', () => {
    const id = hold()
    const said = emits.filter((e) => e.signal === 'overlay:interactive')
    assert.deepEqual(said[0].payload, { on: true, leaseMs: LEASE_MS })
    assert.ok(LEASE_MS >= 4 * 200, 'several re-says fit in one lease')
    ptt({ phase: 'sending', id, released: true })
    assert.equal(emits.filter((e) => e.signal === 'overlay:interactive').at(-1)!.payload, false)
  })
})

describe('away never starts under a hold or under the answer', () => {
  test('a long hold over a browser page: no away, no click-through before release', () => {
    elsewhere()
    mock.timers.tick(1000) // the away count is running
    const id = hold()
    for (let t = 0; t < ARMED_MAX_MS - 1000; t += 500) mock.timers.tick(500)
    assert.equal(k(), 'armed')
    assert.ok(Date.now() - 1_000_000 > AWAY_MS + 1000, 'held past AWAY_MS')
    assert.equal(awayOn(), 0, 'overlay:away true never invoked')
    assert.equal(useFront.getState().away, false)
    assert.equal(falses(), 0, 'never click-through mid-hold')
    ptt({ phase: 'sending', id, released: true })
    handedBack('long hold')
  })

  test('away already on as the hold starts: it ends at once', () => {
    elsewhere()
    mock.timers.tick(AWAY_MS + 10)
    assert.equal(useFront.getState().away, true)
    invokes.length = 0
    const id = hold()
    assert.equal(useFront.getState().away, false)
    assert.ok(invokes.some((i) => i.channel === 'overlay:away' && i.arg === false))
    ptt({ phase: 'sending', id, released: true })
  })

  test("the answer's X stays clickable for as long as the answer shows", () => {
    elsewhere()
    const id = hold()
    draw()
    ptt({ phase: 'sending', id, released: true })
    ptt({ phase: 'idle', lastCancel: 'empty' })
    const ask = sends.find((m) => m.type === 'action')!
    dispatch({ type: 'card', payload: { kind: 'answer', askId: ask.payload.askId, body: 'b' } } as never)
    for (let t = 0; t < AWAY_MS * 4; t += 150) mock.timers.tick(150)
    assert.equal(k(), 'answered')
    assert.equal(awayOn(), 0, 'no away while the answer shows')
    cancelCircle()
    mock.timers.tick(AWAY_MS + 10)
    assert.equal(awayOn(), 1, 'a fresh count after the answer closes')
  })
})

describe('inert with no layer (the feature off)', () => {
  test('a hold takes nothing, words route as ever', () => {
    layerGone()
    emits.length = 0
    const id = hold()
    assert.equal(k(), 'idle')
    assert.equal(mouse().length, 0, 'the mouse is never taken')
    assert.deepEqual(timersRunning(), { reassert: false, ticker: false })
    assert.notEqual(routeFinal({ id, text: 'what is a tensor' }), 'none', 'push to talk routes the words')
    ptt({ phase: 'idle' })
    setLayout(LAYOUT)
  })

  test('the layer going away mid-hold gives the mouse back', () => {
    hold()
    layerGone()
    handedBack('layer gone')
    setLayout(LAYOUT)
  })
})

describe("the layer never reports the circled region as miyagi's own UI", () => {
  const React = require('react') as typeof import('react')
  g.React = React // tsx compiles the layer's JSX with the classic runtime here
  const { renderToStaticMarkup } = require('react-dom/server') as typeof import('react-dom/server')
  const { CircleView } = require('../src/renderer/src/features/circle/Layer') as typeof import('../src/renderer/src/features/circle/Layer')

  type R = { x: number; y: number; w: number; h: number }
  const box: R = { x: 400, y: 300, w: 240, h: 140 }
  const strokes = [loopPoints(box.x + 6, box.y + 6, box.w - 12, box.h - 12)]
  const px = (style: string, prop: string): number | undefined => {
    const m = new RegExp(`(?:^|;)${prop}:(-?[\\d.]+)px`).exec(style)
    return m ? Number(m[1]) : undefined
  }
  /** Every element marked data-ui or data-hit, with the rect its inline style gives (the whole overlay when none). */
  const reported = (html: string): { tag: string; r: R }[] =>
    Array.from(html.matchAll(/<(\w+)([^>]*?)>/g))
      .filter(([, , attrs]) => /\sdata-(ui|hit)(=|\s|$)/.test(attrs) || /\sdata-(ui|hit)=""/.test(attrs))
      .map(([, tag, attrs]) => {
        const style = /style="([^"]*)"/.exec(attrs)?.[1] ?? ''
        const x = px(style, 'left')
        const y = px(style, 'top')
        const w = px(style, 'width')
        const h = px(style, 'height')
        const r = x !== undefined && y !== undefined && w !== undefined ? { x, y, w, h: h ?? 120 } : { x: 0, y: 0, w: LAYOUT.width, h: LAYOUT.height }
        return { tag: `${tag}${attrs.match(/data-part="([^"]+)"/)?.[0] ?? ''}`, r }
      })
  const overlaps = (a: R, b: R): boolean => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h
  // A server render reads a zustand store's initial state, so the view is rendered with the state itself.
  const render = (): string => renderToStaticMarkup(React.createElement(CircleView, { state: useCircle.getState().state, layout: { ...LAYOUT, notch: undefined, workArea: { x: 0, y: 32, width: 1440, height: 868 } } as never }))

  for (const st of ['sealed', 'asking', 'answered'] as const) {
    test(st, () => {
      const base = { since: Date.now(), strokes, box }
      const state =
        st === 'sealed'
          ? { k: st, session: 's', ...base }
          : st === 'asking'
            ? { k: st, session: 's', askId: 'a1', text: 'What is this?', ...base }
            : { k: st, session: 's', askId: 'a1', text: 'What is this?', answer: { title: 'A title', body: 'An answer.' }, ...base }
      useCircle.setState({ state: state as never })
      const html = render()
      assert.match(html, /data-part="circle-ink"/, 'the ink is drawn')
      assert.doesNotMatch(/<svg[^>]*data-part="circle-ink"[^>]*>/.exec(html)![0], /data-ui|data-hit/, 'the ink is not reported')
      for (const { tag, r } of reported(html)) assert.ok(!overlaps(r, box), `${tag} covers the circle (${JSON.stringify(r)})`)
      if (st !== 'sealed') assert.ok(reported(html).length >= 1, 'the chip or the card is reported (beside the circle)')
    })
  }
})
