/**
 * Island diagnostics: what is the island's window really doing on this Mac, written to ~/Library/Logs/miyagi/island.log
 * (a packaged app has no console). Log-only: nothing here changes placement, hit testing or what is drawn.
 *
 * A black island on the black hardware notch looks the same whether it works or not, so the log is the evidence:
 *   - `snapshot`   overlay getBounds / isVisible / isAlwaysOnTop / isVisibleOnAllWorkspaces, the display's bounds /
 *                  workArea / scaleFactor, the helper's safeTop and aux widths, the chosen place and coexist, and the
 *                  window level last seen by the CGWindowList dump. One line each, at ready and on every resend, display
 *                  event, resume, unlock and raise.
 *   - `windows`    miyagi's own CGWindowList entries (layer, bounds, on-screen, z) from `miyagi-listen --windows`, every
 *                  30 s and on resume. It also lists the windows of other notch apps by owner name, so the draw order of
 *                  the two apps' windows is observed instead of assumed.
 *   - `grab`       the overlay stopped / started ignoring the mouse, with the cursor point and the island rect.
 *   - `away`/`wake` the overlay's away state (A8) and main's wake broadcast.
 *   - `other-notch-app` another notch app started or quit (matched process name).
 *   - `renderer`   what the overlay's page measured (island rect, clip-path, devicePixelRatio, visibilityState, hover
 *                  and peek counts), sent over the `island:diag` IPC by renderer/core/islandDiagReport.ts.
 * The file rotates to island.log.1 at about 512 KB, so it can never grow without bound.
 *
 * No electron import at runtime (types only): main/index.ts passes everything in, so test/islandDiag.test.ts runs under node.
 */
import { execFile } from 'node:child_process'
import { appendFileSync, existsSync, mkdirSync, renameSync, statSync } from 'node:fs'
import { dirname } from 'node:path'
import type { ScreenInfo } from '../../common/notch'
import { parseScreens } from '../../common/notch'

/** island.log rotates (to island.log.1, replacing it) once it is bigger than this. */
export const LOG_CAP_BYTES = 512 * 1024
export const WINDOWS_DUMP_MS = 30_000
const OTHER_POLL_MS = 10_000
const HELPER_TIMEOUT_MS = 2500
/** Process names of other apps that draw in the notch (matched with pgrep -x; also the owner names listed by --windows). */
export const OTHER_NOTCH_APPS = ['boringNotch', 'Boring Notch']

type Rect = { x: number; y: number; width: number; height: number }

/** Append one line to the log, rotating first when the file is over the cap. Never throws. */
export function appendRotating(file: string, line: string, cap = LOG_CAP_BYTES): void {
  try {
    mkdirSync(dirname(file), { recursive: true })
    if (existsSync(file) && statSync(file).size > cap) renameSync(file, `${file}.1`)
    appendFileSync(file, `${line.replace(/[\r\n]+/g, ' ')}\n`)
  } catch {
    /* logging never breaks the island */
  }
}

// ---- snapshot ---------------------------------------------------------------------------------------------------------

export type Snapshot = {
  at: string
  why: string
  overlay: Rect
  visible: boolean
  alwaysOnTop: boolean
  allWorkspaces: boolean
  /** The overlay's window level from the last CGWindowList dump (kCGWindowLayer); undefined until one ran. */
  level?: number
  display: { id: number; bounds: Rect; workArea: Rect; scale: number }
  safeTop?: number | null
  auxLeft?: number | null
  auxRight?: number | null
  place: string
  coexist?: boolean
  hasNotch?: boolean
}

const r4 = (n: number): string => String(Math.round(n * 100) / 100)
const rect = (r: Rect): string => `${r4(r.x)},${r4(r.y)},${r4(r.width)}x${r4(r.height)}`
const opt = (v: unknown): string => (v === undefined || v === null ? '?' : String(v))

/** One line per snapshot (no newline inside). Everything on it is a measurement; nothing is derived. */
export function formatSnapshot(s: Snapshot): string {
  return [
    `${s.at} ${s.why}`,
    `overlay=${rect(s.overlay)}`,
    `visible=${s.visible}`,
    `onTop=${s.alwaysOnTop}`,
    `allWorkspaces=${s.allWorkspaces}`,
    `level=${opt(s.level)}`,
    `display=${s.display.id}`,
    `bounds=${rect(s.display.bounds)}`,
    `work=${rect(s.display.workArea)}`,
    `scale=${r4(s.display.scale)}`,
    `safeTop=${opt(s.safeTop)}`,
    `auxL=${opt(s.auxLeft)}`,
    `auxR=${opt(s.auxRight)}`,
    `place=${s.place}`,
    `hasNotch=${opt(s.hasNotch)}`,
    `coexist=${opt(s.coexist)}`
  ].join(' ')
}

