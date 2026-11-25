/**
 * Before the tests: learn the runner's primary display from one quick launch, then write a fake miyagi-listen
 * (gitignored build/helpers/) that reports that display WITH a notch (safe-area top 32, a 204 pt notch in the
 * middle). The real helper is a Swift binary that is not built in CI; the app runs `miyagi-listen --screens` at
 * launch, so every later launch sees a notched Mac. Every other mode (--windows, push to talk) exits quietly.
 */
import { chmodSync, existsSync, mkdirSync, renameSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { HELPER, launch } from './app'

export default async function globalSetup(): Promise<void> {
  if (!process.env.CI) throw new Error('Electron E2E opens real windows: CI only (set CI=1 on a machine where that is fine).')
  const { app } = await launch({ MIYAGI_SKIP_ONBOARDING: '1', MIYAGI_SKIP_LOGIN: '1', MIYAGI_QUIET_LAUNCH: '1' })
  const d = await app.evaluate(({ screen }) => {
    const p = screen.getPrimaryDisplay()
    return { id: p.id, bounds: p.bounds, workArea: p.workArea, scale: p.scaleFactor }
  })
  await app.close()
  const notchW = 200
  const aux = (d.bounds.width - notchW) / 2
  const screens = {
    screens: [
      {
        id: d.id,
        frame: { x: d.bounds.x, y: d.bounds.y, w: d.bounds.width, h: d.bounds.height },
        visible: { x: d.workArea.x, y: d.workArea.y, w: d.workArea.width, h: d.workArea.height },
        safeTop: 32,
        auxLeft: aux,
        auxRight: aux,
        scale: d.scale,
        builtin: true
      }
    ]
  }
  mkdirSync(dirname(HELPER), { recursive: true })
  if (existsSync(HELPER)) renameSync(HELPER, `${HELPER}.real`)
  writeFileSync(HELPER, `#!/bin/sh\n# Fake miyagi-listen for the Electron E2E (written by e2e/electron/global-setup.ts).\n[ "$1" = "--screens" ] && echo '${JSON.stringify(screens)}'\nexit 0\n`)
  chmodSync(HELPER, 0o755)
  console.log(`[e2e] fake notch helper for display ${d.id} (${d.bounds.width}x${d.bounds.height})`)
}
