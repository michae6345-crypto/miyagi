/**
 * The flat skill tree's layouts and lines (round 3). Offline, no React:
 * `node --import tsx --test src/renderer/src/features/skills/flat/layout.test.ts` from app/.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { buildSkillGraph } from '../model'
import { goalBits, ruleLine, statusCell, stillToGo } from './copy'
import { elbowH, elbowV, FOLD_ID, mapLayout, pathFold, pathLayout, stepsLayout, tracksLayout, type Box } from './layout'

const scenario = JSON.parse(readFileSync(new URL('../../../../../../mock/scenarios/skills.json', import.meta.url), 'utf8')) as {
  segments: Record<string, Array<{ payload: Record<string, unknown> }>>
}
const NOW = new Date(2026, 10, 22, 18).getTime()
const g = buildSkillGraph(scenario.segments.skills_progress[0].payload, NOW)!

const overlap = (a: Box, b: Box): boolean => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h
function noOverlaps(boxes: Box[]): void {
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) assert.ok(!overlap(boxes[i], boxes[j]), `${boxes[i].id} overlaps ${boxes[j].id}`)
}

describe('edges', () => {
  it('draws square turns with a small round corner', () => {
    assert.equal(elbowH(0, 10, 100, 10), 'M0 10H100')
    assert.match(elbowH(0, 0, 100, 80), /^M0 0H42Q50 0 50 8V72Q50 80 58 80H100$/)
    assert.equal(elbowV(5, 100, 5, 0), 'M5 100V0')
    assert.match(elbowV(0, 100, 60, 0, 40), /^M0 100V48Q0 40 8 40H52Q60 40 60 32V0$/)
  })
})

describe('pathLayout', () => {
  it('folds the done base track into one card', () => {
    const { ids, fold } = pathFold(g)
    assert.ok(fold)
    assert.equal(fold.track, 'python')
    assert.equal(ids[0], FOLD_ID)
    assert.ok(fold.ids.every((id) => g.byId[id].state === 'mastered'))
  })
  it('places every path skill once, the project last, nothing overlapping', () => {
    const l = pathLayout(g, 960)
    const goal = l.boxes.find((b) => b.id === g.goal!.id)!
    assert.ok(l.boxes.every((b) => b.id === goal.id || b.x + b.w <= goal.x))
    noOverlaps(l.boxes)
    assert.ok(l.w <= 960, `w ${l.w}`)
    // numpy and math each get a name over their first card; the folded python does not
    assert.deepEqual(l.labels.map((t) => t.track).sort(), ['math', 'neural networks', 'numpy'])
  })
  it('only lines between two mastered skills are green', () => {
    for (const e of pathLayout(g, 960).edges) {
      const done = (id: string): boolean => id === FOLD_ID || g.byId[id]?.state === 'mastered'
      assert.equal(e.kind === 'done', done(e.from) && done(e.to), `${e.from} > ${e.to}`)
    }
  })
  it('reports a wider stage than the column when it cannot fit (the view scales it)', () => {
    assert.ok(pathLayout(g, 300).w > 300)
  })
})

describe('mapLayout', () => {
  const l = mapLayout(g)
  it('places every skill and project once, without overlaps', () => {
    assert.equal(l.boxes.length, g.nodes.length)
    noOverlaps(l.boxes)
  })
  it('grows bottom up: a skill sits above what it needs', () => {
    const at = Object.fromEntries(l.boxes.map((b) => [b.id, b]))
    for (const n of g.nodes) for (const r of n.requires) if (at[r] && at[n.id]) assert.ok(at[n.id].y < at[r].y, `${n.id} above ${r}`)
  })
  it('keeps track names clear of cards', () => {
    for (const t of l.labels) {
      const w = t.text.length * 6.6
      const box: Box = { id: t.track, x: t.x - w, y: t.y, w, h: 14 }
      for (const b of l.boxes) assert.ok(!overlap(box, b), `${t.track} label over ${b.id}`)
    }
  })
  it('zooms out to one card per track and in to the path with steps', () => {
    const tl = tracksLayout(g, l)
    assert.equal(tl.boxes.filter((b) => b.id.startsWith('track:')).length, g.tracks.filter((t) => t.total > 0).length)
    noOverlaps(tl.boxes)
    const sl = stepsLayout(g, (id) => g.byId[id].evidence?.total ?? 1)
    noOverlaps(sl.boxes)
    assert.ok(sl.boxes.every((b) => g.goal!.pathIds.includes(b.id)))
  })
})

describe('lines', () => {
  it('says the goal, what is left, and the rules', () => {
    assert.deepEqual(goalBits(g), [`${g.goal!.mastered} of ${g.goal!.total} skills`])
    assert.deepEqual(goalBits(g, 180), [`${g.goal!.mastered} of ${g.goal!.total} skills`, 'about 3 hours left'])
    const rows = stillToGo(g)
    assert.ok(rows.length > 0 && rows[0].isNext)
    assert.ok(rows.every((n) => n.state !== 'mastered'))
    const locked = rows.find((n) => n.state === 'locked')!
    assert.match(statusCell(locked, g), /^Needs /)
    assert.equal(ruleLine({ ...locked, state: 'ready' }, NOW), 'Mastered when you pass it on 2 days without help.')
    assert.equal(ruleLine({ ...locked, state: 'mastered', review: false, dueAt: undefined }, NOW), 'Reviews after 3, 7, 21 and 60 days.')
    assert.equal(ruleLine({ ...locked, state: 'mastered', review: false, dueAt: NOW + 7 * 86_400_000 }, NOW), 'Next review in 7 days.')
  })
})
