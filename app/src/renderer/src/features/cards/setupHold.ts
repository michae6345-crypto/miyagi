/**
 * When a setup card holds the video, and when the drawer says "Waiting on setup" (smart setup, Nov 22).
 *
 * Setup is a companion, not a gate: the engine sends `setup.holdVideo` (true only when the step on screen truly needs a
 * missing tool that Install can get now). A card without the field (an older engine) keeps the old rule: any setup
 * card with buttons holds. Rows the learner settled ("I have it": haveIt; a free alternative chosen: using) never wait.
 * Pure, so tests can check it without the player or the drawer.
 */
import type { Payload } from '../../../../common/wire'

type Card = Payload<'card'>
type Row = NonNullable<Card['items']>[number]

/** A setup card waiting on the learner: the video holds under it ("Set up first"). A passing note (no buttons) is not. */
export function setupWaiting(c: Card | undefined): boolean {
  if (c?.kind !== 'setup') return false
  const hold = c.setup?.holdVideo
  return hold === undefined ? (c.actions?.length ?? 0) > 0 : hold === true
}

/** A row still waiting: needed, not ready, and not settled by the learner (haveIt / using). */
export const rowWaiting = (x: Row): boolean => x.needed && !x.ok && !x.haveIt && !x.using

/** A row the learner settled: "I have it" (haveIt) or a free alternative instead (using). */
export const rowSettled = (x: Row): boolean => !!x.haveIt || !!x.using

/**
 * A licensed app's row (AutoCAD) on a card that draws I have it / Get it / the free alternative itself: the row keeps
 * no button of its own (its install.method "download" would be a second Get it).
 */
export const drawnOnCard = (actions: readonly string[] | undefined, x: Row): boolean =>
  x.setupKind === 'licensed_app' && !!actions?.includes('get_it')

/** The drawer's current step reads "Waiting on setup": a setup card that holds the video and has a row still waiting. */
export function waitingOnSetup(c: Card | undefined): boolean {
  if (c?.kind !== 'setup' || c.setup?.holdVideo === false) return false
  return (c.setup?.items ?? c.items ?? []).some(rowWaiting)
}
