/**
 * Feature: player. Minimize the player window to a small handle (its header only) and back (Michael, Nov 25: a hide
 * control on each overlay surface). Pure math shared by main (src/main/features/player.ts) and tests.
 *
 * The handle keeps the full window's top-right corner, so it stays where the player was (docked on the right: the
 * corner by the screen's edge). Restoring grows the full size back from wherever the handle is now (the learner may
 * have dragged it), kept inside the work area.
 */
import type { Box } from '../../core/geometry'

/** The handle: the header's height (Player.tsx Header is 44 px), wide enough for the title, the dot and restore. */
export const MINI = { width: 240, height: 44 } as const

/** The handle for a full window at `full`: same top-right corner. */
export function miniRect(full: Box): Box {
  return { x: Math.round(full.x + full.width - MINI.width), y: Math.round(full.y), width: MINI.width, height: MINI.height }
}

/** The full window back, grown from the handle's top-right corner, inside `area` (as much of it as fits). */
export function restoreRect(full: Box, mini: Box, area: Box): Box {
  const width = Math.min(full.width, area.width)
  const height = Math.min(full.height, area.height)
  const right = mini.x + mini.width
  const x = Math.min(Math.max(area.x, right - width), area.x + area.width - width)
  const y = Math.min(Math.max(area.y, mini.y), area.y + area.height - height)
  return { x: Math.round(x), y: Math.round(y), width, height }
}