// ---- `miyagi-listen --windows` ----------------------------------------------------------------------------------------

export type WindowEntry = { id: number; pid: number; owner: string; layer: number; x: number; y: number; w: number; h: number; onscreen: boolean; alpha: number; z: number }

/** Parse the helper's one JSON line (native/listen/Windows.swift). Bad or empty output is an empty list; bad entries are skipped. */
export function parseWindows(text: string): WindowEntry[] {
  const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
  try {
    const line = String(text).split('\n').find((l) => l.trim().startsWith('{')) ?? ''
    const list = (JSON.parse(line) as { windows?: unknown }).windows
    if (!Array.isArray(list)) return []
    const out: WindowEntry[] = []
    for (const raw of list) {
      if (!raw || typeof raw !== 'object') continue
      const o = raw as Record<string, unknown>
      const b = (o.bounds && typeof o.bounds === 'object' ? o.bounds : {}) as Record<string, unknown>
      const id = num(o.id), pid = num(o.pid), layer = num(o.layer), x = num(b.x), y = num(b.y), w = num(b.w), h = num(b.h), z = num(o.z)
      if (id === null || pid === null || layer === null || x === null || y === null || w === null || h === null || z === null) continue
      out.push({ id, pid, owner: typeof o.owner === 'string' ? o.owner : '', layer, x, y, w, h, onscreen: o.onscreen === true, alpha: num(o.alpha) ?? 1, z })
    }
    return out
  } catch {
    return []
  }
}

/** One line for a dump: `windows <why> n=2 | owner(pid)#id layer=1000 bounds=0,0,1728x1117 onscreen=true z=3 | ...`. */
export function formatWindows(at: string, why: string, list: WindowEntry[]): string {
  const rows = list.map((e) => `${e.owner || '?'}(${e.pid})#${e.id} layer=${e.layer} bounds=${rect({ x: e.x, y: e.y, width: e.w, height: e.h })} onscreen=${e.onscreen} alpha=${r4(e.alpha)} z=${e.z}`)
  return [`${at} windows:${why} n=${list.length}`, ...rows].join(' | ')
}

/** The overlay's window level: the layer of this process's biggest window that the system lists. */
export function overlayLevel(list: WindowEntry[], pid: number): number | undefined {
  let best: WindowEntry | undefined
  for (const e of list) if (e.pid === pid && (!best || e.w * e.h > best.w * best.h)) best = e
  return best?.layer
}

// ---- the island's rect (same arithmetic as features/overlay-raise.ts) -------------------------------------------------

export function islandRect(
  size: { w: number; h: number; dx?: number; dy?: number; shown?: boolean; top?: number; place?: string },
  bounds: Rect,
  pillTop: number
): { x: number; y: number; w: number; h: number } | null {
  if (size.shown === false) return null
  const top = size.place === 'notch' ? (size.top ?? 0) : pillTop
  return { x: bounds.x + bounds.width / 2 - size.w / 2 + (size.dx ?? 0), y: bounds.y + top + (size.dy ?? 0), w: size.w, h: size.h }
}

// ---- renderer report (island:diag) ------------------------------------------------------------------------------------

export type RendererReport = {
  why: string
  island: { x: number; y: number; w: number; h: number } | null
  clipPath: string
  dpr: number
  visibility: string
  hover: { count: number; lastAt: number }
  peek: { opens: number; closes: number; lastAt: number }
  /** What the page itself holds: its route and the layout.notch it last received (debugging "not in the notch"). */
  seen: string
}

/** Validate an untrusted IPC payload: only plain numbers and short strings survive. Null when it is not a report. */
export function sanitizeRendererReport(raw: unknown): RendererReport | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const n = (v: unknown, d = 0): number => (typeof v === 'number' && Number.isFinite(v) ? v : d)
  const s = (v: unknown, max: number): string => (typeof v === 'string' ? v.replace(/[\r\n]+/g, ' ').slice(0, max) : '')
  const i = o.island && typeof o.island === 'object' ? (o.island as Record<string, unknown>) : undefined
  const h = (o.hover && typeof o.hover === 'object' ? o.hover : {}) as Record<string, unknown>
  const p = (o.peek && typeof o.peek === 'object' ? o.peek : {}) as Record<string, unknown>
  return {
    why: s(o.why, 24) || 'report',
    island: i ? { x: n(i.x), y: n(i.y), w: n(i.w), h: n(i.h) } : null,
    clipPath: s(o.clipPath, 200),
    dpr: n(o.dpr, 1),
    visibility: s(o.visibility, 16),
    hover: { count: n(h.count), lastAt: n(h.lastAt) },
    peek: { opens: n(p.opens), closes: n(p.closes), lastAt: n(p.lastAt) },
    seen: s(o.seen, 900)
  }
}

