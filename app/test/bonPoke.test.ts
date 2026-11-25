import { describe, expect, it } from 'vitest'
import { TRICKS, trickFor } from '../src/renderer/src/features/buddy/Poke'

describe('tap bon', () => {
  it('plays hop, wiggle, twirl, then round again', () => {
    expect([0, 1, 2, 3, 4].map(trickFor)).toEqual(['hop', 'wiggle', 'twirl', 'hop', 'wiggle'])
  })
  it('never falls off the list', () => {
    for (const n of [-1, 7, 1000]) expect(TRICKS).toContain(trickFor(n))
  })
})
