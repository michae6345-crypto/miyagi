/**
 * The open notch island's pastel gradient in bon's color (Michael, Nov 26) and the three concerns Adrian raised about the
 * mint one (MIC-83): it shows only behind calm panels, every island text token keeps 4.5:1 on its brightest point for
 * every bon color, and theme.ts names it as the brand's one gradient exception.
 * Run: node --import tsx --import ./test/setup.mjs --test test/notchTint.test.ts
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, test } from 'node:test'
import { BLOCKED_PANELS, CALM_PANELS, gradientOn, MODE_PANEL, panelOf, type PanelKind } from '../src/renderer/src/core/islandTone'
import { SHORT_OPEN_H } from '../src/renderer/src/core/notchGeometry'
import { islandText, islandTextOnTint, notchGradient, notchPastel, notchTint, rgbOf } from '../src/renderer/src/core/theme'
import { DEFAULT_SKIN, PICKS, SKINS, type SkinName } from '../src/renderer/src/features/buddy/palette'
import { createSkins, SKIN_KEY } from '../src/renderer/src/features/buddy/skin'
import { homeTone } from '../src/renderer/src/features/notch-home/tone'

type RGB = [number, number, number]
const lin = (c: number): number => {
  const v = c / 255
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
}
const lum = ([r, g, b]: number[]): number => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
const ratio = (x: number[], y: number[]): number => {
  const [l1, l2] = [lum(x), lum(y)].sort((p, q) => q - p)
  return (l1 + 0.05) / (l2 + 0.05)
}
const over = (fg: number[], a: number, bg: number[]): RGB => fg.map((c, i) => c * a + bg[i] * (1 - a)) as RGB
/** A token's value ('#rrggbb' or 'rgba(r,g,b,a)') drawn over `bg`. */
function paint(value: string, bg: RGB): RGB {
  if (value.startsWith('#')) return rgbOf(value)
  const m = value.match(/rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)/)
  assert.ok(m, value)
  return over([+m[1], +m[2], +m[3]], +m[4], bg)
}
const stopsOf = (g: string): { rgb: RGB; a: number; at: number }[] =>
  [...g.matchAll(/rgba\((\d+),(\d+),(\d+),([\d.]+)\) (\d+)%/g)].map((m) => ({ rgb: [+m[1], +m[2], +m[3]] as RGB, a: +m[4], at: +m[5] }))

const ALL_SKINS = Object.keys(SKINS) as SkinName[]
const BLACK: RGB = [0, 0, 0]

describe('the gradient shows only behind calm panels', () => {
  test('blocked kinds: Not yet, error, offline, permission, failed (and any warning) never get it', () => {
    for (const k of ['notyet', 'error', 'offline', 'permission', 'failed', 'warning'] as const) assert.ok((BLOCKED_PANELS as readonly string[]).includes(k), k)
    for (const k of BLOCKED_PANELS) {
      assert.equal(gradientOn(true, 400, k), false, k)
      assert.ok(!(CALM_PANELS as readonly string[]).includes(k))
    }
  })
  test('calm panels get it open and tall only: closed and the short peek stay plain black', () => {
    for (const k of CALM_PANELS) {
      assert.equal(gradientOn(true, 194, k), true, k)
      assert.equal(gradientOn(true, SHORT_OPEN_H, k), true, k)
      assert.equal(gradientOn(true, 74, k), false, k)
      assert.equal(gradientOn(false, 194, k), false, k)
      assert.equal(gradientOn(false, 32, k), false, k)
    }
  })
  test('a mode nobody classified is plain black (opt-in)', () => {
    assert.equal(panelOf('build-card'), 'other')
    assert.equal(panelOf(undefined), 'other')
    assert.equal(gradientOn(true, 400, panelOf('some-new-card')), false)
  })
  test('every warning mode maps to a blocked kind; the notch home is the calm one', () => {
    const blocked: Record<string, PanelKind> = {
      offtrack: 'notyet',
      'err-crash': 'error',
      'err-engine-offline': 'offline',
      'err-net-offline': 'offline',
      'err-reconnecting': 'offline',
      'err-build-failed': 'failed',
      'err-editor-closed': 'error',
      'err-stopped': 'error',
      'err-limit': 'warning',
      'err-blocker': 'warning',
      'err-busy': 'warning',
      'ptt-card': 'permission',
      'onboarding-recovery': 'permission',
      'signin-card': 'warning',
      'cap-line': 'warning'
    }
    for (const [id, kind] of Object.entries(blocked)) {
      assert.equal(panelOf(id), kind, id)
      assert.equal(gradientOn(true, 400, panelOf(id)), false, id)
    }
    for (const [id, kind] of Object.entries(MODE_PANEL)) if (id !== 'notch-home') assert.ok((BLOCKED_PANELS as readonly string[]).includes(kind), id)
    assert.equal(panelOf('notch-home'), 'home')
    assert.equal(gradientOn(true, 194, panelOf('notch-home')), true)
  })
  test("the notch home turns 'warning' (plain black) while it says a link can't be used", () => {
    assert.equal(homeTone({ miss: false }), 'home')
    assert.equal(homeTone({ dropped: 'https://a.example', preview: undefined, miss: false }), 'home')
    assert.equal(homeTone({ dropped: 'https://a.example', preview: { teachable: true }, miss: false }), 'home')
    assert.equal(homeTone({ dropped: 'https://a.example', preview: { teachable: false }, miss: false }), 'warning')
    assert.equal(homeTone({ dropped: 'https://a.example', preview: { error: 'not_found' }, miss: false }), 'warning')
    assert.equal(homeTone({ miss: true }), 'warning')
    assert.equal(gradientOn(true, 194, panelOf('notch-home', homeTone({ miss: true }))), false)
  })
})

