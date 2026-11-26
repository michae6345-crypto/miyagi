/**
 * Feature: onboarding. Browser-stage stand-ins for src/main/features/onboarding.ts (nothing here runs in Electron).
 *
 *   onboarding:get / :done / :intro-seen   the flags (memory only in the stage)
 *   onboarding:prompt / :relaunch          log what main would do (the macOS prompt, app.relaunch)
 *   onboarding:install-companion           "nothing bundled" ({ok:false}), so the row takes the engine's own fix
 *                                          (action install, answered by mock/scenarios/onboarding.json)
 *
 * ?onb=<variant> picks a stage fixture:
 *   intro    the branded intro, held on its last frame (a key or click moves on to setup)
 *   full     the real first launch: the intro, the consent screen, then guided setup from step 1 with nothing granted
 *   consent  the consent screen (R05, R06), then guided setup from step 1
 *   step1-4  guided setup opened on that step (the steps before it are done)
 *   mixed    Review setup: Screen Recording on, Accessibility Watching, the companion missing
 *   ready    every row green: You're ready
 *   recovery a lesson that pauses for Accessibility (the island card)
 * What the stage fakes, so every flow can be walked by hand:
 *   - permissions:get / :open answer for the variant. Opening System Settings switches that grant on 2.5 s later, as
 *     if the learner did it, so the step turns green and the walk moves on.
 *   - cloud access (DISTRIBUTION-PLAN 4) is "setting up" until the engine step has been up 2.5 s, then ready, so the
 *     last step shows and advances on its own (full, step1-4).
 *   - library.get {id: "onb_<variant>"} selects the variant's segment in the mock (health answers for that variant).
 *
 * ?flow=1&step=<step> is the one-window first run (features/shell/flow): the HOME window opens (never the setup window)
 * and the flow layer covers it, starting at that step:
 *   consent the consent screen, then setup (onboarding:agree stands in for main; consent is needed from intro,
 *           login and consent, and given for every later step)
 *   intro   the intro, then Sign in        login   Sign in (intro seen)       screen  Screen Recording (signed out
 *   access  Accessibility (Screen on)      vscode  VS Code (both grants on)   engine  Getting miyagi ready (access 2.5 s)
 *   ready   You're ready                   done    You're ready, then Start by itself (the hand-off to home)
 * onboarding:step / onboarding:later / onboarding:resume stand in for main (memory only).
 */
import { cmd } from '../../../../common/wire'
import { bridge, isElectron, registerWebHandler } from '../../bridge'
import { openWindow } from '../../core/surfaces'
import { windowSize } from '../../core/theme'
import { markAsked, refreshCloud, useOnboarding, type CloudView } from './store'

export type StageVariant = 'intro' | 'full' | 'consent' | 'step1' | 'step2' | 'step3' | 'step4' | 'mixed' | 'ready' | 'recovery'
const VARIANTS: readonly StageVariant[] = ['intro', 'full', 'consent', 'step1', 'step2', 'step3', 'step4', 'mixed', 'ready', 'recovery']
/** The variants that open guided setup (at the first-run size). */
const GUIDED: readonly StageVariant[] = ['intro', 'full', 'consent', 'step1', 'step2', 'step3', 'step4']
/** The variants that start before the learner agreed (a real first launch, and the consent screen itself). */
const BEFORE_CONSENT: readonly StageVariant[] = ['intro', 'full', 'consent']

/** The first launch's window (intro and guided setup). main/features/onboarding.ts uses the same numbers. */
export const FIRST_RUN_SIZE = { w: 944, h: 640 } as const
const CLOUD_READY_MS = 2500

let stageVariant: StageVariant | undefined

/** The stage window's size for this variant (dev/Stage.tsx reads FeatureWindow.size). Electron ignores it. */
export function stageWindowSize(): { w: number; h: number } {
  return stageVariant && GUIDED.includes(stageVariant) ? FIRST_RUN_SIZE : windowSize.onboarding
}

export type FlowStep = 'intro' | 'login' | 'consent' | 'screen' | 'access' | 'vscode' | 'engine' | 'ready' | 'done'
const FLOW_STEPS: readonly FlowStep[] = ['intro', 'login', 'consent', 'screen', 'access', 'vscode', 'engine', 'ready', 'done']
/** Each flow step as the guided variant it starts from (grants and the mock segment). */
const FLOW_VARIANT: Record<FlowStep, StageVariant> = { intro: 'full', login: 'full', consent: 'consent', screen: 'step1', access: 'step2', vscode: 'step3', engine: 'step4', ready: 'ready', done: 'ready' }

/** ?flow=1&step=…: the stage's one-window first run, or undefined. */
export function stageFlowStep(): FlowStep | undefined {
  const q = new URLSearchParams(location.search)
  if (q.get('flow') !== '1') return undefined
  return FLOW_STEPS.find((s) => s === q.get('step')) ?? 'intro'
}

