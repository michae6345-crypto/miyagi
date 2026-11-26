/**
 * Feature: drawer (v2 lesson panel, BUILD-PLAN A1). What the panel shows besides core/lesson's step: the hint the
 * learner asked for, the latest "Not yet" diagnosis, the step that just passed (held until "Next step"), and when the
 * learner pressed Check. Imports core only (store.ts and route.ts import this, never the other way round).
 *
 *   hint      the latest card {kind:"hint"} for this step (Les-Hint), until its ✕, the step changes or the engine
 *             withdraws it (a dismissAfterMs of WITHDRAW_MS or less).
 *   notYet    the latest judge "Not yet" card (source "judge", verdict "not_done", or any card with missingLines), and
 *             `at` = when the latest diagnosis of any kind arrived (that card, an offtrack, a failed check). A diagnosis
 *             newer than the hint shows "Not yet"; a hint asked for after it shows the hint (view.ts).
 *   heldPass  step.passed (not skipped, not already): the engine starts the next step at once, but the panel keeps
 *             Les-Passed up until the learner presses "Next step" (decision 7) or starts on the next step.
 */
import { create } from 'zustand'
import type { Payload } from '../../../../../common/wire'
import { onMessage, onUi } from '../../../core/bus'
import { dismissAfter, useLesson, WITHDRAW_MS, type CheckItem, type Offtrack } from '../../../core/lesson'
import { usePressed } from '../../../core/shortcuts'

export type PanelCard = Payload<'card'>
export type HeldPass = { stepId: string; summary?: string; at: number }

/**
 * A Check press waiting for its answer (Nov 25: "Check again doesn't look like it checks"). Set on the press, cleared
 * only by the check's own answer (a card carrying checkedAt, a Not yet, step.passed / step.started, an error) or by
 * the engine's thinking ending after the press, so an unrelated card on the way (an off-track, a cleared advice) no
 * longer ends Checking early. `stuck`: no answer after CHECK_MAX_MS, the panel says so.
 */
export type CheckFlight = { at: number; sawThinking: boolean; stuck?: boolean }

type PanelState = {
  hint?: PanelCard & { at: number }
  /** n: how many check answers this step got (the second one says "Checked again"). */
  notYet: { card?: PanelCard; at: number; n?: number }
  heldPass?: HeldPass
  flight?: CheckFlight
  /** Stage only (?panel=checking): hold the Checking state with no press behind it. */
  stageChecking?: boolean
}

const empty: PanelState = { hint: undefined, notYet: { card: undefined, at: 0 }, heldPass: undefined, stageChecking: undefined, flight: undefined }
export const usePanel = create<PanelState>(() => ({ ...empty }))
const set = usePanel.setState
const get = usePanel.getState

// ---- what the panel can render (route.ts asks the same questions) ---------------------------------------------

/** A hint the panel shows in place: kind "hint" without a diff or output preview (those keep the island card). */
export function isHintCard(c: PanelCard | undefined): boolean {
  return !!c && c.kind === 'hint' && !c.diff && !c.output
}

/**
 * A check's answer on the step: a "Not yet" (verdict not_done, from the judge or Check's own card since Nov 25), any
 * card listing the step's missing lines, or "Couldn't check" (checkIssue: Screen Recording off, the checks failed...).
 */
export function isNotYetCard(c: PanelCard | undefined): boolean {
  if (!c || c.diff || c.output) return false
  return c.verdict === 'not_done' || !!c.checkIssue || (Array.isArray(c.missingLines) && c.missingLines.length > 0)
}

/** The card is about the step on screen (no stepId = the current step). */
export function forCurrentStep(c: { stepId?: string } | undefined): boolean {
  const cur = useLesson.getState().stepId
  return !!c && (!c.stepId || c.stepId === cur)
}

// ---- which view holds (view.ts draws it; drawer/store.ts's Esc asks hintShown) -----------------------------------

/** A press of Check shows Checking at once, before the engine's status thinking arrives (never look dead). */
export const PRESS_GRACE_MS = 1500

/** No answer to a Check after this long: Checking ends and the panel says there was none (never a silent spinner). */
export const CHECK_MAX_MS = 45_000
/**
 * The engine starts thinking on a real check at once. A press it answers without thinking (the Demo stage's "passes
 * nothing", its quiet return under the resume card, a lesson.paused reply) sends no checkedAt either: Checking ends
 * after this long with no thinking, never a 45 s spinner.
 */
