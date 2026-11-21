/** main/launcherFocus.ts and launcher/guard.ts, offline: the two launcher bugs of UI-TEST 2026-11-21. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { BLUR_WINDOW_MS, createFocusMemory } from '../src/main/launcherFocus'
import { isDuplicateToggle, OPEN_GUARD_MS } from '../src/renderer/src/features/launcher/guard'

describe('launcher focus memory', () => {
  test('a home window that has the keyboard when the launcher opens comes back on close', () => {
    const m = createFocusMemory()
    m.focus(7)
    m.opened()
    m.blur(7) // the launcher took the keyboard
    assert.equal(m.closed(), 7)
  })

  test('a window that blurred just before the launcher showed counts too', () => {
    let t = 1000
    const m = createFocusMemory(() => t)
    m.focus(7)
    m.blur(7)
    t += BLUR_WINDOW_MS - 1
    m.opened()
    assert.equal(m.closed(), 7)
  })

  test('opened from another app: nothing to restore (the learner\'s app stays in front, never Finder)', () => {
    let t = 1000
    const m = createFocusMemory(() => t)
    m.focus(7)
    m.blur(7) // miyagi lost focus to VS Code long ago
    t += 60_000
    m.opened()
    assert.equal(m.closed(), undefined)
  })

  test('opening twice does not replace the origin, and closing forgets it', () => {
    const m = createFocusMemory()
    m.focus(3)
    m.opened()
    m.focus(9)
    m.opened()
    assert.equal(m.closed(), 3)
    assert.equal(m.closed(), undefined)
  })
})

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
