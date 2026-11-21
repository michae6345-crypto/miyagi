/**
 * Feature: complete (A8 restyle, mockup Prog-Completion). The lesson-complete card, grown out of the notch island,
 * 408 wide. Priority 64: above a plain card (50, which carries the same card), the step-passed card (55) and the
 * success card (60), below the before-start sheet (65), an off-track (70) and a diagram (80): a diagram opened on top
 * closes back to this card.
 */
import { defineFeature } from '../../core/registry'
import { useOverlayWidth } from '../cards/store'
import { CompletePanel, panelWidth } from './Panel'
import { RoomProbe } from './room'
import { useComplete } from './store'

export default defineFeature({
  id: 'complete',
  islandModes: [
    {
      id: 'complete',
      priority: 64,
      // Read at render time: the overlay's width can clamp it on a small display.
      get width() {
        return panelWidth(useOverlayWidth.getState().w)
      },
      useActive: () => {
        useOverlayWidth((s) => s.w)
        return useComplete((s) => !!s.card)
      },
      Content: CompletePanel
    }
  ],
  // Reports how tall the card may grow, so Done / Start next lesson always stay on screen.
  overlayLayers: [{ id: 'complete-room', z: 1, Component: RoomProbe }]
})
