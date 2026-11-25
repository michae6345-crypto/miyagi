/**
 * On-screen coach (Nov 24), offline, with mock timers and no window:
 *   - store.ts: a text mark has no hold timer (it stays while its step is live), a plain mark still fades at 6 s; what
 *     takes a text mark away (another step, step.passed, Esc, annotate {clear}, a new lesson, not a replay).
 *   - onscreen.ts: lesson.ready with lesson.app asks core's `panel` UI event to collapse, once, after the drawer's own
 *     lesson.ready handler; never without app, never on a replay.
 * `node --import tsx --test src/renderer/src/features/annotate/onscreen.test.ts`
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, it, mock } from 'node:test'
import { pathToFileURL } from 'node:url'

// store.ts imports the spotlight store and core/shortcuts late (its spotlight bridge); they pull in the whole renderer.
// Here they are inert stand-ins: nothing in these tests goes through the bridge.
const dir = mkdtempSync(join(tmpdir(), 'onscreen-'))
const STUB = pathToFileURL(join(dir, 'stub.mjs')).href
writeFileSync(join(dir, 'stub.mjs'), 'const store = { subscribe: () => () => {}, getState: () => ({}) }\nexport const useSpotlight = store\nexport const usePressed = store\n')
registerHooks({
  resolve(specifier, context, next) {
    if (context.parentURL?.includes('/features/annotate/store') && /(spotlight\/store|core\/shortcuts)$/.test(specifier)) return { url: STUB, shortCircuit: true }
    return next(specifier, context)
  }
})

mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 1_000_000 })

const { dispatch, emitUi, onMessage, onUi } = require('../../core/bus') as typeof import('../../core/bus')
const { useAnnotate } = require('./store') as typeof import('./store')
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

describe('text mark hold (store.ts)', () => {
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
  it('Esc removes it, and a re-send this step does not bring it back', () => {
    send('annotate', { marks: [textMark] })
    emitUi('dismiss')
    assert.deepEqual(ids(), [])
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
