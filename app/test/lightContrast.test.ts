/** Light mode: the secondary and faint text inks stay readable (4.5:1, WCAG AA) on the white content panel. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { themeCss } from '../src/renderer/src/core/theme'

const lum = (c: number[]): number => {
  const f = (v: number): number => ((v /= 255) <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4))
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])
}

/** The light value of a `--name: dark; light` pair from themeCss(), as [r, g, b, a]. */
function light(name: string): number[] {
  const css = themeCss()
  const block = css.slice(css.indexOf(':root[data-appearance="light"]'))
  const m = block.match(new RegExp(`--${name}:\\s*rgba?\\(([^)]+)\\)`))
  assert.ok(m, `--${name} not found in the light block`)
  const p = m[1].split(',').map((s) => Number(s.trim()))
  return [p[0], p[1], p[2], p[3] ?? 1]
}

function onWhite(name: string): number {
  const [r, g, b, a] = light(name)
  const mix = [r, g, b].map((v) => v * a + 255 * (1 - a))
  return (lum([255, 255, 255]) + 0.05) / (lum(mix) + 0.05)
}

describe('light mode contrast', () => {
  test('label ink is at least 4.5:1 on the white panel', () => assert.ok(onWhite('c-label') >= 4.5, String(onWhite('c-label'))))
  test('faint ink is at least 4.5:1 on the white panel', () => assert.ok(onWhite('c-faint') >= 4.5, String(onWhite('c-faint'))))
})
