/**
 * Feature: voice. Reads Miyagi's lines aloud with the computer's own voice while voice is on (⌥V). No UI of its
 * own: the shortcut bar's Voice tile reads useVoice (on / speaking). The layer only marks the overlay as the
 * window that speaks.
 */
import { useEffect, type ReactNode } from 'react'
import { defineFeature } from '../../core/registry'
import { attachSpeech } from './store'

function VoiceSpeaker(): ReactNode {
  useEffect(() => attachSpeech(), [])
  return null
}

export default defineFeature({ id: 'voice', overlayLayers: [{ id: 'voice-speaker', z: 0, Component: VoiceSpeaker }] })
