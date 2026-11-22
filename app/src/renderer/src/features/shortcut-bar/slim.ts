/**
 * Slim shortcut bar (video lessons): while the steps drawer is open the bar drops to one quiet row of icons.
 *
 * The drawer already carries the steps and their checks and the player carries Check my work, Replay and Skip step, so
 * the full 78px bar (labels, keycaps, three step buttons) was the third loud surface. The slim row keeps every action
 * (nothing is removed, keys and tooltips still name each one) and gives the drawer the stage. Close the drawer and the
 * full bar comes back. A "Just teach me" lesson has no player, so its bar never slims.
 */
/** The slim row's height: 8px padding around 36px icon tiles. */
export const SLIM_HEIGHT = 52

export function isSlim(drawerOpen: boolean, textLesson: boolean): boolean {
  return drawerOpen && !textLesson
}
