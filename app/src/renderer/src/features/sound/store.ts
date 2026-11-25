/**
 * Feature: sound. Turns app moments into cues, through the gate, without touching any other feature.
 *
 *   step.passed (not skipped, not "already")       tick   (the lesson's last step: done)
 *   card kind "complete" / a skill map             done   (once per lesson; skipped if the last step already chimed)
 *   onUi('setup-done') (Core request 4)            done   (the learner pressed the last setup button; reruns only)
 *   a pointer press on a primary button            tap    (only with the taps sub-toggle)
 *
 * Engine cues play in ONE window: the overlay (index.tsx mounts SoundHost there, like voice's speaker), since every
 * window receives the engine feed. Taps play in the window that was clicked. All windows share the "last cue" time and
 * the "last keystroke" time through localStorage, so no two cues overlap across windows.
 *
 * Typing: the learner types in VS Code and the terminal, which miyagi windows never see, and steps pass live while
 * they type. So before an engine cue the store asks main for the system idle time (sound:idle, any key or mouse input
 * in any app); under a second counts as busy, and the gate holds the cue, the store samples the idle clock again every
 * 225 ms and plays at the first quiet sample, and drops it 2.5 s after the pass if the input never stops.
 *
 *   useSoundLog(s => s.last)   the last cue asked for and what the gate said (the stage monitor reads it)
 */
import { create } from 'zustand'
import { bridge, isElectron, registerWebHandler } from '../../bridge'
import { onMessage, onUi, type UiEvent } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { createGate, withSystemIdle, type Verdict } from './gate'
import { playCue } from './player'
import { useSound } from './settings'
import type { Cue } from './synth'

export type SoundEvent = { id: number; cue: Cue; at: number; verdict: Verdict; why: string }
export const useSoundLog = create<{ last?: SoundEvent }>(() => ({}))

const gate = createGate()
const local = { typingAt: 0, dnd: false }
let hosted = false
let seq = 0
let retry: ReturnType<typeof setTimeout> | undefined
/** Bumped by a lesson reset: a sound:idle answer still in flight from before it must not decide in the new lesson. */
let generation = 0

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

/** The cue the gate is holding, with its own reason and whether it watches system input (a retry reuses both). */
let held: { cue: Cue; why: string; system: boolean } | undefined

/**
 * Ask for a cue. `why` is for the stage monitor and the brief, never shown in the app. `system`: also hold it while
 * the learner is busy anywhere on the Mac (engine cues; not a cue answering a click in miyagi).
 */
export function request(cue: Cue, why: string, opts: { bornAt?: number; system?: boolean } = {}): void {
  const bornAt = opts.bornAt ?? Date.now()
  const system = opts.system === true && cue !== 'tap'
  const gen = generation
  if (!system || !enabled()) return decide(cue, why, bornAt, system, undefined, gen)
  bridge
    .invoke<number>('sound:idle')
    .then((idle) => decide(cue, why, bornAt, system, idle, gen))
    .catch(() => decide(cue, why, bornAt, system, undefined, gen))
}

function decide(cue: Cue, why: string, bornAt: number, system: boolean, idleSeconds: number | undefined, gen: number): void {
  if (gen !== generation) return // asked before a lesson reset: the old lesson's cue never plays in the new one
  const s = useSound.getState()
  const env = withSystemIdle({ now: Date.now(), enabled: s.mode === 'subtle', taps: s.taps, typingAt: local.typingAt, dnd: local.dnd }, idleSeconds)
  const verdict = gate.ask(cue, env, bornAt)
  if (verdict.play) {
    playCue(cue, s.dry)
    share(LAST_KEY, Date.now())
  }
  const waiting = gate.pending()
  if (verdict.play === false && verdict.reason === 'held') {
    held = { cue, why, system }
    if (retry) clearTimeout(retry)
    retry = setTimeout(() => {
      retry = undefined
      const p = gate.pending()
      if (!p) return
      const h = held?.cue === p.cue ? held : { cue: p.cue, why, system }
      request(p.cue, h.why, { bornAt: p.bornAt, system: h.system })
    }, verdict.retryInMs)
  } else if (!waiting || waiting.cue !== held?.cue) held = undefined
  const busy = env.systemBusy === true
  useSoundLog.setState({ last: { id: ++seq, cue, at: Date.now(), verdict, why: busy ? `${why}, input elsewhere` : why } })
}

