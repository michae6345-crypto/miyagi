/**
 * Feature: voice. Voice on/off, and what the shortcut bar reads while a `speak` clip plays.
 *
 *   useVoice(s => s.on)        voice is on (mirrors the engine, which has no echo yet: see Core requests in agents/voice.md)
 *   useVoice(s => s.speaking)  a clip is audible right now
 *   useVoice(s => s.level)     0..1 loudness while speaking; undefined when it can't be measured (animate on your own)
 *   toggleVoice()              for any Voice button: the same path as ⌥V, so the engine hears it too
 *
 * Playback lives in player.ts and runs only in the overlay window (index.tsx attaches it there).
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { notify, useLesson } from '../../core/lesson'
import { triggerShortcut } from '../../core/shortcuts'
import { createPlayer } from './player'

type VoiceState = { on: boolean; speaking: boolean; level?: number }

export const useVoice = create<VoiceState>(() => ({ on: false, speaking: false, level: undefined }))

const player = createPlayer((s) => useVoice.setState(s))
export const attachPlayer = player.attach

/** A Voice button anywhere (shortcut bar, spotlight): runs the ⌥V path so the engine's state follows. */
export const toggleVoice = (): void => triggerShortcut('voice_toggle')

const KEY_LINE = { missing: 'Add an ElevenLabs key in Settings', invalid: 'Check your ElevenLabs key in Settings' } as const

// Not claimed: the local flip AND action {kind:"voice_toggle"} to the engine, so it starts or stops generating audio.
// Without a usable ElevenLabs key, claim it and say why instead (turning voice off always works).
onUi('shortcut', (kind) => {
  if (kind !== 'voice_toggle') return
  const on = useVoice.getState().on
  const key = useLesson.getState().keyStatus?.elevenlabs
  if (!on && (key === 'missing' || key === 'invalid')) {
    notify(KEY_LINE[key])
    return true
  }
  if (!on) player.warm()
  useVoice.setState({ on: !on })
})

onMessage('speak', (p) => {
  if (useVoice.getState().on && p.audioUrl) player.play(p.audioUrl)
})

// Lesson ended, dev reset, reconnect: silence. After a reconnect the engine has restarted with voice off, so follow it.
onUi('reset', (p) => {
  player.stop()
  if ((p as { reason?: string } | undefined)?.reason === 'reconnect') useVoice.setState({ on: false })
})

// Voice off stops the clip at once, wherever `on` was flipped from.
useVoice.subscribe((s, prev) => {
  if (prev.on && !s.on) player.stop()
})
