/**
 * Feature: signincard (Linear MIC-17, app side). Brief: app/agents/signincard.md
 *
 * When the cloud refuses a lesson build claim (server/lesson/cloud_cache.py on_notice), the island says so calmly:
 *
 *   57 signin-card   401 signin_required: "Sign in to build new lessons." Sign in (Google) · Not now · Esc
 *   56 cap-line      429 caps: one line with the reset time in local time ("It resets at 4:00 PM."); also the region
 *                    line (451 region_unavailable): "miyagi isn't available in your region yet." · Not now · Esc
 *
 * Both sit above the build card (45, the notice lands mid-build) and below err-limit (58) and the off-track card (70).
 * Off until the sign-in gate opens (core/gate.ts), like every other card.
 */
import { useGateOpen } from '../../core/gate'
import { defineFeature } from '../../core/registry'
import { useOnboarding } from '../onboarding/store'
import { NoticeLine, SignInCard } from './Card'
import { cloudView, useSignInCard } from './store'
import './web'

// The install mint's region block (main cloud.ts CloudView.region): the region line.
cloudView(useOnboarding.getState().cloud)
useOnboarding.subscribe((s, prev) => {
  if (s.cloud?.region && !prev.cloud?.region) cloudView(s.cloud)
})

const gated =
  (useActive: () => boolean) =>
  (): boolean => {
    const open = useGateOpen()
    const on = useActive()
    return open && on
  }

export default defineFeature({
  id: 'signincard',
  islandModes: [
    { id: 'signin-card', priority: 57, width: 336, useActive: gated(() => useSignInCard((s) => !!s.signin)), Content: SignInCard },
    { id: 'cap-line', priority: 56, width: 480, useActive: gated(() => useSignInCard((s) => !!s.cap || !!s.region)), Content: NoticeLine }
  ]
})
