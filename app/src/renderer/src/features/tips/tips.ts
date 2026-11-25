/**
 * Feature: tips. The seven first-time coach marks, in the order they win when several could show.
 *
 * Each tip finds its real element on screen (data-* attributes the owning lanes already draw, or the island's box) and
 * says where the mark goes: below the island and the menu bar item, beside the lesson panel (never over it). A tip
 * whose element isn't there simply doesn't show (graceful: a lane renames an attribute, the tip waits).
 *
 * Copy: calm, short (12 words or fewer), lowercase miyagi, sentence case. Keys come from the platform (the body names
 * them by KeyName and the card draws the Keycap). Option names (Hint, Show me) are drawn as their pastel chips.
 */
import type { IslandBox } from '../../core/Island'
import type { Rect } from './place'
import { usePrefs } from '../../core/prefs'
import { useCircle } from '../circle/store'
import { usePtt } from '../ptt/store'

export type TipId = 'check' | 'help' | 'mini' | 'pill' | 'launcher' | 'menubar' | 'circle'

/** A piece of a tip's body: text, a keycap (by platform key name), or an option's pastel chip. */
export type BodyPart = string | { key: 'launcher' | 'ptt' | 'ptt_alt' } | { option: 'hint' | 'show_me' | 'explain' }

export type Side = 'below' | 'above' | 'left'

export type Anchor = {
  /** The element the caret points at (overlay coordinates). */
  target: Rect
  /** What the mark must stay clear of (the whole lesson panel for its button and help row). Default: the target. */
  avoid?: Rect
  side: Side
}

/** What the layer knows when it asks each tip "can you show, and where?". */
export type TipContext = {
  /** A rect for a selector, in overlay coordinates, or undefined when it isn't on screen. */
  rect: (selector: string) => Rect | undefined
  /** The element itself (for reading its data-* state). */
  el: (selector: string) => HTMLElement | null
  island: IslandBox
  /** The lesson panel is docked open (false while it collapses to Mini, even though its exit animation is still drawn). */
  panelOpen: boolean
  /** The lesson's video player is docked open (a video lesson). */
  playerOpen: boolean
  /** No engine answers (the idle pill says Can't reach miyagi, or what the app's own engine is doing): nothing to start. */
  offline: boolean
  /** Index of the current step (0-based). */
  stepIndex: number
  /** How long the learner has been on the current step (ms). */
  stepAge: number
  /**
   * The learner did this since the tip on screen appeared: an action they sent (`check_step`, `hint`, `show_me`, from
   * a button, a tile or a key) or `launcher` (the launcher opened, from its key, the pill or the menu bar).
   */
  did: (what: string) => boolean
  /** The menu bar (or taskbar) item, in overlay coordinates, when main can tell (Core request 2). */
  tray?: Rect
  os: 'mac' | 'win'
  seen: (id: TipId) => boolean
  /** Overlay height, to put a bottom taskbar's mark above it. */
  height: number
}

export type Tip = {
  id: TipId
  title: string
  body: (os: 'mac' | 'win') => BodyPart[]
  anchor: (c: TipContext) => Anchor | undefined
  /**
   * The learner just did what the tip teaches (checked, asked for a hint, opened the panel...). The tip closes for good
   * at once, however briefly it was up: it never comes back to teach something already done.
   */
  done?: (c: TipContext) => boolean
  /** Dismissing this tip also counts these as seen (they teach the same thing). */
  alsoSeen?: TipId[]
}

/** How long the learner is on a step (with the panel's help row in view) before Stuck? shows outside a Not yet. */
export const HELP_AFTER_MS = 20000

/**
 * Selectors, newest first: `data-tip-anchor` is what Core request 4 asks the owning lanes to add (stable, meant for
 * this); the rest are what they draw today.
 */
const SEL = {
  panel: '[data-tip-anchor="panel"], [data-part="lesson-panel"]',
  check: '[data-tip-anchor="check"], [data-part="lesson-panel"][data-view="working"] [data-button="primary"]',
  help: '[data-tip-anchor="help"], [data-part="lesson-panel"] [data-part="panel-help"]',
  islandLayer: (mode: string) => `[data-island-layer="${mode}"]`
} as const

/** The lesson panel's view (working, checking, notyet, hint, passed), when it is on screen. */
const panelView = (c: TipContext): string | undefined => c.el(SEL.panel)?.dataset.view

/** The island's live layer for a mode, when that mode is the one on screen and nothing has borrowed the island. */
function islandAnchor(c: TipContext, mode: string): Anchor | undefined {
  if (!c.island.visible || !c.island.pill || c.island.mode !== mode) return undefined
  const target = c.rect(SEL.islandLayer(mode))
  return target ? { target, side: 'below' } : undefined
}

