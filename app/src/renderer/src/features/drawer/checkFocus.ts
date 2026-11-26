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

let target: string | undefined
bridge.onFeature('front:app', (s) => {
  target = nextTarget(target, s as FrontLike)
})
onMessage('lesson.ended', () => {
  target = undefined
})

/** The bundle a Check press hands focus back to (undefined: main's last non-miyagi app). */
export const checkTarget = (): string | undefined => target

/** Call right after the learner pressed Check (a click or Enter): one activation of their app, nothing else. */
export function handBackAfterCheck(): void {
  if (!isElectron) return
  try {
    bridge.invoke('check:handback', target).catch(() => {})
  } catch {
    // an older main without the handler: nothing to hand back
  }
}
