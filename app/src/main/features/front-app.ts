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
 * Polled every POLL_MS, one read at a time, TIMEOUT_MS each. A missing or failing lsappinfo never throws: after
 * MAX_FAILS failures in a row the poll stops and the front app stays unknown, which the renderer treats as the
 * lesson's (nothing folds, nothing hides). Windows: not read (unknown). MIYAGI_FRONT_APP=0 turns it off.
 *
 * The lesson's apps: the editors and terminals below, miyagi itself (its bundle, or one of its windows has the
 * keyboard: the launcher is a non-activating panel, so Launch Services still names the editor), and every app the
 * engine named this lesson (spotlight.app, the setup card's editorLabel).
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac.
 */
import { execFile } from 'node:child_process'
import { app, BrowserWindow } from 'electron'
import { defineMainFeature } from '../context'
import { gateIsOpen } from '../gate'

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

const POLL_MS = 1000
const TIMEOUT_MS = 800
const MAX_FAILS = 5
/** Test 12 item 8: hand activation back to the learner's app at most this often (handBack below). */
const HAND_BACK_MS = 2000

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

    // Test 12 item 8: a click on the overlay (a card, the pill) can make miyagi the active app, even as an accessory
    // app with non-focusable windows. VS Code is then inactive, and macOS spends the learner's next click there
    // (Explorer at 08:55:40) on activating it. When miyagi is in front but none of its windows has the keyboard
    // (the launcher and settings do when they're open), hand activation back to the app the learner was in, so
    // that first click lands. At most once every HAND_BACK_MS. MIYAGI_HAND_BACK=0 turns it off.
    let handedAt = 0
    // Launch gate (main/gate.ts): before the login and setup are through, only the home window is up, and miyagi in
    // front is the learner signing in. Never take that away from them.
    const handBack = (): void => {
      if (!gateIsOpen() || process.env.MIYAGI_HAND_BACK === '0' || !lastOther || Date.now() - handedAt < HAND_BACK_MS) return
      try {
        if (BrowserWindow.getFocusedWindow()) return
        if (!ctx.launcher.isDestroyed() && ctx.launcher.isVisible()) return
      } catch {
        return
      }
      handedAt = Date.now()
      execFile('open', ['-b', lastOther], (err) => {
        if (err) console.warn('[front-app] could not hand focus back to', lastOther, err.message)
      })
      if (!ctx.overlay.isDestroyed()) ctx.raise(ctx.overlay)
    }

    let fails = 0
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const tick = async (): Promise<void> => {
      try {
        const f = await readFront()
        fails = 0
        if (f) last = f
        if (f?.bundle && !MIYAGI.bundles.includes(norm(f.bundle)) && !MIYAGI.names.includes(norm(f.name))) lastOther = f.bundle
        else if (f) handBack()
        publish()
      } catch (err) {
        fails += 1
        if (fails >= MAX_FAILS) {
          stopped = true
          last = null
          publish()
          console.warn('[front-app] lsappinfo keeps failing: front app unknown from now on', err)
        }
      } finally {
        if (!stopped) timer = setTimeout(() => void tick(), POLL_MS)
      }
    }
    void tick()
    app.on('before-quit', () => {
      stopped = true
      clearTimeout(timer)
    })
  }
})
