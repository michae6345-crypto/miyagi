/**
 * Feature: buddy. The back and forth: what the buddy is doing besides pointing, and what it says.
 *
 * A buddy you can talk to (Adrian, Nov 22: "any part you're confused, you talk to it... a lot of this back and
 * forth"). The talking itself is Michael's: push to talk (features/ptt), circle to ask and the engine's answers.
 * This is the buddy's side of it, so there is someone there while it happens:
 *   summoned   it is out on the screen keeping the learner's pointer company (Clicky's cursor does this), not home
 *              in the notch. It comes when the learner starts talking and lingers a while after it is done.
 *   activity   'listening' while the learner holds the keys (it perks up and shows what it hears), 'thinking' from
 *              the moment they let go until the engine answers.
 *   say        a sentence of its own: an answer card's first sentence, said beside what the answer points at.
 * And the learner can answer back without talking: the chips in its bubble (reply()).
 *
 * Wired to what is really there today: answer cards and Esc here (the bus), and in wire.ts the engine's status
 * (thinking), the Explain action and push to talk's state. This file imports nothing that needs the app's bridge,
 * so it is checked offline (test/buddyTalk.test.ts). The browser stage's try-out (PointStage.tsx) drives the same
 * functions by hand.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { fade, reached, usePointing } from './pointing'
import { firstSentence } from './trip'

export type Activity = 'idle' | 'listening' | 'thinking'

export const useTalk = create<{ summoned: boolean; activity: Activity; heard: string; say?: string; sayFor?: string }>(() => ({ summoned: false, activity: 'idle', heard: '' }))
const get = useTalk.getState
const set = useTalk.setState

/** After the last thing happened it stays by the pointer this long, then goes home. */
export const LINGER_MS = 7000
let linger: ReturnType<typeof setTimeout> | undefined
/** The learner asked something and the answer has not come yet: the engine's "thinking" is about that. */
let asked = false

/** Something happened: it stays out, and the clock to go home starts again (when there is nothing left to point at). */
function stay(): void {
  clearTimeout(linger)
  linger = undefined
  if (!get().summoned) return
  if (get().activity !== 'idle' || usePointing.getState().marks.length) return
  linger = setTimeout(() => set({ summoned: false, say: undefined, sayFor: undefined }), LINGER_MS)
}

/** Call it out to keep the pointer company. */
export function summon(): void {
  if (!get().summoned) set({ summoned: true })
  stay()
}

/** Send it home now. */
export function sendHome(): void {
  clearTimeout(linger)
  linger = undefined
  asked = false
  set({ summoned: false, activity: 'idle', heard: '', say: undefined, sayFor: undefined })
}

/** The learner is talking (`heard`: the words so far), has stopped and is waiting, or neither. */
export function setActivity(activity: Activity, heard = ''): void {
  if (activity !== 'idle') summon()
  if (activity === 'thinking') asked = true
  if (activity === 'idle') asked = false
  if (get().activity !== activity || get().heard !== heard) set({ activity, heard, ...(activity === 'listening' ? { say: undefined, sayFor: undefined } : {}) })
  stay()
}

/** It says a sentence of its own. `forKey`: beside that mark (else wherever it is). Nothing: it stops. */
export function say(text?: string, forKey?: string): void {
  const line = text ? firstSentence(text) : undefined
  if (line) summon()
  set({ say: line || undefined, sayFor: line ? forKey : undefined })
  stay()
}

/**
 * The learner answers back from the bubble.
 *   got      "Got it": they have it. The buddy cheers and moves on (the same as getting to the mark).
 *   next     the next step of a tour, without the cheer.
 *   explain  "Explain": ask the engine to explain (the step's Explain action; the mark's label goes with it).
 * `responder`: the browser stage's stand-in for the engine; returns true when it took the reply.
 */
export type ReplyKind = 'got' | 'next' | 'explain'
let responder: ((kind: ReplyKind, key: string) => boolean) | undefined
export function setResponder(fn: typeof responder): void {
  responder = fn
}
/** The engine's side of Explain: whether there is a lesson to explain, and the ask itself. Set by wire.ts. */
export type Engine = { canExplain: () => boolean; explain: (label?: string) => void }
let engine: Engine | undefined
export function setEngine(e: Engine | undefined): void {
  engine = e
}
export function canExplain(): boolean {
  return !!responder || !!engine?.canExplain()
}
export function reply(kind: ReplyKind, key: string): void {
  if (responder?.(kind, key)) return
  if (kind === 'got') return reached([key])
  if (kind === 'next') return fade([key])
  if (!engine) return
  setActivity('thinking')
  engine.explain(usePointing.getState().marks.find((m) => m.key === key)?.label)
}

/**
 * The engine started or stopped thinking (wire.ts). It is the buddy's thinking only when the learner asked the
 * buddy something; when the engine stops, so does the buddy.
 */
export function engineThinking(now: boolean): void {
  if (now && asked && get().summoned) setActivity('thinking')
  else if (!now && get().activity === 'thinking') setActivity('idle')
}

// ---- wired to what is really there ---------------------------------------------------------------------------

// When there is nothing left to point at, the clock to go home starts; while there is, it stays.
usePointing.subscribe((s, prev) => {
  if (s.marks === prev.marks) return
  // What it said about a mark goes with the mark.
  const about = get().sayFor
  if (about && !s.marks.some((m) => m.key === about)) set({ say: undefined, sayFor: undefined })
  if (s.marks.length !== prev.marks.length) stay()
})

// An answer card while the buddy is out: it says the first sentence, beside the mark the answer points at if one is
// up. (The card itself is the cards feature's; this is the buddy saying it.)
onMessage('card', (p) => {
  if (p.kind !== 'answer' || !get().summoned || !p.body) return
  const at = usePointing.getState().marks.find((m) => m.why === 'answer')
  say(p.body, at?.key)
})

onUi('dismiss', () => {
  sendHome() // Esc: the learner wants the screen back. Never claims the event.
})
onUi('reset', sendHome)
onMessage('lesson.ended', sendHome)
