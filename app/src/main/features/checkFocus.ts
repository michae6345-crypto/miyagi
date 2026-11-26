/**
 * Check my work / Check again hands the keyboard back to the learner's app, once (Nov 25, Michael).
 *
 * The bug: a click on the overlay's Check button makes miyagi the active app (the overlay is a panel that never takes
 * the keyboard). With the home window open (it is a normal window, which also puts miyagi in the Dock), AppKit gives
 * that activation to the app's main window, and the dashboard comes forward over VS Code / Blender / the terminal, on
 * every press. Nothing in the check flow opens or focuses a miyagi window (this feature never does either), and the
 * check's answer stays in the overlay.
 *
 * The fix: right after the press, activate the lesson's app once (`open -b <bundle>`, the same Launch Services call as
 * returnFocus), which puts its windows back above the home window. The bundle is the renderer's hint (the last front
 * app that was one of the lesson's apps: VS Code, Blender, a CAD app, a terminal; core/checkFocus.ts), else the last
 * non-miyagi front app (front-app.ts previousApp). One activation per press, at most every ONCE_MS: never a loop
 * (front-app.ts's handBack loop went in PR #281 and must not come back here).
 *
 *   bridge.invoke('check:handback', bundleHint?)  -> the bundle activated, or null
 */
import { execFile } from 'node:child_process'
import { defineMainFeature } from '../context'
import { gateIsOpen } from '../gate'
import { previousApp } from './front-app'

/** Two presses inside this window (a double click, Enter right after a click) activate once. */
export const ONCE_MS = 1500

/** miyagi's own bundles (and a dev Electron): never "the learner's app". */
const OWN = ['dev.sandhacks.miyagi', 'com.github.electron']

/** A reverse-DNS bundle id ("com.microsoft.VSCode", "org.blenderfoundation.blender"), nothing else reaches `open`. */
const BUNDLE = /^[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9-]+)+$/

export function validBundle(b: unknown): string | undefined {
  if (typeof b !== 'string' || b.length > 200 || !BUNDLE.test(b)) return undefined
  const low = b.toLowerCase()
  return OWN.some((o) => low === o || low.startsWith(`${o}.`)) ? undefined : b
}

export type HandBackDeps = {
  /** Activate the app with this bundle id (open -b). */
  activate: (bundle: string) => void
  /** The last non-miyagi front app's bundle (front-app.ts). */
  previous: () => string | undefined
  /** May miyagi move focus at all (the launch gate is open, macOS). */
  allowed: () => boolean
  now?: () => number
}

/** The press handler, pure: which bundle it activated (or undefined). Never opens, shows or focuses a miyagi window. */
export function createHandBack(deps: HandBackDeps): (hint?: unknown) => string | undefined {
  let at = -Infinity
  const now = deps.now ?? Date.now
  return (hint) => {
    if (!deps.allowed()) return undefined
    const bundle = validBundle(hint) ?? validBundle(deps.previous())
    if (!bundle) return undefined
    const t = now()
    if (t - at < ONCE_MS) return undefined
    at = t
    deps.activate(bundle)
    return bundle
  }
}

export default defineMainFeature({
  id: 'check-focus',
  setup(ctx) {
    const handBack = createHandBack({
      activate: (bundle) =>
        execFile('open', ['-b', bundle], (err) => {
          if (err) console.warn('[check-focus] could not hand focus back to', bundle, err.message)
        }),
      previous: previousApp,
      allowed: () => process.platform === 'darwin' && gateIsOpen() && process.env.MIYAGI_HAND_BACK !== '0'
    })
    ctx.handle('check:handback', (hint) => handBack(hint) ?? null)
  }
})
