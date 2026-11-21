/**
 * Feature: onboarding (A3). Browser-stage stand-ins for src/main/features/onboarding.ts (nothing here runs in Electron).
 *
 *   onboarding:get / :done          the done flag (memory only in the stage)
 *   onboarding:prompt / :relaunch   log what main would do (the macOS prompt, app.relaunch)
 *   onboarding:install-companion    "nothing bundled" ({ok:false}), so the row takes the engine's own fix
 *                                   (action install, answered by mock/scenarios/onboarding.json)
 *
 * ?onb=full|mixed|ready|recovery (BUILD-PLAN A3 scenario) picks a stage fixture:
 *   - permissions:get / :open answer for the variant (Accessibility off in full, mixed and recovery). Opening System
 *     Settings switches that grant on 2.5 s later, as if the learner did it, so the rows and the card update live.
 *   - library.get {id: "onb_<variant>"} selects the variant's segment in the mock (it sets the scenario's current
 *     segment, so health.get and the other triggers answer for that variant). Only this file sends those ids.
 *   - full / mixed / ready open the window (full at the two-pane first-run size); recovery plays a lesson that pauses.
 */
import { cmd } from '../../../../common/wire'
import { bridge, isElectron, registerWebHandler } from '../../bridge'
import { openWindow } from '../../core/surfaces'
import { windowSize } from '../../core/theme'
import { markAsked } from './store'

export type StageVariant = 'full' | 'mixed' | 'ready' | 'recovery'
const VARIANTS: readonly StageVariant[] = ['full', 'mixed', 'ready', 'recovery']

/** The two-pane first run's size (Onb-Setup-Full's dialog). main/features/onboarding.ts uses the same numbers. */
export const FIRST_RUN_SIZE = { w: 944, h: 640 } as const

let stageVariant: StageVariant | undefined

/** The stage window's size for this variant (dev/Stage.tsx reads FeatureWindow.size). Electron ignores it. */
export function stageWindowSize(): { w: number; h: number } {
  return stageVariant === 'full' ? FIRST_RUN_SIZE : windowSize.onboarding
}

function setupWeb(): void {
  let done = false
  registerWebHandler('onboarding:get', () => ({ done }))
  registerWebHandler('onboarding:done', () => {
    done = true
    return true
  })
  registerWebHandler('onboarding:prompt', (kind) => {
    console.info(`[onboarding] stage: would ask macOS for ${String(kind)}`)
    return true
  })
  registerWebHandler('onboarding:relaunch', () => {
    console.info('[onboarding] stage: would relaunch miyagi')
    return true
  })
  registerWebHandler('onboarding:install-companion', () => ({ ok: false, reason: 'no-vsix' }))

  const raw = new URLSearchParams(location.search).get('onb')
  const variant = VARIANTS.find((v) => v === raw)
  if (!variant) return
  stageVariant = variant

  const perms: Record<'screen' | 'accessibility' | 'automation', string> = {
    screen: 'granted',
    accessibility: variant === 'ready' ? 'granted' : 'denied',
    automation: 'unknown'
  }
  registerWebHandler('permissions:get', () => ({ ...perms, external: false, at: Date.now() }))
  registerWebHandler('permissions:open', (kind) => {
    if (kind !== 'screen' && kind !== 'accessibility') return false
    console.info(`[onboarding] stage: would open System Settings (${kind}); switching it on in 2.5 s`)
    setTimeout(() => (perms[kind] = 'granted'), 2500)
    return true
  })

  // The mockups' Accessibility row is already Watching (the learner clicked it once).
  if (variant === 'full' || variant === 'mixed') markAsked('accessibility')
  bridge.send(cmd('library.get', { id: `onb_${variant}` }))
  if (variant !== 'recovery') void openWindow('onboarding', { view: variant === 'full' ? 'welcome' : 'checklist' })
}

if (!isElectron) setupWeb()
