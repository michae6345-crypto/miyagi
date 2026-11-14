/**
 * Feature: voice (⌥V). When it's on, Miyagi reads its own lines aloud with the computer's voice:
 *   cards and off-track notes (title, then body) · the step's task when the engine pauses the video for it
 *   (and right when voice turns on) · the passed line.
 * The app owns this entirely: the engine's `speak` / ElevenLabs path isn't used, so there's no key and no state to sync.
 *
 *   useVoice(s => s.on)        voice is on
 *   useVoice(s => s.speaking)  a line is being said right now
 *   toggleVoice()              for any Voice button: the same path as ⌥V
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { triggerShortcut } from '../../core/shortcuts'
import { copy } from '../../core/theme'
import { createSpeech } from './speech'

type VoiceState = { on: boolean; speaking: boolean }

export const useVoice = create<VoiceState>(() => ({ on: false, speaking: false }))

const speech = createSpeech((speaking) => useVoice.setState({ speaking }))
export const attachSpeech = speech.attach

/** A Voice button anywhere (shortcut bar, spotlight): runs the ⌥V path. */
export const toggleVoice = (): void => triggerShortcut('voice_toggle')

const say = (text?: string): void => {
  if (useVoice.getState().on && text) speech.say(text)
}
const titled = (title: string, body: string): string => (/[.?!:]$/.test(title.trim()) ? `${title} ${body}` : `${title}. ${body}`)
const task = (): string => useLesson.getState().instructions || useLesson.getState().stepTitle

// Claimed: voice is local, the engine has nothing to do for it.
onUi('shortcut', (kind) => {
  if (kind !== 'voice_toggle') return
  const on = !useVoice.getState().on
  useVoice.setState({ on })
  if (on) say(task())
  return true
})

onMessage('card', (p) => say(titled(p.title, p.body)))
onMessage('offtrack', (p) => say(titled(p.title, p.body)))
onMessage('step.passed', () => say(copy.passed))
// The engine stopped the video so the learner can work: say what to do.
onMessage('video.pause', () => say(task()))

// Esc, lesson ended, dev reset, reconnect: quiet. `on` stays as the learner set it.
onUi('dismiss', () => speech.stop())
onUi('reset', () => speech.stop())
useVoice.subscribe((s, prev) => {
  if (prev.on && !s.on) speech.stop()
})
