/**
 * Feature: before-start (mockup 03). The "Before you start" sheet grows out of the notch island before step 1 of a
 * "Just teach me" lesson. Priority 65: above a plain card (50) and the step-pass moment (60), below an off-track
 * (70) and a diagram (80), so anything urgent still wins.
 */
import { defineFeature } from '../../core/registry'
import { Sheet, SHEET_W } from './Sheet'
import { useBeforeStart } from './store'

export default defineFeature({
  id: 'before-start',
  islandModes: [{ id: 'before-start', priority: 65, width: SHEET_W, useActive: () => useBeforeStart((s) => s.open), Content: Sheet }]
})
