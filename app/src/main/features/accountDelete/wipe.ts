/**
 * Delete account, the local part: every file and folder miyagi keeps on this Mac, found by reading the code (not
 * guessed). Pure apart from `fs`, so wipe.test.ts runs it with node --test in a temp folder.
 *
 * userData (~/Library/Application Support/miyagi), each with its write-then-rename `.tmp`:
 *   keys.bin            the learner's own API keys (features/settings.ts)
 *   auth.bin            the Supabase session (features/auth.ts)
 *   login.json          the old "made a choice at the login" flag (auth.ts no longer writes it; an old one may stay)
 *   cloud-link.json     the note of the account link (features/cloudLink.ts)
 *   install.bin         the miyagi-cloud install token (features/cloud.ts)
 *   onboarding.json     setup done, intro seen, the saved step (features/onboarding.ts)
 *   age.json            the age step's result (features/agegate.ts)
 *   prefs.json          preferences, consent stamp included (main/prefs.ts)
 *   reminders.json      review reminders (features/reminders.ts)
 *   updates.json        the update check's state (features/updates.ts)
 *   player-bounds.json  where the video player sat (features/player.ts)
 *   errors/             the local error log, the launch marker, a pending crash report (features/errors.ts)
 *   crash-reports/      saved crash reports (features/errors.ts)
 *   telemetry/          the usage sender's state (features/telemetry.ts)
 *   funnel/             activation milestone times (features/funnel.ts)
 * Electron's own storage (cookies, localStorage, IndexedDB, the HTTP cache) is cleared through the session API, not
 * here (accountDelete.ts): the YouTube player's iframe runs in the default session, so its cookies go with it.
 * logs (~/Library/Logs/miyagi): island.log, the push-to-talk log (main/index.ts, features/ptt.ts)
 * crashDumps: Electron's Crashpad folder
 * The engine (main/localEngine.ts layout; the engine reads the same env names):
 *   ~/miyagi/engine/src/demo/cache/{search,lessons,transcripts}   cached searches, built lessons, captions
 *   ~/miyagi/engine/src/demo/runs                                   recorded runs, backups made before "Do it for me"
 *   ~/miyagi/engine/logs                                            engine.log
 *   ~/miyagi/state (state-dev for npm run dev; MIYAGI_STATE_DIR)     saved lessons and progress (sessions/store.py)
 *   ~/.cache/sandhacks-tutor/tts (COACH_TTS_DIR)                     spoken lines (coach/voice.py)
 * Only when the learner ticks it: ~/miyagi/lessons (MIYAGI_LESSONS_DIR, MIYAGI_LESSONS), their own work.
 * Never: ~/miyagi/engine/src itself (the engine, put back by the app), VS Code and its extensions, userData/engine.json
 * (a machine setting: which engine to run, no personal data).
 *
 * Guard: a target is removed only when it is strictly inside one of the roots (userData, logs, crashDumps, ~/miyagi,
 * ~/.cache/sandhacks-tutor). An env override that points anywhere else (MIYAGI_LESSONS_DIR=/) is skipped.
 */
import { existsSync, readdirSync, rmSync } from 'node:fs'
import { isAbsolute, join, relative, resolve, sep } from 'node:path'

export const USER_DATA_FILES = [
  'keys.bin',
  'auth.bin',
  'login.json',
  'cloud-link.json',
  'install.bin',
  'onboarding.json',
  'age.json',
  'prefs.json',
  'reminders.json',
  'updates.json',
  'player-bounds.json'
] as const
export const USER_DATA_DIRS = ['errors', 'crash-reports', 'telemetry', 'funnel'] as const
/** Under the engine's source tree (localEngine.ts KEPT_DIRS and what the engine writes there). */
export const ENGINE_CACHE_DIRS = [
  ['demo', 'cache', 'search'],
  ['demo', 'cache', 'lessons'],
  ['demo', 'cache', 'transcripts'],
  ['demo', 'runs']
] as const

export type Target = { path: string; kind: 'file' | 'dir' | 'contents'; what: string }

export type Where = {
  userData: string
  logs: string
  crashDumps?: string
  home: string
  packaged: boolean
  env: Partial<Record<'MIYAGI_HOME' | 'MIYAGI_STATE_DIR' | 'COACH_TTS_DIR' | 'MIYAGI_LESSONS_DIR' | 'MIYAGI_LESSONS', string>>
  /** The learner ticked "Also delete my lesson folders in ~/miyagi". */
  lessons: boolean
}

