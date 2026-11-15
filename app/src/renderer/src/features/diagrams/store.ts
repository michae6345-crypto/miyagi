/**
 * Feature: diagrams. Every diagram the engine sent for this step (`byKind` / `kinds`, in arrival order: the tabs appear
 * only when there is more than one), and whether the flyout beside the drawer shows them (drawer/Flyout.tsx).
 */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'

export type DiagramPayload = Payload<'diagram'>
export type DiagramKind = DiagramPayload['kind']

type DiagramState = {
  /** What the flyout shows while open; while closed, the newest diagram kept for `step` (what the button opens). */
  diagram?: DiagramPayload
  /** The flyout beside the drawer is out. Only the learner opens it (the Diagram button, ⌥D, or a diagram they asked for). */
  open: boolean
  /** The step the collected kinds belong to (payload stepId, else the lesson's current step). */
  step?: string
  byKind: Partial<Record<DiagramKind, DiagramPayload>>
  kinds: DiagramKind[]
  /** Kinds of `step` the learner has had on screen. A kept kind not in here puts the dot on the bar's Diagram tile. */
  seen: DiagramKind[]
  /** Concept diagrams for the drawer's concept panel (mockup 02), by concept title. Never shown in the flyout. */
  concepts: Record<string, DiagramPayload>
  /** The newest live network (kind "network" with real weights) and its step: kept across a relaunch (below). */
  live?: { step?: string; diagram: DiagramPayload }
}

const empty = { diagram: undefined, open: false, step: undefined, byKind: {}, kinds: [], seen: [], concepts: {}, live: undefined } satisfies DiagramState

/** A network diagram with real weights (data.frames): what NeuralNet.tsx draws. */
export const isLiveNetwork = (p: DiagramPayload): boolean =>
  p.kind === 'network' && Array.isArray((p.data as Record<string, unknown> | undefined)?.frames)

/**
 * The concept panel asks for a picture with action {kind:"diagram", text:"<concept title>"} (contract: concept
 * diagrams are made on demand). The next `diagram` that arrives within this window is that picture: it goes to
 * `concepts`, and the flyout stays as it is.
 */
const CONCEPT_WITHIN_MS = 60000
let conceptAsk: { title: string; at: number } | undefined
export function expectConceptDiagram(title: string): void {
  conceptAsk = { title, at: Date.now() }
}

export const useDiagram = create<DiagramState>(() => ({ ...empty }))
const set = useDiagram.setState
const get = useDiagram.getState

const currentStep = (): string | undefined => useLesson.getState().stepId
/** Do the kept kinds belong to the step that's on (an event without a stepId counts for whichever step is on)? */
const forStep = (s: DiagramState, cur = currentStep()): boolean => !s.step || !cur || s.step === cur

/**
 * Michael, Nov 15 (7 AM): "remove the pop-up for the diagram that starts immediately. I want to click the diagram
 * button, for that to pop up, and for it to come off of the right side panel". Every diagram the engine pushes is
 * kept for its step and shown only when the learner asks: no island card, no unfolding drawer panel, no floating box.
 * While the flyout is out, the kind on screen redraws in place (a training run animates); another kind joins the tabs.
 */
function keep(p: DiagramPayload, step: string | undefined): void {
  const s = get()
  const same = s.step === step
  const kinds = same ? (s.kinds.includes(p.kind) ? s.kinds : [...s.kinds, p.kind]) : [p.kind]
  const byKind = { ...(same ? s.byKind : {}), [p.kind]: p }
  if (same && s.open) {
    set({ byKind, kinds, diagram: s.diagram?.kind === p.kind ? p : s.diagram, seen: s.seen.includes(p.kind) ? s.seen : [...s.seen, p.kind] })
    return
  }
  set({ step, byKind, kinds, diagram: p, seen: same ? s.seen : [], open: false })
}

/** Open the flyout on what the current step already has. False when it has nothing yet (then ask the engine). */
function openKept(): boolean {
  const s = get()
  if (!s.kinds.length || !forStep(s)) return false
  const diagram = (s.diagram && s.byKind[s.diagram.kind]) || s.byKind[s.kinds[s.kinds.length - 1]]
  if (!diagram) return false
  set({ open: true, diagram, seen: [...s.kinds] })
  return true
}

