/**
 * Feature: updates. The pure part, shared by main (src/main/features/updates.ts) and the renderer: no Electron, no DOM.
 *
 *   updateSource(env, os)   where to look: MIYAGI_UPDATE_URL (a manifest or a release JSON), else the GitHub Releases
 *                           API for MIYAGI_RELEASE_REPO (default DEFAULT_RELEASE_REPO, the repo ship-mac.sh publishes to)
 *   sourceForRun(packaged, env, os)   a packaged build: always the official release source, env ignored (A12, R33);
 *                           a dev run: updateSource(env), only when MIYAGI_UPDATE_URL is set
 *   officialInstaller(url, os)        the only installer URLs the card may offer (R26)
 *   readRelease(json, ...)  a manifest, a per-platform manifest, or a GitHub release object → Release (or undefined)
 *   compareSemver(a, b)     semver order (prerelease < release); isNewer(latest, current)
 *
 * The manifest (MIYAGI_UPDATE_URL, any https host):
 *   { "version": "0.2.0", "notes": ["Lessons open faster."],
 *     "url": "https://github.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg", "sha256": "<64 hex>" }
 * or per platform: { "mac": { ...same }, "windows": { ... } }. "dmg" is accepted for "url".
 *
 * Either shape: the installer URL must be an official release asset (officialInstaller, R26), or readRelease answers
 * undefined and the card shows nothing.
 *
 * A GitHub release (GET /repos/<repo>/releases/tags/mac, the rolling "mac" release ship-mac.sh uploads to): the version
 * is the first semver in tag_name, then name ("miyagi 0.2.0"), then a "Version: 0.2.0" body line, then the installer's
 * file name. The installer is the .dmg asset (.exe on Windows), the one naming this arch when there are several. The
 * sha256 is the asset's `digest` ("sha256:<hex>"), else a "sha256: <hex>" body line. Notes are the body's plain lines.
 */

export type UpdateOs = 'mac' | 'windows'

export type Release = {
  version: string
  /** Up to MAX_NOTES short plain lines ("What's new"). */
  notes: string[]
  /** The installer (.dmg / .exe): opened in the browser, never downloaded or run by the app. */
  url: string
  sha256?: string
  /** Bytes, when the source says. */
  size?: number
  /** The installer's file name (Miyagi-Mac.dmg), for the install steps. */
  file?: string
  prerelease?: boolean
}

export type UpdatePhase = 'off' | 'idle' | 'checking' | 'current' | 'available' | 'failed'

/** What a renderer sees (updates:get, updates:check, feat:updates). Never a raw response. */
export type UpdateView = {
  phase: UpdatePhase
  /** This app's version (app.getVersion()). */
  current: string
  /** The newer release once a check found one (kept while a later check runs). */
  latest?: { version: string; notes: string[]; host: string; size?: number; file?: string; sha256?: string }
  /** "Later": the card stays away until this time (ms). The Settings row still shows the update. */
  snoozedUntil?: number
  /** Download was pressed for latest.version (the install steps). */
  opened?: boolean
  /** The last finished check (ms). */
  checkedAt?: number
  os: UpdateOs
}

/** The repo ship-mac.sh publishes to (MIYAGI_RELEASE_REPO overrides both). Its "mac" release holds Miyagi-Mac.dmg. */
export const DEFAULT_RELEASE_REPO = 'adrian-erlikhman/miyagi'

/**
 * The ONLY installers the card may offer (R26 step 2, A13): an asset of the official release repo, at
 * https://github.com/adrian-erlikhman/miyagi/releases/download/<tag>/<asset>, with the asset name each platform's
 * build publishes (ship-mac.sh: Miyagi-Mac.dmg; electron-builder.yml win.artifactName: Miyagi-Windows-Setup.exe).
 * Pinned on purpose: neither MIYAGI_RELEASE_REPO nor MIYAGI_UPDATE_URL can widen it (in a dev run they change where the
 * metadata is read, never what may be opened; a packaged build ignores them, sourceForRun). Add a name here only when a
 * build really publishes it.
 */
