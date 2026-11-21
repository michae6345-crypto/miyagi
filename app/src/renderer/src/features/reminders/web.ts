/**
 * Feature: reminders. Browser-stage stand-ins for main/features/reminders.ts. The stage never posts a real
 * notification: it runs the same rules (logic.ts) on the inline mock's `progress` and shows the in-app toast.
 * Settings are kept in localStorage (not secret).
 *
 * Stage params:
 *   ?scenario=reminders                    finish a short lesson, Esc the completion card: the offer grows from the island
 *   &reminders=offer                       the offer at once (answered state reset)
 *   &reminders=toast                       reminders on, and the reminder fires now from the mock's review queue
 *   &reminders=settings                    the Settings group (what the settings lane mounts in General)
 *   &hold                                  keep the toast up (screenshots)
 */
import { cmd } from '../../../../common/wire'
import { bridge, engineMode, isElectron, registerWebHandler } from '../../bridge'
import { onMessage } from '../../core/bus'
import { stageRebase } from '../dashboard/stage'
import { DEFAULT_SETTINGS, compose, decide, dueFrom, midnightAfter, minuteOf, sanitize, sanitizePatch, welcome, type ReminderSettings, type ReminderState } from './logic'
import { dayKey } from '../dashboard/model'
import { drawsIsland, showToast, useReminders } from './store'

const KEY = 'miyagi.reminders'
const params = typeof location === 'undefined' ? new URLSearchParams() : new URLSearchParams(location.search)
export const STAGE_VIEW = isElectron ? '' : (params.get('reminders') ?? '')

if (!isElectron) {
  const read = (): ReminderSettings => {
    try {
      return { ...DEFAULT_SETTINGS, ...sanitize(JSON.parse(localStorage.getItem(KEY) ?? '{}'), true) }
    } catch {
      return { ...DEFAULT_SETTINGS }
    }
  }
  let s = read()
  const state = (): ReminderState => ({ ...s, supported: true, preview: true })
  const save = (): void => {
    try {
      localStorage.setItem(KEY, JSON.stringify(s))
    } catch {
      /* private window: this session only */
    }
  }

  // Stage views start from a known state, whatever an earlier visit left.
  if (STAGE_VIEW === 'offer') s = { ...DEFAULT_SETTINGS, completedOnce: true }
  if (STAGE_VIEW === 'toast' || STAGE_VIEW === 'settings') s = { ...s, enabled: true, offered: true, snoozeUntil: null, lastDay: null }
  if (STAGE_VIEW) save()

  registerWebHandler('reminders:get', () => state())
  registerWebHandler('reminders:set', (patch) => {
    const p = sanitizePatch(patch)
    const turnedOn = p.enabled === true && !s.enabled
    // Turned on after today's time: the welcome note is today's one, the first look is tomorrow.
    s = { ...s, ...p, ...(turnedOn ? { snoozeUntil: null, ...(minuteOf(Date.now()) >= (p.time ?? s.time) ? { lastDay: dayKey(Date.now()) } : {}) } : {}) }
    save()
    if (turnedOn && drawsIsland()) showToast(welcome(s))
    return state()
  })
  registerWebHandler('reminders:snooze', (kind) => {
    const now = Date.now()
    if (kind === 'day') s = { ...s, snoozeUntil: midnightAfter(now, 1) }
    else if (kind === 'week') s = { ...s, snoozeUntil: midnightAfter(now, 7) }
    else if (kind === 'clear') s = { ...s, snoozeUntil: null }
    save()
    return state()
  })

  // The stage's scheduler: the same daily look as main, on the mock's last `progress`, shown as the toast.
  let last: unknown
  let lessonActive = false
  onMessage('progress', (p) => (last = stageRebase(p)))
  onMessage('lesson.building', () => (lessonActive = true))
  onMessage('lesson.ready', () => (lessonActive = true))
  onMessage('lesson.ended', () => (lessonActive = false))

  const fire = (now: number): void => {
    const note = compose(dueFrom(last, now, s.dailyGoal))
    s = { ...s, lastDay: dayKey(now), ...(note ? { lastSentAt: now } : {}) }
    save()
    useReminders.setState({ s: state() })
    if (note) showToast(note)
  }
  setInterval(() => {
    if (!drawsIsland() || last === undefined || engineMode() !== 'inline') return
    const now = Date.now()
    const d = decide(s, now, lessonActive)
    if (d === 'skip') {
      s = { ...s, lastDay: dayKey(now) }
      save()
    } else if (d === 'look') fire(now)
  }, 15_000)

  // ?reminders=toast: fire now (the time rule aside), once the mock's progress has arrived.
  if (STAGE_VIEW === 'toast') {
    let tries = 0
    const go = (): void => {
      // A scenario that doesn't push progress on connect (?scenario=full): ask, like main does at the time.
      if (tries === 4 && last === undefined) bridge.send(cmd('progress.get', {}))
      if (last !== undefined || tries++ > 20) fire(Date.now())
      else setTimeout(go, 250)
    }
    setTimeout(go, 1200)
  }
}
