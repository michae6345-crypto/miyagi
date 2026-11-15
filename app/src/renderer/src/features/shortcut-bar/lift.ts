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

/** Space between the hole and the bar. */
const GAP = 16
/** About half the bar's width (it's centered); a hole outside this band leaves the bar where it is. */
const HALF_W = 500
/** The bar's top may rise to at most this share of the screen height. */
const MAX_RISE = 0.55

/** How many px to lift the bar above its Dock position right now (0 = stay). */
export function useLift(layout: Layout, bottom: number): number {
  const rect = useSpotlight((s) => (s.target && isUsableRect(s.target.rect) ? s.target.rect : undefined))
  if (!rect) return 0
  const h = hole(toLocal(rect, layout.origin))
  const barTop = layout.height - bottom - BAR_HEIGHT
  const cx = layout.width / 2
  const overlapsX = h.x < cx + HALF_W && h.x + h.w > cx - HALF_W
  if (!overlapsX || h.y + h.h <= barTop - GAP) return 0
  const lifted = layout.height - (h.y - GAP) // the bar's new `bottom`: its lower edge GAP above the hole
  if (lifted + BAR_HEIGHT > layout.height * MAX_RISE) return 0
  return Math.max(0, Math.round(lifted - bottom))
}
