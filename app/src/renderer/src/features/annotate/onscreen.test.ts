/**
 * On-screen coach (Nov 24), offline, with mock timers and no window:
 *   - store.ts: a text mark has no hold timer (it stays while its step is live), a plain mark still fades at 6 s; what
 *     takes a text mark away (another step, step.passed, Esc, annotate {clear}, a new lesson, not a replay); what brings
 *     it back after the learner reached or dismissed it (a Show me press, a "Not yet" for this step; never a bare re-send).
 *   - onscreen.ts: lesson.ready with lesson.app asks core's `panel` UI event to collapse, once, after the drawer's own
 *     lesson.ready handler; never without app, never on a replay.
 * `node --import tsx --test src/renderer/src/features/annotate/onscreen.test.ts`
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, afterEach, before, beforeEach, describe, it, mock } from 'node:test'
import { pathToFileURL } from 'node:url'

// store.ts imports the spotlight store and core/shortcuts late (its spotlight bridge); they pull in the whole renderer.
// Here they are tiny stand-in stores: the spotlight one stays still, the pressed one lets a test press Show me.
const dir = mkdtempSync(join(tmpdir(), 'onscreen-'))
const STUB = pathToFileURL(join(dir, 'stub.mjs')).href
writeFileSync(
  join(dir, 'stub.mjs'),
  [
    'function store(init) {',
    '  let s = init',
    '  const subs = new Set()',
    '  return {',
    '    getState: () => s,',
    '    setState: (p) => { const was = s; s = { ...s, ...p }; subs.forEach((f) => f(s, was)) },',
    '    subscribe: (f) => { subs.add(f); return () => subs.delete(f) }',
    '  }',
    '}',
    // One pair per process: store.ts may load this file apart from the test (its own module instance).
    'const stubs = (globalThis.__annotateStubs ??= { useSpotlight: store({}), usePressed: store({ kind: undefined, at: 0 }) })',
    'export const useSpotlight = stubs.useSpotlight',
    'export const usePressed = stubs.usePressed',
    ''
  ].join('\n')
)
registerHooks({
  resolve(specifier, context, next) {
    if (context.parentURL?.includes('/features/annotate/store') && /(spotlight\/store|core\/shortcuts)$/.test(specifier)) return { url: STUB, shortCircuit: true }
    return next(specifier, context)
  }
})

mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 1_000_000 })

const { dispatch, emitUi, onMessage, onUi } = require('../../core/bus') as typeof import('../../core/bus')
const { fade, useAnnotate } = require('./store') as typeof import('./store')
require('./onscreen')

const send = (type: string, payload: unknown): void => dispatch({ type, payload } as never)
const marks = (): { id?: string; text?: string }[] => useAnnotate.getState().marks
const ids = (): (string | undefined)[] => marks().map((m) => m.id)

/** Keycap labels as the engine spells them on a Mac (engine data, not app copy). */
const SHIFT_A = '\u21e7A'

const textMark = { id: 'os-s1-1', x: 600, y: 400, w: 120, h: 30, why: 'point', stepId: 's1', label: 'Add menu', text: 'Add a torus from the Add menu', keys: [SHIFT_A] }
const plainMark = { id: 'plain-1', x: 200, y: 200, w: 80, h: 24, why: 'point', stepId: 's1' }

// The panel requests and the drawer stand-in's lesson.ready, in the order they ran.
const log: string[] = []
onUi('panel', (r) => void log.push(`panel:${String(r)}`))
// Registered AFTER onscreen.ts, so it runs after onscreen's handler: the collapse must still come after it.
onMessage('lesson.ready', () => void log.push('drawer:open'))

beforeEach(() => {
  send('lesson.ended', {})
  mock.timers.runAll()
  log.length = 0
})
afterEach(() => mock.timers.runAll())

