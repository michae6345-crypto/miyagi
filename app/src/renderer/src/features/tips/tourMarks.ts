/**
 * Feature: tips. The first-lesson walkthrough: five short marks over a sample lesson panel (TourLayer.tsx). Pure data.
 * Copy: calm, 12 words or fewer, lowercase miyagi, the same on a Mac and a PC ("top of your screen", never "the
 * notch"). Keys are drawn from the platform (never typed), option names as their pastel chips (same mapping as the
 * real panel).
 *
 * Refined Nov 21 (Adrian: "the walkthrough can be a bit better"): the sample is now the real lesson panel's shape
 * (header with step dots, the step with its code, Check my work, Need help, the keys line), so every mark points at
 * something the learner will really see. The old fifth mark pointed at an End lesson button the real panel doesn't
 * have; it now points at the keys line, where asking lives.
 */
import type { BodyPart, Side } from './tips'

export type TourTarget = 'island' | 'steps' | 'check' | 'help' | 'keys'
export type TourMark = { id: string; title: string; body: BodyPart[]; target: TourTarget; side: Side }

export const TOUR: readonly TourMark[] = [
  { id: 'pill', title: 'This is miyagi', body: ['It waits at the top of your screen. Point at it for your step.'], target: 'island', side: 'below' },
  { id: 'steps', title: 'One step at a time', body: ['The dots show where you are in the lesson.'], target: 'steps', side: 'left' },
  { id: 'check', title: 'Check my work', body: ['Done with a step? Press it. miyagi checks your real work.'], target: 'check', side: 'left' },
  { id: 'help', title: 'Stuck?', body: ['Try ', { option: 'hint' }, ' first, then ', { option: 'explain' }, '.'], target: 'help', side: 'left' },
  { id: 'ask', title: 'Ask anytime', body: ['Press ', { key: 'launcher' }, ' in any app to ask miyagi.'], target: 'keys', side: 'left' }
]

/** The sample lesson (never sent anywhere: the walkthrough starts no lesson). */
export const SAMPLE = {
  title: 'Sample lesson',
  total: 3,
  step: 'Print your first line',
  line: 'Say hello from Python.',
  where: 'Type this in a new file',
  code: "print('hello')"
} as const

/** How long a mark waits for its target to show (the sample panel springs in) before the tour skips it. */
export const TARGET_GRACE_MS = 900

export type MarkPlan = { kind: 'show'; index: number } | { kind: 'wait' } | { kind: 'skip'; to: number } | { kind: 'end' }

/**
 * Which mark to draw now. The island is always there (TourLayer falls back to the top centre). Any other target that
 * isn't on screen is waited for TARGET_GRACE_MS, then skipped for the next mark whose target is there; with none left
 * the tour ends, so it never stalls on a mark with nothing to point at.
 */
export function planMark(index: number, present: (t: TourTarget) => boolean, waitedMs: number, marks: readonly TourMark[] = TOUR): MarkPlan {
  const mark = marks[index]
  if (!mark) return { kind: 'end' }
  const there = (t: TourTarget): boolean => t === 'island' || present(t)
  if (there(mark.target)) return { kind: 'show', index }
  if (waitedMs < TARGET_GRACE_MS) return { kind: 'wait' }
  for (let i = index + 1; i < marks.length; i++) if (there(marks[i].target)) return { kind: 'skip', to: i }
  return { kind: 'end' }
}