export const NO_THINKING_MS = 3000

/** The panel says Checking right now: a press still waiting for its answer (checkFlight), or the stage's hold. */
export function checkingNow(): boolean {
  const s = get()
  return !!s.stageChecking || (!!s.flight && !s.flight.stuck)
}

type LessonNow = ReturnType<typeof useLesson.getState>

export type PanelFacts = {
  /** A passed step is held on screen (heldPass on a step the lesson knows). */
  holding: boolean
  /** Les-Passed holds: the held pass, or the step on screen passed (not skipped). */
  passed: boolean
  /** The judge "Not yet" card for this step, the offtrack for this step, the failed checks. */
  card?: PanelCard
  off?: Offtrack
  fails: CheckItem[]
  /** The hint for this step. */
  hint?: PanelCard & { at: number }
  /** A diagnosis for this step newer than the hint (or with no hint): Not yet wins over the hint. */
  notyetFresh: boolean
}

/** What the view rule (view.ts pickView) reads, pure. usePanelModel and hintShown share it so they never disagree. */
export function panelFacts(l: Pick<LessonNow, 'stepId' | 'steps' | 'passed' | 'skipped' | 'checks' | 'offtrack'>, p: Pick<PanelState, 'hint' | 'notYet' | 'heldPass'>): PanelFacts {
  const held = p.heldPass
  const holding = !!held && l.steps.some((x) => x.id === held.stepId)
  const donePassed = !!l.stepId && l.passed.includes(l.stepId) && !l.skipped.includes(l.stepId)
  const card = p.notYet.card && isNotYetCard(p.notYet.card) && forCurrentStep(p.notYet.card) ? p.notYet.card : undefined
  const off = l.offtrack && l.offtrack.stepId === l.stepId ? l.offtrack : undefined
  const fails = l.checks.filter((c) => c.status === 'fail')
  const diagnosed = !!card || !!off || fails.length > 0
  const hint = p.hint && forCurrentStep(p.hint) ? p.hint : undefined
  return { holding, passed: holding || donePassed, card, off, fails, hint, notyetFresh: diagnosed && (!hint || p.notYet.at >= hint.at) }
}

/**
 * The panel's hint is the view on screen (not hidden under Passed, Checking or a newer Not yet). Esc closes it only
 * then; a hidden hint is not "something open".
 */
export function hintShown(): boolean {
  const f = panelFacts(useLesson.getState(), get())
  return !!f.hint && !f.passed && !f.notyetFresh && !checkingNow()
}

// ---- the Check in flight ------------------------------------------------------------------------------------------

type Timer = ReturnType<typeof setTimeout>
const timers: { hint?: Timer; notYet?: Timer; flight?: Timer; quiet?: Timer } = {}

/** The press's answer came (or the step moved on): Checking ends. */
export function landFlight(): void {
  clearTimeout(timers.flight)
  clearTimeout(timers.quiet)
  if (get().flight) set({ flight: undefined })
}

/** A Check press (any surface: the panel, a card's Check again, the player, Enter): Checking holds until its answer. */
export function startFlight(at = Date.now()): void {
  clearTimeout(timers.flight)
  set({ flight: { at, sawThinking: false } }) // only thinking seen after the press counts
  timers.flight = setTimeout(() => {
    const f = get().flight
    if (f && f.at === at) set({ flight: { ...f, stuck: true } })
  }, CHECK_MAX_MS)
  clearTimeout(timers.quiet)
  timers.quiet = setTimeout(() => {
    const f = get().flight
    if (f && f.at === at && !f.sawThinking) landFlight() // answered without thinking (or not at all): no spinner
  }, NO_THINKING_MS)
}

usePressed.subscribe((p, prev) => {
  if (p.kind === 'check_step' && (p.at !== prev.at || prev.kind !== 'check_step')) startFlight(p.at)
})

/** The engine's thinking after the press ended (the check set its verdict state): whatever it answered, it answered. */
export function flightStatus(state: string | undefined): void {
  const f = get().flight
  if (!f || f.stuck) return
  if (state === 'thinking') {
    if (!f.sawThinking) set({ flight: { ...f, sawThinking: true } })
    return
  }
  if (f.sawThinking) landFlight()
}
onMessage('status', (p) => flightStatus(p.state))
onMessage('error', () => landFlight())
onMessage('lesson.paused', () => landFlight()) // VS Code closed: the engine answers a Check with the paused surface

