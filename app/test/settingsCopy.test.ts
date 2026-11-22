// Settings > General: no mention of other notch apps, and the island caption has exactly two states.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const src = readFileSync(new URL('../src/renderer/src/features/settings/sections/General.tsx', import.meta.url), 'utf8')

test('General.tsx never mentions Boring Notch', () => {
  assert.doesNotMatch(src, /boring/i)
  assert.doesNotMatch(src, /notch:recheck/)
})

test('the island caption has exactly two states, and the no-notch Mac shows the pref as unavailable', () => {
  const states = [...src.matchAll(/'miyagi is (in the notch|below the menu bar) now'/g)].map((m) => m[1])
  assert.deepEqual(states.sort(), ['below the menu bar', 'in the notch'])
  assert.match(src, /Not available/)
  assert.match(src, /!info\.hasNotch/)
})
