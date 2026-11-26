/**
 * Feature: ambient (help outside a lesson; shared/contracts/AMBIENT-HELP.md). The pure rules, no React, no timers, so
 * test/ambient.test.ts checks them offline.
 *
 *   offerError     is a spotted error worth a quiet chip now (setting on, app not muted, no lesson, not seen before)
 *   chipLine       "Error in Terminal" (the chip's words before Explain)
 *   stopLine       the card's calm first line: "Python stopped at line 3", never alarming, never red
 *   failLine       an AmbientFail in calm words ("Couldn't explain that just now. Try again in a minute.")
 *   isSetupQuery   the launcher text asks to set up the open project ("set up this project", "install dependencies")
 *   isHowDoI       the launcher text is a "how do I ..." about the app in front
 *   sortRows       missing rows first, then the ready ones (the engine already does it; an older one may not)
 *   cleanMuted     a bounded, de-duplicated muted-apps list (ambient.set allows 50)
 */
import type { AmbientErrorKind, AmbientFail, SeenError, SetupItem } from '../../../../../../shared/contracts/events'

/** How long the chip stays when nobody touches it (the brief: auto-hides after 20 s). */
export const CHIP_MS = 20_000
/** A finished help walk-through closes this long after its last step. */
export const HELP_DONE_MS = 2500
/** A help or explain failure line closes on its own after this. */
export const FAIL_MS = 6000
/** ambient.set mutedApps is at most this long (contract). */
export const MUTED_MAX = 50
/** help.ask text is at most this long (contract). */
export const ASK_MAX = 300

export type AmbientPrefs = { errors: boolean; mutedApps: string[] }
export const DEFAULT_AMBIENT: AmbientPrefs = { errors: true, mutedApps: [] }

const norm = (s: string | undefined | null): string => (s ?? '').trim().toLowerCase()

/** The same app however it was spelled ("Terminal", " terminal "). */
export const sameApp = (a: string | undefined, b: string | undefined): boolean => !!norm(a) && norm(a) === norm(b)

export function isMuted(app: string | undefined, muted: readonly string[]): boolean {
  return muted.some((m) => sameApp(m, app))
}

/** Trimmed, no empties, no case-duplicates, at most MUTED_MAX, each at most 80 characters. */
export function cleanMuted(list: unknown): string[] {
  if (!Array.isArray(list)) return []
  const out: string[] = []
  for (const v of list) {
    if (typeof v !== 'string') continue
    const s = v.trim().slice(0, 80)
    if (!s || out.some((o) => sameApp(o, s))) continue
    out.push(s)
    if (out.length >= MUTED_MAX) break
  }
  return out
}

export function cleanPrefs(raw: unknown): AmbientPrefs {
  const r = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  return { errors: typeof r.errors === 'boolean' ? r.errors : DEFAULT_AMBIENT.errors, mutedApps: cleanMuted(r.mutedApps) }
}

/** An error.seen payload that is a real error (not a {id, clear}), with what the chip needs. */
export function isSeenError(p: unknown): p is SeenError {
  if (!p || typeof p !== 'object') return false
  const e = p as Partial<SeenError> & { clear?: unknown }
  return !e.clear && typeof e.id === 'string' && !!e.id && typeof e.title === 'string' && typeof e.app === 'string'
}

export type OfferContext = {
  prefs: AmbientPrefs
  /** A lesson is loaded, building or on a step: the lesson's own off-track covers errors. */
  lesson: boolean
  /** Ids the learner closed, or that already had their 20 s: the same error again never comes back as a new chip. */
  seen: ReadonlySet<string>
  /** The id the chip or card shows now (the same error again just updates it). */
  showing?: string
}

/** Is this error worth a chip now? */
export function offerError(e: SeenError, ctx: OfferContext): boolean {
  if (!ctx.prefs.errors || ctx.lesson) return false
  if (isMuted(e.app, ctx.prefs.mutedApps)) return false
  if (ctx.showing === e.id) return true
  return !ctx.seen.has(e.id)
}

/** The chip's words: "Error in Terminal". An app with no name says "An error". */
export function chipLine(e: Pick<SeenError, 'app'>): string {
  const app = (e.app ?? '').trim()
  return app ? `Error in ${clip(app, 24)}` : 'An error'
}

const LANG: Partial<Record<string, string>> = { python: 'Python', javascript: 'JavaScript', typescript: 'TypeScript', js: 'JavaScript', ts: 'TypeScript', node: 'Node' }
const KIND_WHO: Record<AmbientErrorKind, string> = {
  python_traceback: 'Python',
  js_error: 'JavaScript',
  compiler: 'The build',
  shell_exit: 'The command',
  notebook_cell: 'The cell',
  app_dialog: ''
}

/**
 * The card's calm first line, from the error's own data: "Python stopped at line 3", "The command stopped (exit 1)",
 * "app.py has an error at line 12". A dialog says "<App> showed an error".
 */
export function stopLine(e: Pick<SeenError, 'kind' | 'lang' | 'line' | 'file' | 'exitCode' | 'app'>): string {
  if (e.kind === 'app_dialog') return `${(e.app ?? '').trim() || 'The app'} showed an error`
  if (e.kind === 'shell_exit') return typeof e.exitCode === 'number' ? `The command stopped (exit ${e.exitCode})` : 'The command stopped'
  const who = (e.lang && LANG[norm(e.lang)]) || KIND_WHO[e.kind] || 'It'
  if (e.kind === 'compiler') {
    const name = baseName(e.file)
    return name && typeof e.line === 'number' ? `${name} has an error at line ${e.line}` : 'The build stopped'
  }
  return typeof e.line === 'number' && e.line > 0 ? `${who} stopped at line ${e.line}` : `${who} stopped`
}

