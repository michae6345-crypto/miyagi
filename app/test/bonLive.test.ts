/**
 * bon in a real lesson, offline: the overlay's real features (features/buddy and features/annotate, as the registry
 * mounts them) driven with the event shapes the live engine sends, in the order it sends them. The stage's mock sends a
 * spotlight box straight after step.started, so it hid the live gap (trace Nov 24: the engine sent only
 * `spotlight {clear}` and bon never left the notch). These tests pin both sides of that:
 *   - VS Code lesson: step.started, spotlight {clear}, then spotlight {rect, caption, app: "Code", matched, snippet}:
 *     bon gets exactly one mark (held 10 s), on the left (the caption has the right), and follows the next step's box.
 *   - The same box while another app is in front: no mark. The engine sending only {clear}: no mark, and the
 *     diagnostic says no-mark (engine silence), not an app drop.
 *   - App lesson (on-screen coach): annotate {marks: [{id, why: point, stepId, label, text, keys, x, y, w, h}]} with no
 *     holdMs: bon circles it and stays for the step (no 6 s fade); features/annotate still draws its text box (and only
 *     that) beside the loop; both go on step.passed; a pause hides both and a resume brings both back.
 * Run: node --import tsx --import ./test/setup.mjs --test test/bonLive.test.ts
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, before, beforeEach, describe, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'

// The registry uses import.meta.glob (Vite only): a stand-in that serves the features this test loads itself (the
// real feature modules, below). Assets and CSS resolve to nothing.
const dir = mkdtempSync(join(tmpdir(), 'bon-live-'))
const stub = (name: string, source: string): string => (writeFileSync(join(dir, name), source), pathToFileURL(join(dir, name)).href)
const REGISTRY = stub(
  'registry.mjs',
  `export const defineFeature = (f) => f
export const getFeatures = () => globalThis.__bonLiveFeatures ?? []
export const getOverlayLayers = () => getFeatures().flatMap((f) => f.overlayLayers ?? []).sort((a, b) => a.z - b.z)
export const getIslandModes = () => []
export const getFeatureWindows = () => []
export const getAppWindows = () => []
`
)
const EMPTY = stub('empty.mjs', 'export const scenarios = {}\nexport default ""')
registerHooks({
  resolve(specifier, context, next) {
    if (context.parentURL?.includes('/src/renderer/') && /(^|\/)core\/registry(\.ts)?$|^\.\.?\/registry(\.ts)?$|^\.\/registry$/.test(specifier)) return { url: REGISTRY, shortCircuit: true }
    if (/(^|\/)mock\/scenarios$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})
// cards/panel.ts looks one module up with import.meta.glob (Vite only): here it finds nothing, as before that module
// landed. tsx compiles the renderer as CommonJS through require.extensions, so the call is swapped in its output.
type Compiled = { _compile: (code: string, file: string) => unknown }
const exts = (require('node:module') as { _extensions: Record<string, (m: Compiled, file: string) => unknown> })._extensions
for (const ext of ['.ts', '.tsx']) {
  const load = exts[ext]
  if (!load) continue
  exts[ext] = (m, file) => {
    if (file.includes('/src/renderer/')) {
      const compile = m._compile
      m._compile = function (this: Compiled, code: string, f: string) {
        return compile.call(this, code.replace(/define_import_meta_default\.glob\(/g, '((..._a) => ({}))('), f)
      }
    }
    return load(m, file)
  }
}

// A renderer with a fake Electron bridge (like test/bonWire.test.ts).
const data: Record<string, string> = {}
const storage = { getItem: (k: string) => (k in data ? data[k] : null), setItem: (k: string, v: string) => void (data[k] = v), removeItem: (k: string) => void delete data[k] }
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
  send: () => {},
  invoke: (): Promise<unknown> => Promise.resolve(null)
}
const el = (): Record<string, unknown> => ({ style: {}, setAttribute: () => {}, appendChild: () => {}, addEventListener: () => {}, classList: { add: () => {}, remove: () => {} } })
g.window = { tut, localStorage: storage, location: { search: '' }, devicePixelRatio: 2, innerWidth: 1440, innerHeight: 900, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
g.document = { documentElement: { dataset: { route: 'overlay' }, style: {} }, getElementById: () => el(), createElement: el, head: { prepend: () => undefined, appendChild: () => undefined }, body: el(), addEventListener: () => {}, removeEventListener: () => {}, hidden: false, querySelector: () => null, querySelectorAll: () => [] }
g.location = { search: '' }
if (!g.localStorage) g.localStorage = storage

type Feature = { id: string; overlayLayers?: { id: string; z: number }[]; yieldsToBuddy?: boolean }
const { dispatch, emitUi } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const { useLesson } = require('../src/renderer/src/core/lesson') as typeof import('../src/renderer/src/core/lesson')
// The real features, as the registry mounts them (features load A to Z: annotate first).
const annotateFeature = (require('../src/renderer/src/features/annotate/index') as { default: Feature }).default
const buddyFeature = (require('../src/renderer/src/features/buddy/index') as { default: Feature }).default
const features: Feature[] = [annotateFeature, buddyFeature]
g.__bonLiveFeatures = features
const { usePointing, SPOT_HOLD_MS } = require('../src/renderer/src/features/buddy/pointing') as typeof import('../src/renderer/src/features/buddy/pointing')
const { standsDown, HOLD } = require('../src/renderer/src/features/buddy/marks') as typeof import('../src/renderer/src/features/buddy/marks')
const { buddyWhy, markWords, perchPrefer } = require('../src/renderer/src/features/buddy/trip') as typeof import('../src/renderer/src/features/buddy/trip')
const { useAnnotate } = require('../src/renderer/src/features/annotate/store') as typeof import('../src/renderer/src/features/annotate/store')
const { buddyInBuild, drawnParts } = require('../src/renderer/src/features/annotate/BuddyLayer') as typeof import('../src/renderer/src/features/annotate/BuddyLayer')
const { useFront } = require('../src/renderer/src/features/shortcut-bar/front') as typeof import('../src/renderer/src/features/shortcut-bar/front')
const { useSpotlight } = require('../src/renderer/src/features/spotlight/store') as typeof import('../src/renderer/src/features/spotlight/store')
const { perf } = require('../src/renderer/src/core/perf') as typeof import('../src/renderer/src/core/perf')

const send = (type: string, payload: unknown = {}): void => dispatch({ type, payload } as never)
const marks = (): { rect: { x: number; y: number; w: number; h: number }; why: string; text?: string }[] => usePointing.getState().marks.map((m) => ({ rect: m.rect, why: m.why, ...(m.text ? { text: m.text } : {}) }))
/** What Companion's data-buddy-why would say now (the overlay covers this whole test screen). */
const why = (): string => buddyWhy({ standDown: standsDown(features as never), marks: usePointing.getState().marks.length, here: usePointing.getState().marks.length, summoned: false })