export function closeDiagram(): void {
  if (get().open) set({ open: false })
}

/** Switch the open diagram to another kind sent for this step (the tabs). */
export function showKind(kind: DiagramKind): void {
  const d = get().byKind[kind]
  if (d) set({ diagram: d })
}

/** React: the current step has a diagram the learner hasn't opened yet (the Diagram tile's dot). */
export function useUnseen(): boolean {
  const cur = useLesson((l) => l.stepId)
  return useDiagram((s) => !s.open && forStep(s, cur) && s.kinds.some((k) => !s.seen.includes(k)))
}

onUi('reset', () => set({ ...empty }))
onUi('dismiss', closeDiagram)
onMessage('step.started', closeDiagram)

/** How long after the learner's request the engine's diagram still counts as the one asked for (it opens). */
const ASKED_WITHIN_MS = 30000
let requestedAt = 0

/**
 * The Diagram button (the bar's tile, ⌥D, any Diagram option: they all go through triggerShortcut('diagram')) toggles
 * the flyout. Open: close it. Closed with a diagram kept for this step: open it, no request to the engine. Otherwise
 * nobody claims the press, so action {kind:"diagram"} goes to the engine and its answer opens.
 */
onUi('shortcut', (kind) => {
  if (kind !== 'diagram') return
  if (get().open) {
    closeDiagram()
    return true
  }
  if (openKept()) return true
  requestedAt = Date.now()
  return
})
onMessage('diagram', (p) => {
  if (conceptAsk && Date.now() - conceptAsk.at < CONCEPT_WITHIN_MS) {
    const title = conceptAsk.title
    conceptAsk = undefined
    set({ concepts: { ...get().concepts, [title]: p } })
    return
  }
  const step = p.stepId ?? currentStep()
  const asked = !!requestedAt && Date.now() - requestedAt < ASKED_WITHIN_MS
  if (isLiveNetwork(p)) set({ live: { step, diagram: p } })
  keep(p, step)
  if (!asked) return
  requestedAt = 0
  openKept()
})

/*
 * The step's live network survives a relaunch (Michael's 5 AM shoot: after the overlay was relaunched mid-lesson,
 * the network panel stayed empty until Diagram was pressed, because the engine's replay doesn't resend it).
 * The last live network is kept in localStorage with its lesson and step; the first step.started after launch puts
 * it back (kept, not shown) if it's the same lesson and step, and recent. Later step changes never restore anything.
 */
const SAVE_KEY = 'miyagi.liveNetwork'
const RESTORE_WITHIN_MS = 20 * 60 * 1000
type Saved = { lesson?: string; step?: string; at: number; diagram: DiagramPayload }
let saveTimer: ReturnType<typeof setTimeout> | undefined
useDiagram.subscribe((s, prev) => {
  if (s.live === prev.live || !s.live) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    const live = get().live
    if (!live) return
    const saved: Saved = { lesson: useLesson.getState().lesson?.id, step: live.step, at: Date.now(), diagram: live.diagram }
    try {
      localStorage.setItem(SAVE_KEY, JSON.stringify(saved))
    } catch {
      // storage full or blocked: nothing to restore later, that's all
    }
  }, 1000)
})
let firstStep = true
onMessage('step.started', (p) => {
  if (!firstStep) return
  firstStep = false
  if (get().live) return
  try {
    const raw = localStorage.getItem(SAVE_KEY)
    if (!raw) return
    const saved = JSON.parse(raw) as Saved
    const lesson = useLesson.getState().lesson?.id
    const step = p.stepId ?? useLesson.getState().stepId
    if (!saved?.diagram || !lesson || saved.lesson !== lesson || !step || saved.step !== step) return
    if (Date.now() - saved.at > RESTORE_WITHIN_MS) return
    set({ live: { step, diagram: saved.diagram } })
    keep(saved.diagram, step)
  } catch {
    // unreadable copy: skip it
  }
})
