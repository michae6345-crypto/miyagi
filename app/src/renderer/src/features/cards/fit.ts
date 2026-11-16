/**
 * One row of card buttons that never wraps (Michael's review A22: a second row of buttons made the card jump under
 * the pointer). useFitLevel says how far the row has to shrink to fit; the caller decides what each step is
 * (shorter labels, then icon-only quiet buttons). Measured before paint, so the row is never drawn overflowing.
 */
import { useLayoutEffect, useState, type RefObject } from 'react'

/**
 * 0 = as designed; 1..max = one step smaller each. `sig` names what's in the row (buttons and labels): a new one
 * starts again at 0. A spinner swapping in for an icon has the icon's size, so it never changes the level.
 */
export function useFitLevel(ref: RefObject<HTMLElement | null>, sig: string, max: number): number {
  const [fit, setFit] = useState({ sig, level: 0 })
  // Other buttons: measure again from the full row (set during render, like Clamp's new text).
  if (fit.sig !== sig) setFit({ sig, level: 0 })
  const level = fit.sig === sig ? fit.level : 0
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || level >= max) return
    if (el.scrollWidth > el.clientWidth + 1) setFit({ sig, level: level + 1 })
  })
  return level
}

/** "Visual Studio Code" → "VS Code": the short name a tight row uses. */
export const shortEditor = (label: string): string => label.replace(/visual studio code/i, 'VS Code')
