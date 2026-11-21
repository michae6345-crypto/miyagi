/** launcher/guard.ts, offline: the double-open bug of UI-TEST 2026-11-21 (the focus fix lives in main/index.ts hideLauncher). */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { isDuplicateToggle, OPEN_GUARD_MS } from '../src/renderer/src/features/launcher/guard'

describe('launcher double-open guard', () => {
  test('a second toggle inside the window is ignored, a later one closes', () => {
    assert.equal(isDuplicateToggle(0), true)
    assert.equal(isDuplicateToggle(OPEN_GUARD_MS - 1), true)
    assert.equal(isDuplicateToggle(OPEN_GUARD_MS), false)
    assert.equal(isDuplicateToggle(5000), false)
  })
  test('a clock that went backwards never blocks a close', () => {
    assert.equal(isDuplicateToggle(-5), false)
  })
})
