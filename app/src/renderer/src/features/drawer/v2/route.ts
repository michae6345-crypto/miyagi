/**
 * Feature: drawer (v2, A1). Which engine cards the lesson panel renders itself while it is shown, so the island skips
 * them (A2: "no double render"). Exported from features/drawer/store.ts as isPanelRouted / usePanelRouted.
 *
 *   isPanelRouted(card)                  a card {kind:"hint"} (Les-Hint) or a judge "Not yet" card (Les-NotYet) for the
 *                                        step on screen, while the panel is open. Cards with a diff or output preview
 *                                        stay on the island (the panel has no fix preview).
 *   isPanelRouted({ kind: 'offtrack' })  the off-track diagnosis for this step, unless it carries a fix (a diff, or
 *                                        apply_fix at hint level 3): "Do it for me" lives on the island card.
 *
 * Both answer false while the panel is collapsed (Mini) or in a video lesson (the old drawer), so the island shows
 * everything as before. Imports core and ./panelStore only.
 */
import { useDock } from '../../../core/dock'
import { useLesson, type Offtrack } from '../../../core/lesson'
import { forCurrentStep, isHintCard, isNotYetCard, type PanelCard } from './panelStore'

export type Routable = PanelCard | ({ kind: 'offtrack' } & Partial<Pick<Offtrack, 'stepId' | 'diff' | 'actions' | 'level'>>)

/** The v2 panel is the lesson's surface right now: a "Just teach me" lesson with the panel open. */
export function panelShown(): boolean {
  return useDock.getState().open && useLesson.getState().lesson?.mode === 'lesson'
}

/** Would the panel render this, if it is shown? */
export function panelRenders(x: Routable | undefined): boolean {
  if (!x) return false
  if (x.kind === 'offtrack') {
    const o = x as Extract<Routable, { kind: 'offtrack' }>
    const fix = !!o.diff || o.level === 3 || !!o.actions?.includes('apply_fix')
    return !fix && forCurrentStep(o)
  }
  const c = x as PanelCard
  return (isHintCard(c) || isNotYetCard(c)) && forCurrentStep(c)
}

/** Does the panel render this right now (so the island must not)? */
export function isPanelRouted(x: Routable | undefined): boolean {
  return panelShown() && panelRenders(x)
}

/** isPanelRouted as a hook: re-renders when the panel opens or collapses, or the step changes. */
export function usePanelRouted(x: Routable | undefined): boolean {
  const open = useDock((d) => d.open)
  const lessonMode = useLesson((s) => s.lesson?.mode === 'lesson')
  useLesson((s) => s.stepId)
  return open && lessonMode && panelRenders(x)
}
