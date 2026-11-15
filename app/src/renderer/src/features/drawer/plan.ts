/**
 * Feature: drawer. What a "Just teach me" lesson says about itself, beyond core/lesson: the overview ("what we're
 * building"), the "Before you start" primer, each step's plan line and kind, and the current step's full code,
 * why and concepts (Michael, Sat evening: "the instructions aren't clear and don't show what to type").
 *
 * The engine sends these as additive, optional fields (contract on integration/live). The app's copy of
 * shared/contracts/events.ts doesn't have them yet, so they're read defensively here with local types
 * (Core request 7: sync the contract fields into the app). Every field may be missing: an older engine, a video
 * lesson. Nothing here is required for the drawer to work.
 */
import { create } from 'zustand'
import type { StepSummary } from '../../../../../../shared/contracts/events'
import { bridge, registerWebHandler } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'

/** code: type in the file · run: run a command · read: learn a concept first. */
export type StepKind = 'code' | 'run' | 'read'
/** A "Before you start" concept card. */
export type PrimerItem = { id: string; title: string; body: string; code?: string }
/** One line of the plan (lesson.ready / lesson.updated steps[]). */
export type StepPlan = { kind?: StepKind; what?: string }
/** The current step (step.started): what to type or run, in full, and why. */
export type StepDetail = { stepId: string; kind?: StepKind; why?: string; concepts: string[]; code?: string }

type PlanState = {
  overview?: string
  primer: PrimerItem[]
  plan: Record<string, StepPlan>
  detail?: StepDetail
}

const blank: PlanState = { overview: undefined, primer: [], plan: {}, detail: undefined }

export const usePlan = create<PlanState>(() => ({ ...blank }))
const set = usePlan.setState

// ---------------------------------------------------------------------------
// Defensive readers (the payloads are typed without these fields)
// ---------------------------------------------------------------------------

type Loose = Record<string, unknown>

function str(v: unknown): string | undefined {
  return typeof v === 'string' && v.trim() ? v.trim() : undefined
}

/** Code keeps its indentation: only trailing blank space goes. */
function code(v: unknown): string | undefined {
  return typeof v === 'string' && v.trim() ? v.replace(/^\s*\n/, '').replace(/\s+$/, '') : undefined
}

function kind(v: unknown): StepKind | undefined {
  return v === 'code' || v === 'run' || v === 'read' ? v : undefined
}

function primerOf(v: unknown): PrimerItem[] {
  if (!Array.isArray(v)) return []
  return v.flatMap((x: Loose) => {
    const id = str(x?.id)
    const title = str(x?.title)
    if (!id || !title) return []
    return [{ id, title, body: str(x.body) ?? '', code: code(x.code) }]
  })
}

/** Only the fields that are present, so merging never wipes a known plan line. */
function planOf(steps: StepSummary[]): Record<string, StepPlan> {
  const out: Record<string, StepPlan> = {}
  for (const s of steps as Array<StepSummary & Loose>) {
    const p: StepPlan = {}
    const k = kind(s.kind)
    const w = str(s.what)
    if (k) p.kind = k
    if (w) p.what = w
    out[s.id] = p
  }
  return out
}

function merge(a: Record<string, StepPlan>, b: Record<string, StepPlan>): Record<string, StepPlan> {
  const out = { ...a }
  for (const [id, p] of Object.entries(b)) out[id] = { ...a[id], ...p }
  return out
}

// ---------------------------------------------------------------------------
// Engine messages
// ---------------------------------------------------------------------------

onMessage('lesson.ready', (p) => {
  const lesson = p.lesson as typeof p.lesson & Loose
  set({ overview: str(lesson.overview), primer: primerOf(lesson.primer), plan: planOf(p.steps), detail: undefined })
})

onMessage('lesson.updated', (p) => set((s) => ({ plan: merge(s.plan, planOf(p.steps)) })))

onMessage('step.started', (p) => {
  const x = p as typeof p & Loose
  const k = kind(x.kind)
  const w = str(x.what)
  const concepts = Array.isArray(x.concepts) ? x.concepts.map(str).filter((c): c is string => !!c) : []
  set((s) => ({
    detail: { stepId: p.stepId, kind: k, why: str(x.why), concepts, code: code(x.code) },
    plan: k || w ? merge(s.plan, { [p.stepId]: { ...(k && { kind: k }), ...(w && { what: w }) } }) : s.plan
  }))
})

onUi('reset', () => set({ ...blank }))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
export async function copyText(text: string): Promise<boolean> {
  try {
    if (await bridge.invoke<boolean>('drawer:copy', text)) return true
  } catch {
    // no handler (an older main): fall through
  }
  return execCopy(text)
}

registerWebHandler('drawer:copy', async (text) => {
  if (typeof text !== 'string' || !navigator.clipboard?.writeText) return false
  await navigator.clipboard.writeText(text)
  return true
})

function execCopy(text: string): boolean {
  const ta = document.createElement('textarea')
  ta.value = text
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
