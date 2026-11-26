/** The island's black is the notch's black: pure, opaque, no grey ring. And the pill re-fits under the menu bar. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { belowTop } from '../src/common/notch'
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
    const d = (y: number) => ({ id: 1, bounds: { x: 0, y: 0, width: 100, height: 100 }, workArea: { x: 0, y, width: 100, height: 100 - y } })
    // Mac: flush with the menu bar's bottom edge (MacBook Neo, Nov 25: no more floating 16 pt under it).
    assert.equal(belowTop(d(37), { mac: true }), 37)
    assert.equal(belowTop(d(24), { mac: true }), 24)
    assert.equal(belowTop(d(0), { mac: true }), 0)
    // MIYAGI_PILL_TOP and Windows keep the old rule: never higher than 4 under the band.
    assert.equal(belowTop(d(37), { mac: true, override: 8 }), 41)
    assert.equal(belowTop(d(24), { mac: true, override: 40 }), 40)
    assert.equal(belowTop(d(0), { mac: true, override: 40 }), 40)
    assert.equal(belowTop(d(0), { mac: false }), 8)
    assert.equal(belowTop(d(40), { mac: false }), 44)
  })
})
