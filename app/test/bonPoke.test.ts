/**
 * Tap bon and it plays (Poke.tsx): each tap the next trick, round and round.
 * Run: node --import tsx --import ./test/setup.mjs --test test/bonPoke.test.ts
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { TRICKS, trickFor } from '../src/renderer/src/features/buddy/Poke'

describe('tap bon', () => {
  it('plays hop, wiggle, twirl, then round again', () => {
    assert.deepEqual([0, 1, 2, 3, 4].map(trickFor), ['hop', 'wiggle', 'twirl', 'hop', 'wiggle'])
  })
  it('never falls off the list', () => {
    for (const n of [-1, 7, 1000]) assert.ok(TRICKS.includes(trickFor(n)))
  })
})
