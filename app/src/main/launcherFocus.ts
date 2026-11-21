/**
 * Which miyagi window had the keyboard when the launcher opened (UI-TEST 2026-11-21, item 4). Pure, so
 * test/launcherFocus.test.ts runs it without Electron; main/features/launcher-focus.ts feeds it window events.
 *
 * Esc on a launcher opened from the home window used to hand focus to Finder: main reactivates "the last app that was
 * not miyagi" (front-app.ts previousApp), and that was whatever app came before the learner clicked into miyagi.
 * Now: a miyagi app window that was focused (or lost focus a moment before the launcher took it) gets focus back;
 * otherwise nothing here acts and the learner's app stays in front.
 */

/** A blur this soon before the launcher opened still counts: the window lost focus because the launcher took it. */
export const BLUR_WINDOW_MS = 600

export type FocusMemory = {
  focus(id: number): void
  blur(id: number): void
  /** The launcher is showing: remember the window it came from (once per open). */
  opened(): void
  /** The launcher hid: the window to bring back, if any, and forget it. */
  closed(): number | undefined
}

export function createFocusMemory(now: () => number = Date.now): FocusMemory {
  let current: number | undefined
  let lastBlur: { id: number; at: number } | undefined
  let origin: number | undefined
  let open = false
  return {
    focus(id) {
      current = id
    },
    blur(id) {
      if (current === id) current = undefined
      lastBlur = { id, at: now() }
    },
    opened() {
      if (open) return
      open = true
      origin = current ?? (lastBlur && now() - lastBlur.at <= BLUR_WINDOW_MS ? lastBlur.id : undefined)
    },
    closed() {
      const id = origin
      origin = undefined
      open = false
      return id
    }
  }
}

/** Delays (ms) at which to re-assert focus: main's own `open -b <app>` for the old "previous app" lands after hide. */
export const REFOCUS_AT_MS = [60, 200, 500] as const
