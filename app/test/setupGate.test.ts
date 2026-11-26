/**
 * The setup gate (user test Nov 25, MacBook Neo): while the lesson's packages install, the lesson waits and the overlay
 * shows the progress (features/setup-gate/machine.ts). The engine side: server/orchestrator/setup_gate.py.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { SetupGate, SetupGateItem } from '../../shared/contracts/events'
import { actionFor, actions, CONTINUE_WITHOUT_S, clock, elapsedS, headline, holds, initial, panelOpen, reduce, rowFraction, rowText, subline, type GateState } from '../src/renderer/src/features/setup-gate/machine'

const row = (tool: string, extra: Partial<SetupGateItem> = {}): SetupGateItem => ({ tool, label: tool, status: 'queued', optional: false, ...extra })
const gate = (items: SetupGateItem[], extra: Partial<SetupGate> = {}): SetupGate => ({
  phase: 'running', holds: true, items, done: items.filter((x) => x.status === 'done' || x.status === 'skipped').length, total: items.length, ...extra
})
const fed = (g: SetupGate, s: GateState = initial, now = 1_000_000): GateState => reduce(s, { type: 'gate', payload: g, now })

test('running: the lesson waits, the panel says what installs and which of how many', () => {
  const g = gate([row('numpy', { status: 'done' }), row('tensorflow', { status: 'installing', phase: 'downloading', pct: 41, bytes: 92e6, totalBytes: 224e6 }), row('matplotlib'), row('jupyter')])
  const s = fed(g)
  assert.equal(holds(s), true)
  assert.equal(panelOpen(s), true)
  assert.equal(headline(g), 'Installing tensorflow… 2/4')
  assert.match(subline(g), /Big downloads/)
  assert.equal(rowText(g.items[1]), 'Downloading 41% · 92 MB of 224 MB')
  assert.equal(rowFraction(g.items[1]), 0.41)
  assert.equal(rowText(g.items[2]), 'Waiting')
  assert.equal(rowText(g.items[0]), 'Installed')
  assert.deepEqual(actions(g), []) // no Skip for required rows, nothing to retry
})

test('phases without a size show words and no fake bar', () => {
  for (const [phase, words] of [['resolving', 'Starting'], ['installing', 'Unpacking'], ['verifying', 'Checking it works'], ['preparing', 'Preparing the Python environment']] as const) {
    const x = row('tensorflow', { status: 'installing', phase })
    assert.equal(rowFraction(x), undefined)
    if (phase !== 'resolving') assert.equal(rowText(x), words)
  }
  assert.match(rowText(row('tensorflow', { status: 'installing', phase: 'retrying', attempt: 2 })), /trying again \(try 2\)/)
})

test('done: released, the panel goes', () => {
  const s = fed(gate([row('numpy', { status: 'done' })], { phase: 'done', holds: false }))
  assert.equal(holds(s), false)
  assert.equal(panelOpen(s), false)
})

test('failed: Retry, Show details, Continue anyway; the reason in plain words', () => {
  const tf = row('tensorflow', { status: 'failed', error: 'The download of tensorflow kept stalling (tried 3 times).', errorCode: 'timeout', log: 'Read timed out' })
  const g = gate([row('numpy', { status: 'done' }), tf], { phase: 'failed', holds: true })
  assert.equal(headline(g), "Setup didn't finish")
  assert.equal(rowText(tf), "Didn't install")
  assert.deepEqual(actions(g).map((a) => a.kind), ['retry', 'details', 'continue'])
  assert.deepEqual(actionFor({ kind: 'retry' }), { kind: 'setup_retry' })
  assert.deepEqual(actionFor({ kind: 'continue' }), { kind: 'setup_continue' })
  assert.equal(actionFor({ kind: 'details' }), undefined) // local only
  let s = fed(g)
  s = reduce(s, { type: 'toggleLog' })
  assert.equal(s.logFor, 'tensorflow')
  s = reduce(s, { type: 'toggleLog' })
  assert.equal(s.logFor, undefined)
  // no log: no Show details
  assert.deepEqual(actions(gate([{ ...tf, log: undefined }], { phase: 'failed' })).map((a) => a.kind), ['retry', 'continue'])
})

test('a retried row closes its log; a press is cleared by the next gate', () => {
  const failed = gate([row('tensorflow', { status: 'failed', log: 'x' })], { phase: 'failed' })
  let s = reduce(fed(failed), { type: 'toggleLog', tool: 'tensorflow' })
  s = reduce(s, { type: 'press', what: 'retry' })
  assert.equal(s.pressed, 'retry')
  s = fed(gate([row('tensorflow', { status: 'queued' })]), s)
  assert.equal(s.logFor, undefined)
  assert.equal(s.pressed, undefined)
})

test('optional rows: Skip, and skipped rows say why', () => {
  const g = gate([row('tensorflow', { status: 'installing' }), row('tensorflow-metal', { optional: true })])
  assert.deepEqual(actions(g), [{ kind: 'skip', tool: 'tensorflow-metal' }])
  assert.deepEqual(actionFor({ kind: 'skip', tool: 'tensorflow-metal' }), { kind: 'setup_skip', text: 'tensorflow-metal' })
  assert.equal(rowText(row('tensorflow-metal', { status: 'skipped', errorCode: 'skipped_incompatible' })), 'Skipped: GPU add-on incompatible, runs on CPU')
  assert.equal(rowText(row('jupyter', { status: 'skipped' })), 'Skipped')
})

test('elapsed time: from the engine startedAt, else elapsedS plus the time since it arrived', () => {
  const s = fed(gate([row('a', { status: 'installing' })], { startedAt: 1_000_000 - 75_000 }))
  assert.equal(elapsedS(s, 1_000_000), 75)
  const t = fed(gate([row('a', { status: 'installing' })], { elapsedS: 10 }), initial, 5_000)
  assert.equal(elapsedS(t, 8_000), 13)
  assert.equal(clock(75), '1:15')
  assert.equal(clock(3725), '1:02:05')
})

test('a required install running a minute gets "Continue without it" (the install keeps going)', () => {
  const g = gate([row('tensorflow', { status: 'installing', elapsedS: 50 })])
  assert.deepEqual(actions(g, { receivedAt: 0, now: 5_000 }), []) // 55 s
  assert.deepEqual(actions(g, { receivedAt: 0, now: (CONTINUE_WITHOUT_S - 50) * 1000 }), [{ kind: 'continue_without' }])
  assert.deepEqual(actionFor({ kind: 'continue_without' }), { kind: 'setup_continue' })
  // an optional row alone never offers it (it doesn't hold the lesson)
  assert.deepEqual(actions(gate([row('jupyter', { status: 'installing', optional: true, elapsedS: 600 })], { holds: false }), { receivedAt: 0, now: 0 }), [{ kind: 'skip', tool: 'jupyter' }])
})

test('reset: a new lesson starts with no gate', () => {
  const s = reduce(fed(gate([row('a')])), { type: 'reset' })
  assert.equal(holds(s), false)
  assert.equal(s.gate, undefined)
})
