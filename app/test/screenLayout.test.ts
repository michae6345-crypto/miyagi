// Video-lesson layout (common/screenLayout.ts) on the shared golden cases (shared/layout-cases.json, also checked by
// the engine's server/workspace/tests/test_layout.py), the player dock built on it, and the anti-jitter rules: a
// work-area-only display change never fades or refits the overlay, an open card stays put when the box moves clear.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { EventEmitter } from 'node:events'
import { test } from 'node:test'
import { VIDEO_LAYOUT, videoEditorWidth, videoLayout, type Box } from '../src/common/screenLayout'
import { coversAny, dockRect } from '../src/renderer/src/core/geometry'
import { OVERLAY_RESTORE_MS, trackOverlayLifecycle, workAreaOnly } from '../src/main/platform'

type Case = { name: string; frame: number[]; visible: number[]; safe_top: number; expect: { video: { editor: number[]; column_editor_w: number; player: number[]; panel: number[]; stacked: boolean } } }
const cases = (JSON.parse(readFileSync(new URL('../../shared/layout-cases.json', import.meta.url), 'utf8')) as { cases: Case[] }).cases
const box = ([x, y, width, height]: number[]): Box => ({ x, y, width, height })
const arr = (b: Box): number[] => [b.x, b.y, b.width, b.height]
const right = (b: Box): number => b.x + b.width
const bottom = (b: Box): number => b.y + b.height
const byName = (start: string): Case => cases.find((c) => c.name.startsWith(start))!

for (const c of cases) {
  test(`golden: ${c.name}`, () => {
    const wa = box(c.visible)
    const v = videoLayout(wa)
    assert.equal(v.editor.width, c.expect.video.column_editor_w)
    // the engine moves VS Code to the same right edge (its top also clears the island row: not compared)
    assert.equal(right(v.editor), c.expect.video.editor[0] + c.expect.video.editor[2])
    assert.deepEqual(arr(v.player), c.expect.video.player)
    assert.deepEqual(arr(v.panel), c.expect.video.panel)
    assert.equal(v.stacked, c.expect.video.stacked)
    // nothing over VS Code, nothing off the work area, the player and the drawer never overlap
    assert.ok(v.player.x >= right(v.editor) && v.panel.x >= right(v.editor))
    assert.ok(right(v.player) <= right(wa) && right(v.panel) <= right(wa) && bottom(v.panel) <= bottom(wa) && bottom(v.player) <= bottom(wa))
    const apart = v.stacked ? bottom(v.player) <= v.panel.y : right(v.player) <= v.panel.x
    assert.ok(apart)
    assert.ok(v.player.width >= 360 && v.player.height >= VIDEO_LAYOUT.minPlayerH)
    // the player window and everything that reads the dock (cards, spotlight, drawer tab) agree
    assert.deepEqual(dockRect(wa), v.player)
  })
}

test('1440x900 (MacBook Neo class): VS Code 60%, the player above the steps drawer in the right column', () => {
  const v = videoLayout(box(byName('13-inch 1440x900, no notch, Dock bottom').visible))
  assert.equal(v.editor.width, 864)
  assert.equal(v.stacked, true)
  assert.deepEqual(arr(v.player), [872, 33, 560, 465]) // 16:9 at 560 wide is 315, plus the header and controls
  assert.ok(v.panel.height >= VIDEO_LAYOUT.minPanelH)
})

test('1512x982 (MacBook Pro 14) stacks; 2560x1440 puts the drawer beside the player', () => {
  assert.equal(videoLayout(box(byName('14-inch 1512x982, notch, Dock bottom').visible)).stacked, true)
  const wide = videoLayout(box(byName('external 2560x1440').visible))
  assert.equal(wide.stacked, false)
  assert.equal(wide.panel.width, VIDEO_LAYOUT.panelW)
  assert.equal(right(wide.panel), 2560 - VIDEO_LAYOUT.inset)
})

test('the right column never gets narrower than minColumn, and the player dock keeps its old place', () => {
  assert.equal(videoEditorWidth(800), 400) // 60% would leave 320
  // continuity: the player's x and width are where the old "right 40%" dock put it
  for (const w of [1280, 1440, 1512, 1728]) {
    const old = Math.round(w * 0.4) - 16
    assert.equal(dockRect({ x: 0, y: 25, width: w, height: 800 }).x, w - old - 8)
  }
})

test('workAreaOnly: menu bar / Dock changes only', () => {
  assert.equal(workAreaOnly(['workArea']), true)
  assert.equal(workAreaOnly(['workArea', 'bounds']), false)
  assert.equal(workAreaOnly(['scaleFactor']), false)
  assert.equal(workAreaOnly([]), false)
  assert.equal(workAreaOnly(undefined), false)
})

test('a work-area-only display change never fades or refits the overlay (no back and forth as VS Code opens)', { skip: process.platform !== 'darwin' }, async () => {
  const log: string[] = []
  const win = {
    isDestroyed: () => false,
    isVisible: () => true,
    setOpacity: (o: number) => void log.push(`opacity:${o}`),
    setBounds: () => undefined,
    showInactive: () => undefined,
    hide: () => undefined,
    moveTop: () => void log.push('moveTop'),
    setAlwaysOnTop: () => undefined,
    setVisibleOnAllWorkspaces: () => undefined
  }
  const screen = new EventEmitter()
  let refits = 0
  const stop = trackOverlayLifecycle(win as never, { screen, powerMonitor: new EventEmitter() }, () => void refits++)
  try {
    screen.emit('display-metrics-changed', {}, {}, ['workArea'])
    screen.emit('display-metrics-changed', {}, {}, ['workArea'])
    await new Promise((r) => setTimeout(r, OVERLAY_RESTORE_MS + 60))
    assert.deepEqual(log, [])
    assert.equal(refits, 0)
    screen.emit('display-metrics-changed', {}, {}, ['bounds', 'workArea']) // a resolution change still refits
    await new Promise((r) => setTimeout(r, OVERLAY_RESTORE_MS + 60))
    assert.equal(refits, 1)
  } finally {
    stop()
  }
})

test('an open card re-places only for a box under it (the box following VS Code as it is laid out moves nothing)', () => {
  const card = { x: 600, y: 40, w: 400, h: 200 }
  assert.equal(coversAny(card, [{ x: 100, y: 400, w: 300, h: 40 }]), false) // the target slid down-left: card stays
  assert.equal(coversAny(card, [{ x: 100, y: 400, w: 300, h: 40 }, { x: 700, y: 100, w: 200, h: 30 }]), true)
  assert.equal(coversAny(card, []), false)
})
