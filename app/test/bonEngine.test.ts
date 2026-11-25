/**
 * bon's count from the engine (ui-v4 contract; features/buddy engine.ts createBonLink, growth.ts sync / local / import):
 * bon.import once per Mac and bon.get on connect, each only when engine.hello lists it; `bon` syncs `steps` (followed
 * down too, so Delete progress shrinks bon; the import's answer keeps the larger; never plays a level-up); a ui-v4
 * step.passed grows bon only when `counted`, and the
 * local count stays the fallback for an engine (or scenario) without it.
 * Run: node --import tsx --import ./test/setup.mjs --test test/bonEngine.test.ts
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { bonSteps, counts, createBonLink, type BonDeps } from '../src/renderer/src/features/buddy/engine'
import { createGrowth, GROWTH_KEY, IMPORTED_KEY, type Growth } from '../src/renderer/src/features/buddy/growth'

function memory(): { getItem: (k: string) => string | null; setItem: (k: string, v: string) => void; data: Record<string, string> } {
  const data: Record<string, string> = {}
  return { data, getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => void (data[k] = v) }
}

const ALL = ['progress.get', 'bon.get', 'bon.import']

/** createBonLink on a real growth (createGrowth), with what it sends recorded. */
function link(opts: { app?: boolean; storage?: ReturnType<typeof memory>; caps?: string[]; lessonId?: string } = {}): {
  g: Growth
  sent: { type: string; payload: Record<string, unknown> }[]
  bon: ReturnType<typeof createBonLink>
} {
  const g = createGrowth({ app: opts.app ?? true, storage: opts.storage ?? memory() })
  const sent: { type: string; payload: Record<string, unknown> }[] = []
  const deps: BonDeps = {
    canSend: (t) => (opts.caps ?? []).includes(t),
    send: (type, payload) => void sent.push({ type, payload }),
    local: g.local,
    imported: g.imported,
    markImported: g.markImported,
    sync: g.sync,
    pass: g.pass,
    lessonId: () => opts.lessonId
  }
  return { g, sent, bon: createBonLink(deps) }
}

describe('bonSteps (the contract `bon` payload)', () => {
  it('reads BonState.steps', () => {
    assert.equal(bonSteps({ steps: 25, level: 5, name: 'Budding', fraction: 0, grew: true, lastKey: 'L:s3' }), 25)
    assert.equal(bonSteps({ steps: 5.7, level: 2, name: 'Sprout' }), 5)
  })
  it('has nothing for a payload without a count, or a bad one', () => {
    for (const p of [undefined, null, 3, 'x', {}, { steps: -1 }, { steps: Number.NaN }, { steps: '12' }, { bon: { passed: 27 } }, { stepsPassed: 4 }]) assert.equal(bonSteps(p), undefined)
  })
})

describe('engine.hello (bon.get, bon.import)', () => {
  it('sends nothing to an engine that does not list them', () => {
    const { sent, bon } = link()
    bon.hello(['progress.get', 'health.get'])
    bon.hello(undefined)
    bon.hello('bon.get')
    assert.deepEqual(sent, [])
  })
  it('imports the local count once per Mac, then asks for bon', () => {
    const storage = memory()
    const before = createGrowth({ app: true, storage })
    before.pass('L:s1')
    before.pass('L:s2')
    const { sent, bon } = link({ storage, caps: ALL })
    bon.hello(ALL)
    assert.deepEqual(sent, [
      { type: 'bon.import', payload: { steps: 2, seen: ['L:s1', 'L:s2'] } },
      { type: 'bon.get', payload: {} }
    ])
    assert.equal(storage.data[IMPORTED_KEY], '1')
    // A reconnect (or another window, or the next launch): bon.get only.
    bon.hello(ALL)
    link({ storage, caps: ALL }).bon.hello(ALL)
    assert.deepEqual(sent.slice(2), [{ type: 'bon.get', payload: {} }])
  })
  it('has nothing to import when no count was ever kept, and never asks again', () => {
    const storage = memory()
    const { sent, bon } = link({ storage, caps: ALL })
    bon.hello(ALL)
    assert.deepEqual(sent, [{ type: 'bon.get', payload: {} }])
    assert.equal(storage.data[IMPORTED_KEY], '1')
  })
  it('the browser stage (no storage) never imports', () => {
    const { sent, bon } = link({ app: false, caps: ALL })
    bon.hello(ALL)
    assert.deepEqual(sent, [{ type: 'bon.get', payload: {} }])
  })
  it('bon.get alone when the engine lists only that, bon.import alone when only that', () => {
    const storage = memory()
    createGrowth({ app: true, storage }).pass('L:s1')
    const a = link({ storage })
    a.bon.hello(['bon.get'])
    assert.deepEqual(a.sent, [{ type: 'bon.get', payload: {} }])
    assert.equal(storage.data[IMPORTED_KEY], undefined, 'not imported yet: the engine did not list bon.import')
    const b = link({ storage })
    b.bon.hello(['bon.import'])
    assert.deepEqual(b.sent, [{ type: 'bon.import', payload: { steps: 1, seen: ['L:s1'] } }])
  })
})

