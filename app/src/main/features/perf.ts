/**
 * Low-power tier (Nov 25, MacBook Neo / 8 GB Macs): reads the machine at start, every RECHECK_MS and when the power
 * source changes, and tells every window (renderer features/perf sets <html data-low-power>, perf.css drops the costly
 * effects). The rule itself is pure: renderer/src/features/perf/tier.ts.
 *
 * Low Power Mode: Electron has no API for it, so `pmset -g` is read (`lowpowermode 1`, or `powermode 1` on Macs that
 * name it so): one spawn a minute plus one per power-source change.
 *
 * The engine: the hardware tier (RAM + cores, without Low Power Mode, which the engine reads itself) goes into
 * process.env.MIYAGI_PERF_TIER at setup, which runs before main/index.ts starts the engine (setupLocalEngine copies
 * process.env into the engine's environment), so app and engine agree on the tier. A MIYAGI_PERF_TIER the user set
 * wins, here and there.
 */
import { execFile } from 'node:child_process'
import os from 'node:os'
import { app, powerMonitor } from 'electron'
import { defineMainFeature } from '../context'
import { NORMAL, perfTier, type PerfState } from '../../renderer/src/features/perf/tier'

const RECHECK_MS = 60_000
/** `pmset -g` says `lowpowermode 1` (or `powermode 1`) while Low Power Mode is on. */
export const LPM_LINE = /\b(lowpowermode|powermode)\s+1\b/

function lowPowerMode(): Promise<boolean> {
  if (process.platform !== 'darwin') return Promise.resolve(false)
  return new Promise((resolve) => {
    try {
      execFile('pmset', ['-g'], { timeout: 2000, encoding: 'utf8' }, (err, out) => resolve(!err && LPM_LINE.test(String(out ?? ''))))
    } catch {
      resolve(false)
    }
  })
}

export default defineMainFeature({
  id: 'perf',
  setup(ctx) {
    const userOverride = process.env.MIYAGI_PERF_TIER
    const hardware = (): PerfState => perfTier({ memBytes: os.totalmem(), cores: os.cpus().length, override: userOverride })
    if (!userOverride) process.env.MIYAGI_PERF_TIER = hardware().tier
    let state: PerfState = NORMAL
    const read = async (): Promise<void> => {
      const next = perfTier({ memBytes: os.totalmem(), cores: os.cpus().length, lowPowerMode: await lowPowerMode(), override: userOverride })
      if (next.tier === state.tier && next.reason === state.reason) return
      state = next
      console.log(`[perf] tier ${state.tier}${state.reason ? ` (${state.reason})` : ''}`)
      ctx.broadcast('perf:tier', state)
    }
    const reread = (): void => void read().catch(() => undefined)
    const ready = read().catch(() => undefined)
    ctx.handle('perf:tier', async () => {
      await ready
      return state
    })
    powerMonitor.on('on-battery', reread)
    powerMonitor.on('on-ac', reread)
    const timer = setInterval(reread, RECHECK_MS)
    timer.unref?.()
    app.on('before-quit', () => clearInterval(timer))
  }
})
