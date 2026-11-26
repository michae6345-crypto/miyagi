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
 * returnFocus), which puts its windows back above the home window. Which app: pickTarget (the last front app when
 * it was one of the lesson's apps, never an app the learner chose over it; the renderer's lesson app only when nothing
 * else was in front), and only when it is running (open -b would relaunch a quit app). One activation per press, at
 * most every ONCE_MS: never a loop (front-app.ts's handBack loop went in PR #281 and must not come back here).
 *
 *   bridge.invoke('check:handback', {lesson?, last?: {bundle, lesson}})  -> the bundle activated, or null
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

/**
 * What the renderer knows (front:app): the last front app that was one of the lesson's apps, and the last non-miyagi
 * front app with whether it was one of the lesson's. A plain string (an older renderer) is the lesson app.
 */
export type HandBackHint = { lesson?: string; last?: { bundle?: string; lesson?: boolean } }

function hintOf(h: unknown): HandBackHint {
  if (typeof h === 'string') return { lesson: h }
  if (!h || typeof h !== 'object') return {}
  const o = h as { lesson?: unknown; last?: { bundle?: unknown; lesson?: unknown } }
  const last = o.last && typeof o.last === 'object' ? { bundle: validBundle(o.last.bundle), lesson: o.last.lesson === true } : undefined
  return { lesson: validBundle(o.lesson), last }
}

/**
 * Which app gets the keyboard back, or undefined: never pull the lesson's app over an app the learner chose.
 *   the last app in front (previousApp) was a lesson app (VS Code, Blender, a terminal...)  -> that app
 *   it was another app (Safari with the docs, Notes)                                          -> nothing
 *   nothing else was in front since miyagi started                                            -> the renderer's lesson app
 */
export function pickTarget(previous: string | undefined, hint: HandBackHint): string | undefined {
  const prev = validBundle(previous)
  if (!prev) return hint.lesson
  if (hint.last?.bundle === prev) return hint.last.lesson ? prev : undefined
  return hint.lesson === prev ? prev : undefined
}

export type HandBackDeps = {
  /** Activate the app with this bundle id (open -b). */
  activate: (bundle: string) => void
  /** Is an app with this bundle id running? (`open -b` would launch a quit one.) */
  running: (bundle: string) => Promise<boolean>
  /** The last non-miyagi front app's bundle (front-app.ts). */
  previous: () => string | undefined
  /** May miyagi move focus at all (the launch gate is open, macOS). */
  allowed: () => boolean
  now?: () => number
}

/** The press handler: which bundle it activated (or undefined). Never opens, shows or focuses a miyagi window. */
export function createHandBack(deps: HandBackDeps): (hint?: unknown) => Promise<string | undefined> {
  let at = -Infinity
  const now = deps.now ?? Date.now
  return async (hint) => {
    if (!deps.allowed()) return undefined
    const bundle = pickTarget(deps.previous(), hintOf(hint))
    if (!bundle) return undefined
    const t = now()
    if (t - at < ONCE_MS) return undefined
    at = t // before the await: a double press is one activation
    if (!(await deps.running(bundle).catch(() => false))) return undefined
    deps.activate(bundle)
    return bundle
  }
}

/** lsappinfo find bundleid=<b>: one line per running app with that bundle, nothing when none runs. */
function isRunning(bundle: string): Promise<boolean> {
  return new Promise((resolve) => {
    execFile('lsappinfo', ['find', `bundleid=${bundle}`], { timeout: 800, encoding: 'utf8' }, (err, out) =>
      resolve(!err && String(out ?? '').trim().length > 0)
    )
  })
}

export default defineMainFeature({
  id: 'check-focus',
  setup(ctx) {
    const handBack = createHandBack({
      activate: (bundle) =>
        execFile('open', ['-b', bundle], (err) => {
          if (err) console.warn('[check-focus] could not hand focus back to', bundle, err.message)
        }),
      running: isRunning,
      previous: previousApp,
      allowed: () => process.platform === 'darwin' && gateIsOpen() && process.env.MIYAGI_HAND_BACK !== '0'
    })
    ctx.handle('check:handback', async (hint) => (await handBack(hint)) ?? null)
  }
})
