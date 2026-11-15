/**
 * Feature: drawer. Is the lesson drawer open (the learner's choice)? The spotlight can make it yield
 * for a while (see index.tsx); that never changes `open`, so it slides back once the target moves on.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { useDiagram } from '../diagrams/store'

type DrawerState = {
  open: boolean
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

export const useDrawer = create<DrawerState>(() => ({ open: startOpen }))

export const toggleDrawer = (): void => useDrawer.setState((s) => ({ open: !s.open, concept: undefined }))
export const closeDrawer = (): void => useDrawer.setState({ open: false, concept: undefined })
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
onMessage('lesson.ready', (p) => useDrawer.setState({ open: startOpen || p.lesson.mode === 'lesson', concept: undefined, peekStep: undefined }))

// The engine pushed the first live network for a step: open the drawer so it's seen (updates to the same step's
// network never reopen it, so the learner's own "Hide steps" sticks).
useDiagram.subscribe((s, prev) => {
  if (!s.live || s.live === prev.live) return
  if (prev.live && prev.live.step === s.live.step) return
  useDrawer.setState({ open: true, concept: undefined })
})
// The learner asked for the diagram while the step has a live network: show the drawer (its panel unfolds itself).
useDiagram.subscribe((s, prev) => {
  if (s.liveFocus && s.liveFocus !== prev.liveFocus) useDrawer.setState({ open: true, concept: undefined })
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
