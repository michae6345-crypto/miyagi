/**
 * Feature: cards. Which coach card is showing, plus the live metric series behind the curve.
 * The off-track payload itself lives in core/lesson; core doesn't keep metrics, so they live here.
 */
import { create } from 'zustand'
import { cmd, type Payload } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'
import { seekVideo, useLesson, type CheckItem } from '../../core/lesson'

export type Point = { step: number; value: number }
/** `seq` = event order of its first point (compared with the off-track's), `at` = when its last point arrived (ms). */
export type Run = { runId: string; points: Point[]; seq: number; at: number }
/** One metric (any name the engine sends): the current run, and the run before it (e.g. before the fix). */
export type Series = { run: Run; before?: Run }

/** runId the engine may use for the tutorial's reference curve (open question 4 in FRONTEND-HANDOFF). */
export const TUTORIAL_RUN = 'tutorial'
/** Points kept per run. Past this, every other point is dropped (the shape survives, memory doesn't grow). */
const MAX_POINTS = 400
/** How long "Back on track" stays up. */
export const SUCCESS_MS = 4800

type CardsState = {
  /** The off-track card is open (it can be dismissed; hovering the pill reopens it). */
  offtrackOpen: boolean
  /** Apply fix was pressed: the off-track card collapses to a compact "applying the fix" card until the step passes. */
  fixing: boolean
  /** The current step went off-track at some point → show "Back on track" when it passes. */
  recovered: boolean
  /** An explain card or a diagram opened on top of the off-track card: closing it brings the off-track card back. */
  resume: boolean
  /** When the latest off-track fired: a run that starts after it is "after the fix". */
  offtrackSeq?: number
  /** "Back on track". `since` = the off-track's event order (so the curve can split before/after). */
  success?: { index: number; total: number; summary?: string; checks: CheckItem[]; at: number; since?: number }
  card?: Payload<'card'>
  /** Live `metric` events, by metric name. */
  metrics: Record<string, Series>
  /** The tutorial's reference curve, if the engine streams it as runId "tutorial". */
  tutorial: Record<string, Point[]>
}

const blank: CardsState = { offtrackOpen: false, fixing: false, recovered: false, resume: false, offtrackSeq: undefined, success: undefined, card: undefined, metrics: {}, tutorial: {} }
export const useCards = create<CardsState>(() => ({ ...blank }))
const set = useCards.setState
const get = useCards.getState

let successTimer: ReturnType<typeof setTimeout> | undefined

/** Thin a run that grew past MAX_POINTS: keep every other point, always keep the newest. */
function thin(points: Point[]): Point[] {
  if (points.length <= MAX_POINTS) return points
  return points.filter((_, i) => i % 2 === 0 || i === points.length - 1)
}

function append(run: Run, p: Point): Run {
  const last = run.points[run.points.length - 1]
  const points = last && last.step === p.step ? [...run.points.slice(0, -1), p] : thin([...run.points, p])
  return { ...run, points, at: Date.now() }
}

/** Event order for metric runs and off-tracks: a run is "after the fix" if it started after the off-track. */
let seq = 0
const newRun = (runId: string, p: Point): Run => ({ runId, points: [p], seq: ++seq, at: Date.now() })

/** A card button → `action {kind}`. Apply fix collapses the off-track card into the "applying the fix" view. */
export function act(kind: 'show_me' | 'explain' | 'apply_fix' | 'hint'): void {
  bridge.send(cmd('action', { kind }))
  if (kind === 'apply_fix') set({ fixing: true, offtrackOpen: true })
}

/** Every button kind an engine card can carry (card.actions). */
export type CardAction = NonNullable<Payload<'card'>['actions']>[number]

/**
 * A button on an engine card → `action {kind}` (install: text = the setup item's tool id).
 * The card closes on click; the engine answers with the next card or event.
 */
export function cardAct(kind: CardAction, text?: string): void {
  bridge.send(cmd('action', text === undefined ? { kind } : { kind, text }))
  if (kind !== 'install') set({ card: undefined })
}

/** A card's video jump: core seekVideo sets the intent in every window; the player follows core/lesson.video. */
export function jumpTo(t: number): void {
  seekVideo(t, true)
  closeTop()
}

/** Close the card on top; if it opened over the off-track card, that card comes back. */
function closeTop(): void {
  const back = get().resume && !!useLesson.getState().offtrack
  set({ card: undefined, success: undefined, resume: false, offtrackOpen: back })
}
const over = (): boolean => get().offtrackOpen || get().resume

