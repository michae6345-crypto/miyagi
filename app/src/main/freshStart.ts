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
 *   - Lesson events (steps, checks, cards about a step, video, spotlight, diagrams, pause) pass only while this run
 *     has a lesson (its lesson.ready arrived). Everything else (hello, search rows, library, progress, health, keys,
 *     errors, an answer to a typed question) always passes.
 *   - While a start is on its way (sent, its lesson.ready not here yet) only build traffic for the new lesson passes:
 *     lesson.building, this run's preflight card, the build's thinking / busy, errors and the lesson.ready itself. The
 *     kept lesson's steps, checks, cards, video, spotlight and off-track stay out, and its watching rests the pill.
 *   - A start that leads nowhere expires: a search that ends (search.done: the next pick is its own start), a
 *     library.start answered with an error, or no sign of life for a while (OPEN_TTL_MS; PICK_TTL_MS while this
 *     run's preflight card waits for Build).
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
/** learn modes that build at once (no search, so no search.done ends their wait). */
const BUILD_MODES = new Set<string>(['lesson', 'demo'])
/**
 * action kinds the engine answers (a card, a diagram, a box, a status): while one waits its thinking may show with no
 * lesson. Fire-and-forget kinds (voice_toggle, pick_another, download, open_in_browser, install ...) wait for nothing.
 */
const ANSWERED = new Set<string>(['ask', 'explain', 'diagram', 'hint', 'show_me', 'retry', 'check_step'])
/**
 * A start with no sign of life (a search row, build progress: the engine ticks a build at least once a second, its
 * preflight card) for this long is gone: the engine dropped it, or its search never ended.
 */
export const OPEN_TTL_MS = 2 * 60_000
/** This run's preflight card waits for the learner's Build / Pick another: time to read it. */
export const PICK_TTL_MS = 30 * 60_000
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
  /** A question or press of this run (ask, explain, hint ...) waits for its answer. */
  asking: boolean
  /** The start on its way is a learn's search: its search.done ends the wait (a pick is a start of its own). */
  searching: boolean
}

export class RunGuard {
  private lessonId?: string
  private pending: boolean
  private carried = false
  /** carried: the learner's build came back on the new connection (its lesson.building passed), so its status may too. */
  private building = false
  private asking = false
  /** The start on its way is a learn's search (no build progress yet): its search.done ends the wait. */
  private searching = false
  /** The start on its way is a library.start with no build progress yet: "-> lesson.ready (or error)". */
  private library = false
  /** When the start on its way expires if no sign of life comes before (now() ms). */
  private deadline = 0

  /**
   * `armed`: a run that plays a lesson on purpose (DEMO=1's scripted run, or MIYAGI_REPLAY_ON_CONNECT=1 for
   * `npm run dev:all`'s mock replay): a lesson is on its way at start, after every dev.reset and on every connection,
   * and that wait never expires. `now`: the clock (freshStart.check.ts passes a fake one).
   */
  constructor(
    private readonly armed = false,
    private readonly now: () => number = Date.now
  ) {
    this.pending = armed
  }

  state(): GuardState {
    this.expire()
    return { lessonId: this.lessonId, pending: this.pending, carried: this.carried, asking: this.asking, searching: this.searching }
  }

