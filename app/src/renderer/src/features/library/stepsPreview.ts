/**
 * The step-by-step preview on a lesson's detail page: which rows show, and the quiet "Show all" fold.
 * Labels come from the engine's step list only (title, optional `what`, optional estMinutes). With no steps there is
 * nothing to fold and the page keeps its one-line fallback.
 */
import type { OutlineStep } from '../../../../../../shared/contracts/events'

/** Rows shown before the fold. A list of exactly this many shows whole (a fold that hides one row is worse than the row). */
export const PREVIEW_FOLD = 6

export interface StepsPreview {
  /** The rows to draw. */
  rows: OutlineStep[]
  /** How many are folded away (0 = no control). */
  hidden: number
}

export function previewSteps(steps: readonly OutlineStep[], expanded: boolean): StepsPreview {
  if (expanded || steps.length <= PREVIEW_FOLD) return { rows: [...steps], hidden: 0 }
  return { rows: steps.slice(0, PREVIEW_FOLD), hidden: steps.length - PREVIEW_FOLD }
}

/** "Show all 9 steps" / "Show fewer". */
export const foldLabel = (total: number, expanded: boolean): string => (expanded ? 'Show fewer' : `Show all ${total} steps`)
