/**
 * Core: the launch gate's live state in main (rules: common/gate.ts). Features set their part, core and features listen:
 *
 *   setGatePart('login', ok)   features/auth.ts (signed in, guest for this run, login off, MIYAGI_SKIP_LOGIN=1; sign-out)
 *   setGatePart('consent', ok) features/onboarding.ts (the learner agreed to this build's policy version, prefs.consent)
 *   setGatePart('setup', ok)   features/onboarding.ts (setup done or put off)
 *   gateIsOpen() / gateView()  anyone
 *   onGate((open, view) => …)  called on every change of a part (open may be unchanged)
 *   gateCore({...})            main/index.ts: the overlay window and the launcher key follow the gate
 *
 * While closed: the overlay and launcher windows stay hidden (they are created hidden, so every ctx.overlay user keeps a
 * real window), no global action keys and no launcher key (index.ts), the tray shows only Open miyagi and Quit miyagi
 * (features/launch.ts), and nothing hands focus around (features/front-app.ts). Every part starts false: a feature that
 * never reports keeps the gate shut. Nothing here is saved: each launch starts closed and the features report again.
 */
import { gateOpen, type GatePart, type GateParts, type GateView } from '../common/gate'

const parts: GateParts = { login: false, consent: false, setup: false }
const listeners = new Set<(open: boolean, view: GateView) => void>()

/** MIYAGI_SKIP_ONBOARDING=1: dev and tests, everything opens at once (read live, so tests can set it). */
const forced = (): boolean => process.env.MIYAGI_SKIP_ONBOARDING === '1'

export function gateIsOpen(): boolean {
  return gateOpen(parts, forced())
}

export function gateView(): GateView {
  return { ...parts, open: gateIsOpen() }
}

export function setGatePart(part: GatePart, ok: boolean): void {
  if (parts[part] === ok) return
  parts[part] = ok
  const view = gateView()
  for (const fn of [...listeners]) {
    try {
      fn(view.open, view)
    } catch (err) {
      console.error('[gate] listener failed', err)
    }
  }
}

export function onGate(fn: (open: boolean, view: GateView) => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** What index.ts hands over: its overlay window, its launcher key, and what to drop when the gate closes again. */
export type CoreGate = {
  overlay: { showInactive(): void; hide(): void; isDestroyed(): boolean }
  /** Register (true) or unregister (false) the launcher's global key. */
  launcherKey: (on: boolean) => void
  /** The gate closed again (a sign-out): close the launcher, hand the lesson keys back. */
  closed: () => void
}

/**
 * The overlay shows and the launcher key registers only while the gate is open; both go away when it closes. Both start
 * hidden and unregistered (the windows are created hidden). Returns the unsubscribe.
 */
export function gateCore(core: CoreGate): () => void {
  let live = false
  const apply = (open: boolean): void => {
    if (open === live) return
    live = open
    if (open) {
      if (!core.overlay.isDestroyed()) core.overlay.showInactive()
      core.launcherKey(true)
      return
    }
    if (!core.overlay.isDestroyed()) core.overlay.hide()
    core.launcherKey(false)
    core.closed()
  }
  if (gateIsOpen()) apply(true)
  return onGate((open) => apply(open))
}

/** Tests only: back to all-closed with no listeners. */
export function resetGateForTests(): void {
  parts.login = parts.consent = parts.setup = false
  listeners.clear()
}
