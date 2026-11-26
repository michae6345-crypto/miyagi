/**
 * Stop a lesson or remove a plan midway (a tester, Nov 25: "Let's say midway I want to just remove the plan ... click on
 * it ... it still doesn't do that"). Offline, with a fake bridge:
 *   - removing a plan whose plan.start answer is still on its way never starts its lesson, and the answer (or any later
 *     push still carrying it) does not bring it back; the engine is asked to remove it again, once;
 *   - adding the same plan again afterwards counts as usual;
 *   - the building pill opens the build card (Stop building) at any point of a build, even after Keep working;
 *   - Stop building's two taps send end_lesson;
 *   - the pill's "Planning your lesson…" ends with a learner stop, but not with the old lesson's end as a new one starts.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { beforeEach, describe, test } from 'node:test'
import { pathToFileURL } from 'node:url'

const dir = mkdtempSync(join(tmpdir(), 'stop-midway-'))
const stub = (name: string, source: string): string => (writeFileSync(join(dir, name), source), pathToFileURL(join(dir, name)).href)
const EMPTY = stub('empty.mjs', 'export const scenarios = {}\nexport const defineFeature = (f) => f\nexport default ""')
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier) || (context.parentURL?.includes('/src/renderer/') && /(^|\/)registry$/.test(specifier))) return { url: EMPTY, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})

// cards/panel.ts (imported by the pill store) looks one module up with import.meta.glob (Vite only): here it finds
// nothing. tsx compiles the renderer as CommonJS through require.extensions, so the call is swapped in its output
// (as test/bonLive.test.ts does).
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

const sends: { type: string; payload: Record<string, unknown> }[] = []
const g = globalThis as unknown as Record<string, unknown>
const noop = (): (() => void) => () => {}
const tut = {
  platform: { os: 'darwin', keys: {}, pillTop: 0 },
  onEvent: noop,
  onStatus: noop,
  on: noop,
  onFeature: noop,
  emit: () => {},
  ready: () => {},
  send: (m: { type: string; payload: Record<string, unknown> }) => void sends.push(m),
  invoke: () => Promise.resolve(null)
}
g.window = { tut, devicePixelRatio: 2, innerWidth: 1440, innerHeight: 900, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
g.document = { documentElement: { dataset: { route: 'overlay' }, classList: { add: () => {}, remove: () => {} } }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined }, addEventListener: () => {}, querySelector: () => null, hidden: false }
g.location = { search: '' }
g.innerWidth = 1440
g.innerHeight = 900

const { dispatch } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const plans = require('../src/renderer/src/features/plans/store') as typeof import('../src/renderer/src/features/plans/store')
const { planById, planStateFromCatalog } = require('../src/renderer/src/features/plans/catalog') as typeof import('../src/renderer/src/features/plans/catalog')
const building = require('../src/renderer/src/features/building/store') as typeof import('../src/renderer/src/features/building/store')
const { usePill } = require('../src/renderer/src/features/pill/store') as typeof import('../src/renderer/src/features/pill/store')

type Msg = Parameters<typeof dispatch>[0]
const ev = (type: string, payload: Record<string, unknown>): Msg => ({ type, payload }) as unknown as Msg
const starts = (): string[] => sends.filter((m) => ['learn', 'learn_url', 'library.start'].includes(m.type)).map((m) => m.type)

const blender = planById('intro-blender')!
const reset = (): void => {
  sends.length = 0
  plans._resetRemoved()
  plans.usePlans.setState({ view: { kind: 'library' }, dialog: null, mine: [], fromEngine: false })
  building.useBuildCard.setState({ open: false, dismissed: false, armed: false })
  usePill.setState({ planning: false })
}

describe('removing a plan midway', () => {
  beforeEach(reset)

  test('a plan removed while its plan.start answer is on its way never starts, and the answer does not bring it back', () => {
    plans.startPlan(blender)
    const start = sends.find((m) => m.type === 'plan.start')!
    assert.ok(start, 'plan.start sent')
    assert.ok(plans.myPlan('intro-blender'), 'shown at once')
    plans.removePlan('intro-blender')
    assert.equal(plans.myPlan('intro-blender'), undefined)
    assert.deepEqual(sends.filter((m) => m.type === 'plan.remove').map((m) => m.payload.id), ['intro-blender'])

    // The engine finished the plan.start after the remove (they run beside each other): its answer still has the plan.
    dispatch(ev('plans', { items: [planStateFromCatalog(blender)], reqId: start.payload.reqId }))
    assert.equal(plans.myPlan('intro-blender'), undefined, 'not back on screen')
    assert.deepEqual(starts(), [], 'its lesson never starts')
    assert.equal(sends.filter((m) => m.type === 'plan.remove').length, 2, 'removed again, once')

    dispatch(ev('plans', { items: [planStateFromCatalog(blender)] }))
    assert.equal(plans.myPlan('intro-blender'), undefined)
    assert.equal(sends.filter((m) => m.type === 'plan.remove').length, 2, 'never a loop of removes')
    assert.deepEqual(starts(), [])
  })

  test('the plan page goes back to the Library when its plan is removed', () => {
    plans.usePlans.setState({ mine: [planStateFromCatalog(blender, 1)], view: { kind: 'plan', id: 'intro-blender' } })
    plans.removePlan('intro-blender')
    assert.deepEqual(plans.usePlans.getState().view, { kind: 'library' })
  })

  test('adding the plan again after removing it counts as usual', () => {
    plans.usePlans.setState({ mine: [planStateFromCatalog(blender, 1)] })
    plans.removePlan('intro-blender')
    sends.length = 0
    plans.startPlan(blender)
    const start = sends.find((m) => m.type === 'plan.start')!
    dispatch(ev('plans', { items: [planStateFromCatalog(blender)], reqId: start.payload.reqId }))
    assert.ok(plans.myPlan('intro-blender'))
    assert.equal(starts().length, 1, 'its first lesson starts')
    assert.equal(sends.filter((m) => m.type === 'plan.remove').length, 0)
  })

  test('a goal plan removed and added again in the same run is shown and started, whatever id the engine gives it', () => {
    const proposal = { source: 'goal', title: 'Make coffee', lessons: [{ title: 'Grind', goal: 'grind beans' }, { title: 'Brew', goal: 'brew it' }] }
    // The engine's id for a goal plan is goal-<hash>; the app's stand-in is goal-<slug>.
    const engine = (): Record<string, unknown> => ({ id: 'goal-1a2b3c4d', source: 'goal', goal: 'make coffee', title: 'Make coffee', done: 0, total: 2, nextIndex: 0, lessons: [{ title: 'Grind', goal: 'grind beans', state: 'next' }, { title: 'Brew', goal: 'brew it', state: 'todo' }] })
    plans.addGoalPlan('make coffee', proposal as never)
    let start = sends.filter((m) => m.type === 'plan.start').pop()!
    dispatch(ev('plans', { items: [engine()], reqId: start.payload.reqId }))
    assert.ok(plans.myPlan('goal-1a2b3c4d'))
    plans.removePlan('goal-1a2b3c4d')
    dispatch(ev('plans', { items: [] }))
    sends.length = 0
    plans.addGoalPlan('make coffee', proposal as never)
    start = sends.filter((m) => m.type === 'plan.start').pop()!
    dispatch(ev('plans', { items: [engine()], reqId: start.payload.reqId }))
    assert.ok(plans.myPlan('goal-1a2b3c4d'), 'shown again')
    assert.equal(sends.filter((m) => m.type === 'plan.remove').length, 0, 'never removed again')
    assert.deepEqual(starts(), ['learn'], 'its first lesson starts')
  })

  test('a removed goal plan stays hidden under the engine id from an answer still on its way', () => {
    plans.usePlans.setState({ mine: [{ id: 'goal-make-coffee', source: 'goal', goal: 'make coffee', title: 'Make coffee', done: 0, total: 1, nextIndex: 0, lessons: [{ title: 'Grind', goal: 'g', state: 'next' }] } as never] })
    plans.removePlan('goal-make-coffee')
    dispatch(ev('plans', { items: [{ id: 'goal-1a2b3c4d', source: 'goal', goal: 'Make coffee ', title: 'Make coffee', done: 0, total: 1, nextIndex: 0, lessons: [{ title: 'Grind', goal: 'g', state: 'next' }] }] }))
    assert.deepEqual(plans.usePlans.getState().mine, [])
    assert.deepEqual(sends.filter((m) => m.type === 'plan.remove').map((m) => m.payload.id), ['goal-make-coffee', 'goal-1a2b3c4d'])
  })

  test('another plan in the same answer is kept', () => {
    plans.usePlans.setState({ mine: [planStateFromCatalog(blender, 1)] })
    plans.removePlan('intro-blender')
    const other = PLANS_OTHER()
    dispatch(ev('plans', { items: [planStateFromCatalog(blender), planStateFromCatalog(other)] }))
    assert.deepEqual(plans.usePlans.getState().mine.map((m) => m.id), [other.id])
  })
})

/** Any catalog plan but intro-blender. */
function PLANS_OTHER(): NonNullable<ReturnType<typeof planById>> {
  const ids = ['neural-networks', 'intro-python', 'intro-c']
  for (const id of ids) {
    const p = planById(id)
    if (p) return p
  }
  throw new Error('no second catalog plan')
}

