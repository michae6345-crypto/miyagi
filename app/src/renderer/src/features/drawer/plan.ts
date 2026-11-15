/**
 * Feature: drawer. The current step's "what to type" (Michael, Sat evening: "the instructions aren't clear and
 * don't show what to type"): step.started's kind, why, concepts and full code. core/lesson keeps the rest of a
 * "Just teach me" lesson (lesson.overview, lesson.primer, steps[].kind / what), so the drawer reads those there.
 *
 * Every field is optional (an older engine, a video lesson); nothing here is required for the drawer to work.
 *
 * Also each step's status in the plan (done / skipped / current / locked), the one rule the rows, "N of M done", the
 * header and the concept panel's step rail share.
 */
import { create } from 'zustand'
import { useShallow } from 'zustand/react/shallow'
import type { PrimerItem, StepKind, StepSummary } from '../../../../../../shared/contracts/events'
import { bridge, registerWebHandler } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'

/** The current step (step.started): what to type or run, in full, and why. */
export type StepDetail = { stepId: string; kind?: StepKind; why?: string; concepts: string[]; code?: string }

export const useStepDetail = create<{ detail?: StepDetail }>(() => ({}))
const set = useStepDetail.setState
/**
 * Every step's detail seen this lesson. Back re-starts an earlier step (a new step.started): a field that one leaves
 * out keeps the value the step had the first time, so the step gone back to still shows its code.
 */
const seen = new Map<string, StepDetail>()

const KINDS: readonly StepKind[] = ['code', 'run', 'read']

function text(v: string | undefined): string | undefined {
  return v?.trim() || undefined
}

/** Code keeps its indentation: only leading blank lines and trailing space go. */
function code(v: string | undefined): string | undefined {
  return v?.trim() ? v.replace(/^\s*\n/, '').replace(/\s+$/, '') : undefined
}

onMessage('step.started', (p) => {
  const prev = seen.get(p.stepId)
  const concepts = (p.concepts ?? []).map((c) => c.trim()).filter(Boolean)
  const detail: StepDetail = {
    stepId: p.stepId,
    kind: (p.kind && KINDS.includes(p.kind) ? p.kind : undefined) ?? prev?.kind,
    why: text(p.why) ?? prev?.why,
    concepts: concepts.length ? concepts : (prev?.concepts ?? []),
    code: code(p.code) ?? prev?.code
  }
  seen.set(p.stepId, detail)
  set({ detail })
})
const clearDetail = (): void => {
  seen.clear()
  set({ detail: undefined })
}
onMessage('lesson.ready', clearDetail)
onUi('reset', clearDetail)

// ---------------------------------------------------------------------------
// Step status
// ---------------------------------------------------------------------------

/** skipped: the learner pressed Skip. Finished but not passed: never green, never counted in "N of M done". */
export type StepStatus = 'done' | 'skipped' | 'current' | 'locked'
/** How a step's latest attempt ended (its step.passed). */
type Outcome = 'passed' | 'skipped'

/**
 * core/lesson's passed / skipped lists only ever grow, so after Back the step gone back to is still in them (Michael's
 * desktop test 3, Sun 1:25 AM: it showed "skipped", collapsed, with no code, and "2 of 6 done"). So the drawer keeps
 *  - last: each step's latest step.passed (a skipped step the learner went back to and passed is done, not skipped);
 *  - ended: the step whose step.passed came after its own step.started, i.e. the current step finished THIS attempt
 *    (its tick, the lesson's last step); any step.started opens a new attempt.
 */
type Outcomes = { last: Record<string, Outcome>; ended?: string }
const useOutcomes = create<Outcomes>(() => ({ last: {} }))

onMessage('step.started', () => useOutcomes.setState({ ended: undefined }))
onMessage('step.passed', (p) => useOutcomes.setState((s) => ({ last: { ...s.last, [p.stepId]: p.skipped ? 'skipped' : 'passed' }, ended: p.stepId })))
onMessage('lesson.ready', () => useOutcomes.setState({ last: {}, ended: undefined }))
onUi('reset', () => useOutcomes.setState({ last: {}, ended: undefined }))

type StatusInput = { steps: StepSummary[]; stepId?: string; passed: string[]; skipped: string[] }

/**
 * Every step's status, in plan order. The current step is current (expanded, with its code and checks) until it
 * passes or is skipped in this attempt, whatever core/lesson's lists say. Any step: how its latest attempt ended,
 * else core's lists (a step before the current one counts as done), else locked.
 */
