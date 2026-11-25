/**
 * On-screen coach (Nov 24, agents/app-onscreen-coach.md): in an app lesson (lesson.ready lesson.app: the desktop app a
 * no-code lesson is done in), the coaching happens on the screen itself, beside the buddy's circle. So the lesson
 * drawer starts collapsed to the island; the steps list stays one click away (the Mini pill, or any `panel` open).
 *
 *   - lesson.ready with lesson.app {tool} and no replay: ask core's `panel` UI event to collapse, once, AFTER the
 *     drawer's own lesson.ready handler has opened it (features load A to Z and this one is first, so it waits a tick).
 *   - Never for a lesson without app (code / VS Code lessons keep the drawer open), never on a replay (a reconnect keeps
 *     what the learner chose), and never again once the learner opened the panel: one collapse per lesson.ready.
 *   - Nothing lesson-specific: any app the engine names.
 *
 * lesson.app is the contract's LessonApp; its values are still checked here (wire data).
 */
import type { LessonApp } from '../../../../../../shared/contracts/events'
import { emitUi, onMessage } from '../../core/bus'

export type { LessonApp }

/** The lesson's desktop app, if it is an app lesson: an object with a non-empty string tool. */
export function lessonAppOf(lesson: unknown): LessonApp | undefined {
  const app = lesson && typeof lesson === 'object' ? (lesson as { app?: unknown }).app : undefined
  if (!app || typeof app !== 'object') return undefined
  const { tool, label, using } = app as { tool?: unknown; label?: unknown; using?: unknown }
  if (typeof tool !== 'string' || !tool.trim()) return undefined
  return { tool, label: typeof label === 'string' ? label : tool, ...(typeof using === 'string' && using ? { using } : {}) }
}

/** The collapse waiting for its tick (a second lesson.ready before it runs replaces it). */
let pending: ReturnType<typeof setTimeout> | undefined

onMessage('lesson.ready', (p) => {
  clearTimeout(pending)
  pending = undefined
  if (!p || p.replay || !lessonAppOf(p.lesson)) return
  pending = setTimeout(() => {
    pending = undefined
    emitUi('panel', 'collapse')
  }, 0)
})
