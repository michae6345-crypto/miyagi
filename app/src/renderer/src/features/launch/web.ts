/**
 * Feature: launch. Browser-stage stand-in for main/features/launch.ts (does nothing in Electron).
 *
 *   launch:menu ({x, y})   draws the pill menu in the page at that point (StageMenu), as the native menu would be
 *   ?menu                  opens it under the pill once the stage is up (for shots)
 * The stage has no menu bar item and no Dock: the menu's rows do what the Tray's do (Quit just closes the menu).
 */
import { create } from 'zustand'
import { STAGE, bridge, isElectron, registerWebHandler } from '../../bridge'
import { pill } from '../../core/theme'

export type MenuAt = { x: number; y: number }
export const useStageMenu = create<{ at?: MenuAt }>(() => ({}))
export const closeStageMenu = (): void => useStageMenu.setState({ at: undefined })

function setupWeb(): void {
  registerWebHandler('launch:menu', (p) => {
    const at = p as Partial<MenuAt> | undefined
    if (!Number.isFinite(at?.x) || !Number.isFinite(at?.y)) return false
    useStageMenu.setState({ at: { x: at!.x!, y: at!.y! } })
    return true
  })
  if (new URLSearchParams(location.search).has('menu')) {
    // Under the pill's right half, where a right-click on it opens it.
    setTimeout(() => useStageMenu.setState({ at: { x: Math.round(STAGE.width / 2) + 40, y: bridge.platform.pillTop + pill.height + 6 } }), 1200)
  }
}

if (!isElectron) setupWeb()
