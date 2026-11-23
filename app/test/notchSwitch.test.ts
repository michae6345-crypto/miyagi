// The notch service: last-good cache per display, retry, persistence, no fake first layout, coexist flag (log-only).
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import type { ScreenInfo } from '../src/common/notch'
import { recheckThenResend, startNotch } from '../src/main/notch'

const display = { id: 1, bounds: { x: 0, y: 0, width: 1512, height: 982 }, workArea: { x: 0, y: 38, width: 1512, height: 944 } }
const ext = { id: 2, bounds: { x: 1512, y: 0, width: 2560, height: 1440 }, workArea: { x: 1512, y: 25, width: 2560, height: 1415 } }
const scr = (id: number, w: number, safeTop: number, aux: number | null): ScreenInfo => ({
  id,
  frame: { x: 0, y: 0, w, h: 982 },
  visible: { x: 0, y: 0, w, h: 944 },
  safeTop,
  auxLeft: aux,
  auxRight: aux,
  scale: 2,
  builtin: safeTop > 0
})
const builtin = scr(1, 1512, 32, 661)
const external = scr(2, 2560, 0, null)

const tick = (ms = 20) => new Promise((r) => setTimeout(r, ms))

function harness(reads: (ScreenInfo[] | null)[], other = false, extra: Record<string, unknown> = {}) {
  const state = { changes: 0, reads: 0, other }
  const svc = startNotch({
    helperBin: '/nonexistent',
    mac: true,
    onChange: () => state.changes++,
    read: async () => reads[Math.min(state.reads++, reads.length - 1)],
    isOther: async () => state.other,
    pollMs: 1_000_000,
    debounceMs: 5,
    retryMs: 2,
    ...extra
  })
  return { state, svc }
}

test('first layout carries no fake geometry: below until the first read lands, then notch', async () => {
  const { state, svc } = harness([[builtin, external]])
  assert.equal(svc.ready(), false)
  assert.equal(svc.layoutFor(display, 'notch').place, 'below')
  assert.equal(svc.layoutFor(display, 'notch').hasNotch, false)
  await tick()
  assert.equal(svc.ready(), true)
  assert.equal(state.changes, 1)
  const l = svc.layoutFor(display, 'notch')
  assert.equal(l.place, 'notch')
  assert.equal(l.hasNotch, true)
  assert.equal(l.width, 1512 - 661 * 2 + 4)
  svc.stop()
})

test('keyed per display: external display stays below, built-in gets the notch', async () => {
  const { svc } = harness([[builtin, external]])
  await tick()
  assert.equal(svc.layoutFor(display, 'notch').place, 'notch')
  assert.equal(svc.layoutFor(ext, 'notch').place, 'below')
  assert.equal(svc.layoutFor(ext, 'notch').hasNotch, false)
  svc.stop()
})

test('a helper failure keeps the previous geometry (and does not re-emit)', async () => {
  const { state, svc } = harness([[builtin], null, null])
  await tick()
  const before = state.changes
  svc.refresh()
  await tick(40)
  assert.equal(state.changes, before)
  assert.equal(svc.layoutFor(display, 'notch').place, 'notch')
  assert.equal(svc.layoutFor(display, 'notch').hasNotch, true)
  svc.stop()
})

test('a failed read is retried once', async () => {
  const { state, svc } = harness([null, [builtin]])
  await tick(40)
  assert.equal(state.reads, 2)
  assert.equal(svc.layoutFor(display, 'notch').place, 'notch')
  svc.stop()
})

test('a timeout (never-resolving read is modelled as null) keeps geometry across displays', async () => {
  const { svc } = harness([[builtin], null, null])
  await tick()
  svc.refresh()
  await tick(40)
  assert.equal(svc.layoutFor(display, 'notch').hasNotch, true)
  svc.stop()
})

