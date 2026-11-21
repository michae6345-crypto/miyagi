/**
 * Feature: complete (A8 restyle of Michael's NEW 2; mockup Prog-Completion). The lesson-complete card: when the last
 * step passes the engine sends a card of kind "complete" (contract CardKindV2) with `result` (what the lesson counted)
 * and an optional skillMap (its `next` lessons). This store keeps that card so the panel can draw it; it reads the same
 * `card` message as features/cards (whose own store drops a card on any `diagram`), so a diagram opened on top doesn't
 * lose the panel.
 *
 * Opens: a card with a skillMap, or kind "complete". Closes: any other card, Esc / ✕ (dismiss), Back (a new
 * step.started), a new lesson, a reset (lesson.ended).
 *
 * Honesty: `result` is used only when its counts add up (passed + skipped <= total); otherwise the panel counts the
 * lesson's own step.passed events. Skips are counted as skips, never as passes.
 */
import { noteLearnMode } from '../../core/lesson'
import { create } from 'zustand'
import type { LessonResult } from '../../../../../../shared/contracts/events'
import { cmd, type Payload } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { emitUi, onMessage, onUi } from '../../core/bus'
import { sendAction } from '../../core/shortcuts'
import { readNet, lossSeries, type Net } from './net'
import { readSkillMap, type SkillMap } from './types'

export type { LessonResult }
export type CompleteCard = { title: string; body: string; stepId?: string; endLabel?: string; map?: SkillMap; result?: LessonResult }
type State = {
  card?: CompleteCard
  ending: boolean
  /** The lesson's networks as the engine pushed them: the newest one, and the newest with a training curve (its loss). */
  net?: Net
  trained?: Net
}

const lessonBlank = { net: undefined, trained: undefined }
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

const whole = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : undefined)

/** card.result, checked: whole counts that add up, or nothing at all (never a guessed number). */
export function readResult(raw: unknown): LessonResult | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const r = raw as Record<string, unknown>
  const passed = whole(r.passed)
  const skipped = whole(r.skipped) ?? 0
  const total = whole(r.total)
  if (passed === undefined || total === undefined || !total || passed + skipped > total) return undefined
  const minutes = whole(r.minutes)
  const title = typeof r.title === 'string' && r.title.trim() ? r.title.trim() : undefined
  const lessonId = typeof r.lessonId === 'string' && r.lessonId ? r.lessonId : undefined
  return { passed, skipped, total, ...(minutes ? { minutes } : {}), ...(title ? { title } : {}), ...(lessonId ? { lessonId } : {}) }
}

onMessage('card', (p) => {
  // Read the kind as CardKindV2 (the v2 "complete" isn't in the v1 union).
  const raw = p as Omit<Payload<'card'>, 'kind'> & { kind: string }
  const map = readSkillMap(raw.skillMap)
  if (!map && raw.kind !== 'complete') {
    if (get().card) close() // any other card (an answer, an explain) replaces the panel
    return
  }
  set({
    card: {
      title: raw.title?.trim() || '',
      body: raw.body?.trim() || map?.headline || '',
      stepId: raw.stepId,
      endLabel: raw.setup?.actionLabels?.end_lesson,
      map,
      result: readResult(raw.result)
    },
    ending: false
  })
})
onMessage('step.started', close)
onMessage('lesson.ready', () => {
  close()
  set({ ...lessonBlank })
})
onUi('dismiss', close)
onUi('reset', () => {
  close()
  set({ ...lessonBlank })
})
// The lesson's own network (kind "network" with real weights in data.frames): its newest training run (frames over at
// least two epochs) backs the result's loss when no metric line was printed.
onMessage('diagram', (p) => {
  if (p.kind !== 'network') return
  // A preview (data.preview, before the learner's first real run) is not their network.
  if ((p.data as { preview?: unknown } | undefined)?.preview === true) return
  const net = readNet(p.data)
  if (!net) return
  set(lossSeries(net) ? { net, trained: net } : { net })
})

/** Up next by goal: start that lesson the way the launcher's "Just teach me" does (contract SkillNext.goal). */
export function startLesson(goal: string): void {
  noteLearnMode(undefined)
  bridge.send(cmd('learn', { query: goal, mode: 'lesson' }))
  emitUi('dismiss') // the panel and the engine's card both close; the pill shows the new build
}

/** Up next as a cached lesson: library.start (zero model calls). Only when the engine listed library.start. */
export function startCached(id: string): void {
  bridge.send(cmd('library.start', { id }))
  emitUi('dismiss')
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
