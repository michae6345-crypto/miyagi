/**
 * Main-process feature: autoUpdate (agents/auto-update.md). In-place updates with electron-updater: download in the
 * background, install on quit, "Restart to update" when the learner wants it now, never mid-lesson.
 *
 * OFF, and inert, until both locks in features/updates/auto.ts open:
 *   1. AUTO_UPDATE_ENABLED (build time), or MIYAGI_AUTO_UPDATE=1 in an unpackaged dev run (a packaged build ignores env).
 *   2. canAutoInstall(): a packaged Mac build signed with a Developer ID, in a folder it can replace. Today's builds are
 *      ad-hoc signed (electron-builder.yml mac.identity null + ship-mac.sh codesign -s -), and Squirrel.Mac refuses to
 *      update those, so this answers "off" and the check-only card (features/updates.ts) stays the update path.
 * While off: the four handles answer from memory and userData/auto-update.json (phase "off"); no timer, no network,
 * no child process, no broadcast.
 *
 * electron-updater is NOT a dependency yet (Core request in agents/auto-update.md). It is loaded with a dynamic import
 * of a non-literal name, so this file type-checks and bundles without it; with both locks open and the package
 * missing, the phase is "unavailable" and nothing else happens.
 *
 * When on:
 *   - feed: features/updates/auto.ts feedFor() (generic provider, https://downloads.miyagi.study/<os>, pinned when
 *     packaged); channel stable | beta (userData/auto-update.json, autoUpdate:channel) → latest-mac.yml | beta-mac.yml
 *   - autoDownload, autoInstallOnAppQuit, allowDowngrade false (rollback is a newer build, never a downgrade), all
 *     set by configureUpdater(), which sets allowDowngrade after the channel (the channel setter flips it to true)
 *   - checks 60 s after launch, then every 6 h (CHECK_EVERY_MS, same as the card). These timers start as soon as lock 1
 *     is open, before lock 2 is read: every tick asks miyagi-cloud's minimum-version policy, and also checks the feed
 *     once electron-updater is loaded. So `required` works in phase off (lock 2 closed) and unavailable too.
 *   - miyagi-cloud's minimum-version answer (GET <cloud>/v1/app/version) sets `required`; the renderer turns that into
 *     the one "Update miyagi" card (renderer side not built yet: agents/auto-update.md, Left to build)
 *
 * Handles, registered in every build (flag on or off), so the renderer (Settings "Updates" row) never hits
 * "No handler registered":
 *   autoUpdate:get → AutoView · autoUpdate:check → AutoView (flag off: the view, nothing else) · autoUpdate:restart
 *   (phase ready only; the renderer calls it only with no lesson running; flag off: false) → boolean ·
 *   autoUpdate:channel ('stable' | 'beta') → AutoView (flag off: saved, nothing else).
 * Broadcasts feat:autoUpdate AutoView after every change (flag off: never).
 */
