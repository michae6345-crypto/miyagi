/**
 * Where the player docks: the right 40% of the work area, inset 8px, ending above the shortcut bar
 * (which sits 24px above the dock/taskbar, ~80px tall). Pure math, shared by the main process
 * (src/main/features/player.ts) and the browser stage, so both put it in the same place.
 *
 * v2 (W0-5): the math moved to core/geometry.ts; this file re-exports it so every import keeps working.
 */
export { dockRect, DOCK_FRACTION, type Box } from '../../core/geometry'