test('last good geometry is persisted and used before the helper answers', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'notch-'))
  const file = join(dir, 'notch-cache.json')
  const a = harness([[builtin]], false, { cacheFile: file })
  await tick()
  a.svc.stop()
  assert.match(readFileSync(file, 'utf8'), /"safeTop":32/)
  const b = harness([null, null], false, { cacheFile: file })
  assert.equal(b.svc.ready(), true)
  assert.equal(b.svc.layoutFor(display, 'notch').place, 'notch')
  await tick(40) // the helper keeps failing: the persisted geometry stays
  assert.equal(b.svc.layoutFor(display, 'notch').hasNotch, true)
  b.svc.stop()
})

test('a corrupt cache file is no cache', () => {
  const dir = mkdtempSync(join(tmpdir(), 'notch-'))
  const file = join(dir, 'c.json')
  writeFileSync(file, 'garbage')
  const { svc } = harness([null], false, { cacheFile: file })
  assert.equal(svc.ready(), false)
  svc.stop()
})

test('refresh is debounced', async () => {
  const { state, svc } = harness([[builtin]], false, { debounceMs: 30 })
  await tick()
  const reads = state.reads
  svc.refresh()
  svc.refresh()
  svc.refresh()
  await tick(80)
  assert.equal(state.reads, reads + 1)
  svc.stop()
})

test('coexist is a private flag: it never changes the place', async () => {
  const { state, svc } = harness([[builtin]], true)
  await tick()
  const l = svc.layoutFor(display, 'notch')
  assert.equal(l.coexist, true)
  assert.equal(l.place, 'notch')
  const before = state.changes
  state.other = false
  await svc.recheck()
  assert.equal(state.changes, before + 1)
  assert.equal(svc.layoutFor(display, 'notch').coexist, false)
  assert.equal(svc.layoutFor(display, 'notch').place, 'notch')
  svc.stop()
})

test('non-mac: always below, no work', async () => {
  const state = { reads: 0 }
  const svc = startNotch({ helperBin: '/x', mac: false, onChange: () => undefined, read: async () => (state.reads++, [builtin]) })
  await tick()
  assert.equal(state.reads, 0)
  assert.equal(svc.layoutFor(display, 'notch').place, 'below')
  svc.stop()
})

test('pref change: recheck, then resend the layout', async () => {
  const { svc } = harness([[builtin]])
  await tick()
  const seen: string[] = []
  await recheckThenResend(svc, () => seen.push(svc.layoutFor(display, 'notch').place))
  assert.deepEqual(seen, ['notch'])
  svc.stop()
})

test('pref change still resends when there is no service', async () => {
  let n = 0
  await recheckThenResend(undefined, () => n++)
  assert.equal(n, 1)
})

test('a display that is gone is forgotten, and an entry only fits a display of its own size', async () => {
  const { svc } = harness([[builtin, external], [builtin]])
  await tick()
  assert.equal(svc.layoutFor(ext, 'notch').hasNotch, false)
  svc.refresh()
  await tick(40)
  // id 2 was dropped by the second read; a recycled id on a screen of another size never borrows the old notch
  assert.equal(svc.layoutFor({ ...display, bounds: { ...display.bounds, width: 1920 } }, 'notch').hasNotch, false)
  assert.equal(svc.layoutFor(display, 'notch').hasNotch, true)
})

test('a read asked for during a read in flight runs once more after it (a display plugged in mid-read)', async () => {
  // the first read is slow and sees only the built-in; the display is plugged in while it runs
  let n = 0
  const slow = async (): Promise<ScreenInfo[]> => {
    n++
    await tick(40)
    return n === 1 ? [builtin] : [builtin, external]
  }
  const { svc } = harness([], false, { read: slow })
  await tick(5)
  svc.refresh() // debounced re-read while the first is still in flight
  await tick(150)
  assert.equal(n, 2, 'exactly one more read')
  assert.equal(svc.layoutFor(ext, 'notch').place, 'below')
  assert.equal(svc.layoutFor(ext, 'notch').hasNotch, false)
  svc.stop()
})
