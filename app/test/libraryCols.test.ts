/**
 * The Library's lesson tables (features/library/tableCols.ts): which columns show and how wide, per the v4 mock
 * (Lesson · Plan · Works in · Grows · Time · Progress · Opened).
 * Run: node --import tsx --import ./test/setup.mjs --test test/libraryCols.test.ts
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { CAP, EASY, FLOOR, layoutCols, ORDER, type ColKey } from '../src/renderer/src/features/library/tableCols'

/** Content widths close to the stage's `full` scenario (Bricolage 13 px meta, 14 px / 600 titles). */
const NEED: Record<ColKey, number> = { plan: 103, tool: 56, grows: 130, time: 44, progress: 114, opened: 50 }
const TITLE = 302 // "Subdivision and smooth shading" + its thumb
const keys = (l: ReturnType<typeof layoutCols>): ColKey[] => l.cols.map((c) => c.key)
const widthOf = (l: ReturnType<typeof layoutCols>, k: ColKey): number | undefined => l.cols.find((c) => c.key === k)?.width

describe('library table columns', () => {
  it('shows every column the mock has, in its order, on the default window', () => {
    const l = layoutCols({ width: 960, gap: 16, title: TITLE, need: NEED })
    assert.deepEqual(keys(l), ['plan', 'tool', 'grows', 'time', 'progress', 'opened'])
    assert.ok(l.titleFits, 'the longest title fits whole')
    for (const c of l.cols) assert.ok(c.width >= NEED[c.key], `${c.key} is not cut (${c.width} < ${NEED[c.key]})`)
  })

  it('eases the columns toward the mock widths when there is room, never past them', () => {
    const l = layoutCols({ width: 1040, gap: 16, title: TITLE, need: NEED })
    for (const c of l.cols) assert.ok(c.width <= Math.max(EASY[c.key], NEED[c.key]), `${c.key} ${c.width}`)
    assert.ok(l.lesson >= TITLE)
    assert.equal(l.template.split(' ')[0], 'minmax(0,1fr)', 'the Lesson column takes the rest')
  })

  it('the px columns and gaps never take more than the table', () => {
    for (const width of [480, 640, 760, 860, 960, 1040, 1400]) {
      const l = layoutCols({ width, gap: 16, title: TITLE, need: NEED })
      assert.equal(l.lesson + l.cols.reduce((n, c) => n + c.width + 16, 0), width)
    }
  })

  it('leaves out a column only when every row lacks it', () => {
    const l = layoutCols({ width: 960, gap: 16, title: TITLE, need: { ...NEED, plan: 0, opened: 0 } })
    assert.deepEqual(keys(l), ['tool', 'grows', 'time', 'progress'])
    // A column with content is never left out on a wide table, however short its content.
    const thin = layoutCols({ width: 960, gap: 16, title: TITLE, need: { ...NEED, plan: 20 } })
    assert.ok(keys(thin).includes('plan'))
  })

  it('gives the title its room first: Plan and Grows shrink (truncate) before anything drops', () => {
    // 880: the titles need 302; at content width the others leave less, so Plan and Grows give some back.
    const l = layoutCols({ width: 880, gap: 16, title: TITLE, need: NEED })
    assert.deepEqual(keys(l), ORDER)
    assert.ok(l.titleFits)
    assert.ok(widthOf(l, 'plan')! < NEED.plan || widthOf(l, 'grows')! < NEED.grows, 'Plan or Grows gave way')
    assert.ok(widthOf(l, 'plan')! >= FLOOR.plan! && widthOf(l, 'grows')! >= FLOOR.grows!)
    for (const k of ['tool', 'time', 'progress', 'opened'] as const) assert.equal(widthOf(l, k), NEED[k], `${k} keeps its width`)
  })

  it('drops Plan, then Grows, then Opened, then Works in; Time and Progress stay', () => {
    const seen: ColKey[][] = []
    for (let width = 1000; width >= 300; width -= 10) {
      const k = keys(layoutCols({ width, gap: 16, title: TITLE, need: NEED }))
      if (!seen.length || seen[seen.length - 1].join() !== k.join()) seen.push(k)
    }
    assert.deepEqual(seen, [
      ['plan', 'tool', 'grows', 'time', 'progress', 'opened'],
      ['tool', 'grows', 'time', 'progress', 'opened'],
      ['tool', 'time', 'progress', 'opened'],
      ['tool', 'time', 'progress'],
      ['time', 'progress']
    ])
  })

  it('a very long title truncates rather than empty the row (it asks for half the table at most)', () => {
    const l = layoutCols({ width: 960, gap: 16, title: 900, need: NEED })
    assert.ok(keys(l).length >= 4, 'most columns stay')
    assert.ok(!l.titleFits)
    assert.ok(l.lesson >= 480)
  })

  it('a column never asks for more than its cap', () => {
    const l = layoutCols({ width: 2000, gap: 16, title: 200, need: { ...NEED, plan: 900, grows: 900 } })
    assert.equal(widthOf(l, 'plan'), CAP.plan)
    assert.equal(widthOf(l, 'grows'), CAP.grows)
  })
})
