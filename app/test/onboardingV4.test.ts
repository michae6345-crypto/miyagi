/**
 * The v4 setup page's copy and grouping (features/onboarding/setupRail.ts): the rail beside each guided step stays
 * calm and short (12 words a line at most, no em dash, the brand lowercase), and both macOS grants show side by side,
 * each with its live check, on either grant step.
 * Run from app/: node --import tsx --import ./test/setup.mjs --test test/onboardingV4.test.ts
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { stepGroup, stepRail } from '../src/renderer/src/features/onboarding/setupRail'
import type { Row } from '../src/renderer/src/features/onboarding/rows'

const words = (s: string): number => s.trim().split(/\s+/).length
const ids: Row['id'][] = ['screen', 'accessibility', 'companion', 'engine']
const variants: Array<Pick<Row, 'id' | 'action'>> = [
  ...ids.map((id) => ({ id })),
  { id: 'companion', action: { id: 'get-vscode', label: 'Get VS Code' } },
  { id: 'companion', action: { id: 'install-companion', label: 'Install in VS Code' } }
]

test('every rail line is calm and short', () => {
  for (const v of variants) {
    const rail = stepRail(v)
    if (!rail) continue
    assert.ok(rail.lines.length >= 2 && rail.lines.length <= 3, `${v.id}: two or three lines`)
    for (const text of [rail.title, ...rail.lines.flat()]) {
      assert.ok(words(text) <= 12, `${v.id}: "${text}" is over 12 words`)
      assert.ok(!/[—–]/.test(text), `${v.id}: "${text}" has a dash`)
      assert.ok(!/Miyagi/.test(text), `${v.id}: "${text}" capitalizes the brand`)
    }
  }
})

test('the engine step has no rail; the grant and VS Code steps do', () => {
  assert.equal(stepRail({ id: 'engine' }), undefined)
  assert.match(stepRail({ id: 'screen' })!.title, /Screen Recording/)
  assert.match(stepRail({ id: 'accessibility' })!.title, /Accessibility/)
  assert.equal(stepRail({ id: 'companion', action: { id: 'get-vscode', label: 'Get VS Code' } })!.lines[0][0], 'Get VS Code')
})

test('both grants show together on either grant step; other steps show their own row', () => {
  const steps = ids.map((id) => ({ id }))
  assert.deepEqual(stepGroup(steps[0], steps).map((r) => r.id), ['screen', 'accessibility'])
  assert.deepEqual(stepGroup(steps[1], steps).map((r) => r.id), ['screen', 'accessibility'])
  assert.deepEqual(stepGroup(steps[2], steps).map((r) => r.id), ['companion'])
  assert.deepEqual(stepGroup(steps[3], steps).map((r) => r.id), ['engine'])
  // Windows walks no grants: the VS Code step stays on its own.
  const pc = [{ id: 'companion' as const }, { id: 'engine' as const }]
  assert.deepEqual(stepGroup(pc[0], pc).map((r) => r.id), ['companion'])
})
