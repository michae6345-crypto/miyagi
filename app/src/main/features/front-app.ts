/**
 * Which app is in front (Michael's review of desktop tests 2-3, A8 / A9).
 *
 * The engine's events don't say (spotlight.app names the box's app; screen.seen is a 5 s debug summary), so main
 * reads it here and broadcasts it: bridge.onFeature('front:app', (s: FrontState) => …); bridge.invoke('front:state')
 * returns the current one (a renderer that loads late or reloads).
 *   A8: features/shortcut-bar folds the bar to its handle and asks main to make the overlay click-through
 *       (main/features/overlay-raise.ts, 'overlay:away') once a non-lesson app has been in front for a few seconds.
 *   A9: features/spotlight/store.ts draws the box only while its app (spotlight.app) is in front: `aliases`.
 *
 * macOS: Launch Services (`lsappinfo front` + `lsappinfo info`, ~15 ms, no permission prompt), like the engine
 * (server/workspace/editor.py). Never `osascript … System Events`: that asks for Automation mid-demo.
 * Read when the front app changes, not on a clock (perf lane, Nov 25: two lsappinfo processes every second):
 * NSWorkspaceDidActivateApplicationNotification (systemPreferences.subscribeWorkspaceNotification) and miyagi's own
 * did-become-active / did-resign-active trigger a read (and one more LAG_MS later: Launch Services can lag the
 * notification), plus a slow SAFETY_MS re-read in case a notification is missed.
 * Without the notification (it threw), the old POLL_MS poll. One read at a time (a trigger during a read queues one
 * more), TIMEOUT_MS each. A missing or failing lsappinfo never throws: after MAX_FAILS failures in a row reading stops
 * and the front app stays unknown, which the renderer treats as the lesson's (nothing folds, nothing hides). Windows:
 * not read (unknown). MIYAGI_FRONT_APP=0 turns it off. watchFront (exported) is the scheduling, tested offline.
 *
 * The lesson's apps: the editors and terminals below, miyagi itself (its bundle, or one of its windows has the
 * keyboard: the launcher is a non-activating panel, so Launch Services still names the editor), and every app the
 * engine named this lesson (spotlight.app, the setup card's editorLabel).
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac.
 */
import { execFile } from 'node:child_process'
import { app, BrowserWindow, systemPreferences } from 'electron'
import { defineMainFeature } from '../context'

/** Mirrored in renderer features/shortcut-bar/front.ts. */
export type FrontState = {
  /** false: no reading (Windows, lsappinfo missing, not read yet). */
  known: boolean
  /** Launch Services' display name ("Code", "Google Chrome") and bundle id. */
  name: string
  bundle: string
  /** Lowercase names this app goes by ("code", "visual studio code"…), to compare with spotlight.app. */
  aliases: string[]
  /** One of miyagi's own windows / processes is in front. */
  miyagi: boolean
  /** It's one of the lesson's apps (see above). */
  lesson: boolean
}

/** Without the activation notification: read this often (the old poll). */
const POLL_MS = 1000
/** With it: still re-read this often, in case a notification was missed. */
const SAFETY_MS = 10_000
/** A trigger reads at once and again this much later: Launch Services can lag the activation notification. */
const LAG_MS = 250
const TIMEOUT_MS = 800
const MAX_FAILS = 5

const UNKNOWN: FrontState = { known: false, name: '', bundle: '', aliases: [], miyagi: false, lesson: true }

/** Editors and terminals a lesson happens in: bundle ids and the names they go by (lowercase). */
const LESSON_APPS: { bundles: string[]; names: string[] }[] = [
  {
    bundles: ['com.microsoft.vscode', 'com.microsoft.vscodeinsiders', 'com.vscodium'],
    names: ['code', 'visual studio code', 'vs code', 'vscode', 'code - insiders', 'visual studio code - insiders', 'vscodium']
  },
  { bundles: ['com.todesktop.230313mzl4w4u92'], names: ['cursor'] },
  { bundles: ['com.exafunction.windsurf'], names: ['windsurf'] },
  { bundles: ['com.apple.terminal'], names: ['terminal'] },
  { bundles: ['com.googlecode.iterm2'], names: ['iterm2', 'iterm'] },
  { bundles: ['dev.warp.warp-stable'], names: ['warp'] },
  { bundles: ['com.mitchellh.ghostty'], names: ['ghostty'] }
]
/** miyagi itself: the built app, and Electron in dev. Same list as the engine's (server/workspace/editor.py). */
const MIYAGI = { bundles: ['dev.sandhacks.miyagi', 'com.github.electron'], names: ['miyagi', 'electron', 'miyagi-overlay'] }

