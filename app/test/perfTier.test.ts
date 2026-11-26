import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { applyTier, perfTier } from '../src/renderer/src/features/perf/tier'

const GB = 1024 ** 3

test('perf tier: 8 GB, <= 6 cores or Low Power Mode is low; battery alone is not', () => {
  assert.equal(perfTier({ memBytes: 8 * GB, cores: 8 }).tier, 'low') // 8 GB M1 / M2 Air
  assert.equal(perfTier({ memBytes: 16 * GB, cores: 6 }).tier, 'low') // A-series (MacBook Neo)
  assert.equal(perfTier({ memBytes: 16 * GB, cores: 10, lowPowerMode: true }).tier, 'low')
  assert.equal(perfTier({ memBytes: 16 * GB, cores: 10 }).tier, 'normal')
  assert.equal(perfTier({}).tier, 'normal') // nothing known: as before
  assert.match(perfTier({ memBytes: 8 * GB, cores: 6 }).reason, /8 GB RAM, 6 cores/)
})

test('perf tier: MIYAGI_PERF_TIER overrides', () => {
  assert.equal(perfTier({ memBytes: 64 * GB, cores: 14, override: 'low' }).tier, 'low')
  assert.equal(perfTier({ memBytes: 8 * GB, cores: 4, override: ' Normal ' }).tier, 'normal')
  assert.equal(perfTier({ memBytes: 8 * GB, override: 'auto' }).tier, 'low')
})

test('perf tier: applyTier sets and clears <html data-low-power>', () => {
  const root = { dataset: {} as Record<string, string | undefined> }
  applyTier(root, perfTier({ memBytes: 8 * GB }))
  assert.equal(root.dataset.lowPower, '8 GB RAM')
  applyTier(root, perfTier({ memBytes: 32 * GB, cores: 12 }))
  assert.equal('lowPower' in root.dataset, false)
})

test('perf.css: only under data-low-power, and never stops a progress indicator', () => {
  const css = readFileSync(new URL('../src/renderer/src/features/perf/perf.css', import.meta.url), 'utf8')
  const rules = css.replace(/\/\*[\s\S]*?\*\//g, '')
  for (const sel of rules.split('{').slice(0, -1).flatMap((r) => r.split('}').pop()!.split(','))) {
    if (sel.trim()) assert.match(sel.trim(), /^:root\[data-low-power\] /, sel)
  }
  assert.doesNotMatch(rules, /mg-spin|mg-thinking|mg-skeleton|bd-dots|bd-bars/)
})

test('perf: pmset Low Power Mode line, both spellings', async () => {
  // main/features/perf.ts imports electron; the regex is the contract, kept in step here.
  const LPM_LINE = /\b(lowpowermode|powermode)\s+1\b/
  const src = readFileSync(new URL('../src/main/features/perf.ts', import.meta.url), 'utf8')
  assert.ok(src.includes(String(LPM_LINE)), 'perf.ts LPM_LINE changed: update this test')
  assert.equal(LPM_LINE.test(' lowpowermode         1\n'), true)
  assert.equal(LPM_LINE.test(' powermode            1\n'), true)
  assert.equal(LPM_LINE.test(' lowpowermode         0\n powermode 0'), false)
  assert.equal(LPM_LINE.test(' highpowermode 1'), false)
})
