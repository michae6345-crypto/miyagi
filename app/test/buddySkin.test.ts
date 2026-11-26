/**
 * The learner's color for their buddy: the set they pick from (palette.ts PICKS) and how a pick is kept (skin.ts).
 * Run: node --import tsx --import ./test/setup.mjs --test test/buddySkin.test.ts
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { DEFAULT_SKIN, PICK_APART, PICKS, SKINS, type SkinName } from '../src/renderer/src/features/buddy/palette'
import { createSkins, SKIN_KEY } from '../src/renderer/src/features/buddy/skin'

/** sRGB hex to CIE Lab (D65). */
function lab(hex: string): [number, number, number] {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const u = parseInt(hex.slice(i, i + 2), 16) / 255
    return u <= 0.04045 ? u / 12.92 : ((u + 0.055) / 1.055) ** 2.4
  })
  const f = (t: number): number => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116)
  const x = f((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047)
  const y = f(0.2126 * r + 0.7152 * g + 0.0722 * b)
  const z = f((0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883)
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)]
}
const apart = (a: string, b: string): number => Math.hypot(...lab(a).map((v, i) => v - lab(b)[i]))

/** A localStorage stand-in. */
function memory(seed: Record<string, string> = {}): { getItem: (k: string) => string | null; setItem: (k: string, v: string) => void; data: Record<string, string> } {
  const data = { ...seed }
  return { data, getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => void (data[k] = v) }
}

describe('the colors a learner can pick (palette.ts PICKS)', () => {
  it('six to eight of them, none twice, and it comes in the first one', () => {
    assert.ok(PICKS.length >= 6 && PICKS.length <= 8, `${PICKS.length} colors`)
    assert.equal(new Set(PICKS).size, PICKS.length)
    assert.equal(PICKS[0], DEFAULT_SKIN)
  })

  it('no two are easy to mix up: every pair is at least PICK_APART apart in Lab', () => {
    for (let i = 0; i < PICKS.length; i++) {
      for (let j = i + 1; j < PICKS.length; j++) {
        const d = apart(SKINS[PICKS[i]].body, SKINS[PICKS[j]].body)
        assert.ok(d >= PICK_APART, `${PICKS[i]} and ${PICKS[j]} are ${d.toFixed(1)} apart`)
      }
    }
  })

  it('cream is not offered: it is too close to sand', () => {
    assert.ok(!PICKS.includes('cream' as SkinName))
    assert.ok(apart(SKINS.cream.body, SKINS.sand.body) < PICK_APART)
  })

  it('each one draws its loop in its own color', () => {
    for (const p of PICKS) assert.equal(SKINS[p].stroke, SKINS[p].body, p)
  })
})

describe('keeping the pick (skin.ts)', () => {
  it('a new learner: the default, not chosen yet', () => {
    const s = createSkins({ app: true, storage: memory() })
    assert.equal(s.store.getState().name, DEFAULT_SKIN)
    assert.equal(s.chosen(), false)
  })

  it('in the app a pick is saved, and the next launch comes up in it', () => {
    const storage = memory()
    const s = createSkins({ app: true, storage })
    s.pick('peach')
    assert.equal(s.store.getState().name, 'peach')
    assert.equal(s.chosen(), true)
    assert.equal(storage.data[SKIN_KEY], 'peach')
    const next = createSkins({ app: true, storage })
    assert.equal(next.store.getState().name, 'peach')
    assert.equal(next.chosen(), true)
  })

  it('Continue without touching a swatch keeps the one it came in, and that counts as chosen', () => {
    const storage = memory()
    const s = createSkins({ app: true, storage })
    s.confirm()
    assert.equal(s.chosen(), true)
    assert.equal(storage.data[SKIN_KEY], DEFAULT_SKIN)
    assert.equal(createSkins({ app: true, storage }).chosen(), true)
  })

  it('a pick in another window (Settings) reaches this one', () => {
    const s = createSkins({ app: true, storage: memory() })
    s.onStorage(SKIN_KEY, 'sky')
    assert.equal(s.store.getState().name, 'sky')
    s.onStorage('something.else', 'pink')
    s.onStorage(SKIN_KEY, 'not-a-color')
    s.onStorage(SKIN_KEY, null)
    assert.equal(s.store.getState().name, 'sky')
  })

  it('only a color that is offered is taken: a stale or hand-edited value falls back to the default', () => {
    for (const bad of ['cream', 'clay', 'nope', '']) {
      const s = createSkins({ app: true, storage: memory({ [SKIN_KEY]: bad }) })
      assert.equal(s.store.getState().name, DEFAULT_SKIN, bad)
      assert.equal(s.chosen(), false, bad)
    }
    const s = createSkins({ app: true, storage: memory() })
    s.pick('cream' as SkinName)
    assert.equal(s.store.getState().name, DEFAULT_SKIN)
  })

  it('each pick counts, so the picker’s buddy can beam at it', () => {
    const s = createSkins({ app: true, storage: memory() })
    s.pick('pink')
    s.pick('pink')
    s.pick('mint')
    assert.equal(s.store.getState().picks, 3)
  })

  it('storage that throws does not break a pick', () => {
    const s = createSkins({
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
    s.pick('lilac')
    assert.equal(s.store.getState().name, 'lilac')
  })

  it('the browser stage never writes, and ?skin= shows any skin and counts as chosen', () => {
    const storage = memory({ [SKIN_KEY]: 'peach' })
    const plain = createSkins({ app: false, search: '?buddy=pick', storage })
    assert.equal(plain.store.getState().name, DEFAULT_SKIN)
    assert.equal(plain.chosen(), false)
    plain.pick('sky')
    plain.confirm()
    assert.equal(storage.data[SKIN_KEY], 'peach')
    const fixed = createSkins({ app: false, search: '?buddy=point&skin=cream-shade', storage })
    assert.equal(fixed.store.getState().name, 'cream-shade')
    assert.equal(fixed.chosen(), true)
    // ?skin= is a stage tool: the app ignores it.
    assert.equal(createSkins({ app: true, search: '?skin=mint', storage: memory() }).store.getState().name, DEFAULT_SKIN)
  })
})
