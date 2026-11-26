/** features/drawer/v2/drag.ts: moving the docked lesson panel by its header (user report, main 1d453ca0). */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { clampOffset, HOME, isDrag, KEEP_VISIBLE, movedMaxHeight, movedRect, ownsPress, parseOffset } from '../src/renderer/src/features/drawer/v2/drag'

// 1440x900 with a 25 pt menu bar: the dock at right 16, top 52, 360 wide (core/dock panelRect).
const area = { x: 0, y: 25, w: 1440, h: 875 }
const home = { x: 1440 - 16 - 360, y: 52, w: 360, h: 900 - 16 - 52 }

describe('panel drag', () => {
  test('a press that barely moves is a click, not a drag', () => {
    assert.equal(isDrag(0, 0), false)
    assert.equal(isDrag(2, 2), false)
    assert.equal(isDrag(4, 0), true)
    assert.equal(isDrag(-3, -3), true)
  })

  test('a move inside the work area is kept as is', () => {
    assert.deepEqual(clampOffset(home, { dx: -600, dy: 100 }, area), { dx: -600, dy: 100 })
  })

  test('never past the right or left edge: the whole width stays on screen', () => {
    assert.deepEqual(clampOffset(home, { dx: 500, dy: 0 }, area), { dx: 16, dy: 0 })
    assert.deepEqual(clampOffset(home, { dx: -5000, dy: 0 }, area), { dx: -home.x, dy: 0 })
  })

  test('never above the work area (menu bar, notch), and the header stays above the bottom', () => {
    assert.deepEqual(clampOffset(home, { dx: 0, dy: -200 }, area), { dx: 0, dy: area.y - home.y })
    const low = clampOffset(home, { dx: 0, dy: 5000 }, area)
    assert.equal(home.y + low.dy, area.y + area.h - KEEP_VISIBLE)
  })

  test('a junk offset is home', () => {
    assert.deepEqual(clampOffset(home, { dx: Number.NaN, dy: Infinity }, area), HOME)
  })

  test('moved down, the panel gets shorter; moved up or sideways, it keeps its height', () => {
    assert.equal(movedMaxHeight(home, { dx: 0, dy: 200 }), home.h - 200)
    assert.equal(movedMaxHeight(home, { dx: -300, dy: -10 }), home.h)
    assert.equal(movedMaxHeight(home, { dx: 0, dy: 5000 }), 120)
    assert.deepEqual(movedRect(home, { dx: -100, dy: 40 }), { x: home.x - 100, y: home.y + 40, w: 360, h: home.h - 40 })
  })

  test('a saved offset is read back, anything else is home', () => {
    assert.deepEqual(parseOffset('{"dx":-120.4,"dy":33}'), { dx: -120, dy: 33 })
    assert.deepEqual(parseOffset(null), HOME)
    assert.deepEqual(parseOffset('nope'), HOME)
    assert.deepEqual(parseOffset('{"dx":"1","dy":2}'), HOME)
  })

  test('a press on the header buttons is theirs, not a drag', () => {
    const el = (hit: boolean): EventTarget => ({ closest: () => (hit ? {} : null) }) as unknown as EventTarget
    assert.equal(ownsPress(el(true)), true)
    assert.equal(ownsPress(el(false)), false)
    assert.equal(ownsPress(null), false)
  })
})