export const OFFICIAL_RELEASE_REPO = 'adrian-erlikhman/miyagi'
export const OFFICIAL_ASSETS: Readonly<Record<UpdateOs, readonly string[]>> = { mac: ['Miyagi-Mac.dmg'], windows: ['Miyagi-Windows-Setup.exe'] }
const OFFICIAL_PREFIX = `https://github.com/${OFFICIAL_RELEASE_REPO}/releases/download/`
/** A release tag: the rolling "mac" / "windows" releases, or a versioned vX.Y.Z (R08 step 2). No "/", "%", "?" or "#". */
const TAG_RE = /^(?:mac|windows|v\d{1,6}\.\d{1,6}\.\d{1,6}(?:-[0-9A-Za-z.-]{1,64})?)$/

/**
 * The tag and asset of an official installer URL for this platform, or undefined for anything else: another repo,
 * host, scheme, port, user, path, query or fragment, an encoded character, another file name, or another platform's
 * installer. An exact string match (no normalizing), then the URL parser must print it back unchanged.
 */
export function officialInstaller(raw: unknown, os: UpdateOs): { tag: string; asset: string } | undefined {
  if (typeof raw !== 'string' || raw.length > 512 || !raw.startsWith(OFFICIAL_PREFIX)) return undefined
  const [tag = '', asset = '', ...rest] = raw.slice(OFFICIAL_PREFIX.length).split('/')
  if (rest.length || !TAG_RE.test(tag) || !OFFICIAL_ASSETS[os].includes(asset)) return undefined
  try {
    if (new URL(raw).href !== raw) return undefined
  } catch {
    return undefined
  }
  return { tag, asset }
}

export const isOfficialInstaller = (raw: unknown, os: UpdateOs): boolean => !!officialInstaller(raw, os)

export const CHECK_EVERY_MS = 6 * 60 * 60_000
export const SNOOZE_MS = 24 * 60 * 60_000
export const MAX_NOTES = 6
const MAX_NOTE = 140

const OFF_RE = /^(off|0|false|no)$/i
const REPO_RE = /^[A-Za-z0-9_.-]{1,100}\/[A-Za-z0-9_.-]{1,100}$/
const SEMVER_RE = /v?(\d{1,6})\.(\d{1,6})\.(\d{1,6})(?:-([0-9A-Za-z.-]{1,64}))?(?:\+[0-9A-Za-z.-]{1,64})?/
const HEX64 = /^[a-f0-9]{64}$/

export type Source = { url: string; kind: 'manifest' | 'github' }

/**
 * Where to look, or undefined (off). MIYAGI_UPDATE_URL=off turns checks off; a URL there must be https (http only for
 * localhost / 127.0.0.1, for a dev manifest). Otherwise the GitHub Releases API for MIYAGI_RELEASE_REPO.
 */
export function updateSource(env: { MIYAGI_UPDATE_URL?: string; MIYAGI_RELEASE_REPO?: string }, os: UpdateOs): Source | undefined {
  const raw = env.MIYAGI_UPDATE_URL?.trim()
  if (raw) {
    if (OFF_RE.test(raw)) return undefined
    try {
      const u = new URL(raw)
      const local = u.hostname === '127.0.0.1' || u.hostname === 'localhost'
      if (u.username || u.password) return undefined
      if (u.protocol !== 'https:' && !(u.protocol === 'http:' && local)) return undefined
      return { url: u.href, kind: 'manifest' }
    } catch {
      return undefined
    }
  }
  const repo = env.MIYAGI_RELEASE_REPO?.trim()
  const r = repo && REPO_RE.test(repo) && !repo.includes('..') ? repo : DEFAULT_RELEASE_REPO
  return { url: `https://api.github.com/repos/${r}/releases/tags/${os}`, kind: 'github' }
}

/**
 * Where THIS run looks (main/features/updates.ts). A packaged build ignores the environment (A12, R33): whoever can
 * set the app's env (launchctl setenv, a wrapper) could otherwise point the check at their own manifest or switch it
 * off, so it always reads the official release source, OFFICIAL_RELEASE_REPO's "mac" / "windows" release. Dev runs
 * (not packaged) honor MIYAGI_UPDATE_URL and MIYAGI_RELEASE_REPO, and look only when MIYAGI_UPDATE_URL is set.
 */
