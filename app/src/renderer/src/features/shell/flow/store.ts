/**
 * Feature: shell / flow. The first run, inside the home window (Michael, Nov 21: "ONE app", never a login window
 * floating over home). The flow layer covers the whole window, sidebar included, until setup is over; then it hands
 * the window to home.
 *
 *   pending  the home window just opened and asks main whether the flow is on (onboarding:get); nothing shows yet
 *   intro    the branded intro (features/onboarding Intro), the first time only
 *   login    "Sign in to miyagi" (features/auth Login), while main says the login is needed
 *   setup    guided setup (features/onboarding Guided): Screen Recording, Accessibility, VS Code, Getting miyagi ready
 *   ready    You're ready (or Review setup when something the learner can fix is left)
 *   leaving  the hand-off: the flow fades, the sidebar slides in, the bonsai lands in the sidebar, Home rises
 *   off      home as usual
 *
 * Main decides (main/features/onboarding.ts onboarding:get): flow = setup not done on this Mac and not put off.
 * The guided step on screen is saved (onboarding:step), so a relaunch for Screen Recording lands back on it.
 */
import { create } from 'zustand'
import { bridge } from '../../../bridge'
import { markDone, markIntroSeen, useOnboarding, type GuidedStepId } from '../../onboarding/store'
import { ARRIVE_MS } from './motion'

export type FlowPhase = 'pending' | 'intro' | 'login' | 'setup' | 'ready' | 'leaving' | 'off'

type State = {
  phase: FlowPhase
  /** The login screen is part of this run (main: login on, nobody signed in, no choice made yet). */
  login: boolean
  /** The guided step saved before a relaunch: the walk opens there. */
  resume?: GuidedStepId
}

export const useFlow = create<State>(() => ({ phase: 'pending', login: false }))
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
/** The home window asks once, when it first renders. */
export function initFlow(): void {
  if (started) return
  started = true
  const fallback = setTimeout(() => get().phase === 'pending' && set({ phase: 'off' }), GET_WAIT_MS)
  bridge
    .invoke<FlowGet>('onboarding:get')
    .then((r) => {
      clearTimeout(fallback)
      if (get().phase !== 'pending') return
      if (!r?.flow) return set({ phase: 'off' })
      const login = r.login === true
      set({ login, resume: asStep(r.step), phase: !r.introSeen ? 'intro' : login ? 'login' : 'setup' })
    })
    .catch(() => {
      clearTimeout(fallback)
      set({ phase: 'off' })
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
  set({ phase: 'leaving' })
  clearTimeout(arriveTimer)
  arriveTimer = setTimeout(() => set({ phase: 'off' }), ARRIVE_MS)
}

// Remember the guided step on screen (main writes it to onboarding.json) while the flow runs, so a relaunch for
// Screen Recording comes back to the same step instead of the intro.
useOnboarding.subscribe((s, prev) => {
  if (!s.step || s.step === prev.step) return
  const p = get().phase
  if (p === 'setup') bridge.invoke('onboarding:step', s.step).catch(() => undefined)
})
