/**
 * Feature: launch (brief: app/agents/launch-ease.md). Renderer side of main/features/launch.ts.
 *
 *   - Right-click the pill: the miyagi menu at the pointer (Open miyagi, Start a lesson, Settings…, Quit miyagi), the
 *     same one as the menu bar item. In Electron it's a native menu (bridge.invoke('launch:menu', {x, y})); if it can't
 *     open, Settings opens instead, so a right-click is never dead. This replaced the gear that was glued to the
 *     pill's right edge (it covered the status dot on Michael's Mac). Pill-sized only: cards keep their own clicks.
 *   - feat:launch:open from main (the menu bar item, the pill menu), sent to the overlay window only: 'launcher' opens
 *     the launcher, 'settings' grows Settings out of the pill.
 * Browser stage: web.ts stands in for main and draws the menu in the page (StageMenu).
 */
import { useEffect, useRef, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { useIslandBox } from '../../core/Island'
import { defineFeature } from '../../core/registry'
import { openSettings } from '../../core/surfaces'
import { StageMenu } from './StageMenu'
import './web'

bridge.onFeature('launch:open', (what) => {
  if (what === 'launcher') bridge.emit('launcher:toggle')
  else if (what === 'settings') void openSettings()
})

/** Air between the pill's bottom edge and the menu. */
const MENU_GAP = 6

/** Listens for a right-click on the pill; draws nothing itself (the stage's menu stand-in aside). */
function PillMenu(): ReactNode {
  const holder = useRef<HTMLDivElement>(null)
  const island = useIslandBox()
  const islandRef = useRef(island)
  islandRef.current = island

  useEffect(() => {
    const root = holder.current?.parentElement // the overlay root
    if (!root) return
    const onMenu = (e: MouseEvent): void => {
      const t = e.target instanceof Element ? e.target : null
      if (!t?.closest('[data-island-layer]') || !islandRef.current.pill) return
      e.preventDefault()
      // Overlay coordinates (the stage scales the overlay with CSS; Electron's scale is 1).
      const box = root.getBoundingClientRect()
      const k = box.width ? root.offsetWidth / box.width : 1
      // At the pointer's x, just under the pill: the menu never covers the pill's own words, count or status dot.
      const i = islandRef.current
      const under = i.h > 0 ? i.y + i.h + MENU_GAP : 0
      const at = { x: Math.round((e.clientX - box.left) * k), y: Math.round(Math.max((e.clientY - box.top) * k, under)) }
      bridge
        .invoke<boolean>('launch:menu', at)
        .then((ok) => {
          if (!ok) void openSettings()
        })
        .catch(() => void openSettings())
    }
    root.addEventListener('contextmenu', onMenu)
    return () => root.removeEventListener('contextmenu', onMenu)
  }, [])

  return (
    <div ref={holder} className="pointer-events-none absolute inset-0">
      <StageMenu />
    </div>
  )
}

export default defineFeature({
  id: 'launch',
  // Over the island (50) like the gear it replaces, under the shortcut bar (60).
  overlayLayers: [{ id: 'launch-pill-menu', z: 55, Component: PillMenu }]
})