describe("bon's pastel gradient", () => {
  test('black to 35% (melts into the hardware notch), then only rising to a muted pastel at the bottom edge', () => {
    for (const name of ALL_SKINS) {
      const g = notchGradient(SKINS[name].body)
      assert.match(g, /^linear-gradient\(180deg,/)
      const stops = stopsOf(g)
      assert.ok(stops.length >= 5, name)
      assert.equal(stops[0].at, 0)
      assert.equal(stops[stops.length - 1].at, 100)
      for (const s of stops.filter((x) => x.at <= 35)) assert.equal(s.a, 0, name)
      for (let i = 1; i < stops.length; i++) assert.ok(stops[i].a >= stops[i - 1].a && stops[i].at > stops[i - 1].at, name)
      const last = stops[stops.length - 1]
      assert.ok(last.a >= 0.25 && last.a <= 0.4, `${name} ${last.a}`)
    }
  })
  test("it is bon's color, softened toward white: each bon color gives its own gradient", () => {
    const seen = new Set<string>()
    for (const name of PICKS) {
      const body = rgbOf(SKINS[name].body)
      const p = notchPastel(SKINS[name].body)
      p.forEach((c, i) => assert.ok(c >= body[i], `${name}: lighter, never darker`))
      assert.deepEqual(stopsOf(notchGradient(SKINS[name].body))[0].rgb, p)
      seen.add(notchGradient(SKINS[name].body))
    }
    assert.equal(seen.size, PICKS.length)
  })
  test('every island text token keeps >= 4.5:1 on the brightest point for every bon color (muted ones step up on it)', () => {
    const tokens = Object.keys(islandText) as (keyof typeof islandText)[]
    for (const name of ALL_SKINS) {
      const last = stopsOf(notchGradient(SKINS[name].body)).at(-1)!
      const bg = over(last.rgb, last.a, BLACK)
      assert.ok(Math.abs(last.a - notchTint.alpha) < 1e-9)
      for (const t of tokens) {
        const value = (islandTextOnTint as Partial<Record<string, string>>)[t] ?? islandText[t]
        const r = ratio(paint(value, bg), bg)
        assert.ok(r >= 4.5, `${t} on ${name}: ${r.toFixed(2)}:1`)
        // And on the black top of the same panel.
        assert.ok(ratio(paint(value, BLACK), BLACK) >= 4.5, `${t} on black`)
      }
    }
  })
  test('the brighter muted set is needed (the plain faint grey would fail on the gradient)', () => {
    const last = stopsOf(notchGradient(SKINS[DEFAULT_SKIN].body)).at(-1)!
    const bg = over(last.rgb, last.a, BLACK)
    assert.ok(ratio(paint(islandText['--c-faint'], bg), bg) < 4.5)
    for (const k of Object.keys(islandTextOnTint)) assert.ok(k in islandText, k)
  })
})

describe("live: the gradient follows bon's color", () => {
  const memory = (): { getItem: (k: string) => string | null; setItem: (k: string, v: string) => void } => {
    const m = new Map<string, string>()
    return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v) }
  }
  const gradientFor = (s: ReturnType<typeof createSkins>): string => notchGradient(SKINS[s.store.getState().name].body)
  test("no color chosen: bon's default color", () => {
    const s = createSkins({ app: true, storage: memory() })
    assert.equal(s.chosen(), false)
    assert.equal(gradientFor(s), notchGradient(SKINS[DEFAULT_SKIN].body))
  })
  test('a pick in this window, or in another one (Settings, setup: the storage event), changes it at once', () => {
    const s = createSkins({ app: true, storage: memory() })
    const before = gradientFor(s)
    s.pick('lilac')
    assert.equal(gradientFor(s), notchGradient(SKINS.lilac.body))
    assert.notEqual(gradientFor(s), before)
    s.onStorage(SKIN_KEY, 'peach')
    assert.equal(gradientFor(s), notchGradient(SKINS.peach.body))
  })
})

test("theme.ts names the island gradient as the brand's one gradient exception (Michael's call)", () => {
  const src = readFileSync(new URL('../src/renderer/src/core/theme.ts', import.meta.url), 'utf8')
  assert.match(src, /No gradients[^]*exception[^]*notchGradient/)
  assert.match(src, /Michael's call, Nov 26/)
})