export function formatRenderer(at: string, r: RendererReport): string {
  const t = (ms: number): string => (ms > 0 ? new Date(ms).toISOString() : '-')
  const isl = r.island ? rect({ x: r.island.x, y: r.island.y, width: r.island.w, height: r.island.h }) : 'none'
  return `${at} renderer:${r.why} island=${isl} clip="${r.clipPath || 'none'}" dpr=${r4(r.dpr)} visibility=${r.visibility || '?'} hover=${r.hover.count}@${t(r.hover.lastAt)} peek=${r.peek.opens}/${r.peek.closes}@${t(r.peek.lastAt)}${r.seen ? ` seen=${r.seen}` : ''}`
}

// ---- the recorder -----------------------------------------------------------------------------------------------------

type OverlayLike = {
  isDestroyed(): boolean
  getBounds(): Rect
  isVisible(): boolean
  isAlwaysOnTop(): boolean
  isVisibleOnAllWorkspaces(): boolean
  setIgnoreMouseEvents(ignore: boolean, options?: { forward?: boolean }): void
}

export type IslandDiagOpts = {
  logFile: string
  /** The overlay window (a getter: it is created after this module loads). */
  overlay: () => OverlayLike | undefined
  display: () => { id: number; bounds: Rect; workArea: Rect; scaleFactor: number }
  /** The overlay's layout.notch as main last sent it. */
  notch: () => { place: string; hasNotch?: boolean; coexist?: boolean }
  islandSize: () => { w: number; h: number; dx?: number; dy?: number; shown?: boolean; top?: number; place?: string }
  pillTop: () => number
  cursor: () => { x: number; y: number }
  /** Path of miyagi-listen; with mac false nothing runs. */
  helperBin: string
  mac: boolean
  pid: number
  /** Test seams. */
  now?: () => Date
  run?: (bin: string, args: string[]) => Promise<string>
  pgrep?: (name: string) => Promise<boolean>
  cap?: number
}

export type IslandDiag = {
  /** Log one snapshot line. 'resend' and 'raise' skip a line identical (but for its time) to the previous one. */
  snapshot(why: string): void
  /** Dump miyagi's own CGWindowList entries (and other notch apps') as one line. */
  dumpWindows(why: string): Promise<void>
  /** Feature calls main already routes: 'overlay:away' (payload on/off) and 'overlay:wake'. */
  onFeature(channel: string, payload?: unknown): void
  /** The `island:diag` IPC handler. */
  onRenderer(raw: unknown): void
  /** Re-read `--screens` (safeTop, aux widths); logs when the answer changed. */
  refreshScreens(why: string): Promise<void>
  /** Start the timers and the grab / other-app watchers. Call once the overlay exists. */
  start(): void
  stop(): void
}

function execText(bin: string, args: string[]): Promise<string> {
  return new Promise((resolve) => {
    try {
      execFile(bin, args, { timeout: HELPER_TIMEOUT_MS, maxBuffer: 1 << 20 }, (err, stdout) => resolve(err ? '' : String(stdout)))
    } catch {
      resolve('')
    }
  })
}

function pgrepExact(name: string): Promise<boolean> {
  return new Promise((resolve) => {
    try {
      execFile('pgrep', ['-x', name], { timeout: 1500 }, (err, stdout) => resolve(!err && String(stdout).trim().length > 0))
    } catch {
      resolve(false)
    }
  })
}

