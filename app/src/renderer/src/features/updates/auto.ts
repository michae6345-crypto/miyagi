/**
 * Feature: updates, the in-place (auto) update path. Pure, shared by main (src/main/features/autoUpdate.ts) and tests:
 * no Electron, no DOM, no electron-updater. Design and rollout: app/agents/auto-update.md.
 *
 * OFF today, on purpose. Two locks, both needed before anything runs:
 *   1. AUTO_UPDATE_ENABLED (below, build time) or, in an unpackaged dev run only, env MIYAGI_AUTO_UPDATE=1.
 *      A packaged build ignores the environment (A12, R33: a `launchctl setenv` must not turn it on or off).
 *   2. The build must be able to install an update: on the Mac a Developer ID signature (Squirrel.Mac refuses to swap
 *      an ad-hoc signed app, and every ad-hoc build has a different designated requirement). canAutoInstall().
 * Until both hold, the check-only card (manifest.ts + main/features/updates.ts) stays the only update path.
 *
 *   autoUpdateRequested(packaged, env)   lock 1
 *   parseCodesign(text) / appBundleOf()  what `codesign -dv --verbose=2 <miyagi.app>` says about this build
 *   canAutoInstall(...)                  lock 2, with a plain reason when it says no
 *   parseChannel / updaterChannel        stable | beta → electron-updater's "latest" | "beta" (latest-mac.yml, beta-mac.yml)
 *   feedFor(os, packaged, env)           the generic feed electron-updater reads (pinned in a packaged build)
 *   configureUpdater(u, feed, channel)   feed + channel onto electron-updater, allowDowngrade false set LAST
 *   readVersionPolicy / policyVerdict    miyagi-cloud's minimum-version answer → "required" forces "Update miyagi"
 */
import { compareSemver, findVersion, parseSemver, type UpdateOs } from './manifest'

/**
 * AUTO_UPDATE_ENABLED: in-place updates with electron-updater (download in the background, install on quit). Off until
 * the Developer ID exists AND electron-updater is a dependency (agents/auto-update.md, Core requests). Belongs in
 * common/flags.ts beside the other launch flags once Adrian takes this lane; kept here so this PR stays out of core.
 */
export const AUTO_UPDATE_ENABLED = false

const ON_RE = /^(1|on|true|yes)$/i
const OFF_RE = /^(0|off|false|no)$/i

/** Lock 1. Packaged: the build-time flag only. Dev run: MIYAGI_AUTO_UPDATE=1 turns it on, =0 off, else the flag. */
export function autoUpdateRequested(packaged: boolean, env: { MIYAGI_AUTO_UPDATE?: string }, flag = AUTO_UPDATE_ENABLED): boolean {
  if (packaged) return flag
  const v = env.MIYAGI_AUTO_UPDATE?.trim()
  if (v && ON_RE.test(v)) return true
  if (v && OFF_RE.test(v)) return false
  return flag
}

// ---- signature ----------------------------------------------------------------------------------------------------

export type Signature = {
  /** Signed with a "Developer ID Application" certificate (the only kind Squirrel.Mac will update in place). */
  developerId: boolean
  /** The Apple team id (10 characters), when there is one. */
  teamId?: string
  /** `Signature=adhoc`: what scripts/ship-mac.sh makes today (identity null + codesign -s -). */
  adhoc: boolean
}

const TEAM_RE = /^[A-Z0-9]{10}$/

/** Read `codesign -dv --verbose=2 <app>` output (codesign writes it to stderr). Anything unreadable: not signed. */
export function parseCodesign(text: unknown): Signature {
  if (typeof text !== 'string') return { developerId: false, adhoc: false }
  const lines = text.split(/\r?\n/).map((l) => l.trim())
  const adhoc = lines.some((l) => /^Signature=adhoc$/i.test(l))
  const team = lines.find((l) => l.startsWith('TeamIdentifier='))?.slice('TeamIdentifier='.length)
  const teamId = team && TEAM_RE.test(team) ? team : undefined
  const developerId = !adhoc && !!teamId && lines.some((l) => /^Authority=Developer ID Application: .+\([A-Z0-9]{10}\)$/.test(l))
  return { developerId, teamId, adhoc }
}

