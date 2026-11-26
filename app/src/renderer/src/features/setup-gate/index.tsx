/**
 * Feature: setup-gate (user test Nov 25). While the lesson's environment installs, the lesson waits: this card grows out
 * of the island with the progress, and the player holds the clip (features/player/store.ts). Priority 61: above the
 * setup card it replaces while installs run (cards 50/60), below a build failure (62) and Before you start (65).
 */
import { defineFeature } from '../../core/registry'
import { PANEL_W, SetupGatePanel } from './Panel'
import { useSetupGate } from './store'
import { panelOpen } from './machine'

export default defineFeature({
  id: 'setup-gate',
  islandModes: [{ id: 'setup-gate', priority: 61, width: PANEL_W, useActive: () => useSetupGate((s) => panelOpen(s)), Content: SetupGatePanel }]
})