const VSCODE = { known: true, name: 'Code', bundle: 'com.microsoft.VSCode', aliases: ['code', 'visual studio code'], miyagi: false, lesson: true }
const CHROME = { known: true, name: 'Google Chrome', bundle: 'com.google.Chrome', aliases: ['google chrome', 'chrome'], miyagi: false, lesson: false }
const ROW = { x: 412, y: 318, w: 520, h: 19 }
const ROW2 = { x: 412, y: 356, w: 300, h: 19 }
/** The engine's step-start box, as session.py sends it (spotlight {rect, caption, app, matched, snippet}). */
const spot = (rect: typeof ROW, caption = 'Type the function header here'): Record<string, unknown> => ({ rect, caption, app: 'Code', matched: 'def area(', snippet: 'def area(r):' })
const step = (stepId: string, index = 0): void => send('step.started', { stepId, index, title: `Step ${index + 1}`, instructions: 'Write it' })
/** wire.ts and the annotate store bridge the spotlight store late (a dynamic import): let those land. */
const settle = async (): Promise<void> => {
  for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r))
}

before(async () => {
  await import('../src/renderer/src/features/spotlight/store')
  await settle()
  // One mock clock for the whole file: a reset hands out timer ids again, and a store's stale id (cleared later) would
  // then cancel another store's new timer, which real timers never do.
  mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 1_700_000_000_000 })
})
after(() => mock.timers.reset())

describe('the overlay as mounted: who draws', () => {
  test('bon draws (annotate yields), and annotate keeps only the coach text box', () => {
    assert.deepEqual(
      features.flatMap((f) => (f.overlayLayers ?? []).map((l) => `${l.id}@${l.z}`)),
      ['annotate@48', 'buddy-reach@30', 'buddy@55']
    )
    assert.equal(annotateFeature.yieldsToBuddy, true)
    assert.equal(standsDown(features as never), false, 'bon does not stand down')
    assert.equal(buddyInBuild(features), true, 'annotate draws no stroke while bon is in the build')
    assert.deepEqual(drawnParts({ label: 'Move it' }, true), { stroke: false, label: false, text: false })
    assert.deepEqual(drawnParts({ label: 'Move it', text: 'Press G to move the cube' }, true), { stroke: false, label: false, text: true })
    assert.deepEqual(drawnParts({ label: 'Move it' }, false), { stroke: true, label: true, text: false }, 'without bon it draws as before')
  })

  test('bon’s body is not data-ui (the engine would black out the line numbers under it); its bubble is', () => {
    const src = readFileSync(join(__dirname, '../src/renderer/src/features/buddy/Companion.tsx'), 'utf8')
    const body = src.match(/<span[^>]*data-part="buddy-body"[^>]*>/)
    assert.ok(body, 'the body span is there')
    assert.doesNotMatch(body[0], /data-ui/)
    assert.match(src, /data-ui\s+data-hit=\{ready \|\| undefined\}\s+data-part="bubble"/)
  })
})

