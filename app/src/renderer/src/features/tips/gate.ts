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
