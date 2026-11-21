/**
 * Feature: onboarding (A3). Brief: app/agents/onboarding.md. Mockups: Onb-Setup-Full, Onb-Checklist-Mixed,
 * Onb-Setup-Ready, Onb-Permission-Recovery.
 *
 *   window 'onboarding' (kind 'app')  the setup window: rows for Screen Recording, Accessibility, the VS Code
 *                                     companion and the engine (with the cloud install token), then Ready.
 *                                     main/features/onboarding.ts opens it on the first run; openOnboarding() from
 *                                     core/surfaces opens it any time after.
 *   island mode 'onboarding-recovery' a permission went away mid-lesson: priority 75 (README island table), a card
 *                                     grown from the pill that keeps the learner's place.
 */
import { defineFeature, type FeatureWindow } from '../../core/registry'
import { Onboarding } from './Onboarding'
import { Recovery, RECOVERY_W } from './Recovery'
import { useOnboarding } from './store'
import { stageWindowSize } from './web'

const setupWindow: FeatureWindow = {
  route: 'onboarding',
  kind: 'app',
  Component: Onboarding,
  // The stage reads this when it opens the window (Electron sizes app windows in main).
  get size() {
    return stageWindowSize()
  }
}

export default defineFeature({
  id: 'onboarding',
  windows: [setupWindow],
  islandModes: [{ id: 'onboarding-recovery', priority: 75, width: RECOVERY_W, useActive: () => useOnboarding((s) => !!s.recovery), Content: Recovery }]
})
