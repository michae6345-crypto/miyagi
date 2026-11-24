/**
 * The v4 Progress page's data (features/progress/v4/model.ts): what it reads from `progress`, and the numbers it shows.
 * Run: node --import tsx --import ./test/setup.mjs --test test/progressV4.test.ts
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { allNums, closest, dayKey, goalLine, guide, hm, readV4, weekBars, weekNums, weeks12, whenLabel } from '../src/renderer/src/features/progress/v4/model'

// Sunday Nov 22 2026, 6 PM local.
const NOW = new Date(2026, 10, 22, 18, 0).getTime()
const day = (back: number): string => dayKey(new Date(2026, 10, 22 - back, 12).getTime())

describe('readV4', () => {
  it('returns empty parts for nothing at all', () => {
    const v = readV4(undefined)
    assert.equal(v.days.size, 0)
    assert.equal(v.minutesKnown, false)
    assert.deepEqual(v.passes, [])
  })
  it('reads minutes per day and adds up repeated days', () => {
    const v = readV4({
      activity: [
        { date: day(0), reps: 2, minutes: 10 },
        { date: day(0), reps: 1, minutes: 5 },
        { date: 'bad', minutes: 9 }
      ]
    })
    assert.equal(v.minutesKnown, true)
    assert.deepEqual(v.days.get(day(0)), { steps: 3, minutes: 15 })
    assert.equal(v.days.size, 1)
  })
  it('keeps steps only when the engine sends no minutes', () => {
    const v = readV4({ activity: [{ date: day(1), reps: 4 }] })
    assert.equal(v.minutesKnown, false)
    assert.equal(v.days.get(day(1))?.minutes, undefined)
  })
  it('reads recent passes newest first and drops ones without a time or a step', () => {
    const v = readV4({
      recent: [{ at: 1_790_000_000, step: 'Old' }, { at: 1_790_100_000, title: 'New', skill: 'Loops' }, { step: 'No time' }, { at: 1_790_000_000 }]
    })
    assert.deepEqual(
      v.passes.map((p) => p.step),
      ['New', 'Old']
    )
    assert.equal(v.passes[0].skill, 'Loops')
  })
  it('reads goal, plans, bon and per-skill steps; drops malformed ones', () => {
    const v = readV4({
      goal: { title: 'Fit sin(x)', mastered: 20, total: 13, minutesLeft: 180 },
      plans: [
        { title: 'A', done: 3, total: 8 },
        { title: '', total: 2 },
        { title: 'B', done: 1 }
      ],
      bon: { passed: 58 },
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
    assert.equal(v.goal?.mastered, 13)
    assert.deepEqual(
      v.plans.map((p) => p.title),
      ['A']
    )
    assert.equal(v.bonPassed, 58)
    assert.deepEqual(v.skills, [{ label: 'Matrices', done: 3, need: 5, mastered: false }])
  })
})

describe('charts and numbers', () => {
  const v = readV4({
    activity: [
      { date: day(0), reps: 2, minutes: 15 },
      { date: day(4), reps: 3, minutes: 41 },
      { date: day(10), reps: 1, minutes: 30 }
    ]
  })
  it('this week runs Monday to Sunday with today last', () => {
    const b = weekBars(v, NOW)
    assert.equal(b.length, 7)
    assert.equal(b[0].label, 'Mon')
    assert.equal(b[6].now, true)
    assert.equal(b[6].value, 15)
    assert.equal(b[2].value, 41)
  })
  it('12 weeks, oldest first, "Now" last, weekly sums', () => {
    const w = weeks12(v, NOW)
    assert.equal(w.length, 12)
    assert.equal(w[11].label, 'Now')
    assert.equal(w[11].value, 56)
    assert.equal(w[10].value, 30)
  })
  it('week and all-time numbers', () => {
    assert.deepEqual(weekNums(v, NOW), { minutes: 56, steps: 5 })
    assert.deepEqual(allNums(v, 2), { minutes: 86, steps: 6, lessons: 2 })
    assert.deepEqual(allNums(readV4({ totals: { minutes: 999, steps: 58, lessons: 4 } }), 1), { minutes: 999, steps: 58, lessons: 4 })
    assert.equal(allNums(readV4({ activity: [{ date: day(0), reps: 2 }] }), 0).minutes, undefined)
  })
  it('hm, guide lines and labels', () => {
    assert.deepEqual(hm(108), { h: 1, m: 48 })
    assert.equal(guide(41, true, false)?.label, '30 min')
    assert.equal(guide(130, true, true)?.label, '2 hr')
    assert.equal(guide(0, false, true), undefined)
    assert.match(whenLabel(new Date(2026, 10, 22, 16, 12).getTime(), NOW), /^Today, 4:12/)
    assert.equal(whenLabel(new Date(2026, 10, 21, 9).getTime(), NOW), 'Yesterday')
    assert.equal(whenLabel(new Date(2026, 10, 18, 9).getTime(), NOW), 'Wednesday')
    assert.equal(whenLabel(new Date(2026, 10, 10, 9).getTime(), NOW), 'Nov 10')
    assert.equal(
      goalLine({
        title: 'g',
        mastered: 1,
        total: 2,
        minutesLeft: 180,
        eta: new Date(2026, 11, 4, 12).getTime()
      }),
      'about 3 hours, around Dec 4'
    )
  })
  it('closest to mastered ranks by how far along', () => {
    const c = closest(
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
    assert.deepEqual(
      c.map((s) => s.label),
      ['B', 'A']
    )
  })
})
