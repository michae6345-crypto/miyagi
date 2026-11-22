// Settings > General: no mention of other notch apps; the island caption names only where miyagi is.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const src = readFileSync(new URL('../src/renderer/src/features/settings/sections/General.tsx', import.meta.url), 'utf8')

test('General.tsx never mentions Boring Notch', () => {
  assert.doesNotMatch(src, /boring/i)
  assert.doesNotMatch(src, /other notch app/i)
})

test('the island caption says where miyagi is, in two places only', () => {
  const states = [...src.matchAll(/'miyagi is (in the notch|below the menu bar) now\.'/g)].map((m) => m[1])
  assert.deepEqual(states.sort(), ['below the menu bar', 'in the notch'])
})