describe('stopping a build midway', () => {
  beforeEach(reset)

  test('the building pill opens the build card at any point, even after Keep working', () => {
    dispatch(ev('lesson.building', { message: 'Planning the lesson', progress: 0.1, stage: 'planning' }))
    assert.equal(building.useBuildCard.getState().open, true)
    building.keepWorking()
    assert.equal(building.useBuildCard.getState().open, false)
    dispatch(ev('lesson.building', { message: 'Writing step 4', progress: 0.5, stage: 'steps' }))
    assert.equal(building.useBuildCard.getState().open, false, 'Keep working holds for the rest of this build')
    building.openBuildCard() // the pill's click
    assert.equal(building.useBuildCard.getState().open, true)
  })

  test('the card opens from the pill before the engine said anything (an old engine, or "Planning your lesson…")', () => {
    building.openBuildCard()
    assert.equal(building.useBuildCard.getState().open, true)
  })

  test('Stop building takes two taps, then sends end_lesson and closes the card', () => {
    building.openBuildCard()
    building.tapStop({ detail: 1 }, 1000)
    assert.equal(sends.length, 0)
    assert.equal(building.useBuildCard.getState().armed, true)
    building.tapStop({ detail: 1 }, 1000 + building.CONFIRM_MIN_MS)
    assert.deepEqual(sends.map((m) => m.type), ['end_lesson'])
    assert.equal(building.useBuildCard.getState().open, false)
    dispatch(ev('lesson.ended', { reason: 'stopped' }))
    dispatch(ev('lesson.building', { message: 'Planning the lesson', progress: 0.1, stage: 'planning' }))
    assert.equal(building.useBuildCard.getState().open, true, 'the next build opens it again')
  })

  test('one double-click on Stop building is not two taps: it stays armed and sends nothing', () => {
    building.openBuildCard()
    building.tapStop({ detail: 1 }, 1000)
    building.tapStop({ detail: 2 }, 1400) // the double-click's second click, even after CONFIRM_MIN_MS
    building.tapStop({ detail: 1 }, 1100) // or any confirm sooner than CONFIRM_MIN_MS
    assert.deepEqual(sends, [])
    assert.equal(building.useBuildCard.getState().armed, true)
    building.tapStop({ detail: 1 }, 2000)
    assert.deepEqual(sends.map((m) => m.type), ['end_lesson'])
  })

  test('a lone second click of a double-click never arms by itself; the keyboard (detail 0) works', () => {
    building.openBuildCard()
    building.tapStop({ detail: 2 }, 1000)
    assert.equal(building.useBuildCard.getState().armed, false)
    building.tapStop({ detail: 0 }, 1000)
    building.tapStop({ detail: 0 }, 1500)
    assert.deepEqual(sends.map((m) => m.type), ['end_lesson'])
  })

  test('isRushedConfirm', () => {
    assert.equal(building.isRushedConfirm(0, building.CONFIRM_MIN_MS - 1, 1), true)
    assert.equal(building.isRushedConfirm(0, building.CONFIRM_MIN_MS, 1), false)
    assert.equal(building.isRushedConfirm(0, 5000, 2), true)
    assert.equal(building.isRushedConfirm(0, 5000, undefined), false)
  })

  test('"Planning your lesson…" ends with a learner stop, not with the old lesson ending as a new one starts', () => {
    usePill.setState({ planning: true })
    dispatch(ev('lesson.ended', { lessonId: 'old', reason: 'new lesson' }))
    assert.equal(usePill.getState().planning, true)
    dispatch(ev('lesson.ended', { reason: 'stopped' }))
    assert.equal(usePill.getState().planning, false)
  })
})
