/**
 * Feature: drawer. The current step's "what to type" (Michael, Sat evening: "the instructions aren't clear and
 * don't show what to type"): step.started's kind, why, concepts and full code. core/lesson keeps the rest of a
 * "Just teach me" lesson (lesson.overview, lesson.primer, steps[].kind / what), so the drawer reads those there.
 *
 * Every field is optional (an older engine, a video lesson); nothing here is required for the drawer to work.
 */
import { create } from 'zustand'
import type { PrimerItem, StepKind } from '../../../../../../shared/contracts/events'
import { bridge, registerWebHandler } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'

/** The current step (step.started): what to type or run, in full, and why. */
export type StepDetail = { stepId: string; kind?: StepKind; why?: string; concepts: string[]; code?: string }

export const useStepDetail = create<{ detail?: StepDetail }>(() => ({}))
const set = useStepDetail.setState

const KINDS: readonly StepKind[] = ['code', 'run', 'read']

function text(v: string | undefined): string | undefined {
  return v?.trim() || undefined
}

/** Code keeps its indentation: only leading blank lines and trailing space go. */
function code(v: string | undefined): string | undefined {
  return v?.trim() ? v.replace(/^\s*\n/, '').replace(/\s+$/, '') : undefined
}

onMessage('step.started', (p) =>
  set({
    detail: {
      stepId: p.stepId,
      kind: p.kind && KINDS.includes(p.kind) ? p.kind : undefined,
      why: text(p.why),
      concepts: (p.concepts ?? []).map((c) => c.trim()).filter(Boolean),
      code: code(p.code)
    }
  })
)
onMessage('lesson.ready', () => set({ detail: undefined }))
onUi('reset', () => set({ detail: undefined }))

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
