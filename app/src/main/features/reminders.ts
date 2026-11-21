/**
 * Main-process side of reminders (renderer: src/renderer/src/features/reminders/, pure rules in its logic.ts).
 *
 * Gentle, opt-in reminders that bring the learner back without nagging:
 *   - Off by default. The renderer offers it once, after the first finished lesson; Settings turns it on or off.
 *   - At most one notification a day, at the learner's time (default 6:00 PM local), only when something is due: a
 *     review item whose time has come, or reps left for today's goal (when the engine counts activity). Nothing due =
 *     nothing sent. Never in quiet hours, never while snoozed or while the dashboard's rest is on. Mid-lesson it waits
 *     for the lesson to end (a lesson counts as running only while its events keep coming; see logic.ts lessonSignal).
 *   - The text is calm and specific ("2 skills ready for a quick review: pandas groupby, numpy arrays"). A click opens
 *     the home window on Home.
 *   - Turning it on sends one confirmation right away, so the learner sees what a reminder looks like and macOS asks
 *     for permission in context, not at 6 PM out of nowhere. That one is the day's notification: the first look is
 *     tomorrow.
 *
 * Development builds (not packaged) never post a real notification: the same note goes to the overlay as an in-app
 * toast (feat:reminders:toast). MIYAGI_REAL_NOTIFICATIONS=1 opts a dev run in.
 *
 * Handles (bridge.invoke from any window):
 *   reminders:get             → ReminderState
 *   reminders:set (patch)     → ReminderState (editable keys only; saved to userData/reminders.json; broadcast as feat:reminders)
 *   reminders:snooze (kind)   'day' (not today) | 'week' | 'clear' → ReminderState
 * Nothing here talks to the network or opens a URL; the only file is userData/reminders.json.
 */
import { Notification, powerMonitor } from 'electron'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { cmd } from '../../common/wire'
import { defineMainFeature } from '../context'
import {
  DEFAULT_SETTINGS,
  compose,
  decide,
  dueFrom,
  lessonClock,
  lessonRunning,
  midnightAfter,
  sanitize,
  sanitizePatch,
  turnOn,
  turnsOn,
  welcome,
  type ReminderNote,
  type ReminderSettings,
  type ReminderState
} from '../../renderer/src/features/reminders/logic'
import { dayKey } from '../../renderer/src/features/dashboard/model'

const TICK_MS = 30_000
/** The engine answers progress.get within this, or the last answer it sent is used (when fresh enough). */
const ANSWER_MS = 8_000
/** An older cached answer is not trusted to say what is due now. */
const CACHE_MS = 6 * 3_600_000
/** Between two tries when the engine can't answer (inside the day's grace window). */
const RETRY_MS = 5 * 60_000

