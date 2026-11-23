/**
 * Skills extras, pure (recap.ts). Offline, no React, no window:
 * `node --import tsx --test src/renderer/src/features/skills/extras/recap.test.ts` from app/.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { buildSkillGraph } from '../model'
import { goalAway, lessonRecap, minutesWords, nextLabel, recapWord, skillsAway, weekLines } from './recap'

const scenario = JSON.parse(readFileSync(new URL('../../../../../../mock/scenarios/skills-extras.json', import.meta.url), 'utf8')) as {
  segments: Record<string, Array<{ payload: Record<string, unknown> }>>
}
const progress = scenario.segments.extras_progress[0].payload
const NOW = new Date(2026, 10, 22, 18).getTime()
const g = buildSkillGraph(progress, NOW)!

describe('lessonRecap', () => {
  it('says what the lesson moved, from its unseen events', () => {
    const r = lessonRecap(g, { lessonIds: ['pandas_csv'], skillIds: ['dfs', 'csv'] })!
    assert.deepEqual(
      r.rows.map((x) => [x.node.id, recapWord(x)]),
      [
        ['csv', 'mastered'],
        ['clean', 'ready now'],
        ['group', '1 skill away']
      ]
    )
    assert.equal(r.next?.skillId, 'broad')
    assert.equal(nextLabel(r.next!), 'Next: Broadcasting · 12 min')
  })

  it('ignores events from another lesson and falls back to the lesson’s own skills', () => {
    const r = lessonRecap(g, { lessonIds: ['linalg'], skillIds: [] })!
    const kinds = Object.fromEntries(r.rows.map((x) => [x.node.id, x.kind]))
    assert.equal(kinds.csv, undefined)
    assert.equal(kinds.vec, 'mastered')
    assert.equal(kinds.mat, 'practicing')
    assert.ok(r.rows.length <= 4)
  })

  it('is undefined without a graph or with nothing from the lesson', () => {
    assert.equal(lessonRecap(undefined, { lessonIds: ['x'], skillIds: [] }), undefined)
    const empty = buildSkillGraph({ ...progress, graph: { ...(progress.graph as object), events: [] } }, NOW)!
    assert.equal(lessonRecap(empty, { lessonIds: ['nope'], skillIds: [] }), undefined)
  })

  it('counts skills away through every prerequisite not mastered', () => {
    assert.equal(skillsAway('group', g), 1)
    assert.equal(skillsAway('csv', g), 0)
  })
})

describe('the week', () => {
  it('reads like the mockup', () => {
    const t = weekLines(g.week!, goalAway(g), 3)
    assert.equal(t.lead, '2 skills mastered')
    assert.equal(t.rest, ', 3 kept fresh, 1 h 40 min.')
    assert.equal(t.goal, 'Your goal is 5 skills away.')
    assert.equal(t.days, '4 practice days. Your weekly goal is 3.')
  })

  it('never calls out a missed day', () => {
    const t = weekLines({ days: [false, false, false, false, false, false, false] }, undefined, 3)
    assert.equal(t.lead, 'A fresh week')
    assert.equal(t.goal, undefined)
    assert.ok(!/miss|streak|lost|broke/i.test(Object.values(t).join(' ')))
  })

  it('writes minutes plainly', () => {
    assert.equal(minutesWords(45), '45 min')
    assert.equal(minutesWords(100), '1 h 40 min')
    assert.equal(minutesWords(120), '2 h')
  })
})

describe('portfolio', () => {
  it('keeps the finished project and the goal', () => {
    assert.equal(g.portfolio.length, 1)
    assert.equal(g.portfolio[0].artifact?.kind, 'image')
    assert.equal(g.goal?.id, 'fit')
    assert.equal(g.goal?.inferred, false)
  })
})
