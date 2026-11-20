/**
 * Feature: drawer. Is the lesson drawer open (the learner's choice)? The spotlight can make it yield
 * for a while (see index.tsx); that never changes `open`, so it slides back once the target moves on.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { usePressed } from '../../core/shortcuts'
import { useDiagram } from '../diagrams/store'

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
}

/** Stage only: `?drawer=open` starts with the drawer open (review and screenshots). */
const startOpen = typeof location !== 'undefined' && new URLSearchParams(location.search).get('drawer') === 'open'

const SIDE_KEY = 'miyagi.drawer.side'
/** The edge the learner chose by dragging (saved), else undefined: the lesson's kind picks (lesson.ready below). */
function savedSide(): Side | undefined {
  try {
    const v = localStorage.getItem(SIDE_KEY)
    return v === 'left' || v === 'right' ? v : undefined
  } catch {
    return undefined
  }
}

const initialSide = savedSide() ?? 'right'
export const useDrawer = create<DrawerState>(() => ({ open: startOpen, side: initialSide, at: initialSide }))

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
// Every lesson opens it (Michael, Nov 15 9:15: in a video lesson the steps and their code weren't on screen while the
// video played). A video lesson puts it on the LEFT edge, over VS Code's sidebar, clear of the player docked on the
// right; a "Just teach me" lesson keeps the right. A side the learner dragged it to wins in both.
onMessage('lesson.ready', (p) => {
  const side = savedSide() ?? (p.lesson.mode === 'lesson' ? 'right' : 'left')
  useDrawer.setState({ open: true, side, at: side, concept: undefined, peekStep: undefined, claimed: false })
})

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
