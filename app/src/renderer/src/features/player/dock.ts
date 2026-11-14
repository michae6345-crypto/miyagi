/**
 * Where the player docks: the right 40% of the work area, inset 8px, ending above the shortcut bar
 * (which sits 24px above the dock/taskbar, ~80px tall). Pure math, shared by the main process
 * (src/main/features/player.ts) and the browser stage, so both put it in the same place.
 */
export type Box = { x: number; y: number; width: number; height: number }

export const DOCK_FRACTION = 0.4
const INSET = 8
/** Shortcut bar (80) + its 24px gap + a little air, so the bar never covers the chapter list. */
const BAR_CLEARANCE = 112

export function dockRect(workArea: Box): Box {
  const width = Math.round(workArea.width * DOCK_FRACTION) - INSET * 2
  return {
    x: workArea.x + workArea.width - width - INSET,
    y: workArea.y + INSET,
    width,
    height: Math.max(320, workArea.height - INSET * 2 - BAR_CLEARANCE)
  }
}