/** The .app folder that holds this executable (…/miyagi.app/Contents/MacOS/miyagi → …/miyagi.app), else undefined. */
export function appBundleOf(execPath: string): string | undefined {
  const m = /^(\/.+?\.app)\/Contents\/MacOS\/[^/]+$/.exec(execPath)
  return m ? m[1] : undefined
}

export type InstallCheck = { ok: true } | { ok: false; why: string }

/**
 * Lock 2: can this build install an update in place? Plain reasons, for the log only (the learner never sees them).
 * Windows: the nsis installer updates itself without a signature (SmartScreen still warns), but Windows is not a
 * launch target, so it stays off there until someone decides otherwise (`windows` must be passed true).
 */
export function canAutoInstall(o: {
  os: UpdateOs
  packaged: boolean
  signature?: Signature
  /** Squirrel.Mac cannot replace an app that runs from the dmg or another read-only place. */
  bundleWritable?: boolean
  windows?: boolean
}): InstallCheck {
  if (!o.packaged) return { ok: false, why: 'a dev run is not an installed app' }
  if (o.os === 'windows') return o.windows ? { ok: true } : { ok: false, why: 'Windows auto-update is not turned on' }
  if (!o.signature) return { ok: false, why: 'the signature could not be read' }
  if (o.signature.adhoc) return { ok: false, why: 'ad-hoc signed: macOS refuses to update it in place' }
  if (!o.signature.developerId) return { ok: false, why: 'not signed with a Developer ID' }
  if (o.bundleWritable === false) return { ok: false, why: 'miyagi is not in a folder it can replace (still in the dmg?)' }
  return { ok: true }
}

// ---- channel ------------------------------------------------------------------------------------------------------

export type UpdateChannel = 'stable' | 'beta'

/** A saved or typed channel → stable | beta. Anything else is stable. */
export function parseChannel(raw: unknown): UpdateChannel {
  return typeof raw === 'string' && raw.trim().toLowerCase() === 'beta' ? 'beta' : 'stable'
}

/** electron-updater's channel name: the feed file it reads is `<channel>-mac.yml` ("latest" = stable). */
export const updaterChannel = (c: UpdateChannel): 'latest' | 'beta' => (c === 'beta' ? 'beta' : 'latest')

/**
 * The channel a running version belongs on: a prerelease build (0.3.0-beta.2) stays on beta even with no saved
 * choice, so a beta tester is never silently moved to an older stable.
 */
export function channelFor(current: string, saved: unknown): UpdateChannel {
  if (parseChannel(saved) === 'beta') return 'beta'
  return (parseSemver(current)?.pre.length ?? 0) > 0 ? 'beta' : 'stable'
}

// ---- feed ---------------------------------------------------------------------------------------------------------

/**
 * Where electron-updater reads `latest-mac.yml` / `beta-mac.yml` and the zips they name. A generic (plain https) feed
 * on our own host, so it keeps working if the source repo goes private, and it needs no token in the app (a GitHub
 * provider on a private repo would). The release pipeline uploads there (agents/auto-update.md, Feed).
 */
export const OFFICIAL_FEED_BASE = 'https://downloads.miyagi.study'

export type Feed = { provider: 'generic'; url: string }

/**
 * The feed for this run. Packaged: always OFFICIAL_FEED_BASE/<os> (env ignored, A12). Dev run: MIYAGI_UPDATE_FEED may
 * point at another feed (https, or http on localhost / 127.0.0.1), for testing against a local folder server.
 */
export function feedFor(os: UpdateOs, packaged: boolean, env: { MIYAGI_UPDATE_FEED?: string }): Feed | undefined {
  const official: Feed = { provider: 'generic', url: `${OFFICIAL_FEED_BASE}/${os}` }
  const raw = env.MIYAGI_UPDATE_FEED?.trim()
  if (packaged || !raw) return official
  if (OFF_RE.test(raw)) return undefined
  try {
    const u = new URL(raw)
    const local = u.hostname === '127.0.0.1' || u.hostname === 'localhost'
    if (u.username || u.password || u.search || u.hash) return undefined
    if (u.protocol !== 'https:' && !(u.protocol === 'http:' && local)) return undefined
    return { provider: 'generic', url: `${u.origin}${u.pathname.replace(/\/+$/, '')}` }
  } catch {
    return undefined
  }
}

// ---- updater settings ---------------------------------------------------------------------------------------------

