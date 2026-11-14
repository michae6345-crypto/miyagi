/** Feature: spotlight. The current screen-first spotlight target (screen points). */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { onMessage, onUi } from '../../core/bus'

export type SpotlightTarget = Exclude<Payload<'spotlight'>, { clear: true }> & { code?: string }

export const useSpotlight = create<{ target?: SpotlightTarget }>(() => ({ target: undefined }))
const clear = (): void => useSpotlight.setState({ target: undefined })

onUi('reset', clear)
onMessage('lesson.ready', clear)
onMessage('step.started', clear)
onMessage('step.passed', clear)
onMessage('spotlight', (p) => useSpotlight.setState({ target: 'clear' in p ? undefined : (p as SpotlightTarget) }))
