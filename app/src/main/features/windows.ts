/**
 * Windows parity for the installed app (no renderer side).
 *
 * macOS gives an app one instance for free: opening Miyagi again just focuses the running one.
 * Windows starts a second process, which would stack a second overlay and lose every global shortcut
 * to the first. So the installed Windows build keeps one instance and a second launch exits.
 *
 * No-op on the Mac and in `npm run dev` (dev restarts must never be blocked by a stale process).
 * Checked on Windows 11 (packaged build): a second launch exits, the first keeps running.
 */
import { defineMainFeature } from '../context'

export default defineMainFeature({
  id: 'windows',
  setup(ctx) {
    if (ctx.platform.os !== 'win' || !ctx.app.isPackaged) return
    // Runs before the core windows' ready-to-show, so a second instance exits before anything appears.
    if (!ctx.app.requestSingleInstanceLock()) ctx.app.exit(0)
  }
})
