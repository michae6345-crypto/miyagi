/**
 * Feature: buddy. The back and forth (talk.ts), wired to the app: the engine's status, the Explain action, and push
 * to talk. And today's pointing (pointing.ts spotlit): the spotlight's boxes. Loaded for its side effects by index.tsx. Kept apart from talk.ts because these imports need the app's
 * bridge, and talk.ts is checked offline.
 */
import { onMessage } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { sendAction, usePressed } from '../../core/shortcuts'
import { spotlit } from './pointing'
import { engineThinking, setActivity, setEngine } from './talk'

// Explain from the bubble is the step's Explain action; the mark's label goes with it.
setEngine({
  canExplain: () => !!useLesson.getState().lesson,
  explain: (label) => sendAction('explain', label)
})

// The engine is thinking about what the learner asked; when it stops, so does the buddy.
useLesson.subscribe((s, prev) => {
  if (s.engineState === prev.engineState) return
  if (s.engineState === 'thinking') engineThinking(true)
  else if (prev.engineState === 'thinking') engineThinking(false)
})

// Push to talk (Michael's features/ptt): the buddy comes over and listens while the keys are held, and thinks from
// the moment they are let go. Loaded late: this feature loads early (features load A to Z) and a static import
// would pull ptt's own import chain in out of order.
if (typeof window !== 'undefined') {
  void import('../ptt/store')
    .then(({ usePtt }) => {
      usePtt.subscribe((s, prev) => {
        const now = s.ptt.phase
        if (now === prev.ptt.phase && s.ptt.text === prev.ptt.text) return
        if (now === 'arming' || now === 'listening') setActivity('listening', s.ptt.text)
        else if (now === 'sending') setActivity('thinking')
        else if (prev.ptt.phase === 'arming' || prev.ptt.phase === 'listening') setActivity('idle')
      })
    })
    .catch(() => undefined)
}

// Today's pointing: a new spotlight box gets the buddy too, until the engine sends its own annotate (pointing.ts
// spotlit; the same bridge as Michael's features/annotate/store.ts). Read from the spotlight store (read-only), so its
// calm gate and front-app rule apply here too. Loaded late, for the same reason as push to talk above.
if (typeof window !== 'undefined') {
  void import('../spotlight/store')
    .then(({ useSpotlight }) => {
      /** A Show me press not yet answered by a new spotlight box. */
      let showMeAsked = false
      usePressed.subscribe((p, was) => {
        if (!p.kind || (p.kind === was.kind && p.at === was.at)) return
        showMeAsked = p.kind === 'show_me'
      })
      onMessage('step.started', () => {
        showMeAsked = false
      })
      useSpotlight.subscribe((s, prev) => {
        if (s.target === prev.target) return
        const again = !!s.target && s.showMe && showMeAsked
        if (again) showMeAsked = false
        spotlit(s.target?.rect, again)
      })
    })
    .catch(() => undefined)
}
