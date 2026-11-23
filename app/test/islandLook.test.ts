/** The island's black is the notch's black: pure, opaque, no grey ring. And the pill re-fits under the menu bar. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { fitPillTop } from '../src/main/platform'
import { color, hud, shadows } from '../src/renderer/src/core/theme'

describe('island look', () => {
  test('the island is pure opaque #000 (hud.notch)', () => {
    assert.equal(hud.notch, '#000000')
    assert.equal(color.island, hud.notch)
  })
  test('no grey ring on the pill or the card: the edge ring is the notch black', () => {
    assert.ok(shadows.pill.startsWith(`0 0 0 0.5px ${hud.notch}`))
    assert.ok(!/255,\s*255,\s*255/.test(shadows.pill))
  })
  test('the pill re-fits under a notch band and stays put on a hidden menu bar', () => {
    const rect = (y: number) => ({ x: 0, y, width: 100, height: 100 })
    assert.equal(fitPillTop(8, { bounds: rect(0), workArea: rect(37) }), 41)
    assert.equal(fitPillTop(40, { bounds: rect(0), workArea: rect(24) }), 40)
    assert.equal(fitPillTop(40, { bounds: rect(0), workArea: rect(0) }), 40)
  })
})
