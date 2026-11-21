/**
 * Feature: tips. The six first-time coach marks, in the order they win when several could show.
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

export type TipId = 'check' | 'help' | 'mini' | 'pill' | 'launcher' | 'menubar'

/** A piece of a tip's body: text, a keycap (by platform key name), or an option's pastel chip. */
export type BodyPart = string | { key: 'launcher' } | { option: 'hint' | 'show_me' }

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
  /** The lesson panel is docked open. */
  panelOpen: boolean
  /** Index of the current step (0-based). */
  stepIndex: number
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
  /** Dismissing this tip also counts these as seen (they teach the same thing). */
  alsoSeen?: TipId[]
}

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
    anchor: (c) => {
      const target = c.rect(SEL.check)
      const avoid = c.rect(SEL.panel)
      return target && avoid ? { target, avoid, side: 'left' } : undefined
    }
  },
  {
    id: 'help',
    title: 'Stuck?',
    body: () => ['Try ', { option: 'hint' }, ' first, then ', { option: 'show_me' }, '.'],
    // When it matters: the first Not yet, or from the second step on (the learner has met the panel by then).
    anchor: (c) => {
      const panel = c.el(SEL.panel)
      const view = panel?.dataset.view
      if (!view || view === 'passed' || view === 'checking') return undefined
      if (view !== 'notyet' && c.stepIndex < 1) return undefined
      const target = c.rect(SEL.help)
      const avoid = c.rect(SEL.panel)
      return target && avoid ? { target, avoid, side: 'left' } : undefined
    }
  },
  {
    id: 'mini',
    title: 'Your lesson, tucked away',
    body: () => ['It keeps your place. Click it to open the panel again.'],
    anchor: (c) => islandAnchor(c, 'mini'),
    alsoSeen: ['pill']
  },
  {
    id: 'pill',
    title: 'This is miyagi',
    body: () => ['Click it to open your lesson.'],
    // The step pill with the panel closed (a video lesson, or before the panel docks). With the panel open the pill
    // has nothing to open.
    anchor: (c) => (c.panelOpen ? undefined : islandAnchor(c, 'compact'))
  },
  {
    id: 'launcher',
    title: 'Ask miyagi anything',
    body: () => ['Press ', { key: 'launcher' }, ' in any app to start a lesson.'],
    anchor: (c) => islandAnchor(c, 'idle')
  },
  {
    id: 'menubar',
    title: 'miyagi is always here',
    body: (os) => [os === 'mac' ? 'Open it from the menu bar, even with every window closed.' : 'Open it from the taskbar, even with every window closed.'],
    // After the launcher's tip (the first thing to learn), only while the island is idle, and only when main knows
    // where its item is. A taskbar at the bottom of the screen gets the mark above it.
    anchor: (c) => {
      if (!c.tray || !c.seen('launcher')) return undefined
      if (!c.island.visible || !c.island.pill || c.island.mode !== 'idle') return undefined
      return { target: c.tray, side: c.tray.y > c.height / 2 ? 'above' : 'below' }
    }
  }
]
