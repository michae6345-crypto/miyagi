/**
 * v2 (A2): the cards and the docked lesson panel (A1, features/drawer) must never draw the same thing twice.
 *
 * While the panel is SHOWN (core/dock `open`, not collapsed to the Mini pill), a card the panel renders itself is
 * "panel-routed" and the island skips it (BUILD-PLAN A2: no double render in the notyet and hint shots). Collapsed to
 * the Mini pill, or with no panel at all, every card grows out of the pill as before.
 *
 * Who decides: A1's `isPanelRouted` (BUILD-PLAN A1 "isPanelRouted exported"), found at runtime in any drawer module so
 * this file compiles with or without A1. It always gets an object, never a bare kind: the engine card itself
 * (`isPanelRouted(card)`), or the live off-track as `isPanelRouted({ kind: 'offtrack', ...offtrack })`, so A1 can keep an
 * off-track that carries a fix (diff, level 3, apply_fix) on the island, where "Do it for me" lives. The step-passed card
 * ('success') is not one A1 models, so it stays routed whenever the panel shows (decision 7: Les-Passed draws it).
 * Until A1 lands, FALLBACK_ROUTED stands in: the Not yet card (offtrack, its "Waiting for the fix" view), the
 * step-passed card and the hint card, the three the Les-NotYet / Les-Hint / Les-Passed panels draw.
 */
import type { Payload } from '../../../../common/wire'
import { useDock } from '../../core/dock'
import type { Offtrack } from '../../core/lesson'

/** The island modes / card kinds this feature asks about: its three modes plus every engine card kind. */
export type RoutedKind = 'offtrack' | 'success' | Payload<'card'>['kind'] | 'complete'

type AnyFn = (...args: unknown[]) => unknown

/** What A1 exports, once its modules have loaded (they are already in the bundle; this only reads their exports). */
const found: Record<string, AnyFn | undefined> = {}
const WANTED = ['isPanelRouted', 'openPanel'] as const
const drawerModules = import.meta.glob('../drawer/**/*.{ts,tsx}')

function scan(mod: unknown): void {
  if (!mod || typeof mod !== 'object') return
  const m = mod as Record<string, unknown>
  for (const name of WANTED) {
    if (typeof m[name] === 'function') found[name] ??= m[name] as AnyFn
    // `useDrawer.openPanel` (the plan's wording): a method on the drawer store's state.
    const store = m.useDrawer as { getState?: () => Record<string, unknown> } | undefined
    const viaStore = typeof store?.getState === 'function' ? store.getState()[name] : undefined
    if (!found[name] && typeof viaStore === 'function') found[name] = (...a: unknown[]) => (store!.getState!()[name] as AnyFn)(...a)
  }
}

// Read after this module has finished loading (dynamic imports never re-enter a module mid-evaluation).
void Promise.all(Object.values(drawerModules).map((load) => load().then(scan, () => undefined)))

/** A1's export by name (`isPanelRouted`, `openPanel`), or undefined while A1 isn't there. */
export function drawerExport(name: (typeof WANTED)[number]): AnyFn | undefined {
  return found[name]
}

/** The cards the panel draws itself when A1 doesn't say (Les-NotYet, Les-Hint, Les-Passed). */
const FALLBACK_ROUTED = new Set<RoutedKind>(['offtrack', 'success', 'hint'])

/** What isRouted asks about: the engine card, or the live off-track (lesson.offtrack). */
export type RoutedSubject = Payload<'card'> | Offtrack

/** Does the panel draw this card itself? (Only matters while it's shown: see usePanelShown.) */
export function isRouted(kind: RoutedKind, live?: RoutedSubject): boolean {
  // A1 doesn't model the step-passed card; with the panel shown it's always Les-Passed's (decision 7).
  if (kind === 'success') return true
  const fn = found.isPanelRouted
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

/** This card is drawn by the panel right now, so the island skips it. */
export function useRoutedAway(kind: RoutedKind | undefined, live?: RoutedSubject): boolean {
  const shown = usePanelShown()
  return shown && !!kind && isRouted(kind, live)
}
