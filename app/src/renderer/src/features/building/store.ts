/**
 * Feature: building (Home-Building). Whether the build card is showing, and the two-tap Stop building.
 *
 * It opens on the first v2 lesson.building of a build (one that says what it is doing: phases, stage or source), once
 * per build: "Keep working" folds it back into the building pill for the rest of that build. It closes on
 * lesson.ready (the lesson is there), a failed build (the errors feature's build-failed card, 62, takes over), a
 * disconnect (no `failed` can arrive any more), lesson.ended and a reset. An old engine that sends only message +
 * progress never opens it: the building pill alone says it, as before.
 *
 * Stop building is two taps, like the bar's End: the first arms it for STOP_ARM_MS, the second sends end_lesson
 * (the engine stops the build and answers lesson.ended). Nothing else sends anything.
 */
import { create } from 'zustand'
import { cmd, type Payload } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'

/** How long the first tap on Stop building stays armed. */
export const STOP_ARM_MS = 3000

type BuildCardState = {
  open: boolean
  /** Keep working was pressed during this build: don't open again until the next one. */
  dismissed: boolean
  /** Stop building got its first tap. */
  armed: boolean
}

export const useBuildCard = create<BuildCardState>(() => ({ open: false, dismissed: false, armed: false }))
const set = useBuildCard.setState
const get = useBuildCard.getState

let armTimer: ReturnType<typeof setTimeout> | undefined
const disarm = (): void => {
  clearTimeout(armTimer)
  armTimer = undefined
  if (get().armed) set({ armed: false })
}

/** The build is over (ready, failed, ended, gone): close, and let the next build open the card again. */
function finished(): void {
  disarm()
  set({ open: false, dismissed: false })
}

/** Keep working: back into the building pill; this build won't pop the card again. */
export function keepWorking(): void {
  disarm()
  if (get().open) set({ open: false, dismissed: true })
}

/**
 * The building pill was clicked: the card again, so Stop building is always one click away (a tester, Nov 25, could not
 * stop a lesson mid-build: after Keep working, or for a build that never opened the card, the pill had no click at all).
 * It opens before the engine's first lesson.building too (the pill's "Planning your lesson…"): the card shows its frame
 * and the two actions, and Stop then ends the start the engine has queued or is running (main.py _stop_starts).
 */
export function openBuildCard(): void {
  disarm()
  set({ open: true, dismissed: false })
}

/** Stop building: the first tap arms it, a second one within STOP_ARM_MS sends end_lesson. */
export function tapStop(): void {
  if (!get().open) return
  if (!get().armed) {
    set({ armed: true })
    clearTimeout(armTimer)
    armTimer = setTimeout(disarm, STOP_ARM_MS)
    return
  }
  disarm()
  bridge.send(cmd('end_lesson', {}))
  set({ open: false, dismissed: true })
}

/** A build that says what it is doing (v2): only these open the card. */
export function isV2Build(p: Payload<'lesson.building'>): boolean {
  return !!(p.phases?.length || p.stage || p.source)
}

onMessage('lesson.building', (p) => {
  if (p.failed) return finished()
  if (!isV2Build(p) || get().dismissed || get().open) return
  set({ open: true })
})
onMessage('lesson.ready', finished)
onMessage('step.started', finished)
onMessage('lesson.ended', finished)
onUi('reset', finished)
// The 'dismiss' UI event (the stage's Esc, a card's ✕) folds it like Keep working. In Electron the overlay window is
// not focusable, so Esc never reaches it there (launcher.md Core request 16).
onUi('dismiss', keepWorking)
// Dropped mid-build: no `failed` can arrive any more (core drops the building pill the same way).
useLesson.subscribe((s, prev) => {
  if (prev.connected && !s.connected) finished()
})
