// Where the island goes on a display (common/notch.ts islandAnchor, belowTop, menuBarBottom) and the notch service's
// answer when the helper is missing or times out (main/notch.ts). MacBook Neo, Nov 25: no notch (the camera is in the
// bezel), so the island must hang flush from the menu bar, never float under it, whatever the helper does.
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { belowTop, islandAnchor, MAX_MENU_BAR, menuBarBottom, type ScreenInfo } from '../src/common/notch'
import { startNotch } from '../src/main/notch'

const screen = (id: number, w: number, h: number, safeTop: number, aux: number | null, builtin = true): ScreenInfo => ({
  id,
  frame: { x: 0, y: 0, w, h },
  visible: { x: 0, y: 0, w, h: h - Math.max(24, safeTop) },
  safeTop,
  auxLeft: aux,
  auxRight: aux,
  scale: 2,
  builtin
})
const disp = (id: number, w: number, h: number, band: number, x = 0) => ({ id, bounds: { x, y: 0, width: w, height: h }, workArea: { x, y: band, width: w, height: h - band } })

// 14-inch MacBook Pro: a 32 pt notch, 38 pt menu bar band.
const MBP = { d: disp(1, 1512, 982, 38), s: screen(1, 1512, 982, 32, 661) }
// MacBook Neo: no notch, a plain 24 pt menu bar; NSScreen reports safeAreaInsets.top 0 and no auxiliary areas.
const NEO = { d: disp(1, 1408, 881, 24), s: screen(1, 1408, 881, 0, null) }
// A 27-inch external display beside it, with its own menu bar.
const EXT = { d: disp(7, 2560, 1440, 25, 1512), s: screen(7, 2560, 1440, 0, null, false) }

describe('islandAnchor', () => {
  test('notch: the island sits in the notch, top 0', () => {
    const a = islandAnchor(MBP.d, { mac: true, known: true, info: MBP.s })
    assert.equal(a.place, 'notch')
    assert.equal(a.top, 0)
    assert.equal(a.notch.hasNotch, true)
    assert.equal(a.notch.width, 194)
  })

  test('notch, but the pref says below: flush under the notch band', () => {
    const a = islandAnchor(MBP.d, { mac: true, known: true, info: MBP.s, pref: 'below' })
    assert.deepEqual([a.place, a.top], ['below', 38])
  })

  test('no notch (MacBook Neo): flush with the menu bar bottom, centred, never a fake notch', () => {
    const a = islandAnchor(NEO.d, { mac: true, known: true, info: NEO.s })
    assert.equal(a.place, 'below')
    assert.equal(a.top, 24) // the menu bar's bottom edge: no gap, no float (it was 40)
    assert.equal(a.notch.hasNotch, false)
    assert.equal(a.notch.x, (1408 - a.notch.width) / 2)
  })

  test('helper missing or timed out (no info, nothing known): still top-anchored from the work area', () => {
    for (const d of [NEO.d, MBP.d]) {
      const a = islandAnchor(d, { mac: true, known: false })
      assert.equal(a.place, 'below')
      assert.equal(a.top, d.workArea.y)
    }
    // Known from the cache for another display but not this one: same answer, never a notch.
    assert.equal(islandAnchor(MBP.d, { mac: true, known: true }).place, 'below')
    assert.equal(islandAnchor(MBP.d, { mac: true, known: true }).top, 38)
  })

  test('external display: below its own menu bar, display-local', () => {
    const a = islandAnchor(EXT.d, { mac: true, known: true, info: EXT.s })
    assert.equal(a.place, 'below')
    assert.equal(a.top, 25)
    assert.equal(a.notch.x, (2560 - a.notch.width) / 2) // centred on that display, not the primary
  })

  test('external display without a menu bar (Displays have separate Spaces off): the display top edge', () => {
    assert.equal(islandAnchor(disp(7, 2560, 1440, 0, 1512), { mac: true, known: true, info: EXT.s, menuBar: false }).top, 0)
  })

  test('a notchless Mac whose menu bar hides itself: under where the menu bar slides in, not at 0', () => {
    assert.equal(islandAnchor(disp(1, 1408, 881, 0), { mac: true, known: true, info: NEO.s }).top, 24)
    assert.equal(islandAnchor(disp(1, 1408, 881, 0), { mac: true, known: false }).top, 24) // helper missing too
  })

  test('never mid-screen: a work area that starts far down is not a menu bar', () => {
    assert.equal(menuBarBottom(disp(1, 1408, 881, 400)), 0)
    assert.equal(islandAnchor(disp(1, 1408, 881, 400), { mac: true, known: false }).top, 24)
    assert.ok(menuBarBottom(disp(1, 1408, 881, 24), { ...NEO.s, safeTop: 500 }) <= MAX_MENU_BAR)
  })

  test('a notched display whose menu bar hides itself: under the notch band (helper safeTop), not behind the notch', () => {
    assert.equal(belowTop(disp(1, 1512, 982, 0), { mac: true, info: MBP.s }), 32)
    assert.equal(islandAnchor(disp(1, 1512, 982, 0), { mac: true, known: true, info: MBP.s, pref: 'below' }).top, 32)
  })

  test('Windows: unchanged (8 px, or 4 under a taskbar at the top); never the notch', () => {
    assert.deepEqual(islandAnchor(disp(1, 1920, 1080, 0), { mac: false, known: true }).top, 8)
    assert.deepEqual(islandAnchor(disp(1, 1920, 1080, 48), { mac: false, known: true }).top, 52)
    assert.equal(islandAnchor(MBP.d, { mac: false, known: true, info: MBP.s }).place, 'below')
  })
})

describe('notch service without a helper answer', () => {
  test('a helper that times out (null twice) still gives a top-anchored island, and a later read moves it into the notch', async () => {
    let answer: ScreenInfo[] | null = null
    let changes = 0
    const svc = startNotch({ helperBin: '/nonexistent', mac: true, onChange: () => changes++, read: async () => answer, isOther: async () => false, retryMs: 1, pollMs: 60_000 })
    try {
      await svc.recheck()
      assert.equal(svc.ready(), false)
      assert.deepEqual([svc.layoutFor(MBP.d, 'notch').place, svc.belowTopFor(MBP.d)], ['below', 38])
      assert.deepEqual([svc.layoutFor(NEO.d, 'notch').place, svc.belowTopFor(NEO.d)], ['below', 24])
      answer = [MBP.s]
      await new Promise((r) => setTimeout(r, 1100)) // recheck is rate-limited to once a second
      await svc.recheck()
      assert.equal(svc.layoutFor(MBP.d, 'notch').place, 'notch')
      assert.ok(changes >= 1)
    } finally {
      svc.stop()
    }
  })

  test('a missing helper binary resolves (never hangs) and the island stays below the menu bar', async () => {
    const svc = startNotch({ helperBin: '/nonexistent/miyagi-listen', mac: true, onChange: () => undefined, isOther: async () => false, retryMs: 1, pollMs: 60_000 })
    try {
      await svc.recheck()
      assert.equal(svc.layoutFor(NEO.d, undefined).place, 'below')
      assert.equal(svc.belowTopFor(NEO.d), 24)
      assert.equal(svc.belowTopFor(NEO.d, 56), 56) // MIYAGI_PILL_TOP still wins
    } finally {
      svc.stop()
    }
  })
})
