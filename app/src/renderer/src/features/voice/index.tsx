/**
 * Feature: voice. Reads Miyagi's lines aloud with the computer's own voice while voice is on (⌥V). No UI of its
 * own: the shortcut bar's Voice tile reads useVoice (on / speaking). The layer only marks the overlay as the
 * window that speaks.
 */
import { useEffect, type ReactNode } from 'react'
import { VOICE_ENABLED } from '../../../../common/flags'
import { defineFeature } from '../../core/registry'
import { attachSpeech } from './store'

function VoiceSpeaker(): ReactNode {
  useEffect(() => attachSpeech(), [])
  return null
}

// Voice is off for now (common/flags): no speaker layer, so speech is never attached and nothing is ever said.
export default defineFeature({ id: 'voice', overlayLayers: VOICE_ENABLED ? [{ id: 'voice-speaker', z: 0, Component: VoiceSpeaker }] : [] })
