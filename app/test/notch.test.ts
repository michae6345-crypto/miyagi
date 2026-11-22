// Notch geometry: pure notchFor, effective place, and the --screens JSON parser (common/notch.ts).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { effectivePlace, notchFor, parseScreens, stageNotch, type ScreenInfo } from '../src/common/notch'
import { sanitizePrefs, DEFAULT_PREFS } from '../src/common/prefs'

const screen = (id: number, w: number, h: number, safeTop: number, aux: number | null, builtin = true): ScreenInfo => ({
  id,
  frame: { x: 0, y: 0, w, h },
  visible: { x: 0, y: 0, w, h: h - 38 },
  safeTop,
  auxLeft: aux,
  auxRight: aux,
  scale: 2,
  builtin
})
const disp = (id: number, w: number, h: number, band: number) => ({ id, bounds: { x: 0, y: 0, width: w, height: h }, workArea: { x: 0, y: band, width: w, height: h - band } })

test('14-inch MacBook Pro notch', () => {
  const n = notchFor(disp(1, 1512, 982, 38), screen(1, 1512, 982, 32, 661))
  assert.deepEqual(n, { hasNotch: true, x: (1512 - 194) / 2, width: 194, height: 32 })
})

test('16-inch MacBook Pro notch', () => {
  const n = notchFor(disp(1, 1728, 1117, 38), screen(1, 1728, 1117, 32, 764))
  assert.deepEqual(n, { hasNotch: true, x: (1728 - 204) / 2, width: 204, height: 32 })
})

test('external display: placeholder 185 wide, height is the menu-bar band, no notch', () => {
  const n = notchFor(disp(2, 2560, 1440, 25), screen(2, 2560, 1440, 0, null, false))
  assert.deepEqual(n, { hasNotch: false, x: (2560 - 185) / 2, width: 185, height: 25 })
})

test('fake notch band is at least 24 (hidden menu bar)', () => {
  assert.equal(notchFor(disp(2, 1920, 1080, 0), undefined).height, 24)
})

test('no-notch display uses the helper safeTop for the band, not the work area', () => {
  const n = notchFor(disp(2, 1920, 1080, 0), screen(2, 1920, 1080, 24, null, false))
  assert.equal(n.hasNotch, false)
  assert.equal(n.height, 24)
})

test('helper failure (no info) gives the placeholder, not a notch', () => {
  const n = notchFor(disp(1, 1512, 982, 38))
  assert.equal(n.hasNotch, false)
  assert.equal(n.width, 185)
  assert.equal(n.height, 38)
})

test('safeTop without aux areas is not a notch', () => {
  assert.equal(notchFor(disp(1, 1512, 982, 38), screen(1, 1512, 982, 32, null)).hasNotch, false)
})

test('effective place', () => {
  assert.equal(effectivePlace('notch', true, true), 'notch') // notched display, whatever else runs
  assert.equal(effectivePlace(undefined, true, true), 'notch')
  assert.equal(effectivePlace('below', true, true), 'below') // the pref wins
  assert.equal(effectivePlace('notch', true, false), 'below') // no notch on this display
  assert.equal(effectivePlace('notch', false, true), 'below') // not a Mac
})

test('parseScreens reads the helper line', () => {
  const line =
    '{"screens":[{"auxLeft":661,"auxRight":661,"builtin":true,"frame":{"h":982,"w":1512,"x":0,"y":0},"id":1,"safeTop":32,"scale":2,"visible":{"h":944,"w":1512,"x":0,"y":0}},{"auxLeft":null,"auxRight":null,"builtin":false,"frame":{"h":1440,"w":2560,"x":1512,"y":0},"id":7,"safeTop":0,"scale":1,"visible":{"h":1415,"w":2560,"x":1512,"y":0}}]}\n'
  const s = parseScreens(line)
  assert.equal(s.length, 2)
  assert.equal(s[0].auxLeft, 661)
  assert.equal(s[1].auxLeft, null)
  assert.equal(s[1].builtin, false)
})

test('parseScreens never throws and drops bad entries', () => {
  assert.deepEqual(parseScreens(''), [])
  assert.deepEqual(parseScreens('not json'), [])
  assert.deepEqual(parseScreens('{"screens":5}'), [])
  assert.deepEqual(parseScreens('{"screens":[{"id":1},null,"x"]}'), [])
})

test('island pref is validated', () => {
  assert.deepEqual(DEFAULT_PREFS.island, { place: 'notch' })
  assert.deepEqual(sanitizePrefs({ island: { place: 'below' } }).island, { place: 'below' })
  assert.deepEqual(sanitizePrefs({ island: { place: 'sideways' } }).island, { place: 'notch' })
  assert.equal(sanitizePrefs({ island: 'x' }).island, undefined)
})

test('stage notch presets', () => {
  assert.deepEqual(stageNotch(null, 1600), { hasNotch: true, x: 700, width: 200, height: 32, place: 'notch', coexist: false, boringNotch: false })
  assert.equal(stageNotch('fake', 1600).hasNotch, false)
  assert.equal(stageNotch('below', 1600).place, 'below')
})
