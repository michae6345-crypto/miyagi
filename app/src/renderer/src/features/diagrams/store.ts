/**
 * Feature: diagrams. The diagram on screen, whether it's open, and every kind the engine sent for this step
 * (`byKind` / `kinds`, in arrival order): the tabs appear only when there is more than one.
 */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'

export type DiagramPayload = Payload<'diagram'>
export type DiagramKind = DiagramPayload['kind']

type DiagramState = {
  diagram?: DiagramPayload
  open: boolean
  /** The step the collected kinds belong to (payload stepId, else the lesson's current step). */
  step?: string
  byKind: Partial<Record<DiagramKind, DiagramPayload>>
  kinds: DiagramKind[]
}

const empty = { diagram: undefined, open: false, step: undefined, byKind: {}, kinds: [] } satisfies DiagramState

export const useDiagram = create<DiagramState>(() => ({ ...empty }))
const set = useDiagram.setState
const get = useDiagram.getState

/** Switch the open diagram to another kind sent for this step (the tabs). */
export function showKind(kind: DiagramKind): void {
  const d = get().byKind[kind]
  if (d) set({ diagram: d })
}

onUi('reset', () => set({ ...empty }))
onUi('dismiss', () => set({ open: false }))
// ⌥D while a diagram is open just closes it (claim it, so no new request goes to the engine).
onUi('shortcut', (kind) => {
  if (kind !== 'diagram' || !get().open) return
  set({ open: false })
  return true
})
onMessage('diagram', (p) => {
  const step = p.stepId ?? useLesson.getState().stepId
  const s = get()
  const same = s.step === step
  const kinds = same ? (s.kinds.includes(p.kind) ? s.kinds : [...s.kinds, p.kind]) : [p.kind]
  set({ diagram: p, open: true, step, byKind: { ...(same ? s.byKind : {}), [p.kind]: p }, kinds })
})
onMessage('card', () => set({ open: false }))
onMessage('offtrack', () => set({ open: false }))
onMessage('step.started', () => set({ open: false }))
