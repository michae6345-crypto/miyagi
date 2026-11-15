/**
 * Feature: drawer. A run step (step.kind "run") tucks the drawer to its "Steps" handle so VS Code's Run button and the
 * terminal are clear (Michael's test, Sun 2:56 AM), unless the learner pressed the handle for this step.
 * While it is tucked, nothing floats on its own: the Diagram button slides the flyout out from the handle's edge, below
 * the editor's tab row (RUN_DROP) so the Run button stays clear, and above the terminal (RUN_SHARE). Flyout.tsx.
 */
import { useLesson } from '../../core/lesson'
import { useStepDetail } from './plan'
import { useDrawer } from './store'

/** Below the editor's tab row and its Run ▷ (VS Code: title bar + tabs + breadcrumbs ≈ 80 px). */
export const RUN_DROP = 88
/** The share of the work area above the terminal panel (VS Code's panel takes about the bottom third). */
export const RUN_SHARE = 0.6

/** The run step's id while it has the drawer tucked, else undefined. */
export function useRunTuck(): string | undefined {
  const lessonMode = useLesson((s) => s.lesson?.mode === 'lesson')
  const open = useDrawer((s) => s.open)
  const runStep = useStepDetail((s) => (s.detail?.kind === 'run' ? s.detail.stepId : undefined))
  const peekStep = useDrawer((s) => s.peekStep)
  return lessonMode && open && runStep && peekStep !== runStep ? runStep : undefined
}
