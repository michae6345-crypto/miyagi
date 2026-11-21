/**
 * Feature: building (A5, Home-Building). The build card grows out of the island while a lesson builds. Priority 45
 * (README island table): above the building pill (3) and the hover overview (20), below every lesson card (50+), so a
 * build failure (62) or anything urgent still wins.
 */
import { defineFeature } from '../../core/registry'
import { BuildCard, CARD_W } from './Card'
import { useBuildCard } from './store'

export default defineFeature({
  id: 'building',
  islandModes: [{ id: 'build-card', priority: 45, width: CARD_W, useActive: () => useBuildCard((s) => s.open), Content: BuildCard }]
})
