/**
 * Where the island is, for every surface that sits under it or grows out of it (the launcher, Settings, the flyout, the
 * completion card, the overview's clear zone). In the notch the island's top is the display top and its resting bottom
 * is the notch's bottom; below the menu bar they are platform.pillTop and pillTop + the pill's height.
 * Work-area-based docks (the lesson panel, the player) don't use these.
 */
import type { Layout } from '../../../preload/api'
import { bridge } from '../bridge'
import { islandBottomAt, islandTopAt } from './notchGeometry'

/** The island's top edge in display coordinates (0 in the notch). */
export const islandTop = (layout: Layout): number => islandTopAt(layout, bridge.platform.pillTop)

/** The island's resting bottom edge in display coordinates (notch or pill). */
export const islandBottom = (layout: Layout): number => islandBottomAt(layout, bridge.platform.pillTop)
