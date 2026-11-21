/**
 * Feature: drawer. Is the lesson drawer open (the learner's choice)? The spotlight can make it yield
 * for a while (see index.tsx); that never changes `open`, so it slides back once the target moves on.
 */
import { create } from 'zustand'
import { onMessage, onUi, type PanelRequest } from '../../core/bus'
import { setDock } from '../../core/dock'
import { useLesson } from '../../core/lesson'
import { usePressed } from '../../core/shortcuts'
import { useBeforeStart } from '../before-start/store'
import { useCards } from '../cards/store'
import { useComplete } from '../complete/store'
import { useDiagram } from '../diagrams/store'
import { useSearch } from '../launcher/store'
import { closeHint, usePanel } from './v2/panelStore'

export type Side = 'left' | 'right'

type DrawerState = {
  open: boolean
  /**
   * The learner asked for the drawer (pressed Diagram, or the handle while it had yielded): it stays out even while a
   * spotlight box overlaps it, until the step changes or they press another action (Michael's test 11: a fix box on
   * the code line hid the drawer and the Diagram flyout for ~50 s in a video lesson).
   */
  claimed?: boolean
  /**
   * Which screen edge the learner put the drawer on (drag its header sideways; saved). Michael, Nov 15 5:45 AM: things
   * under it (VS Code's Run button, the terminal) couldn't be clicked, and it couldn't be moved.
   */
  side: Side
  /** Where it's drawn right now: `side`, or the other edge while the spotlight's target sits under it (index.tsx). */
  at: Side
  /** The panel's last rendered height (it hugs its content). Kept while it's hidden, for the spotlight check. */
  panelH?: number
  /** Mockup 02: the primer item (concept) open in the concept panel; the drawer collapses to a step rail meanwhile. */
  concept?: string
  /**
   * A run step tucks the drawer to its handle so VS Code's Run button (top-right of the editor tabs) and the terminal
   * panel stay clear (Michael's test, Sun 2:56 AM: "I can't open the terminal because the overlay on the right side is
   * covering it"). The learner pressing the handle brings it back for that step: this is that step's id.
   */
  peekStep?: string
  /** v2 (A1): the same as the exported openPanel / collapsePanel, for readers that hold the store (A2: useDrawer.getState().openPanel()). */
  openPanel: () => void
  collapsePanel: () => void
}

/** Stage only: `?drawer=open` starts with the drawer open (review and screenshots). */
const startOpen = typeof location !== 'undefined' && new URLSearchParams(location.search).get('drawer') === 'open'

const SIDE_KEY = 'miyagi.drawer.side'
function savedSide(): Side {
  try {
    return localStorage.getItem(SIDE_KEY) === 'left' ? 'left' : 'right'
  } catch {
    return 'right'
  }
}

const initialSide = savedSide()
export const useDrawer = create<DrawerState>(() => ({ open: startOpen, side: initialSide, at: initialSide, openPanel, collapsePanel }))

/** The learner dropped the drawer on an edge: keep it there (this session and the next). */
export function setDrawerSide(side: Side): void {
  if (useDrawer.getState().side !== side) useDrawer.setState({ side })
  try {
    localStorage.setItem(SIDE_KEY, side)
  } catch {
    // storage unavailable: the side holds for this session only
  }
}
export const setDrawerAt = (at: Side): void => {
  if (useDrawer.getState().at !== at) useDrawer.setState({ at })
}

export const toggleDrawer = (): void => useDrawer.setState((s) => ({ open: !s.open, concept: undefined, claimed: false }))
export const closeDrawer = (): void => useDrawer.setState({ open: false, concept: undefined, claimed: false })
/** The handle was pressed while the drawer had yielded to the spotlight: bring it back and keep it out. */
export const claimDrawer = (): void => useDrawer.setState({ open: true, claimed: true })
/** A concept chip was clicked: open the concept panel (the drawer stays open, as a rail). */
export const openConcept = (id: string): void => useDrawer.setState({ open: true, concept: id })
/** "Back to step N": the full drawer again. */
export const closeConcept = (): void => useDrawer.setState({ concept: undefined })
/** The handle was pressed while a run step had the drawer tucked: show it for the rest of this step. */
export const peekDrawer = (stepId: string): void => useDrawer.setState({ open: true, peekStep: stepId })
export const setPanelHeight = (h: number): void => {
  if (h > 0 && useDrawer.getState().panelH !== h) useDrawer.setState({ panelH: h })
}

// Esc / a card's ✕ close cards, diagrams and sheets, never the drawer: during a lesson it only closes when the
// learner hides it with its own control or the right-edge "Steps" handle (Michael's live test, Sun 12:55 AM: a
// "Not yet" card's ✕ took the whole drawer with it, and the step plan and code to type were gone).
onUi('reset', closeDrawer)
// A new lesson starts closed (the stage's ?drawer=open keeps it open for review). A "Just teach me" lesson
// (lesson.mode "lesson") opens it: there's no player and no chapter list, so the drawer is where
// "Step N of M" and the step's instructions live (Michael, Sat 3:56 PM).
onMessage('lesson.ready', (p) => useDrawer.setState({ open: startOpen || p.lesson.mode === 'lesson', concept: undefined, peekStep: undefined, claimed: false }))

