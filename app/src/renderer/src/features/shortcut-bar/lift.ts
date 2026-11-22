/**
 * Feature: shortcut bar. Keep the bar off the spot the learner has to look at (Michael's desktop test, item 4).
 *
 * The bar sits 24px above the Dock (workArea), but a full-screen app has no Dock in its Space, so the bar covered
 * the editor's terminal right where the spotlight pointed. While the spotlight's hole reaches into the bar's band
 * (and overlaps it horizontally), the bar lifts to sit just above the hole. If that would push it past the middle
 * of the screen (a tall hole), it stays put: covering the middle of the screen is worse.
 */
import type { Layout } from '../../../../preload/api'
import { hole, isUsableRect, toLocal } from '../spotlight/place'
import { useSpotlight } from '../spotlight/store'
import { BAR_HEIGHT } from './ShortcutBar'
import { SLIM_HEIGHT } from './slim'
import { useSlim } from './useSlim'

/**
 * The bar's lower edge above the Dock / taskbar: clear of an editor's status bar (VS Code's is 22px) with a little air
 * (review A12: it covered the status bar). The folded handle sits lower, over the status bar's empty middle.
 */
export const ABOVE_DOCK = 30

/** The bar's top edge in overlay px right now (Dock position, lifted over the spotlight's hole): the floating net keeps above it. */
export function useBarTop(layout: Layout): number {
  const bottom = layout.height - (layout.workArea.y + layout.workArea.height) + ABOVE_DOCK
  const height = useSlim() ? SLIM_HEIGHT : BAR_HEIGHT
  return layout.height - bottom - useLift(layout, bottom, height) - height
}

/** Space between the hole and the bar. */
const GAP = 16
/** About half the bar's width (it's centered); a hole outside this band leaves the bar where it is. */
const HALF_W = 500
/** The bar's top may rise to at most this share of the screen height. */
const MAX_RISE = 0.55

/** How many px to lift the bar above its Dock position right now (0 = stay). */
export function useLift(layout: Layout, bottom: number, height: number = BAR_HEIGHT): number {
  const rect = useSpotlight((s) => (s.target && isUsableRect(s.target.rect) ? s.target.rect : undefined))
  if (!rect) return 0
  const h = hole(toLocal(rect, layout.origin))
  const barTop = layout.height - bottom - height
  const cx = layout.width / 2
  const overlapsX = h.x < cx + HALF_W && h.x + h.w > cx - HALF_W
  if (!overlapsX || h.y + h.h <= barTop - GAP) return 0
  const lifted = layout.height - (h.y - GAP) // the bar's new `bottom`: its lower edge GAP above the hole
  if (lifted + height > layout.height * MAX_RISE) return 0
  return Math.max(0, Math.round(lifted - bottom))
}
