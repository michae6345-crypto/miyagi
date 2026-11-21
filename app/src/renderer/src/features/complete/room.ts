/**
 * How tall the completion card may grow: from the island's top (platform.pillTop) down to the usable screen's bottom
 * (the work area, so the Dock stays clear), less 16 px. An invisible overlay layer reports it, the same way the cards
 * feature reports the overlay's width.
 */
import { useEffect, type ReactNode } from 'react'
import { create } from 'zustand'
import type { Layout } from '../../../../preload/api'
import { bridge } from '../../bridge'

const MARGIN = 16

export const useRoom = create<{ h: number }>(() => ({ h: typeof window === 'undefined' ? 900 : window.innerHeight - 56 }))

export function roomFor(layout: Layout, top: number): number {
  const wa = layout.workArea
  // workArea is in screen points; the overlay's own top-left is layout.origin.
  const waBottom = wa && wa.height > 0 ? wa.y - layout.origin.y + wa.height : layout.height
  const bottom = Math.min(layout.height, waBottom)
  return Math.max(240, Math.floor(bottom - top - MARGIN))
}

export function RoomProbe({ layout }: { layout: Layout }): ReactNode {
  const h = roomFor(layout, bridge.platform.pillTop)
  useEffect(() => useRoom.setState({ h }), [h])
  return null
}
