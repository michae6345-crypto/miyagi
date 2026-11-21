/**
 * Every launch is a fresh start (Michael: "Every time I start miyagi, it opens up the stuff on the left and right
 * ... It's like continuing a lesson. No, I need it to restart.").
 *
 * The engine sends a full snapshot on every connect: after a restart it replays the lesson it kept (lesson.ready,
 * step.started, check.updated, cards ...). Main relayed all of it to every window and into the replay log, so on
 * launch the drawer opened (drawer/store.ts opens on every lesson.ready), the player window showed (features/player.ts),
 * the lesson keys registered and the pill took the lesson's state, before the learner had asked for anything.
 *
 * RunGuard decides, per engine event, whether it belongs to a lesson the learner started or chose in THIS app run:
 *   - Nothing is accepted at launch. A lesson becomes this run's lesson only when the lesson.ready that follows a
 *     start command from this run arrives: learn, learn_url, build_lesson, library.start (Home / launcher Continue
 *     and Ready to run), or action resume (an explicit "Continue").
 *   - Lesson events (steps, checks, cards about a step, video, spotlight, diagrams, pause) pass only while this run
 *     has a lesson or one is on its way. Everything else (hello, search rows, library, progress, health, keys,
 *     errors, an answer to a typed question) always passes.
 *   - The run's lesson ends with lesson.ended (any reason but "interrupted": an engine deploy that comes back with the
 *     same lesson, whose replay then passes again because its id matches).
 *
 * Pure (no electron, no socket), so main/engine.ts runs it on every event and freshStart.check.ts tests it in Node.
 */
import type { Incoming, Outgoing } from '../common/wire'

/** Commands that start (or explicitly choose) a lesson in this run. */
const START = new Set<string>(['learn', 'learn_url', 'build_lesson', 'library.start'])
/** action kinds that explicitly choose a lesson: "Continue" on a saved lesson. */
const START_ACTIONS = new Set<string>(['resume'])

/** Events that only mean something inside a lesson: dropped when this run has none. */
const LESSON_EVENTS = new Set<string>([
  'lesson.ready',
  'lesson.updated',
  'lesson.building',
  'step.started',
  'step.passed',
  'check.updated',
  'offtrack',
  'spotlight',
  'video.seek',
  'video.pause',
  'video.play',
  'metric',
  'screen.seen',
  'lesson.paused',
  'lesson.resumed'
])
/** Card kinds that belong to a lesson (an "answer" to a typed question, or an explain of a selection, does not). */
const LESSON_CARDS = new Set<string>(['resume', 'setup', 'step', 'where', 'hint', 'complete'])
/** Pill states that say a lesson is running. idle / thinking / busy pass. */
const LESSON_STATUS = new Set<string>(['watching', 'offtrack', 'passed'])

export type GuardState = {
  /** The lesson this run started or chose (its lesson.ready id). */
  lessonId?: string
  /** A start command went out and its lesson.ready hasn't come yet. */
  pending: boolean
}

export class RunGuard {
  private lessonId?: string
  private pending: boolean

  /** `armed`: a run that plays a lesson on purpose from the start (DEMO=1's scripted run). */
  constructor(armed = false) {
    this.pending = armed
  }

  state(): GuardState {
    return { lessonId: this.lessonId, pending: this.pending }
  }

  /** Every command the app sends to the engine (main/engine.ts send()). */
  command(cmd: Outgoing): void {
    if (START.has(cmd.type)) this.pending = true
    else if (cmd.type === 'action' && START_ACTIONS.has(String((cmd.payload as { kind?: unknown })?.kind))) this.pending = true
    else if (cmd.type === 'dev.reset') {
      this.pending = false
      this.lessonId = undefined
    }
  }

  /** May this engine event reach the windows, main's features and the replay log? */
  admit(e: Incoming): boolean {
    if (e.type === 'lesson.ready') {
      const id = (e.payload as { lesson?: { id?: unknown } })?.lesson?.id
      const same = typeof id === 'string' && !!id && id === this.lessonId
      if (!this.pending && !same) return false
      this.pending = false
      this.lessonId = typeof id === 'string' ? id : undefined
      return true
    }
    if (e.type === 'lesson.ended') {
      const p = e.payload as { lessonId?: unknown; reason?: unknown }
      const mine = !p?.lessonId || p.lessonId === this.lessonId
      if (mine && p?.reason !== 'interrupted') this.lessonId = undefined
      // Always passes: windows reset on it, which is never harmful.
      return true
    }
    const live = this.pending || !!this.lessonId
    if (e.type === 'lesson.building') {
      // A failed build ends the wait; a later stale lesson.ready must not slip through.
      if ((e.payload as { failed?: unknown })?.failed === true) {
        const pass = live
        this.pending = false
        return pass
      }
      return live
    }
    if (live) return true
    if (LESSON_EVENTS.has(e.type)) return false
    if (e.type === 'card') {
      const p = e.payload as { kind?: unknown; stepId?: unknown }
      return !LESSON_CARDS.has(String(p?.kind)) && !p?.stepId
    }
    if (e.type === 'diagram') return !(e.payload as { stepId?: unknown })?.stepId
    if (e.type === 'status') return !LESSON_STATUS.has(String((e.payload as { state?: unknown })?.state))
    if (e.type === 'blocker') {
      const p = e.payload as { kind?: unknown; clear?: unknown }
      return p?.clear === true || p?.kind === 'network'
    }
    return true
  }
}
