// MIC-89: the notch home panel's layout math (features/notch-home/layout.ts). Michael's shot (Nov 26) had the step line
// and the progress bar running under the right column, Continue on the bottom edge and bon jammed into the Library row.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { HOME, HOME_W, PANEL_INSET, bodyHeight, dropLabel, homeColumns, panelHeight, progressSegs, rightHeight, sideInsetAt } from '../src/renderer/src/features/notch-home/layout'
import { NOTCH_RADII, notchSize } from '../src/renderer/src/core/notchGeometry'
import type { NotchLayout } from '../src/common/notch'

test('the columns, the gutters and the divider add up to the panel width', () => {
  const c = homeColumns()
  assert.equal(HOME.padX + c.left + HOME.gutter + HOME.rule + HOME.gutter + c.right + HOME.padX, HOME_W)
  assert.equal(c.inner, HOME_W - 2 * HOME.padX)
  // The divider sits one gutter after the left column, the right column one gutter after the divider.
  assert.equal(c.ruleX, HOME.padX + c.left + HOME.gutter)
  assert.equal(c.rightX, c.ruleX + HOME.rule + HOME.gutter)
  assert.equal(c.rightX + c.right + HOME.padX, HOME_W)
})

test('each column has room for its content', () => {
  const c = homeColumns()
  // Left: the thumbnail plus a title column of ~24 characters a line (two lines), and Continue lesson (about 150 wide).
  assert.ok(c.text >= 170, `title column ${c.text}`)
  assert.ok(c.left >= 150 + 2 * 40, `left ${c.left}`)
  // Right: wider than the 200 that cut "React Basics: Building Re…" short.
  assert.ok(c.right > 200, `right ${c.right}`)
  // The footer holds Library (about 80) and bon's own slot, apart.
  assert.ok(c.right - (80 + HOME.bonGap + HOME.row) >= 40, 'Library and bon do not touch')
})

test('the thumbnail is 16:9 and the title block is no taller than two title lines and its label', () => {
  assert.equal(Math.round((HOME.thumb.w / HOME.thumb.h) * 9), 16)
  // label 14 + gap 2 + two lines of 18 = 52; the thumbnail must not overhang the block by more than a line.
  assert.ok(HOME.thumb.h <= 52)
})

test('the right column grows with its ready lessons, capped at HOME.ready', () => {
  const base = HOME.row + HOME.rowGap + HOME.drop + HOME.footGap + HOME.row
  assert.equal(rightHeight(0), base)
  assert.equal(rightHeight(1), base + HOME.rowGap + HOME.row)
  assert.equal(rightHeight(2), base + 2 * (HOME.rowGap + HOME.row))
  assert.equal(rightHeight(9), rightHeight(HOME.ready))
  assert.equal(rightHeight(-1), rightHeight(0))
})

test('the body is at least minBody, else the right column; the panel adds its padding', () => {
  for (const n of [0, 1, 2]) {
    assert.equal(bodyHeight(n), Math.max(HOME.minBody, rightHeight(n)))
    assert.equal(panelHeight(n), HOME.padTop + bodyHeight(n) + HOME.padBottom)
  }
  // The left half's own content fits in the shortest body: title block 52 + step line 8 + 16, progress 3, Continue 30,
  // with at least 12 between groups.
  assert.ok(HOME.minBody >= 52 + 8 + 16 + 12 + 3 + 12 + 30)
})

test('progress segments: done, the step you are on, the rest; at most 24', () => {
  assert.deepEqual(progressSegs(1, 7), ['at', 'todo', 'todo', 'todo', 'todo', 'todo', 'todo'])
  assert.deepEqual(progressSegs(3, 6), ['done', 'done', 'at', 'todo', 'todo', 'todo'])
  assert.deepEqual(progressSegs(6, 6), ['done', 'done', 'done', 'done', 'done', 'at'])
  assert.equal(progressSegs(5, 60).length, 24)
  assert.equal(progressSegs(60, 60).filter((s) => s === 'at').length, 1)
  // Out of range never draws past the end or a second "at".
  assert.deepEqual(progressSegs(9, 3), ['done', 'done', 'at'])
  assert.deepEqual(progressSegs(0, 3), ['at', 'todo', 'todo'])
  assert.deepEqual(progressSegs(1, 0), [])
})

