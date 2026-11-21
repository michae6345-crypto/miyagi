/**
 * Feature: overview. When the hover card may open (Michael's audit A8: it opened over the spotlight's box and the
 * editor top, and repeated the drawer):
 *   - in a "Just teach me" lesson (lesson.mode "lesson"), only while the drawer is closed: the drawer is that
 *     lesson's step card, and it's open by default; never while the v2 lesson panel is docked (core/dock);
 *   - never over a spotlight hole (the main target or the coach's other targets), in any lesson.
 * The card's own rect is the island's: centered in the overlay at `pillTop`, CARD_W wide, as tall as it was last time.
 * The layout comes from a null overlay layer (LayoutProbe): the island hands its modes no layout.
 */
import { useEffect, type ReactNode } from 'react'
import { create } from 'zustand'
import { useShallow } from 'zustand/react/shallow'
import type { Layout } from '../../../../preload/api'
import { bridge } from '../../bridge'
import { useDock } from '../../core/dock'
import { useLesson, type Rect } from '../../core/lesson'
import { useDrawer } from '../drawer/store'
import { hole, intersects, isUsableRect, toLocal } from '../spotlight/place'
import { useSpotlight } from '../spotlight/store'

/** The hover card's width (the island mode's `width`). */
export const CARD_W = 440
/** Until the card has been measured once. */
const CARD_H_GUESS = 300
/** Air kept between the card and a hole. */
const HOLE_MARGIN = 8

export const useCardGeom = create<{ layout?: Layout; h: number }>(() => ({ h: CARD_H_GUESS }))

/** The card measures itself while it's open, so the next decision uses its real height. */
export const setCardHeight = (h: number): void => {
  if (h > 0 && useCardGeom.getState().h !== h) useCardGeom.setState({ h })
}

/** Renders nothing: keeps the overlay's layout where the island mode's hook can read it. */
export function LayoutProbe({ layout }: { layout: Layout }): ReactNode {
  useEffect(() => {
    useCardGeom.setState({ layout })
  }, [layout])
  return null
}

/** Would the card, opened now, cover a spotlight hole? */
function useCardOverHole(): boolean {
  const { layout, h } = useCardGeom(useShallow((s) => ({ layout: s.layout, h: s.h })))
  const main = useSpotlight((s) => (s.target && isUsableRect(s.target.rect) ? s.target.rect : undefined))
  const others = useSpotlight((s) => s.targets)
  if (!layout || (!main && !others.length)) return false
  const card: Rect = { x: (layout.width - CARD_W) / 2 - HOLE_MARGIN, y: bridge.platform.pillTop - HOLE_MARGIN, w: CARD_W + HOLE_MARGIN * 2, h: h + HOLE_MARGIN * 2 }
  // The coach's other targets are only drawn while the main spotlight is up.
  const rects = main ? [main, ...others.map((t) => t.rect)] : []
  return rects.some((r) => intersects(card, hole(toLocal(r, layout.origin))))
}

/** The overview island mode's useActive: hovering the pill during a step, and the card has somewhere to go. */
export function useOverviewActive(hover: boolean): boolean {
  const base = useLesson((s) => hover && !!s.stepId && !s.offtrack)
  const textLesson = useLesson((s) => s.lesson?.mode === 'lesson')
  const drawerOpen = useDrawer((s) => s.open)
  // v2 (A1): the docked lesson panel is the step card; the hover card would repeat it.
  const panelOpen = useDock((s) => s.open)
  const overHole = useCardOverHole()
  return base && !(textLesson && drawerOpen) && !panelOpen && !overHole
}
