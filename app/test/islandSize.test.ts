/** core/islandSize.ts, offline: a closed card never leaves the island as an empty card-sized box. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { islandSize, islandSizeFor, PILL_FALLBACK } from '../src/renderer/src/core/islandSize'
import { pill } from '../src/renderer/src/core/theme'

describe('islandSize', () => {
  test('a pill takes its row width and is always pill-tall', () => {
    assert.deepEqual(islandSize(undefined, { w: 211.4, h: 34 }, 120), { w: 212, h: pill.height })
    assert.deepEqual(islandSize(undefined, { w: 380, h: 90 }, 120), { w: 380, h: pill.height })
  })

  test('a pill whose row measures 0 keeps the last pill width, never the card it came from', () => {
    // Michael, Nov 21: card (620 x 280) closed with its X, the pill row measured 0, the island stayed 620 x 280.
    assert.deepEqual(islandSize(undefined, { w: 0, h: 0 }, 180), { w: 180, h: pill.height })
  })

  test('a layer that was never found falls back to the pill', () => {
    assert.deepEqual(islandSize(undefined, undefined, 180), { w: 180, h: pill.height })
    assert.deepEqual(islandSize(620, undefined, 180), { w: 180, h: pill.height })
    assert.deepEqual(islandSize(undefined, undefined, 0), PILL_FALLBACK)
  })

  test('a card is its fixed width and its content height', () => {
    assert.deepEqual(islandSize(620, { w: 620, h: 279.2 }, 120), { w: 620, h: 280 })
  })

  test('a card with nothing in it is the pill, not an empty black card', () => {
    assert.deepEqual(islandSize(560, { w: 560, h: 0 }, 150), { w: 150, h: pill.height })
  })

  test('garbage measurements never win', () => {
    assert.deepEqual(islandSize(undefined, { w: Number.NaN, h: 34 }, 140), { w: 140, h: pill.height })
    assert.deepEqual(islandSize(440, { w: 440, h: Number.POSITIVE_INFINITY }, 140), { w: 140, h: pill.height })
  })

  test('a card whose layer is empty collapses to the pill, not fixed x 34', () => {
    // An empty layer is max-content with the resting pill in it: it measures ~120 x 34 even for a 600px card.
    assert.deepEqual(islandSizeFor(600, true, { w: 120, h: 34 }, 120), { w: 120, h: pill.height })
    // The same for a card whose Boundary fell back to the resting pill inside the body.
    assert.deepEqual(islandSizeFor(600, true, { w: 120, h: 34 }, 150), { w: 120, h: pill.height })
    assert.deepEqual(islandSizeFor(600, false, { w: 600, h: 280 }, 120), { w: 600, h: 280 })
  })
})