describe('bon (the engine count)', () => {
  it('syncs steps quietly', () => {
    const { g, bon } = link({ caps: ALL })
    bon.bon({ steps: 24, level: 4, name: 'Sapling', fraction: 0.8889 })
    assert.equal(g.store.getState().steps, 24)
    assert.equal(g.store.getState().level, 4)
    bon.bon({ steps: 25, level: 5, name: 'Budding', grew: true, lastKey: 'L:s3' })
    assert.equal(g.store.getState().level, 5)
    assert.equal(g.store.getState().grew, 0, 'the moment belongs to the counted step.passed')
  })
  it('follows the engine down: Delete progress (data.delete progress) shrinks bon', () => {
    const storage = memory()
    const { g, bon } = link({ storage, caps: ALL, lessonId: 'L' })
    bon.bon({ steps: 24 })
    bon.passed({ stepId: 's4', key: 'L:s4', counted: true })
    bon.bon({ steps: 25, grew: true, lastKey: 'L:s4' })
    assert.equal(g.store.getState().level, 5)
    // The engine erased its counter and pushes the empty bon.
    bon.bon({ steps: 0, level: 1, name: 'Seed' })
    assert.equal(g.store.getState().steps, 0)
    assert.equal(g.store.getState().level, 1)
    assert.equal(JSON.parse(storage.data[GROWTH_KEY]).steps, 0, 'saved, so other windows and the next launch follow')
    assert.equal(g.store.getState().grew, 1, 'shrinking plays no moment')
    // Passing the same step again counts: the engine forgot it, and so did this window.
    assert.equal(bon.passed({ stepId: 's4', key: 'L:s4', counted: true }), undefined)
    assert.equal(g.store.getState().steps, 1)
  })
  it('the import answer keeps the larger count (once); later answers are followed as they are', () => {
    const storage = memory()
    const before = createGrowth({ app: true, storage })
    for (let i = 1; i <= 9; i++) before.pass(`L:s${i}`)
    const { g, bon } = link({ storage, caps: ALL })
    bon.hello(ALL)
    bon.bon({ steps: 4 })
    assert.equal(g.store.getState().steps, 9, 'the import: the larger of the two')
    bon.bon({ steps: 4 })
    assert.equal(g.store.getState().steps, 4, 'after it, the engine is the count')
  })
  it('ignores a payload without steps', () => {
    const { g, bon } = link()
    bon.bon({ level: 6 })
    bon.bon(null)
    assert.equal(g.store.getState().steps, 0)
  })
})

describe('step.passed (counted)', () => {
  it('a ui-v4 engine: only counted passes grow bon, under the engine key', () => {
    const storage = memory()
    const { g, bon } = link({ storage, caps: ALL, lessonId: 'L' })
    bon.bon({ steps: 24 })
    assert.equal(bon.passed({ stepId: 's2', key: 'L:s2' }), undefined, 'not counted (a key counted before)')
    assert.equal(bon.passed({ stepId: 's2', key: 'L:s2', counted: false }), undefined)
    assert.equal(bon.passed({ stepId: 's3', key: 'L:s3', assisted: true }), undefined, 'no counted: the engine did not count it')
    assert.equal(g.store.getState().steps, 24)
    assert.equal(bon.passed({ stepId: 's4', key: 'L:s4', counted: true }), 5, 'the 25th pass: Budding, the level-up moment')
    assert.equal(g.store.getState().grew, 1)
    assert.deepEqual(JSON.parse(storage.data[GROWTH_KEY]).seen, ['L:s4'])
    // The engine's push after it: no double count, no second moment.
    bon.bon({ steps: 25, grew: true, lastKey: 'L:s4' })
    assert.equal(g.store.getState().steps, 25)
    assert.equal(g.store.getState().grew, 1)
  })
  it('counted wins even where the hello was missed (a window opened mid-session)', () => {
    const { g, bon } = link({ caps: [] })
    assert.equal(bon.passed({ stepId: 's1', key: 'L:s1', counted: false }), undefined)
    bon.passed({ stepId: 's2', key: 'L:s2', counted: true })
    assert.equal(g.store.getState().steps, 1)
  })
  it('never a skipped or already-done pass, whatever it says', () => {
    for (const p of [{ stepId: 's1', skipped: true, counted: true }, { stepId: 's1', already: true, counted: true }, { stepId: '', counted: true }, null, undefined]) {
      assert.equal(counts(p, true), false)
      assert.equal(counts(p, false), false)
    }
  })
  it('the fallback: an engine without bon counts every pass locally, once per step', () => {
    const { g, bon } = link({ caps: ['progress.get'], lessonId: 'L' })
    bon.passed({ stepId: 's1' })
    bon.passed({ stepId: 's1' })
    bon.passed({ stepId: 's2', key: 'K:s2' })
    bon.passed({ stepId: 's3', skipped: true })
    bon.passed({ stepId: 's4', already: true })
    assert.equal(g.store.getState().steps, 2)
    assert.deepEqual(JSON.parse(JSON.stringify(g.local()?.seen)), ['L:s1', 'K:s2'])
  })
  it('a pass without key or counted counts locally even when bon.get is listed (pre-ui-v4 scenarios)', () => {
    assert.equal(counts({ stepId: 's1' }, true), true)
    assert.equal(counts({ stepId: 's1', key: 'L:s1' }, true), false)
    assert.equal(counts({ stepId: 's1', key: 'L:s1' }, false), true)
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
  it('follows the engine down, and forgets the passes remembered here', () => {
    const storage = memory()
    const g = createGrowth({ app: true, storage })
    g.sync(10)
    g.pass('L:s1')
    g.sync(6)
    assert.equal(g.store.getState().steps, 6)
    assert.equal(g.store.getState().level, 2)
    assert.deepEqual(JSON.parse(storage.data[GROWTH_KEY]).seen, [])
    const stage = createGrowth({ app: false, search: '?steps=10' })
    stage.sync(6)
    assert.equal(stage.store.getState().steps, 6)
  })
  it('an equal count changes nothing', () => {
    const storage = memory()
    const g = createGrowth({ app: true, storage })
    g.sync(14)
    g.pass('L:s1')
    g.sync(15)
    assert.deepEqual(JSON.parse(storage.data[GROWTH_KEY]).seen, ['L:s1'])
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
