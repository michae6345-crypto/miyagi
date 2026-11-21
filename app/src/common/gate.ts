/**
 * The launch gate (Michael, Nov 21: "It needs to allow me to log in first, like it's just starting from new"). Pure,
 * shared by main (main/gate.ts keeps the live state) and the renderer (the first-run flow starts on the part it still
 * needs).
 *
 * The overlay (pill, cards, shortcut bar), the launcher, the global keys and the full tray menu exist for the learner
 * only once every part is true:
 *   login  signed in with Google (a stored session counts), "Continue without an account" in this run, login switched
 *          off, or MIYAGI_SKIP_LOGIN=1
 *   setup  guided setup finished or put off ("Set up later")
 * MIYAGI_SKIP_ONBOARDING=1 opens it outright (dev, tests).
 */

export type GatePart = 'login' | 'setup'
export type GateParts = Record<GatePart, boolean>
/** What main broadcasts (feat:onboarding:gate) and onboarding:get carries as `gate`. */
export type GateView = GateParts & { open: boolean }

export const GATE_PARTS: readonly GatePart[] = ['login', 'setup']

export function gateOpen(parts: GateParts, forced = false): boolean {
  return forced || GATE_PARTS.every((p) => parts[p])
}

/** The first-run phase a closed gate starts on (after the intro): the earliest part still missing. Login comes first. */
export function firstNeeded(parts: GateParts): GatePart | undefined {
  return GATE_PARTS.find((p) => !parts[p])
}

/** A plain copy of a gate view that came over IPC; anything malformed reads as closed with every part missing. */
export function cleanGate(raw: unknown): GateView {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const parts: GateParts = { login: r.login === true, setup: r.setup === true }
  return { ...parts, open: r.open === true }
}
