/**
 * Feature: reminders (agents/reminders.md). Gentle, opt-in reminders that bring the learner back without nagging.
 *
 *   offer      island mode, priority 41 (below the review reminder 42 and every lesson card): the one-time
 *              "Want a nudge when a review is due?" after the first finished lesson, at the next idle moment.
 *   toast      overlay layer z 92: the in-app stand-in for the macOS notification (browser stage, dev builds).
 *   settings   <RemindersGroup /> (Settings.tsx), for the settings lane to mount in General (Core request).
 *
 * Main (src/main/features/reminders.ts) keeps the settings and posts at most one notification a day.
 * Stage: ?scenario=reminders (finish the lesson, Esc the completion card) · &reminders=offer · &reminders=toast&hold ·
 * &reminders=settings. See web.ts.
 */
import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { defineFeature } from '../../core/registry'
import { OfferCard, OFFER_W } from './Offer'
import { SettingsPreview } from './Settings'
import { useOfferActive, useReminders } from './store'
import { ReminderToast } from './Toast'
import { STAGE_VIEW } from './web'

/** Stage `&reminders=offer`: arm the offer as if a lesson had just been finished. */
function StageOffer(): ReactNode {
  useEffect(() => {
    if (STAGE_VIEW !== 'offer') return
    const t = setTimeout(() => useReminders.setState({ offerArmed: true }), 1200)
    return () => clearTimeout(t)
  }, [])
  return null
}

export default defineFeature({
  id: 'reminders',
  islandModes: [{ id: 'reminders-offer', priority: 41, width: OFFER_W, useActive: useOfferActive, Content: OfferCard }],
  overlayLayers: [
    { id: 'reminders-toast', z: 92, Component: ReminderToast },
    ...(STAGE_VIEW === 'offer' ? [{ id: 'reminders-stage-offer', z: 0, Component: StageOffer }] : []),
    ...(STAGE_VIEW === 'settings' ? [{ id: 'reminders-settings', z: 91, Component: SettingsPreview }] : [])
  ]
})