export const TIPS: Tip[] = [
  {
    id: 'check',
    title: 'Check my work',
    body: () => ["Press it when you think you're done. miyagi checks your real work."],
    // Only while the panel is docked open: while it collapses to Mini its exit animation still draws it, and the mark
    // must not follow it away.
    anchor: (c) => {
      if (!c.panelOpen) return undefined
      const target = c.rect(SEL.check)
      const avoid = c.rect(SEL.panel)
      return target && avoid ? { target, avoid, side: 'left' } : undefined
    },
    // A check started (from the button or a key), or its answer is already in.
    done: (c) => {
      const view = panelView(c)
      return c.did('check_step') || view === 'checking' || view === 'notyet' || view === 'passed'
    }
  },
  {
    id: 'help',
    title: 'Stuck?',
    body: () => ['Try ', { option: 'hint' }, ' first, then ', { option: 'show_me' }, '.'],
    // When it matters: the first Not yet, or from the second step on once the learner has been on the step a while
    // (HELP_AFTER_MS), so it never follows the Check my work tip straight onto the same panel. Not while a hint is
    // already on screen (the learner just did what it says), and only while the panel is docked open.
    anchor: (c) => {
      if (!c.panelOpen) return undefined
      const view = panelView(c)
      if (!view || view === 'passed' || view === 'checking' || view === 'hint') return undefined
      if (view !== 'notyet' && (c.stepIndex < 1 || c.stepAge < HELP_AFTER_MS)) return undefined
      const target = c.rect(SEL.help)
      const avoid = c.rect(SEL.panel)
      return target && avoid ? { target, avoid, side: 'left' } : undefined
    },
    done: (c) => c.did('hint') || c.did('show_me') || panelView(c) === 'hint'
  },
  {
    id: 'mini',
    title: 'Your lesson, tucked away',
    body: () => ['It keeps your place. Click it to open the panel again.'],
    anchor: (c) => islandAnchor(c, 'mini'),
    // The panel is open again.
    done: (c) => c.panelOpen,
    alsoSeen: ['pill']
  },
  {
    id: 'pill',
    title: 'This is miyagi',
    body: () => ['Point at it to see your step.'],
    // The step pill on its own: no panel docked open and no video player beside it (both already show the step). The
    // pill takes no click; pointing at it opens the step card, so that is what the copy teaches.
    anchor: (c) => (c.panelOpen || c.playerOpen ? undefined : islandAnchor(c, 'compact')),
    // Pointing at it grew the step card (the overview card) out of the island.
    done: (c) => c.island.visible && c.island.mode === 'overview'
  },
  {
    id: 'launcher',
    title: 'Ask miyagi anything',
    body: () => ['Press ', { key: 'launcher' }, ' in any app to start a lesson.'],
    // Not while the engine is offline or not installed: the idle pill then says so, and the key can't start anything.
    anchor: (c) => (c.offline ? undefined : islandAnchor(c, 'idle')),
    // The launcher opened (its key, a press on the pill, the menu bar): it borrows the island.
    done: (c) => c.did('launcher')
  },
  {
    id: 'menubar',
    title: 'miyagi is always here',
    body: (os) => [os === 'mac' ? 'Open it from the menu bar, even with every window closed.' : 'Open it from the taskbar, even with every window closed.'],
    // After the launcher's tip (the first thing to learn), only while the island is idle, and only when main knows
    // where its item is. A taskbar at the bottom of the screen gets the mark above it.
    anchor: (c) => {
      if (!c.tray || !c.seen('launcher') || c.offline) return undefined
      if (!c.island.visible || !c.island.pill || c.island.mode !== 'idle') return undefined
      return { target: c.tray, side: c.tray.y > c.height / 2 ? 'above' : 'below' }
    }
  },
  {
    id: 'circle',
    title: 'Circle to ask',
    // The push-to-talk keys, as the learner set them (Settings > General), drawn from the platform's keycaps.
    body: () => ['Hold ', { key: usePrefs.getState().ptt.chord === 'control+option' ? 'ptt_alt' : 'ptt' }, ' and circle anything to ask.'],
    // Only when the keys can work (push to talk on, its helper ready, Input Monitoring not off), and after the first
    // things to learn: on the step pill in a lesson, or on the idle pill once the launcher's tip is seen.
    anchor: (c) => {
      const ptt = usePtt.getState().ptt
      if (c.offline || !usePrefs.getState().ptt.enabled || !ptt.available || ptt.perms.input === 'denied') return undefined
      return islandAnchor(c, 'compact') ?? (c.seen('launcher') ? islandAnchor(c, 'idle') : undefined)
    },
    // A circle was asked about.
    done: () => useCircle.getState().asked > 0
  }
]