const norm = (s: string | undefined | null): string => (s ?? '').trim().toLowerCase()

function aliasesOf(name: string, bundle: string): string[] {
  const n = norm(name)
  const b = norm(bundle)
  const group = [...LESSON_APPS, MIYAGI].find((g) => (b && g.bundles.includes(b)) || (n && g.names.includes(n)))
  return [...new Set([n, ...(group?.names ?? [])].filter(Boolean))]
}

function lsappinfo(args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    try {
      execFile('lsappinfo', args, { timeout: TIMEOUT_MS, encoding: 'utf8', windowsHide: true }, (err, stdout) =>
        err ? reject(err) : resolve(String(stdout ?? ''))
      )
    } catch (err) {
      reject(err)
    }
  })
}

/** The active app from Launch Services, or null when it can't tell. Throws only when lsappinfo can't run. */
async function readFront(): Promise<{ name: string; bundle: string } | null> {
  const asn = (await lsappinfo(['front'])).trim()
  if (!asn) return null
  const info = await lsappinfo(['info', '-only', 'bundleID', '-only', 'name', asn])
  const bundle = /"CFBundleIdentifier"="([^"]*)"/.exec(info)?.[1] ?? ''
  const name = /"LSDisplayName"="([^"]*)"/.exec(info)?.[1] ?? ''
  return bundle || name ? { name, bundle } : null
}

/**
 * When to read the front app: on every trigger (an activation notification, miyagi's own activation changes), and on
 * a fallback clock (safetyMs when triggers come in, pollMs when `subscribe` couldn't). One read at a time: a trigger
 * during a read runs one more right after it. After maxFails failed reads in a row it stops for good (onGiveUp).
 * Returns stop().
 */
export function watchFront(deps: {
  read: () => Promise<void>
  /** Call fn on every front-app change; returns an unsubscribe, or undefined when it can't (then: the poll). */
  subscribe: (fn: () => void) => (() => void) | undefined
  pollMs: number
  safetyMs: number
  /** Each trigger also reads again this much later (Launch Services can lag the notification). 0: no second read. */
  lagMs?: number
  maxFails: number
  onGiveUp: (err: unknown) => void
}): () => void {
  let fails = 0
  let stopped = false
  let reading = false
  let again = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let lagTimer: ReturnType<typeof setTimeout> | undefined
  let unsubscribe: (() => void) | undefined
  let every = deps.pollMs
  const run = async (): Promise<void> => {
    if (stopped) return
    if (reading) {
      again = true
      return
    }
    clearTimeout(timer)
    reading = true
    try {
      await deps.read()
      fails = 0
    } catch (err) {
      fails += 1
      if (fails >= deps.maxFails) {
        stop()
        deps.onGiveUp(err)
      }
    } finally {
      reading = false
    }
    if (stopped) return
    if (again) {
      again = false
      return void run()
    }
    timer = setTimeout(() => void run(), every)
  }
  const stop = (): void => {
    stopped = true
    clearTimeout(timer)
    clearTimeout(lagTimer)
    unsubscribe?.()
    unsubscribe = undefined
  }
  try {
    unsubscribe = deps.subscribe(() => {
      void run()
      if (!deps.lagMs) return
      clearTimeout(lagTimer)
      lagTimer = setTimeout(() => void run(), deps.lagMs)
    })
  } catch {
    unsubscribe = undefined
  }
  if (unsubscribe) every = deps.safetyMs
  void run()
  return stop
}

