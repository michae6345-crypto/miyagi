/**
 * Feature: plans. Which Library view is on screen (the Library list, Browse plans, one plan), the two "new plan"
 * dialogs, and the learner's own plans.
 *
 * Wiring: the ui-v4 contract (shared/contracts/UI-V4.md, plan messages) had not landed when this was written, so the
 * learner's plans are a local, typed placeholder (`MyPlan`), and starting a plan sends the one command the contract
 * already has for a catalog lesson: `learn {query: lesson.goal, mode: "lesson"}` (catalog/README: a lesson's goal is
 * the text to build it from). When the plan messages land, `startPlan` / `addPlan` send them instead and `mine` comes
 * from the engine's answer.
 */
import { create } from 'zustand'
import { cmd } from '../../../../common/wire'
import { bridge, isElectron } from '../../bridge'
import { planById, type Plan, type PlanLesson } from './catalog'

export type View = { kind: 'library' } | { kind: 'plans' } | { kind: 'plan'; id: string } | { kind: 'custom'; id: string }
export type Dialog = 'playlist' | 'goal' | null

/** A plan the learner added. `done` = lessons passed. A playlist or goal plan carries its own lessons. */
export type MyPlan = { id: string; title: string; done: number; total: number; next?: string; minutesLeft: number; art: string; lessons?: PlanLesson[]; project?: string; source?: 'playlist' | 'goal' }

type State = { view: View; dialog: Dialog; mine: MyPlan[]; starting?: string }

/** Stage only: ?plans=demo seeds the mock's two plans (Neural networks 3 of 8, Intro to Blender 1 of 10). */
function seed(): MyPlan[] {
  if (isElectron || new URLSearchParams(location.search).get('plans') !== 'demo') return []
  const nn = planById('neural-networks')
  const bl = planById('intro-blender')
  const mk = (p: Plan | undefined, done: number, total: number, left: number): MyPlan[] =>
    p ? [{ id: p.id, title: p.title, done, total, next: p.lessons[done]?.title, minutesLeft: left, art: p.id }] : []
  return [...mk(nn, 3, 8, 120), ...mk(bl, 1, 10, 150)]
}

/** Stage only: ?plan=<id> opens that plan page, ?plans=browse opens Browse plans, ?dialog=playlist|goal a dialog. */
function firstView(): { view: View; dialog: Dialog } {
  if (isElectron) return { view: { kind: 'library' }, dialog: null }
  const q = new URLSearchParams(location.search)
  const plan = q.get('plan')
  const d = q.get('dialog')
  const dialog: Dialog = d === 'playlist' || d === 'goal' ? d : null
  if (plan && planById(plan)) return { view: { kind: 'plan', id: plan }, dialog }
  if (q.get('plans') === 'browse' || dialog) return { view: { kind: 'plans' }, dialog }
  return { view: { kind: 'library' }, dialog }
}

export const usePlans = create<State>(() => ({ ...firstView(), mine: seed() }))
const set = usePlans.setState

export const showLibrary = (): void => set({ view: { kind: 'library' }, dialog: null })
export const showPlans = (): void => set({ view: { kind: 'plans' }, dialog: null })
export const showPlan = (id: string): void => set({ view: planById(id) ? { kind: 'plan', id } : { kind: 'custom', id }, dialog: null })
export const openDialog = (dialog: Exclude<Dialog, null>): void => set({ dialog })
export const closeDialog = (): void => set({ dialog: null })

const learn = (l: PlanLesson): void => bridge.send(cmd('learn', { query: l.goal, mode: 'lesson' }))

/** Start (or continue) a catalog plan: its next lesson is built from the lesson's goal. */
export function startPlan(plan: Plan): void {
  const s = usePlans.getState()
  const mine = s.mine.find((m) => m.id === plan.id)
  const lesson = plan.lessons[mine?.done ?? 0] ?? plan.lessons[0]
  if (!mine) {
    const total = plan.lessons.length
    set({ mine: [...s.mine, { id: plan.id, title: plan.title, done: 0, total, next: lesson.title, minutesLeft: plan.lessons.reduce((n, l) => n + l.minutes, 0), art: plan.id }] })
  }
  learn(lesson)
}

/** Add a plan made in a dialog (from a playlist or a goal). It shows under Your plans; the first lesson starts. */
export function addPlan(p: Omit<MyPlan, 'done'>, start = true): void {
  const s = usePlans.getState()
  set({ mine: [...s.mine.filter((m) => m.id !== p.id), { ...p, done: 0 }], dialog: null, view: { kind: 'library' } })
  if (start && p.lessons?.[0]) learn(p.lessons[0])
}
