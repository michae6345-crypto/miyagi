/**
 * Feature: plans. Which Library view is on screen (the Library list, Browse plans, one plan), the two "new plan"
 * dialogs, and the learner's own plans.
 *
 * Wiring: the ui-v4 contract (shared/contracts/UI-V4.md "Plans"). The Library sends `plans.list {}` when it mounts and
 * `mine` is the engine's `plans` answer (it is pushed again whenever a plan lesson changes state). Starting a catalog
 * plan sends `plan.start {catalogId, reqId}`; a dialog's plan sends `plan.start {playlistId, url, proposal}` or
 * `plan.start {goal, proposal}`; removing one sends `plan.remove {id}`. Every lesson of a plan starts with
 * `plan: {id, index}`: `library.start {id, plan}` once it was built, `learn_url {url, plan}` for a video,
 * `learn {query: goal, mode: "lesson", plan}` otherwise.
 *
 * Fallback: with no engine answer (the browser stage without ?scenario=ui-v4, an engine without the plan messages),
 * a started plan is kept locally in the same PlanState shape, and ?plans=demo seeds the mock's two plans.
 */
import { create } from 'zustand'
import type { PlanLessonRef, PlanProposal, PlanState } from '../../../../../../shared/contracts/events'
import { cmd } from '../../../../common/wire'
import { bridge, isElectron } from '../../bridge'
import { onMessage } from '../../core/bus'
import { setPage } from '../shell/store'
import { setSidebarFeed } from '../shell/ui'
import { planById, planStateFromCatalog, planStateFromProposal, type CatalogPlan } from './catalog'

export type View = { kind: 'library' } | { kind: 'plans' } | { kind: 'plan'; id: string } | { kind: 'custom'; id: string }
export type Dialog = 'playlist' | 'goal' | null

/** A plan the learner has: the contract's PlanState, as the engine sends it. */
export type MyPlan = PlanState

type State = {
  view: View
  dialog: Dialog
  mine: MyPlan[]
  /** The engine answered plans.list (or pushed plans) at least once. */
  fromEngine: boolean
}

/** Stage only: ?plans=demo seeds the mock's two plans (Neural networks 3 of 8, Intro to Blender 1 of 10). */
function seed(): MyPlan[] {
  if (isElectron || new URLSearchParams(location.search).get('plans') !== 'demo') return []
  const mk = (p: CatalogPlan | undefined, done: number): MyPlan[] => (p ? [planStateFromCatalog(p, done)] : [])
  return [...mk(planById('neural-networks'), 3), ...mk(planById('intro-blender'), 1)]
}

/** Stage only: ?plan=<id> opens that plan page, ?plans=browse opens Browse plans, ?dialog=playlist|goal a dialog. */
function firstView(): { view: View; dialog: Dialog } {
  if (isElectron) return { view: { kind: 'library' }, dialog: null }
  const q = new URLSearchParams(location.search)
  const plan = q.get('plan')
  const d = q.get('dialog')
  const dialog: Dialog = d === 'playlist' || d === 'goal' ? d : null
  if (plan) return { view: planById(plan) ? { kind: 'plan', id: plan } : { kind: 'custom', id: plan }, dialog }
  if (q.get('plans') === 'browse' || dialog) return { view: { kind: 'plans' }, dialog }
  return { view: { kind: 'library' }, dialog }
}

export const usePlans = create<State>(() => ({ ...firstView(), mine: seed(), fromEngine: false }))
const set = usePlans.setState
const get = usePlans.getState

export const showLibrary = (): void => set({ view: { kind: 'library' }, dialog: null })
export const showPlans = (): void => set({ view: { kind: 'plans' }, dialog: null })
export const showPlan = (id: string): void => set({ view: planById(id) ? { kind: 'plan', id } : { kind: 'custom', id }, dialog: null })
export const openDialog = (dialog: Exclude<Dialog, null>): void => set({ dialog })
export const closeDialog = (): void => set({ dialog: null })

/** The learner's plan with this id (a preset's id is its catalog id). */
export const myPlan = (id: string): MyPlan | undefined => get().mine.find((m) => m.id === id || m.catalogId === id)

let seq = 0
export const reqId = (kind: string): string => `r-${kind}-${Date.now().toString(36)}-${++seq}`

// ---- the engine's answers ---------------------------------------------------------------------------------------

/** plan.start answers with the full list; the plan it added is started once the list lands (or locally after WAIT_MS). */
type Pending = { reqId: string; before: Set<string>; match: (p: PlanState) => boolean; local: PlanState; timer: ReturnType<typeof setTimeout>; index?: number }
let pending: Pending | undefined
const WAIT_MS = 2500

const isPlan = (p: unknown): p is PlanState => !!p && typeof p === 'object' && typeof (p as PlanState).id === 'string' && typeof (p as PlanState).title === 'string' && Array.isArray((p as PlanState).lessons)

onMessage('plans', (payload) => {
  const items = Array.isArray(payload?.items) ? payload.items.filter(isPlan) : []
  set({ mine: items, fromEngine: true })
  const p = pending
  if (!p) return
  // The plan the start added: the one that wasn't there before, else the one it names (a preset already on the list).
  const added = items.find((i) => !p.before.has(i.id) && p.match(i)) ?? items.find((i) => !p.before.has(i.id)) ?? items.find(p.match)
  if (payload?.reqId !== undefined && payload.reqId !== p.reqId && !added) return
  clearTimeout(p.timer)
  pending = undefined
  startAt(added ?? p.local, p.index)
})

