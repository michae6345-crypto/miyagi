/**
 * Feature: ptt (renderer). Push to talk: what the island shows, and where the words go.
 *
 * Main (main/features/ptt.ts) owns the helper and the session rules and broadcasts ONE PttState (`ptt:state`); every
 * window gets it. Here:
 *   - `owned`: the island's claim while a session is on (listening / sending). Released on every terminal state, when
 *     the helper exits, when the engine link drops, on Esc, and after HARD_CAP_MS whatever happens, so the island can
 *     never stay stuck (it cooperates with core/islandState.ts's watchdog: a pill-sized mode is never "ownerless").
 *   - the first-use card: when the learner holds the chord before the microphone was ever allowed (or Input Monitoring
 *     is off), a small card asks with one explicit Allow button. A bare key press never raises a system prompt.
 *   - routing the final text (overlay window only, once per id): a lesson is running -> the same ask a typed question
 *     makes (sendAction('ask', text)); no lesson -> the launcher opens prefilled in search/build mode so the learner
 *     confirms (no surprise paid build). Empty -> nothing.
 */
import { create } from 'zustand'
import { HARD_CAP_MS } from '../../../../main/pttProtocol'
import { active, PTT_REST, type PttState } from '../../../../common/pttState'
import { bridge, isElectron } from '../../bridge'
import { onUi } from '../../core/bus'
import { gateIsOpen, onGateOpen } from '../../core/gate'
import { notify, useLesson } from '../../core/lesson'
import { usePrefs } from '../../core/prefs'
import { sendAction } from '../../core/shortcuts'
import { shouldShowInputCard } from './inputCard'
import { routeFor, type Routed } from './route'
import { createTail, type PttTiming } from './tail'
import { stripWake } from './wake'

export type PttCard = 'mic' | 'mic-denied' | 'input'

type Store = {
  ptt: PttState
  /** The island is showing the session (listening / sending). */
  owned: boolean
  /** The first-use / permission card, if showing. */
  card?: PttCard
}

export const usePtt = create<Store>(() => ({ ptt: PTT_REST, owned: false, card: undefined }))
const set = usePtt.setState
const get = usePtt.getState

/** The permission card closes by itself (nobody is at the keyboard to dismiss it): it is not a sticky surface. */
export const CARD_MS = 12_000
/** Sending never outstays this, even if main's final is lost (the helper itself waits at most 1.5 s for it). */
export const SENDING_MAX_MS = 5500

let cap: ReturnType<typeof setTimeout> | undefined
let cardTimer: ReturnType<typeof setTimeout> | undefined
let sendTimer: ReturnType<typeof setTimeout> | undefined
let seen: string | undefined
let inputCardCount = 0
let inputCardAt = 0
let inputCardDeclined = false

/** One idempotent way back to rest for the island's claim. */
export function release(): void {
  clearTimeout(cap)
  clearTimeout(sendTimer)
  cap = sendTimer = undefined
  if (get().owned) set({ owned: false })
}

export function closeCard(): void {
  clearTimeout(cardTimer)
  cardTimer = undefined
  if (get().card) set({ card: undefined })
}

function openCard(card: PttCard): void {
  clearTimeout(cardTimer)
  cardTimer = setTimeout(closeCard, CARD_MS)
  set({ card })
}

/**
 * Input Monitoring is off while push to talk is on: with no key listener a hold can never reach the helper, so the card
 * cannot wait for one. Once per run, with the same explicit Allow button, and never before the launch gate is open
 * (first-run setup is not over yet): it is asked again when the gate opens and when the pref changes.
 */
function maybeInputCard(): void {
  const facts = { shownCount: inputCardCount, sinceLastMs: Date.now() - inputCardAt, declined: inputCardDeclined, inputDenied: get().ptt.perms.input === 'denied', enabled: usePrefs.getState().ptt.enabled, gateOpen: gateIsOpen() }
  if (!shouldShowInputCard(facts)) return
  inputCardCount += 1
  inputCardAt = Date.now()
  openCard('input')
}

