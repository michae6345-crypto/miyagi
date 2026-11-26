/**
 * Plan rows and skill chips are clickable (Michael, Nov 25: Library > Browse plans > Intro to Blender, "these aren't
 * clickable"). Offline, with a fake bridge:
 *   - a plan page's lesson rows are focusable buttons-in-a-row (tabindex, pointer, aria-expanded) and its skill chips are
 *     buttons, on a catalog plan the learner hasn't added as well as on their own;
 *   - a row's Enter/Space opens it, but a key pressed on a chip inside it is the chip's;
 *   - a chip opens its skill on the Skills page (the peek when the graph has it, the search when it doesn't) and never
 *     fires the row under it;
 *   - Start lesson on a lesson of a plan not added yet adds the plan, then starts THAT lesson with plan {id, index};
 *   - Home's and Progress's plan rows open the plan's page; "Browse plans" opens Browse plans;
 *   - the start gate says why calmly (skipped, nothing to build from, offline).
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { beforeEach, describe, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'
import * as React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// Vite-only modules (import.meta.glob scenarios, the feature registry, assets) resolve to small stand-ins.
const dir = mkdtempSync(join(tmpdir(), 'plan-rows-'))
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
g.document = { documentElement: { dataset: { route: 'library' }, classList: { add: () => {}, remove: () => {} } }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined }, addEventListener: () => {}, querySelector: () => null, hidden: false }
g.location = { search: '' }
// tsx compiles .tsx with the classic runtime (React.createElement).
;(globalThis as { React?: unknown }).React = React
const h = React.createElement

const { dispatch } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const { useLesson } = require('../src/renderer/src/core/lesson') as typeof import('../src/renderer/src/core/lesson')
const plans = require('../src/renderer/src/features/plans/store') as typeof import('../src/renderer/src/features/plans/store')
const { planById, planStateFromCatalog } = require('../src/renderer/src/features/plans/catalog') as typeof import('../src/renderer/src/features/plans/catalog')
const ui = require('../src/renderer/src/features/plans/ui') as typeof import('../src/renderer/src/features/plans/ui')
const { lessonGate, rowLabel } = require('../src/renderer/src/features/plans/lessonRow') as typeof import('../src/renderer/src/features/plans/lessonRow')
const { PlanPage } = require('../src/renderer/src/features/plans/PlanPage') as typeof import('../src/renderer/src/features/plans/PlanPage')
const { showSkill, findSkill } = require('../src/renderer/src/features/skills/go') as typeof import('../src/renderer/src/features/skills/go')
const { useSkills } = require('../src/renderer/src/features/skills/store') as typeof import('../src/renderer/src/features/skills/store')
const { buildSkillGraph } = require('../src/renderer/src/features/skills/model') as typeof import('../src/renderer/src/features/skills/model')
const { useShell } = require('../src/renderer/src/features/shell/store') as typeof import('../src/renderer/src/features/shell/store')

type Seg = { type: string; payload: Record<string, unknown> }
const MOCK = JSON.parse(readFileSync(join(import.meta.dirname, '..', 'mock', 'scenarios', 'ui-v4.json'), 'utf8')) as { segments: Record<string, Seg[]> }
const PROGRESS = MOCK.segments.uiv4_progress.find((x) => x.type === 'progress')!.payload

const blender = planById('intro-blender')!
const reset = (): void => {
  sends.length = 0
  plans.usePlans.setState({ view: { kind: 'library' }, dialog: null, mine: [], fromEngine: false })
  useSkills.setState({ raw: undefined, selected: undefined, query: '', picker: false })
  useShell.setState({ page: 'home', visited: ['home'] })
}
type El = { props: Record<string, unknown> & { onClick?: (e?: unknown) => void; onKeyDown?: (e: unknown) => void } }
const key = (k: string, self: boolean): { key: string; target: object; currentTarget: object; preventDefault: () => void; stopPropagation: () => void; stopped: boolean } => {
  const row = {}
  const ev = { key: k, target: self ? row : {}, currentTarget: row, preventDefault: () => {}, stopped: false, stopPropagation: () => (ev.stopped = true) }
  return ev
}

describe('the plan page draws clickable rows and chips', () => {
  beforeEach(reset)
  test('a catalog plan the learner has not added: every lesson row is focusable, says it opens, and is not expanded', () => {
    const html = renderToStaticMarkup(h(PlanPage, { id: 'intro-blender' }))
    const rows = html.match(/<div role="row" tabindex="0"[^>]*data-plan-lesson="\d+"/g) ?? []
    assert.equal(rows.length, blender.lessons.length)
    for (const r of rows) {
      assert.match(r, /cursor-pointer/)
      assert.match(r, /mg-v4-row/)
      assert.match(r, /aria-expanded="false"/)
      assert.match(r, /\. Open\./)
    }
  })
  test('the header Grows list and the rows Grows column are skill buttons', () => {
    const html = renderToStaticMarkup(h(PlanPage, { id: 'intro-blender' }))
    const chips = html.match(/<button type="button" data-skill-chip="[^"]+"/g) ?? []
    // Every skill of the plan in the header, and every row's skills in the table.
    const expected = blender.skills.length + blender.lessons.reduce((n, l) => n + l.grows.length, 0)
    assert.equal(chips.length, expected)
    assert.ok(chips.some((c) => c.includes('data-skill-chip="bl.transform"')))
  })
  test('the project checklist has no empty circles that read as checkboxes', () => {
    const html = renderToStaticMarkup(h(PlanPage, { id: 'intro-blender' }))
    const project = html.slice(html.indexOf('data-plan-project'))
    assert.doesNotMatch(project.slice(0, project.indexOf('</section>')), /lucide-circle/)
  })
})

describe('TableRow', () => {
  test('with onClick: Enter and Space on the row open it; a key from a control inside it does not', () => {
    let opened = 0
    const el = ui.TableRow({ template: '1fr', children: 'x', onClick: () => opened++ }) as unknown as El
    assert.equal(el.props.tabIndex, 0)
    el.props.onKeyDown!(key('Enter', true))
    el.props.onKeyDown!(key(' ', true))
    assert.equal(opened, 2)
    el.props.onKeyDown!(key('Enter', false))
    assert.equal(opened, 2)
  })
  test('without onClick: no tab stop, no hover class, no pointer (it must not look clickable)', () => {
    const el = ui.TableRow({ template: '1fr', children: 'x' }) as unknown as El
    assert.equal(el.props.tabIndex, undefined)
    assert.doesNotMatch(String(el.props.className), /mg-v4-row|cursor-pointer/)
  })
  test('aria-expanded and aria-controls follow the row', () => {
    const open = ui.TableRow({ template: '1fr', children: 'x', onClick: () => {}, expanded: true, controls: 'p1' }) as unknown as El
    assert.equal(open.props['aria-expanded'], true)
    assert.equal(open.props['aria-controls'], 'p1')
    assert.equal(rowLabel('Move, rotate and scale', 2, false), 'Move, rotate and scale. Lesson 2. Open.')
  })
})

describe('skill chips open the skill on the Skills page', () => {
  beforeEach(reset)
  test('no graph yet: Skills page, the skill searched by name, the id kept for when the graph lands', () => {
    assert.equal(showSkill({ id: 'bl.transform', label: 'Transforms' }), 'search')
    assert.equal(useShell.getState().page, 'skills')
    assert.equal(useSkills.getState().query, 'Transforms')
    assert.equal(useSkills.getState().selected, 'bl.transform')
  })
  test('with the graph: the peek opens on it and the search is cleared', () => {
    useSkills.setState({ raw: PROGRESS, query: 'old' })
    const graph = buildSkillGraph(PROGRESS, Date.now())!
    const id = graph.nodes.find((n) => n.kind !== 'capstone')!.id
    assert.equal(showSkill({ id }), 'peek')
    assert.equal(useSkills.getState().selected, id)
    assert.equal(useSkills.getState().query, '')
    // A label alone finds the same node (a table tag knows only the name).
    assert.equal(findSkill(graph, { label: graph.byId[id].label.toUpperCase() }), id)
  })
  test('a chip click stops at the chip (the row under it does not open) and goes to Skills', () => {
    const el = ui.SkillChip({ children: 'Transforms', skill: { id: 'bl.transform', label: 'Transforms' } }) as unknown as El
    const ev = key('Enter', false)
    el.props.onClick!(ev)
    assert.equal(ev.stopped, true)
    assert.equal(useShell.getState().page, 'skills')
    const k = key('Enter', false)
    el.props.onKeyDown!(k)
    assert.equal(k.stopped, true)
  })
  test('a chip with no skill stays a plain label', () => {
    const el = ui.SkillChip({ children: 'Viewport' }) as unknown as { type: string }
    assert.equal(el.type, 'span')
  })
})

describe('starting a lesson from its row', () => {
  beforeEach(() => {
    reset()
    mock.timers.enable({ apis: ['setTimeout'] })
  })
  test('a plan not added yet: plan.start, then THAT lesson with plan {id, index}', () => {
    plans.startPlan(blender, 3)
    const start = sends.find((m) => m.type === 'plan.start')
    assert.equal(start?.payload.catalogId, 'intro-blender')
    // The engine answers with the plan it added.
    dispatch({ type: 'plans', payload: { reqId: start!.payload.reqId, items: [planStateFromCatalog(blender)] } } as never)
    const learn = sends.find((m) => m.type === 'learn')
    assert.deepEqual(learn?.payload.plan, { id: 'intro-blender', index: 3 })
    assert.equal(learn?.payload.query, blender.lessons[3].goal)
    mock.timers.reset()
  })
  test('no engine answer: the local plan starts that lesson after the wait', () => {
    plans.startPlan(blender, 5)
    mock.timers.tick(3000)
    const learn = sends.find((m) => m.type === 'learn')
    assert.deepEqual(learn?.payload.plan, { id: 'intro-blender', index: 5 })
    mock.timers.reset()
  })
  test('a plan the learner has: that lesson at once, no plan.start', () => {
    plans.usePlans.setState({ mine: [planStateFromCatalog(blender, 1)] })
    plans.startPlan(blender, 4)
    assert.equal(sends.some((m) => m.type === 'plan.start'), false)
    assert.deepEqual(sends.find((m) => m.type === 'learn')?.payload.plan, { id: 'intro-blender', index: 4 })
    mock.timers.reset()
  })
  test('Start plan (no index) still starts the next lesson', () => {
    plans.usePlans.setState({ mine: [planStateFromCatalog(blender, 2)] })
    plans.startPlan(blender)
    assert.deepEqual(sends.find((m) => m.type === 'learn')?.payload.plan, { id: 'intro-blender', index: 2 })
    mock.timers.reset()
  })
})

describe('the start gate says why, calmly', () => {
  const on = { connected: true, name: 'miyagi' }
  test('ready, in progress, passed', () => {
    assert.deepEqual(lessonGate({ passed: false, startable: true }, on), { can: true, label: 'Start lesson' })
    assert.equal(lessonGate({ passed: false, startable: true, state: 'in_progress' }, on).label, 'Continue lesson')
    assert.equal(lessonGate({ passed: true, startable: true, state: 'done' }, on).label, 'Start again')
  })
  test('skipped, nothing to build from, offline: no start and one short line', () => {
    for (const [l, ctx, why] of [
      [{ passed: false, startable: true, state: 'skipped' as const }, on, 'Left out of this plan.'],
      [{ passed: false, startable: false }, on, 'This lesson isn’t ready yet.'],
      [{ passed: false, startable: true }, { connected: false, name: 'miyagi' }, 'Starts once miyagi connects.']
    ] as const) {
      const gate = lessonGate(l, ctx)
      assert.equal(gate.can, false)
      assert.equal(gate.why, why)
      assert.ok(gate.why!.split(' ').length <= 12)
      assert.doesNotMatch(gate.why!, /—/)
    }
  })
  test('the row preview reads connected from the lesson store', () => {
    assert.equal(typeof useLesson.getState().connected, 'boolean')
  })
})

describe('plan rows elsewhere open the plan', () => {
  beforeEach(reset)
  test('openPlan: the Library page on that plan (a preset on its catalog page)', () => {
    plans.usePlans.setState({ mine: [{ ...planStateFromCatalog(blender, 1), id: 'p-77', catalogId: 'intro-blender' }] })
    plans.openPlan('p-77')
    assert.equal(useShell.getState().page, 'lessons')
    assert.deepEqual(plans.usePlans.getState().view, { kind: 'plan', id: 'intro-blender' })
  })
  test('openPlan on a plan of the learner own (a playlist plan) opens its own page', () => {
    plans.usePlans.setState({ mine: [{ ...planStateFromCatalog(blender), id: 'pl-abc', catalogId: undefined, source: 'playlist' }] })
    plans.openPlan('pl-abc')
    assert.deepEqual(plans.usePlans.getState().view, { kind: 'custom', id: 'pl-abc' })
  })
  test('openBrowsePlans: Browse plans, not the Library list', () => {
    plans.openBrowsePlans()
    assert.equal(useShell.getState().page, 'lessons')
    assert.deepEqual(plans.usePlans.getState().view, { kind: 'plans' })
  })
})
