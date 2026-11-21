/**
 * Feature: complete (Michael's NEW 2). The lesson-complete panel (the learner's network and the skills they
 * mastered), grown out of the notch island. Priority 64: above a plain card (50, which carries the same card) and the step-pass moment
 * (60), below the before-start sheet (65), an off-track (70) and a diagram (80): a diagram opened on top closes
 * back to this panel.
 */
import { defineFeature } from '../../core/registry'
import { useOverlayWidth } from '../cards/store'
import { CompletePanel, panelWidth } from './Panel'
import { useComplete } from './store'

export default defineFeature({
  id: 'complete',
  islandModes: [
    {
      id: 'complete',
      priority: 64,
      // Read at render time (like the off-track card): the overlay's width, whether there's a map and a network decide it.
      get width() {
        const s = useComplete.getState()
        return panelWidth(useOverlayWidth.getState().w, !!s.card?.map, !!s.net)
      },
      useActive: () => {
        useOverlayWidth((s) => s.w)
        useComplete((s) => !!s.card?.map)
        useComplete((s) => !!s.net)
        return useComplete((s) => !!s.card)
      },
      Content: CompletePanel
    }
  ]
})