/** Ask for the learner's plans (the Library, Browse plans and a plan page call it when they mount). */
export function loadPlans(): void {
  bridge.send(cmd('plans.list', {}))
}

// ---- starting ---------------------------------------------------------------------------------------------------

const watchUrl = (videoId: string): string => `https://www.youtube.com/watch?v=${videoId}`

/** Start lesson `index` of a plan, with `plan: {id, index}` so the engine marks it. */
export function startLesson(p: PlanState, index: number): void {
  const l = p.lessons[index]
  if (!l) return
  const plan: PlanLessonRef = { id: p.id, index }
  if (l.libraryId) bridge.send(cmd('library.start', { id: l.libraryId, plan }))
  else if (l.videoId) bridge.send(cmd('learn_url', { url: watchUrl(l.videoId), plan }))
  else if (l.goal) bridge.send(cmd('learn', { query: l.goal, mode: 'lesson', plan }))
}

/** Lesson `index` when one was picked, else the plan's next lesson. */
function startAt(p: PlanState, index: number | undefined): void {
  if (index !== undefined) startLesson(p, index)
  else startNext(p)
}

/** Start (or continue) a plan at its next lesson. */
export function startNext(p: PlanState): void {
  const index = p.nextIndex ?? p.lessons.findIndex((l) => l.state === 'next' || l.state === 'in_progress' || l.state === 'todo')
  if (index === null || index < 0) return
  startLesson(p, index)
}

function begin(local: PlanState, match: (p: PlanState) => boolean, payload: { catalogId?: string; playlistId?: string; url?: string; goal?: string; proposal?: PlanProposal }, start: boolean, index?: number): void {
  const s = get()
  const id = reqId('plan')
  if (pending) clearTimeout(pending.timer)
  const before = new Set(s.mine.map((m) => m.id))
  // Shown at once (the engine's answer replaces it); started at once only when nothing answers.
  set({ mine: [...s.mine.filter((m) => m.id !== local.id), local] })
  const timer = setTimeout(() => {
    if (pending?.reqId !== id) return
    pending = undefined
    if (start) startAt(myPlan(local.id) ?? local, index)
  }, WAIT_MS)
  pending = start ? { reqId: id, before, match, local, timer, index } : undefined
  if (!start) clearTimeout(timer)
  bridge.send(cmd('plan.start', { ...payload, reqId: id }))
}

/**
 * Start (or continue) a catalog plan: plan.start {catalogId}, then its next lesson, or lesson `index` when the learner
 * picked one on the plan page (a plan they haven't added yet is added first, so the lesson still carries plan: {id, index}).
 */
export function startPlan(plan: CatalogPlan, index?: number): void {
  const mine = myPlan(plan.id)
  if (mine) return startAt(mine, index)
  begin(planStateFromCatalog(plan), (p) => p.catalogId === plan.id || p.id === plan.id, { catalogId: plan.id }, true, index)
}

/** A plan made in the playlist dialog: plan.start {playlistId, url, proposal} (skipped videos carry skip: true). */
export function addPlaylistPlan(info: { playlistId: string; url: string }, proposal: PlanProposal, start = true): void {
  const local = planStateFromProposal(`pl-${info.playlistId}`, proposal, { playlistId: info.playlistId, url: info.url })
  set({ dialog: null, view: { kind: 'library' } })
  begin(local, (p) => p.playlistId === info.playlistId, { playlistId: info.playlistId, url: info.url, proposal }, start)
}

/** A plan made in the goal dialog: plan.start {goal, proposal}. */
export function addGoalPlan(goal: string, proposal: PlanProposal, start = true): void {
  const local = planStateFromProposal(`goal-${goal.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40)}`, proposal, { goal })
  set({ dialog: null, view: { kind: 'library' } })
  begin(local, (p) => p.source === 'goal' && p.goal === goal, { goal, proposal }, start)
}

/**
 * Open a plan's page from anywhere in the home window (Home's Plans, Progress's Plans, the sidebar): the Library page,
 * on the plan. A preset opens on its catalog page (the one Browse plans opens), any other plan on its own.
 */
export function openPlan(id: string): void {
  const m = myPlan(id)
  setPage('lessons')
  showPlan(m?.catalogId && planById(m.catalogId) ? m.catalogId : id)
}

/** Open Browse plans from anywhere in the home window (Home's and Progress's "Browse plans"). */
export function openBrowsePlans(): void {
  setPage('lessons')
  showPlans()
}

/** Remove a plan (the lessons it started stay in the library). */
export function removePlan(id: string): void {
  set((s) => ({ mine: s.mine.filter((m) => m.id !== id), view: s.view.kind !== 'library' && 'id' in s.view && s.view.id === id ? { kind: 'library' } : s.view }))
  bridge.send(cmd('plan.remove', { id }))
}

// ---- the sidebar's Plans ----------------------------------------------------------------------------------------

/**
 * The app sidebar lists the learner's plans ("Neural networks… 3 of 8", Adrian's v4 mock); a row opens that plan's
 * page on Library. Fed from `mine`, so it follows every `plans` answer and push (and the local fallback).
 */
function feedSidebar(mine: MyPlan[]): void {
  setSidebarFeed({
    plans: mine.length
      ? mine.map((p) => ({
          id: p.id,
          title: p.title,
          done: p.done,
          total: p.total,
          onOpen: () => openPlan(p.id)
        }))
      : null
  })
}
feedSidebar(get().mine)
usePlans.subscribe((s, prev) => {
  if (s.mine !== prev.mine) feedSidebar(s.mine)
})
