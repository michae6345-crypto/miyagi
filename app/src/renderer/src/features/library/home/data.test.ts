/** Home v4's view model (home/data.ts): the week, the counts, the rows, first run. Run by test/v4home.test.ts. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { LibraryItem } from '../../../../../../../shared/contracts/events'
import type { DashData } from '../../dashboard/types'
import { agoLabel, buildHome, greeting, hoursMinutes, isFirstRun, leftLabel, lessonMeta, nextRows, passRows, sizeLabel, weekBars, weekStats } from './data'
import { sampleHome } from './sample'

// Tuesday Nov 24 2026, 19:30 local.
const NOW = new Date(2026, 10, 24, 19, 30).getTime()
const empty: DashData = { tracks: [], completed: [], inProgress: [], next: [], activity: null, review: null, settings: {} }
const item = (id: string, over: Partial<LibraryItem> = {}): LibraryItem => ({ id, title: id, steps: 5, estMinutes: 15, tools: ['jupyter'], ready: true, ...over })

test('greeting and labels', () => {
  assert.equal(greeting(NOW, 'Sam Rivera'), 'Good evening, Sam')
  assert.equal(greeting(new Date(2026, 10, 24, 9).getTime()), 'Good morning')
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
  assert.equal(weekStats(data, { minutes: { '2026-11-23': 20, '2026-11-24': 15, '2026-11-16': 99 } }, NOW).minutes, 35)
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
