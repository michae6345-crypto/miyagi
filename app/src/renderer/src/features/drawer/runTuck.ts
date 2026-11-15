/**
 * Feature: drawer. A run step (step.kind "run") tucks the drawer to its "Steps" handle so VS Code's Run button and the
 * terminal are clear (Michael's test, Sun 2:56 AM), unless the learner pressed the handle for this step.
 * While it is tucked, the live network floats out instead of tucking with it: training is the demo moment
 * (Michael's test 6). FloatNet shows it in RUN_CORNER; dragging it settles it there for real.
 */
import { useLesson } from '../../core/lesson'
import type { Corner } from './netFloat'
import { useStepDetail } from './plan'
import { useDrawer } from './store'

/** Top-left: clear of the Run button (top-right of the editor tabs) and the terminal (bottom). */
export const RUN_CORNER: Corner = 'tl'

/** The run step's id while it has the drawer tucked, else undefined. */
export function useRunTuck(): string | undefined {
  const lessonMode = useLesson((s) => s.lesson?.mode === 'lesson')
  const open = useDrawer((s) => s.open)
  const runStep = useStepDetail((s) => (s.detail?.kind === 'run' ? s.detail.stepId : undefined))
  const peekStep = useDrawer((s) => s.peekStep)
  return lessonMode && open && runStep && peekStep !== runStep ? runStep : undefined
}