/** "Not now" on the Input Monitoring card: quiet for the rest of this run (Settings still has the row). */
export function declineInputCard(): void {
  inputCardDeclined = true
  closeCard()
}

// The card closes by itself; if nobody saw it, it is offered again (inputCard.ts decides when).
const reoffer = setInterval(maybeInputCard, 60_000) as unknown as { unref?: () => void }
reoffer.unref?.()

/** A new PttState from main (or the stage's mock helper). */
export function receive(next: PttState): void {
  const prev = get().ptt
  const live = next.phase === 'listening' || next.phase === 'sending'
  tail.observe(next)
  // A hold the safety net already sent (below) is done for the island, even while the helper is still finishing it.
  if (live && !get().owned && next.id !== spent) {
    set({ owned: true })
    clearTimeout(cap)
    cap = setTimeout(release, HARD_CAP_MS) // the hard cap: never longer than this, whatever main or the helper do
  }
  if (!live) release()
  if (next.phase === 'sending' && prev.phase !== 'sending') {
    clearTimeout(sendTimer)
    sendTimer = setTimeout(release, SENDING_MAX_MS)
  }
  set({ ptt: next })

  // First use: the chord went down and the microphone was never asked about. A card, never a surprise prompt.
  if (next.phase === 'arming' && prev.phase !== 'arming') {
    if (next.perms.mic === 'undetermined') openCard('mic')
    else if (next.perms.mic === 'denied') openCard('mic-denied')
  }
  if (next.phase === 'error' && prev.phase !== 'error') {
    if (next.code === 'input_denied' || next.code === 'tap_failed') openCard('input')
    else if (next.code === 'mic_undetermined') openCard('mic')
    else if (next.code === 'mic_denied') openCard('mic-denied')
    else if (next.code === 'no_stt') notify("Speech isn't ready on this Mac.")
    else if (next.code === 'assets_missing') notify('Speech files are still downloading.')
  }
  maybeInputCard()
  // Listening starts: the card has done its job.
  if (live) closeCard()
}

// Esc: the card goes, and a session in flight is cancelled.
onUi('dismiss', () => {
  closeCard()
  if (active(get().ptt)) {
    release()
    bridge.invoke('ptt:cancel').catch(() => undefined)
  }
})
// The engine link dropped: nothing can be asked now, so the island lets go.
let wasConnected = useLesson.getState().connected
useLesson.subscribe((s) => {
  if (wasConnected && !s.connected) {
    release()
    closeCard()
  }
  wasConnected = s.connected
})

// The learner's pref (Settings > General) reaches the helper through main.
usePrefs.subscribe((s, p) => {
  if (s.ptt.enabled !== p.ptt.enabled || s.ptt.chord !== p.ptt.chord) bridge.invoke('ptt:config', s.ptt).catch(() => undefined)
  if (s.ptt.enabled && !p.ptt.enabled) maybeInputCard()
})
onGateOpen(maybeInputCard)

// ---- the words ----

/** Only the overlay routes the words (every window hears the broadcast; the launcher must not ask twice). */
const isRouter = (): boolean => !isElectron || document.documentElement.dataset.route === 'overlay'

export function routeFinal(f: { id: string; text: string }): Routed {
  f = { id: f.id, text: stripWake(f.text) } // "hey miyagi, ..." asks only the words after it (wake.ts)
  if (!isRouter() || seen === f.id) return 'none'
  seen = f.id
  const text = f.text.trim()
  const lesson = useLesson.getState()
  const where = routeFor(text, !!lesson.lesson && !!lesson.stepId)
  if (where === 'ask') sendAction('ask', text)
  else if (where === 'launcher') {
    bridge
      .invoke<boolean>('ptt:prefill', text)
      // The launcher is a toggle: open it only if it isn't open already (then it takes the text from the broadcast).
      .then((ok) => ok && !launcherSignal && bridge.emit('launcher:toggle'))
      .catch(() => undefined)
  }
  return where
}

let launcherSignal = false
bridge.on('launcher:open', () => (launcherSignal = true))
bridge.on('launcher:closed', () => (launcherSignal = false))

