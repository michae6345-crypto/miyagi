/**
 * Feature: spotlight. The current screen-first spotlight target (screen points), the coach's other
 * targets, and how long a spotlight lives.
 *
 * Lifetime (Michael's P0-2: "Show me / Explain / Hint must visibly point at my screen"): a spotlight
 * STAYS until `spotlight {clear:true}`, the step moves on (step.started / step.passed clear it at once, so the
 * old step's box never lingers into the new one), or the lesson ends or resets. There is no timeout.
 *
 * Timing (Michael's tests 2-3, A9): the latest spotlight message always wins (a clear followed by a new target is
 * a move; a target followed by a clear is gone), and the spotlight's lifetime is NOT tied to the card it came with:
 * closing a card leaves the box up until the engine clears it.
 *
 * Front app (review A9: "draw it only while spotlight.app is the front app"): while another app is in front, the box
 * and caption hide; the target is kept and comes back when its app does (unless the engine cleared or moved it
 * meanwhile). Only when the payload names an app and main knows the front one (macOS: main/features/front-app.ts,
 * read through features/shortcut-bar/front.ts); miyagi's own windows in front keep it.
 */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { onMessage, onUi } from '../../core/bus'
import { usePressed } from '../../core/shortcuts'
import { useFront } from '../shortcut-bar/front'
import { sameRect } from './place'

export type SpotlightTarget = Exclude<Payload<'spotlight'>, { clear: true }> & { code?: string }
/** A box the coach points at (`card.targets` / `offtrack.targets`), screen points. The engine spotlights targets[0]. */
export type CoachTarget = NonNullable<Payload<'card'>['targets']>[number]

/**
 * Cut-order switch (FRONTEND-HANDOFF → "Cut order"): 'dim' = full-screen dim with a rounded cut-out
 * (the real thing); 'outline' = only the hairline ring at the rect, no dim. Flip this one constant
 * to cut the dim; in the browser stage `?spotlight=outline` (or `?spotlight=dim`) overrides it.
 */
export type SpotlightMode = 'dim' | 'outline'
export const SPOTLIGHT_MODE: SpotlightMode = 'dim'

export function spotlightMode(): SpotlightMode {
  const q = typeof location === 'undefined' ? null : new URLSearchParams(location.search).get('spotlight')
  return q === 'outline' || q === 'dim' ? q : SPOTLIGHT_MODE
}

/** A clear followed this quickly by a new spotlight is a move (the cut-out springs), not a fade out and back in. */
export const REPLACE_GRACE_MS = 800
/** Rect changes smaller than this (px, any edge) are OCR jitter: the hole stays put (Michael, live test: "jumpy"). */
export const JITTER_PX = 8

/**
 * showMe: the current target answers a Show me press, so it keeps the strong dim (scrim.spotlight). Anything else in a
 * "Just teach me" lesson (the step's "type here" target) gets the soft one, so the learner's own code stays readable
 * (Michael's audit A6). See Spotlight.tsx.
 */
export const useSpotlight = create<{ target?: SpotlightTarget; targets: CoachTarget[]; showMe: boolean }>(() => ({ target: undefined, targets: [], showMe: false }))
const set = useSpotlight.setState
const get = useSpotlight.getState

/** The engine's current target, drawn or not (`target` is undefined while its app isn't in front). */
let current: SpotlightTarget | undefined

/** The target's app is known and another (non-miyagi) app is in front. */
function offApp(t: SpotlightTarget | undefined): boolean {
  const app = t?.app?.trim().toLowerCase()
  const f = useFront.getState()
  return !!app && f.known && !f.miyagi && !f.aliases.includes(app)
}

/** Keep `current` and draw it only while its app is in front. */
function put(t: SpotlightTarget | undefined, showMe: boolean): void {
  current = t
  set({ target: offApp(t) ? undefined : t, showMe })
}

useFront.subscribe(() => {
  const shown = offApp(current) ? undefined : current
  if (shown !== get().target) set({ target: shown })
})

let pendingClear: ReturnType<typeof setTimeout> | undefined

function clearNow(): void {
  clearTimeout(pendingClear)
  pendingClear = undefined
  current = undefined
  set({ target: undefined, targets: [], showMe: false })
}

/**
 * The last Show me press, for as long as a spotlight can still be its answer: core clears `usePressed` the moment
 * the spotlight arrives (maybe before our handler runs), so keep our own copy. Another press, a new step or a
 * reset ends it, and so does SHOW_ME_MS without an answer.
 */
const SHOW_ME_MS = 30_000
let showMePressedAt = 0
usePressed.subscribe((s) => {
  if (s.kind) showMePressedAt = s.kind === 'show_me' ? s.at : 0
})
const answersShowMe = (): boolean => usePressed.getState().kind === 'show_me' || (showMePressedAt > 0 && Date.now() - showMePressedAt < SHOW_ME_MS)
const forgetShowMe = (): void => {
  showMePressedAt = 0
}
onUi('reset', forgetShowMe)
onMessage('step.started', forgetShowMe)
onMessage('step.passed', forgetShowMe)

/** Clear, but give a replacement that's already on its way a beat to arrive (no dim flash). */
function clearSoon(): void {
  if (!current) return clearNow()
  clearTimeout(pendingClear)
  pendingClear = setTimeout(clearNow, REPLACE_GRACE_MS)
}

const validTargets = (t: CoachTarget[] | undefined): CoachTarget[] =>
  (t ?? []).filter((x) => x && x.rect && [x.rect.x, x.rect.y, x.rect.w, x.rect.h].every(Number.isFinite) && x.rect.w > 0 && x.rect.h > 0)

onUi('reset', clearNow) // dev reset, reconnect, and engine lesson.ended (core turns it into a reset)
onMessage('lesson.ready', clearNow)
onMessage('lesson.ended', clearNow)
// A clear lands together with the new step: no grace, the old step's box must not sit over the new step's code.
onMessage('step.started', clearNow)
onMessage('step.passed', clearNow)

onMessage('spotlight', (p) => {
  if ('clear' in p) return clearSoon()
  clearTimeout(pendingClear)
  pendingClear = undefined
  const next = p as SpotlightTarget
  const prev = current
  // A re-spotlight: the engine re-sends the same target every screen read. Ignore OCR jitter so the hole doesn't wobble.
  const still = !!(prev && next.rect && sameRect(prev.rect, next.rect, JITTER_PX))
  if (prev && still && prev.caption === next.caption && prev.matched === next.matched && prev.code === next.code && prev.snippet === next.snippet) return
  // A Show me answer keeps its strong dim while the engine re-reads it (new words at the same place).
  const showMe = answersShowMe() || (still && get().showMe)
  // New words at (nearly) the same place: keep the old rect so only the caption changes.
  put(still && prev ? { ...next, rect: prev.rect } : next, showMe)
})

// The coach's targets: the engine spotlights targets[0]; the rest are drawn as extra cut-outs while it's up.
onMessage('card', (p) => set({ targets: validTargets(p.targets) }))
onMessage('offtrack', (p) => set({ targets: validTargets(p.targets) }))
