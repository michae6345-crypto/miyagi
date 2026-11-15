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
  /** Concept diagrams for the drawer's concept panel (mockup 02), by concept title. Never shown on the island. */
  concepts: Record<string, DiagramPayload>
  /**
   * The live network the engine pushed for a step (kind "network" with real weights, sent without the learner asking:
   * the forward pass starting, a training run, the stuck-loss off-track). It shows in the drawer's right-hand panel
   * for that step and updates in place as new ones arrive; it never opens over the code. ⌃⌥D opens it full size.
   */
  live?: { step?: string; diagram: DiagramPayload }
}

const empty = { diagram: undefined, open: false, step: undefined, byKind: {}, kinds: [], concepts: {}, live: undefined } satisfies DiagramState

/** A network diagram with real weights (data.frames): what NeuralNet.tsx draws. */
export const isLiveNetwork = (p: DiagramPayload): boolean =>
  p.kind === 'network' && Array.isArray((p.data as Record<string, unknown> | undefined)?.frames)

/**
 * The concept panel asks for a picture with action {kind:"diagram", text:"<concept title>"} (contract: concept
 * diagrams are made on demand). The next `diagram` that arrives within this window is that picture: it goes to
 * `concepts`, and the island stays as it is.
 */
const CONCEPT_WITHIN_MS = 60000
let conceptAsk: { title: string; at: number } | undefined
export function expectConceptDiagram(title: string): void {
  conceptAsk = { title, at: Date.now() }
}

export const useDiagram = create<DiagramState>(() => ({ ...empty }))
const set = useDiagram.setState
const get = useDiagram.getState

/** Switch the open diagram to another kind sent for this step (the tabs). */
export function showKind(kind: DiagramKind): void {
  const d = get().byKind[kind]
  if (d) set({ diagram: d })
}

onUi('reset', () => {
  unhold()
  set({ ...empty })
})
onUi('dismiss', () => {
  unhold()
  set({ open: false })
})
/**
 * A diagram the learner asked for (⌥D / the bar's Diagram) is held this long before an automatic card or off-track
 * may close it (Michael's desktop test: an off-track closed a requested diagram ~5 s in). What arrives meanwhile
 * waits behind it (cards keep their state; the diagram's higher island priority hides them) and shows when the hold
 * ends. The learner's own Esc / ⌥D, a new step or a reset still close it at once.
 */
export const HOLD_MS = 8000
/** How long after the request the engine's diagram still counts as the one asked for. */
const ASKED_WITHIN_MS = 30000
let requestedAt = 0
let heldUntil = 0
let holdTimer: ReturnType<typeof setTimeout> | undefined
const unhold = (): void => {
  heldUntil = 0
  clearTimeout(holdTimer)
  holdTimer = undefined
}

// ⌥D while a diagram is open just closes it (claim it, so no new request goes to the engine).
onUi('shortcut', (kind) => {
  if (kind !== 'diagram') return
  if (!get().open) {
    // The step's live network is already here: open it full size, no new request to the engine.
    const live = liveForStep()
    if (live) {
      const step = live.step ?? useLesson.getState().stepId
      const s = get()
      const same = s.step === step
      const kinds = same ? (s.kinds.includes('network') ? s.kinds : [...s.kinds, 'network' as DiagramKind]) : ['network' as DiagramKind]
      set({ diagram: live.diagram, open: true, step, byKind: { ...(same ? s.byKind : {}), network: live.diagram }, kinds })
      unhold()
      heldUntil = Date.now() + HOLD_MS
      return true
    }
    requestedAt = Date.now()
    return
  }
  unhold()
  set({ open: false })
  return true
})
onMessage('diagram', (p) => {
  if (conceptAsk && Date.now() - conceptAsk.at < CONCEPT_WITHIN_MS) {
    const title = conceptAsk.title
    conceptAsk = undefined
    set({ concepts: { ...get().concepts, [title]: p } })
    return
  }
  const step = p.stepId ?? useLesson.getState().stepId
  const asked = !!requestedAt && Date.now() - requestedAt < ASKED_WITHIN_MS
  if (isLiveNetwork(p)) {
    set({ live: { step, diagram: p } })
    // Pushed, not asked for: the drawer panel shows it (and the full-size view, if it's already open, follows along).
    if (!asked) {
      const s = get()
      if (s.open && s.diagram && isLiveNetwork(s.diagram) && s.step === step) set({ diagram: p, byKind: { ...s.byKind, network: p } })
      return
    }
  }
  const s = get()
  const same = s.step === step
  const kinds = same ? (s.kinds.includes(p.kind) ? s.kinds : [...s.kinds, p.kind]) : [p.kind]
  set({ diagram: p, open: true, step, byKind: { ...(same ? s.byKind : {}), [p.kind]: p }, kinds })
  unhold()
  if (asked) heldUntil = Date.now() + HOLD_MS
  requestedAt = 0
})
/** An automatic card / off-track: close the diagram now, or (during a hold) when the hold ends. */
function autoClose(): void {
  const left = heldUntil - Date.now()
  if (get().open && left > 0) {
    if (!holdTimer)
      holdTimer = setTimeout(() => {
        unhold()
        set({ open: false })
      }, left)
    return
  }
  unhold()
  set({ open: false })
}
onMessage('card', autoClose)
onMessage('offtrack', autoClose)
onMessage('step.started', () => {
  unhold()
  set({ open: false })
})

/** The live network for the lesson's current step (an event without a stepId counts for whichever step is on). */
export function liveForStep(): DiagramState['live'] {
  const live = get().live
  const cur = useLesson.getState().stepId
  return live && (!live.step || !cur || live.step === cur) ? live : undefined
}
/** React: the live network for the current step, or undefined. */
export function useLiveNetwork(): DiagramPayload | undefined {
  const live = useDiagram((s) => s.live)
  const cur = useLesson((s) => s.stepId)
  return live && (!live.step || !cur || live.step === cur) ? live.diagram : undefined
}
