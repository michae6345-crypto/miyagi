/**
 * Feature: ambient. bon points at an AmbientTarget (an error on screen, a help step's control) with the existing
 * pointing: the buddy stroke (features/annotate) and the character's loop (features/buddy pointing). Whichever of the
 * two draws in this build draws it (buddy/marks.ts standsDown); the other holds the mark and draws nothing. Read-only
 * use of their exported `show` / `fade`: no edits there.
 *
 * Ambient marks use ids starting "amb-", so pointAway() takes away only ours.
 */
import type { AmbientTarget } from '../../../../../../shared/contracts/events'
import { fade as fadeAnnotate, show as showAnnotate, useAnnotate } from '../annotate/store'
import { fade as fadeBuddy, show as showBuddy, usePointing } from '../buddy/pointing'

/** A help step stays pointed at while the learner works through it (the annotate maximum). */
export const STEP_HOLD_MS = 30_000
/** Show me on an error: long enough to look, then it fades (or when the learner goes there). */
export const SHOW_HOLD_MS = 8000

export const isTarget = (t: Partial<AmbientTarget> | undefined | null): t is AmbientTarget =>
  !!t && [t.x, t.y, t.w, t.h].every((v) => typeof v === 'number' && Number.isFinite(v)) && (t.w as number) > 0 && (t.h as number) > 0

let asks = 0

/** Point at `t` (screen points) as mark `id` (prefixed "amb-"). Returns false when there is nothing to point at. */
export function pointAt(id: string, t: AmbientTarget | undefined, holdMs = SHOW_HOLD_MS): boolean {
  if (!isTarget(t)) return false
  // A fresh askId each time: both stores forget what was "gone" on a new ask, so Back to a step points at it again.
  const mark = { id: `amb-${id}`, x: t.x, y: t.y, w: t.w, h: t.h, displayId: t.displayId, label: t.label, why: 'point' as const, askId: `amb-${++asks}` }
  try {
    showAnnotate([mark], holdMs)
  } catch {
    // the annotate layer is not in this build
  }
  try {
    showBuddy([mark], holdMs)
  } catch {
    // the buddy is not in this build
  }
  return true
}

/** Take away the ambient marks (a step moved on, the card closed); anything the coach drew stays. */
export function pointAway(): void {
  const ours = (keys: { key: string; id?: string }[]): string[] => keys.filter((m) => m.id?.startsWith('amb-')).map((m) => m.key)
  const a = ours(useAnnotate.getState().marks)
  if (a.length) fadeAnnotate(a)
  const b = ours(usePointing.getState().marks)
  if (b.length) fadeBuddy(b)
}