/** The stand-in pressed store, once store.ts's late import of it has resolved. */
let pressed: { setState: (p: { kind?: string; at: number }) => void }
before(async () => {
  await new Promise((r) => setImmediate(r))
  pressed = (globalThis as unknown as { __annotateStubs: { usePressed: typeof pressed } }).__annotateStubs.usePressed
})
after(() => mock.timers.reset())
const press = (kind: string): void => pressed.setState({ kind, at: Date.now() })
const notYet = (stepId: string): void => send('card', { kind: 'step', title: 'Not yet', body: '', source: 'judge', verdict: 'not_done', stepId })
const startS1 = (): void => send('step.started', { stepId: 's1', index: 0, title: 't', instructions: 'i' })
const reach = (): void => fade([(useAnnotate.getState().marks[0] as { key: string }).key])

describe('text mark hold (store.ts)', () => {
  // The coach's marks are for a live step: each test starts with s1 running.
  beforeEach(() => startS1())

  it('a text mark has no fade timer; a plain mark still fades at 6 s', () => {
    send('step.started', { stepId: 's1', index: 0, title: 'Add a torus', instructions: 'Add a torus' })
    send('annotate', { marks: [textMark], holdMs: 2000 })
    assert.deepEqual(ids(), ['os-s1-1'])
    assert.equal(marks()[0].text, 'Add a torus from the Add menu')
    mock.timers.tick(120_000)
    assert.deepEqual(ids(), ['os-s1-1'], 'still there after 2 minutes: holdMs does not apply to it')

    send('annotate', { marks: [plainMark] })
    assert.deepEqual(ids(), ['plain-1'], 'a replacing annotate takes the text mark away')
    mock.timers.tick(5999)
    assert.deepEqual(ids(), ['plain-1'])
    mock.timers.tick(1)
    assert.deepEqual(ids(), [], 'the plain mark fades at 6 s')
  })
  it('in a mixed set only the plain mark fades', () => {
    send('annotate', { marks: [textMark, plainMark] })
    mock.timers.tick(6000)
    assert.deepEqual(ids(), ['os-s1-1'])
  })
  it('step.started for the same step keeps it (no timer); another step drops it', () => {
    send('annotate', { marks: [textMark] })
    send('step.started', { stepId: 's1', index: 0, title: 't', instructions: 'i' })
    mock.timers.tick(60_000)
    assert.deepEqual(ids(), ['os-s1-1'], 'kept for its own step, untimed')
    send('step.started', { stepId: 's2', index: 1, title: 't', instructions: 'i' })
    assert.deepEqual(ids(), [])
  })
  it('a replayed step.started keeps it', () => {
    send('annotate', { marks: [textMark] })
    send('step.started', { stepId: 's2', index: 1, title: 't', instructions: 'i', replay: true })
    assert.deepEqual(ids(), ['os-s1-1'])
  })
  it('step.passed removes it', () => {
    send('annotate', { marks: [textMark] })
    send('step.passed', { stepId: 's1' })
    assert.deepEqual(ids(), [])
  })
  it('Esc removes it; a plain re-send this step (no ask) does not bring it back', () => {
    startS1()
    send('annotate', { marks: [textMark] })
    emitUi('dismiss')
    assert.deepEqual(ids(), [])
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), [])
  })
  it('Esc, then Show me: the re-send draws it again with its text', () => {
    startS1()
    send('annotate', { marks: [textMark] })
    emitUi('dismiss')
    press('show_me')
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), ['os-s1-1'])
    assert.equal(marks()[0].text, 'Add a torus from the Add menu')
    // The ask is spent: reached again, a bare re-send stays gone.
    reach()
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), [])
  })
  it('reached, then "Not yet" for this step: the re-send draws it again', () => {
    startS1()
    send('annotate', { marks: [textMark] })
    reach()
    assert.deepEqual(ids(), [])
    notYet('s1')
    assert.deepEqual(ids(), [], 'the card alone draws nothing new')
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), ['os-s1-1'])
    assert.equal(marks()[0].text, 'Add a torus from the Add menu')
    mock.timers.tick(60_000)
    assert.deepEqual(ids(), ['os-s1-1'], 'still untimed')
  })
  it('reached, a re-send first (skipped), then "Not yet": the card draws it again', () => {
    startS1()
    send('annotate', { marks: [textMark] })
    reach()
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), [])
    notYet('s1')
    assert.deepEqual(ids(), ['os-s1-1'])
  })
  it('a "Not yet" for another step is not an ask', () => {
    startS1()
    send('annotate', { marks: [textMark] })
    emitUi('dismiss')
    notYet('s0')
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), [])
  })
  it('annotate {clear} removes it', () => {
    send('annotate', { marks: [textMark] })
    send('annotate', { clear: true })
    assert.deepEqual(ids(), [])
  })
  it('a new lesson removes it; a replay of the same lesson keeps it', () => {
    send('annotate', { marks: [textMark] })
    send('lesson.ready', { lesson: { id: 'l1', mode: 'lesson' }, steps: [], replay: true })
    assert.deepEqual(ids(), ['os-s1-1'])
    send('lesson.ready', { lesson: { id: 'l2', mode: 'lesson' }, steps: [] })
    assert.deepEqual(ids(), [])
  })
  it('a re-send with new text updates it in place (same birth)', () => {
    send('annotate', { marks: [textMark] })
    const born = (useAnnotate.getState().marks[0] as { born: number }).born
    mock.timers.tick(3000)
    send('annotate', { marks: [{ ...textMark, text: 'Pick Torus from the Mesh list' }] })
    assert.equal(marks()[0].text, 'Pick Torus from the Mesh list')
    assert.equal((useAnnotate.getState().marks[0] as { born: number }).born, born)
  })
})

