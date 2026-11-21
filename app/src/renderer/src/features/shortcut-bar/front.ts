/**
 * The app in front, and "away" (Michael's review of desktop tests 2-3, A8 / A9).
 *
 * main/features/front-app.ts broadcasts which app is in front (macOS; unknown elsewhere, which counts as the lesson's).
 * Away: a lesson is on, a non-lesson app has been in front for AWAY_MS, and the pointer isn't on the bar. The bar folds
 * to its handle (fold.ts) and main makes the whole overlay click-through, drawer and cards included ('overlay:away',
 * main/features/overlay-raise.ts). It ends when a lesson app is in front again, the pointer reaches the bar's handle
 * or any shortcut fires (wake()), or the pointer rests on the island (main's 'overlay:wake').
 * features/spotlight/store.ts reads useFront for A9 (the box only while its app is in front).
 *
 * Browser stage (no main): window.__miyagiFront({ known: true, name: 'Google Chrome', aliases: ['google chrome'], lesson: false })
 * plays an app switch; __miyagiFront({ lesson: true }) comes back.
 */
import { create } from 'zustand'
import { bridge, isElectron, registerWebHandler } from '../../bridge'
import { onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { barHovered, reveal } from './fold'

/** Mirror of FrontState in main/features/front-app.ts. */
export type FrontState = {
  known: boolean
  name: string
  bundle: string
  /** Lowercase names the front app goes by ("code", "visual studio code"…). */
  aliases: string[]
  miyagi: boolean
  lesson: boolean
}
const UNKNOWN: FrontState = { known: false, name: '', bundle: '', aliases: [], miyagi: false, lesson: true }

/** How long another app is in front before the overlay steps aside. */
export const AWAY_MS = 3000
/** The pointer was on the bar when the count ran out: look again this soon. */
const RECHECK_MS = 1000

export const useFront = create<FrontState & { away: boolean }>(() => ({ ...UNKNOWN, away: false }))

/** A lesson is on and a known, non-lesson app is in front. */
function elsewhere(): boolean {
  const f = useFront.getState()
  return f.known && !f.lesson && !f.miyagi && !!useLesson.getState().lesson
}

function tellMain(on: boolean): void {
  try {
    bridge.invoke('overlay:away', on).catch(() => {})
  } catch {
    // no handler (older main): nothing to tell
  }
}

function setAway(on: boolean): void {
  if (useFront.getState().away === on) return
  useFront.setState({ away: on })
  tellMain(on)
  // Back: the bar comes out (and folds again IDLE_MS later if the pointer stays off it).
  if (!on) reveal()
}

let timer: ReturnType<typeof setTimeout> | undefined
function expire(): void {
  timer = undefined
  if (!elsewhere()) return setAway(false)
  if (barHovered()) {
    timer = setTimeout(expire, RECHECK_MS)
    return
  }
  setAway(true)
}

/** Re-read the situation: back in a lesson app ends away at once; another app starts the count (if not running). */
function update(): void {
  if (!elsewhere()) {
    clearTimeout(timer)
    timer = undefined
    return setAway(false)
  }
  if (useFront.getState().away || timer) return
  timer = setTimeout(expire, AWAY_MS)
}

/** The learner reached for miyagi (the handle, a shortcut, a rest on the island): back now, a fresh count after. */
export function wake(): void {
  clearTimeout(timer)
  timer = undefined
  setAway(false)
  update()
}

function apply(s: unknown): void {
  if (!s || typeof s !== 'object') return
  useFront.setState({ ...UNKNOWN, ...(s as Partial<FrontState>) })
  update()
}

registerWebHandler('front:state', () => UNKNOWN)
registerWebHandler('overlay:away', (on) => !!on)

bridge.onFeature('front:app', apply)
bridge.onFeature('overlay:wake', wake)
try {
  bridge.invoke('front:state').then(apply, () => {})
} catch {
  // no handler yet: the first broadcast brings it
}
useLesson.subscribe((s, prev) => {
  if (!!s.lesson !== !!prev.lesson) update()
})
onUi('shortcut', () => {
  if (useFront.getState().away) wake()
})

if (!isElectron && typeof window !== 'undefined') {
  ;(window as unknown as { __miyagiFront?: (s: Partial<FrontState>) => void }).__miyagiFront = (s) => apply({ ...useFront.getState(), ...s })
}