export function stepStatuses(x: StatusInput, o: Outcomes): StepStatus[] {
  const cur = x.steps.findIndex((s) => s.id === x.stepId)
  return x.steps.map((s, i) => {
    if (s.id === x.stepId && o.ended !== s.id) return 'current'
    const last = o.last[s.id]
    if (last) return last === 'skipped' ? 'skipped' : 'done'
    if (x.skipped.includes(s.id)) return 'skipped'
    return x.passed.includes(s.id) || (cur >= 0 && i < cur) ? 'done' : 'locked'
  })
}

/**
 * The current step, when it just passed (or was skipped) and the engine's next step.started hasn't come yet: the gap
 * where the pill already runs ahead to the next step (Michael's test 10, item 9). The drawer holds that step open and
 * names the next one in its header, so nothing collapses and re-grows at a step change.
 */
export function useJustEnded(): string | undefined {
  const ended = useOutcomes((o) => o.ended)
  return useLesson((s) => (ended && ended === s.stepId ? ended : undefined))
}

/** stepStatuses for the lesson in core/lesson. */
export function useStepStatuses(): StepStatus[] {
  const o = useOutcomes()
  return useLesson(useShallow((s) => stepStatuses(s, o)))
}

// ---------------------------------------------------------------------------
// How big the plan is (review A14)
// ---------------------------------------------------------------------------

/** One row of the outline: its step's StepSummary.index once that step arrives, and about how long it takes. */
export type OutlineRow = { index: number; estMinutes?: number }
/** lesson.ready's lesson.outline (engine E23): the number of steps the lesson ends with, sent before they all arrive. */
export type Outline = { count: number; rows: OutlineRow[] }

/**
 * The outline, when the engine sent one. It is an additive field this branch's contract doesn't have yet, so it is
 * read defensively from core/lesson's lesson (core keeps lesson.ready's lesson object whole).
 */
export function lessonOutline(lesson: unknown): Outline | undefined {
  const o = (lesson as { outline?: { count?: unknown; steps?: unknown } } | undefined)?.outline
  if (!o || typeof o.count !== 'number' || !Number.isFinite(o.count) || o.count < 1) return undefined
  const rows: OutlineRow[] = []
  for (const r of Array.isArray(o.steps) ? (o.steps as Array<{ index?: unknown; estMinutes?: unknown }>) : []) {
    if (typeof r?.index !== 'number') continue
    rows.push({ index: r.index, estMinutes: typeof r.estMinutes === 'number' ? r.estMinutes : undefined })
  }
  return { count: Math.round(o.count), rows }
}

/**
 * How many steps the lesson has, or undefined while that isn't known (Michael's review A14: "1 steps" and "Step 1 of 1"
 * next to "More steps coming" while a lesson streamed in). Complete: the step list. Still building: the outline's
 * count when the engine sent one, else unknown, and nothing says "of N" until it is.
 */
export function planTotal(steps: number, complete: boolean, outline?: Outline): number | undefined {
  if (complete) return steps
  return outline ? Math.max(outline.count, steps) : undefined
}

/** "1 step", "3 steps". */
export function count(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`
}

/** A step's concept names a primer item by id or by title (any case). */
export function findPrimer(primer: PrimerItem[], concept: string): PrimerItem | undefined {
  const c = concept.trim().toLowerCase()
  return primer.find((p) => p.id.toLowerCase() === c) ?? primer.find((p) => p.title.toLowerCase() === c)
}

/**
 * Copy to the clipboard. The overlay window can't take focus (focusable: false), and Chromium refuses both
 * navigator.clipboard and execCommand('copy') in an unfocused document, so Electron copies in main
 * (src/main/features/drawer.ts, Electron's clipboard). The browser stage stands in with navigator.clipboard.
 * execCommand stays as the last try.
 */
export async function copyText(value: string): Promise<boolean> {
  try {
    if (await bridge.invoke<boolean>('drawer:copy', value)) return true
  } catch {
    // no handler (an older main): fall through
  }
  return execCopy(value)
}

registerWebHandler('drawer:copy', async (value) => {
  if (typeof value !== 'string' || !navigator.clipboard?.writeText) return false
  await navigator.clipboard.writeText(value)
  return true
})

function execCopy(value: string): boolean {
  const ta = document.createElement('textarea')
  ta.value = value
  ta.setAttribute('readonly', '')
  Object.assign(ta.style, { position: 'fixed', top: '0', left: '-9999px', opacity: '0' })
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  ta.remove()
  return ok
}
