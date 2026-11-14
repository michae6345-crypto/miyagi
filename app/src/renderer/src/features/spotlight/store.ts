/**
 * Feature: spotlight. The current screen-first spotlight target (screen points), the coach's other
 * targets, and how long a spotlight lives.
 *
 * Lifetime (Michael's P0-2: "Show me / Explain / Hint must visibly point at my screen"): a spotlight
 * STAYS until `spotlight {clear:true}`, the step moves on (step.started / step.passed: the video resumes,
 * and a dim over it would hide it), the lesson ends or resets (lesson.ended arrives as a core reset), or
 * the learner dismisses the card it came with (✕ / Esc). There is no timeout.
 */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { onMessage, onUi } from '../../core/bus'
import { useCards } from '../cards/store'
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
export const REPLACE_GRACE_MS = 300
/** A card that opens this soon after its spotlight still owns it (the engine may send them in either order). */
const PAIR_MS = 1500

export const useSpotlight = create<{ target?: SpotlightTarget; targets: CoachTarget[] }>(() => ({ target: undefined, targets: [] }))
const set = useSpotlight.setState
const get = useSpotlight.getState

/** The coach card the current spotlight came with: dismissing that card clears the spotlight too. */
type CardRef = { card: Payload<'card'> } | { offtrack: true }
let cameWith: CardRef | undefined
let arrivedAt = 0
let pendingClear: ReturnType<typeof setTimeout> | undefined

function clearNow(): void {
  clearTimeout(pendingClear)
  pendingClear = undefined
  cameWith = undefined
  set({ target: undefined, targets: [] })
}

/** Clear, but give a replacement that's already on its way a beat to arrive (no dim flash). */
function clearSoon(): void {
  if (!get().target) return clearNow()
  clearTimeout(pendingClear)
  pendingClear = setTimeout(clearNow, REPLACE_GRACE_MS)
}

function openCard(): CardRef | undefined {
  const c = useCards.getState()
  if (c.card) return { card: c.card }
  if (c.offtrackOpen) return { offtrack: true }
  return undefined
}

/** Is that card still up? An off-track card under an explain card or diagram (`resume`) comes back, so it counts. */
function stillOpen(ref: CardRef): boolean {
  const c = useCards.getState()
  return 'card' in ref ? c.card === ref.card : c.offtrackOpen || c.resume
}

const validTargets = (t: CoachTarget[] | undefined): CoachTarget[] =>
  (t ?? []).filter((x) => x && x.rect && [x.rect.x, x.rect.y, x.rect.w, x.rect.h].every(Number.isFinite) && x.rect.w > 0 && x.rect.h > 0)

onUi('reset', clearNow) // dev reset, reconnect, and engine lesson.ended (core turns it into a reset)
onMessage('lesson.ready', clearNow)
onMessage('step.started', clearSoon)
onMessage('step.passed', clearSoon)

onMessage('spotlight', (p) => {
  if ('clear' in p) return clearSoon()
  clearTimeout(pendingClear)
  pendingClear = undefined
  const next = p as SpotlightTarget
  const prev = get().target
  // A re-spotlight: the engine re-sends the same target every screen read. Ignore OCR jitter so the hole doesn't wobble.
  if (prev && prev.caption === next.caption && prev.matched === next.matched && prev.code === next.code && next.rect && sameRect(prev.rect, next.rect)) return
  arrivedAt = Date.now()
  cameWith = openCard()
  set({ target: next })
})

// The coach's targets: the engine spotlights targets[0]; the rest are drawn as extra cut-outs while it's up.
onMessage('card', (p) => set({ targets: validTargets(p.targets) }))
onMessage('offtrack', (p) => set({ targets: validTargets(p.targets) }))

// A card that opens right after its spotlight still owns it.
useCards.subscribe((s, before) => {
  if (!get().target || cameWith || Date.now() - arrivedAt > PAIR_MS) return
  if ((s.card && s.card !== before.card) || (s.offtrackOpen && !before.offtrackOpen)) cameWith = openCard()
})

// ✕ / Esc: cards close their top card in their own dismiss handler; look once every handler has run.
onUi('dismiss', () => {
  const ref = cameWith
  if (!ref || !get().target) return
  queueMicrotask(() => {
    if (cameWith === ref && !stillOpen(ref)) clearNow()
  })
})