export function sourceForRun(packaged: boolean, env: { MIYAGI_UPDATE_URL?: string; MIYAGI_RELEASE_REPO?: string }, os: UpdateOs): Source | undefined {
  if (packaged) return { url: `https://api.github.com/repos/${OFFICIAL_RELEASE_REPO}/releases/tags/${os}`, kind: 'github' }
  return env.MIYAGI_UPDATE_URL?.trim() ? updateSource(env, os) : undefined
}

// ---- semver -------------------------------------------------------------------------------------------------------

type Semver = { major: number; minor: number; patch: number; pre: string[] }

export function parseSemver(raw: unknown): Semver | undefined {
  if (typeof raw !== 'string') return undefined
  const m = SEMVER_RE.exec(raw.trim())
  if (!m) return undefined
  return { major: Number(m[1]), minor: Number(m[2]), patch: Number(m[3]), pre: m[4] ? m[4].split('.') : [] }
}

/** The first semver in a string, normalized ("miyagi v0.2.0 (arm64)" → "0.2.0"). */
export function findVersion(raw: unknown): string | undefined {
  const s = parseSemver(raw)
  if (!s) return undefined
  return `${s.major}.${s.minor}.${s.patch}${s.pre.length ? `-${s.pre.join('.')}` : ''}`
}

/** <0 when a is older than b, 0 equal, >0 newer. Unparseable sorts lowest. */
export function compareSemver(a: string, b: string): number {
  const x = parseSemver(a)
  const y = parseSemver(b)
  if (!x || !y) return x ? 1 : y ? -1 : 0
  for (const k of ['major', 'minor', 'patch'] as const) if (x[k] !== y[k]) return x[k] - y[k]
  // A prerelease is older than its release (0.2.0-beta.1 < 0.2.0).
  if (!x.pre.length || !y.pre.length) return x.pre.length ? -1 : y.pre.length ? 1 : 0
  for (let i = 0; i < Math.max(x.pre.length, y.pre.length); i++) {
    const p = x.pre[i]
    const q = y.pre[i]
    if (p === undefined) return -1
    if (q === undefined) return 1
    const pn = /^\d+$/.test(p)
    const qn = /^\d+$/.test(q)
    if (pn && qn && Number(p) !== Number(q)) return Number(p) - Number(q)
    if (pn !== qn) return pn ? -1 : 1
    if (p !== q) return p < q ? -1 : 1
  }
  return 0
}

/** Offer `latest` over `current`? Newer only; a prerelease only to someone already on a prerelease. */
export function isNewer(latest: Release, current: string): boolean {
  if (!parseSemver(current) || !parseSemver(latest.version)) return false
  const onPre = (parseSemver(current)?.pre.length ?? 0) > 0
  if ((latest.prerelease || (parseSemver(latest.version)?.pre.length ?? 0) > 0) && !onPre) return false
  return compareSemver(latest.version, current) > 0
}

// ---- notes --------------------------------------------------------------------------------------------------------

