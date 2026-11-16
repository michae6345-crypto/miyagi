/**
 * Feature: overview. The code to type for the current step (contract step.started.code, then spotlight.snippet: "Just teach me" steps and
 * Show me). The step card shows it under the instructions (Michael, Sat 3:23 PM), and it stays there after the
 * spotlight itself clears. A new step, or any reset, drops it.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'

export const useStepSnippet = create<{ stepId?: string; code?: string }>(() => ({}))
const set = useStepSnippet.setState
const none = { stepId: undefined, code: undefined }

onMessage('spotlight', (p) => {
  if ('clear' in p) return
  const code = p.snippet?.replace(/\s+$/, '')
  if (code) set({ stepId: useLesson.getState().stepId, code })
})
onMessage('step.started', (p) => {
  // The step's own code (contract step.started.code) is the snippet until a spotlight sends one (Michael, test 10:
  // in video lessons the code was only in the closed drawer).
  const code = p.code?.replace(/\s+$/, '')
  if (code) set({ stepId: p.stepId, code })
  else if (useStepSnippet.getState().stepId !== p.stepId) set(none)
})
onUi('reset', () => set(none))
