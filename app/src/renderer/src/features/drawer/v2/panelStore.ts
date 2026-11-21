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
import { dismissAfter, useLesson, WITHDRAW_MS } from '../../../core/lesson'
import { usePressed } from '../../../core/shortcuts'

export type PanelCard = Payload<'card'>
export type HeldPass = { stepId: string; summary?: string; at: number }

type PanelState = {
  hint?: PanelCard & { at: number }
  notYet: { card?: PanelCard; at: number }
  heldPass?: HeldPass
  /** Stage only (?panel=checking): hold the Checking state with no press behind it. */
  stageChecking?: boolean
}

const empty: PanelState = { hint: undefined, notYet: { card: undefined, at: 0 }, heldPass: undefined, stageChecking: undefined }
export const usePanel = create<PanelState>(() => ({ ...empty }))
const set = usePanel.setState
const get = usePanel.getState

// ---- what the panel can render (route.ts asks the same questions) ---------------------------------------------

/** A hint the panel shows in place: kind "hint" without a diff or output preview (those keep the island card). */
export function isHintCard(c: PanelCard | undefined): boolean {
  return !!c && c.kind === 'hint' && !c.diff && !c.output
}

/** A "Not yet" verdict on the step: the judge's not_done card, or any card listing the step's missing lines. */
export function isNotYetCard(c: PanelCard | undefined): boolean {
  if (!c || c.diff || c.output) return false
  return (c.source === 'judge' && c.verdict === 'not_done') || (Array.isArray(c.missingLines) && c.missingLines.length > 0)
}

/** The card is about the step on screen (no stepId = the current step). */
export function forCurrentStep(c: { stepId?: string } | undefined): boolean {
  const cur = useLesson.getState().stepId
  return !!c && (!c.stepId || c.stepId === cur)
}

// ---- engine events ----------------------------------------------------------------------------------------------

const timers: { hint?: ReturnType<typeof setTimeout>; notYet?: ReturnType<typeof setTimeout> } = {}

onMessage('card', (c) => {
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
    set({ notYet: { card: c, at: Date.now() } })
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