// ---- other windows: the shared clock ------------------------------------------------------------------------------

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    const at = Number(e.newValue)
    if (!Number.isFinite(at)) return
    if (e.key === LAST_KEY) gate.note(at)
    if (e.key === TYPING_KEY) local.typingAt = Math.max(local.typingAt, at)
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
      local.typingAt = now
      // Throttled: one localStorage write per 300 ms of typing at most.
      if (now - sharedTypingAt > 300) {
        sharedTypingAt = now
        share(TYPING_KEY, now)
      }
    },
    true
  )

  // ---- taps: a pointer press on the one primary of a surface -------------------------------------------------------
  // pointerdown, not click: the press dip (pressMotion whileTap) shows on press-down, and click waits for mouse-up, so
  // on a slow press the sound would trail the visual. Left button, mouse or pen only; keys never tap.
  document.addEventListener(
    'pointerdown',
    (e) => {
      const s = useSound.getState()
      if (s.mode !== 'subtle' || !s.taps || e.button !== 0 || !e.isPrimary) return
      if (e.pointerType !== 'mouse' && e.pointerType !== 'pen') return
      const btn = (e.target as HTMLElement | null)?.closest?.('button')
      if (btn && !btn.disabled && isPrimary(btn)) request('tap', 'primary press')
    },
    true
  )
}

/**
 * The primary: core/ui/buttons.tsx marks it data-button="primary". core/ui/atoms.tsx's PrimaryButton and
 * core/ui/glass.tsx's GlassPrimary have no marker yet (Core request 3); the fallback reads the white fill
 * (color.accent), which no option or chrome button uses. GlassPrimary in light appearance is ink, so it gets no tap
 * until it carries the marker.
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
    request('done', 'last step passed', { system: true })
  } else request('tick', 'step passed', { system: true })
})

onMessage('card', (p) => {
  if (!hosted) return
  const raw = p as { kind?: string; skillMap?: unknown }
  if (raw.kind !== 'complete' && !raw.skillMap) return
  if (doneFor === lessonKey()) return
  doneFor = lessonKey()
  request('done', 'lesson complete', { system: true })
})

onMessage('lesson.ready', () => {
  doneFor = undefined
})
onUi('reset', () => {
  generation++
  doneFor = undefined
  gate.reset()
  if (retry) clearTimeout(retry)
  retry = undefined
  held = undefined
})

// ---- setup finished: an explicit UI event, never a Prefs flip --------------------------------------------------------

/**
 * Core request 4: the one-window setup lane emits onUi('setup-done') when the learner presses its last button. Not
 * Prefs.onboarded: markDone() also runs on the first frame of setup when every permission is already granted (a
 * reinstall), which would chime before anything was done. Sounds are Off by default and set in Settings after setup,
 * so in practice this only plays when setup is run again. Not gated on `hosted` and no system-input hold: it answers a
 * click in the window that finished. Cast: 'setup-done' joins the UiEvent union with Core request 4.
 */
onUi('setup-done' as UiEvent, () => {
  request('done', 'setup finished')
})

// ---- Do Not Disturb ------------------------------------------------------------------------------------------------

// The stage has no main process: never in Do Not Disturb, and the system is idle unless ?busy=1 (the learner is
// typing in another app right now: engine cues wait, then drop) or ?busy=input (idle is whole seconds since the last
// key or pointer press in the stage page, like getSystemIdleTime: press a key, then a test Tick, to see the poll).
if (!isElectron) {
  let lastInput = 0
  const mark = (): void => void (lastInput = Date.now())
  if (typeof document !== 'undefined') {
    document.addEventListener('keydown', mark, true)
    document.addEventListener('pointerdown', mark, true)
  }
  registerWebHandler('sound:dnd', () => false)
  registerWebHandler('sound:idle', () => {
    const busy = new URLSearchParams(location.search).get('busy')
    if (busy === '1') return 0
    if (busy === 'input') return Math.floor((Date.now() - lastInput) / 1000)
    return 60
  })
}

let dndTimer: ReturnType<typeof setInterval> | undefined
const readDnd = (): void => {
  bridge
    .invoke<boolean>('sound:dnd')
    .then((on) => (local.dnd = on === true))
    .catch(() => (local.dnd = false))
}
const watchDnd = (): void => {
  const on = hosted && enabled()
  if (on && !dndTimer) {
    readDnd()
    dndTimer = setInterval(readDnd, 30_000)
  } else if (!on && dndTimer) {
    clearInterval(dndTimer)
    dndTimer = undefined
    local.dnd = false
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
