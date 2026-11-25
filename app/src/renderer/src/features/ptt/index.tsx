/**
 * Feature: ptt. Push to talk (hold Fn+Control, or Control+Option, to ask by voice). Main side: src/main/features/ptt.ts
 * (the miyagi-listen helper). This folder: the island's listening pill, the first-use Allow card, the final-text routing
 * (store.ts, route.ts) and the browser stage's mock helper (web.ts). Off with PTT_ENABLED = false (common/flags.ts).
 *
 * Priority: both sit ABOVE the lesson cards (a session in flight must be visible), and below nothing the learner is
 * typing into (the launcher and settings are their own windows). The listening pill is pill-sized; the card is a card.
 * Each claims the island only while it has a reason to (store.ts: owned, released on every exit and after 65 s).
 */
import { PTT_ENABLED } from '../../../../common/flags'
import { defineFeature } from '../../core/registry'
import { AllowCard, CARD_W, ListeningPill, NotchRing } from './Island'
import { usePtt } from './store'
import './web'

export default defineFeature({
  id: 'ptt',
  enabled: PTT_ENABLED,
  islandModes: [
    { id: 'ptt-listening', priority: 84, useActive: () => usePtt((s) => s.owned && (s.ptt.phase === 'listening' || s.ptt.phase === 'sending')), Content: ListeningPill, notch: { useView: () => 'ears+drop', Right: NotchRing } },
    { id: 'ptt-card', priority: 82, width: CARD_W, useActive: () => usePtt((s) => !!s.card && !s.owned), Content: AllowCard }
  ]
})
