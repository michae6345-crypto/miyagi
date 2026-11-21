/**
 * Feature: shell / flow. The first run, inside the home window (Michael, Nov 21: "ONE app", never a login window
 * floating over home). The flow layer covers the whole window, sidebar included, until setup is over; then it hands
 * the window to home.
 *
 *   pending  a first open of the home window on this Mac: it asks main whether the flow is on (onboarding:get)
 *   intro    the branded intro (features/onboarding Intro), the first time only
 *   login    "Sign in to miyagi" (features/auth Login), while main says the login is needed
 *   setup    guided setup (features/onboarding Guided): Screen Recording, Accessibility, VS Code, Getting miyagi ready
 *   ready    You're ready (or Review setup when something the learner can fix is left)
 *   leaving  the hand-off: the flow fades, the sidebar slides in, the bonsai lands in the sidebar, Home rises
 *   off      home as usual
 *
 * Main decides (main/features/onboarding.ts onboarding:get): flow = setup not done on this Mac and not put off.
 * The guided step on screen is saved (onboarding:step), so a relaunch for Screen Recording lands back on it.
 *
 * No blank first frame: every answer is remembered in this window's localStorage (OFF_KEY), so an open after the
 * first run starts on 'off' and home is there in the first paint; main's answer still comes, and a flow that turns
 * out to be on (a late answer, or flags reset) still starts. Only a real first run waits on 'pending'.
 *
 * Again (reopenFlow): every ask for setup after the first run (home's Finish setup, the sidebar's Setup, Engine and
 * Cloud rows, Settings' Open setup, here or from the tray's Settings) runs guided setup over home, in this same window:
 * core/surfaces.ts openOnboarding calls requestSetup here (setSetupOpener), and from any other window it opens this
 * one with {setup} (Shell.tsx). Home stays mounted underneath; the flow fades in over it and out again, and the bonsai
 * stays in the sidebar. It is never a trap: "Back to home" (and Esc) in every phase, and You're ready's primary is
 * Done (leaveAgain): back to home, no lesson started.
 */
import { create } from 'zustand'
import { bridge, isElectron } from '../../../bridge'
import { setSetupOpener } from '../../../core/surfaces'
import { markDone, markIntroSeen, useOnboarding, type GuidedStepId } from '../../onboarding/store'
import { stageFlowStep } from '../../onboarding/web'
import { ARRIVE_MS } from './motion'

export type FlowPhase = 'pending' | 'intro' | 'login' | 'setup' | 'ready' | 'leaving' | 'off'

type State = {
  phase: FlowPhase
  /** The login screen is part of this run (main: login on, nobody signed in, no choice made yet). */
  login: boolean
  /** The guided step saved before a relaunch: the walk opens there. */
  resume?: GuidedStepId
  /** Setup reopened over home (reopenFlow): home stays mounted under the flow, the bonsai stays in the sidebar. */
  again: boolean
}

/** Remembered "no flow here" (setup done or put off), read synchronously on the next open of the window. */
const OFF_KEY = 'miyagi.flow.off'
function readOff(): boolean {
  try {
    return localStorage.getItem(OFF_KEY) === '1'
  } catch {
    return false
  }
}
function writeOff(off: boolean): void {
  try {
    if (off) localStorage.setItem(OFF_KEY, '1')
    else localStorage.removeItem(OFF_KEY)
  } catch {
    /* no storage: the next open waits for main's answer, as on a first run */
  }
}

/** The stage's ?flow=1 always plays the flow (its localStorage outlives a run). */
const stageFlow = !isElectron && !!stageFlowStep()

export const useFlow = create<State>(() => ({ phase: !stageFlow && readOff() ? 'off' : 'pending', login: false, again: false }))
const set = useFlow.setState
const get = useFlow.getState

/** onboarding:get, as main/features/onboarding.ts answers it. */
type FlowGet = { done?: boolean; introSeen?: boolean; flow?: boolean; login?: boolean; step?: string }

const STEPS: readonly GuidedStepId[] = ['screen', 'accessibility', 'companion', 'engine']
const asStep = (s: unknown): GuidedStepId | undefined => STEPS.find((x) => x === s)
/** An answer that never comes must not leave the window blank. */
const GET_WAIT_MS = 1500

/** The flow layer is up (pending shows only the window's plain paper: neither home nor the flow, for a few ms). */
export const flowCovers = (p: FlowPhase): boolean => p === 'intro' || p === 'login' || p === 'setup' || p === 'ready'

let started = false
/** 'off' is a guess (remembered, or main took too long), not the learner's choice: main's answer may still start the flow. */
let guessed = get().phase === 'off'

