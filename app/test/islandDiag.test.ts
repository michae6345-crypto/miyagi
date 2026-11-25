// island.log diagnostics: one line per snapshot, the --windows parser, rotation, the renderer report and the recorder.
import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import {
  appendRotating,
  createIslandDiag,
  formatRenderer,
  formatSnapshot,
  formatWindows,
  islandRect,
  overlayLevel,
  parseWindows,
  sanitizeRendererReport,
  type Snapshot
} from '../src/main/features/islandDiag'

const snap: Snapshot = {
  at: '2026-11-21T06:24:00.000Z',
  why: 'resend',
  overlay: { x: 0, y: 0, width: 1728, height: 1117 },
  visible: true,
  alwaysOnTop: true,
  allWorkspaces: true,
  level: 1000,
  display: { id: 1, bounds: { x: 0, y: 0, width: 1728, height: 1117 }, workArea: { x: 0, y: 38, width: 1728, height: 1079 }, scale: 2 },
  safeTop: 32,
  auxLeft: 769.5,
  auxRight: 769.5,
  place: 'notch',
  coexist: true,
  hasNotch: true
}

test('formatSnapshot: one line with bounds, level, visible, display and scale', () => {
  const line = formatSnapshot(snap)
  assert.equal(line.includes('\n'), false)
  for (const part of ['overlay=0,0,1728x1117', 'visible=true', 'level=1000', 'display=1', 'bounds=0,0,1728x1117', 'work=0,38,1728x1079', 'scale=2', 'safeTop=32', 'place=notch', 'coexist=true', 'onTop=true']) {
    assert.ok(line.includes(part), part)
  }
  assert.match(formatSnapshot({ ...snap, level: undefined, safeTop: null }), /level=\? .*safeTop=\?/)
})

const sample = JSON.stringify({
  windows: [
    { alpha: 1, bounds: { h: 210, w: 640, x: 544, y: 0 }, id: 7, layer: 27, onscreen: true, owner: 'boringNotch', pid: 900, z: 2 },
    { alpha: 1, bounds: { h: 1117, w: 1728, x: 0, y: 0 }, id: 41, layer: 1000, onscreen: true, owner: 'miyagi', pid: 812, z: 3 },
    { alpha: 1, bounds: { h: 400, w: 300, x: 10, y: 10 }, id: 42, layer: 0, onscreen: false, owner: 'miyagi', pid: 812, z: 9 },
    { id: 'bad' }
  ]
})