const expand = (p: string, home: string): string => resolve(p.startsWith('~') ? join(home, p.slice(1)) : p)

/** The engine's home (localEngine.ts): MIYAGI_HOME, else ~/miyagi/engine. */
export const engineHome = (w: Pick<Where, 'env' | 'home'>): string => (w.env.MIYAGI_HOME?.trim() ? expand(w.env.MIYAGI_HOME.trim(), w.home) : join(w.home, 'miyagi', 'engine'))

/** Every target, in the order they are removed. */
export function eraseTargets(w: Where): Target[] {
  const t: Target[] = []
  for (const name of USER_DATA_FILES) {
    t.push({ path: join(w.userData, name), kind: 'file', what: name })
    t.push({ path: join(w.userData, `${name}.tmp`), kind: 'file', what: `${name}.tmp` })
  }
  for (const name of USER_DATA_DIRS) t.push({ path: join(w.userData, name), kind: 'dir', what: name })
  t.push({ path: w.logs, kind: 'contents', what: 'logs' })
  if (w.crashDumps) t.push({ path: w.crashDumps, kind: 'contents', what: 'crash dumps' })

  const engine = engineHome(w)
  for (const parts of ENGINE_CACHE_DIRS) t.push({ path: join(engine, 'src', ...parts), kind: 'dir', what: parts.join('/') })
  t.push({ path: join(engine, 'logs'), kind: 'dir', what: 'engine logs' })
  const state = w.env.MIYAGI_STATE_DIR?.trim() ? expand(w.env.MIYAGI_STATE_DIR.trim(), w.home) : join(w.home, 'miyagi', w.packaged ? 'state' : 'state-dev')
  t.push({ path: state, kind: 'dir', what: 'engine state' })
  const tts = w.env.COACH_TTS_DIR?.trim() ? expand(w.env.COACH_TTS_DIR.trim(), w.home) : join(w.home, '.cache', 'sandhacks-tutor', 'tts')
  t.push({ path: tts, kind: 'dir', what: 'spoken lines' })

  if (w.lessons) {
    const roots = new Set([join(w.home, 'miyagi', 'lessons')])
    for (const v of [w.env.MIYAGI_LESSONS_DIR, w.env.MIYAGI_LESSONS]) if (v?.trim()) roots.add(expand(v.trim(), w.home))
    for (const p of roots) t.push({ path: p, kind: 'dir', what: 'lesson folders' })
  }
  return t
}

/** The folders a target may sit in (never one of them itself). */
export function allowedRoots(w: Where): string[] {
  return [w.userData, w.logs, w.crashDumps, join(w.home, 'miyagi'), join(w.home, '.cache', 'sandhacks-tutor')].filter((r): r is string => !!r).map((r) => resolve(r))
}

/** Strictly inside a root: `root/x`, never `root`, never `root/../x`. */
export function insideRoots(path: string, roots: readonly string[]): boolean {
  if (!isAbsolute(path)) return false
  const p = resolve(path)
  return roots.some((r) => {
    const rel = relative(r, p)
    return !!rel && rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel)
  })
}

export type Fs = {
  existsSync(p: string): boolean
  rmSync(p: string, o: { recursive?: boolean; force?: boolean }): void
  readdirSync(p: string): string[]
}
const realFs: Fs = { existsSync, rmSync, readdirSync: (p) => readdirSync(p) }

export type WipeResult = { ok: boolean; removed: string[]; failed: string[]; skipped: string[] }

/** Remove every target that exists. One that can't go doesn't stop the others. Never logs a path (it names the home folder). */
export function wipe(targets: readonly Target[], roots: readonly string[], fs: Fs = realFs): WipeResult {
  const r: WipeResult = { ok: true, removed: [], failed: [], skipped: [] }
  for (const t of targets) {
    if (t.kind !== 'contents' && !insideRoots(t.path, roots)) {
      r.skipped.push(t.what)
      continue
    }
    if (t.kind === 'contents' && !roots.includes(resolve(t.path))) {
      r.skipped.push(t.what)
      continue
    }
    try {
      if (!fs.existsSync(t.path)) continue
      if (t.kind === 'contents') for (const name of fs.readdirSync(t.path)) fs.rmSync(join(t.path, name), { recursive: true, force: true })
      else fs.rmSync(t.path, { recursive: t.kind === 'dir', force: true })
      r.removed.push(t.what)
    } catch {
      r.ok = false
      r.failed.push(t.what)
    }
  }
  return r
}
