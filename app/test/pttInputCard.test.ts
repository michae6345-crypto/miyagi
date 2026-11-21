/** features/ptt/inputCard.ts: the once-per-run Input Monitoring card waits for the launch gate. Run from app/. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { shouldShowInputCard } from '../src/renderer/src/features/ptt/inputCard'

const ok = { shown: false, inputDenied: true, enabled: true, gateOpen: true }

describe('input card', () => {
  test('shows when everything lines up', () => assert.equal(shouldShowInputCard(ok), true))
  test('never during first-run setup (gate closed)', () => assert.equal(shouldShowInputCard({ ...ok, gateOpen: false }), false))
  test('once per run', () => assert.equal(shouldShowInputCard({ ...ok, shown: true }), false))
  test('not when push to talk is off', () => assert.equal(shouldShowInputCard({ ...ok, enabled: false }), false))
  test('not when the grant is there', () => assert.equal(shouldShowInputCard({ ...ok, inputDenied: false }), false))
})