function setupWeb(): void {
  const flowStep = stageFlowStep()
  let done = false
  let introSeen = !!flowStep && flowStep !== 'intro'
  let later = false
  let savedStep: string | undefined
  const login = flowStep === 'intro' || flowStep === 'login'
  const raw0 = new URLSearchParams(location.search).get('onb')
  const variant0 = flowStep ? FLOW_VARIANT[flowStep] : VARIANTS.find((v) => v === raw0)
  // Consent (main: prefs.consent): needed on a real first launch and on the consent screen's own fixtures; the later
  // fixtures (a step, ready, the checklist) start agreed. Memory only, like the other flags.
  let consent = !(variant0 && BEFORE_CONSENT.includes(variant0))
  // The store may have asked onboarding:get before this module registered it: set its consent directly too.
  useOnboarding.setState({ consent })
  registerWebHandler('onboarding:get', () => ({ done, introSeen, consent, ...(flowStep ? { flow: !done && !later, login, step: savedStep } : {}) }))
  registerWebHandler('onboarding:agree', () => {
    consent = true
    console.info('[onboarding] stage: would record prefs.consent {version, at} in main')
    return true
  })
  registerWebHandler('onboarding:step', (step) => {
    savedStep = typeof step === 'string' ? step : undefined
    return true
  })
  registerWebHandler('onboarding:later', () => {
    later = true
    return true
  })
  registerWebHandler('onboarding:resume', () => {
    later = false
    return true
  })
  registerWebHandler('onboarding:done', () => {
    done = true
    return true
  })
  registerWebHandler('onboarding:intro-seen', () => {
    introSeen = true
    return true
  })
  registerWebHandler('onboarding:prompt', (kind) => {
    // Like main: nothing is asked before consent.
    if (!consent) return false
    console.info(`[onboarding] stage: would ask macOS for ${String(kind)}`)
    return true
  })
  registerWebHandler('onboarding:relaunch', () => {
    console.info('[onboarding] stage: would relaunch miyagi')
    return true
  })
  // Restart miyagi (main/permissions.ts permissions:relaunch) and Reset miyagi in the list (permissions:reset).
  registerWebHandler('permissions:relaunch', () => {
    console.info('[onboarding] stage: would restart miyagi')
    return true
  })
  registerWebHandler('permissions:reset', (kind) => {
    console.info(`[onboarding] stage: would reset miyagi's ${String(kind)} row`)
    return true
  })
  registerWebHandler('onboarding:install-companion', () => ({ ok: false, reason: 'no-vsix' }))

  const variant = variant0
  if (!variant) return
  stageVariant = variant
  const guided = GUIDED.includes(variant)

  // ?os=win: like main/permissions.ts on Windows, which has no such grants (both read as on).
  const win = bridge.platform.os === 'win'
  const screenOn = win || variant === 'step2' || variant === 'step3' || variant === 'step4' || variant === 'mixed' || variant === 'ready' || variant === 'recovery'
  const accessOn = win || variant === 'step3' || variant === 'step4' || variant === 'ready'
  const perms: Record<'screen' | 'accessibility' | 'automation', string> = {
    screen: screenOn ? 'granted' : 'denied',
    accessibility: accessOn ? 'granted' : 'denied',
    automation: 'unknown'
  }
  registerWebHandler('permissions:get', () => ({ ...perms, external: false, at: Date.now() }))
  registerWebHandler('permissions:open', (kind) => {
    if (kind !== 'screen' && kind !== 'accessibility') return false
    console.info(`[onboarding] stage: would open System Settings (${kind}); switching it on in 2.5 s`)
    // ?regrant=1: macOS shows it on but never reports the grant (an update dropped it): the step says what to try.
    if (!new URLSearchParams(location.search).has('regrant')) setTimeout(() => (perms[kind] = 'granted'), 2500)
    return true
  })

  // The flow's ready: access is set up already (the walk goes straight to You're ready).
  if (guided || (flowStep && variant === 'ready')) {
    // Cloud access: setting up until the engine step has been on screen a moment, then ready.
    let cloud: CloudView = variant === 'ready' ? { state: 'ok', configured: true, secure: true, hasToken: true } : { state: 'minting', configured: true, secure: true, hasToken: false }
    registerWebHandler('cloud:get', () => cloud)
    registerWebHandler('cloud:retry', () => cloud)
    let timer: ReturnType<typeof setTimeout> | undefined
    useOnboarding.subscribe((s) => {
      if (s.step !== 'engine' || timer || cloud.state === 'ok') return
      timer = setTimeout(() => {
        cloud = { state: 'ok', configured: true, secure: true, hasToken: true }
        refreshCloud()
      }, CLOUD_READY_MS)
    })
    refreshCloud()
  }

  if (new URLSearchParams(location.search).has('regrant')) {
    markAsked('screen')
    markAsked('accessibility')
  }
  // The checklist mockup's Accessibility row is already Watching (the learner clicked it once).
  if (variant === 'mixed') markAsked('accessibility')
  const segment = variant === 'mixed' || variant === 'ready' || variant === 'recovery' ? variant : variant === 'step4' ? 'ready' : 'full'
  bridge.send(cmd('library.get', { id: `onb_${segment}` }))
  if (variant === 'recovery') return
  // One window: home opens, and the flow layer covers it.
  if (flowStep) {
    void openWindow('library')
    return
  }
  const view = variant === 'intro' || variant === 'full' ? 'intro' : guided ? 'setup' : 'checklist'
  void openWindow('onboarding', variant === 'intro' ? { view, hold: true } : { view })
}

if (!isElectron) setupWeb()
