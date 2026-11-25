/** Home v4's view model (home/data.ts): the week, the counts, the rows, first run. Run by test/v4home.test.ts. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import type { Activity, LibraryItem, PlanState } from '../../../../../../../shared/contracts/events'
import { FEATURED, IDEAS, starters } from './catalog'
import type { DashData } from '../../dashboard/types'
import { agoLabel, buildHome, coverForTool, firstLessons, fromContract, hoursMinutes, railParts, isFirstRun, leftLabel, lessonMeta, nextRows, passRows, sizeLabel, weekBars, weekStats } from './data'
import { sampleHome } from './sample'

// Tuesday Nov 24 2026, 19:30 local.
const NOW = new Date(2026, 10, 24, 19, 30).getTime()
const empty: DashData = { tracks: [], completed: [], inProgress: [], next: [], activity: null, review: null, settings: {} }
const item = (id: string, over: Partial<LibraryItem> = {}): LibraryItem => ({ id, title: id, steps: 5, estMinutes: 15, tools: ['jupyter'], ready: true, ...over })

test('labels', () => {
  assert.deepEqual(hoursMinutes(108), [['1', 'h'], ['48', 'min']])
  assert.deepEqual(hoursMinutes(22), [['22', 'min']])
  assert.equal(leftLabel(180), 'about 3 hours left')
  assert.equal(sizeLabel(150), 'about 2.5 hr')
  assert.equal(agoLabel(NOW - 12 * 86_400_000, NOW), '12 days ago')
  assert.equal(lessonMeta({ tools: ['jupyter'], steps: 6, estMinutes: 15 }), 'Jupyter · 6 steps · 15 min')
})

test('the week runs Monday to Sunday, today marked, later days empty', () => {
  const data: DashData = { ...empty, activity: [ { date: '2026-11-23', reps: 3, assisted: 0, hints: 0 }, { date: '2026-11-24', reps: 2, assisted: 0, hints: 0 } ] }
  const bars = weekBars(data, {}, NOW)
  assert.equal(bars.length, 7)
  assert.deepEqual(bars.map((b) => b.value), [3, 2, 0, 0, 0, 0, 0])
  assert.equal(bars.findIndex((b) => b.today), 1)
  assert.ok(bars[2].future)
  assert.equal(weekStats(data, {}, NOW).steps, 5)
  assert.equal(weekStats(data, {}, NOW).minutes, undefined)
  assert.deepEqual(weekStats(data, { week: { minutes: 35, steps: 4, mastered: 1 }, minutesTracked: true }, NOW), { minutes: 35, steps: 4, mastered: 1 })
  assert.equal(weekStats(data, { week: { minutes: 35, steps: 4, mastered: 1 }, minutesTracked: false }, NOW).minutes, undefined)
})

// The contract's own mock (app/mock/scenarios/ui-v4.json): activity and plans as the engine sends them.
const scenario = JSON.parse(readFileSync(new URL('../../../../../../mock/scenarios/ui-v4.json', import.meta.url), 'utf8')) as { segments: Record<string, Array<{ type?: string; payload?: unknown }>> }
const sent = <T,>(seg: string, type: string): T => scenario.segments[seg].find((m) => m.type === type)!.payload as T

test('ui-v4 activity and plans map to the week, the numbers, passes, plans, up next and the goal', () => {
  const activity = sent<Activity>('uiv4_activity', 'activity')
  const plans = sent<{ items: PlanState[] }>('uiv4_plans', 'plans').items
  const parts = fromContract({ activity, plans, names: new Map([['bl.materials', 'Materials']]) })
  const bars = weekBars(undefined, parts, NOW)
  assert.deepEqual(bars.map((b) => b.value), [0, 22, 41, 0, 18, 12, 15])
  assert.deepEqual(bars.map((b) => b.label).join(''), 'MTWTFSS')
  assert.ok(bars[6].today && !bars.some((b) => b.future))
  assert.deepEqual(weekStats(undefined, parts, NOW), { minutes: 108, steps: 6, mastered: 2 })
  const m = buildHome({ items: [], extra: parts, now: NOW, skip: new Set(), done: new Set() })
  assert.equal(m.passes[0].step, 'Add one row to every row')
  assert.equal(m.passes[0].skill, 'Forward pass')
  assert.ok(!m.passes.some((p) => p.lesson))
  assert.deepEqual(m.plans.map((p) => `${p.title} ${p.done}/${p.total} ${p.next}`).slice(0, 2), ['Neural networks from scratch 3/9 The forward pass', 'Intro to Blender 6/10 Subdivision and smooth shading'])
  assert.ok(m.next.length >= 2)
  assert.equal(m.next.find((n) => n.title === 'Give it a material')?.skill, 'Materials')
  assert.equal(m.goal?.unit, 'lessons')
  assert.equal(isFirstRun(undefined, [], parts), false)
  // minutesTracked false: the bars count steps and there is no minutes number.
  const steps = fromContract({ activity: { ...activity, minutesTracked: false } })
  assert.deepEqual(weekBars(undefined, steps, NOW).map((b) => b.value), [0, 1, 2, 0, 1, 1, 1])
  assert.equal(weekStats(undefined, steps, NOW).minutes, undefined)
})

test('start here comes from the catalog plans, leaving out plans already added', () => {
  const s = starters()
  assert.deepEqual(s.map((p) => p.id), ['intro-python', 'intro-blender', 'intro-cad'])
  assert.equal(s[0].ends, 'Ends with a number guessing game')
  assert.equal(sizeLabel(s[0].minutes), 'about 3 hr')
  assert.deepEqual(starters(new Set(['intro-blender'])).map((p) => p.id), ['intro-python', 'intro-cad'])
  assert.equal(coverForTool('blender'), 'mug')
})

test('up next leaves out what is on Continue, finished or started', () => {
  const items = [item('a'), item('b', { progress: { stepIndex: 1, stepTitle: 'x', total: 5 } }), item('c'), item('d', { ready: false }), item('e')]
  assert.deepEqual(nextRows(items, empty, new Set(['a']), new Set(['e'])).map((r) => r.id), ['c'])
})

test('recently passed falls back to finished lessons, newest first', () => {
  const data: DashData = { ...empty, completed: [ { lessonId: 'x', title: 'Old', finishedAt: 1 }, { lessonId: 'y', title: 'New', finishedAt: 5 }, { lessonId: 'z', title: 'No time' } ] }
  const rows = passRows(data, {})
  assert.deepEqual(rows.map((r) => r.step), ['New', 'Old'])
  assert.ok(rows.every((r) => r.lesson))
  assert.equal(passRows(data, { passes: [{ key: 'p', at: 9, step: 'A step', skill: 'Loops' }] })[0].step, 'A step')
})

test('first run: nothing started, nothing finished, no skill touched', () => {
  assert.equal(isFirstRun(empty, [item('a')], {}), true)
  assert.equal(isFirstRun(empty, [item('a', { progress: { stepIndex: 1, stepTitle: 'x', total: 5 } })], {}), false)
  assert.equal(isFirstRun({ ...empty, completed: [{ lessonId: 'x', title: 'X' }] }, [], {}), false)
})

test('the featured lesson leads: first card and first idea, the curated goal', () => {
  assert.equal(FEATURED.title, 'A neural net from scratch')
  assert.equal(FEATURED.goal, 'build a neural network from scratch')
  assert.equal(IDEAS[0], 'Build a neural network from scratch')
  assert.ok(!IDEAS.some((t) => /image classifier/i.test(t)))
})

test('first-run rows: saved lessons ready to start first, then suggestions, three at most', () => {
  const picks = [
    { id: 's1', title: 'S1', meta: 'm', cover: 'code' as const, goal: 'g1' },
    { id: 's2', title: 'S2', meta: 'm', cover: 'code' as const, goal: 'g2' },
    { id: 's3', title: 'S3', meta: 'm', cover: 'code' as const, goal: 'g3' }
  ]
  assert.deepEqual(firstLessons([], new Set(), picks).map((r) => r.id), ['s1', 's2', 's3'])
  const rows = firstLessons([item('a'), item('b', { ready: false }), item('c')], new Set(['c']), picks)
  assert.deepEqual(rows.map((r) => r.id), ['a', 's1', 's2'])
  assert.equal(rows[0].saved, true)
  assert.equal(rows[1].goal, 'g1')
})

test('the rail shows only parts with something in them', () => {
  const m = buildHome({ data: empty, items: [], extra: {}, now: NOW, skip: new Set(), done: new Set() })
  assert.deepEqual(railParts(m), { week: false, goal: false, skills: false, fresh: false, any: false })
  const s = sampleHome(NOW)
  const full = buildHome({ data: s.data, items: s.items, extra: s.extra, now: NOW, skip: new Set(), done: new Set() })
  assert.equal(railParts(full).any, true)
  // Steps counted but no bar this week: no chart of zeros, the rail stays empty.
  const noBars = { ...m, stats: { steps: 0, mastered: 0 } }
  assert.equal(railParts(noBars).week, false)
})

test('the sample learner builds the mock page with no zero rows', () => {
  const s = sampleHome(NOW)
  const m = buildHome({ data: s.data, items: s.items, extra: s.extra, now: NOW, skip: new Set(), done: new Set() })
  assert.equal(m.plans.length, 2)
  assert.equal(m.next.length, 4)
  assert.equal(m.passes.length, 5)
  assert.equal(m.skills.length, 6)
  assert.ok(m.skills.every((r) => r.total > 0))
  assert.equal(m.fresh.map((f) => f.label).join(','), 'Functions,DataFrames')
  assert.equal(m.goal?.total, 13)
})