/** The home window asks once, when it first renders. */
export function initFlow(): void {
  if (started) return
  started = true
  setSetupOpener(requestSetup)
  const fallback = setTimeout(() => {
    if (get().phase !== 'pending') return
    guessed = true
    set({ phase: 'off' })
  }, GET_WAIT_MS)
  bridge
    .invoke<FlowGet>('onboarding:get')
    .then((r) => {
      clearTimeout(fallback)
      writeOff(!r?.flow)
      const p = get().phase
      if (!r?.flow) {
        if (p === 'pending') set({ phase: 'off' })
        return
      }
      // On: start it, unless the learner already left it or reopened it themselves.
      if (p !== 'pending' && !(p === 'off' && guessed)) return
      guessed = false
      const login = r.login === true
      set({ login, resume: asStep(r.step), again: false, phase: !r.introSeen ? 'intro' : login ? 'login' : 'setup' })
    })
    .catch(() => {
      clearTimeout(fallback)
      if (get().phase === 'pending') set({ phase: 'off' })
    })
}

export function endIntro(): void {
  markIntroSeen()
  set({ phase: get().login ? 'login' : 'setup' })
}

/** Signed in, or "Continue without an account" (auth:continue already told main): on to setup. */
export function endLogin(): void {
  set({ phase: 'setup', login: false })
}

export const toReady = (): void => set({ phase: 'ready' })
export const backToSetup = (): void => set({ phase: 'setup', resume: undefined })

let arriveTimer: ReturnType<typeof setTimeout> | undefined
/** Hand the window to home. `done`: setup is finished (Start); false: "Set up later". */
export function finishFlow(done: boolean): void {
  const p = get().phase
  if (p === 'off' || p === 'leaving') return
  if (done) markDone()
  else bridge.invoke('onboarding:later').catch(() => undefined)
  guessed = false
  writeOff(true)
  set({ phase: 'leaving' })
  clearTimeout(arriveTimer)
  arriveTimer = setTimeout(() => set({ phase: 'off', again: false }), ARRIVE_MS)
}

/** Setup was put off ("Set up later") when it was opened again: leaving before it is done puts it off again. */
let putOff = false

/**
 * Guided setup again, over home in this window: main forgets "Set up later" (onboarding:resume, so a relaunch for
 * Screen Recording comes back to the step), the walk opens on the first step not done (or You're ready).
 */
export function reopenFlow(): void {
  if (get().phase !== 'off') return
  clearTimeout(arriveTimer)
  putOff = !useOnboarding.getState().done
  bridge.invoke('onboarding:resume').catch(() => undefined)
  guessed = false
  writeOff(false)
  set({ phase: 'setup', resume: undefined, login: false, again: true })
}

/** Setup asked for while the window is still deciding or handing over: run it once home is there. */
let wanted = false
/** Any ask for setup in this window (core/surfaces.ts openOnboarding, the {setup} window arg). */
export function requestSetup(): void {
  const p = get().phase
  if (p === 'off') reopenFlow()
  else if (p === 'pending' || p === 'leaving') wanted = true
  // Otherwise the flow is on screen already.
}
useFlow.subscribe((s) => {
  if (!wanted) return
  if (flowCovers(s.phase)) wanted = false // the first run itself started: it is the setup asked for
  else if (s.phase === 'off') {
    wanted = false
    reopenFlow()
  }
})

/**
 * Setup again, handed back to home ("Back to home", Esc, You're ready's Done): never a lesson (no library.start), never
 * "Set up later" of its own. `done`: You're ready's Done (setup finished, as Start would mark it). Leaving before setup
 * is done puts back only the learner's own earlier "Set up later" that reopenFlow cleared, so the next launch doesn't
 * open on the first-run flow; setup that was done stays done.
 */
export function leaveAgain(done = false): void {
  const s = get()
  if (!s.again || !flowCovers(s.phase)) return
  if (done) markDone()
  else if (putOff && !useOnboarding.getState().done) bridge.invoke('onboarding:later').catch(() => undefined)
  putOff = false
  writeOff(true)
  set({ phase: 'leaving' })
  clearTimeout(arriveTimer)
  arriveTimer = setTimeout(() => set({ phase: 'off', again: false }), ARRIVE_MS)
}

// Remember the guided step on screen (main writes it to onboarding.json) while the flow runs, so a relaunch for
// Screen Recording comes back to the same step instead of the intro.
useOnboarding.subscribe((s, prev) => {
  if (!s.step || s.step === prev.step) return
  const p = get().phase
  if (p === 'setup') bridge.invoke('onboarding:step', s.step).catch(() => undefined)
})
