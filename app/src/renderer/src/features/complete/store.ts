/**
 * Feature: complete (Michael's NEW 2, mockup 10 style). The lesson-complete card: when the last step passes the
 * engine sends a card of kind "complete" (lesson_end.card() sends kind "step") with an optional skillMap. This store
 * keeps that card so the panel can draw it; it reads the same `card` message as features/cards (whose own store
 * drops a card on any `diagram`), so a diagram opened on top doesn't lose the panel.
 *
 * Opens: a card with a skillMap, or kind "complete". Closes: any other card, Esc / ✕ (dismiss), Back (a new
 * step.started), a new lesson, a reset (lesson.ended).
 */
import { noteLearnMode } from '../../core/lesson'
import { create } from 'zustand'
import { cmd, type Payload } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { emitUi, onMessage, onUi } from '../../core/bus'
import { sendAction } from '../../core/shortcuts'
import { readNet, lossSeries, type Net } from './net'
import { readSkillMap, type SkillMap } from './types'

export type CompleteCard = { title: string; body: string; stepId?: string; endLabel?: string; map?: SkillMap }
export type PassedCheck = { stepId: string; label: string; at: number }
type State = {
  card?: CompleteCard
  ending: boolean
  /** The lesson's networks as the engine pushed them (mockup 12): the newest one, and the newest with a training curve. */
  net?: Net
  trained?: Net
  /** Every check this window saw pass in this lesson (stepId:checkId), newest last. */
  checks: Record<string, PassedCheck>
  /** When this window saw the lesson load (lesson.ready), for the minutes it took. */
  startedAt?: number
}

const lessonBlank = { net: undefined, trained: undefined, checks: {}, startedAt: undefined }
export const useComplete = create<State>(() => ({ card: undefined, ending: false, ...lessonBlank }))
const set = useComplete.setState
const get = useComplete.getState

/** End lesson didn't bring lesson.ended this fast: reset here anyway (like the bar's End on a finished lesson). */
const END_FALLBACK_MS = 1500
let endTimer: ReturnType<typeof setTimeout> | undefined

const close = (): void => {
  clearTimeout(endTimer)
  set({ card: undefined, ending: false })
}

onMessage('card', (p) => {
  // kind "complete" isn't in the contract's union yet (Michael's email): compare it as a plain string
  const raw = p as Omit<Payload<'card'>, 'kind'> & { kind: string; skillMap?: unknown }
  const map = readSkillMap(raw.skillMap)
  if (!map && raw.kind !== 'complete') {
    if (get().card) close() // any other card (an answer, an explain) replaces the panel
    return
  }
  set({
    card: {
      title: raw.title?.trim() || 'Lesson complete',
      body: raw.body?.trim() || map?.headline || '',
      stepId: raw.stepId,
      endLabel: raw.setup?.actionLabels?.end_lesson,
      map
    },
    ending: false
  })
})
onMessage('step.started', close)
onMessage('lesson.ready', () => {
  close()
  set({ ...lessonBlank, startedAt: Date.now() })
})
onUi('dismiss', close)
onUi('reset', () => {
  close()
  set({ ...lessonBlank })
})
// The lesson's own network (kind "network" with real weights in data.frames): its newest picture, and its newest
// training run (frames over at least two epochs) for the loss chart.
onMessage('diagram', (p) => {
  if (p.kind !== 'network') return
  // A preview (data.preview, before the learner's first real run) is not their network: not the thumbnail, not the charts.
  if ((p.data as { preview?: unknown } | undefined)?.preview === true) return
  const net = readNet(p.data)
  if (!net) return
  set(lossSeries(net) ? { net, trained: net } : { net })
})
onMessage('check.updated', (p) => {
  const key = `${p.stepId}:${p.checkId}`
  const checks = { ...get().checks }
  if (p.status === 'pass') checks[key] = checks[key] ?? { stepId: p.stepId, label: p.label, at: Date.now() }
  else delete checks[key]
  set({ checks })
})

/** Up next: start that lesson the way the launcher's "Just teach me" does (contract SkillNext.goal). */
export function startLesson(goal: string): void {
  noteLearnMode(undefined)
  bridge.send(cmd('learn', { query: goal, mode: 'lesson' }))
  emitUi('dismiss') // the panel and the engine's card both close; the pill shows the new build
}

/** End lesson: action end_lesson (the engine answers lesson.ended, which resets every store). */
export function endLesson(): void {
  if (get().ending) return
  set({ ending: true })
  sendAction('end_lesson')
  clearTimeout(endTimer)
  endTimer = setTimeout(() => {
    if (get().ending) emitUi('reset', { scope: 'lesson', reason: 'end_lesson' })
  }, END_FALLBACK_MS)
}
