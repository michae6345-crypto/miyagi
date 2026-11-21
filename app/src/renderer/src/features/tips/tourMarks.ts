/**
 * Feature: tips. The first-lesson walkthrough: five short marks over a sample lesson panel (TourLayer.tsx). Pure data.
 * Copy: calm, 12 words or fewer, lowercase miyagi. Keys are drawn from the platform (never typed), option names as
 * their pastel chips (same mapping as the real panel).
 */
import type { BodyPart, Side } from './tips'

export type TourTarget = 'island' | 'steps' | 'check' | 'help' | 'end'
export type TourMark = { id: string; title: string; body: BodyPart[]; target: TourTarget; side: Side }

export const TOUR: readonly TourMark[] = [
  { id: 'pill', title: 'This is miyagi', body: ['Point at it for your step. Press ', { key: 'launcher' }, ' to ask.'], target: 'island', side: 'below' },
  { id: 'steps', title: 'Your steps', body: ['Each lesson is a short list. One step at a time.'], target: 'steps', side: 'left' },
  { id: 'check', title: 'Check my work', body: ["Press it when you're done. miyagi checks it."], target: 'check', side: 'left' },
  { id: 'help', title: 'Stuck?', body: ['Try ', { option: 'hint' }, ' first, then ', { option: 'explain' }, '.'], target: 'help', side: 'left' },
  { id: 'end', title: 'Finish anytime', body: ['End lesson stops it. Your place is saved.'], target: 'end', side: 'left' }
]

/** The sample lesson's steps (never sent anywhere: the walkthrough starts no lesson). */
export const SAMPLE = {
  title: 'Sample lesson',
  steps: ['Print your first line', 'Change the message', 'Run it again'],
  hint: "Type print('hello') and run it."
} as const
