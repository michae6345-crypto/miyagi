/**
 * Feature: errors (main side, BUILD-PLAN A7). Local only: nothing here touches the network.
 *
 *   bridge.invoke('diagnostics:copy', text)        Copy details: scrubbed again here, capped, then the clipboard
 *   bridge.invoke('errors:info')                   { version, system } for Copy details
 *   bridge.invoke('errors:context', {lesson,step,total})  the lesson and step, kept in this launch's marker
 *   bridge.invoke('errors:crash-pending')          { report } when the last launch ended without a clean quit and
 *                                                  crashReports is 'ask'; null otherwise
 *   bridge.invoke('errors:crash-decide', {save})   save: the report goes to userData/crash-reports/ (this Mac only)
 *   bridge.invoke('errors:renderer', {message, stack})  a window's uncaught error / unhandled rejection, into the log
 *
 * How a crash is noticed: a marker file (userData/errors/session.json) is written at launch and removed on a clean
 * quit. Found at the next launch = the app did not quit cleanly. The report is built from allowlisted fields only
 * (app and OS version, the error log this app wrote, lesson name and step), every line scrubbed (scrub.ts): no code,
 * no files, no screenshots, no keys. crashReports 'never' drops it, 'always' saves it without asking, 'ask' (the
 * default) waits for the learner in Err-CrashConsent; it stays pending (next launch asks again) until they answer.
 * The error log: renderer and child processes that went away and main's uncaught exceptions (observed with
 * uncaughtExceptionMonitor, so Electron's own handling is unchanged).
 */
import { app, clipboard } from 'electron'
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs'
import { arch, release } from 'node:os'
import { join } from 'node:path'
import { sanitizePrefs } from '../../common/prefs'
import { MAX_TEXT, scrub } from '../../renderer/src/features/errors/scrub'
import { defineMainFeature } from '../context'

type Context = { lesson?: string; step?: number; total?: number }
type Marker = { startedAt: string; version: string; pid?: number; context: Context }
type LogLine = { at: string; text: string }

const MAX_LOG = 30
/** Renderer errors logged per launch at most. */
const RENDERER_MAX = 20

function readJson<T>(file: string): T | undefined {
  try {
    return JSON.parse(readFileSync(file, 'utf8')) as T
  } catch {
    return undefined
  }
}
function write(file: string, data: string): void {
  try {
    writeFileSync(file, data, { mode: 0o600 })
  } catch (err) {
    console.warn('[errors] could not write', err instanceof Error ? err.message : 'failed')
  }
}
function remove(file: string): void {
  try {
    if (existsSync(file)) unlinkSync(file)
  } catch {
    /* gone already */
  }
}

/** The process that wrote a marker is still running (a live instance, not a crash). EPERM still means it exists. */
function alive(pid: unknown): boolean {
  if (typeof pid !== 'number' || !Number.isInteger(pid) || pid <= 0 || pid === process.pid) return false
  try {
    process.kill(pid, 0)
    return true
  } catch (err) {
    return (err as NodeJS.ErrnoException | undefined)?.code === 'EPERM'
  }
}

function systemLabel(): string {
  if (process.platform === 'darwin') return `macOS ${process.getSystemVersion()} (${arch()})`
  if (process.platform === 'win32') return `Windows ${release()} (${arch()})`
  return `${process.platform} ${release()} (${arch()})`
}

/** Only these fields, each checked: a short title, two small whole numbers. */
function sanitizeContext(raw: unknown): Context {
  if (!raw || typeof raw !== 'object') return {}
  const r = raw as Record<string, unknown>
  const n = (v: unknown): number | undefined => (typeof v === 'number' && Number.isInteger(v) && v > 0 && v < 10000 ? v : undefined)
  const lesson = typeof r.lesson === 'string' && r.lesson.trim() ? scrub(r.lesson.replace(/\s+/g, ' ').trim(), 120) : undefined
  return { lesson, step: n(r.step), total: n(r.total) }
}

function buildReport(prev: Marker, log: LogLine[]): string {
  const c = prev.context ?? {}
  const lines = ['miyagi crash report', `App: ${scrub(String(prev.version ?? ''), 40)}`, `System: ${systemLabel()}`, `Last started: ${scrub(String(prev.startedAt ?? ''), 40)}`]
  if (c.lesson) lines.push(`Lesson: ${c.lesson}${c.step ? `, step ${c.step}${c.total ? ` of ${c.total}` : ''}` : ''}`)
  const since = Date.parse(prev.startedAt ?? '') || 0
  const recent = log.filter((l) => (Date.parse(l.at) || 0) >= since).slice(-12)
  lines.push('Error log:')
  if (recent.length) for (const l of recent) lines.push(`  ${l.at.slice(11, 19)} ${l.text}`)
  else lines.push('  (nothing was logged before it closed)')
  lines.push('Not included: your code or files, screenshots, API keys.')
  return scrub(lines.join('\n'))
}

