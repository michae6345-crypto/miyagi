/**
 * Main-process feature: updates (agents/updates.md). Updates people never have to think about, without auto-install:
 * the app is ad-hoc signed, so electron-updater cannot swap it on the Mac. We only look, then offer the installer.
 *
 *   1. Where: sourceForRun() (features/updates/manifest.ts). A packaged app: always the GitHub Releases API for the
 *      official repo (adrian-erlikhman/miyagi, the repo ship-mac.sh publishes to), tag "mac" / "windows"; the
 *      environment is ignored (A12, R33: a launchctl setenv must not point the check elsewhere or switch it off).
 *      A dev run: MIYAGI_UPDATE_URL (a manifest, https; http only for localhost) or the Releases API for
 *      MIYAGI_RELEASE_REPO; MIYAGI_UPDATE_URL=off = never look.
 *   2. When: CHECK_DELAY_MS after launch (never competes with the engine start), then every 6 h, and on wake when the
 *      last check is older than that. Only in a packaged app, unless MIYAGI_UPDATE_URL is set (dev manifests).
 *   3. What: a GET with no cookies and a generic User-Agent; nothing about the learner is sent. The answer is read with
 *      readRelease(), compared with app.getVersion() (semver), and kept only if its installer URL is an official
 *      release asset (R26): exactly https://github.com/adrian-erlikhman/miyagi/releases/download/<tag>/<asset> with
 *      this platform's asset name (manifest.ts officialInstaller). Anything else: no offer, no card. In a dev run a
 *      MIYAGI_RELEASE_REPO or MIYAGI_UPDATE_URL override changes where the metadata is read, never what may be opened.
 *      The SHA-256 is not verified against the file yet (TODO(R26) at updates:download).
 *   4. Offer: the renderer's card (features/updates) waits until no lesson runs. Download opens the installer URL that
 *      main holds (the renderer never passes a URL). Later snoozes the card for 24 h (userData/updates.json).
 *
 * Handles (renderer → main, all return UpdateView):
 *   updates:get                   the current view (no network)
 *   updates:check                 check now (Settings "Check for updates"); an update found here clears the snooze
 *   updates:download              open the installer in the browser; marks it opened (the card shows install steps)
 *   updates:later                 snooze the card for SNOOZE_MS
 *   updates:quit                  quit miyagi (the install steps' "Quit miyagi"); returns true
 * Broadcasts feat:updates UpdateView after every change.
 */
import { powerMonitor } from 'electron'
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  CHECK_EVERY_MS,
  isNewer,
  isOfficialInstaller,
  OFFICIAL_RELEASE_REPO,
  readRelease,
  SNOOZE_MS,
  sourceForRun,
  type Release,
  type UpdateOs,
  type UpdatePhase,
  type UpdateView
} from '../../renderer/src/features/updates/manifest'
import { isAllowedUrl, safeOpenExternal } from '../safeOpen'
import { defineMainFeature } from '../context'

const CHECK_DELAY_MS = 45_000
/** A failed check tries again sooner than the 6 h tick, once per this long. */
const RETRY_MS = 60 * 60_000
const TIMEOUT_MS = 15_000
const MAX_BYTES = 512 * 1024

type Saved = { snoozedUntil?: number; openedVersion?: string; checkedAt?: number }

function readSaved(file: string): Saved {
  try {
    if (!existsSync(file)) return {}
    const j = JSON.parse(readFileSync(file, 'utf8')) as Record<string, unknown>
    const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : undefined)
    return {
      snoozedUntil: num(j.snoozedUntil),
      openedVersion: typeof j.openedVersion === 'string' && j.openedVersion.length < 64 ? j.openedVersion : undefined,
      checkedAt: num(j.checkedAt)
    }
  } catch {
    return {}
  }
}

function writeSaved(file: string, s: Saved): void {
  try {
    const tmp = `${file}.tmp`
    writeFileSync(tmp, JSON.stringify(s), 'utf8')
    renameSync(tmp, file)
  } catch {
    // Not worth a card: the snooze is for this run only.
  }
}

const hostOf = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

