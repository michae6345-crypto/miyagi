/**
 * Feature: onboarding (A3). State for the setup window and the mid-lesson recovery card.
 *
 * Inputs, never prompting (BUILD-PLAN Section 6: polling never prompts):
 *   - permissions   main/permissions.ts: permissions:get once, then feat:permissions while this window watches
 *                   (permissions:watch only while the onboarding window is focused or a recovery card is open)
 *   - health        the engine's health (health.get, only when engine.hello lists it): VS Code and the companion
 *   - engine        core/lesson: connected, localEngine (main/localEngine.ts), keyStatus.cloud (config.status)
 *   - cloud         main/features/cloud.ts: cloud:get / feat:cloud (the install token's phase, never the token)
 * Prompts happen only in a click handler (onboarding:prompt in main/features/onboarding.ts). System Settings opens only
 * through core's permissions:open(kind), never a URL from here.
 *
 * The recovery card (Onb-Permission-Recovery) opens on lesson.paused {reason: "permission"}, or when a permission this
 * window already watches goes from granted to denied during a lesson. It closes on lesson.resumed, when the grant is
 * back, on "Keep going without pointing" (Accessibility only), and when the lesson ends.
 */
import { create } from 'zustand'
import type { HealthItem, LibraryItem, PermissionKind } from '../../../../../../shared/contracts/events'
import { cmd, type Payload } from '../../../../common/wire'
import { bridge, isElectron } from '../../bridge'
import { emitUi, onMessage, onUi } from '../../core/bus'
import { canSend, notify, useLesson } from '../../core/lesson'
import { closeWindow } from '../../core/surfaces'
import { setPrefs } from '../../core/prefs'
import { sendAction } from '../../core/shortcuts'

export type PermissionState = 'granted' | 'denied' | 'not-determined' | 'unknown'
export type Permissions = Record<PermissionKind, PermissionState> & { external: boolean; at: number }
/** main/features/cloud.ts CloudView: what a renderer may see (never the token). */
export type CloudView = { state: 'off' | 'minting' | 'ok' | 'failed'; configured: boolean; secure: boolean; hasToken: boolean }
/** The window's two first views: the two-pane first run (Onb-Setup-Full) or the compact checklist (Onb-Checklist-Mixed). */
export type OnbView = 'welcome' | 'checklist'
/** What a row's button does. The component maps each to a handler below. */
export type RowAction = 'allow-screen' | 'open-accessibility' | 'relaunch' | 'install-companion' | 'get-vscode' | 'retry-engine' | 'retry-cloud'
export type Asked = Partial<Record<'screen' | 'accessibility' | 'companion', number>>
export type RecoveryKind = Extract<PermissionKind, 'screen' | 'accessibility'>
export type Recovery = { kind: RecoveryKind; why: 'paused' | 'dropped'; title?: string; body?: string; at: number }

type State = {
  perms?: Permissions
  health?: Payload<'health'>
  cloud?: CloudView
  /** When the learner clicked a row's button: that row shows Watching while miyagi waits for it. */
  asked: Asked
  /** The companion install is running (main's execFile, or the engine's install action). */
  installing: boolean
  /** onboarding.json done flag (main/features/onboarding.ts). */
  done: boolean
  /** A cached lesson the engine offers for the first run (library answer). Only then does Ready show a lesson card. */
  suggestion?: LibraryItem
  recovery?: Recovery
  /** Permissions the learner chose to go on without, for this lesson ("Keep going without pointing"). */
  skipped: RecoveryKind[]
}

export const useOnboarding = create<State>(() => ({ asked: {}, installing: false, done: false, skipped: [] }))
const set = useOnboarding.setState
const get = useOnboarding.getState