/** The part of electron-updater's AppUpdater that configureUpdater() writes (so this file needs no electron-updater). */
export type UpdaterSettings = {
  autoDownload: boolean
  autoInstallOnAppQuit: boolean
  allowDowngrade: boolean
  allowPrerelease: boolean
  channel: string | null
  logger: unknown
  setFeedURL(options: Feed & { channel?: string }): void
}

/**
 * Point electron-updater at the feed and channel. Called at start and again on every channel switch.
 *
 * ORDER MATTERS: electron-updater's `channel` setter also sets `allowDowngrade = true` (its docs: set allowDowngrade
 * explicitly after the channel). So the channel and the feed go first and `allowDowngrade = false` goes LAST. Set it
 * any earlier and every build, stable included, would accept a downgrade: a beta tester who picks Stable would be
 * moved back to an older stable build, and rollback (agents/auto-update.md) would stop being roll-forward only.
 * test/autoUpdate.test.ts pins this with a fake updater whose `channel` setter flips allowDowngrade the same way.
 */
export function configureUpdater(u: UpdaterSettings, feed: Feed, channel: UpdateChannel): void {
  const name = updaterChannel(channel)
  u.logger = null
  u.autoDownload = true
  u.autoInstallOnAppQuit = true
  u.allowPrerelease = channel === 'beta'
  u.channel = name
  u.setFeedURL({ ...feed, channel: name })
  // Last, after the channel setter. Rollback is a newer build carrying the old code, never a downgrade.
  u.allowDowngrade = false
}

// ---- minimum version (miyagi-cloud) -------------------------------------------------------------------------------

/**
 * miyagi-cloud's answer to GET <cloud>/v1/app/version?os=mac&channel=stable (agents/auto-update.md, Core requests):
 *   { "min": "0.2.0", "blocked": ["0.2.3"], "latest": "0.2.4" }
 * min      versions below it must update before the next lesson (a broken engine contract, a security fix)
 * blocked  exact versions pulled after release (a bad build): treated like "below min"
 * latest   informational only; the feed, not this, decides what is downloaded
 */
export type VersionPolicy = { min?: string; blocked: string[]; latest?: string }

const MAX_BLOCKED = 50

/** A cloud answer → VersionPolicy. Anything malformed is dropped field by field; no answer = no policy. */
export function readVersionPolicy(json: unknown): VersionPolicy | undefined {
  if (!json || typeof json !== 'object' || Array.isArray(json)) return undefined
  const j = json as Record<string, unknown>
  const exact = (v: unknown): string | undefined => (typeof v === 'string' && v.length < 64 && parseSemver(v) ? findVersion(v) : undefined)
  const blocked = Array.isArray(j.blocked)
    ? j.blocked.slice(0, MAX_BLOCKED).map(exact).filter((v): v is string => !!v)
    : []
  return { min: exact(j.min), blocked, latest: exact(j.latest) }
}

export type PolicyVerdict = 'ok' | 'required'

/**
 * "required": this version may not start a lesson; the island shows one card, "Update miyagi", until it is updated.
 * An unreadable current version is never locked out. main/features/autoUpdate.ts asks only when lock 1 is open.
 */
export function policyVerdict(policy: VersionPolicy | undefined, current: string): PolicyVerdict {
  const cur = findVersion(current)
  if (!policy || !cur) return 'ok'
  if (policy.blocked.includes(cur)) return 'required'
  if (policy.min && compareSemver(cur, policy.min) < 0) return 'required'
  return 'ok'
}

// ---- view ---------------------------------------------------------------------------------------------------------

/**
 * off          lock 1 or 2 is closed (today, always); the check-only card is the update path
 * unavailable  both locks open but electron-updater is not installed or failed to load
 * idle | checking | downloading | ready | failed   electron-updater's own states
 * ready        downloaded and verified; installs on quit, or now with "Restart to update"
 */
export type AutoPhase = 'off' | 'unavailable' | 'idle' | 'checking' | 'downloading' | 'ready' | 'failed'

export type AutoView = {
  phase: AutoPhase
  current: string
  channel: UpdateChannel
  /** The version being downloaded or ready to install. */
  version?: string
  /** 0..100 while downloading. */
  percent?: number
  /** miyagi-cloud says this version must update (minimum version or a pulled build). */
  required: boolean
  os: UpdateOs
}
