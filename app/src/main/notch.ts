/**
 * Main: where the notch is. Runs `miyagi-listen --screens` (one-shot, no permissions) at launch and when displays
 * change, and keeps the last good answer per display id: a failed or timed-out read never wipes geometry we already
 * had (retried once), the last good geometry is persisted so a launch can place the island before the helper answers,
 * and nothing is emitted from a fake geometry. Also notes (privately, log-only) whether another notch app is running.
 * Pure parts (notchFor, effectivePlace, parseScreens) live in common/notch.ts; this file only talks to processes.
 * No electron import: the caller passes the helper path, the cache file and the display events.
 */
import { execFile } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { effectivePlace, notchFor, parseScreens, type IslandPlace, type NotchGeom, type NotchLayout, type ScreenInfo } from '../common/notch'

export { effectivePlace, notchFor, parseScreens, type IslandPlace, type NotchGeom, type NotchLayout, type ScreenInfo } from '../common/notch'

const HELPER_TIMEOUT_MS = 2000
/** Display events, wake and unlock come in bursts: one read, this long after the last. */
export const REFRESH_DEBOUNCE_MS = 250
/** Between the first try and its one retry. */
const RETRY_MS = 400
/** recheck() (app focus, pref change) re-reads the helper at most this often. */
const RECHECK_MIN_MS = 1000
/** pgrep is cheap; a short poll catches the other notch app starting or quitting. */
const OTHER_POLL_MS = 5_000

/** Run the helper's --screens. Resolves null when it could not answer (missing, timeout, bad or empty output); never rejects. */
export function readScreensOrNull(bin: string): Promise<ScreenInfo[] | null> {
  return new Promise((resolve) => {
    try {
      if (!existsSync(bin)) return resolve(null)
      execFile(bin, ['--screens'], { timeout: HELPER_TIMEOUT_MS, maxBuffer: 1 << 20 }, (err, stdout) => {
        if (err) return resolve(null)
        const list = parseScreens(String(stdout))
        resolve(list.length ? list : null) // a Mac always has a screen: an empty list is a failed read
      })
    } catch {
      resolve(null)
    }
  })
}

/** Run the helper's --screens. Never rejects: a missing helper, a timeout or bad output is an empty list. */
export async function readScreens(bin: string): Promise<ScreenInfo[]> {
  return (await readScreensOrNull(bin)) ?? []
}

const found = (cmd: string, args: string[]): Promise<boolean> =>
  new Promise((resolve) => {
    try {
      execFile(cmd, args, { timeout: 1500 }, (err, stdout) => resolve(!err && String(stdout).trim().length > 0))
    } catch {
      resolve(false)
    }
  })

/**
 * Is another notch app running? Private and log-only: it sets `coexist` on the layout, never the placement and never
 * any UI text. Matches the bundle id and the process names; nothing is launched. Any failure is "no". Never throws.
 */
export async function isOtherNotchAppRunning(): Promise<boolean> {
  const hits = await Promise.all([
    found('pgrep', ['-x', 'boringNotch']),
    found('pgrep', ['-x', 'Boring Notch']),
    found('lsappinfo', ['find', 'bundleid=theboringteam.boringnotch'])
  ])
  return hits.some(Boolean)
}

type Display = { id: number; bounds: { x: number; y: number; width: number; height: number }; workArea: { x: number; y: number; width: number; height: number } }

export type NotchService = {
  /** The notch part of `layout` for a display, given the pref. */
  layoutFor(display: Display, pref: IslandPlace | undefined): NotchLayout
  /** The notch geometry for a display (display-local), as the layout carries it. */
  geometryFor(display: Display): NotchGeom
  /** Another notch app is running (private, log-only flag). */
  coexist(): boolean
  /** True once geometry for at least one display is known (read or persisted); until then every layout is `below`, never a fake notch. */
  ready(): boolean
  /** Re-read the screens (debounced 250 ms, for display events, wake and unlock). */
  refresh(): void
  /** Deprecated, always false (the layout still carries the field for one merge). */
  boringNotch(): boolean
  /** Look again right now (pref change, app focused): re-reads the helper (at most once a second) and the other-app state. Resolves after; `onChange` has fired if anything changed. */
  recheck(): Promise<void>
  stop(): void
}

export type StartNotchOpts = {
  helperBin: string
  mac: boolean
  onChange: () => void
  /** Where to persist the last good geometry (e.g. join(app.getPath('userData'), 'notch-cache.json')). Absent: not persisted. */
  cacheFile?: string
  /** Tests: replace the helper call (null = failed). */
  read?: () => Promise<ScreenInfo[] | null>
  /** Tests: replace the other-notch-app check. */
  isOther?: () => Promise<boolean>
  pollMs?: number
  debounceMs?: number
  retryMs?: number
}

