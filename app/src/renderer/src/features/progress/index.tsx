/**
 * Feature: progress (A8, miyagi-v2 BUILD-PLAN). Island modes and one app window:
 *
 *   step-passed  priority 55 (README island table): Prog-Step-Passed. Only while the lesson panel is collapsed to the
 *                Mini pill (decision 7), or in a video lesson once SHOW_ON_VIDEO is flipped; never while the panel is
 *                open, never on the last step (store.ts).
 *   review       priority 42: Prog-Review-Reminder, at launch with no lesson running (fixture data until a scheduler
 *                exists). Below every lesson card; a lesson starting closes it.
 *   window       route `progress`, kind 'app': Prog-Progress-Window (core/surfaces openProgress()).
 *
 * Stage: ?scenario=progress&hold&clean (the step card held open) · &window=progress · ?scenario=full&review&clean
 * (the reminder) · ?scenario=core-v2&window=progress (the empty states).
 */
import { defineFeature } from '../../core/registry'
import { useDock } from '../../core/dock'
import { useGateOpen } from '../../core/gate'
import { useLesson } from '../../core/lesson'
import { ReviewReminderCard, REVIEW_W } from './ReviewReminder'
import { StepPassedCard, STEP_W } from './StepPassed'
import { STAGE_HOLD, useProgress } from './store'
import { ProgressWindow } from './Window'
import './web'

/** Decision 7: the step card also shows in video lessons once this is flipped (off for this push). */
export const SHOW_ON_VIDEO = false

export default defineFeature({
  id: 'progress',
  islandModes: [
    {
      id: 'step-passed',
      priority: 55,
      width: STEP_W,
      useActive: () => {
        const card = useProgress((s) => !!s.step)
        const open = useDock((d) => d.open)
        const mini = useDock((d) => d.collapsed)
        const video = useLesson((s) => !!s.lesson && s.lesson.mode !== 'lesson')
        return card && !open && (mini || STAGE_HOLD || (video && SHOW_ON_VIDEO))
      },
      Content: StepPassedCard
    },
    {
      id: 'review',
      priority: 42,
      width: REVIEW_W,
      useActive: () => {
        // Never before the sign-in gate opens (core/gate.ts): the launch check itself waits for it too (store.ts).
        const open = useGateOpen()
        const review = useProgress((s) => !!s.review)
        const lesson = useLesson((s) => !!s.lesson || s.building)
        return open && review && !lesson
      },
      Content: ReviewReminderCard
    }
  ],
  windows: [{ route: 'progress', kind: 'app', Component: ProgressWindow }]
})