/** The file's own name ("~/code/app/app.py" -> "app.py"); paths stay on this Mac. */
export function baseName(file: string | undefined): string {
  if (!file) return ''
  const parts = file.split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] ?? ''
}

/** Retry wording from seconds: "in a minute", "in 20 minutes", "soon". */
export function retryWords(s: number | undefined): string {
  if (typeof s !== 'number' || !Number.isFinite(s) || s <= 0) return 'in a minute'
  if (s <= 90) return 'in a minute'
  const m = Math.round(s / 60)
  return m >= 60 ? 'in an hour' : `in ${m} minutes`
}

/** An AmbientFail in calm words, at most about 12 words. `what`: explain (an error) or help (a how-do-I). */
export function failLine(error: AmbientFail | string | undefined, retryInS?: number, what: 'explain' | 'help' = 'explain'): string {
  const verb = what === 'explain' ? 'explain that' : 'find the steps'
  switch (error) {
    case 'cap':
      return `That's enough help for now. Try again ${retryWords(retryInS)}.`
    case 'offline':
      return `miyagi is offline. Try again when you're connected.`
    case 'busy':
      return `Couldn't ${verb} just now. Try again in a minute.`
    case 'gone':
      return what === 'explain' ? 'That error is gone.' : 'That help ended.'
    case 'no_app':
      return 'Click the app you need help with, then ask again.'
    default:
      return `Couldn't ${verb} just now. Try again in a minute.`
  }
}

/** A fail worth a Try again button (the cap and a gone error are not). */
export const canRetry = (error: AmbientFail | string | undefined): boolean => error === 'busy' || error === 'offline' || error === 'failed' || error === undefined

// ---- the launcher's two commands ----------------------------------------------------------------------------------

/**
 * The whole input is one of these phrases. Never a prefix: on the way to "set up a React app" or "install pytorch" the
 * partial text ("set", "set up", "install") would swap the search rows for this command for a moment.
 */
const SETUP_PHRASES = ['set up this project', 'setup this project', 'check this project', 'set up my project', 'set up project', 'project setup', 'install dependencies', 'install requirements', 'fix my environment', 'set up my environment']
/** Or exactly one of these shapes ("set up the environment", "install the deps"). Never a topic like "set up a React app". */
const SETUP_RE = /^(set ?up|check|scan|fix)( my| this| the)? (project|environment|env|dev environment|folder|repo)$|^install( the| my)? (dependencies|deps|requirements|packages)$/

export function isSetupQuery(text: string): boolean {
  const q = text.trim().toLowerCase().replace(/\s+/g, ' ').replace(/[.?!]+$/, '')
  return SETUP_PHRASES.includes(q) || SETUP_RE.test(q)
}

/** "how do I export as STL", "how can I ...", "where is the export button", "how to ..." (and something after it). */
const HOW_RE = /^(how (do|can|would|should) i|how to|where (is|are|do i find|can i find)|where's|how do you)\s+\S/i

export function isHowDoI(text: string): boolean {
  const t = text.trim()
  return t.length <= ASK_MAX && HOW_RE.test(t)
}

// ---- the setup card ---------------------------------------------------------------------------------------------

/** Missing (needed and not ok) rows first, in the engine's order; then the ready ones. */
export function sortRows(items: readonly SetupItem[]): SetupItem[] {
  const missing = items.filter((x) => x.needed && !x.ok)
  const rest = items.filter((x) => !(x.needed && !x.ok))
  return [...missing, ...rest]
}

/** What the row's button does: install through setup.fix, open a page (licensed / download / web app), or nothing. */
export type RowFix = 'install' | 'link' | 'none'

export function rowFix(x: SetupItem): RowFix {
  if (!x.needed || x.ok) return 'none'
  const m = x.install?.method
  if (x.setupKind === 'licensed_app' || m === 'download' || m === 'open') return x.install?.url ? 'link' : 'none'
  if (m === 'brew' || m === 'brew_cask' || m === 'pip' || m === 'npm' || m === 'vscode_ext') return 'install'
  return 'none'
}

/** The rows "Fix all" may install, in order (never a licensed app: those are never installed). */
export function fixable(items: readonly SetupItem[]): string[] {
  return sortRows(items)
    .filter((x) => rowFix(x) === 'install')
    .map((x) => x.tool)
}

/** "4 of 7 ready" / "All 7 ready" / "Nothing to set up". */
export function readyLine(ready: number, total: number): string {
  if (!total) return 'Nothing to set up'
  if (ready >= total) return total === 1 ? 'Ready' : `All ${total} ready`
  return `${ready} of ${total} ready`
}

/** A row's second line: why, and the file that asked for it. */
export function rowDetail(x: Pick<SetupItem, 'why' | 'from'>): string {
  const why = (x.why ?? '').trim()
  return x.from ? (why ? `${why} · ${x.from}` : x.from) : why
}

/** setup.report error in calm words. */
export function scanError(error: string | undefined): string | undefined {
  if (error === 'no_project') return 'Open a project folder in VS Code, then try again.'
  if (error === 'too_big') return 'This folder is too big to check. Open the project folder itself.'
  if (error === 'unreadable') return "Couldn't read this project's files."
  return error ? "Couldn't check this project just now." : undefined
}

/** One help step's position: "2 of 4". */
export const stepCount = (current: number, total: number): string => `${Math.min(total, current + 1)} of ${total}`

/** Cut at a word boundary with "…" past `max` characters. */
export function clip(text: string, max: number): string {
  if (text.length <= max) return text
  const at = text.lastIndexOf(' ', max)
  return `${(at > max / 2 ? text.slice(0, at) : text.slice(0, max)).replace(/[\s,:·–—-]+$/, '')}…`
}