let current: NotchService | undefined
/** The running service, for features that only read it (overlay-raise). */
export const getNotchService = (): NotchService | undefined => current

function loadCache(file: string | undefined): Map<number, ScreenInfo> {
  const out = new Map<number, ScreenInfo>()
  try {
    if (file && existsSync(file)) for (const s of parseScreens(readFileSync(file, 'utf8'))) out.set(s.id, s)
  } catch {
    /* an unreadable cache is no cache */
  }
  return out
}

function saveCache(file: string | undefined, good: Map<number, ScreenInfo>): void {
  if (!file) return
  try {
    mkdirSync(dirname(file), { recursive: true })
    writeFileSync(file, JSON.stringify({ screens: [...good.values()] }) + '\n')
  } catch {
    /* persisting is best effort */
  }
}

/**
 * Start the service (macOS only does real work; elsewhere every layout is 'below').
 * `onChange` fires when the geometry or the coexist flag changed, so main re-sends the layout.
 */
export function startNotch(opts: StartNotchOpts): NotchService {
  /** The last good geometry per display id: only ever replaced by a successful read, never wiped. */
  const good = opts.mac ? loadCache(opts.cacheFile) : new Map<number, ScreenInfo>()
  let coexist = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let poll: ReturnType<typeof setInterval> | undefined
  let stopped = false
  let inflight: Promise<void> | undefined
  let lastRead = 0

  const read = opts.read ?? ((): Promise<ScreenInfo[] | null> => readScreensOrNull(opts.helperBin))
  const wait = (ms: number): Promise<void> => new Promise((r) => (setTimeout(r, ms) as { unref?: () => void }).unref?.())

  const readOnce = async (): Promise<void> => {
    let list = await read().catch(() => null)
    if (!list?.length && !stopped) {
      await wait(opts.retryMs ?? RETRY_MS)
      list = await read().catch(() => null)
    }
    if (stopped) return
    if (!list?.length) return // failed twice: keep the last good geometry as it is
    const before = JSON.stringify([...good])
    // A successful read lists every display now attached: forget the ones that are gone (ids can be recycled).
    const ids = new Set(list.map((s) => s.id))
    for (const id of [...good.keys()]) if (!ids.has(id)) good.delete(id)
    for (const s of list) good.set(s.id, s)
    if (JSON.stringify([...good]) === before) return
    saveCache(opts.cacheFile, good)
    opts.onChange()
  }
  const readNow = (): Promise<void> => {
    if (!opts.mac) return Promise.resolve()
    lastRead = Date.now()
    inflight ??= readOnce().finally(() => (inflight = undefined))
    return inflight
  }
  const checkOther = async (): Promise<void> => {
    if (!opts.mac) return
    const now = await (opts.isOther ?? isOtherNotchAppRunning)().catch(() => false)
    if (stopped || now === coexist) return
    coexist = now
    opts.onChange()
  }
  void readNow()
  void checkOther()
  if (opts.mac) {
    poll = setInterval(() => void checkOther(), opts.pollMs ?? OTHER_POLL_MS)
    poll.unref?.()
  }

  /** An entry fits a display only if its frame is that display's size: an id Electron reassigned must not lend its notch to another screen. */
  const fits = (s: ScreenInfo | undefined, display: Display): ScreenInfo | undefined =>
    s && Math.abs(s.frame.w - display.bounds.width) < 2 && Math.abs(s.frame.h - display.bounds.height) < 2 ? s : undefined
  const geometryFor = (display: Display): NotchGeom => notchFor(display, fits(good.get(display.id), display))
  const svc: NotchService = {
    layoutFor(display, pref) {
      const geom = geometryFor(display)
      // Until geometry is known there is no notch to draw: 'below' (the renderer shows nothing black), then a resend.
      const place = good.size ? effectivePlace(pref, opts.mac, geom.hasNotch) : 'below'
      return { ...geom, place, coexist, boringNotch: false }
    },
    geometryFor,
    coexist: () => coexist,
    ready: () => good.size > 0,
    refresh() {
      clearTimeout(timer)
      timer = setTimeout(() => void readNow(), opts.debounceMs ?? REFRESH_DEBOUNCE_MS)
    },
    boringNotch: () => false,
    async recheck() {
      if (Date.now() - lastRead >= RECHECK_MIN_MS) await readNow()
      await checkOther()
    },
    stop() {
      stopped = true
      clearTimeout(timer)
      if (poll) clearInterval(poll)
      if (current === svc) current = undefined
    }
  }
  current = svc
  return svc
}

/** The island pref changed: look again (helper and other-app state), then resend the layout whatever the answer, so the choice acts at once. */
export function recheckThenResend(svc: Pick<NotchService, 'recheck'> | undefined, resend: () => void): Promise<void> {
  return (svc?.recheck() ?? Promise.resolve()).catch(() => undefined).then(resend)
}
