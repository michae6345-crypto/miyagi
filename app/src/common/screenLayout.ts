/**
 * Video-lesson screen layout (Michael, Nov 25, after the MacBook Neo test: "VS Code in the middle, the video on the
 * right, it's a mess"). One pure function, shared by every window that is placed for a video lesson:
 *
 *   videoLayout(workArea) -> { editor, column, player, panel, stacked }
 *
 *   editor   VS Code: the left EDITOR_FRACTION of the work area (60%), never leaving the right column under MIN_COLUMN.
 *            The engine moves VS Code there (server/workspace/layout.py video_editor_w: the same numbers, checked
 *            against the same cases in shared/layout-cases.json by both test suites).
 *   column   the rest, on the right: the player and the steps drawer live here, never over VS Code.
 *   player   the video player window (main/features/player.ts, via core/geometry.ts dockRect).
 *   panel    the steps drawer in a video lesson (renderer features/drawer/geometry.ts, right side).
 *   stacked  true when the column is too narrow for the player and the drawer side by side (a 1440x900-class Mac):
 *            the player on top (16:9 video plus its chrome), the drawer below it. Wide screens (2560x1440): the player
 *            on the left of the column, the drawer at the right edge, both full height.
 *
 * Work-area points, top-left origin (Electron's display.workArea, or a window-local copy of it: every rect comes back
 * in the same space as the input). Pure: no Electron, no DOM. Whoever places a window calls it once per lesson start;
 * a window the learner moves afterwards is theirs (lay out once, then only follow).
 */

export type Box = { x: number; y: number; width: number; height: number }

export const VIDEO_LAYOUT = {
  /** VS Code's share of the work area's width. */
  editorFraction: 0.6,
  /** The right column never gets narrower than this (the player's minWidth 360 plus air). */
  minColumn: 400,
  /** Air between the column's windows and the work area's edges. */
  inset: 8,
  /** Air between the player and the drawer. */
  gap: 16,
  /** The drawer's width when it stands beside the player. */
  panelW: 340,
  /** Narrower than this, the player stacks above the drawer instead of beside it. */
  playerMinW: 480,
  /** The player's header and controls around the 16:9 video (its chapter list scrolls in what is left). */
  playerChrome: 150,
  /** The player window's minHeight (main/features/player.ts). */
  minPlayerH: 320,
  /** The drawer keeps at least this much below a stacked player. */
  minPanelH: 300
} as const

export type VideoLayout = { editor: Box; column: Box; player: Box; panel: Box; stacked: boolean }

/** VS Code's width in a video lesson (the engine's video_editor_w rounds the same way: half up). */
export function videoEditorWidth(width: number, fraction: number = VIDEO_LAYOUT.editorFraction): number {
  return Math.round(Math.max(0, Math.min(width * fraction, width - VIDEO_LAYOUT.minColumn)))
}

export function videoLayout(wa: Box, fraction: number = VIDEO_LAYOUT.editorFraction): VideoLayout {
  const L = VIDEO_LAYOUT
  const editorW = videoEditorWidth(wa.width, fraction)
  const editor = { x: wa.x, y: wa.y, width: editorW, height: wa.height }
  const column = { x: wa.x + editorW, y: wa.y, width: wa.width - editorW, height: wa.height }
  const inner = { x: column.x + L.inset, y: wa.y + L.inset, width: Math.max(0, column.width - L.inset * 2), height: Math.max(0, wa.height - L.inset * 2) }
  const besideW = inner.width - L.gap - L.panelW
  if (besideW >= L.playerMinW) {
    const player = { x: inner.x, y: inner.y, width: besideW, height: inner.height }
    const panel = { x: inner.x + besideW + L.gap, y: inner.y, width: L.panelW, height: inner.height }
    return { editor, column, player, panel, stacked: false }
  }
  const ideal = Math.round((inner.width * 9) / 16) + L.playerChrome
  const most = Math.max(L.minPlayerH, inner.height - L.gap - L.minPanelH)
  const playerH = Math.min(Math.max(ideal, L.minPlayerH), most)
  const player = { x: inner.x, y: inner.y, width: inner.width, height: playerH }
  const panelY = inner.y + playerH + L.gap
  const panel = { x: inner.x, y: panelY, width: inner.width, height: Math.max(0, inner.y + inner.height - panelY) }
  return { editor, column, player, panel, stacked: true }
}