export function createIslandDiag(o: IslandDiagOpts): IslandDiag {
  const now = o.now ?? ((): Date => new Date())
  const run = o.run ?? execText
  const pgrep = o.pgrep ?? pgrepExact
  const write = (line: string): void => appendRotating(o.logFile, line, o.cap)
  const stamp = (): string => now().toISOString()
  let screens: ScreenInfo[] = []
  let level: number | undefined
  let lastKey = ''
  let away: boolean | undefined
  let ignoring: boolean | undefined
  let others = ''
  let dumping = false
  let timers: ReturnType<typeof setInterval>[] = []
  let started = false

  const screenFor = (id: number): ScreenInfo | undefined => screens.find((s) => s.id === id)

  function snapshot(why: string): void {
    try {
      const w = o.overlay()
      if (!w || w.isDestroyed()) return
      const d = o.display()
      const n = o.notch()
      const sc = screenFor(d.id)
      const line = formatSnapshot({
        at: stamp(),
        why,
        overlay: w.getBounds(),
        visible: w.isVisible(),
        alwaysOnTop: w.isAlwaysOnTop(),
        allWorkspaces: w.isVisibleOnAllWorkspaces(),
        level,
        display: { id: d.id, bounds: d.bounds, workArea: d.workArea, scale: d.scaleFactor },
        safeTop: sc?.safeTop,
        auxLeft: sc?.auxLeft,
        auxRight: sc?.auxRight,
        place: n.place,
        coexist: n.coexist,
        hasNotch: n.hasNotch
      })
      const key = line.slice(line.indexOf(' ') + 1)
      if ((why === 'resend' || why === 'raise') && key === lastKey) return
      lastKey = key
      write(line)
    } catch {
      /* never breaks the island */
    }
  }

  async function dumpWindows(why: string): Promise<void> {
    if (!o.mac || dumping) return
    dumping = true
    try {
      const args = ['--windows', '--pid', String(o.pid)]
      for (const name of OTHER_NOTCH_APPS) args.push('--owner', name)
      const list = parseWindows(await run(o.helperBin, args))
      level = overlayLevel(list, o.pid) ?? level
      write(formatWindows(stamp(), why, list))
    } finally {
      dumping = false
    }
  }

  async function refreshScreens(why: string): Promise<void> {
    if (!o.mac) return
    const next = parseScreens(await run(o.helperBin, ['--screens']))
    if (next.length === 0 || JSON.stringify(next) === JSON.stringify(screens)) return
    screens = next
    snapshot(`screens:${why}`)
  }

  function onFeature(channel: string, payload?: unknown): void {
    const point = (): string => {
      const c = o.cursor()
      const isl = islandRect(o.islandSize(), o.display().bounds, o.pillTop())
      return `cursor=${r4(c.x)},${r4(c.y)} island=${isl ? rect({ x: isl.x, y: isl.y, width: isl.w, height: isl.h }) : 'none'}`
    }
    if (channel === 'overlay:away') {
      const next = !!payload
      if (next === away) return
      away = next
      write(`${stamp()} away=${next} ${point()}`)
    } else if (channel === 'overlay:wake') {
      write(`${stamp()} wake ${point()}`)
    }
  }

  /** The overlay's click-through switch is the grab: ignore=false means the overlay is eating the mouse. Wrapped once. */
  function watchGrab(): void {
    const w = o.overlay()
    if (!w || w.isDestroyed()) return
    const orig = w.setIgnoreMouseEvents.bind(w)
    w.setIgnoreMouseEvents = (ignore: boolean, options?: { forward?: boolean }): void => {
      try {
        if (ignore !== ignoring) {
          ignoring = ignore
          const c = o.cursor()
          const isl = islandRect(o.islandSize(), o.display().bounds, o.pillTop())
          write(`${stamp()} grabbed=${!ignore} cursor=${r4(c.x)},${r4(c.y)} island=${isl ? rect({ x: isl.x, y: isl.y, width: isl.w, height: isl.h }) : 'none'}`)
        }
      } catch {
        /* never breaks the island */
      }
      orig(ignore, options)
    }
  }

  async function pollOthers(): Promise<void> {
    if (!o.mac) return
    const running: string[] = []
    for (const name of OTHER_NOTCH_APPS) if (await pgrep(name)) running.push(name)
    const key = running.join(',')
    if (key === others) return
    others = key
    write(`${stamp()} other-notch-app running=[${key}]`)
  }

  function onRenderer(raw: unknown): void {
    const r = sanitizeRendererReport(raw)
    if (r) write(formatRenderer(stamp(), r))
  }

  function start(): void {
    if (started) return
    started = true
    watchGrab()
    void refreshScreens('start')
    void pollOthers()
    void dumpWindows('start')
    if (o.mac) {
      const t1 = setInterval(() => void dumpWindows('periodic'), WINDOWS_DUMP_MS)
      const t2 = setInterval(() => void pollOthers(), OTHER_POLL_MS)
      t1.unref?.()
      t2.unref?.()
      timers = [t1, t2]
    }
  }

  return {
    snapshot,
    dumpWindows,
    onFeature,
    onRenderer,
    refreshScreens,
    start,
    stop() {
      for (const t of timers) clearInterval(t)
      timers = []
    }
  }
}