describe('only while its step is live (store.ts)', () => {
  beforeEach(() => startS1())

  it('an annotate after step.passed for that step draws no text mark', () => {
    send('step.passed', { stepId: 's1' })
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), [])
  })
  it('an annotate for s1 after step.started s2 draws no text mark, and leaves what s2 drew', () => {
    send('step.started', { stepId: 's2', index: 1, title: 't', instructions: 'i' })
    const s2Mark = { ...textMark, id: 'os-s2-1', stepId: 's2', text: 'Scale it with S' }
    send('annotate', { marks: [s2Mark] })
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), ['os-s2-1'], 'the late s1 answer neither draws nor replaces')
    mock.timers.tick(60_000)
    assert.deepEqual(ids(), ['os-s2-1'])
  })
  it('a late text mark is not remembered as gone: its step running again draws it', () => {
    send('step.passed', { stepId: 's1' })
    send('annotate', { marks: [textMark] })
    startS1()
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), ['os-s1-1'])
  })
  it('a plain mark for another step still draws, on its hold (as before)', () => {
    send('step.started', { stepId: 's2', index: 1, title: 't', instructions: 'i' })
    send('annotate', { marks: [plainMark] })
    assert.deepEqual(ids(), ['plain-1'])
    mock.timers.tick(6000)
    assert.deepEqual(ids(), [])
  })
})

