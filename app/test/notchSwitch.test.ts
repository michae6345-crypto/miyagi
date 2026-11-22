// Boring Notch quitting: the island must move into the notch at once (service state, recheck, pref change).
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { recheckThenResend, startNotch } from '../src/main/notch'

const display = { id: 1, bounds: { x: 0, y: 0, width: 1512, height: 982 }, workArea: { x: 0, y: 38, width: 1512, height: 944 } }

function harness(initial: boolean) {
  const state = { boring: initial, changes: 0, lookups: 0 }
  const svc = startNotch({
    helperBin: '/nonexistent',
    mac: true,
    onChange: () => state.changes++,
    isBoring: async () => (state.lookups++, state.boring),
    pollMs: 1_000_000
  })
  return { state, svc }
}
const tick = () => new Promise((r) => setTimeout(r, 5))

test('boring true -> false: recheck flips place to notch and fires onChange', async () => {
  const { state, svc } = harness(true)
  await tick()
  assert.equal(svc.layoutFor(display, 'notch').place, 'below')
  assert.equal(svc.layoutFor(display, 'notch').boringNotch, true)
  const before = state.changes
  state.boring = false // user quit Boring Notch; the poll has not run yet
  await svc.recheck()
  assert.equal(state.changes, before + 1)
  assert.equal(svc.layoutFor(display, 'notch').place, 'notch')
  assert.equal(svc.layoutFor(display, 'notch').boringNotch, false)
  svc.stop()
})

test('recheck with no change does not fire onChange', async () => {
  const { state, svc } = harness(false)
  await tick()
  const before = state.changes
  await svc.recheck()
  assert.equal(state.changes, before)
  svc.stop()
})

test('pref change: rechecks first, then resends the layout with the fresh answer', async () => {
  const { state, svc } = harness(true)
  await tick()
  state.boring = false
  const seen: string[] = []
  const lookups = state.lookups
  await recheckThenResend(svc, () => seen.push(svc.layoutFor(display, 'notch').place))
  assert.equal(state.lookups, lookups + 1)
  assert.deepEqual(seen, ['notch'])
  svc.stop()
})

test('pref change still resends when there is no service', async () => {
  let n = 0
  await recheckThenResend(undefined, () => n++)
  assert.equal(n, 1)
})

test('poll default is short', () => {
  assert.match(readFileSync(new URL('../src/main/notch.ts', import.meta.url), 'utf8'), /BORING_POLL_MS = 5_000/)
})