bridge.onFeature('ptt:state', (p) => {
  if (p && typeof p === 'object') receive(p as PttState)
})
bridge.onFeature('ptt:final', (p) => {
  const f = p as { id?: unknown; text?: unknown } | undefined
  if (f && typeof f.id === 'string' && typeof f.text === 'string') finalFromHelper({ id: f.id, text: f.text })
})
bridge
  .invoke<PttState>('ptt:get')
  .then((s) => s && typeof s === 'object' && receive(s))
  .catch(() => undefined) // no helper (or the stage without a mock): push to talk stays out of sight

// ---- speed (Nov 22): the release tail's safety net, and the seams circle to ask plugs into ----

/** The hold the safety net sent: the island lets go of it at once. */
let spent: string | undefined

/** The safety net (tail.ts): if the helper sends no final within SAFETY_MS of the key-up, the last partial is the final. */
const tail = createTail((f) => {
  spent = f.id
  release()
  routeFinal(f)
  logTiming()
})

function logTiming(): void {
  const t = tail.timing()
  if (t?.releaseToFinalMs !== undefined) console.info(`[ptt] release to final ${Math.round(t.releaseToFinalMs)} ms (${t.via})`)
}

/** The helper's final (main's 'ptt:final', or the stage's mock): timed, then routed. A hold the tail already sent is not asked twice (routeFinal's seen id). */
export function finalFromHelper(f: { id: string; text: string }): Routed {
  const first = tail.timing()?.id === f.id && tail.timing()?.finalAt === undefined
  tail.final(f.id, 'helper')
  if (first) logTiming()
  return routeFinal(f)
}

/** The browser stage only: its "send" script holds the Sending face for shots, so the tail must not end it. */
export const pauseTail = (on: boolean): void => tail.pause(on)

/** The current (or last) hold's timing: down, up, final, which path, release to final in ms. */
export const pttTiming = (): PttTiming | undefined => tail.timing()

type DownFn = (d: { id: string }) => void
type PartialFn = (p: { id: string; text: string }) => void
const downFns = new Set<DownFn>()
const partialFns = new Set<PartialFn>()

/**
 * The push-to-talk keys went down (the helper's ptt down, before the 250 ms debounce). Local work only: main asks the
 * engine to warm up (ask.warm, a paid cache write) later, once the hold passes the minimum and the mic opens
 * ('listening'), so taps and Fn+Control+arrow presses cost nothing. Circle to ask: prepare the capture for this hold
 * here (prefetch SCShareableContent and our own windows to exclude), keyed by id. Returns an unsubscribe.
 */
export function onPttDown(fn: DownFn): () => void {
  downFns.add(fn)
  return () => void downFns.delete(fn)
}

/** Every new partial of the hold in flight, while the keys are held and during the tail. text has the wake word dropped. Returns an unsubscribe. */
export function onPttPartial(fn: PartialFn): () => void {
  partialFns.add(fn)
  return () => void partialFns.delete(fn)
}

const call = <T>(fns: Set<(v: T) => void>, v: T): void => {
  for (const fn of fns) {
    try {
      fn(v)
    } catch (err) {
      console.warn('[ptt] a listener failed', err)
    }
  }
}

/** main's 'ptt:down' (or the stage's mock). */
export function receiveDown(d: { id: string }): void {
  call(downFns, d)
}
/** main's 'ptt:partial' (or the stage's mock). Only the current hold's words. */
export function receivePartial(p: { id: string; text: string }): void {
  if (p.id !== get().ptt.id) return
  call(partialFns, { id: p.id, text: stripWake(p.text) })
}

bridge.onFeature('ptt:down', (p) => {
  const d = p as { id?: unknown } | undefined
  if (d && typeof d.id === 'string') receiveDown({ id: d.id })
})
bridge.onFeature('ptt:partial', (p) => {
  const f = p as { id?: unknown; text?: unknown } | undefined
  if (f && typeof f.id === 'string' && typeof f.text === 'string') receivePartial({ id: f.id, text: f.text })
})
