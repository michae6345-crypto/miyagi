/**
 * Feature: demo. The offline demo: "A neural net from scratch", with no engine, no keys and no network.
 *
 *   - The Demo button (corner of the stage) reloads into ?scenario=demo&clean.
 *   - mock/scenarios/demo.json is the scripted engine (built from lesson.ts by scripts/demo-scenario.ts). It answers
 *     the same commands the real engine does, so every surface behaves as with API keys, topic already chosen.
 *   - Desktop: the learner's VS Code under the overlay (z -100), driven by the engine's events and the learner's presses.
 *   - Presenter: the walkthrough, one beat per → (walkthrough.ts), and you can take over by hand at any point.
 */
import type { ReactNode } from 'react'
import { defineFeature } from '../../core/registry'
import { Desktop } from './Desktop'
import { Presenter } from './Presenter'
import { demoOn } from './store'

function DesktopLayer(): ReactNode {
  return demoOn ? <Desktop /> : null
}

export default defineFeature({
  id: 'demo',
  overlayLayers: [
    { id: 'demo-desktop', z: -100, Component: DesktopLayer },
    { id: 'demo-presenter', z: 95, Component: Presenter }
  ]
})
