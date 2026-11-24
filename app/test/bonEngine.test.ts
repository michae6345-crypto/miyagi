/**
 * bon's count from the engine (features/buddy engine.ts passedOf, growth.ts sync): the engine's passed-step counter
 * wins when it is ahead, never lowers the count, never plays a level-up, and the local count stays the fallback.
 * Run: node --import tsx --import ./test/setup.mjs --test test/bonEngine.test.ts
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { passedOf } from '../src/renderer/src/features/buddy/engine'
import { createGrowth, GROWTH_KEY } from '../src/renderer/src/features/buddy/growth'

function memory(): { getItem: (k: string) => string | null; setItem: (k: string, v: string) => void; data: Record<string, string> } {
  const data: Record<string, string> = {}
  return { data, getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => void (data[k] = v) }
}

describe('passedOf (the engine payload)', () => {
  it('reads the count from where the contract may put it', () => {
    assert.equal(passedOf({ bon: { passed: 27 } }), 27)
    assert.equal(passedOf({ activity: { stepsPassed: 9 } }), 9)
    assert.equal(passedOf({ stepsPassed: 4 }), 4)
    assert.equal(passedOf({ passedSteps: 5.7 }), 5)
    assert.equal(passedOf({ stepId: 's1', passedTotal: 12 }), 12)
  })
  it('has nothing for a payload without a count, or a bad one', () => {
    for (const p of [undefined, null, 3, 'x', {}, { bon: null }, { bon: { passed: -1 } }, { stepsPassed: Number.NaN }, { skills: [], completed: [] }]) assert.equal(passedOf(p), undefined)
  })
})

describe('growth sync (the engine count)', () => {
  it('takes the engine count when it is ahead, quietly, and saves it', () => {
    const storage = memory()
    const g = createGrowth({ app: true, storage })
    g.sync(27)
    const s = g.store.getState()
    assert.equal(s.steps, 27)
    assert.equal(s.level, 5)
    assert.equal(s.grew, 0, 'a sync never plays the level-up moment')
    assert.equal(JSON.parse(storage.data[GROWTH_KEY]).steps, 27)
  })
  it('never lowers the count shown', () => {
    const g = createGrowth({ app: false, search: '?steps=10' })
    g.sync(6)
    assert.equal(g.store.getState().steps, 10)
  })
  it('a live pass after a sync counts on top, and keeps the engine count saved', () => {
    const storage = memory()
    const g = createGrowth({ app: true, storage })
    g.sync(14)
    assert.equal(g.pass('L:s1'), 4, 'passing step 15 reaches Sapling')
    assert.equal(g.store.getState().grew, 1)
    const saved = JSON.parse(storage.data[GROWTH_KEY])
    assert.equal(saved.steps, 15)
    assert.equal(saved.engine, 14)
    // The engine then reports the same pass: no double count.
    g.sync(15)
    assert.equal(g.store.getState().steps, 15)
  })
  it('ignores anything that is not a count', () => {
    const g = createGrowth({ app: false })
    for (const v of [undefined, null, -3, Number.NaN, '12']) g.sync(v)
    assert.equal(g.store.getState().steps, 0)
  })
})
