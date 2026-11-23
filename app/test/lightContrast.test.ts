/** Light mode: the secondary and faint text inks stay readable (4.5:1, WCAG AA) on the white content panel. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { themeCss } from '../src/renderer/src/core/theme'

const lum = (c: number[]): number => {
  const f = (v: number): number => ((v /= 255) <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4))
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])
}

/** The light value of a `--name: dark; light` pair from themeCss(), as [r, g, b, a] (rgba() or #RRGGBB). */
function light(name: string): number[] {
  const css = themeCss()
  const block = css.slice(css.indexOf(':root[data-appearance="light"]'))
  const m = block.match(new RegExp(`--${name}:\\s*(?:rgba?\\(([^)]+)\\)|#([0-9a-fA-F]{6}))`))
  assert.ok(m, `--${name} not found in the light block`)
  if (m[2]) return [0, 2, 4].map((i) => parseInt(m[2].slice(i, i + 2), 16)).concat(1)
  const p = m[1].split(',').map((s) => Number(s.trim()))
  return [p[0], p[1], p[2], p[3] ?? 1]
}

/** Contrast of a themed ink over a background (default white; the cream pane is #F6F6F3). */
function onWhite(name: string, bg: number[] = [255, 255, 255]): number {
  const [r, g, b, a] = light(name)
  const mix = [r, g, b].map((v, i) => v * a + bg[i] * (1 - a))
  const [hi, lo] = [lum(bg), lum(mix)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}
const PAPER = [246, 246, 243]

describe('light mode contrast', () => {
  test('label ink is at least 4.5:1 on the white panel', () => assert.ok(onWhite('c-label') >= 4.5, String(onWhite('c-label'))))
  test('faint ink is at least 4.5:1 on the white panel', () => assert.ok(onWhite('c-faint') >= 4.5, String(onWhite('c-faint'))))
})

describe('light mode contrast on the cream pane', () => {
  test('label ink is at least 4.5:1 on #F6F6F3', () => assert.ok(onWhite('c-label', PAPER) >= 4.5, String(onWhite('c-label', PAPER))))
  test('faint ink is at least 4.5:1 on #F6F6F3', () => assert.ok(onWhite('c-faint', PAPER) >= 4.5, String(onWhite('c-faint', PAPER))))
})