// ---- engine events ----------------------------------------------------------------------------------------------

onMessage('card', (c) => {
  if (c.checkedAt !== undefined && forCurrentStep(c)) landFlight() // this press's answer (Not yet / Couldn't check)
  const after = dismissAfter(c)
  const withdrawn = after !== undefined && after <= WITHDRAW_MS
  if (isHintCard(c)) {
    clearTimeout(timers.hint)
    if (withdrawn) return set({ hint: undefined })
    const hint = { ...c, at: Date.now() }
    set({ hint })
    if (after !== undefined) timers.hint = setTimeout(() => get().hint === hint && set({ hint: undefined }), after)
    return
  }
  if (isNotYetCard(c)) {
    clearTimeout(timers.notYet)
    if (withdrawn) return set((s) => ({ notYet: { ...s.notYet, card: undefined } }))
    landFlight()
    const n = c.checkedAt !== undefined ? (get().notYet.n ?? 0) + 1 : get().notYet.n
    set({ notYet: { card: c, at: Date.now(), n } })
    if (after !== undefined) timers.notYet = setTimeout(() => get().notYet.card === c && set((s) => ({ notYet: { ...s.notYet, card: undefined } })), after)
  }
})

onMessage('offtrack', (o) => {
  const after = dismissAfter(o)
  if (after !== undefined && after <= WITHDRAW_MS) return
  set((s) => ({ notYet: { ...s.notYet, at: Date.now() } }))
  // Already on the next step while the passed one was held: let the panel follow the learner.
  if (get().heldPass && o.stepId !== get().heldPass?.stepId) set({ heldPass: undefined })
})

onMessage('check.updated', (p) => {
  if (p.status === 'fail') set((s) => ({ notYet: { ...s.notYet, at: Date.now() } }))
  const held = get().heldPass
  if (held && p.stepId !== held.stepId && (p.status === 'fail' || p.status === 'pass')) set({ heldPass: undefined })
})

onMessage('step.passed', (p) => {
  clearTimeout(timers.hint)
  clearTimeout(timers.notYet)
  landFlight()
  const already = (p as typeof p & { already?: boolean }).already
  set({
    hint: undefined,
    notYet: { card: undefined, at: 0 },
    stageChecking: undefined,
    heldPass: p.skipped || already ? undefined : { stepId: p.stepId, summary: p.summary?.trim() || undefined, at: Date.now() }
  })
})

onMessage('step.started', (p) => {
  clearTimeout(timers.hint)
  clearTimeout(timers.notYet)
  landFlight()
  // The engine starts the next step right after step.passed: the held pass stays (Les-Passed until "Next step").
  // Back to an earlier step (or the same one again) ends it.
  const held = get().heldPass
  const steps = useLesson.getState().steps
  const pos = (id: string): number => steps.findIndex((x) => x.id === id)
  const keep = !!held && pos(p.stepId) > pos(held.stepId)
  set({ hint: undefined, notYet: { card: undefined, at: 0 }, stageChecking: undefined, heldPass: keep ? held : undefined })
})

const clearAll = (): void => {
  clearTimeout(timers.hint)
  clearTimeout(timers.notYet)
  clearTimeout(timers.flight)
  clearTimeout(timers.quiet)
  set({ ...empty, notYet: { card: undefined, at: 0 } })
}
onMessage('lesson.ready', clearAll)
onMessage('lesson.ended', (p) => {
  if ((p.reason as string | undefined) === 'interrupted') return
  clearAll()
})
onUi('reset', clearAll)

// The learner pressed an action (Hint, Explain, Show me...) while the passed step was held: they're on the next step.
usePressed.subscribe((s, prev) => {
  if (s.kind && s.at !== prev.at && get().heldPass) set({ heldPass: undefined })
})

// ---- the learner's controls -------------------------------------------------------------------------------------

/** "Next step" (Les-Passed): show the step the engine already started. */
export const releasePass = (): void => set({ heldPass: undefined })
/** The hint's ✕: close it here (the panel's own surface; the island never showed it). */
export const closeHint = (): void => {
  clearTimeout(timers.hint)
  set({ hint: undefined })
}
/** Stage only: hold Checking (see stage.ts). */
export const setStageChecking = (on: boolean): void => set({ stageChecking: on || undefined })
