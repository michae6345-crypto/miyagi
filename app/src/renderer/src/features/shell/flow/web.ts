/**
 * Feature: shell / flow. Browser-stage extras for the one-window first run (nothing here runs in Electron). The flow's
 * stand-ins for main (onboarding:get with flow/login/step, the grants per step) live in features/onboarding/web.ts:
 *   ?scenario=onboarding&flow=1&size=1440x900&clean&step=intro|login|screen|access|vscode|engine|ready|done
 * step=done plays You're ready, then presses Start by itself a moment later, so the hand-off to home can be watched
 * (and screenshotted) without a click.
 */
import { isElectron } from '../../../bridge'
import { stageFlowStep } from '../../onboarding/web'
import { finishFlow, useFlow } from './store'

const DONE_AFTER_MS = 1400

if (!isElectron && stageFlowStep() === 'done') {
  let timer: ReturnType<typeof setTimeout> | undefined
  useFlow.subscribe((s) => {
    if (s.phase !== 'ready' || timer) return
    timer = setTimeout(() => finishFlow(true), DONE_AFTER_MS)
  })
}
