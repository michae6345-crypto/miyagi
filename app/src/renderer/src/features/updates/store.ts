/**
 * Feature: updates. The view main keeps (src/main/features/updates.ts) plus what this card shows right now.
 *
 *   view        UpdateView from updates:get at load and every feat:updates broadcast (or an invoke's answer)
 *   steps       Download was pressed in this run: the card shows the install steps instead of the offer
 *   notesOpen   "What's new" is expanded
 *   visible     the card is on the island (Esc closes it: Later)
 *
 * Every action is an invoke whose answer is the new view, so the browser stage (web.ts) needs no broadcast.
 */
import { create } from 'zustand'
import { bridge } from '../../bridge'
import { onUi } from '../../core/bus'
import type { UpdateView } from './manifest'
// Stage stand-ins first: the updates:get below runs at load.
import './web'

type State = {
  view?: UpdateView
  steps: boolean
  notesOpen: boolean
  visible: boolean
  /** Download pressed but the browser did not open. */
  openFailed: boolean
  busy?: 'download' | 'later' | 'quit' | 'check'
}

export const useUpdates = create<State>(() => ({ view: undefined, steps: false, notesOpen: false, visible: false, openFailed: false, busy: undefined }))
const set = useUpdates.setState
const get = useUpdates.getState

function isView(v: unknown): v is UpdateView {
  return !!v && typeof v === 'object' && typeof (v as UpdateView).phase === 'string' && typeof (v as UpdateView).current === 'string'
}
const take = (v: unknown): void => {
  if (isView(v)) set({ view: v })
}

bridge
  .invoke<UpdateView>('updates:get')
  .then(take)
  .catch(() => undefined)
bridge.onFeature('updates', take)

/** The card wants the island: an offer not snoozed, or the steps the learner asked for. */
export function wantsCard(s: State, now = Date.now()): boolean {
  if (!s.view?.latest) return false
  return s.steps || !(s.view.snoozedUntil && s.view.snoozedUntil > now)
}

export async function download(): Promise<void> {
  if (get().busy) return
  set({ busy: 'download', openFailed: false })
  const v = await bridge.invoke<UpdateView>('updates:download').catch(() => undefined)
  take(v)
  const ok = isView(v) && !!v.opened
  set({ busy: undefined, steps: ok, openFailed: !ok })
}

/** Later (and Esc): the card goes for 24 h. The Settings row still offers the update. */
export async function later(): Promise<void> {
  if (get().busy === 'later') return
  set({ busy: 'later', steps: false, notesOpen: false, openFailed: false })
  take(await bridge.invoke<UpdateView>('updates:later').catch(() => undefined))
  set({ busy: undefined })
}

export async function quitToInstall(): Promise<void> {
  set({ busy: 'quit' })
  await bridge.invoke('updates:quit').catch(() => undefined)
}

/** For the Settings row (Core request): check now; resolves with the new view. */
export async function checkNow(): Promise<UpdateView | undefined> {
  set({ busy: 'check' })
  const v = await bridge.invoke<UpdateView>('updates:check').catch(() => undefined)
  take(v)
  set({ busy: undefined })
  return isView(v) ? v : undefined
}

export const toggleNotes = (): void => set({ notesOpen: !get().notesOpen })
export const setVisible = (on: boolean): void => set({ visible: on })

onUi('dismiss', () => {
  if (!get().visible) return
  void later()
  return true
})
