/**
 * The island's size from one measurement of the active mode's layer (core/Island.tsx). Pure, so it is tested offline
 * (test/islandSize.test.ts).
 *
 * Michael's repro (Nov 21): a card closed with its ✕ and the island stayed a big empty black rectangle (about 600 x 280,
 * pill-rounded) at the top centre, eating clicks. The old rule was "a 0 measurement never wins: the last good size
 * stays", so a pill-sized mode whose row measured 0 (or was never found) kept the CARD's width and height, and a card
 * whose content rendered nothing kept its old height. Now:
 *   - a pill is always pill-tall; its width is the row's, else the last pill width, never a card's;
 *   - a card is its fixed width and its content's height; a card with nothing in it is the pill, not an empty card.
 */
import { pill } from './theme'

export type IslandSize = { w: number; h: number }

/** A pill whose row hasn't been measured yet (the island's first frame). */
export const PILL_FALLBACK: IslandSize = { w: 120, h: pill.height }

/**
 * @param fixed     the mode's card width; undefined for a pill-sized mode
 * @param measured  the layer's offsetWidth / offsetHeight; undefined when the layer was never found
 * @param pillW     the last width a pill measured (what a pill falls back to)
 */
export function islandSize(fixed: number | undefined, measured: { w: number; h: number } | undefined, pillW: number): IslandSize {
  const w = measured && Number.isFinite(measured.w) ? Math.ceil(measured.w) : 0
  const h = measured && Number.isFinite(measured.h) ? Math.ceil(measured.h) : 0
  const pillSize = { w: pillW > 0 ? pillW : PILL_FALLBACK.w, h: pill.height }
  if (fixed === undefined) return w > 0 ? { w, h: pill.height } : pillSize
  return fixed > 0 && h > 0 ? { w: fixed, h } : pillSize
}

/**
 * The size when the layer may be empty. An empty layer (nothing rendered, or its Boundary fell back to the resting
 * pill) renders the pill inside a max-content layer, so it measures ~120 x 34: with a card's `fixed` width that would
 * be a card-wide 34px bar. While empty the island is the pill, whatever the mode's card width.
 */
export function islandSizeFor(fixed: number | undefined, empty: boolean, measured: { w: number; h: number } | undefined, pillW: number): IslandSize {
  return islandSize(empty ? undefined : fixed, measured, pillW)
}
