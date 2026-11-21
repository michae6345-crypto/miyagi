/**
 * Feature: errors. Browser-stage stand-ins for main/features/errors.ts (nothing here runs in Electron), and the
 * stage's `?err=` switch: `?scenario=errors&err=<state>` asks the inline mock for the `dev.err.<state>` trigger, whose
 * err-prefixed segment plays that state (mock/scenarios/errors.json):
 *
 *   reconnect | back | engine-offline | offline | online | busy | kernel | editor-closed | build-failed | limit | crash
 *
 * crash: the stage's errors:crash-pending returns a sample (already scrubbed) report. limit also needs &v2Cloud=1.
 * The `diagnostics:copy` stand-in is core's (bridge.ts).
 */
import type { Outgoing } from '../../../../common/wire'
import { bridge, engineMode, isElectron, registerWebHandler } from '../../bridge'

const SAMPLE_REPORT = [
  'miyagi crash report',
  'App: miyagi stage',
  'System: macOS (stage)',
  'Last started: 2026-11-20T10:42:00.000Z',
  'Lesson: Code your first neural network, step 3 of 6',
  'Error log:',
  '  10:51:02 renderer gone: crashed (exit 5)',
  'Not included: your code or files, screenshots, API keys.'
].join('\n')

function setupWeb(): void {
  const params = new URLSearchParams(location.search)
  const err = params.get('err') ?? ''

  registerWebHandler('errors:info', () => ({ version: 'stage', system: 'browser stage' }))
  registerWebHandler('errors:crash-pending', () => (err === 'crash' ? { report: SAMPLE_REPORT } : null))
  registerWebHandler('errors:crash-decide', (d) => {
    const save = !!(d && typeof d === 'object' && (d as { save?: unknown }).save === true)
    console.info(`[errors] stage: crash report ${save ? 'would be saved on this Mac' : 'dropped'}`)
    return { saved: save }
  })
  registerWebHandler('errors:context', () => true)

  if (!/^[a-z-]{1,24}$/.test(err) || err === 'crash') return
  const trigger = (state: string): void => {
    if (engineMode() !== 'inline') return
    // A dev-only trigger for the inline mock (like dev.reset): it never reaches a real engine.
    bridge.send({ type: `dev.err.${state}`, payload: {} } as unknown as Outgoing)
  }
  setTimeout(() => trigger(err), 300)
  // Engine offline: Restart in the stage brings the fake link back (bridge.ts fakes the restart itself).
  if (err === 'engine-offline')
    bridge.onFeature('engine-local', (p) => {
      if ((p as { state?: string } | undefined)?.state === 'running') trigger('recover')
    })
}

if (!isElectron) setupWeb()
