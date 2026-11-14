/**
 * Feature: diagrams. Intuition diagrams morph out of the pill (⌥D):
 *   network · gradients · heatmap (TODO). The engine sends the data; we only render.
 */
import { defineFeature } from '../../core/registry'
import { DiagramView } from './Diagram'
import { useDiagram } from './store'

export default defineFeature({
  id: 'diagrams',
  islandModes: [{ id: 'diagram', priority: 80, width: 640, useActive: () => useDiagram((d) => d.open && !!d.diagram), Content: DiagramView }]
})
