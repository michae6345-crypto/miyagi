/** features/ptt/inputCard.ts: the Input Monitoring card waits for the launch gate and comes back until it is dealt with. Run from app/. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { MAX_OFFERS, REOFFER_MS, shouldShowInputCard } from '../src/renderer/src/features/ptt/inputCard'

const ok = { shownCount: 0, sinceLastMs: 0, declined: false, inputDenied: true, enabled: true, gateOpen: true }

describe('input card', () => {
  test('shows when everything lines up', () => assert.equal(shouldShowInputCard(ok), true))
  test('never during first-run setup (gate closed)', () => assert.equal(shouldShowInputCard({ ...ok, gateOpen: false }), false))
  test('not right after it showed', () => assert.equal(shouldShowInputCard({ ...ok, shownCount: 1, sinceLastMs: 10_000 }), false))
  test('comes back after a few minutes if it was missed', () => assert.equal(shouldShowInputCard({ ...ok, shownCount: 1, sinceLastMs: REOFFER_MS }), true))
  test('stops after MAX_OFFERS', () => assert.equal(shouldShowInputCard({ ...ok, shownCount: MAX_OFFERS, sinceLastMs: REOFFER_MS * 2 }), false))
  test('"Not now" silences it for the run', () => assert.equal(shouldShowInputCard({ ...ok, declined: true }), false))
  test('not when push to talk is off', () => assert.equal(shouldShowInputCard({ ...ok, enabled: false }), false))
  test('not when the grant is there', () => assert.equal(shouldShowInputCard({ ...ok, inputDenied: false }), false))
})
