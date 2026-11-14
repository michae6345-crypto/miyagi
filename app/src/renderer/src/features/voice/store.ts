/** Feature: voice. Voice on/off and the latest `speak` audio from the engine (ElevenLabs). */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'

type VoiceState = { on: boolean; speaking: boolean; last?: { url: string; text: string; at: number } }

export const useVoice = create<VoiceState>(() => ({ on: false, speaking: false, last: undefined }))

export const toggleVoice = (): void => useVoice.setState((s) => ({ on: !s.on }))

onUi('reset', () => useVoice.setState({ speaking: false, last: undefined }))
// Toggle locally AND let the action reach the engine (not claimed), so it knows to generate audio.
onUi('shortcut', (kind) => {
  if (kind === 'voice_toggle') toggleVoice()
})
onMessage('speak', (p) => useVoice.setState({ last: { url: p.audioUrl, text: p.text, at: Date.now() } }))
