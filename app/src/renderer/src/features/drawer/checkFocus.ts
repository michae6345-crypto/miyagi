/**
 * Feature: drawer. After a Check press (Check my work / Check again, on the panel, the player or a card), the keyboard
 * goes back to the app the learner works in, once (main/features/checkFocus.ts runs `open -b`). Never a miyagi window:
 * the check's answer shows in the overlay (Nov 25, Michael: every Check brought the dashboard forward).
 *
 * Which app: the last front app that was one of the lesson's apps (front-app.ts marks VS Code, the terminals, and every
 * app the engine named this lesson: Blender, a CAD app...), from the front:app broadcast. Main falls back to the last
 * non-miyagi front app when this has none.
 */
import { bridge, isElectron } from '../../bridge'
import { onMessage } from '../../core/bus'

/** The front:app broadcast, as much of it as this needs (main/features/front-app.ts FrontState). */
export type FrontLike = { known?: boolean; bundle?: string; miyagi?: boolean; lesson?: boolean }

/** The lesson app to hand back to, after this front:app update: a known, non-miyagi lesson app replaces it. */
export function nextTarget(prev: string | undefined, s: FrontLike | undefined): string | undefined {
  if (!s || !s.known || s.miyagi || !s.lesson || !s.bundle) return prev
  return s.bundle
}

/** The last non-miyagi front app, and whether it was one of the lesson's (main hands back only to a lesson app). */
export function nextLast(prev: { bundle: string; lesson: boolean } | undefined, s: FrontLike | undefined): { bundle: string; lesson: boolean } | undefined {
  if (!s || !s.known || s.miyagi || !s.bundle) return prev
  return { bundle: s.bundle, lesson: !!s.lesson }
}

let target: string | undefined
let last: { bundle: string; lesson: boolean } | undefined
bridge.onFeature('front:app', (s) => {
  target = nextTarget(target, s as FrontLike)
  last = nextLast(last, s as FrontLike)
})
onMessage('lesson.ended', () => {
  target = undefined
})

/** What main decides from (main/features/checkFocus.ts pickTarget). */
export const checkTarget = (): { lesson?: string; last?: { bundle: string; lesson: boolean } } => ({ lesson: target, last })

/** Call right after the learner pressed Check (a click or Enter): at most one activation of their app, nothing else. */
export function handBackAfterCheck(): void {
  if (!isElectron) return
  try {
    bridge.invoke('check:handback', checkTarget()).catch(() => {})
  } catch {
    // an older main without the handler: nothing to hand back
  }
}