test('the drop zone names any link, not only YouTube', () => {
  assert.equal(dropLabel({ sent: false, miss: false, linkAny: false }), 'Drop a link to learn it')
  assert.equal(dropLabel({ sent: false, miss: false, linkAny: true }), 'Drop a link to learn it')
  assert.equal(dropLabel({ sent: true, miss: false, linkAny: true }), 'Building your lesson…')
  assert.match(dropLabel({ sent: false, miss: true, linkAny: true }), /can read/)
  assert.doesNotMatch(dropLabel({ sent: false, miss: false, linkAny: false }), /YouTube/)
})

test('the panel sits inside the island the way notchSize sizes it', () => {
  assert.equal(PANEL_INSET, NOTCH_RADII.open.top + NOTCH_RADII.open.taper)
  const nm: NotchLayout = { hasNotch: true, x: 620, width: 200, height: 32, place: 'notch', coexist: false }
  const s = notchSize(nm, 'card', 'drop', HOME_W, { w: HOME_W, h: panelHeight(2) })
  assert.equal(s.w, HOME_W + 2 * PANEL_INSET)
  assert.equal(s.h, nm.height + panelHeight(2))
})

test('the side inset follows the open shape: ear, slanted side, rounded bottom corner', () => {
  const h = 230
  const { top, taper, bottom } = NOTCH_RADII.open
  assert.equal(sideInsetAt(h, 0), top)
  assert.equal(sideInsetAt(h, top), top)
  // The slanted side leans in steadily, then the corner curves in to top + taper + bottom at the very bottom.
  assert.ok(sideInsetAt(h, h / 2) > top && sideInsetAt(h, h / 2) < top + taper)
  assert.ok(sideInsetAt(h, h - bottom / 2) > sideInsetAt(h, h - bottom))
  assert.ok(Math.abs(sideInsetAt(h, h) - (top + taper + bottom)) < 1e-9)
})

// 14" and 16" MacBook Pro notches (about 185 and 200 wide; 32 and 38 tall with the menu bar), with 0 to 2 ready lessons.
const NOTCHES: NotchLayout[] = [
  { hasNotch: true, x: 663, width: 185, height: 32, place: 'notch', coexist: false },
  { hasNotch: true, x: 656, width: 200, height: 38, place: 'notch', coexist: false }
]

test('nothing is clipped: every corner of the content clears the slanted sides and the bottom corners', () => {
  for (const nm of NOTCHES) {
    for (const ready of [0, 1, 2]) {
      const H = nm.height + panelHeight(ready)
      const contentEdge = PANEL_INSET + HOME.padX // the content's left (and, mirrored, right) edge from the island's edge
      const top = nm.height + HOME.padTop // the content's first pixel row, under the notch
      const bottom = H - HOME.padBottom // its last
      assert.ok(top >= nm.height + 8, `${nm.height}: content starts under the notch`)
      for (let y = top; y <= bottom; y += 1) {
        const side = sideInsetAt(H, y)
        assert.ok(contentEdge - side >= HOME.clearance, `notch ${nm.width}x${nm.height}, ${ready} ready: ${(contentEdge - side).toFixed(1)} px at y ${y}`)
      }
      // The bottom padding clears the bottom edge itself.
      assert.ok(H - bottom >= HOME.clearance + 8)
    }
  }
})

test('the open shape stays wider than the notch it hangs from, at every notch', () => {
  for (const nm of NOTCHES) assert.ok(HOME_W + 2 * PANEL_INSET > nm.width + 2 * 36)
})
