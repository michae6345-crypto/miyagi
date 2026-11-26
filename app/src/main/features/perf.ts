/**
 * Low-power tier (Nov 25, MacBook Neo / 8 GB Macs): reads the machine once at start and again when the power source
 * changes, and tells every window (renderer features/perf sets <html data-low-power>, perf.css drops the costly
 * effects). The rule itself is pure: renderer/src/features/perf/tier.ts.
 *
 * Low Power Mode: Electron has no API for it, so `pmset -g` is read (one spawn at start and per power-source change,
 * never polled). MIYAGI_PERF_TIER=low|normal forces the tier.
 */
import { execFile } from 'node:child_process'
import os from 'node:os'
import { powerMonitor } from 'electron'
import { defineMainFeature } from '../context'
import { NORMAL, perfTier, type PerfState } from '../../renderer/src/features/perf/tier'

function lowPowerMode(): Promise<boolean> {
  if (process.platform !== 'darwin') return Promise.resolve(false)
  return new Promise((resolve) => {
    try {
      execFile('pmset', ['-g'], { timeout: 2000, encoding: 'utf8' }, (err, out) => resolve(!err && /\blowpowermode\s+1\b/.test(String(out ?? ''))))
    } catch {
      resolve(false)
    }
  })
}

export default defineMainFeature({
  id: 'perf',
  setup(ctx) {
    let state: PerfState = NORMAL
    const read = async (): Promise<void> => {
      const next = perfTier({ memBytes: os.totalmem(), cores: os.cpus().length, lowPowerMode: await lowPowerMode(), override: process.env.MIYAGI_PERF_TIER })
      if (next.tier === state.tier && next.reason === state.reason) return
      state = next
      console.log(`[perf] tier ${state.tier}${state.reason ? ` (${state.reason})` : ''}`)
      ctx.broadcast('perf:tier', state)
    }
    ctx.handle('perf:tier', async () => {
      await ready
      return state
    })
    const ready = read().catch(() => undefined)
    for (const ev of ['on-battery', 'on-ac'] as const) powerMonitor.on(ev as 'on-battery', () => void read().catch(() => undefined))
  }
})
