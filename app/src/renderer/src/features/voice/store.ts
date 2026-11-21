/**
 * Feature: voice (⌥V). When it's on, Miyagi reads its own lines aloud with the computer's voice:
 *   cards and off-track notes (title, then body) · the step's task when the engine pauses the video for it
 *   (and right when voice turns on) · the passed line.
 * With Settings → "Read lessons aloud" on, every new lesson starts with voice on.
 * The app owns this entirely: the engine's `speak` / ElevenLabs path isn't used, so there's no key and no state to sync.
 *
 *   useVoice(s => s.on)        voice is on
 *   useVoice(s => s.speaking)  a line is being said right now
 *   toggleVoice()              for any Voice button: the same path as ⌥V
 */
import { create } from 'zustand'
import { VOICE_ENABLED } from '../../../../common/flags'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { usePrefs } from '../../core/prefs'
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
  if (VOICE_ENABLED && useVoice.getState().on && text) speech.say(text)
}
const titled = (title: string, body: string): string => (/[.?!:]$/.test(title.trim()) ? `${title} ${body}` : `${title}. ${body}`)
const task = (): string => useLesson.getState().instructions || useLesson.getState().stepTitle

// Claimed: voice is local, the engine has nothing to do for it. With voice off (common/flags) the press is
// swallowed: voice never turns on and nothing reaches the engine.
onUi('shortcut', (kind) => {
  if (kind !== 'voice_toggle') return
  if (!VOICE_ENABLED) return true
  const on = !useVoice.getState().on
  useVoice.setState({ on })
  if (on) say(task())
  return true
})

// Settings → "Read lessons aloud" (pref voiceOnStart): a new lesson turns voice on and reads its first task once.
// Read only here, so flipping the pref mid-lesson waits for the next lesson; ⌥V still toggles freely.
let readFirstTask = false
onMessage('lesson.ready', () => {
  if (!VOICE_ENABLED || !usePrefs.getState().voiceOnStart) return
  useVoice.setState({ on: true })
  readFirstTask = true // lesson.ready has no step yet: the first step.started brings the task
})
onMessage('step.started', (p) => {
  if (!readFirstTask) return
  readFirstTask = false
  say(p.instructions || p.title)
})

onMessage('card', (p) => say(titled(p.title, p.body)))
onMessage('offtrack', (p) => say(titled(p.title, p.body)))
onMessage('step.passed', (p) => {
  if (!p.skipped && !(p as typeof p & { already?: boolean }).already) say(copy.passed)
})
// The engine stopped the video so the learner can work: say what to do.
onMessage('video.pause', () => say(task()))

// Esc, lesson ended, dev reset, reconnect: quiet. `on` stays as the learner set it.
onUi('dismiss', () => speech.stop())
onUi('reset', () => {
  readFirstTask = false
  speech.stop()
})
useVoice.subscribe((s, prev) => {
  if (prev.on && !s.on) speech.stop()
})
