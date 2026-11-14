/** Feature: spotlight. The current screen-first spotlight target (screen points). */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { onMessage, onUi } from '../../core/bus'
import { sameRect } from './place'

export type SpotlightTarget = Exclude<Payload<'spotlight'>, { clear: true }> & { code?: string }

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

/** On step.passed the ring turns green (status color) for a beat, then the spotlight fades out. */
export const PASS_HOLD_MS = 900

export const useSpotlight = create<{ target?: SpotlightTarget }>(() => ({ target: undefined }))
let passTimer: ReturnType<typeof setTimeout> | undefined
const clear = (): void => {
  clearTimeout(passTimer)
  useSpotlight.setState({ target: undefined })
}

onUi('reset', clear)
onMessage('lesson.ready', clear)
onMessage('step.started', clear)
onMessage('step.passed', () => {
  if (!useSpotlight.getState().target) return
  clearTimeout(passTimer)
  passTimer = setTimeout(clear, PASS_HOLD_MS)
})
onMessage('spotlight', (p) => {
  if ('clear' in p) return clear()
  clearTimeout(passTimer)
  const next = p as SpotlightTarget
  const prev = useSpotlight.getState().target
  // The engine re-sends the same target every screen read; ignore OCR jitter so the hole doesn't wobble.
  if (prev && prev.caption === next.caption && prev.matched === next.matched && prev.code === next.code && sameRect(prev.rect, next.rect)) return
  useSpotlight.setState({ target: next })
})
