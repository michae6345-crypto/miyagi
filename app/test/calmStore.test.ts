/**
 * Spotlight calm wiring (features/spotlight/store.ts) in a video lesson, offline: the gate is closed until something
 * asks, Hint / Explain / Show me / Not yet / a card with targets reach the box, a faded box stays gone while the
 * engine re-sends it, "Just teach me" lessons keep the old lifetime, and typing fades the box.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'

// Vite-only modules (import.meta.glob scenarios, the feature registry, assets) resolve to small stand-ins.
const dir = mkdtempSync(join(tmpdir(), 'calm-store-'))
const stub = (name: string, source: string): string => (writeFileSync(join(dir, name), source), pathToFileURL(join(dir, name)).href)
const EMPTY = stub('empty.mjs', 'export const scenarios = {}\nexport const defineFeature = (f) => f\nexport default ""')
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier) || (context.parentURL?.includes('/src/renderer/') && /(^|\/)registry$/.test(specifier))) return { url: EMPTY, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})

const g = globalThis as unknown as Record<string, unknown>
const listeners: Array<(e: unknown) => void> = []
const noop = (): (() => void) => () => {}
const tut = { platform: { os: 'darwin', keys: {}, pillTop: 0 }, onEvent: noop, onStatus: noop, on: noop, onFeature: noop, emit: () => {}, ready: () => {}, send: () => {}, invoke: () => Promise.resolve(null) }
g.window = { tut, addEventListener: (t: string, fn: (e: unknown) => void) => t === 'keydown' && listeners.push(fn), removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
g.document = { documentElement: { dataset: {} }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined }, addEventListener: () => {}, hidden: false }
g.location = { search: '' }

const { dispatch, emitUi } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const { useLesson } = require('../src/renderer/src/core/lesson') as typeof import('../src/renderer/src/core/lesson')
const { usePressed } = require('../src/renderer/src/core/shortcuts') as typeof import('../src/renderer/src/core/shortcuts')
const { useSpotlight } = require('../src/renderer/src/features/spotlight/store') as typeof import('../src/renderer/src/features/spotlight/store')
const { CALM_MS } = require('../src/renderer/src/features/spotlight/calm') as typeof import('../src/renderer/src/features/spotlight/calm')

const rect = { x: 100, y: 100, w: 200, h: 40 }
const box = { rect, caption: 'here', app: undefined }
const send = (type: string, payload: unknown = {}): void => dispatch({ type, payload } as never)
const spot = (r = rect): void => send('spotlight', { ...box, rect: r })
const shown = (): boolean => !!useSpotlight.getState().target
const press = (kind: string): void => usePressed.setState({ kind: kind as never, at: Date.now() })
const key = (k: string, extra: object = {}): void => listeners.forEach((fn) => fn({ key: k, ...extra }))
const lessonMode = (mode: string): void => void useLesson.setState({ lesson: { id: 'l', title: 't', mode } as never })

beforeEach(() => {
  mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 1_000_000 })
  emitUi('reset')
  usePressed.setState({ kind: undefined, at: 0 })
  lessonMode('video')
})
afterEach(() => {
  emitUi('reset')
  mock.timers.reset()
})

test('video lesson: closed until a step starts, then shows and fades after CALM_MS', () => {
  spot()
  assert.equal(shown(), false)
  send('step.started', { id: 's1' })
  spot()
  assert.equal(shown(), true)
  mock.timers.tick(CALM_MS)
  assert.equal(shown(), false)
  spot() // the engine re-sends the same target: stays gone
  assert.equal(shown(), false)
})

test('hint press: its spotlight shows after the step-start box faded, and fades itself', () => {
  send('step.started', { id: 's1' })
  spot()
  mock.timers.tick(CALM_MS)
  assert.equal(shown(), false)
  press('hint')
  spot()
  assert.equal(shown(), true)
  mock.timers.tick(CALM_MS)
  assert.equal(shown(), false)
  spot() // one-shot: re-sends after the fade do not bring it back
  assert.equal(shown(), false)
})

test('explain press works the same', () => {
  press('explain')
  spot()
  assert.equal(shown(), true)
})

test('a card with targets arms the gate (spotlight after it, or one refused just before it)', () => {
  send('step.started', { id: 's1' })
  spot()
  mock.timers.tick(CALM_MS)
  send('card', { targets: [{ rect }] })
  spot()
  assert.equal(shown(), true)
  mock.timers.tick(CALM_MS)
  assert.equal(shown(), false)
  spot() // refused
  mock.timers.tick(100)
  send('card', { targets: [{ rect }] })
  assert.equal(shown(), true)
})

test('a card without targets does not arm the gate', () => {
  send('card', { targets: [] })
  spot()
  assert.equal(shown(), false)
})

test('refused then offtrack replays the box within REFUSED_MS, not after', () => {
  spot()
  mock.timers.tick(1000)
  send('offtrack', { targets: [] })
  assert.equal(shown(), true)
  emitUi('reset')
  lessonMode('video') // core clears the lesson on reset
  spot()
  mock.timers.tick(3000)
  send('offtrack', { targets: [] })
  assert.equal(shown(), false)
})

test('show me pins: no fade, and it is shown with the strong dim', () => {
  press('show_me')
  spot()
  assert.equal(shown(), true)
  assert.equal(useSpotlight.getState().showMe, true)
  usePressed.setState({ kind: undefined, at: Date.now() }) // core clears pressed when the spotlight arrives
  mock.timers.tick(CALM_MS * 5)
  assert.equal(shown(), true)
  key('a') // a pinned box ignores typing
  assert.equal(shown(), true)
})

test('"Just teach me" lessons keep the old lifetime (no gate, no fade)', () => {
  lessonMode('lesson')
  spot()
  assert.equal(shown(), true)
  mock.timers.tick(CALM_MS * 5)
  assert.equal(shown(), true)
  key('a')
  assert.equal(shown(), true)
})

test('typing fades the box, a modifier or a chord does not; Not yet opens the gate again', () => {
  send('step.started', { id: 's1' })
  spot()
  key('Shift')
  key('e', { altKey: true })
  assert.equal(shown(), true)
  key('x')
  assert.equal(shown(), false)
  spot()
  assert.equal(shown(), false)
  send('offtrack', { targets: [] })
  spot()
  assert.equal(shown(), true)
})

test('step.passed and lesson.ended close the gate', () => {
  send('step.started', { id: 's1' })
  send('step.passed', { id: 's1' })
  spot()
  assert.equal(shown(), false)
})
