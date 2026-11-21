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
 *     and Ready to run), action resume (an explicit "Continue") or action build (this run's preflight card).
 *   - Lesson events (steps, checks, cards about a step, a preflight card, video, spotlight, diagrams, pause) pass only
 *     while this run has a lesson or one is on its way. Everything else (hello, search rows, library, progress,
 *     health, keys, errors, an answer to a typed question) always passes.
 *   - The pill never spins for a lesson this run doesn't have: with no lesson, `status` thinking / busy pass only while
 *     a question or button press of this run (action ask, explain, hint ...) waits for its answer, and an old lesson's
 *     watching / offtrack / passed reach the windows as idle.
 *   - The run's lesson ends with lesson.ended (any reason but "interrupted": an engine deploy that comes back with the
 *     same lesson, whose replay then passes again because its id matches).
 *   - A wait for a lesson ends with its lesson.ready, a failed build, end_lesson (command or action) or dev.reset. It
 *     survives a new engine connection (sleep / wake during a long build), but then only a fresh lesson.ready (no
 *     `replay: true`, or the run's own id) ends it: the new connection's snapshot of an old lesson never does, and of
 *     that snapshot only lesson.building (the learner's build) passes, until a start goes out on the new connection.
 *
 * Pure (no electron, no socket), so main/engine.ts runs it on every event and freshStart.check.ts tests it in Node.
 */
import type { Incoming, Outgoing } from '../common/wire'

/** Commands that start (or explicitly choose) a lesson in this run. */
const START = new Set<string>(['learn', 'learn_url', 'build_lesson', 'library.start'])
/** action kinds that explicitly choose a lesson: "Continue" on a saved lesson, "Build" on this run's preflight card. */
const START_ACTIONS = new Set<string>(['resume', 'build'])

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
/**
 * Card kinds that belong to a lesson (an "answer" to a typed question, or an explain of a selection, does not).
 * preflight (what the picked video is, Build / Pick another) only ever follows a learn / learn_url of this run, while
 * a lesson is on its way; at launch it is an old pick's card from the engine's snapshot.
 */
const LESSON_CARDS = new Set<string>(['resume', 'setup', 'preflight', 'step', 'where', 'hint', 'complete'])
/** Pill states that say a lesson is running: shown as idle when this run has none. */
const LESSON_STATUS = new Set<string>(['watching', 'offtrack', 'passed'])
/** Pill states that say the engine is working: shown for this run's lesson, or a press of this run still waiting. */
const WORKING_STATUS = new Set<string>(['thinking', 'busy'])

/** A fresh object every time: listeners and the replay log never share it. */
const idle = (): Incoming => ({ type: 'status', payload: { state: 'idle' } }) as Incoming

export type GuardState = {
  /** The lesson this run started or chose (its lesson.ready id). */
  lessonId?: string
  /** A start command went out and its lesson.ready hasn't come yet. */
  pending: boolean
  /** The wait came over a new engine connection: only a fresh lesson.ready (not a snapshot replay) ends it. */
  carried: boolean
  /** A non-start action of this run (ask, explain, hint ...) waits for its answer. */
  asking: boolean
}

export class RunGuard {
  private lessonId?: string
  private pending: boolean
  private carried = false
  /** carried: the learner's build came back on the new connection (its lesson.building passed), so its status may too. */
  private building = false
  private asking = false

  /**
   * `armed`: a run that plays a lesson on purpose (DEMO=1's scripted run, or MIYAGI_REPLAY_ON_CONNECT=1 for
   * `npm run dev:all`'s mock replay): a lesson is on its way at start, after every dev.reset and on every connection.
   */
  constructor(private readonly armed = false) {
    this.pending = armed
  }

  state(): GuardState {
    return { lessonId: this.lessonId, pending: this.pending, carried: this.carried, asking: this.asking }
  }

  /** Every command the app sends to the engine (main/engine.ts send(), only once it really leaves). */
  command(cmd: Outgoing): void {
    const kind = cmd.type === 'action' ? String((cmd.payload as { kind?: unknown })?.kind) : undefined
    if (START.has(cmd.type) || (kind !== undefined && START_ACTIONS.has(kind))) {
      this.wait(true)
    } else if (cmd.type === 'dev.reset') {
      // The mock replays its scenario's 'connect' segment: armed runs (DEMO) take its lesson again.
      this.wait(this.armed)
      this.lessonId = undefined
      this.asking = false
    } else if (cmd.type === 'end_lesson' || kind === 'end_lesson') {
      // The learner stopped: a build or start still on its way is abandoned (lesson.ended clears the run's lesson).
      this.wait(false)
      this.asking = false
    } else if (kind !== undefined) {
      this.asking = true
    }
  }

  /**
   * A new engine connection (main/engine.ts ws 'open'). Its snapshot may replay an old lesson. A wait from the old
   * connection stays (a long build survives sleep / wake), but only a fresh lesson.ready ends it now. A question sent
   * on the old connection lost its socket: its answer no longer comes.
   */
  connected(): void {
    this.asking = false
    if (this.armed) return this.wait(true)
    this.carried = this.pending
    this.building = false
  }

  /** Does this engine event reach the windows, main's features and the replay log exactly as sent? */
  admit(e: Incoming): boolean {
    return this.filter(e) === e
  }

  /**
   * What of this engine event reaches the windows, main's features and the replay log: the event itself, a rewrite
   * (an old lesson's watching becomes idle) or nothing.
   */
  filter(e: Incoming): Incoming | undefined {
    if (e.type === 'lesson.ready') {
      const p = e.payload as { lesson?: { id?: unknown }; replay?: unknown }
      const id = typeof p?.lesson?.id === 'string' && p.lesson.id ? p.lesson.id : undefined
      const same = !!id && id === this.lessonId
      if (!same && !this.pending) return undefined
      // A new connection's snapshot replay never answers a start sent on the old one.
      if (!same && this.carried && p?.replay === true) return undefined
      this.wait(false)
      this.lessonId = id
      return e
    }
    if (e.type === 'lesson.ended') {
      const p = e.payload as { lessonId?: unknown; reason?: unknown }
      const mine = !p?.lessonId || p.lessonId === this.lessonId
      if (mine && p?.reason !== 'interrupted') this.lessonId = undefined
      // Always passes: windows reset on it, which is never harmful.
      return e
    }
    if (e.type === 'lesson.building') {
      // The learner's build, also when its wait came over a new connection.
      const pass = this.live() || this.pending
      if ((e.payload as { failed?: unknown })?.failed === true) this.wait(false)
      // (A failed build ends the wait: a later stale lesson.ready must not slip through.)
      else if (pass && this.carried) this.building = true
      return pass ? e : undefined
    }
    if (this.live()) return e
    if (e.type === 'status') {
      const state = String((e.payload as { state?: unknown })?.state)
      if (WORKING_STATUS.has(state)) return this.asking || (this.carried && this.building) ? e : undefined
      // A lesson this run doesn't have is running in the engine: the pill rests (a waiting press keeps its spinner).
      if (LESSON_STATUS.has(state)) return this.asking ? undefined : idle()
      this.asking = false
      return e
    }
    if (LESSON_EVENTS.has(e.type)) return undefined
    if (e.type === 'card') {
      const p = e.payload as { kind?: unknown; stepId?: unknown }
      if (LESSON_CARDS.has(String(p?.kind)) || p?.stepId) return undefined
      this.asking = false
      return e
    }
    if (e.type === 'diagram') {
      if ((e.payload as { stepId?: unknown })?.stepId) return undefined
      this.asking = false
      return e
    }
    if (e.type === 'error') this.asking = false
    if (e.type === 'blocker') {
      const p = e.payload as { kind?: unknown; clear?: unknown }
      return p?.clear === true || p?.kind === 'network' ? e : undefined
    }
    return e
  }

  /** This run has a lesson, or one is on its way from a start sent on this connection. */
  private live(): boolean {
    return !!this.lessonId || (this.pending && !this.carried)
  }

  private wait(on: boolean): void {
    this.pending = on
    this.carried = false
    this.building = false
  }
}
