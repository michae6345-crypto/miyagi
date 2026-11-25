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

/** Does a path's straight H / V legs run through a box (2 px inside its edges)? */
function crosses(d: string, b: Box): boolean {
  const t = d.match(/[MHVQ]|-?\d+(?:\.\d+)?/g)!
  let x = 0
  let y = 0
  const inside = (x1: number, y1: number, x2: number, y2: number): boolean =>
    Math.max(x1, x2) > b.x + 2 && Math.min(x1, x2) < b.x + b.w - 2 && Math.max(y1, y2) > b.y + 2 && Math.min(y1, y2) < b.y + b.h - 2
  for (let i = 0; i < t.length; ) {
    const c = t[i++]
    if (c === 'M') (x = +t[i++]), (y = +t[i++])
    else if (c === 'H') {
      const nx = +t[i++]
      if (inside(x, y, nx, y)) return true
      x = nx
    } else if (c === 'V') {
      const ny = +t[i++]
      if (inside(x, y, x, ny)) return true
      y = ny
    } else if (c === 'Q') (i += 2), (x = +t[i++]), (y = +t[i++])
  }
  return false
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
  it('reports a wider stage than the column when it cannot fit (the view pans it)', () => {
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
  it('routes every edge around the cards it does not join', () => {
    for (const lay of [l, tracksLayout(g)]) for (const e of lay.edges) for (const b of lay.boxes) if (b.id !== e.from && b.id !== e.to) assert.ok(!crosses(e.d, b), `${e.from} > ${e.to} crosses ${b.id}`)
  })
  it('stands each track in one column, its project over it', () => {
    for (const t of g.tracks) {
      const xs = l.boxes.filter((b) => g.byId[b.id]?.track === t.id && g.byId[b.id].kind === 'skill' && t.id !== 'python').map((b) => b.x + b.w / 2)
      // one column: every card's center within the column's widest row
      if (xs.length) assert.ok(Math.max(...xs) - Math.min(...xs) < 200, `${t.id} spreads ${Math.max(...xs) - Math.min(...xs)}`)
    }
    const at = Object.fromEntries(l.boxes.map((b) => [b.id, b]))
    const goal = at[g.goal!.id]
    const under = g.byId[g.goal!.id].requires.map((r) => at[r])
    const mid = under.reduce((s, b) => s + b.x + b.w / 2, 0) / under.length
    assert.ok(Math.abs(goal.x + goal.w / 2 - mid) < 1, 'the goal centered over what it needs')
  })
  it('zooms out to one card per track and in to the path with steps', () => {
    const tl = tracksLayout(g)
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
