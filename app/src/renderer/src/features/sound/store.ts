/**
 * Feature: sound. Turns app moments into cues, through the gate, without touching any other feature.
 *
 *   step.passed (not skipped, not "already")       tick   (the lesson's last step: done)
 *   card kind "complete" / a skill map             done   (once per lesson; skipped if the last step already chimed)
 *   Prefs.onboarded false -> true (setup finished) done
 *   a pointer click on a primary button            tap    (only with the taps sub-toggle)
 *
 * Engine cues play in ONE window: the overlay (index.tsx mounts SoundHost there, like voice's speaker), since every
 * window receives the engine feed. Taps play in the window that was clicked. All windows share the "last cue" time and
 * the "last keystroke" time through localStorage, so no two cues overlap across windows and none plays while the
 * learner types anywhere in miyagi.
 *
 *   useSoundLog(s => s.last)   the last cue asked for and what the gate said (the stage monitor reads it)
 */
import { create } from 'zustand'
import { bridge, isElectron, registerWebHandler } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { usePrefs } from '../../core/prefs'
import { createGate, type Verdict } from './gate'
import { playCue } from './player'
import { useSound } from './settings'
import type { Cue } from './synth'

export type SoundEvent = { id: number; cue: Cue; at: number; verdict: Verdict; why: string }
export const useSoundLog = create<{ last?: SoundEvent }>(() => ({}))

const gate = createGate()
const env = { typingAt: 0, dnd: false }
let hosted = false
let seq = 0
let retry: ReturnType<typeof setTimeout> | undefined

const LAST_KEY = 'miyagi.sound.last'
const TYPING_KEY = 'miyagi.sound.typing'
const enabled = (): boolean => useSound.getState().mode === 'subtle'

const share = (key: string, at: number): void => {
  try {
    localStorage.setItem(key, String(at))
  } catch {
    /* no storage: this window only */
  }
}

/** Ask for a cue. `why` is for the stage monitor and the brief, never shown in the app. */
export function request(cue: Cue, why: string, bornAt = Date.now()): void {
  const s = useSound.getState()
  const verdict = gate.ask(cue, { now: Date.now(), enabled: s.mode === 'subtle', taps: s.taps, typingAt: env.typingAt, dnd: env.dnd }, bornAt)
  if (verdict.play) {
    playCue(cue, s.dry)
    share(LAST_KEY, Date.now())
  } else if (verdict.reason === 'held') {
    if (retry) clearTimeout(retry)
    retry = setTimeout(() => {
      retry = undefined
      const p = gate.pending()
      if (p) request(p.cue, why, p.bornAt)
    }, verdict.retryInMs)
  }
  useSoundLog.setState({ last: { id: ++seq, cue, at: Date.now(), verdict, why } })
}

// ---- other windows: the shared clock ------------------------------------------------------------------------------

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    const at = Number(e.newValue)
    if (!Number.isFinite(at)) return
    if (e.key === LAST_KEY) gate.note(at)
    if (e.key === TYPING_KEY) env.typingAt = Math.max(env.typingAt, at)
  })
}

// ---- typing: any key into a field, in any miyagi window ------------------------------------------------------------

const isField = (t: EventTarget | null): boolean => {
  const el = t as HTMLElement | null
  if (!el || typeof el.closest !== 'function') return false
  return !!el.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]')
}
let sharedTypingAt = 0
if (typeof document !== 'undefined') {
  document.addEventListener(
    'keydown',
    (e) => {
      const editKey = e.key.length === 1 || e.key === 'Backspace' || e.key === 'Delete'
      if (!enabled() || !editKey || e.metaKey || e.ctrlKey || !isField(e.target)) return
      const now = Date.now()
      env.typingAt = now
      // Throttled: one localStorage write per 300 ms of typing at most.
      if (now - sharedTypingAt > 300) {
        sharedTypingAt = now
        share(TYPING_KEY, now)
      }
    },
    true
  )

  // ---- taps: a pointer click on the one primary of a surface -------------------------------------------------------
  document.addEventListener(
    'click',
    (e) => {
      const s = useSound.getState()
      if (s.mode !== 'subtle' || !s.taps || e.detail === 0) return // detail 0 = keyboard "click": no tap for keys
      const btn = (e.target as HTMLElement | null)?.closest?.('button')
      if (btn && !btn.disabled && isPrimary(btn)) request('tap', 'primary press')
    },
    true
  )
}

