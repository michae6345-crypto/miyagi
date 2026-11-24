/**
 * The v4 Progress page's data (features/progress/v4/model.ts): what it reads from the UI-V4 messages (`activity`,
 * `bon`, `plans`) and from `progress`, and the numbers it shows. The contract payloads come from
 * mock/scenarios/ui-v4.json, the contract's own mock.
 * Run: node --import tsx --import ./test/setup.mjs --test test/progressV4.test.ts
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, it } from 'node:test'
import {
  aboutHr,
  allNums,
  bonSteps,
  closest,
  dayKey,
  EMPTY_V4,
  freshLabel,
  fromGraph,
  goalLine,
  guide,
  hm,
  lastPassed,
  plain,
  railGoal,
  readActivity,
  readBon,
  readPlans,
  readV4,
  weekBars,
  weekNums,
  weeks12,
  whenLabel,
  type V4
} from '../src/renderer/src/features/progress/v4/model'
import { buildSkillGraph } from '../src/renderer/src/features/skills/model'
import { fromContract, planGoalFor } from '../src/renderer/src/features/library/home/data'
import type { Activity, PlanState } from '../../shared/contracts/events'

// Sunday Nov 22 2026, 6 PM local (the mock's today).
const NOW = new Date(2026, 10, 22, 18, 0).getTime()
const day = (back: number): string => dayKey(new Date(2026, 10, 22 - back, 12).getTime())
const v4 = (part: Partial<V4>): V4 => ({ ...EMPTY_V4, ...part })

type Seg = { type: string; payload: Record<string, unknown> }
const MOCK = JSON.parse(readFileSync(join(import.meta.dirname, '..', 'mock', 'scenarios', 'ui-v4.json'), 'utf8')) as { segments: Record<string, Seg[]> }
const first = (seg: string, type: string): Record<string, unknown> => {
  const e = MOCK.segments[seg].find((x) => x.type === type)
  assert.ok(e, `${seg} has ${type}`)
  return e.payload
}
const ACTIVITY = first('uiv4_activity', 'activity')
const DAYS = ACTIVITY.days as Array<{ date: string; minutes: number; steps: number }>

describe('activity (ui-v4 mock)', () => {
  const v = v4(readActivity(ACTIVITY))
  it('reads the 84 days, today last, in minutes', () => {
    assert.equal(DAYS.length, 84)
    assert.equal(v.days.size, 84)
    assert.equal(v.today, DAYS[83].date)
    assert.equal(v.activitySeen, true)
    assert.equal(v.minutesKnown, true)
  })
  it('the week chart is the last 7 days, today last', () => {
    const b = weekBars(v, Date.now())
    assert.deepEqual(
      b.map((x) => x.key),
      DAYS.slice(-7).map((d) => d.date)
    )
    assert.deepEqual(
      b.map((x) => x.value),
      DAYS.slice(-7).map((d) => d.minutes)
    )
    assert.equal(b[6].now, true)
    assert.equal(b.filter((x) => x.now).length, 1)
  })
  it('12 weeks are Monday-to-Sunday sums of the 84 days', () => {
    const w = weeks12(v, Date.now())
    assert.equal(w.length, 12)
    // The mock's today is a Sunday, so the 84 days are exactly 12 Monday-to-Sunday weeks.
    const sums = Array.from({ length: 12 }, (_, i) => DAYS.slice(i * 7, i * 7 + 7).reduce((n, d) => n + d.minutes, 0))
    assert.deepEqual(
      w.map((x) => x.value),
      sums
    )
    assert.equal(new Date(`${w[0].key}T12:00:00`).getDay(), 1)
    assert.equal(w[11].label, 'Now')
    assert.equal(w[11].value, 108)
  })
  it('the week numbers and the totals are the engine\'s', () => {
    assert.deepEqual(weekNums(v, Date.now()), { minutes: 108, steps: 6, mastered: 2 })
    assert.deepEqual(allNums(v, 0), { minutes: 959, steps: 58, lessons: 4 })
    assert.equal(v.totals.mastered, 11)
  })
  it('recent rows: ISO `at`, newest first, the first skill, the lesson', () => {
    const recent = ACTIVITY.recent as Array<{ at: string; stepTitle: string; skills: string[]; lessonTitle: string }>
    assert.equal(v.passes.length, recent.length)
    assert.equal(v.passes[0].at, Date.parse(recent[0].at))
    assert.equal(v.passes[0].at, Date.parse('2026-11-22T16:12:00-08:00'))
    assert.equal(v.passes[0].step, recent[0].stepTitle)
    assert.equal(v.passes[0].skill, recent[0].skills[0])
    assert.equal(v.passes[0].lesson, recent[0].lessonTitle)
    for (let i = 1; i < v.passes.length; i++) assert.ok(v.passes[i - 1].at >= v.passes[i].at)
  })
  it('the newest pass per skill (a track\'s Last practiced)', () => {
    const last = lastPassed(v)
    assert.equal(last.get('forward pass'), Date.parse('2026-11-22T16:12:00-08:00'))
  })
  it('steps mode when minutesTracked is false: no minutes anywhere', () => {
    const s = v4(readActivity({ ...ACTIVITY, minutesTracked: false }))
    assert.equal(s.minutesKnown, false)
    assert.deepEqual(
      weekBars(s, Date.now()).map((x) => x.value),
      DAYS.slice(-7).map((d) => d.steps)
    )
    assert.equal(weekNums(s, Date.now()).minutes, undefined)
    assert.equal(allNums(s, 0).minutes, undefined)
    assert.equal(
      weeks12(s, Date.now()).reduce((n, x) => n + x.value, 0),
      58
    )
  })
  it('drops malformed days and passes', () => {
    const s = readActivity({
      minutesTracked: true,
      days: [{ date: 'bad', minutes: 9 }, { date: day(0), minutes: 5, steps: 1 }],
      recent: [{ at: 'nope', stepTitle: 'X' }, { at: '2026-11-22T10:00:00-08:00' }, { at: '2026-11-22T10:00:00-08:00', stepTitle: 'Call `np.dot`', skills: ['`fit`'] }]
    })
    assert.equal(s.days.size, 1)
    assert.deepEqual(
      s.passes.map((p) => [p.step, p.skill]),
      [['Call np.dot', 'fit']]
    )
  })
  it('nothing yet: not seen, no numbers', () => {
    assert.equal(EMPTY_V4.activitySeen, false)
    assert.deepEqual(weekNums(EMPTY_V4, NOW), { minutes: undefined, steps: 0 })
  })
})

describe('bon and plans (ui-v4 mock)', () => {
  it('reads bon: steps, level, name and next', () => {
    assert.deepEqual(readBon(first('uiv4_bon', 'bon')), { steps: 24, level: 4, name: 'Sapling', next: { name: 'Budding', left: 1 } })
    const grown = readBon(first('uiv4_pass', 'bon'))
    assert.equal(grown?.steps, 25)
    assert.equal(grown?.name, 'Budding')
    assert.equal(readBon({}), undefined)
  })
  it('bon falls back to the local count, and never shows 0 once activity counts passed steps', () => {
    assert.equal(bonSteps(v4({ bon: { steps: 24 } }), 3), 24)
    assert.equal(bonSteps(EMPTY_V4, 3), 3)
    assert.equal(bonSteps(v4(readActivity(ACTIVITY)), 0), 58)
    assert.equal(bonSteps(EMPTY_V4, 0), 0)
  })
  it('reads plans: id, title, done, total; drops malformed ones', () => {
    const plans = readPlans(first('uiv4_plans', 'plans'))
    assert.ok(plans.length > 0)
    assert.equal(plans[0].id, 'neural-networks')
    assert.equal(plans[0].title, 'Neural networks from scratch')
    for (const p of plans) assert.ok(p.done <= p.total)
    assert.deepEqual(readPlans({ items: [{ title: '', total: 2 }, { title: 'B', done: 1 }, { id: 'a', title: 'A', done: 9, total: 8 }] }), [{ id: 'a', title: 'A', done: 8, total: 8 }])
  })
})

describe('progress (parts UI-V4 does not carry yet)', () => {
  it('reads goal, review minutes and per-skill steps; ignores the old activity fields', () => {
    const p = readV4({
      goal: { title: 'Fit sin(x)', mastered: 20, total: 13, minutesLeft: 180 },
      review: { minutes: 4 },
      activity: [{ date: day(0), reps: 2, minutes: 10 }],
      bon: { passed: 58 },
      plans: [{ title: 'A', done: 3, total: 8 }],
      skills: [
        {
          track: 't',
          skills: [
            { label: 'Matrices', state: 'practicing', reps: 3, need: 5 },
            { label: 'X', state: 'practicing', reps: 1 }
          ]
        }
      ]
    })
    assert.deepEqual(Object.keys(p).sort(), ['goal', 'reviewMinutes', 'skills'])
    assert.equal(p.goal?.mastered, 13)
    assert.equal(p.reviewMinutes, 4)
    assert.deepEqual(p.skills, [{ label: 'Matrices', done: 3, need: 5, mastered: false }])
    assert.equal(readV4({ review: { minutes: 0 } }).reviewMinutes, undefined)
  })
  it('closest to mastered ranks by how far along', () => {
    const c = closest(
      v4(
        readV4({
          skills: [
            {
              track: 't',
              skills: [
                { label: 'A', reps: 1, need: 3 },
                { label: 'B', reps: 3, need: 5 },
                { label: 'C', reps: 0, need: 2 },
                { label: 'D', reps: 4, need: 4, state: 'mastered' }
              ]
            }
          ]
        })
      )
    )
    assert.deepEqual(
      c.map((s) => s.label),
      ['B', 'A']
    )
  })
})

describe('labels', () => {
  it('hm, guide lines and when labels', () => {
    assert.deepEqual(hm(108), { h: 1, m: 48 })
    assert.equal(guide(41, true, false)?.label, '30 min')
    assert.equal(guide(130, true, true)?.label, '2 hr')
    assert.equal(guide(0, false, true), undefined)
    assert.match(whenLabel(new Date(2026, 10, 22, 16, 12).getTime(), NOW), /^Today, 4:12/)
    assert.equal(whenLabel(new Date(2026, 10, 21, 9).getTime(), NOW), 'Yesterday')
    assert.equal(whenLabel(new Date(2026, 10, 18, 9).getTime(), NOW), 'Wednesday')
    assert.equal(whenLabel(new Date(2026, 10, 10, 9).getTime(), NOW), 'Nov 10')
    assert.equal(goalLine({ title: 'g', mastered: 1, total: 2, minutesLeft: 180, eta: new Date(2026, 11, 4, 12).getTime() }), 'about 3 hours, around Dec 4')
  })
  it('drops markdown backticks', () => {
    assert.equal(plain('Training with `fit`'), 'Training with fit')
  })
  it('never leaves a Keep fresh row blank', () => {
    assert.equal(freshLabel({ lastAt: NOW - 3 * 86_400_000 }, NOW), '3 days ago')
    assert.equal(freshLabel({ when: 'Saturday' }, NOW), 'Saturday')
    assert.equal(freshLabel({ dueAt: NOW + 2 * 86_400_000 }, NOW), 'due in 2 days')
    assert.equal(freshLabel({}, NOW), 'due')
  })
  it('keeps "about 2.5 hr" on one line', () => {
    assert.equal(aboutHr(150), 'about\u00a02.5\u00a0hr')
    assert.doesNotMatch(aboutHr(20), / /)
  })
})

describe('rail from the skill graph (QA R3-04: progress without goal / need / review)', () => {
  const graph = buildSkillGraph(first('uiv4_progress', 'progress'), NOW)
  const r = fromGraph(graph)
  it('the goal is the graph goal, counted in skills', () => {
    assert.ok(r.goal)
    assert.equal(r.goal.title, graph?.goal?.label)
    assert.ok(r.goal.total > 0 && r.goal.mastered <= r.goal.total)
  })
  it('closest to mastered: practicing skills by steps passed, furthest along first', () => {
    assert.deepEqual(
      r.near.map((s) => `${s.label} ${s.done}/${s.need}`),
      ['Layers as matrices 3/5', 'Broadcasting 2/4', 'Modifiers 2/5']
    )
  })
  it('keep fresh: the graph keepFresh skills, with when they were last practiced', () => {
    assert.deepEqual(
      r.fresh.map((f) => f.label),
      ['Transforms']
    )
    assert.ok(r.fresh[0].lastAt)
  })
  it('no graph: nothing made up', () => {
    assert.deepEqual(fromGraph(undefined), { near: [], fresh: [] })
  })
})

describe('the rail names the one goal Home and Skills name (QA R2-02, R3-04)', () => {
  const graph = buildSkillGraph(first('uiv4_progress', 'progress'), NOW)
  const activity = ACTIVITY as unknown as Activity
  const plans = (first('uiv4_plans', 'plans').items ?? []) as PlanState[]
  const home = fromContract({ activity, plans }).goal
  const plan = planGoalFor(graph, home)
  it('an inferred graph goal gives way to the plan goal (usePlanGoal / fromContract)', () => {
    assert.equal(graph?.goal?.inferred, true)
    assert.ok(home && plan)
    const g = railGoal(undefined, plan, fromGraph(graph).goal)
    assert.ok(g)
    assert.equal(g.title, home.title)
    assert.notEqual(g.title, graph?.goal?.label)
    assert.equal(g.mastered, home.done)
    assert.equal(g.total, home.total)
    assert.equal(g.unit, 'lessons')
    assert.equal(`${g.mastered} of ${g.total} ${g.unit ?? 'skills'}`, `${home.done} of ${home.total} lessons`)
  })
  it('a picked graph goal stays (usePlanGoal is undefined), counted in skills', () => {
    assert.ok(graph?.goal)
    const picked = { ...graph, goal: { ...graph.goal, inferred: false } }
    assert.equal(planGoalFor(picked, home), undefined)
    const g = railGoal(undefined, planGoalFor(picked, home), fromGraph(picked).goal)
    assert.equal(g?.title, plain(graph.goal.label))
    assert.equal(g?.unit, undefined)
  })
  it('no plan goal: the graph goal; the engine goal always wins', () => {
    const fallback = fromGraph(graph).goal
    assert.deepEqual(railGoal(undefined, undefined, fallback), fallback)
    const own = { title: 'Own', mastered: 1, total: 2 }
    assert.deepEqual(railGoal(own, plan, fallback), own)
  })
})
