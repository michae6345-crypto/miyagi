/**
 * Feature: perf. The low-power tier (tier.ts) on <html data-low-power> in every window, so perf.css can drop the costly
 * effects on a MacBook Neo / 8 GB Mac. Main (main/features/perf.ts) decides; the browser stage takes ?lowpower=1.
 * No UI of its own.
 */
import { bridge, isElectron } from '../../bridge'
import { defineFeature } from '../../core/registry'
import { applyTier, perfTier, type PerfState } from './tier'
import './perf.css'

if (typeof document !== 'undefined') {
  const root = document.documentElement
  const set = (s: PerfState | undefined): void => {
    if (s && (s.tier === 'low' || s.tier === 'normal')) applyTier(root, s)
  }
  if (isElectron) {
    bridge.invoke<PerfState>('perf:tier').then(set, () => undefined)
    bridge.onFeature('perf:tier', (s) => set(s as PerfState))
  } else if (new URLSearchParams(location.search).get('lowpower') === '1') {
    set(perfTier({ override: 'low' }))
  }
}

export default defineFeature({ id: 'perf' })
