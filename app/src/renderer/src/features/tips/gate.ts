/**
 * Feature: tips. When the layer may teach at all (core/gate.ts, lane overlay-gate). Pure, so test/overlayGate.test.ts
 * checks it without a window.
 */

/** The layer's loop (and with it the STARTUP_MS clock) runs only with tips on, something left to teach and the gate open. */
export function tipsRunning(s: { enabled: boolean; off: boolean; allSeen: boolean; gateOpen: boolean }): boolean {
  return s.enabled && !s.off && !s.allSeen && s.gateOpen
}

/** The floor is free for a tip: the sign-in gate is open and first-run setup is finished. Starts the STARTUP_MS wait. */
export function floorFree(onboarded: boolean, gateOpen: boolean): boolean {
  return gateOpen && onboarded
}

/**
 * onboarding:get's answer says first-run setup no longer holds the floor: done, or put off ("Set up later": the launch
 * gate's setup part is open then, while `done` stays false).
 */
export function setupSettled(answer: unknown): boolean {
  if (!answer || typeof answer !== 'object') return false
  const r = answer as { done?: unknown; gate?: unknown }
  if (r.done === true) return true
  return !!r.gate && typeof r.gate === 'object' && (r.gate as { setup?: unknown }).setup === true
}
