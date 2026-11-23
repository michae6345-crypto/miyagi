/**
 * Spotlight calm gate (video lessons): one primary surface at a time.
 *
 * In a video lesson the drawer, the player and the shortcut bar are already on screen, so the dim is the fourth loud
 * thing. The gate lets the spotlight in only when something asks for it, then folds it away:
 *   arm()          a step started, or Not yet arrived: the next spotlight may show.
 *   arm(true)      the learner pressed Show me: the answer shows and stays until the engine clears it (as before).
 *   shown()        a spotlight is on screen: start the fade count (CALM_MS) once per episode.
 *   keystroke()    the learner typed: fade it now (they are working on the code it pointed at).
 * Once faded, the engine re-sending the same target on every screen read is refused (admit() is false) until the next
 * arm(), so a faded box never comes back by itself. Pure: no stores, no DOM; timers are injectable for tests.
 */

/** How long a spotlight stays before it fades on its own. */
export const CALM_MS = 4000

export type Timers = { set: (fn: () => void, ms: number) => unknown; clear: (t: unknown) => void }

export type CalmGate = {
  /** A step started or Not yet arrived (pinned: a Show me answer, which stays until cleared). */
  arm: (pinned?: boolean) => void
  /** May a spotlight message show right now? */
  admit: () => boolean
  /** A spotlight is on screen: begin the fade count (a no-op after the first call of an episode). */
  shown: () => void
  /** The learner pressed a real key: fade a visible, unpinned spotlight now. */
  keystroke: () => void
  /** Lesson over or reset: closed, nothing pending, no fade callback. */
  reset: () => void
}

export function calmGate(fade: () => void, ms: number = CALM_MS, timers: Timers = { set: (fn, ms) => setTimeout(fn, ms), clear: (t) => clearTimeout(t as ReturnType<typeof setTimeout>) }): CalmGate {
  let open = false
  let pinned = false
  let visible = false
  let timer: unknown

  const stop = (): void => {
    if (timer !== undefined) timers.clear(timer)
    timer = undefined
  }
  const close = (): void => {
    const was = visible
    stop()
    open = false
    pinned = false
    visible = false
    if (was) fade()
  }

  return {
    arm(p = false) {
      open = true
      pinned = p
      // A fresh arm while a box is up (Not yet over a step-start box): a new episode with its own count.
      if (visible) {
        stop()
        if (!pinned) timer = timers.set(close, ms)
      }
    },
    admit: () => open,
    shown() {
      if (!open) return
      visible = true
      if (!pinned && timer === undefined) timer = timers.set(close, ms)
    },
    keystroke() {
      if (visible && !pinned) close()
    },
    reset() {
      stop()
      open = false
      pinned = false
      visible = false
    }
  }
}

/** A key that counts as typing: not a lone modifier, not a shortcut chord (Alt+E and friends are actions, not typing). */
export function isTyping(e: { key: string; altKey?: boolean; ctrlKey?: boolean; metaKey?: boolean }): boolean {
  if (e.altKey || e.ctrlKey || e.metaKey) return false
  return !['Shift', 'Alt', 'Control', 'Meta', 'CapsLock', 'Fn', 'Escape', 'Tab'].includes(e.key)
}
