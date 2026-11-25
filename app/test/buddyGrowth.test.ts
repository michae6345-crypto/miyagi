/**
 * bon grows as the learner passes steps (growth.ts): the levels, what counts, and how the count is kept.
 * Run: node --import tsx --import ./test/setup.mjs --test test/buddyGrowth.test.ts
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { clampLevel, createGrowth, GROWTH_KEY, levelFor, LEVELS, MAX_LEVEL, progressOf } from '../src/renderer/src/features/buddy/growth'

function memory(seed: Record<string, string> = {}): { getItem: (k: string) => string | null; setItem: (k: string, v: string) => void; data: Record<string, string> } {
  const data = { ...seed }
  return { data, getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => void (data[k] = v) }
}
const passMany = (g: ReturnType<typeof createGrowth>, n: number, lesson = 'L'): (number | undefined)[] => Array.from({ length: n }, (_, i) => g.pass(`${lesson}:s${i + 1}`))

describe('the levels (growth.ts LEVELS)', () => {
  it('eight of them, starting at nothing, each asking for more steps than the last, and by more each time', () => {
    assert.equal(MAX_LEVEL, 8)
    assert.equal(LEVELS[0].at, 0)
    const gaps = LEVELS.slice(1).map((l, i) => l.at - LEVELS[i].at)
    gaps.forEach((g, i) => {
      assert.ok(g > 0, `level ${i + 2} needs more steps than level ${i + 1}`)
      if (i > 0) assert.ok(g >= gaps[i - 1], `the climb to level ${i + 2} is not shorter than the one before`)
    })
  })

  it('every level has its own name and its own look', () => {
    assert.equal(new Set(LEVELS.map((l) => l.name)).size, LEVELS.length)
    assert.equal(new Set(LEVELS.map((l) => l.has)).size, LEVELS.length)
  })

  it('a level starts exactly at its count', () => {
    LEVELS.forEach((l, i) => {
      assert.equal(levelFor(l.at), i + 1)
      if (l.at > 0) assert.equal(levelFor(l.at - 1), i)
    })
    assert.equal(levelFor(10_000), MAX_LEVEL)
  })

  it('the first level-up comes quickly: three passed steps', () => {
    assert.equal(LEVELS[1].at, 3)
  })
})

describe('what the growth card says (progressOf)', () => {
  it('names the level and counts the steps left to the next one', () => {
    const p = progressOf(5)
    assert.deepEqual(p, { level: 2, name: 'Sprout', steps: 5, next: { level: 3, name: 'Shoot', at: 8, left: 3 }, fraction: 2 / 5 })
  })

  it('a new learner is a Seed with three steps to go', () => {
    const p = progressOf(0)
    assert.equal(p.name, 'Seed')
    assert.equal(p.next?.left, 3)
    assert.equal(p.fraction, 0)
  })

  it('at the top there is no next level and the bar is full', () => {
    const p = progressOf(LEVELS[MAX_LEVEL - 1].at + 12)
    assert.equal(p.level, MAX_LEVEL)
    assert.equal(p.next, undefined)
    assert.equal(p.fraction, 1)
  })

  it('a bad count is read as none', () => {
    assert.equal(progressOf(Number.NaN).steps, 0)
    assert.equal(progressOf(-4).steps, 0)
    assert.equal(clampLevel(99), MAX_LEVEL)
    assert.equal(clampLevel('x'), 1)
  })
})

describe('counting passed steps (createGrowth)', () => {
  it('each passed step counts once, and the pass that crosses a line says which level it reached', () => {
    const g = createGrowth({ app: true, storage: memory() })
    assert.deepEqual(passMany(g, 3), [undefined, undefined, 2])
    assert.deepEqual(g.store.getState(), { steps: 3, level: 2, grew: 1 })
  })

  it('the same step again (a replay after a reconnect) is not counted twice', () => {
    const g = createGrowth({ app: true, storage: memory() })
    g.pass('L:s1')
    g.pass('L:s1')
    g.pass('L:s1')
    assert.equal(g.store.getState().steps, 1)
    // The same step id in another lesson is another step.
    g.pass('M:s1')
    assert.equal(g.store.getState().steps, 2)
  })

  it('a pass with no name is not counted', () => {
    const g = createGrowth({ app: true, storage: memory() })
    assert.equal(g.pass(''), undefined)
    assert.equal(g.store.getState().steps, 0)
  })

  it('it is saved, and the next launch comes up at the same level without a level-up moment', () => {
    const storage = memory()
    passMany(createGrowth({ app: true, storage }), 9)
    const next = createGrowth({ app: true, storage })
    assert.deepEqual(next.store.getState(), { steps: 9, level: 3, grew: 0 })
    // And it still knows which steps it counted.
    next.pass('L:s9')
    assert.equal(next.store.getState().steps, 9)
  })

  it('two windows hearing the same pass count it once', () => {
    const storage = memory()
    const overlay = createGrowth({ app: true, storage })
    const settings = createGrowth({ app: true, storage })
    overlay.pass('L:s1')
    settings.pass('L:s1')
    assert.equal(JSON.parse(storage.data[GROWTH_KEY]).steps, 1)
    assert.equal(settings.store.getState().steps, 1)
  })

  it('a window follows a count made in another one, without its own level-up moment', () => {
    const storage = memory()
    const overlay = createGrowth({ app: true, storage })
    const settings = createGrowth({ app: true, storage })
    passMany(overlay, 3)
    settings.onStorage(GROWTH_KEY, storage.data[GROWTH_KEY])
    assert.deepEqual(settings.store.getState(), { steps: 3, level: 2, grew: 0 })
    settings.onStorage('other', '{"steps":50,"seen":[]}')
    settings.onStorage(GROWTH_KEY, 'not json')
    assert.equal(settings.store.getState().steps, 3)
  })

  it('a damaged save starts again from a Seed instead of breaking', () => {
    for (const bad of ['{', '{"steps":"many"}', '{"steps":-3}', 'null']) {
      const g = createGrowth({ app: true, storage: memory({ [GROWTH_KEY]: bad }) })
      assert.equal(g.store.getState().level, 1, bad)
    }
  })

  it('storage that throws does not stop it growing', () => {
    const g = createGrowth({
      app: true,
      storage: {
        getItem: () => {
          throw new Error('denied')
        },
        setItem: () => {
          throw new Error('denied')
        }
      }
    })
    assert.deepEqual(passMany(g, 3), [undefined, undefined, 2])
  })

  it('the browser stage never writes, and ?level= or ?steps= sets where it starts', () => {
    const storage = memory({ [GROWTH_KEY]: '{"steps":40,"seen":[]}' })
    const plain = createGrowth({ app: false, search: '?buddy=grow', storage })
    assert.equal(plain.store.getState().level, 1)
    passMany(plain, 3)
    assert.equal(plain.store.getState().level, 2)
    assert.equal(JSON.parse(storage.data[GROWTH_KEY]).steps, 40)
    assert.equal(createGrowth({ app: false, search: '?level=6' }).store.getState().steps, 40)
    assert.equal(createGrowth({ app: false, search: '?steps=14' }).store.getState().level, 3)
    assert.equal(createGrowth({ app: true, search: '?level=8', storage: memory() }).store.getState().level, 1)
  })
})