  /** Every command the app sends to the engine (main/engine.ts send(), only once it really leaves). */
  command(cmd: Outgoing): void {
    this.expire()
    const kind = cmd.type === 'action' ? String((cmd.payload as { kind?: unknown })?.kind) : undefined
    if (START.has(cmd.type) || (kind !== undefined && START_ACTIONS.has(kind))) {
      this.wait(true)
      const mode = cmd.type === 'learn' ? String((cmd.payload as { mode?: unknown })?.mode) : ''
      this.searching = cmd.type === 'learn' && !BUILD_MODES.has(mode)
      this.library = cmd.type === 'library.start'
    } else if (cmd.type === 'dev.reset') {
      // The mock replays its scenario's 'connect' segment: armed runs (DEMO) take its lesson again.
      this.wait(this.armed)
      this.lessonId = undefined
      this.asking = false
    } else if (cmd.type === 'end_lesson' || kind === 'end_lesson') {
      // The learner stopped: a build or start still on its way is abandoned (lesson.ended clears the run's lesson).
      this.wait(false)
      this.asking = false
    } else if (kind === 'pick_another') {
      // Back to the search rows (the engine re-sends them and search.done): the next pick is a start of its own.
      if (this.pending && !this.carried) {
        this.searching = true
        this.touch(OPEN_TTL_MS)
      }
    } else if (kind !== undefined && ANSWERED.has(kind)) {
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
    this.expire()
    this.carried = this.pending
    this.building = false
    // The socket was down (asleep): the carried build gets time to show its progress on the new connection.
    if (this.pending) this.touch(OPEN_TTL_MS)
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
    this.expire()
    if (e.type === 'lesson.ready') {
      const p = e.payload as { lesson?: { id?: unknown }; replay?: unknown }
      const id = typeof p?.lesson?.id === 'string' && p.lesson.id ? p.lesson.id : undefined
      const same = !!id && id === this.lessonId
      // The engine runs a lesson this run didn't start (a respawned engine replaying another save): the run's lesson
      // is no longer there, so its steps, checks and cards stay out like at launch (lane reconnect).
      if (!same && !this.pending) return this.foreign()
      // A new connection's snapshot replay never answers a start sent on the old one.
      if (!same && this.carried && p?.replay === true) return this.foreign()
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
      const pass = !!this.lessonId || this.pending
      // (A failed build ends the wait: a later stale lesson.ready must not slip through.)
      if ((e.payload as { failed?: unknown })?.failed === true) this.wait(false)
      else if (this.pending) {
        this.searching = this.library = false
        this.touch(OPEN_TTL_MS)
        if (this.carried) this.building = true
      }
      return pass ? e : undefined
    }
    // This run's lesson: everything about it passes.
    if (this.lessonId) return e
    // A start of this run is on its way (sent on this connection), its lesson.ready not here yet: only its build
    // traffic passes, never the kept lesson's steps, checks, cards, video or spotlight.
    const opening = this.pending && !this.carried
    if (e.type === 'search.result' && opening) this.touch(OPEN_TTL_MS)
    if (e.type === 'search.done' && opening && this.searching) {
      // The search is over: nothing picked starts nothing; a pick (build_lesson / learn_url) is a start of its own.
      this.wait(false)
      return e
    }
    if (e.type === 'status') {
      const state = String((e.payload as { state?: unknown })?.state)
      if (WORKING_STATUS.has(state)) return opening || this.asking || (this.carried && this.building) ? e : undefined
      // A lesson this run doesn't have is running in the engine: the pill rests (a waiting press keeps its spinner).
      if (LESSON_STATUS.has(state)) return this.asking ? undefined : idle()
      this.asking = false
      return e
    }
    if (LESSON_EVENTS.has(e.type)) return undefined
    if (e.type === 'card') {
      const p = e.payload as { kind?: unknown; stepId?: unknown }
      // preflight (what the picked video is, Build / Pick another) follows this run's pick; at launch it is an old one.
      if (opening && p?.kind === 'preflight' && !p?.stepId) {
        this.touch(PICK_TTL_MS)
        return e
      }
      if (LESSON_CARDS.has(String(p?.kind)) || p?.stepId) return undefined
      this.asking = false
      return e
    }
    if (e.type === 'diagram') {
      if ((e.payload as { stepId?: unknown })?.stepId) return undefined
      this.asking = false
      return e
    }
    if (e.type === 'error') {
      this.asking = false
      // A library.start answered with an error starts nothing. (A learn_url's preflight error is followed by its build.)
      if (opening && this.library) this.wait(false)
    }
    if (e.type === 'blocker') {
      const p = e.payload as { kind?: unknown; clear?: unknown }
      return p?.clear === true || p?.kind === 'network' ? e : undefined
    }
    return e
  }

  /** A lesson.ready for a lesson this run didn't start: dropped, and the run's own lesson (if any) is gone from the engine. */
  private foreign(): undefined {
    this.lessonId = undefined
    return undefined
  }

  private wait(on: boolean): void {
    this.pending = on
    this.carried = false
    this.building = false
    this.searching = false
    this.library = false
    this.deadline = on ? this.now() + OPEN_TTL_MS : 0
  }

  /** A sign of life from the start on its way: it may wait `ms` more. */
  private touch(ms: number): void {
    this.deadline = Math.max(this.deadline, this.now() + ms)
  }

  /** A start on its way with no sign of life for too long is gone: the old lesson stays out for the rest of the run. */
  private expire(): void {
    if (this.pending && !this.armed && this.now() > this.deadline) this.wait(false)
  }
}