export default defineMainFeature({
  id: 'errors',
  setup(ctx) {
    const dir = join(app.getPath('userData'), 'errors')
    const reportsDir = join(app.getPath('userData'), 'crash-reports')
    try {
      mkdirSync(dir, { recursive: true, mode: 0o700 })
    } catch {
      /* write() warns later */
    }
    const markerFile = join(dir, 'session.json')
    const logFile = join(dir, 'errors.json')
    const pendingFile = join(dir, 'pending-report.txt')

    // ---- the error log (scrubbed as it's written) ----
    let log: LogLine[] = (readJson<LogLine[]>(logFile) ?? []).filter((l) => l && typeof l.at === 'string' && typeof l.text === 'string').slice(-MAX_LOG)
    const record = (text: string): void => {
      log = [...log, { at: new Date().toISOString(), text: scrub(text.replace(/\s+/g, ' '), 300) }].slice(-MAX_LOG)
      write(logFile, JSON.stringify(log))
    }
    app.on('render-process-gone', (_e, _wc, d) => record(`window gone: ${d.reason} (exit ${d.exitCode})`))
    app.on('child-process-gone', (_e, d) => record(`${d.type} process gone: ${d.reason} (exit ${d.exitCode})${d.name ? ` ${d.name}` : ''}`))
    process.on('uncaughtExceptionMonitor', (err) => {
      const first = err instanceof Error ? `${err.name}: ${err.message} ${(err.stack ?? '').split('\n').slice(1, 4).join(' ')}` : String(err)
      record(`main error: ${first}`)
    })

    // ---- last launch: a marker still there = it did not quit cleanly ----
    // Unless its process still runs: this is a second instance (Windows packaged exits in windows.ts right after this
    // setup, or a second copy opened from the dmg). It must not call the live one a crash, nor take over its marker.
    // A marker alone is not a crash: Force Quit, SIGKILL, power loss and `npm run dev` restarts leave one too. Only a
    // packaged app with something logged since that launch started (a window or child process went away, or main threw)
    // gets a report; any other stale marker is dropped silently (the marker below overwrites it).
    const prev = readJson<Marker>(markerFile)
    const second = !!prev && typeof prev === 'object' && alive(prev.pid)
    if (prev && typeof prev === 'object' && !second && app.isPackaged) {
      const since = Date.parse(String(prev.startedAt ?? ''))
      if (Number.isFinite(since) && log.some((l) => Date.parse(l.at) >= since)) write(pendingFile, buildReport(prev, log))
    }

    const prefs = sanitizePrefs(readJson<unknown>(join(app.getPath('userData'), 'prefs.json')))
    const choice = (): 'ask' | 'always' | 'never' => {
      const now = sanitizePrefs(readJson<unknown>(join(app.getPath('userData'), 'prefs.json')))
      return now.crashReports ?? prefs.crashReports ?? 'ask'
    }
    const pending = (): string | undefined => {
      try {
        return existsSync(pendingFile) ? readFileSync(pendingFile, 'utf8') : undefined
      } catch {
        return undefined
      }
    }
    const save = (report: string): boolean => {
      try {
        mkdirSync(reportsDir, { recursive: true, mode: 0o700 })
        writeFileSync(join(reportsDir, `crash-${new Date().toISOString().replace(/[:.]/g, '-')}.txt`), scrub(report), { mode: 0o600 })
        return true
      } catch (err) {
        console.warn('[errors] could not save the crash report', err instanceof Error ? err.message : 'failed')
        return false
      }
    }
    // Settled without asking: 'never' drops it, 'always' keeps it.
    const settled = choice()
    if (settled !== 'ask' && pending()) {
      if (settled === 'always') save(pending()!)
      remove(pendingFile)
    }

    // ---- this launch ----
    let marker: Marker = { startedAt: new Date().toISOString(), version: app.getVersion(), pid: process.pid, context: {} }
    if (!second) {
      write(markerFile, JSON.stringify(marker))
      app.on('will-quit', () => remove(markerFile))
    }

    // A window's uncaught errors (features/errors/report.ts): into the same log, at most RENDERER_MAX per launch so a
    // render loop cannot flood it. features/telemetry.ts sends new log lines when the learner allows it.
    let fromRenderer = 0
    ctx.handle('errors:renderer', (raw) => {
      if (!raw || typeof raw !== 'object' || fromRenderer >= RENDERER_MAX) return false
      const r = raw as { message?: unknown; stack?: unknown }
      const message = typeof r.message === 'string' ? r.message.slice(0, 300) : ''
      if (!message) return false
      const frames = typeof r.stack === 'string' ? r.stack.split('\n').slice(1, 3).join(' ').slice(0, 300) : ''
      fromRenderer++
      record(`renderer error: ${message} ${frames}`.trim())
      return true
    })
    ctx.handle('errors:info', () => ({ version: app.getVersion(), system: systemLabel() }))
    ctx.handle('errors:context', (raw) => {
      const context = sanitizeContext(raw)
      if (JSON.stringify(context) === JSON.stringify(marker.context)) return true
      marker = { ...marker, context }
      if (!second) write(markerFile, JSON.stringify(marker))
      return true
    })
    ctx.handle('diagnostics:copy', (text) => {
      if (typeof text !== 'string' || !text.trim()) return false
      clipboard.writeText(scrub(text, MAX_TEXT))
      return true
    })
    ctx.handle('errors:crash-pending', () => {
      // A second instance leaves the question to the live one.
      const report = second ? undefined : pending()
      return report && choice() === 'ask' ? { report: scrub(report) } : null
    })
    ctx.handle('errors:crash-decide', (raw) => {
      const report = pending()
      const want = !!raw && typeof raw === 'object' && (raw as { save?: unknown }).save === true
      const saved = !!report && want ? save(report) : false
      remove(pendingFile)
      return { saved }
    })
  }
})