onUi('reset', () => {
  clearTimeout(successTimer)
  set({ ...blank })
})
onUi('dismiss', closeTop)
onMessage('lesson.ready', () => set({ ...blank }))
// A card with buttons survives step.started when it's for this step or for no step
// (e.g. "Open VS Code?" or "Continue where you left off?"); plain cards are cleared as before.
onMessage('step.started', (p) => {
  const c = get().card
  const keep = !!c?.actions?.length && (!c.stepId || c.stepId === p.stepId)
  set({ offtrackOpen: false, fixing: false, recovered: false, resume: false, offtrackSeq: undefined, card: keep ? c : undefined })
})
onMessage('offtrack', () => set({ offtrackOpen: true, fixing: false, recovered: true, resume: false, offtrackSeq: ++seq, card: undefined, success: undefined }))
// "Apply this fix?" (a diff to confirm) replaces the "Waiting for the fix" view, so `fixing` ends here.
onMessage('card', (p) => set({ card: p, resume: over(), offtrackOpen: false, ...(p.diff ? { fixing: false } : {}) }))
onMessage('diagram', () => set({ card: undefined, resume: over(), offtrackOpen: false }))
onMessage('step.passed', (p) => {
  const { recovered, offtrackSeq } = get()
  set({ offtrackOpen: false, fixing: false, resume: false })
  if (!recovered) return
  const lesson = useLesson.getState()
  const index = lesson.steps.findIndex((x) => x.id === p.stepId)
  const summary = (p as typeof p & { summary?: string }).summary
  set({ success: { index, total: lesson.steps.length, summary, checks: lesson.checks, at: Date.now(), since: offtrackSeq } })
  clearTimeout(successTimer)
  successTimer = setTimeout(() => set({ success: undefined }), SUCCESS_MS)
})

/**
 * metric {runId, step, name, value}. A new run starts when the runId changes or the step goes
 * backwards (the learner re-ran the script); the old run is kept as `before` for "now vs before fix".
 */
onMessage('metric', (p) => {
  if (!Number.isFinite(p.step) || !Number.isFinite(p.value)) return
  const pt: Point = { step: p.step, value: p.value }
  const s = get()

  if (p.runId === TUTORIAL_RUN) {
    const prev = s.tutorial[p.name] ?? []
    set({ tutorial: { ...s.tutorial, [p.name]: thin([...prev.filter((x) => x.step !== pt.step), pt].sort((a, b) => a.step - b.step)) } })
    return
  }

  const cur = s.metrics[p.name]
  let next: Series
  if (!cur) next = { run: newRun(p.runId, pt) }
  else if (cur.before && p.runId === cur.before.runId && p.runId !== cur.run.runId) next = { ...cur, before: append(cur.before, pt) } // late point from the old run
  else {
    const last = cur.run.points[cur.run.points.length - 1]
    const restart = p.runId !== cur.run.runId || (last !== undefined && p.step < last.step)
    next = restart ? { run: newRun(p.runId, pt), before: cur.run } : { ...cur, run: append(cur.run, pt) }
  }
  set({ metrics: { ...s.metrics, [p.name]: next } })
})

/**
 * The series a card should draw: the metric named `label` (the off-track curve's label) if it
 * streams, else the most recently updated one. `after` = the run that started after the off-track
 * (the re-run), if any; `before` = the run it replaced (or the current run, until the re-run starts).
 */
export function useSeries(label?: string, since?: number): { name?: string; series?: Series; tutorial?: Point[]; after?: Run; before?: Run } {
  const metrics = useCards((c) => c.metrics)
  const tutorial = useCards((c) => c.tutorial)
  const offtrackSeq = useCards((c) => since ?? c.offtrackSeq)
  const name = label && metrics[label] ? label : latest(metrics)
  const series = name ? metrics[name] : undefined
  const after = series && offtrackSeq !== undefined && series.run.seq > offtrackSeq ? series.run : undefined
  const before = after ? series?.before : series?.run
  return { name, series, tutorial: name ? tutorial[name] : undefined, after, before }
}

function latest(metrics: Record<string, Series>): string | undefined {
  let best: string | undefined
  for (const [k, v] of Object.entries(metrics)) if (!best || v.run.at > metrics[best].run.at) best = k
  return best
}
