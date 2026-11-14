/** Feature: cards. Which coach card is showing (the off-track payload itself lives in core/lesson). */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { onMessage, onUi } from '../../core/bus'
import { useLesson, type CheckItem } from '../../core/lesson'

type CardsState = {
  /** The off-track card is open (it can be dismissed; hovering the pill reopens it). */
  offtrackOpen: boolean
  /** The current step went off-track at some point → show "Back on track" when it passes. */
  recovered: boolean
  success?: { index: number; summary?: string; checks: CheckItem[]; at: number }
  card?: Payload<'card'>
}

const blank: CardsState = { offtrackOpen: false, recovered: false, success: undefined, card: undefined }
export const useCards = create<CardsState>(() => ({ ...blank }))
const set = useCards.setState

let successTimer: ReturnType<typeof setTimeout> | undefined

onUi('reset', () => set({ ...blank }))
onUi('dismiss', () => set({ offtrackOpen: false, success: undefined, card: undefined }))
onMessage('lesson.ready', () => set({ ...blank }))
onMessage('step.started', () => set({ offtrackOpen: false, recovered: false, card: undefined }))
onMessage('offtrack', () => set({ offtrackOpen: true, recovered: true, card: undefined }))
onMessage('card', (p) => set({ card: p, offtrackOpen: false }))
onMessage('diagram', () => set({ card: undefined, offtrackOpen: false }))
onMessage('step.passed', (p) => {
  const { recovered } = useCards.getState()
  set({ offtrackOpen: false })
  if (!recovered) return
  const lesson = useLesson.getState()
  const index = lesson.steps.findIndex((x) => x.id === p.stepId)
  set({ success: { index, summary: (p as typeof p & { summary?: string }).summary, checks: lesson.checks, at: Date.now() } })
  clearTimeout(successTimer)
  successTimer = setTimeout(() => set({ success: undefined }), 3800)
})
