/**
 * Feature: buddy. The back and forth (talk.ts), wired to the app: the engine's status, the Explain action, and push
 * to talk. And today's pointing (pointing.ts spotlit): the spotlight's boxes. Loaded for its side effects by index.tsx. Kept apart from talk.ts because these imports need the app's
 * bridge, and talk.ts is checked offline.
 */
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage } from '../../core/bus'
import { canSend, useLesson } from '../../core/lesson'
import { sendAction, usePressed } from '../../core/shortcuts'
import { createBonLink } from './engine'
import { bonImported, LEVELS, localSteps, markBonImported, passStep, syncSteps } from './growth'
import { words } from './name'
import { cheer, spotlit } from './pointing'
import { engineThinking, say, setActivity, setEngine, summon } from './talk'

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

// bon's count from the engine (engine.ts, ui-v4): on every connect, bon.import once per Mac and bon.get, each only when
// the hello lists it; every `bon` (the answer, and the push after a counted pass) syncs the count, quietly.
const bon = createBonLink({
  canSend,
  send: (type, payload) => {
    if (type === 'bon.import') bridge.send(cmd('bon.import', payload as { steps: number; seen?: string[] }))
    else bridge.send(cmd('bon.get', {}))
  },
  local: localSteps,
  imported: bonImported,
  markImported: markBonImported,
  sync: syncSteps,
  pass: passStep,
  lessonId: () => useLesson.getState().lesson?.id
})
onMessage('engine.hello', (p) => bon.hello(p?.capabilities))
onMessage('bon', (p) => bon.bon(p))

// It grows each time the learner passes a step (growth.ts, engine.ts counts): a ui-v4 engine says which passes count
// (`counted`); otherwise a skipped step is not a pass, and neither is one that was already done when the lesson got to
// it. On a level-up it comes out, hops, and says its new level; Companion.tsx shows the growing itself. After
// pointing.ts's own step.passed handler has cleared the marks, so its words show.
onMessage('step.passed', (p) => {
  const level = bon.passed(p)
  if (!level) return
  summon()
  say(words.grew(level, LEVELS[level - 1].name))
  cheer()
})