describe('a VS Code lesson, with the events the live engine sends', () => {
  beforeEach(() => {
    emitUi('reset')
    useFront.setState({ ...VSCODE, away: false })
    useLesson.setState({ lesson: { id: 'L1', mode: 'lesson' } as never })
  })
  after(() => {
    emitUi('reset')
  })

  test('step start, {clear}, then the box: bon gets one mark, on the left, held 10 s', () => {
    step('s1')
    send('spotlight', { clear: true })
    send('spotlight', spot(ROW))
    assert.ok(useSpotlight.getState().target, 'the spotlight shows the box')
    assert.deepEqual(marks(), [{ rect: ROW, why: 'point' }])
    assert.equal(usePointing.getState().bridged, true)
    assert.equal(perchPrefer(false, usePointing.getState().bridged), 'left', 'the caption has the right of the box')
    assert.equal(why(), 'held')
    // The engine re-reads the same box every few seconds: still one mark, same deadline.
    mock.timers.tick(3000)
    send('spotlight', spot({ ...ROW, x: ROW.x + 3 }))
    assert.equal(marks().length, 1)
    mock.timers.tick(SPOT_HOLD_MS - 3000 - 50)
    assert.equal(marks().length, 1, 'still pointing just before 10 s')
    mock.timers.tick(100)
    assert.equal(marks().length, 0, 'gone after its hold')
  })

  test('the next step: bon follows the learner to the new box', () => {
    step('s1')
    send('spotlight', { clear: true })
    send('spotlight', spot(ROW))
    assert.deepEqual(marks()[0].rect, ROW)
    step('s2', 1)
    assert.equal(marks().length, 0, 'the old step’s mark goes with its step')
    send('spotlight', { clear: true })
    send('spotlight', spot(ROW2, 'Return the area'))
    assert.deepEqual(marks(), [{ rect: ROW2, why: 'point' }])
  })

  test('the same box while another app is in front: no mark; back in VS Code: the mark', () => {
    useFront.setState({ ...CHROME, away: false })
    step('s1')
    send('spotlight', { clear: true })
    send('spotlight', spot(ROW))
    assert.equal(useSpotlight.getState().target, undefined)
    assert.equal(marks().length, 0)
    useFront.setState({ ...VSCODE, away: false })
    assert.deepEqual(marks(), [{ rect: ROW, why: 'point' }])
  })

  test('the engine sends only {clear} (screen reader down, as on Nov 21-24): no mark, and it reads as engine silence', () => {
    const before = perf.snapshot()['buddy.spotlit'] ?? 0
    step('s1')
    send('spotlight', { clear: true })
    mock.timers.tick(15_000)
    assert.equal(marks().length, 0)
    assert.equal((perf.snapshot()['buddy.spotlit'] ?? 0) - before, 0, 'no box ever reached bon')
    assert.equal(why(), 'no-mark')
  })
})

describe('an app lesson (on-screen coach), with the annotate the live engine sends', () => {
  const COACH = { id: 'os-s1-1', why: 'point', stepId: 's1', label: 'Move the cube', text: 'Press G to move the cube', keys: ['G'], x: 700, y: 400, w: 120, h: 90 }
  beforeEach(() => {
    emitUi('reset')
    useLesson.setState({ lesson: { id: 'B1', mode: 'lesson' } as never })
  })
  after(() => {
    emitUi('reset')
  })

  test('bon circles it and stays for the step; the text box is drawn by annotate, beside it', () => {
    step('s1')
    send('annotate', { marks: [COACH] })
    assert.deepEqual(marks(), [{ rect: { x: 700, y: 400, w: 120, h: 90 }, why: 'point', text: 'Press G to move the cube' }])
    assert.equal(perchPrefer(true, usePointing.getState().bridged), 'left', 'the text box takes the right')
    assert.equal(markWords(usePointing.getState().marks[0]), undefined, 'bon does not say the label over the text box')
    const drawn = useAnnotate.getState().marks
    assert.equal(drawn.length, 1)
    assert.deepEqual(drawnParts(drawn[0], buddyInBuild(features)), { stroke: false, label: false, text: true })
    mock.timers.tick(HOLD.base + 5000)
    assert.equal(marks().length, 1, 'a text mark is not timed (the step’s action stays)')
    assert.equal(useAnnotate.getState().marks.length, 1)
    send('step.passed', { stepId: 's1' })
    assert.equal(marks().length, 0)
    assert.equal(useAnnotate.getState().marks.length, 0)
  })

  test('paused: both hide; resumed: both come back, with no re-send', () => {
    step('s1')
    send('annotate', { marks: [COACH] })
    send('lesson.paused', { reason: 'user' })
    assert.equal(marks().length, 0)
    assert.equal(useAnnotate.getState().marks.length, 0)
    send('lesson.resumed', {})
    assert.equal(marks().length, 1)
    assert.equal(useAnnotate.getState().marks.length, 1)
  })

  test('a late text mark for a step that is over draws nothing; the next step keeps none of the old one', () => {
    step('s2', 1)
    send('annotate', { marks: [COACH] })
    assert.equal(marks().length, 0)
    assert.equal(useAnnotate.getState().marks.length, 0)
  })

  test('a plain answer mark still fades at its hold', () => {
    step('s1')
    send('annotate', { marks: [{ why: 'answer', askId: 'a1', x: 10, y: 10, w: 80, h: 30 }] })
    assert.equal(marks().length, 1)
    mock.timers.tick(HOLD.base + 10)
    assert.equal(marks().length, 0)
  })
})