/** The last app in front that wasn't miyagi (its bundle id), for returnFocus after the launcher hides. */
let lastOther = ''
export const previousApp = (): string | undefined => lastOther || undefined

export default defineMainFeature({
  id: 'front-app',
  setup(ctx) {
    let state: FrontState = UNKNOWN
    ctx.handle('front:state', () => state)
    if (ctx.platform.os !== 'mac' || process.env.MIYAGI_FRONT_APP === '0') return

    /** Apps the engine named this lesson (spotlight.app, setup editorLabel), lowercase. */
    const named = new Set<string>()
    let last: { name: string; bundle: string } | null = null

    const compute = (): FrontState => {
      if (!last) return UNKNOWN
      const aliases = aliasesOf(last.name, last.bundle)
      const focused = (() => {
        try {
          return !!BrowserWindow.getFocusedWindow()
        } catch {
          return false
        }
      })()
      const miyagi = focused || MIYAGI.bundles.includes(norm(last.bundle)) || aliases.some((a) => MIYAGI.names.includes(a))
      const tool = LESSON_APPS.some((g) => g.bundles.includes(norm(last!.bundle)) || g.names.some((n) => aliases.includes(n)))
      const lesson = miyagi || tool || aliases.some((a) => named.has(a))
      return { known: true, name: last.name, bundle: last.bundle, aliases, miyagi, lesson }
    }
    const publish = (): void => {
      const next = compute()
      if (JSON.stringify(next) === JSON.stringify(state)) return
      state = next
      ctx.broadcast('front:app', state)
    }

    ctx.engine.onEvent((e) => {
      const p = (e as { payload?: unknown }).payload as Record<string, unknown> | undefined
      if (e.type === 'lesson.ready' || e.type === 'lesson.ended') named.clear()
      else if (e.type === 'spotlight' && typeof p?.app === 'string' && norm(p.app)) named.add(norm(p.app))
      else if (e.type === 'card') {
        const label = (p?.setup as { editorLabel?: unknown } | undefined)?.editorLabel
        if (typeof label === 'string' && norm(label)) named.add(norm(label))
      } else return
      publish()
    })

    // Test 12 item 8 had a handBack here: when miyagi was the active app with no window holding the keyboard, it
    // re-activated the learner's app (open -b, at most every 2 s). A click on the overlay no longer activates miyagi
    // (every floating surface is a non-activating panel, main/platform.ts focusPanel / panelType), so it isn't needed,
    // and it did harm: while VS Code was still starting, or after an app window closed, it flipped the front app back
    // and forth, and the shortcut bar's away fold (A8) folded and unfolded with it (user report, main 1d453ca0:
    // "switches windows / moves back and forth").

    const read = async (): Promise<void> => {
      const f = await readFront()
      if (f) last = f
      if (f?.bundle && !MIYAGI.bundles.includes(norm(f.bundle)) && !MIYAGI.names.includes(norm(f.name))) lastOther = f.bundle
      publish()
    }
    const stop = watchFront({
      read,
      subscribe: (fn) => {
        const id = systemPreferences.subscribeWorkspaceNotification?.('NSWorkspaceDidActivateApplicationNotification', () => fn())
        if (typeof id !== 'number') return undefined
        // miyagi's own activation changes too (its notification can come before Launch Services has caught up).
        app.on('did-become-active', fn)
        app.on('did-resign-active', fn)
        return () => {
          systemPreferences.unsubscribeWorkspaceNotification?.(id)
          app.off?.('did-become-active', fn)
          app.off?.('did-resign-active', fn)
        }
      },
      pollMs: POLL_MS,
      safetyMs: SAFETY_MS,
      lagMs: LAG_MS,
      maxFails: MAX_FAILS,
      onGiveUp: (err) => {
        last = null
        publish()
        console.warn('[front-app] lsappinfo keeps failing: front app unknown from now on', err)
      }
    })
    // `miyagi` also counts one of our windows holding the keyboard (the launcher, Settings): no read needed for that.
    app.on('browser-window-focus', publish)
    app.on('browser-window-blur', publish)
    app.on('before-quit', stop)
  }
})