/**
 * The primary: core/ui/buttons.tsx marks it data-button="primary". core/ui/atoms.tsx's PrimaryButton has no marker
 * (Core request: add one); it is the white fill (color.accent), which no option or chrome button uses.
 */
function isPrimary(btn: HTMLElement): boolean {
  if (btn.dataset.button) return btn.dataset.button === 'primary'
  if (!btn.classList.contains('mg-press-light')) return false
  const bg = getComputedStyle(btn).backgroundColor.replace(/\s/g, '')
  return bg === 'rgb(255,255,255)' || bg === 'rgba(255,255,255,1)'
}

// ---- engine moments (overlay only) ---------------------------------------------------------------------------------

/** Lesson id the "done" already played for, so the complete card after the last step doesn't chime twice. */
let doneFor: string | undefined
const lessonKey = (): string => useLesson.getState().lesson?.id ?? 'lesson'

onMessage('step.passed', (p) => {
  if (!hosted || p.skipped || p.already) return
  const { steps } = useLesson.getState()
  const last = steps.length > 0 && steps[steps.length - 1].id === p.stepId && !p.pending && useLesson.getState().complete
  if (last) {
    doneFor = lessonKey()
    request('done', 'last step passed')
  } else request('tick', 'step passed')
})

onMessage('card', (p) => {
  if (!hosted) return
  const raw = p as { kind?: string; skillMap?: unknown }
  if (raw.kind !== 'complete' && !raw.skillMap) return
  if (doneFor === lessonKey()) return
  doneFor = lessonKey()
  request('done', 'lesson complete')
})

onMessage('lesson.ready', () => {
  doneFor = undefined
})
onUi('reset', () => {
  doneFor = undefined
  gate.reset()
  if (retry) clearTimeout(retry)
  retry = undefined
})

// ---- setup finished: Prefs.onboarded turns true (onboarding's markDone) --------------------------------------------

/**
 * Only a change seen AFTER this window has the saved value counts: at startup Prefs begins at the default (false) and
 * then loads true, which is not a setup finishing.
 */
let onboardedBase: boolean | undefined
bridge
  .invoke<{ onboarded?: boolean }>('prefs:get')
  .then((p) => {
    onboardedBase = !!(p?.onboarded ?? usePrefs.getState().onboarded)
  })
  .catch(() => undefined)
usePrefs.subscribe((p) => {
  if (onboardedBase === undefined) return
  if (p.onboarded && !onboardedBase && hosted) request('done', 'setup finished')
  onboardedBase = p.onboarded
})

// ---- Do Not Disturb ------------------------------------------------------------------------------------------------

// The stage has no main process: never in Do Not Disturb.
if (!isElectron) registerWebHandler('sound:dnd', () => false)

let dndTimer: ReturnType<typeof setInterval> | undefined
const readDnd = (): void => {
  bridge
    .invoke<boolean>('sound:dnd')
    .then((on) => (env.dnd = on === true))
    .catch(() => (env.dnd = false))
}
const watchDnd = (): void => {
  const on = hosted && enabled()
  if (on && !dndTimer) {
    readDnd()
    dndTimer = setInterval(readDnd, 30_000)
  } else if (!on && dndTimer) {
    clearInterval(dndTimer)
    dndTimer = undefined
    env.dnd = false
  }
}
useSound.subscribe(watchDnd)

/** The overlay's SoundHost calls this on mount; engine cues play only in a hosted window. */
export function attachSound(): () => void {
  hosted = true
  watchDnd()
  return () => {
    hosted = false
    watchDnd()
  }
}
