/**
 * Feature: sound. Subtle UI sounds, OFF by default: a soft tick when a step passes, two gentle notes when a lesson or
 * the setup finishes, and (a sub-toggle) a barely-there tap on a primary press. Synthesized (synth.ts), gated
 * (gate.ts), wired to the bus (store.ts). Brief: app/agents/sound.md.
 *
 * Layers:
 *   sound-host     the overlay: the one window that plays engine cues (every window gets the engine feed)
 *   sound-monitor  browser stage only, with ?sound=…: the Sounds setting, test cues and a readout of the last cue
 */
import { useEffect, type ReactNode } from 'react'
import { isElectron } from '../../bridge'
import { defineFeature } from '../../core/registry'
import { SoundMonitor } from './Monitor'
import { attachSound } from './store'

function SoundHost(): ReactNode {
  useEffect(() => attachSound(), [])
  return null
}

const staged = !isElectron && typeof location !== 'undefined' && new URLSearchParams(location.search).has('sound')

export default defineFeature({
  id: 'sound',
  overlayLayers: [{ id: 'sound-host', z: 0, Component: SoundHost }, ...(staged ? [{ id: 'sound-monitor', z: 90, Component: SoundMonitor }] : [])]
})
