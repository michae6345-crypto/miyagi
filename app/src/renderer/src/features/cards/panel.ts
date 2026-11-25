/**
 * v2 (A2): the cards and the docked lesson panel (A1, features/drawer) must never draw the same thing twice.
 *
 * While the panel is SHOWN (core/dock `open`, not collapsed to the Mini pill), a card the panel renders itself is
 * "panel-routed" and the island skips it (BUILD-PLAN A2: no double render in the notyet and hint shots). Collapsed to
 * the Mini pill, or with no panel at all, a card that is new since the panel last showed grows out of the pill as before
 * (one the panel already showed is spent: cards/store.ts consumeRouted).
 *
 * Who decides: A1's `isPanelRouted` (BUILD-PLAN A1 "isPanelRouted exported"), read off features/drawer/store.ts at call
 * time through a namespace import, so this file compiles and runs with or without A1. It always gets an object, never a
 * bare kind: the engine card itself (`isPanelRouted(card)`), or the live off-track as
 * `isPanelRouted({ kind: 'offtrack', ...offtrack })`, so A1 can keep an off-track that carries a fix (diff, level 3,
 * apply_fix) on the island, where "Do it for me" lives. The step-passed card ('success') is not one A1 models, so it
 * stays routed whenever the panel shows (decision 7: Les-Passed draws it).
 * Until A1 lands, FALLBACK_ROUTED stands in: the Not yet card (offtrack, its "Waiting for the fix" view), the
 * step-passed card and the hint card, the three the Les-NotYet / Les-Hint / Les-Passed panels draw.
 *
 * Also here: A1's panel store (`usePanel` and its `heldPass`: Les-Passed stays up until the learner presses Next step),
 * read only, so the pill says "Step N passed" exactly as long as the panel does (pill/store.ts useHeldPass).
 */
import type { Payload } from '../../../../common/wire'
import { useDock } from '../../core/dock'
import { useLesson, type Offtrack } from '../../core/lesson'
import * as drawerStore from '../drawer/store'

/** The island modes / card kinds this feature asks about: its three modes plus every engine card kind. */
export type RoutedKind = 'offtrack' | 'success' | Payload<'card'>['kind'] | 'complete'

type AnyFn = (...args: unknown[]) => unknown

/**
 * features/drawer/store.ts as a plain record, read by name at call time, never while modules load (the drawer store and
 * this module import each other through cards/store). A name A1 doesn't export yet is just undefined.
 *
 * A function, not a constant: in a production bundle the drawer store's namespace object is built when that module runs,
 * which is after this one, so `const drawer = drawerStore` captured undefined for good and the first read threw
 * ("Cannot read properties of undefined (reading 'usePanel')": the island crashed and hid as soon as a lesson with the
 * panel started). The dev server's native modules hid it, because there the namespace exists before any module runs.
 */
const drawer = (): Record<string, unknown> => (drawerStore as Record<string, unknown> | undefined) ?? {}
type DrawerName = 'isPanelRouted' | 'openPanel'

/** A1's export by name (`isPanelRouted`, `openPanel`, or `useDrawer.getState().openPanel`), or undefined while A1 isn't there. */
export function drawerExport(name: DrawerName): AnyFn | undefined {
  const direct = drawer()[name]
  if (typeof direct === 'function') return direct as AnyFn
  // `useDrawer.openPanel` (the plan's wording): a method on the drawer store's state.
  const store = drawer().useDrawer as { getState?: () => Record<string, unknown> } | undefined
  const viaStore = typeof store?.getState === 'function' ? store.getState()[name] : undefined
  return typeof viaStore === 'function' ? (...a: unknown[]) => (store!.getState!()[name] as AnyFn)(...a) : undefined
}

/** The slice of A1's panel store (drawer/v2/panelStore.ts `usePanel`) the pill reads. */
export type HeldPassStore = {
  getState: () => { heldPass?: { stepId: string } }
  subscribe: (fn: () => void) => () => void
}
/**
 * drawer/store.ts doesn't re-export A1's panel store yet (pill.md Core request 6), so that one module is also looked up by
 * its exact path: eager (evaluated with the bundle like a static import, no async scan) and nothing else under drawer/.
 * Before A1 lands the map is empty.
 */
const panelStoreModule = Object.values(import.meta.glob<Record<string, unknown>>('../drawer/v2/panelStore.ts', { eager: true }))[0]
const isStore = (x: unknown): x is HeldPassStore =>
  typeof x === 'function' && typeof (x as Partial<HeldPassStore>).getState === 'function' && typeof (x as Partial<HeldPassStore>).subscribe === 'function'

/** A1's panel store (`usePanel`): drawer/store.ts's re-export when there is one, else its own module; undefined before A1. */
export function panelStore(): HeldPassStore | undefined {
  const viaDrawer = drawer().usePanel
  if (isStore(viaDrawer)) return viaDrawer
  const own = panelStoreModule?.usePanel
  return isStore(own) ? own : undefined
}

/** The cards the panel draws itself when A1 doesn't say (Les-NotYet, Les-Hint, Les-Passed). */
const FALLBACK_ROUTED = new Set<RoutedKind>(['offtrack', 'success', 'hint'])

/** What isRouted asks about: the engine card, or the live off-track (lesson.offtrack). */
export type RoutedSubject = Payload<'card'> | Offtrack

/** Does the panel draw this card itself? (Only matters while it's shown: see usePanelShown.) */
export function isRouted(kind: RoutedKind, live?: RoutedSubject): boolean {
  // A1 doesn't model the step-passed card; with the panel shown it's always Les-Passed's (decision 7).
  if (kind === 'success') return true
  const fn = drawerExport('isPanelRouted')
  if (!fn) return FALLBACK_ROUTED.has(kind)
  try {
    return fn({ kind, ...live }) === true
  } catch {
    return false
  }
}

/** The lesson panel is on screen (docked open, not the Mini pill). */
export const panelShown = (): boolean => {
  const d = useDock.getState()
  return d.open && !d.collapsed
}
export function usePanelShown(): boolean {
  return useDock((d) => d.open && !d.collapsed)
}

/**
 * This card is drawn by the panel right now, so the island skips it. Subscribes to everything A1's answer reads (the
 * dock, the current step, the lesson mode), so a card for a step that moved on or a mode change is re-asked at once.
 * (A1's own `usePanelRouted` hook isn't called: it isn't there before A1 lands, and a hook that is sometimes there and
 * sometimes not can't keep a stable call order.)
 */
export function useRoutedAway(kind: RoutedKind | undefined, live?: RoutedSubject): boolean {
  const shown = usePanelShown()
  useLesson((s) => s.stepId)
  useLesson((s) => s.lesson?.mode)
  return shown && !!kind && isRouted(kind, live)
}