import { execFile } from 'node:child_process'
import { accessSync, constants, existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import {
  appBundleOf,
  autoUpdateRequested,
  canAutoInstall,
  channelFor,
  configureUpdater,
  feedFor,
  parseChannel,
  parseCodesign,
  policyVerdict,
  readVersionPolicy,
  type AutoPhase,
  type AutoView,
  type Signature,
  type UpdateChannel,
  type UpdaterSettings
} from '../../renderer/src/features/updates/auto'
import { CHECK_EVERY_MS, type UpdateOs } from '../../renderer/src/features/updates/manifest'
import { cloudUrl } from './cloud'
import { defineMainFeature } from '../context'

const CHECK_DELAY_MS = 60_000
const POLICY_TIMEOUT_MS = 10_000
const MAX_POLICY_BYTES = 16 * 1024

/** The part of electron-updater's AppUpdater this file uses (so it compiles without the package). */
type UpdaterLike = UpdaterSettings & {
  checkForUpdates(): Promise<unknown>
  quitAndInstall(isSilent?: boolean, isForceRunAfter?: boolean): void
  on(event: string, fn: (...args: unknown[]) => void): unknown
}

/** electron-updater, if it is installed. The name is a variable on purpose: no static import, no type dependency. */
async function loadUpdater(): Promise<UpdaterLike | undefined> {
  const name = 'electron-updater'
  try {
    const mod = (await import(/* @vite-ignore */ name)) as { autoUpdater?: UpdaterLike; default?: { autoUpdater?: UpdaterLike } }
    return mod.autoUpdater ?? mod.default?.autoUpdater
  } catch {
    return undefined
  }
}

/** What codesign says about the running .app (Mac only). Never throws; unreadable = undefined. */
function readSignature(bundle: string): Promise<Signature | undefined> {
  return new Promise((resolve) => {
    execFile('/usr/bin/codesign', ['-dv', '--verbose=2', bundle], { timeout: 10_000 }, (err, stdout, stderr) => {
      // codesign -d prints to stderr and exits 0 for a signed app; an unsigned one exits 1.
      if (err && !stderr) return resolve(undefined)
      resolve(parseCodesign(`${stdout}\n${stderr}`))
    })
  })
}

/** Squirrel.Mac replaces the .app folder: it must not be inside a mounted dmg and its parent must be writable. */
function bundleWritable(bundle: string): boolean {
  if (bundle.startsWith('/Volumes/')) return false
  try {
    accessSync(dirname(bundle), constants.W_OK)
    return true
  } catch {
    return false
  }
}

type Saved = { channel?: UpdateChannel }

function readSaved(file: string): Saved {
  try {
    if (!existsSync(file)) return {}
    const j = JSON.parse(readFileSync(file, 'utf8')) as Record<string, unknown>
    return j.channel === undefined ? {} : { channel: parseChannel(j.channel) }
  } catch {
    return {}
  }
}

function writeSaved(file: string, s: Saved): void {
  try {
    writeFileSync(`${file}.tmp`, JSON.stringify(s), 'utf8')
    renameSync(`${file}.tmp`, file)
  } catch {
    // The choice holds for this run only.
  }
}

const versionOf = (info: unknown): string | undefined => {
  const v = (info as { version?: unknown } | undefined)?.version
  return typeof v === 'string' && v.length < 64 ? v : undefined
}

export default defineMainFeature({
  id: 'autoUpdate',
  setup(ctx) {
    const os: UpdateOs = process.platform === 'win32' ? 'windows' : 'mac'
    const packaged = ctx.app.isPackaged === true
    const current = ctx.app.getVersion()
    const file = join(ctx.app.getPath('userData'), 'auto-update.json')
    let saved = readSaved(file)
    let phase: AutoPhase = 'off'
    let version: string | undefined
    let percent: number | undefined
    let required = false
    let updater: UpdaterLike | undefined

    const channel = (): UpdateChannel => channelFor(current, saved.channel)
    const view = (): AutoView => ({ phase, current, channel: channel(), version, percent, required, os })
    const publish = (): AutoView => {
      const v = view()
      ctx.broadcast('autoUpdate', v)
      return v
    }

    // Lock 1. Off today: the handles below answer without a timer, codesign or network call.
    const enabled = autoUpdateRequested(packaged, process.env)

    ctx.handle('autoUpdate:get', () => view())
    ctx.handle('autoUpdate:check', () => (enabled ? check() : view()))
    ctx.handle('autoUpdate:restart', () => {
      if (!enabled || phase !== 'ready' || !updater) return false
      const u = updater
      // A beat so the renderer's invoke resolves before the windows close.
      setTimeout(() => u.quitAndInstall(false, true), 150)
      return true
    })
    ctx.handle('autoUpdate:channel', (raw) => {
      saved = { ...saved, channel: parseChannel(raw) }
      writeSaved(file, saved)
      if (!enabled) return view()
      if (updater && configure(updater)) void check()
      return publish()
    })

    if (!enabled) return

    async function askPolicy(): Promise<void> {
      const host = cloudUrl()
      if (!host) return
      try {
        const url = `${host}/v1/app/version?os=${os}&channel=${channel()}`
        // Same rule as the update card: nothing about the learner, no install token, no cookies.
        const res = await fetch(url, {
          headers: { Accept: 'application/json', 'User-Agent': `miyagi/${current}` },
          credentials: 'omit',
          signal: AbortSignal.timeout(POLICY_TIMEOUT_MS)
        })
        if (!res.ok) return
        const text = await res.text()
        if (text.length > MAX_POLICY_BYTES) return
        const next = policyVerdict(readVersionPolicy(JSON.parse(text)), current) === 'required'
        if (next !== required) {
          required = next
          if (required) console.warn(`[autoUpdate] miyagi-cloud says ${current} must update`)
          publish()
        }
      } catch {
        // Offline or the endpoint is not there yet: never lock anyone out on a failed check.
      }
    }

    async function check(): Promise<AutoView> {
      void askPolicy()
      if (!updater || phase === 'downloading' || phase === 'ready') return view()
      try {
        await updater.checkForUpdates()
      } catch (err) {
        console.warn('[autoUpdate] check failed:', err instanceof Error ? err.message : 'unknown')
        phase = 'failed'
        publish()
      }
      return view()
    }

    function configure(u: UpdaterLike): boolean {
      const feed = feedFor(os, packaged, process.env)
      if (!feed) return false
      // Sets allowDowngrade = false after the channel (electron-updater's channel setter turns it back on).
      configureUpdater(u, feed, channel())
      return true
    }

    // With lock 1 open the timers run whatever lock 2 says: check() always asks the version policy, and checks the
    // feed only once `updater` is set below. So `required` also reaches phase off (lock 2 closed) and unavailable.
    const first = setTimeout(() => void check(), CHECK_DELAY_MS)
    first.unref?.()
    const tick = setInterval(() => void check(), CHECK_EVERY_MS)
    tick.unref?.()
    ctx.app.on('before-quit', () => {
      clearTimeout(first)
      clearInterval(tick)
    })

    void (async () => {
      // Lock 2: can this build replace itself?
      const bundle = os === 'mac' ? appBundleOf(process.execPath) : undefined
      const signature = bundle ? await readSignature(bundle) : undefined
      const can = canAutoInstall({ os, packaged, signature, bundleWritable: bundle ? bundleWritable(bundle) : undefined })
      if (!can.ok) {
        console.info(`[autoUpdate] off: ${can.why}`)
        return
      }
      const u = await loadUpdater()
      if (!u) {
        console.warn('[autoUpdate] electron-updater is not installed: the update card stays the update path')
        phase = 'unavailable'
        publish()
        return
      }
      if (!configure(u)) {
        console.warn('[autoUpdate] no feed for this run')
        return
      }
      updater = u
      u.on('checking-for-update', () => {
        phase = 'checking'
        publish()
      })
      u.on('update-not-available', () => {
        phase = 'idle'
        publish()
      })
      u.on('update-available', (info) => {
        phase = 'downloading'
        version = versionOf(info)
        percent = 0
        publish()
      })
      u.on('download-progress', (p) => {
        const n = (p as { percent?: unknown } | undefined)?.percent
        percent = typeof n === 'number' && Number.isFinite(n) ? Math.max(0, Math.min(100, Math.round(n))) : percent
        publish()
      })
      u.on('update-downloaded', (info) => {
        // electron-updater checked the sha512 from the feed; Squirrel.Mac checks the signature when it installs.
        phase = 'ready'
        version = versionOf(info) ?? version
        percent = undefined
        console.info(`[autoUpdate] miyagi ${version ?? '?'} is ready; it installs on quit`)
        publish()
      })
      u.on('error', (err) => {
        console.warn('[autoUpdate] error:', err instanceof Error ? err.message : 'unknown')
        phase = phase === 'ready' ? 'ready' : 'failed'
        publish()
      })
      phase = 'idle'
      publish()
    })()
  }
})