/** Which window this module runs in (Electron loads index.html#/<route>; the stage is one page). */
function route(): string {
  if (!isElectron) return 'stage'
  return location.hash.replace(/^#\/?/, '') || 'overlay'
}
/** The recovery card lives in the overlay (the island); in the stage everything is one page. */
const hostsRecovery = (): boolean => route() === 'overlay' || route() === 'stage'

// ---- reads ---------------------------------------------------------------------------------------------------------

function applyPerms(p: unknown): void {
  if (!p || typeof p !== 'object') return
  const next = p as Permissions
  const prev = get().perms
  set({ perms: next })
  // A grant came back: the row stops watching, and an open recovery card for it closes.
  const rec = get().recovery
  if (rec && next[rec.kind] === 'granted') closeRecovery(true)
  // A grant went away during a lesson (only seen while someone watches: main polls only then).
  if (!hostsRecovery() || !prev) return
  const s = useLesson.getState()
  if (!s.lesson || !s.stepId) return
  for (const k of ['screen', 'accessibility'] as const) {
    if (prev[k] === 'granted' && next[k] === 'denied' && !get().skipped.includes(k)) openRecovery({ kind: k, why: 'dropped', at: Date.now() })
  }
}

export function refreshPerms(): Promise<void> {
  return bridge
    .invoke<Permissions | undefined>('permissions:get')
    .then(applyPerms)
    .catch(() => undefined)
}

/** health.get, when this engine understands it. Never prompts (engine side). */
export function requestHealth(): void {
  if (canSend('health.get')) bridge.send(cmd('health.get', {}))
}

export function refreshCloud(): void {
  bridge
    .invoke<CloudView>('cloud:get')
    .then((c) => c && set({ cloud: c }))
    .catch(() => undefined)
}

// Watching: main polls permissions only while at least one window asked for it. The stage has no poller of its own,
// so it reads permissions:get itself while watching.
const watchers = new Set<string>()
let stagePoll: ReturnType<typeof setInterval> | undefined
export function watchPerms(who: string, on: boolean): void {
  const before = watchers.size > 0
  if (on) watchers.add(who)
  else watchers.delete(who)
  const now = watchers.size > 0
  if (before === now) return
  bridge.invoke('permissions:watch', now).catch(() => undefined)
  if (!isElectron) {
    clearInterval(stagePoll)
    stagePoll = now ? setInterval(() => void refreshPerms(), 1000) : undefined
  }
  if (now) void refreshPerms()
}

bridge.onFeature('permissions', applyPerms)
bridge.onFeature('cloud', (c) => c && typeof c === 'object' && set({ cloud: c as CloudView }))
bridge.onFeature('onboarding:companion', (p) => {
  const st = (p as { state?: string } | undefined)?.state
  if (st === 'installing') set({ installing: true })
  else if (st === 'done' || st === 'failed') {
    set({ installing: false })
    requestHealth()
  }
})
onMessage('health', (p) => {
  set({ health: { items: Array.isArray(p.items) ? p.items : [], ready: p.ready, total: p.total } })
  const companion = p.items?.find((i) => i.id === 'companion')
  if (companion && companion.state !== 'checking') set({ installing: false })
})
// A new engine: ask again (its health answer is what the rows show). The stage's window asks from its own effect.
onMessage('engine.hello', () => {
  if (route() === 'onboarding' || get().recovery) requestHealth()
})
onMessage('library', (p) => {
  if (!wantSuggestion) return
  const items = Array.isArray(p.items) ? p.items : []
  // The engine's pick: an item it flags as suggested, else the first cached lesson ready to start and not begun.
  const flagged = items.find((i) => (i as LibraryItem & { suggested?: boolean }).suggested === true && i.ready)
  const pick = flagged ?? items.find((i) => i.ready && !i.progress)
  set({ suggestion: pick })
})

let wantSuggestion = false
/** Ready asks the engine once for a first lesson (library.list). Without the capability there is no lesson card. */
export function requestSuggestion(): void {
  if (wantSuggestion || !canSend('library.list')) return
  wantSuggestion = true
  bridge.send(cmd('library.list', {}))
}

bridge
  .invoke<{ done?: boolean }>('onboarding:get')
  .then((r) => r && set({ done: r.done === true }))
  .catch(() => undefined)
refreshCloud()

// ---- the row buttons (every prompt or System Settings pane opens only here, on a click) ----------------------------

const noteAsked = (k: keyof Asked): void => set((s) => ({ asked: { ...s.asked, [k]: Date.now() } }))

/** Stage fixtures use this to start a row as already asked (the mockup's Watching row). */
export function markAsked(k: keyof Asked): void {
  noteAsked(k)
}

async function openPane(kind: PermissionKind): Promise<void> {
  // Tell the engine the learner is on it (it holds checks); the app opens the pane itself.
  if (canSend('permission.open')) bridge.send(cmd('permission.open', { kind }))
  await bridge.invoke<boolean>('permissions:open', kind).catch(() => false)
}

/** The companion: main installs the bundled extension with VS Code's own CLI; without one, the engine's own fix. */
async function installCompanion(item?: HealthItem): Promise<void> {
  noteAsked('companion')
  set({ installing: true })
  const r = await bridge.invoke<{ ok: boolean; reason?: string }>('onboarding:install-companion').catch(() => ({ ok: false, reason: 'unavailable' }))
  if (r?.ok) {
    set({ installing: false })
    requestHealth()
    return
  }
  // Nothing bundled here (dev, the stage): the engine's health row says how to fix it (fix: an action kind).
  if (item?.fix === 'install') {
    sendAction('install', item.id)
    return
  }
  set({ installing: false })
  notify("Couldn't install the companion here.", 'info', { id: 'onb-companion' })
}

export async function runAction(a: RowAction, item?: HealthItem): Promise<void> {
  switch (a) {
    case 'allow-screen':
      noteAsked('screen')
      // A capture makes macOS ask (main, on this click only); then the pane, where the switch is.
      await bridge.invoke('onboarding:prompt', 'screen').catch(() => false)
      await openPane('screen')
      return
    case 'open-accessibility':
      noteAsked('accessibility')
      await bridge.invoke('onboarding:prompt', 'accessibility').catch(() => false)
      await openPane('accessibility')
      return
    case 'relaunch':
      await bridge.invoke('onboarding:relaunch').catch(() => false)
      return
    case 'install-companion':
      return installCompanion(item)
    case 'get-vscode':
      noteAsked('companion')
      await bridge.invoke('open:external', 'https://code.visualstudio.com/download').catch(() => false)
      return
    case 'retry-engine':
      await bridge.invoke('engine-local:restart').catch(() => undefined)
      return
    case 'retry-cloud':
      await bridge
        .invoke<CloudView>('cloud:retry')
        .then((c) => c && set({ cloud: c }))
        .catch(() => undefined)
      return
  }
}

// ---- finishing -----------------------------------------------------------------------------------------------------

/** Setup is done once on this Mac: onboarding.json in userData (main), and the shared pref. */
export function markDone(): void {
  if (get().done) return
  set({ done: true })
  bridge.invoke('onboarding:done').catch(() => undefined)
  setPrefs({ onboarded: true })
}

/** Start learning: the engine's suggested lesson (zero model calls), else the launcher. Then the window closes. */
export function startLearning(): void {
  markDone()
  const pick = get().suggestion
  if (pick && canSend('library.start')) bridge.send(cmd('library.start', { id: pick.id }))
  else bridge.emit('launcher:toggle')
  void closeWindow('onboarding')
}

// ---- the recovery card ---------------------------------------------------------------------------------------------

function openRecovery(r: Recovery): void {
  if (!hostsRecovery()) return
  const had = !!get().recovery
  set({ recovery: r })
  if (had) return
  watchPerms('recovery', true)
  requestHealth()
  emitUi('surface', { id: 'recovery', open: true })
}

export function closeRecovery(back = false): void {
  const r = get().recovery
  if (!r) return
  set({ recovery: undefined })
  watchPerms('recovery', false)
  emitUi('surface', { id: 'recovery', open: false })
  if (back) notify(r.kind === 'screen' ? 'Screen Recording is back on.' : 'Accessibility is back on.', 'info', { id: 'onb-recovery' })
}

/** "Keep going without pointing": the lesson goes on; miyagi won't point at buttons until it is back. */
export function keepGoing(): void {
  const r = get().recovery
  if (!r || r.kind !== 'accessibility') return
  set((s) => ({ skipped: [...s.skipped.filter((k) => k !== r.kind), r.kind] }))
  closeRecovery()
}

/** Which grant a pause is about: the one that's off now (Screen Recording first: without it nothing works). */
function pausedKind(p?: Permissions): RecoveryKind {
  if (p?.screen === 'denied') return 'screen'
  return 'accessibility'
}

onMessage('lesson.paused', (p) => {
  if (p.reason !== 'permission' || !hostsRecovery()) return
  void refreshPerms().then(() => {
    const kind = pausedKind(get().perms)
    if (get().perms?.[kind] === 'granted') return
    openRecovery({ kind, why: 'paused', title: p.title, body: p.body, at: Date.now() })
  })
})
onMessage('lesson.resumed', () => {
  const r = get().recovery
  if (r) closeRecovery(r.why === 'paused')
})
onMessage('lesson.ended', () => {
  closeRecovery()
  set({ skipped: [] })
})
onUi('reset', () => {
  closeRecovery()
  set({ skipped: [] })
})
// Esc on the recovery card: the same as "Keep going without pointing" (Accessibility only; Screen Recording stays).
onUi('dismiss', () => {
  if (get().recovery?.kind === 'accessibility') keepGoing()
})
