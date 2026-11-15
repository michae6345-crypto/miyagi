/**
 * The overview's text lines, all read from core/lesson (nothing PINN-specific, nothing explains the UI):
 *  - Instructions: the step's "what do I do now" (Michael P1-6: stored, never shown until now). 2 lines max.
 *  - StepSnippet: the code to type for this step (spotlight.snippet), monospace, under the instructions.
 *  - GoalNote: lesson.goalMatch.note in amber under the title, only when the video doesn't fit the goal (score < 0.5).
 *  - Meta: who built the lesson (builtByLabel) and, for a long video still building, where its parts stand.
 */
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { builtByLabel, useLesson } from '../../core/lesson'
import { color, fill, font } from '../../core/theme'
import { useDrawer } from '../drawer/store'
import { useStepSnippet } from './snippet'

/** Below this goalMatch score the video doesn't fit what the learner asked for (contract: preflight warning). */
const GOAL_MISMATCH = 0.5

export function Instructions(): ReactNode {
  const text = useLesson((s) => s.instructions.trim())
  if (!text) return null
  return (
    <div className="mt-[16px] line-clamp-2 text-[14px] leading-[20px]" style={{ color: color.label }} title={text}>
      {text}
    </div>
  )
}

/** The code to type for this step, monospace like the cards' diff view (spotlight.snippet, kept by ./snippet). */
export function StepSnippet(): ReactNode {
  const stepId = useLesson((s) => s.stepId)
  const snip = useStepSnippet()
  // The code lives in one place (Michael's desktop test, item 5): in a "Just teach me" lesson or with the drawer
  // open, the drawer has it.
  const textLesson = useLesson((s) => s.lesson?.mode === 'lesson')
  const drawerOpen = useDrawer((s) => s.open)
  if (textLesson || drawerOpen || !snip.code || snip.stepId !== stepId) return null
  return (
    <pre
      className="mt-[10px] max-h-[126px] overflow-hidden whitespace-pre rounded-[12px] px-[12px] py-[8px] text-[12.5px] leading-[18px]"
      style={{ fontFamily: font.mono, background: fill.field, color: color.text }}
    >
      {snip.code}
    </pre>
  )
}

export function GoalNote(): ReactNode {
  const goal = useLesson((s) => s.lesson?.goalMatch)
  const note = goal?.note.trim()
  if (!note || goal?.score == null || goal.score >= GOAL_MISMATCH) return null
  return (
    <div className="mt-[3px] line-clamp-2 text-[13px] leading-[17px]" style={{ color: color.label }} title={note}>
      {note}
    </div>
  )
}

/** "Next part is still building" while the learner waits on it; otherwise "More steps coming" until the lesson is complete. */
export function partLine(complete: boolean, pendingNext: boolean): string | undefined {
  return pendingNext ? 'Next part is still building' : complete ? undefined : 'More steps coming'
}

export function Meta(): ReactNode {
  const m = useLesson(useShallow((s) => ({ by: builtByLabel(s.lesson?.builtBy, s.lesson?.mode), part: partLine(s.complete, s.pendingNext) })))
  if (!m.by && !m.part) return null
  return (
    <div className="mt-[16px] flex items-center justify-between gap-[12px] text-[13px] leading-[17px]" style={{ color: color.faint }}>
      <span className="truncate">{m.by}</span>
      {m.part && <span className="shrink-0">{m.part}</span>}
    </div>
  )
}
