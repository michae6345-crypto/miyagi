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

/**
 * A setup card waiting on the learner: the video holds under it. A passing note (no buttons) is not. An older engine
 * (no holdVideo) holds for a card with something to do, but not for one whose only button is Skip: nothing on it can
 * get the tool (Michael, Nov 22: "Set up first" over the AutoCAD video, Skip the only button).
 */
export function setupWaiting(c: Card | undefined): boolean {
  if (c?.kind !== 'setup') return false
  const hold = c.setup?.holdVideo
  return hold === undefined ? (c.actions ?? []).some((a) => a !== 'skip_setup') : hold === true
}

/** A row still waiting: needed, not ready, and not settled by the learner (haveIt / using). */
export const rowWaiting = (x: Row): boolean => x.needed && !x.ok && !x.haveIt && !x.using

/** A row the learner settled: "I have it" (haveIt) or a free alternative instead (using). */
export const rowSettled = (x: Row): boolean => !!x.haveIt || !!x.using

/** The paid-app actions the setup card draws itself (setupPlan.ts). */
const APP_ACTIONS: readonly string[] = ['have_it', 'get_it', 'alternative']

/**
 * A licensed app's row (AutoCAD) whose I have it / Get it / free alternative the card draws itself: the row keeps no
 * button of its own (its install.method "download" would be a second Get it). The engine sends those actions on the
 * card (APP_RENDERS_APP_ACTIONS) or only on the row (today's engine): either counts.
 */
export const drawnOnCard = (actions: readonly string[] | undefined, x: Row): boolean =>
  x.setupKind === 'licensed_app' && (!!actions?.includes('get_it') || !!x.actions?.some((a) => APP_ACTIONS.includes(a)))

/** The drawer's current step reads "Waiting on setup": a setup card that holds the video and has a row still waiting. */
export function waitingOnSetup(c: Card | undefined): boolean {
  if (c?.kind !== 'setup' || c.setup?.holdVideo === false) return false
  return (c.setup?.items ?? c.items ?? []).some(rowWaiting)
}