// A pushed diagram opens nothing (Michael, Nov 15 7 AM). The learner opened the Diagram flyout: it slides out of the
// drawer's inner edge, so bring the drawer (as the full panel, not the concept rail) if it was closed.
useDiagram.subscribe((s, prev) => {
  if (!s.open || prev.open) return
  const d = useDrawer.getState()
  useDrawer.setState(!d.open || d.concept ? { open: true, concept: undefined, claimed: true } : { claimed: true })
})
// The claim ends with the step, or when the learner presses any other action (Show me must still clear the box).
onMessage('step.started', () => useDrawer.setState({ claimed: false }))
usePressed.subscribe((s, prev) => {
  if (s.kind && s.kind !== 'diagram' && s.at !== prev.at && useDrawer.getState().claimed) useDrawer.setState({ claimed: false })
})

// ---------------------------------------------------------------------------------------------------------------
// v2 lesson panel (BUILD-PLAN A1). In a "Just teach me" lesson (lesson.mode "lesson") the drawer is the docked lesson
// panel (v2/LessonPanel.tsx); `open` still says whether it shows, so every reader of useDrawer keeps working. Video
// lessons keep the drawer above unchanged.
//   openPanel()       show it (the Mini pill's click, A2; the recovery card, A3; a `panel` UI event)
//   collapsePanel()   collapse it to the Mini pill (its chevron, Esc hide, Esc when nothing else is open)
//   isPanelRouted(x)  does the panel render this card / off-track right now (so the island must not)? See v2/route.ts.
// ---------------------------------------------------------------------------------------------------------------

export { isPanelRouted, usePanelRouted, panelShown, type Routable } from './v2/route'

/** The v2 panel is this lesson's drawer ("Just teach me"). */
export const isPanelLesson = (): boolean => useLesson.getState().lesson?.mode === 'lesson'

export function openPanel(): void {
  useDrawer.setState({ open: true, concept: undefined })
  if (isPanelLesson()) setDock({ collapsed: false })
}

export function collapsePanel(): void {
  useDrawer.setState({ open: false, concept: undefined, claimed: false })
  if (isPanelLesson()) setDock({ open: false, collapsed: true, rect: undefined })
}

/** The Mini pill, the recovery card and the keys ask through core's `panel` UI event (no feature imports another's opener). */
onUi('panel', (req) => {
  const r = req as PanelRequest | undefined
  if (r === 'open') openPanel()
  else if (r === 'collapse') collapsePanel()
  else if (r === 'toggle') (useDrawer.getState().open ? collapsePanel : openPanel)()
  else return
  return true
})

/**
 * Esc collapses the panel only when nothing else is open (A1): a card, the off-track card, a diagram, the completion
 * panel, the launcher, "Before you start", or the panel's own hint. Every `dismiss` handler runs on the same Esc, in
 * feature order, so a surface that closed earlier in this same Esc counts as open (`closedNow`, cleared next tick).
 */
function othersOpen(): boolean {
  const c = useCards.getState()
  return (
    !!c.card ||
    c.offtrackOpen ||
    !!c.success ||
    useDiagram.getState().open ||
    !!useComplete.getState().card ||
    useBeforeStart.getState().open ||
    useSearch.getState().open ||
    !!usePanel.getState().hint
  )
}
let closedNow = false
let wasOpen = false
function noteOthers(): void {
  const now = othersOpen()
  if (wasOpen && !now) {
    closedNow = true
    queueMicrotask(() => (closedNow = false))
  }
  wasOpen = now
}
for (const s of [useCards, useDiagram, useComplete, useBeforeStart, useSearch, usePanel] as { subscribe: (fn: () => void) => () => void }[]) s.subscribe(noteOthers)

onUi('dismiss', () => {
  if (!isPanelLesson() || !useDrawer.getState().open) return
  // The panel's hint is its own "something open": Esc closes it first.
  if (usePanel.getState().hint) return closeHint()
  if (othersOpen() || closedNow) return
  collapsePanel()
})

// A new lesson: the panel isn't collapsed (lesson.ready opens it above).
onMessage('lesson.ready', () => setDock({ collapsed: false }))

/** http(s) links only; anything else (file:, javascript:, a bare path) is ignored. */
export function isWebLink(url: string): boolean {
  try {
    const u = new URL(url)
    return u.protocol === 'https:' || u.protocol === 'http:'
  } catch {
    return false
  }
}

/**
 * A source row was clicked. Electron: core's window-open handler denies the window and sends http(s) to the
 * default browser (src/main/index.ts). Browser stage: a new tab.
 */
export function openSource(url: string): void {
  if (isWebLink(url)) window.open(url, '_blank', 'noopener,noreferrer')
}
