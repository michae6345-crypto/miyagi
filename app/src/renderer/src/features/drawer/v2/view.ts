/**
 * Feature: drawer (v2, A1). Which state the lesson panel shows, and what it shows in it.
 *
 * View priority (BUILD-PLAN A1): passed > checking > notyet > hint > working.
 *   passed    the step on screen passed (or the one held after step.passed, until "Next step")         Les-Passed
 *   checking  the learner pressed Check and the engine is checking                                     Les-Checking
 *   notyet    a diagnosis for this step (judge "Not yet" card, offtrack, a failed check) newer than
 *             any hint the learner asked for after it                                                Les-NotYet
 *   hint      a hint for this step                                                                     Les-Hint
 *   working   otherwise                                                                                Les-Working
 */
import { useEffect, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { MissingLine, StepKind } from '../../../../../../../shared/contracts/events'
import { useLesson, useThinking } from '../../../core/lesson'
import { usePressed } from '../../../core/shortcuts'
import { useStepDetail } from '../plan'
import { forCurrentStep, isNotYetCard, usePanel, type PanelCard } from './panelStore'
import { panelRenders } from './route'

export type PanelView = 'passed' | 'checking' | 'notyet' | 'hint' | 'working'

/** The one rule, pure: the highest state that holds wins. */
export function pickView(f: { passed: boolean; checking: boolean; notyet: boolean; hint: boolean }): PanelView {
  if (f.passed) return 'passed'
  if (f.checking) return 'checking'
  if (f.notyet) return 'notyet'
  if (f.hint) return 'hint'
  return 'working'
}

/** A press of Check shows Checking at once, before the engine's status thinking arrives (never look dead). */
const PRESS_GRACE_MS = 1500

function useChecking(): boolean {
  const thinking = useThinking()
  const press = usePressed(useShallow((p) => ({ kind: p.kind, at: p.at })))
  const stage = usePanel((s) => !!s.stageChecking)
  const pressed = press.kind === 'check_step'
  const [fresh, setFresh] = useState(false)
  useEffect(() => {
    if (!pressed) return setFresh(false)
    const left = PRESS_GRACE_MS - (Date.now() - press.at)
    if (left <= 0) return setFresh(false)
    setFresh(true)
    const id = setTimeout(() => setFresh(false), left)
    return () => clearTimeout(id)
  }, [pressed, press.at])
  return stage || (pressed && (thinking || fresh))
}

export type NotYetInfo = {
  /** The first line is the finding (white), the rest say more (muted). Backticks mark code. */
  lines: string[]
  missing?: MissingLine[]
  fixCaption?: string
}

export type HintInfo = { lines: string[]; n?: number; of?: number }

export type PanelStep = {
  id?: string
  /** 0-based position, -1 before the first step. */
  index: number
  total: number
  title: string
  instructions: string
  kind?: StepKind
  code?: string
  where?: string
  then?: string
  video?: { start: number; end: number }
}

export type PanelModel = {
  view: PanelView
  lessonTitle: string
  step: PanelStep
  passed: number[]
  skipped: number[]
  notYet?: NotYetInfo
  hint?: HintInfo
  /** Les-Passed. */
  summary?: string
  upNext?: { index: number; title: string; what?: string }
  /** The engine already started the next step ("Next step" shows it). */
  canNext: boolean
  /** The lesson's last step passed: the completion card takes over, no "Next step". */
  last: boolean
  /** status.detail while checking ("Reading `x_train` in your kernel"). */
  checkingCaption?: string
}

const splitLines = (t: string | undefined): string[] =>
  (t ?? '')
    .split(/\n+/)
    .map((x) => x.trim())
    .filter(Boolean)

const GENERIC = /^(not yet|hint)\.?$/i

function notYetFrom(card: PanelCard | undefined, off: { title: string; body: string } | undefined, fails: { label: string; detail?: string }[]): NotYetInfo {
  if (card) {
    const title = card.title?.trim()
    const lines = [...(title && !GENERIC.test(title) ? [title] : []), ...splitLines(card.body)]
    return { lines, missing: card.missingLines?.length ? card.missingLines : undefined, fixCaption: card.fixCaption?.trim() || undefined }
  }
  if (off) return { lines: [off.title, ...splitLines(off.body)].filter(Boolean) }
  const f = fails[0]
  return { lines: f ? [f.label, ...(f.detail ? [f.detail] : [])] : [] }
}

function hintFrom(card: PanelCard): HintInfo {
  const body = splitLines(card.body)
  const title = card.title?.trim()
  const lines = body.length ? body : title && !GENERIC.test(title) ? [title] : []
  if (card.guidingQuestion?.trim()) lines.push(card.guidingQuestion.trim())
  return { lines, n: card.hintStep?.n, of: card.hintStep?.of }
}

export function usePanelModel(): PanelModel {
  const held = usePanel((s) => s.heldPass)
  const hintCard = usePanel((s) => s.hint)
  const notYet = usePanel((s) => s.notYet)
  const detail = useStepDetail((s) => s.detail)
  const checking = useChecking()
  const l = useLesson(
    useShallow((s) => ({
      lessonTitle: s.lesson?.title ?? '',
      steps: s.steps,
      outlineCount: s.lesson?.outline?.count ?? 0,
      outline: s.lesson?.outline?.steps,
      stepId: s.stepId,
      title: s.stepTitle,
      instructions: s.instructions,
      step: s.step,
      stepVideo: s.stepVideo,
      passedIds: s.passed,
      skippedIds: s.skipped,
      checks: s.checks,
      offtrack: s.offtrack,
      complete: s.complete,
      detail: s.statusDetail,
      lastPassed: s.lastPassed
    }))
  )
  const pos = (id: string | undefined): number => (id ? l.steps.findIndex((x) => x.id === id) : -1)
  const total = Math.max(l.steps.length, l.outlineCount)
  const heldIndex = held ? pos(held.stepId) : -1
  const holding = !!held && heldIndex >= 0
  // While a pass is held, the panel stays on that step (its title, its green dot), whatever the engine started since.
  const shownId = holding ? held!.stepId : l.stepId
  const index = pos(shownId)
  const row = index >= 0 ? l.steps[index] : undefined
  const st = l.step && l.step.stepId === shownId ? l.step : undefined
  const det = detail && detail.stepId === shownId ? detail : undefined
  const step: PanelStep = {
    id: shownId,
    index,
    total,
    title: (holding ? row?.title : l.title) || row?.title || '',
    instructions: (holding ? st?.instructions : l.instructions) || '',
    kind: st?.kind ?? det?.kind ?? row?.kind,
    code: st?.code?.trim() ? st.code.replace(/^\s*\n/, '').replace(/\s+$/, '') : det?.code,
    where: st?.where?.trim() || undefined,
    then: st?.then?.trim() || undefined,
    video: (holding ? row?.video : l.stepVideo) ?? undefined
  }
  const passed = l.passedIds.filter((id) => !l.skippedIds.includes(id)).map(pos).filter((i) => i >= 0)
  const skipped = l.skippedIds.map(pos).filter((i) => i >= 0)
  const donePassed = !!l.stepId && l.passedIds.includes(l.stepId) && !l.skippedIds.includes(l.stepId)

  // Not yet: the freshest diagnosis for the step on screen.
  const card = notYet.card && isNotYetCard(notYet.card) && forCurrentStep(notYet.card) ? notYet.card : undefined
  const off = l.offtrack && l.offtrack.stepId === l.stepId ? l.offtrack : undefined
  const fails = l.checks.filter((c) => c.status === 'fail')
  const diagnosed = !!card || !!off || fails.length > 0
  const hint = hintCard && forCurrentStep(hintCard) ? hintCard : undefined
  const notyetFresh = diagnosed && (!hint || notYet.at >= hint.at)
  // An off-track with a fix stays on the island card: the panel says only "Not yet" and its title.
  const offInfo = off && !card ? (panelRenders({ kind: 'offtrack', ...off }) ? off : { title: off.title, body: '' }) : undefined

  const view = pickView({ passed: holding || donePassed, checking: !holding && checking, notyet: notyetFresh, hint: !!hint })

  const nextRow = index >= 0 ? l.steps[index + 1] : undefined
  const outlineNext = !nextRow && index >= 0 ? l.outline?.find((o) => o.index === (row?.index ?? index) + 1) : undefined
  const upNext = nextRow ? { index: index + 1, title: nextRow.title, what: nextRow.what?.trim() || undefined } : outlineNext ? { index: index + 1, title: outlineNext.title } : undefined
  const last = index >= 0 && total > 0 && index === total - 1 && l.complete
  const summary = holding ? held!.summary : l.lastPassed && l.lastPassed.stepId === shownId ? l.lastPassed.summary : undefined

  return {
    view,
    lessonTitle: l.lessonTitle,
    step,
    passed,
    skipped,
    notYet: view === 'notyet' ? notYetFrom(card, offInfo, fails) : undefined,
    hint: view === 'hint' && hint ? hintFrom(hint) : undefined,
    summary: summary?.trim() || undefined,
    upNext: last ? undefined : upNext,
    canNext: holding && !!l.stepId && l.stepId !== held!.stepId,
    last,
    checkingCaption: l.detail
  }
}
