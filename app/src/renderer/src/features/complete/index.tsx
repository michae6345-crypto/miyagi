/**
 * Feature: complete. The lesson-complete panel (direction A, "Summary": one narrow column), grown out
 * of the notch island. Priority 64: above a plain card (50, which carries the same card) and the step-pass moment
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
      // Read at render time (like the off-track card): the overlay's width and whether there's a map decide it.
      get width() {
        return panelWidth(useOverlayWidth.getState().w, !!useComplete.getState().card?.map)
      },
      useActive: () => {
        useOverlayWidth((s) => s.w)
        useComplete((s) => !!s.card?.map)
        return useComplete((s) => !!s.card)
      },
      Content: CompletePanel
    }
  ]
})
