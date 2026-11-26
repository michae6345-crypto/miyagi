/**
 * The first-lesson walkthrough's launch rules (main/features/onboarding.ts; renderer features/tips TourLayer.tsx). Pure,
 * so test/onboardingTour.test.ts checks them without Electron.
 *
 *   due      the tour is owed to this Mac: set once on a first run (setup never finished nor put off, tour never seen)
 *            and kept in onboarding.json (tourDue) until the tour is seen or declined. An install that finished setup
 *            on an older build (done, no tourDue) is never owed one: an upgrade never pops a tour.
 *   auto     the home window's first-run flow handed over to home (or home opened with the flow already over): the
 *            tour starts by itself once, if it is due, not seen, the launch gate is open (sign-in, consent, setup done
 *            or put off) and it was not already started or asked for in this run. Never on a quiet launch (at login,
 *            MIYAGI_QUIET_LAUNCH=1) or with MIYAGI_SKIP_ONBOARDING=1.
 *   start    an explicit ask (You're ready's "Show me around", Settings, the menu bar): at once when the gate is open,
 *            else held until it opens (You're ready asks a moment before setup is marked done and the gate opens).
 */

export type TourFlag = { done: boolean; later?: boolean; tourSeen?: boolean; tourDue?: boolean }

/** At launch: is the tour owed to this Mac? A first run makes it due; an earlier due stays until it is seen. */
export function tourDueAtLaunch(f: TourFlag): boolean {
  if (f.tourSeen === true) return false
  if (f.tourDue === true) return true
  return !f.done && f.later !== true
}

export type AutoTour = {
  due: boolean
  seen: boolean
  gateOpen: boolean
  /** The tour was already started (by hand or by itself) or auto-asked in this run. */
  tried: boolean
  /** MIYAGI_SKIP_ONBOARDING=1 */
  skip: boolean
  /** Started at login or MIYAGI_QUIET_LAUNCH=1: nothing opens by itself. */
  quiet: boolean
}

/** The flow handed over to home: start the tour by itself? */
export function shouldAutoTour(s: AutoTour): boolean {
  return !s.skip && !s.quiet && s.due && !s.seen && s.gateOpen && !s.tried
}

export type StartAsk = { gateOpen: boolean }

/** An explicit start: 'now' with the gate open, else 'hold' until the gate opens (the overlay is hidden until then). */
export function startDecision(s: StartAsk): 'now' | 'hold' {
  return s.gateOpen ? 'now' : 'hold'
}

/** The gate just opened: a held explicit start runs now. */
export function onGateOpened(s: { held: boolean }): 'start' | 'none' {
  return s.held ? 'start' : 'none'
}

/** After the flow's hand-off (renderer shell/flow ARRIVE_MS 900 ms) and home's first paint: the auto tour waits this long. */
export const AUTO_TOUR_DELAY_MS = 1400