export default defineMainFeature({
  id: 'updates',
  setup(ctx) {
    const os: UpdateOs = process.platform === 'win32' ? 'windows' : 'mac'
    // Packaged: always the official release source; MIYAGI_UPDATE_URL / MIYAGI_RELEASE_REPO are ignored (A12, R33: a
    // launchctl setenv must not steer the check). Dev: only with MIYAGI_UPDATE_URL set, and then as it says.
    const source = sourceForRun(ctx.app.isPackaged === true, process.env, os)
    const current = ctx.app.getVersion()
    const file = join(ctx.app.getPath('userData'), 'updates.json')
    /** Openable: an official release asset for this platform (R26) AND on safeOpen's allowlist (it opens it). */
    const trusted = (url: string): boolean => isOfficialInstaller(url, os) && isAllowedUrl(url)
    let saved = readSaved(file)
    let phase: UpdatePhase = source ? 'idle' : 'off'
    let latest: Release | undefined
    let inFlight: Promise<UpdateView> | undefined
    let retryTimer: ReturnType<typeof setTimeout> | undefined

    const view = (): UpdateView => ({
      phase,
      current,
      // Kept through a re-check ('checking'), so the card does not blink every 6 h.
      latest: latest
        ? { version: latest.version, notes: latest.notes, host: hostOf(latest.url), size: latest.size, file: latest.file, sha256: latest.sha256 }
        : undefined,
      snoozedUntil: saved.snoozedUntil && saved.snoozedUntil > Date.now() ? saved.snoozedUntil : undefined,
      opened: !!latest && saved.openedVersion === latest.version,
      checkedAt: saved.checkedAt,
      os
    })
    const publish = (): UpdateView => {
      const v = view()
      ctx.broadcast('updates', v)
      return v
    }
    const save = (patch: Saved): void => {
      saved = { ...saved, ...patch }
      writeSaved(file, saved)
    }

    async function fetchRelease(): Promise<Release | undefined> {
      if (!source) return undefined
      const res = await fetch(source.url, {
        headers: {
          Accept: source.kind === 'github' ? 'application/vnd.github+json' : 'application/json',
          // Generic on purpose: no install id, no user, nothing but the app name and version.
          'User-Agent': `miyagi/${current}`
        },
        credentials: 'omit',
        redirect: 'follow',
        signal: AbortSignal.timeout(TIMEOUT_MS)
      })
      if (!res.ok) throw new Error(`update check: HTTP ${res.status}`)
      const text = await res.text()
      if (text.length > MAX_BYTES) throw new Error('update check: answer too large')
      const rel = readRelease(JSON.parse(text), os, process.arch)
      // Only an official release asset counts (R26: readRelease already pins it; checked again here, where it is kept).
      // Anything else is no offer at all: the card shows nothing.
      if (rel && !trusted(rel.url)) {
        console.warn(`[updates] ignored a release whose installer is not an official ${OFFICIAL_RELEASE_REPO} asset`)
        return undefined
      }
      return rel
    }

    function check(manual: boolean): Promise<UpdateView> {
      if (!source) return Promise.resolve(view())
      if (inFlight) return inFlight
      clearTimeout(retryTimer)
      phase = 'checking'
      publish()
      inFlight = fetchRelease()
        .then((rel) => {
          const found = rel && isNewer(rel, current) ? rel : undefined
          if (found && latest?.version !== found.version) console.info(`[updates] miyagi ${found.version} is available (this is ${current})`)
          latest = found
          phase = found ? 'available' : 'current'
          // Asking by hand means "show me": drop a Later.
          save({ checkedAt: Date.now(), ...(manual && found ? { snoozedUntil: undefined } : {}) })
        })
        .catch((err) => {
          // Offline, rate-limited, a release being uploaded: say nothing, try again later. Keep an offer already found.
          console.warn('[updates] check failed:', err instanceof Error ? err.message : 'unknown')
          phase = latest ? 'available' : 'failed'
          retryTimer = setTimeout(() => void check(false), RETRY_MS)
          retryTimer.unref?.()
        })
        .then(() => {
          inFlight = undefined
          return publish()
        })
      return inFlight
    }

    ctx.handle('updates:get', () => view())
    ctx.handle('updates:check', () => check(true))
    ctx.handle('updates:download', async () => {
      if (phase !== 'available' || !latest) return view()
      // The pin once more at the moment of opening: never anything but an official asset, even if a later edit lets
      // something else into `latest`. Refused: the offer goes away (nothing to show).
      if (!trusted(latest.url)) {
        console.warn('[updates] refused to open an installer that is not an official release asset')
        latest = undefined
        phase = 'current'
        return publish()
      }
      // TODO(R26): the SHA-256 is not verified against the installer. latest.sha256 (the asset's `digest`, or a
      // "sha256:" line) is read, but the BROWSER downloads the file, so main never holds the bytes to hash, and the
      // digest comes from the same GitHub answer as the URL (a hijacked release would change both). R26 step 4 is the
      // fix: a signed miyagi.study/update/latest.json (Ed25519, public key built into the app) carrying version, url
      // and sha256, then an in-app download that hashes the file and opens it only on a match.
      const ok = await safeOpenExternal(latest.url)
      if (ok) save({ openedVersion: latest.version })
      return publish()
    })
    ctx.handle('updates:later', () => {
      save({ snoozedUntil: Date.now() + SNOOZE_MS })
      return publish()
    })
    ctx.handle('updates:quit', () => {
      // A beat so the renderer's invoke resolves before the windows close.
      setTimeout(() => ctx.app.quit(), 150)
      return true
    })

    if (!source) return
    const first = setTimeout(() => void check(false), CHECK_DELAY_MS)
    first.unref?.()
    const tick = setInterval(() => void check(false), CHECK_EVERY_MS)
    tick.unref?.()
    ctx.app.whenReady().then(() => {
      powerMonitor.on('resume', () => {
        if (!saved.checkedAt || Date.now() - saved.checkedAt >= CHECK_EVERY_MS) setTimeout(() => void check(false), CHECK_DELAY_MS)
      })
    })
    ctx.app.on('before-quit', () => {
      clearTimeout(first)
      clearTimeout(retryTimer)
      clearInterval(tick)
    })
  }
})
