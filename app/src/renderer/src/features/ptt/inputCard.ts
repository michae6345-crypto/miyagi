/**
 * Feature: ptt. When the once-per-run Input Monitoring card may show. Pure, so the rule is tested without a window.
 *
 * It shows only when push to talk is on, Input Monitoring is off, it hasn't shown this run, and the launch gate is open
 * (signed in and first-run setup finished or put off: main/gate.ts). A closed gate means the first-run flow or setup is
 * on screen, and a permission card there would talk over the guided steps. The card is not lost while the gate is
 * closed: it is asked again whenever the gate opens or a pref changes.
 */
export type InputCardFacts = { shown: boolean; inputDenied: boolean; enabled: boolean; gateOpen: boolean }

export function shouldShowInputCard(f: InputCardFacts): boolean {
  return !f.shown && f.inputDenied && f.enabled && f.gateOpen
}
