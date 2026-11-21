/**
 * Main: where the notch is. Runs `miyagi-listen --screens` (one-shot, no permissions) at launch and when displays
 * change, caches the answer by display id, and watches for Boring Notch (which owns the notch while it runs).
 * Pure parts (notchFor, effectivePlace, parseScreens) live in common/notch.ts; this file only talks to processes.
 * No electron import: the caller passes the helper path and the display events.
 */
import { execFile } from 'node:child_process'
import { existsSync } from 'node:fs'
import { effectivePlace, notchFor, parseScreens, type IslandPlace, type NotchLayout, type ScreenInfo } from '../common/notch'

export { effectivePlace, notchFor, parseScreens, type IslandPlace, type NotchGeom, type NotchLayout, type ScreenInfo } from '../common/notch'

const HELPER_TIMEOUT_MS = 2000
const REFRESH_DEBOUNCE_MS = 300
const BORING_POLL_MS = 30_000

/** Run the helper's --screens. Never rejects: a missing helper, a timeout or bad output is an empty list. */
export function readScreens(bin: string): Promise<ScreenInfo[]> {
  return new Promise((resolve) => {
    try {
      if (!existsSync(bin)) return resolve([])
      execFile(bin, ['--screens'], { timeout: HELPER_TIMEOUT_MS, maxBuffer: 1 << 20 }, (err, stdout) => resolve(err ? [] : parseScreens(String(stdout))))
    } catch {
      resolve([])
    }
  })
}

/** Is Boring Notch running? A cheap pgrep on its process name; any failure (no match exits 1, no pgrep) is "no". Never throws. */
export function isBoringNotchRunning(): Promise<boolean> {
  return new Promise((resolve) => {
    try {
      execFile('pgrep', ['-x', 'boringNotch'], { timeout: 1500 }, (err, stdout) => resolve(!err && String(stdout).trim().length > 0))
    } catch {
      resolve(false)
    }
  })
}

type Display = { id: number; bounds: { x: number; y: number; width: number; height: number }; workArea: { x: number; y: number; width: number; height: number } }

export type NotchService = {
  /** The notch part of `layout` for a display, given the pref. */
  layoutFor(display: Display, pref: IslandPlace | undefined): NotchLayout
  /** Re-read the screens (debounced 300 ms, for display events). */
  refresh(): void
  boringNotch(): boolean
  stop(): void
}

/**
 * Start the service (macOS only does real work; elsewhere it answers the fake notch and 'below' via effectivePlace).
 * `onChange` fires when the geometry or the Boring Notch state changed, so main re-sends the layout.
 */
export function startNotch(opts: { helperBin: string; mac: boolean; onChange: () => void }): NotchService {
  let cache = new Map<number, ScreenInfo>()
  let boring = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let poll: ReturnType<typeof setInterval> | undefined
  let stopped = false

  const readNow = async (): Promise<void> => {
    if (!opts.mac) return
    const next = new Map(parseList(await readScreens(opts.helperBin)))
    if (stopped) return
    const changed = JSON.stringify([...next]) !== JSON.stringify([...cache])
    cache = next
    if (changed) opts.onChange()
  }
  const checkBoring = async (): Promise<void> => {
    if (!opts.mac) return
    const now = await isBoringNotchRunning()
    if (stopped || now === boring) return
    boring = now
    opts.onChange()
  }
  void readNow()
  void checkBoring()
  if (opts.mac) {
    poll = setInterval(() => void checkBoring(), BORING_POLL_MS)
    poll.unref?.()
  }

  return {
    layoutFor(display, pref) {
      return { ...notchFor(display, cache.get(display.id)), place: effectivePlace(pref, opts.mac, boring), boringNotch: boring }
    },
    refresh() {
      clearTimeout(timer)
      timer = setTimeout(() => void readNow(), REFRESH_DEBOUNCE_MS)
    },
    boringNotch: () => boring,
    stop() {
      stopped = true
      clearTimeout(timer)
      if (poll) clearInterval(poll)
    }
  }
}

function parseList(list: ScreenInfo[]): [number, ScreenInfo][] {
  return list.map((s) => [s.id, s])
}
