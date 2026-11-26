/**
 * Main-process feature: offer to move miyagi into Applications (Lane C, DEPLOY-READINESS Nov 25). No window, no IPC.
 *
 * A built Mac app opened from somewhere else (Downloads, a mounted DMG, the Desktop; macOS then runs it translocated
 * from a random read-only folder) asks once, calmly: "Move miyagi to Applications?" with Move and Not now. Move calls
 * Electron's app.moveToApplicationsFolder: it copies (from a DMG) or moves the app, replaces an older copy there, and
 * starts the moved app. Not now is remembered for this version (userData/location.json), so the question comes back
 * only with an update.
 *
 * index.ts awaits offerMoveToApplications() early in whenReady, BEFORE the engine starts: the move quits this copy, and
 * an engine started from the old path would outlive it with a command line the moved app can't prove is its own.
 * Never in `npm run dev`, never on Windows, never in a second copy (the first one holds the single-instance lock).
 */
import { app, dialog } from 'electron'
import { readFileSync, renameSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { defineMainFeature } from '../context'

export const LOCATION_FILE = 'location.json'

export const MOVE_COPY = {
  title: 'Move miyagi to Applications?',
  line: 'miyagi works best from your Applications folder.',
  move: 'Move',
  later: 'Not now'
} as const

export type Where = {
  platform: string
  packaged: boolean
  /** app.isInApplicationsFolder() */
  inApplications: boolean
  /** The version a learner said Not now to, if any. */
  declined?: string
  version: string
  /** MIYAGI_NO_MOVE=1: never ask (a test Mac, a recording). */
  off?: boolean
}

/** Ask? A built Mac app outside Applications, not already declined for this version. */
export function shouldOfferMove(w: Where): boolean {
  if (w.platform !== 'darwin' || !w.packaged || w.off) return false
  if (w.inApplications) return false
  return w.declined !== w.version
}

/** The version declined in location.json, or undefined (missing, unreadable, malformed). */
export function readDeclined(file: string): string | undefined {
  try {
    const raw = JSON.parse(readFileSync(file, 'utf8')) as { declined?: unknown }
    return typeof raw.declined === 'string' && raw.declined.length <= 64 ? raw.declined : undefined
  } catch {
    return undefined
  }
}

export function writeDeclined(file: string, version: string): void {
  try {
    const tmp = `${file}.tmp`
    writeFileSync(tmp, JSON.stringify({ declined: version }), { mode: 0o600 })
    renameSync(tmp, file)
  } catch {
    console.warn('[location] could not save the Not now') // never the path: it names the home folder
  }
}

/**
 * The launch-time question. Resolves false when nothing happened (not asked, Not now, or the move failed) and true
 * when the move started (this copy is about to quit: the caller starts nothing else).
 */
export async function offerMoveToApplications(): Promise<boolean> {
  if (process.platform !== 'darwin' || !app.isPackaged) return false
  try {
    const file = join(app.getPath('userData'), LOCATION_FILE)
    const ask = shouldOfferMove({
      platform: process.platform,
      packaged: app.isPackaged,
      inApplications: app.isInApplicationsFolder(),
      declined: readDeclined(file),
      version: app.getVersion(),
      off: process.env.MIYAGI_NO_MOVE === '1'
    })
    // A second copy hands over to the first (features/launch.ts): it never asks.
    if (!ask || !app.requestSingleInstanceLock()) return false
    const { response } = await dialog.showMessageBox({
      type: 'question',
      message: MOVE_COPY.title,
      detail: MOVE_COPY.line,
      buttons: [MOVE_COPY.move, MOVE_COPY.later],
      defaultId: 0,
      cancelId: 1,
      noLink: true
    })
    if (response !== 0) {
      writeDeclined(file, app.getVersion())
      return false
    }
    // Another copy in Applications: replace it when it isn't running; when it is, it comes forward and this one quits.
    return app.moveToApplicationsFolder({ conflictHandler: () => true })
  } catch {
    // The learner cancelled the admin prompt, or the copy failed: carry on from here.
    console.warn('[location] the move to Applications did not happen')
    return false
  }
}

export default defineMainFeature({
  id: 'location',
  setup() {
    // Nothing per window: index.ts calls offerMoveToApplications() before the engine starts.
  }
})
