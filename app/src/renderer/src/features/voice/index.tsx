/**
 * Feature: voice. Plays the engine's `speak` audio while voice is on (⌥V). No UI of its own: the shortcut bar's
 * Voice tile reads useVoice (on / speaking / level). The layer only marks the overlay as the window that plays.
 */
import { useEffect, type ReactNode } from 'react'
import { defineFeature } from '../../core/registry'
import { attachPlayer } from './store'

function VoicePlayer(): ReactNode {
  useEffect(() => attachPlayer(), [])
  return null
}

export default defineFeature({ id: 'voice', overlayLayers: [{ id: 'voice-player', z: 0, Component: VoicePlayer }] })