test('parseWindows: sample CGWindowList JSON, miyagi layer 1000 at 0,0 1728x1117; bad entries and bad text are skipped', () => {
  const list = parseWindows(`noise\n${sample}\n`)
  assert.equal(list.length, 3)
  const m = list.find((e) => e.id === 41)!
  assert.deepEqual([m.owner, m.layer, m.x, m.y, m.w, m.h, m.onscreen, m.z], ['miyagi', 1000, 0, 0, 1728, 1117, true, 3])
  assert.equal(overlayLevel(list, 812), 1000)
  assert.equal(overlayLevel(list, 1), undefined)
  assert.deepEqual(parseWindows(''), [])
  assert.deepEqual(parseWindows('{"windows":5}'), [])
  assert.deepEqual(parseWindows('not json {'), [])
  const line = formatWindows('T', 'periodic', list)
  assert.equal(line.includes('\n'), false)
  assert.match(line, /miyagi\(812\)#41 layer=1000 bounds=0,0,1728x1117 onscreen=true/)
})

test('islandRect follows overlay-raise: notch top vs pill top, hidden island is null', () => {
  const b = { x: 0, y: 0, width: 1728, height: 1117 }
  assert.deepEqual(islandRect({ w: 189, h: 32, place: 'notch', top: 0 }, b, 38), { x: 769.5, y: 0, w: 189, h: 32 })
  assert.deepEqual(islandRect({ w: 300, h: 34 }, b, 38), { x: 714, y: 38, w: 300, h: 34 })
  assert.equal(islandRect({ w: 1, h: 1, shown: false }, b, 0), null)
})

test('appendRotating rotates at the cap and keeps the old file as .1', () => {
  const dir = mkdtempSync(join(tmpdir(), 'island-'))
  const f = join(dir, 'sub', 'island.log')
  appendRotating(f, 'a'.repeat(100), 250)
  appendRotating(f, 'b'.repeat(100), 250)
  appendRotating(f, 'c'.repeat(100), 250) // 303 bytes now, over the cap
  assert.equal(existsSync(`${f}.1`), false)
  appendRotating(f, 'd\nd', 250) // rotates first; newline inside a line is flattened
  assert.ok(existsSync(`${f}.1`))
  assert.equal(readFileSync(f, 'utf8'), 'd d\n')
  assert.ok(statSync(`${f}.1`).size > 250)
  for (let i = 0; i < 20; i++) appendRotating(f, 'x'.repeat(100), 250)
  assert.ok(statSync(f).size <= 250 + 101)
})

test('renderer report: untrusted payloads are sanitized, then formatted on one line', () => {
  assert.equal(sanitizeRendererReport(null), null)
  assert.equal(sanitizeRendererReport('x'), null)
  const r = sanitizeRendererReport({ why: 'hover\nx', island: { x: 769.5, y: 0, w: 189, h: 32 }, clipPath: 'path("M0 0")', dpr: 2, visibility: 'visible', hover: { count: 3, lastAt: 1763706000000 }, peek: { opens: 2, closes: 1, lastAt: 0 }, extra: 'ignored' })!
  const line = formatRenderer('T', r)
  assert.equal(line.includes('\n'), false)
  assert.match(line, /renderer:hover x island=769.5,0,189x32 clip="path\("M0 0"\)" dpr=2 visibility=visible hover=3@2025|2026/)
  assert.match(line, /peek=2\/1@-/)
  assert.match(formatRenderer('T', sanitizeRendererReport({})!), /island=none clip="none"/)
})

test('createIslandDiag: snapshots, dedupe, windows dump, grab / away / wake, other-app, renderer', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'island-'))
  const file = join(dir, 'island.log')
  const calls: { ignore: boolean }[] = []
  const overlay = {
    isDestroyed: () => false,
    getBounds: () => snap.overlay,
    isVisible: () => true,
    isAlwaysOnTop: () => true,
    isVisibleOnAllWorkspaces: () => true,
    setIgnoreMouseEvents(ignore: boolean) {
      calls.push({ ignore })
    }
  }
  let boring = false
  const diag = createIslandDiag({
    logFile: file,
    overlay: () => overlay,
    display: () => ({ id: 1, bounds: snap.display.bounds, workArea: snap.display.workArea, scaleFactor: 2 }),
    notch: () => ({ place: 'notch', hasNotch: true, coexist: boring }),
    islandSize: () => ({ w: 189, h: 32, place: 'notch', top: 0 }),
    pillTop: () => 38,
    cursor: () => ({ x: 800, y: 5 }),
    helperBin: '/helper',
    mac: true,
    pid: 812,
    now: () => new Date('2026-11-21T06:24:00.000Z'),
    run: async (_bin, args) =>
      args[0] === '--windows' ? sample : JSON.stringify({ screens: [{ id: 1, frame: { x: 0, y: 0, w: 1728, h: 1117 }, visible: { x: 0, y: 0, w: 1728, h: 1079 }, safeTop: 32, auxLeft: 769.5, auxRight: 769.5, scale: 2, builtin: true }] }),
    pgrep: async (name) => boring && name === 'boringNotch'
  })
  diag.start()
  await new Promise((r) => setTimeout(r, 20))
  diag.snapshot('resend')
  diag.snapshot('resend') // identical: skipped
  diag.snapshot('ready') // never skipped
  overlay.setIgnoreMouseEvents(false)
  overlay.setIgnoreMouseEvents(false)
  overlay.setIgnoreMouseEvents(true)
  diag.onFeature('overlay:away', true)
  diag.onFeature('overlay:away', true)
  diag.onFeature('overlay:wake')
  diag.onRenderer({ why: 'hover', island: { x: 1, y: 2, w: 3, h: 4 } })
  boring = true
  await diag.dumpWindows('resume')
  diag.stop()
  const lines = readFileSync(file, 'utf8').trimEnd().split('\n')
  assert.ok(lines.every((l) => l.startsWith('2026-11-21T06:24:00.000Z ')))
  assert.equal(lines.filter((l) => / resend /.test(l)).length, 1)
  assert.equal(lines.filter((l) => / ready /.test(l)).length, 1)
  assert.ok(lines.some((l) => / ready /.test(l) && l.includes('level=1000') && l.includes('safeTop=32') && l.includes('auxL=769.5')))
  assert.equal(lines.filter((l) => l.includes('grabbed=')).length, 2) // true, then false; the repeated false is no transition
  assert.ok(lines.some((l) => l.includes('grabbed=true') && l.includes('cursor=800,5') && l.includes('island=769.5,0,189x32')))
  assert.equal(lines.filter((l) => l.includes(' away=true')).length, 1)
  assert.equal(lines.filter((l) => l.includes(' wake ')).length, 1)
  assert.ok(lines.some((l) => l.includes('windows:start') && l.includes('layer=1000')))
  assert.ok(lines.some((l) => l.includes('windows:resume')))
  assert.ok(lines.some((l) => l.includes('renderer:hover')))
  assert.equal(calls.length, 3) // the wrapped switch still reaches the real window
})