describe('no text mark on idle (store.ts)', () => {
  beforeEach(() => startS1())

  it('lesson.paused withdraws it; an annotate while paused draws none; after lesson.resumed the re-send draws it', () => {
    send('annotate', { marks: [textMark] })
    send('lesson.paused', { reason: 'editor_closed', stepId: 's1' })
    assert.deepEqual(ids(), [])
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), [], 'not while paused')
    send('lesson.resumed', { reason: 'editor_closed', stepId: 's1' })
    assert.deepEqual(ids(), [], 'resume alone draws nothing')
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), ['os-s1-1'], 'not remembered as gone: the re-send draws it')
    assert.equal(marks()[0].text, 'Add a torus from the Add menu')
  })
  it('a pause keeps a plain mark on its own hold', () => {
    send('annotate', { marks: [textMark, plainMark] })
    send('lesson.paused', { reason: 'user' })
    assert.deepEqual(ids(), ['plain-1'])
    mock.timers.tick(6000)
    assert.deepEqual(ids(), [])
  })
  it('a blocker withdraws it; its clear lets the re-send draw it', () => {
    send('annotate', { marks: [textMark] })
    send('blocker', { kind: 'editor_closed', title: 'Open it again' })
    assert.deepEqual(ids(), [])
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), [])
    send('blocker', { kind: 'editor_closed', clear: true })
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), ['os-s1-1'])
  })
  it('a blocker clear of another kind keeps it quiet', () => {
    send('blocker', { kind: 'network' })
    send('blocker', { kind: 'kernel', clear: true })
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), [])
  })
  it('status idle withdraws it; watching again lets the re-send draw it', () => {
    send('annotate', { marks: [textMark] })
    send('status', { state: 'idle' })
    assert.deepEqual(ids(), [])
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), [])
    send('status', { state: 'watching' })
    send('annotate', { marks: [textMark] })
    assert.deepEqual(ids(), ['os-s1-1'])
  })
  it('a new step clears idle; a reconnect replay of lesson.ready starts from live', () => {
    send('status', { state: 'idle' })
    send('step.started', { stepId: 's2', index: 1, title: 't', instructions: 'i' })
    send('annotate', { marks: [{ ...textMark, stepId: 's2' }] })
    assert.deepEqual(ids(), ['os-s1-1'])
    send('lesson.paused', { reason: 'network' })
    assert.deepEqual(ids(), [])
    send('lesson.ready', { lesson: { id: 'l1', mode: 'lesson' }, steps: [], replay: true })
    send('annotate', { marks: [{ ...textMark, stepId: 's2' }] })
    assert.deepEqual(ids(), ['os-s1-1'])
  })
})

describe('drawer collapse (onscreen.ts)', () => {
  const ready = (lesson: Record<string, unknown>, replay?: boolean): void => send('lesson.ready', { lesson: { id: 'l', title: 'A lesson', mode: 'lesson', ...lesson }, steps: [], ...(replay ? { replay } : {}) })

  it('an app lesson collapses the panel once, after the drawer opened it', () => {
    ready({ app: { tool: 'blender', label: 'Blender' } })
    assert.deepEqual(log, ['drawer:open'], 'nothing yet: it waits for the drawer handler')
    mock.timers.tick(0)
    assert.deepEqual(log, ['drawer:open', 'panel:collapse'])
    mock.timers.tick(60_000)
    assert.deepEqual(log, ['drawer:open', 'panel:collapse'], 'once')
  })
  it('never re-collapses after the learner opens it', () => {
    ready({ app: { tool: 'blender', label: 'Blender' } })
    mock.timers.tick(0)
    emitUi('panel', 'open')
    send('step.started', { stepId: 's2', index: 1, title: 't', instructions: 'i' })
    send('step.passed', { stepId: 's2' })
    mock.timers.tick(60_000)
    assert.deepEqual(log, ['drawer:open', 'panel:collapse', 'panel:open'])
  })
  it('a lesson without app does not collapse', () => {
    ready({})
    ready({ app: null })
    ready({ app: { label: 'No tool' } })
    ready({ app: { tool: '' } })
    mock.timers.tick(1000)
    assert.ok(!log.includes('panel:collapse'), log.join(','))
  })
  it('a replay does not collapse', () => {
    ready({ app: { tool: 'blender', label: 'Blender' } }, true)
    mock.timers.tick(1000)
    assert.deepEqual(log, ['drawer:open'])
  })
  it('two lesson.ready in one tick collapse once', () => {
    ready({ app: { tool: 'blender', label: 'Blender' } })
    ready({ app: { tool: 'blender', label: 'Blender' } })
    mock.timers.tick(0)
    assert.deepEqual(
      log.filter((l) => l === 'panel:collapse'),
      ['panel:collapse']
    )
  })
  it('a code lesson right after an app lesson cancels the pending collapse', () => {
    ready({ app: { tool: 'blender', label: 'Blender' } })
    ready({})
    mock.timers.tick(0)
    assert.ok(!log.includes('panel:collapse'))
  })
})
