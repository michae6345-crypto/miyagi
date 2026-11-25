// The overlay window's flags and bounds are load-bearing for the notch: pin them.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { overlayBounds, overlayWindowOptions } from '../src/main/platform'

const display = { bounds: { x: 0, y: 0, width: 1728, height: 1117 }, workArea: { x: 0, y: 38, width: 1728, height: 1079 } }

test('overlay bounds are the display bounds, not the work area', () => {
  assert.deepEqual(overlayBounds(display), display.bounds)
  const o = overlayWindowOptions(overlayBounds(display))
  assert.deepEqual({ x: o.x, y: o.y, width: o.width, height: o.height }, display.bounds)
  assert.notEqual(o.y, display.workArea.y)
})

test('overlay window flags', () => {
  const o = overlayWindowOptions(overlayBounds(display))
  assert.equal(o.frame, false)
  assert.equal(o.enableLargerThanScreen, true)
  assert.equal(o.focusable, false)
  assert.equal(o.transparent, true)
  assert.equal(o.alwaysOnTop, true)
  assert.equal(o.hasShadow, false)
  assert.equal(o.fullscreenable, false)
})

test('macOS overlay is a panel', { skip: process.platform !== 'darwin' }, () => {
  assert.equal(overlayWindowOptions(display.bounds).type, 'panel')
})