/** Release notes as a few plain lines: no headings, no markdown marks, links as their text, no em dashes, no version or hash lines. */
export function cleanNotes(raw: unknown): string[] {
  const lines = Array.isArray(raw) ? raw.filter((l): l is string => typeof l === 'string') : typeof raw === 'string' ? raw.split(/\r?\n/) : []
  const out: string[] = []
  for (const line of lines) {
    // A heading ("## What's new") titles the notes; the card has its own.
    if (/^\s{0,3}#{1,6}\s/.test(line)) continue
    let t = line
      // eslint-disable-next-line no-control-regex
      .replace(/[\u0000-\u001f\u007f]/g, ' ')
      .replace(/!\[[^\]]*]\([^)]*\)/g, '')
      .replace(/\[([^\]]*)]\([^)]*\)/g, '$1')
      .replace(/<[^>]{0,200}>/g, '')
      .replace(/^\s{0,6}([-*+]|\d{1,2}[.)])\s+/, '')
      .replace(/[*_`]{1,3}/g, '')
      .replace(/\s*[\u2014\u2013]\s*/g, ', ')
      .replace(/\s+/g, ' ')
      .trim()
    if (!t || /^(version|sha-?256)\s*[:=]/i.test(t) || /^https?:\/\//i.test(t) || /^[-=_*\s]+$/.test(t)) continue
    if (t.length > MAX_NOTE) t = `${t.slice(0, MAX_NOTE - 1).trimEnd()}…`
    out.push(t)
    if (out.length >= MAX_NOTES) break
  }
  return out
}

// ---- reading a release --------------------------------------------------------------------------------------------

const obj = (v: unknown): Record<string, unknown> | undefined => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : undefined)
const str = (v: unknown): string | undefined => (typeof v === 'string' && v.length <= 4096 ? v : undefined)

function sha(raw: unknown): string | undefined {
  const s = str(raw)?.trim().toLowerCase().replace(/^sha256:/, '')
  return s && HEX64.test(s) ? s : undefined
}

const EXT: Record<UpdateOs, RegExp> = { mac: /\.dmg$/i, windows: /\.exe$/i }

/** Our own manifest (flat, or keyed by platform). */
function fromManifest(j: Record<string, unknown>, os: UpdateOs): Release | undefined {
  const m = obj(j[os]) ?? j
  const version = findVersion(str(m.version))
  const url = str(m.url) ?? str(m.dmg) ?? str(m.download)
  // Whatever host serves the manifest, the installer is an official release asset or there is no offer (R26).
  if (!version || !url || !isOfficialInstaller(url, os)) return undefined
  const size = typeof m.size === 'number' && Number.isFinite(m.size) && m.size > 0 ? Math.round(m.size) : undefined
  return {
    version,
    notes: cleanNotes(m.notes),
    url,
    sha256: sha(m.sha256),
    size,
    // The pinned asset's own name (the install steps show it), never free text from the manifest.
    file: officialInstaller(url, os)?.asset,
    prerelease: m.prerelease === true
  }
}

/** A GitHub release object (the Releases API). */
function fromGithub(j: Record<string, unknown>, os: UpdateOs, arch: string): Release | undefined {
  if (j.draft === true) return undefined
  const assets = (Array.isArray(j.assets) ? j.assets : []).map(obj).filter((a): a is Record<string, unknown> => !!a)
  const tag = str(j.tag_name)
  // Only an official asset of THIS release (R26): its name on the list, its URL the pinned one for this release's tag
  // and that name, and fully uploaded (an asset mid-upload, state "starter"/"open", is not a download yet).
  const installers = assets.filter((a) => {
    const name = str(a.name) ?? ''
    const at = officialInstaller(str(a.browser_download_url), os)
    return EXT[os].test(name) && !!at && at.asset === name && at.tag === tag && (a.state === undefined || a.state === 'uploaded')
  })
  if (!installers.length) return undefined
  const archRe = arch === 'arm64' ? /arm64|aarch64|apple/i : /x64|x86_64|intel|amd64/i
  const otherRe = arch === 'arm64' ? /x64|x86_64|intel|amd64/i : /arm64|aarch64|apple/i
  const asset =
    installers.find((a) => archRe.test(str(a.name) ?? '')) ?? installers.find((a) => !otherRe.test(str(a.name) ?? '')) ?? installers[0]
  const body = str(j.body) ?? ''
  const bodyVersion = /^\s*version\s*[:=]\s*(\S+)/im.exec(body)?.[1]
  const version = findVersion(str(j.tag_name)) ?? findVersion(str(j.name)) ?? findVersion(bodyVersion) ?? findVersion(str(asset.name))
  if (!version) return undefined
  const bodySha = /sha-?256\s*[:=]\s*([a-f0-9]{64})/i.exec(body)?.[1]
  const size = typeof asset.size === 'number' && asset.size > 0 ? asset.size : undefined
  return {
    version,
    notes: cleanNotes(body),
    url: str(asset.browser_download_url)!,
    sha256: sha(asset.digest) ?? sha(bodySha),
    size,
    file: str(asset.name),
    prerelease: j.prerelease === true
  }
}

/** Any accepted shape → a Release, or undefined (unknown shape, no version, no installer). */
export function readRelease(json: unknown, os: UpdateOs, arch: string): Release | undefined {
  const j = obj(json)
  if (!j) return undefined
  if (Array.isArray(j.assets)) return fromGithub(j, os, arch)
  return fromManifest(j, os)
}

/** "182 MB" (decimal, like Finder). */
export function formatSize(bytes?: number): string | undefined {
  if (!bytes || bytes <= 0) return undefined
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  return `${Math.max(1, Math.round(bytes / 1e6))} MB`
}
