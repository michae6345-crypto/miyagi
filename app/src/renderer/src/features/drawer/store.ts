/**
 * Feature: drawer. Is the lesson drawer open (the learner's choice)? The spotlight can make it yield
 * for a while (see index.tsx); that never changes `open`, so it slides back once the target moves on.
 */
import { create } from 'zustand'
import { bridge, isElectron } from '../../bridge'
import { onMessage, onUi, type PanelRequest } from '../../core/bus'
import { setDock, useDock } from '../../core/dock'
import { useLesson } from '../../core/lesson'
import { usePressed } from '../../core/shortcuts'
import { useBeforeStart } from '../before-start/store'
import { useCards } from '../cards/store'
import { useComplete } from '../complete/store'
import { useDiagram } from '../diagrams/store'
import { useErrors } from '../errors/store'
import { useSearch } from '../launcher/store'
import { closeHint, hintShown, usePanel } from './v2/panelStore'
import { isWebLink, linkHost } from './links'
import { isPanelRouted } from './v2/route'

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
  /**
   * v2: where the lesson panel comes from and goes to. 'edge': it slides in from the screen's right edge (a lesson's
   * first step) and out to it (the lesson ends). 'pill': it morphs out of the Mini pill and back into it (collapse and
   * reopen). collapsePanel sets 'pill'; a new lesson resets it to 'edge'.
   */
  via?: 'edge' | 'pill'
  /** v2 (A1): the same as the exported openPanel / collapsePanel, for readers that hold the store (A2: useDrawer.getState().openPanel()). */
  openPanel: () => void
  collapsePanel: () => void
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
export const closeDrawer = (): void => useDrawer.setState({ open: false, concept: undefined, claimed: false, via: 'edge' })
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
// video played). Both kinds of lesson put it on the right: a video lesson in the column beside VS Code, with the player
// (geometry.ts panelRect; the left edge covered VS Code's Explorer, Michael Nov 25). A side the learner dragged it to wins.
onMessage('lesson.ready', () => {
  const side = savedSide() ?? 'right'
  useDrawer.setState({ open: true, side, at: side, concept: undefined, peekStep: undefined, claimed: false, via: 'edge' })
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
  useDrawer.setState({ open: false, concept: undefined, claimed: false, via: 'pill' })
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
 * Esc collapses the panel only when nothing else the learner can see is open (A1): an island card, the off-track card,
 * a diagram, the completion panel, the launcher, "Before you start", or the panel's own hint. Every `dismiss` handler
 * runs on the same Esc, in feature order, so a surface that closed earlier in this same Esc counts as open
 * (`closedNow`, cleared next tick). A card the panel renders itself (isPanelRouted: the island hides it) and a hint
 * hidden under Checking, Passed or a newer Not yet are not open: closing one must not spend the Esc.
 */
function othersOpen(): boolean {
  const c = useCards.getState()
  return (
    (!!c.card && !isPanelRouted(c.card)) ||
    (c.offtrackOpen && !isPanelRouted({ kind: 'offtrack', ...useLesson.getState().offtrack })) ||
    !!c.success ||
    useDiagram.getState().open ||
    !!useComplete.getState().card ||
    useBeforeStart.getState().open ||
    useSearch.getState().open ||
    // An error card on the island (engine offline, editor closed, build failed, crash): Esc is that card's first.
    !!useErrors.getState().visible ||
    hintShown()
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
// useLesson, usePressed and useDock too: what isPanelRouted and hintShown read (the step, a diagnosis, a Check press,
// the panel opening) can change what counts as open without any of the surfaces above changing.
for (const s of [useCards, useDiagram, useComplete, useBeforeStart, useSearch, useErrors, usePanel, useLesson, usePressed, useDock] as { subscribe: (fn: () => void) => () => void }[]) s.subscribe(noteOthers)

/**
 * App windows open over the lesson (account, library, progress, onboarding). In the browser stage they share this
 * page, so Esc reaches every dismiss handler at once: the window takes it, never the panel too (persona QA: one Esc
 * closed the account menu AND collapsed the panel). Electron windows get their own keys; the list stays empty there.
 */
const appWindows = new Set<string>()
let appClosedNow = false
// The stage opens ?window=<route> while bridge.ts initialises, before this listener exists: read the list it already
// has (as dev/Stage.tsx does), or one Esc would close that window and collapse the panel too. Stage only.
if (!isElectron) {
  bridge
    .invoke<string[]>('window:stage-list')
    .then((list) => {
      if (Array.isArray(list)) for (const r of list) appWindows.add(r)
    })
    .catch(() => undefined)
}
bridge.onFeature('window:stage', (p) => {
  const { route, open } = (p ?? {}) as { route?: string; open?: boolean }
  if (!route) return
  if (open) appWindows.add(route)
  else if (appWindows.delete(route)) {
    appClosedNow = true
    setTimeout(() => (appClosedNow = false), 0)
  }
})

onUi('dismiss', () => {
  if (!isPanelLesson() || !useDrawer.getState().open) return
  if (appWindows.size > 0 || appClosedNow) return
  // The panel's hint, while it is the view on screen, is its own "something open": Esc closes it first.
  if (hintShown()) return closeHint()
  if (othersOpen() || closedNow) return
  collapsePanel()
})

// A new lesson: the panel isn't collapsed (lesson.ready opens it above).
onMessage('lesson.ready', () => setDock({ collapsed: false }))

// http(s) links only; anything else (file:, javascript:, a bare path) is ignored. linkHost: where a link goes, shown
// next to it. Both live in ./links (pure, so tests import them without the stores).
export { isWebLink, linkHost }

/**
 * A source row was clicked. Electron: core's window-open handler denies the window and sends http(s) to the
 * default browser (src/main/index.ts). Browser stage: a new tab.
 */
export function openSource(url: string): void {
  if (isWebLink(url)) window.open(url, '_blank', 'noopener,noreferrer')
}

/**
 * Setup Download / Open links main would not open (not on its setup list, main/safeOpen.ts SETUP_PAGES), keyed by tool AND
 * URL (refusedKey): the text to show on the row with a Copy button instead ('' = not a web link, nothing to copy).
 * A corrected URL the engine sends later for the same tool is a new key, so its row offers Get it again.
 */
export const useRefusedLinks = create<{ byKey: Record<string, string> }>(() => ({ byKey: {} }))

const refusedKey = (tool: string, url: string | undefined): string => `${tool}\n${url ?? ''}`

/** The refused link for this tool and URL (the text to copy), or undefined when it wasn't refused. */
export function refusedLink(byKey: Record<string, string>, tool: string, url: string | undefined): string | undefined {
  return Object.prototype.hasOwnProperty.call(byKey, refusedKey(tool, url)) ? byKey[refusedKey(tool, url)] : undefined
}

/** main's answer (safeOpen.ts SetupOpen); the browser stage answers a plain boolean. */
type SetupOpen = { opened: true } | { opened: false; refused: boolean; copy?: string }

/**
 * A setup row's Download or Open button (cards/index.tsx, cards/VSCodeSheet.tsx). The URL comes from the engine (maybe from a
 * video description), so it never goes through window.open (any https): main opens it only if it is on the setup
 * list, else the row shows it as text with Copy (app-harden). A link on the list the system failed to open is not
 * "refused": the row keeps Get it, so the learner can try again.
 */
export function openSetupLink(tool: string, url: string): void {
  void bridge
    .invoke<SetupOpen | boolean>('open:external', { setup: url })
    .catch((): SetupOpen => ({ opened: false, refused: false }))
    .then((r) => {
      const res: SetupOpen = typeof r === 'boolean' ? (r ? { opened: true } : { opened: false, refused: true, copy: url }) : r
      if (!res.opened && !res.refused) return
      useRefusedLinks.setState((s) => {
        const byKey = { ...s.byKey }
        const key = refusedKey(tool, url)
        if (res.opened) delete byKey[key]
        else byKey[key] = res.copy && isWebLink(res.copy) ? res.copy : ''
        return { byKey }
      })
    })
}

/**
 * Does this setup row's button open a link? "download" (a download page) and "open" (a web app, kind web_app). Both
 * go through main's setup list (openSetupLink), never the engine's open_in_browser: Claude's requirements may mark any
 * tool a web_app with any https URL, and the engine would `open` it (app-harden).
 */
export const isLinkRow = (method: string): boolean => method === 'download' || method === 'open'

/**
 * A link row's button (cards/index.tsx itemAct, cards/VSCodeSheet.tsx act): a link main already refused is copied;
 * anything else goes to main's setup list (no URL at all is refused there and shows "Not a web link").
 */
export function linkRowAct(tool: string, url: string | undefined): void {
  const refused = refusedLink(useRefusedLinks.getState().byKey, tool, url)
  if (refused !== undefined) void copySetupLink(refused)
  else openSetupLink(tool, url ?? '')
}

/** Copy a refused setup link (main's clipboard: the overlay can't take focus; see drawer/plan.ts copyText). */
export async function copySetupLink(url: string): Promise<boolean> {
  if (!url) return false
  try {
    if (await bridge.invoke<boolean>('drawer:copy', url)) return true
  } catch {
    // no handler (the stage without one): fall through
  }
  try {
    await navigator.clipboard.writeText(url)
    return true
  } catch {
    return false
  }
}