export default defineMainFeature({
  id: 'reminders',
  setup(ctx) {
    const file = join(ctx.app.getPath('userData'), 'reminders.json')
    let s: ReminderSettings = { ...DEFAULT_SETTINGS }
    try {
      s = { ...DEFAULT_SETTINGS, ...sanitize(JSON.parse(readFileSync(file, 'utf8')), true) }
    } catch {
      /* first run or unreadable: defaults (off) */
    }
    const preview = !ctx.app.isPackaged && process.env.MIYAGI_REAL_NOTIFICATIONS !== '1'

    const state = (): ReminderState => ({ ...s, supported: preview || Notification.isSupported(), preview })
    const save = (): void => {
      try {
        writeFileSync(file, JSON.stringify(s, null, 2))
      } catch (err) {
        console.warn('[reminders] could not save', err instanceof Error ? err.message : '')
      }
      ctx.broadcast('reminders', state())
    }

    // ---- what the engine says ---------------------------------------------------------------------------------------
    let last: { raw: unknown; at: number } | undefined
    let answer: ((raw: unknown) => void) | undefined
    /** When the last lesson event arrived (0 = no lesson running). */
    let lessonAt = 0
    const lessonActive = (): boolean => lessonRunning(lessonAt, Date.now())
    ctx.engine.onEvent((e) => {
      if (e.type === 'progress') {
        last = { raw: e.payload, at: Date.now() }
        answer?.(e.payload)
      } else lessonAt = lessonClock(lessonAt, e.type, e.payload, Date.now())
    })
    ctx.engine.onStatus((connected) => {
      if (!connected) lessonAt = 0
    })

    async function freshProgress(): Promise<unknown> {
      if (ctx.engine.connected && ctx.engine.can('progress.get')) {
        const raw = await new Promise<unknown>((resolve) => {
          const timer = setTimeout(() => resolve(undefined), ANSWER_MS)
          answer = (p) => {
            clearTimeout(timer)
            resolve(p)
          }
          ctx.engine.send(cmd('progress.get', {}))
        })
        answer = undefined
        if (raw) return raw
      }
      return last && Date.now() - last.at < CACHE_MS ? last.raw : undefined
    }

    // ---- the notification -------------------------------------------------------------------------------------------
    /** Kept until clicked or replaced: a garbage-collected Notification loses its click handler. */
    let shown: Notification | undefined

    const openHome = (): void => {
      const win = ctx.openWindow('library', { page: 'home', from: 'reminder' })
      if (!win || ctx.platform.os !== 'mac') return
      const steal = (): void => {
        if (!win.isDestroyed()) ctx.app.focus({ steal: true })
      }
      if (win.isVisible()) steal()
      else win.once('show', steal)
    }

    function post(note: ReminderNote): void {
      if (preview) {
        ctx.broadcast('reminders:toast', note)
        return
      }
      if (!Notification.isSupported()) return
      try {
        shown?.close()
        const n = new Notification({ title: note.title, body: note.body, silent: false })
        n.on('click', () => {
          openHome()
          shown = undefined
        })
        n.on('close', () => {
          if (shown === n) shown = undefined
        })
        n.show()
        shown = n
      } catch (err) {
        console.warn('[reminders] notification failed', err instanceof Error ? err.message : '')
      }
    }

    // ---- the daily look ---------------------------------------------------------------------------------------------
    let looking = false
    let lastTry = 0

    async function tick(): Promise<void> {
      if (looking) return
      const now = Date.now()
      const d = decide(s, now, lessonActive())
      if (d === 'off' || d === 'wait') return
      if (d === 'skip') {
        s = { ...s, lastDay: dayKey(now) }
        return save()
      }
      if (now - lastTry < RETRY_MS) return
      looking = true
      lastTry = now
      try {
        const raw = await freshProgress()
        // The engine can't say what is due: try again later inside the grace window, never guess.
        if (raw === undefined) return
        // Re-check: settings or a lesson may have changed while the engine answered.
        if (decide(s, Date.now(), lessonActive()) !== 'look') return
        const note = compose(dueFrom(raw, Date.now(), s.dailyGoal))
        s = { ...s, lastDay: dayKey(now), ...(note ? { lastSentAt: Date.now() } : {}) }
        save()
        if (note) post(note)
      } finally {
        looking = false
      }
    }

    const timer = setInterval(() => void tick(), TICK_MS)
    ctx.app.on('before-quit', () => clearInterval(timer))
    // A Mac asleep at the reminder's time looks as soon as it wakes (still inside the grace window).
    try {
      powerMonitor.on('resume', () => setTimeout(() => void tick(), 5_000))
    } catch {
      /* no power monitor here: the interval still covers it */
    }

    // ---- windows ------------------------------------------------------------------------------------------------------
    ctx.handle('reminders:get', () => state())
    ctx.handle('reminders:set', (patch) => {
      const p = sanitizePatch(patch)
      const turnedOn = turnsOn(s, p)
      s = turnedOn ? turnOn(s, p, Date.now()) : { ...s, ...p }
      save()
      if (turnedOn) post(welcome(s))
      return state()
    })
    ctx.handle('reminders:snooze', (kind) => {
      const now = Date.now()
      if (kind === 'day') s = { ...s, snoozeUntil: midnightAfter(now, 1) }
      else if (kind === 'week') s = { ...s, snoozeUntil: midnightAfter(now, 7) }
      else if (kind === 'clear') s = { ...s, snoozeUntil: null }
      else return state()
      save()
      return state()
    })
  }
})
