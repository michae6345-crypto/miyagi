/**
 * Feature: settings. "Confirm before skipping a step" (Lessons). One place every Skip step button asks: with the
 * preference off the press runs at once; on, the first press arms the button (its label becomes "Tap again to skip")
 * and a second press within ARM_MS runs it. Nothing is skipped on the arming press.
 */
import { create } from 'zustand'
import { useLocal } from './local'

export const ARM_MS = 4000
export const SKIP_ARMED_LABEL = 'Tap again to skip'

const useArm = create<{ at: number }>(() => ({ at: 0 }))
let timer: ReturnType<typeof setTimeout> | undefined

/** True when the press may go ahead (preference off, or it was armed a moment ago). */
export function guardSkip(now: number = Date.now()): boolean {
  if (!useLocal.getState().confirmSkip) return true
  const { at } = useArm.getState()
  if (at && now - at <= ARM_MS) {
    clearTimeout(timer)
    useArm.setState({ at: 0 })
    return true
  }
  useArm.setState({ at: now })
  clearTimeout(timer)
  timer = setTimeout(() => useArm.setState({ at: 0 }), ARM_MS)
  return false
}

/** Re-renders a Skip step button while it is armed. */
export function useSkipArmed(): boolean {
  return useArm((s) => s.at > 0) && useLocal((s) => s.confirmSkip)
}

/** The label a Skip step button shows now (non-reactive: pair it with useSkipArmed in the component). */
export const skipLabel = (base: string): string => (useArm.getState().at > 0 && useLocal.getState().confirmSkip ? SKIP_ARMED_LABEL : base)
