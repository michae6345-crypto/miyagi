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

export const useSpotlight = create<{ target?: SpotlightTarget }>(() => ({ target: undefined }))
const clear = (): void => useSpotlight.setState({ target: undefined })

onUi('reset', clear)
onMessage('lesson.ready', clear)
onMessage('step.started', clear)
onMessage('step.passed', clear)
onMessage('spotlight', (p) => {
  if ('clear' in p) return clear()
  const next = p as SpotlightTarget
  const prev = useSpotlight.getState().target
  // The engine re-sends the same target every screen read; ignore OCR jitter so the hole doesn't wobble.
  if (prev && prev.caption === next.caption && prev.matched === next.matched && prev.code === next.code && sameRect(prev.rect, next.rect)) return
  useSpotlight.setState({ target: next })
})
