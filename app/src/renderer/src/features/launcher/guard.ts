/**
 * Feature: launcher. The double-open guard (UI-TEST 2026-11-21, item 3): a double-click on "New lesson", or the key
 * pressed twice fast, sends two toggles. The first opens the launcher, the second used to close it again at once.
 * main closes by sending `launcher:close` to this window; a close that arrives this soon after an open is that second
 * toggle, never a learner leaving (Esc, a click outside and Build close from this window, not through here).
 */
export const OPEN_GUARD_MS = 400

/** True when a `launcher:close` from main, `sinceOpen` ms after the last open, is a duplicate toggle to ignore. */
export function isDuplicateToggle(sinceOpen: number, guardMs: number = OPEN_GUARD_MS): boolean {
  return sinceOpen >= 0 && sinceOpen < guardMs
}
