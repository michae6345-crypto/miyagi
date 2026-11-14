/**
 * Says short lines with the computer's own voice (Web Speech API): no key, no network, no engine audio.
 *
 * One line at a time, newest wins. Only a window that attach()es speaks (the overlay, see index.tsx), so a line
 * that several windows hear is said once.
 */
export type SpeechReport = (speaking: boolean) => void

/** Markdown and code punctuation read badly aloud ("u underscore t"): drop it. */
const speakable = (text: string): string => text.replace(/[`*_#·|]/g, ' ').replace(/\s+/g, ' ').trim()

/** A downloaded high-quality voice if there is one, else the system's default, in the app's language. */
function pickVoice(all: SpeechSynthesisVoice[]): SpeechSynthesisVoice | undefined {
  const lang = navigator.language.slice(0, 2)
  const mine = all.filter((v) => v.localService && v.lang.startsWith(lang))
  const rank = (v: SpeechSynthesisVoice): number =>
    /premium/i.test(v.name) ? 0 : /enhanced/i.test(v.name) ? 1 : v.default ? 2 : /samantha|aria|jenny/i.test(v.name) ? 3 : 4
  return mine.sort((a, b) => rank(a) - rank(b))[0]
}

export function createSpeech(report: SpeechReport): { attach(): () => void; say(text: string): void; stop(): void } {
  const synth = typeof speechSynthesis === 'undefined' ? undefined : speechSynthesis
  let attached = 0
  let seq = 0
  let voice: SpeechSynthesisVoice | undefined
  // Held until each line ends: Chrome can garbage-collect a pending utterance and never fire its onend.
  const alive = new Set<SpeechSynthesisUtterance>()
  synth?.addEventListener('voiceschanged', () => (voice = undefined))

  const stop = (): void => {
    seq++
    synth?.cancel() // the cut line's onerror ('interrupted') arrives later and is ignored by its old id
    report(false)
  }

  const say = (text: string): void => {
    const line = speakable(text)
    if (!attached || !synth || !line) return
    stop()
    const id = seq
    voice ??= pickVoice(synth.getVoices())
    const u = new SpeechSynthesisUtterance(line)
    if (voice) u.voice = voice
    u.lang = voice?.lang ?? navigator.language
    u.onstart = () => id === seq && report(true)
    u.onend = u.onerror = () => {
      alive.delete(u)
      if (id === seq) report(false)
    }
    alive.add(u)
    synth.speak(u)
  }

  return {
    attach() {
      attached++
      return () => {
        attached--
        if (!attached) stop()
      }
    },
    say,
    stop
  }
}
