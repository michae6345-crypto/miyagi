/**
 * "Hide miyagi overlays" (Michael, Nov 25): main/overlayHide.ts (the switch), common/shortcuts.ts (its key, clear of
 * every other global key), features/player/mini.ts (the player's handle), and the wiring the feature relies on.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { hideOverlaysAccelerator, quitAccelerator, sameAccelerator } from '../src/common/shortcuts'
import { describePlatform } from '../src/main/platform'
import { onOverlaysHidden, overlaysHidden, setOverlaysHidden, toggleOverlaysHidden } from '../src/main/overlayHide'
import { MINI, miniRect, restoreRect } from '../src/renderer/src/features/player/mini'

const SRC = join(__dirname, '..', 'src')
const read = (p: string): string => readFileSync(join(SRC, p), 'utf8')

describe('hide miyagi overlays: the switch', () => {
  test('toggles, and listeners hear only changes', () => {
    setOverlaysHidden(false)
    const heard: boolean[] = []
    const off = onOverlaysHidden((h) => heard.push(h))
    assert.equal(toggleOverlaysHidden(), true)
    assert.equal(overlaysHidden(), true)
    setOverlaysHidden(true) // no change: not heard
    assert.equal(setOverlaysHidden(false), false)
    off()
    toggleOverlaysHidden()
    assert.deepEqual(heard, [true, false])
    setOverlaysHidden(false)
  })

  test('a listener that throws does not stop the others', () => {
    setOverlaysHidden(false)
    const heard: boolean[] = []
    const offs = [
      onOverlaysHidden(() => {
        throw new Error('boom')
      }),
      onOverlaysHidden((h) => heard.push(h))
    ]
    const warn = console.warn
    console.warn = () => undefined
    try {
      setOverlaysHidden(true)
    } finally {
      console.warn = warn
    }
    assert.deepEqual(heard, [true])
    offs.forEach((f) => f())
    setOverlaysHidden(false)
  })
})

describe('hide miyagi overlays: its key', () => {
  for (const mac of [true, false]) {
    test(`${mac ? 'Mac' : 'Windows'}: clear of the quit key, every default shortcut and the presenter keys`, () => {
      const key = hideOverlaysAccelerator(mac)
      assert.equal(sameAccelerator(key, quitAccelerator(mac)), false)
      for (const [kind, acc] of Object.entries(describePlatform(mac ? 'darwin' : 'win32').accelerators)) {
        assert.equal(sameAccelerator(key, acc), false, `${key} clashes with ${kind}`)
      }
      const mod = mac ? 'Control+Alt+Command' : 'Control+Alt+Shift'
      for (const p of [`${mod}+Right`, `${mod}+Left`, `${mod}+R`]) assert.equal(sameAccelerator(key, p), false)
    })
  }
})

describe('the player handle', () => {
  const full = { x: 900, y: 40, width: 520, height: 700 }
  const area = { x: 0, y: 25, width: 1440, height: 875 }

  test('the handle keeps the full window’s top-right corner', () => {
    assert.deepEqual(miniRect(full), { x: 900 + 520 - MINI.width, y: 40, width: MINI.width, height: MINI.height })
  })

  test('restoring where the handle still is gives the same bounds back', () => {
    assert.deepEqual(restoreRect(full, miniRect(full), area), full)
  })

  test('a handle dragged to the left edge grows back inside the work area', () => {
    const r = restoreRect(full, { x: 0, y: 600, width: MINI.width, height: MINI.height }, area)
    assert.equal(r.x, 0)
    assert.equal(r.width, 520)
    assert.ok(r.y + r.height <= area.y + area.height)
    assert.ok(r.y >= area.y)
  })

  test('a full size larger than the display is fitted to it', () => {
    const r = restoreRect({ x: 0, y: 0, width: 3000, height: 2000 }, { x: 1200, y: 30, width: MINI.width, height: MINI.height }, area)
    assert.deepEqual(r, { x: 0, y: 25, width: 1440, height: 875 })
  })
})

describe('hide miyagi overlays: wiring', () => {
  test('the overlay grab poll and the interactive signal take no mouse while hidden', () => {
    assert.match(read('main/features/overlay-raise.ts'), /if \(overlaysHidden\(\)\)/)
    assert.match(read('main/index.ts'), /setIgnoreMouseEvents\(!payload \|\| overlaysHidden\(\)/)
  })
  test('the overlay root stays mounted but undrawn, and reports no bounds while hidden', () => {
    const o = read('renderer/src/core/Overlay.tsx')
    assert.match(o, /visibility: 'hidden', pointerEvents: 'none'/)
    assert.match(o, /overlaysHiddenNow\(\) \? null : root\.current/)
  })
  test('the player hides with the overlays (which pauses it) and shows again without focus', () => {
    const p = read('main/features/player.ts')
    assert.match(p, /onOverlaysHidden\(/)
    assert.match(p, /&& !mini/) // minimized to its handle counts as off screen: paused
  })
  test('the menu bar item offers it with its key', () => {
    const l = read('main/features/launch.ts')
    assert.match(l, /'Show miyagi overlays' : 'Hide miyagi overlays'/)
    assert.match(l, /accelerator: hideOverlaysAccelerator\(mac\)/)
  })
})
