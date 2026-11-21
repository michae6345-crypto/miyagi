/**
 * Core: the app starts the engine on this Mac when nobody else has (Michael's docs/DISTRIBUTION.md, app ask 1,
 * and "C", the self-contained app). One download: open miyagi and it works, offline, in seconds.
 *
 *   1. Only on macOS (the engine reads the screen with Vision / ScreenCaptureKit), only in a built app or with
 *      MIYAGI_AUTOSTART=1, never with DEMO=1, and only when ENGINE_URL is unset or points at this Mac.
 *   2. Something already answers on 127.0.0.1:<port> and it isn't ours (step 7). `npm run dev` or engine mode dev
 *      → use it: an engine started in Terminal stays the user's. The installed app (packaged, engine mode bundled)
 *      never adopts it (lane engine-isolation, app/agents/engine-isolation.md): a dev engine or a dev app's engine
 *      would hand the installed app its lesson, its save and its screen. It says "Another miyagi engine is running.",
 *      writes the holder (lsof pid and command) to engine.log, never stops it, and starts its own once the port is free.
 *   3. ~/miyagi/engine/bin/miyagi-engine exists with no BUNDLED marker (the user ran Michael's one-liner) → start it.
 *      The app never replaces an engine the user installed.
 *   4. A12 (DISTRIBUTION-PLAN.md section 2): this app carries a standalone Python with the engine's packages
 *      (Resources/engine/python + src/, put there by scripts/bundle-engine.mjs) → copy the source to
 *      ~/miyagi/engine/src once per bundled version (cached lessons kept), then start
 *      `Resources/engine/python/bin/python3 -s -B -m server.orchestrator.main --host 127.0.0.1` directly (cwd = src). No
 *      uv, no Python download, no network; nothing is written inside the signed app (-B, and all precompiled: a
 *      PYTHON.json without precompiled: true isn't used). No PYTHON* variables are set: the engine passes its
 *      environment to VS Code and to the learner's commands, which must see the user's own Python setup.
 *   5. Older bundles (install.sh + src/, no python/): run `install.sh --src … --no-app --no-vscode --no-start --yes`
 *      once (uv + Python + packages: about a minute, needs the network), then start the launcher it writes.
 *   6. Quit → stop only the engine this app started.
 *   7. Port taken by an engine THIS app started on an earlier launch (miyagi was force-quit or crashed, so step 6 never
 *      ran): that engine still wants the old launch's token and would refuse this launch forever. Its pid file
 *      (~/miyagi/engine/run/app-engine.json; app-engine-dev.json for `npm run dev`, so a dev app never reclaims the
 *      installed app's engine, nor the reverse), its exact command line (this app's Python or launcher, never just the
 *      module name) and its start time say it's ours, so stop it and start a fresh one.
 *      Anything else on the port (an engine started in Terminal) stays the user's: step 2.
 *   8. The engine this app starts (bundled Python or launcher) always gets ORCH_AUTO_RESUME=0 and ORCH_AUTOSTART=0
 *      (hard in a built app: a launch starts from new, never reloads the last lesson) and an explicit MIYAGI_STATE_DIR
 *      (~/miyagi/state for the installed app, ~/miyagi/state-dev for `npm run dev`, unless the env names one).
 *
 * Which engine (lane realapp, app/agents/real-app.md, SHIP.md "Which engine"):
 *   - Default, what every user gets: the engine inside the app (steps 1-7) + the miyagi cloud (features/cloud.ts).
 *   - Dev (Michael's Mac): engine mode "dev" never starts or installs an engine; the app only connects to ENGINE_URL
 *     (default ws://localhost:8787: the dev engine in Terminal, with its own .env). Set it with env MIYAGI_ENGINE=dev
 *     or, for an app opened from Finder / Spotlight (no shell environment), with userData/engine.json
 *     {"engine": "dev"} (`npm run install:local -- --mode-only --engine dev` writes it). {"cloud": "off"} there also stops the app
 *     sending its cloud token (MIYAGI_CLOUD_URL=off), so the dev engine uses its .env keys. Env always wins.
 *
 * Every window hears the state as feat:engine-local {state, line?, runtime?}; bridge.invoke('engine-local:get') reads it.
 * The macOS Screen Recording prompt names miyagi (the app started the engine), not Terminal.
 *
 * Also here (A12): the VS Code companion that ships in Resources/vscode, installed with VS Code's own `code` CLI.
 *   bridge.invoke('engine-local:companion')          → CompanionStatus (read-only probe, never prompts, no network)
 *   bridge.invoke('engine-local:companion-install')  → CompanionStatus after `code --install-extension <vsix> --force`
 *                                                      plus ms-python.python and ms-toolsai.jupyter when missing
 *   feat:engine-local-companion                        the same status while an install runs
 * Only Visual Studio Code (bundle id com.microsoft.VSCode). Never a `code` found on PATH: other editors ship one.
 */
import { app, clipboard, ipcMain, shell, type IpcMainInvokeEvent } from 'electron'
import { execFile, spawn, type ChildProcess, type SpawnOptions } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { accessSync, appendFileSync, closeSync, constants, existsSync, mkdirSync, openSync, readFileSync, rmSync, writeFileSync, writeSync } from 'node:fs'
import { cp, rename, rm } from 'node:fs/promises'
import { connect } from 'node:net'
import { homedir } from 'node:os'
import { basename, join } from 'node:path'
import type { EngineLink } from './engine'

export type LocalEngineState = 'off' | 'checking' | 'installing' | 'starting' | 'running' | 'external' | 'missing' | 'failed'
/**
 * `runtime`: which way this app runs the engine. bundled = the Python inside the app; launcher = ~/miyagi/engine/bin.
 * `reason`: on failed / missing, why, in one plain line for "Copy details" (paths and error codes stay out of `line`).
 */
export type LocalEngineStatus = { state: LocalEngineState; line?: string; logs?: string; runtime?: 'bundled' | 'launcher'; reason?: string }

/** The line every surface shows when the engine didn't come up (Home's rail, the setup step). */
export const ENGINE_FAILED_LINE = "miyagi couldn't start its engine."

/** No answer this long after the app started the engine, or after launch when the app doesn't manage one. */
const START_TIMEOUT_MS = 60_000
const UNMANAGED_TIMEOUT_MS = 12_000

/** Michael's installer (docs/INSTALL.md), for a Mac where the app carries no engine. */
const ONE_LINER = 'curl -fsSL https://raw.githubusercontent.com/michae6345-crypto/miyagi/integration/live/scripts/install.sh | bash'

/** True when something accepts a TCP connection on 127.0.0.1:port within `ms`. */
function listening(port: number, ms = 700): Promise<boolean> {
  return new Promise((resolve) => {
    const s = connect({ host: '127.0.0.1', port })
    const done = (ok: boolean): void => {
      s.destroy()
      resolve(ok)
    }
    s.setTimeout(ms, () => done(false))
    s.once('connect', () => done(true))
    s.once('error', () => done(false))
  })
}

/** Where VS Code keeps its `code` CLI inside the app (it exists even if the user never ran "Install 'code' in PATH"). */
const VSCODE_APPS = ['/Applications/Visual Studio Code.app', join(homedir(), 'Applications', 'Visual Studio Code.app')]
const CODE_IN_APP = join('Contents', 'Resources', 'app', 'bin')

/**
 * A Finder-launched app has a bare PATH; the installer and the engine need uv, git, curl, and VS Code's `code` (the
 * engine opens lesson folders with it). VS Code's own bin folders only, never a `code` shim another editor installs.
 */
function fixedPath(home: string): string {
  const extra = [join(home, 'bin'), join(homedir(), '.local/bin'), ...VSCODE_APPS.map((a) => join(a, CODE_IN_APP)), '/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin']
  return [...extra, process.env.PATH ?? ''].filter(Boolean).join(':')
}

const readText = (p: string): string => {
  try {
    return readFileSync(p, 'utf8').trim()
  } catch {
    return ''
  }
}

const executable = (p: string): boolean => {
  try {
    accessSync(p, constants.X_OK)
    return true
  } catch {
    return false
  }
}

/**
 * The engine bundle: Resources/engine in a built app. MIYAGI_BUNDLE_DIR points a dev run (not packaged) at
 * app/build/engine to try the bundled path without packaging; a packaged app ignores it.
 */
function bundleDir(): string {
  const dev = !app.isPackaged ? process.env.MIYAGI_BUNDLE_DIR?.trim() : ''
  return dev || join(process.resourcesPath, 'engine')
}

/** The companion .vsix folder: Resources/vscode when packaged, <bundle>/vscode in a dev run (bundle-engine's layout). */
function vscodeDir(): string {
  const dev = !app.isPackaged ? process.env.MIYAGI_BUNDLE_DIR?.trim() : ''
  return dev ? join(dev, 'vscode') : join(process.resourcesPath, 'vscode')
}

/** Folders the engine writes into its own source tree, kept across app updates (copySource). */
const KEPT_DIRS: readonly string[][] = [
  ['demo', 'cache'],
  ['demo', 'runs'],
]

/** Where Rosetta 2 lives once installed (Apple silicon only). */
const ROSETTA = '/Library/Apple/usr/share/rosetta/rosetta'

/**
 * Can this Mac run the bundled Python? PYTHON.json `arch` (bundle-engine.mjs) says which one the app carries: arm64
 * needs Apple silicon (an x64 app under Rosetta still runs an arm64 child natively); x64 runs on Intel, and on Apple
 * silicon only with Rosetta. A bundle without a readable arch isn't trusted: the installer / missing path takes over,
 * never a spawn that dies with "bad CPU type". → '' when it can, else why not (for engine.log)
 */
function pythonArchProblem(bundle: string): string {
  let manifest: { arch?: unknown; precompiled?: unknown }
  try {
    manifest = JSON.parse(readFileSync(join(bundle, 'PYTHON.json'), 'utf8')) as { arch?: unknown; precompiled?: unknown }
  } catch {
    return 'no readable PYTHON.json'
  }
  // Built where the target Python couldn't run: no import check and no .pycs, so a lesson .venv made from it would
  // write .pycs inside the signed app. Never used.
  if (manifest?.precompiled !== true) return 'bundled Python was not precompiled or import-checked (PYTHON.json precompiled is not true)'
  const arch = manifest.arch
  const appleSilicon = process.arch === 'arm64' || app.runningUnderARM64Translation
  if (arch === 'universal2') return ''
  if (arch === 'arm64') return appleSilicon ? '' : `bundled Python is arm64, this Mac is ${process.arch}`
  if (arch === 'x64') {
    if (!appleSilicon) return ''
    return process.arch === 'x64' || existsSync(ROSETTA) ? '' : 'bundled Python is x64 and Rosetta is not installed'
  }
  return `unknown bundled Python arch: ${String(arch)}`
}

/** Which engine this launch uses: env MIYAGI_ENGINE, else userData/engine.json. → { mode, cloud } */
export type EngineMode = { mode: 'bundled' | 'dev'; cloud?: 'off'; source: 'env' | 'file' | 'default' }
export function engineMode(): EngineMode {
  const pick = (v: unknown): 'bundled' | 'dev' | undefined => {
    const t = typeof v === 'string' ? v.trim().toLowerCase() : ''
    return t === 'dev' || t === 'external' ? 'dev' : t === 'bundled' || t === 'app' ? 'bundled' : undefined
  }
  let file: { engine?: unknown; cloud?: unknown } = {}
  try {
    const v: unknown = JSON.parse(readFileSync(join(app.getPath('userData'), 'engine.json'), 'utf8'))
    if (v && typeof v === 'object') file = v as typeof file
  } catch {
    // No file: the default.
  }
  const cloud = typeof file.cloud === 'string' && /^(off|0|false|no)$/i.test(file.cloud.trim()) ? ('off' as const) : undefined
  const env = pick(process.env.MIYAGI_ENGINE)
  if (env) return { mode: env, cloud, source: 'env' }
  const fromFile = pick(file.engine)
  return fromFile ? { mode: fromFile, cloud, source: 'file' } : { mode: 'bundled', cloud, source: 'default' }
}

/** v2: the latest state, for core modules that need it (main/permissions.ts: 'external' means grants are unknown). */
let current: LocalEngineStatus = { state: 'off' }
export function localEngineState(): LocalEngineState {
  return current.state
}

/**
 * ROADMAP 1.4 (features/recover.ts sets these). The engine this app started died while it was running (a crash, not a
 * quit or a Restart): how long to wait before starting it again, or undefined to give up and report the failure (the
 * learner then gets Retry). Without a policy a crash is reported at once, as before.
 */
export type RespawnPolicy = (why: string) => number | undefined
let respawnPolicy: RespawnPolicy | undefined
export function setRespawnPolicy(policy: RespawnPolicy | undefined): void {
  respawnPolicy = policy
}
/** The same restart the Engine offline card's Restart runs (feat:engine-local:restart), for main-side recovery. */
let restartRef: () => { ok: boolean; state: LocalEngineState } = () => ({ ok: false, state: current.state })
export function restartLocalEngine(): { ok: boolean; state: LocalEngineState } {
  return restartRef()
}
/** Is the engine process this app started alive right now (not one in Terminal)? */
let ownChildAlive = (): boolean => false
export function localEngineChildAlive(): boolean {
  return ownChildAlive()
}

/**
 * v2 (W0-5): a per-launch engine token. 32 random bytes, made once per app launch, kept in memory only: passed to the
 * engine this app starts in its environment (MIYAGI_ENGINE_TOKEN, never on a command line) and sent back by the link
 * as a header, so a page in a browser or another local process can't drive the engine (the engine checks it, E2).
 * MIYAGI_ENGINE_TOKEN already in this app's environment (dev, an engine started by hand with the same value) wins.
 */
export const ENGINE_TOKEN: string = process.env.MIYAGI_ENGINE_TOKEN?.trim() || randomBytes(32).toString('base64url')

/**
 * Why this launch doesn't start an engine of its own, or '' when it does (step 1). Pure, so it can be checked in Node.
 * `npm run dev` is not packaged: it connects to ENGINE_URL (the engine in Terminal) unless MIYAGI_AUTOSTART=1.
 */
export function whyUnmanaged(o: { platform: string; packaged: boolean; autostart: boolean; demo: boolean; local: boolean; dev: boolean }): string {
  if (o.platform !== 'darwin') return `not macOS (${o.platform})`
  if (o.demo) return 'DEMO=1 (mock engine)'
  if (o.dev) return 'engine mode dev (engine.json or MIYAGI_ENGINE)'
  if (!o.local) return 'ENGINE_URL points at another machine'
  if (!o.packaged && !o.autostart) return 'a development build (npm run dev) without MIYAGI_AUTOSTART=1'
  return ''
}

/** The line every surface shows while an engine this app didn't start holds its port (packaged app, step 2). */
export const ENGINE_HELD_LINE = 'Another miyagi engine is running.'
/** How often the installed app checks whether that engine has gone, so it can start its own. */
export const HELD_POLL_MS = 5000

/**
 * Step 2, pure: something answers on the port and reclaimOwnLeftover() said it isn't ours (`ours`: it was ours and is
 * now stopped, so start a fresh one). Adopt it as 'external' only in `npm run dev` or engine mode dev. The installed
 * app (packaged, mode bundled or unset) never silently uses an engine it didn't start.
 */
export function adoptExternal(o: { packaged: boolean; mode?: 'bundled' | 'dev'; ours: boolean }): boolean {
  if (o.ours) return false
  return !o.packaged || o.mode === 'dev'
}

/** Step 7: one pid file per build, so a dev app and the installed app never reclaim or stop each other's engine. */
export function pidFileName(packaged: boolean): string {
  return packaged ? 'app-engine.json' : 'app-engine-dev.json'
}

/**
 * Step 8, pure: what every engine this app starts must see, whatever the inherited environment says. A built app
 * pins ORCH_AUTO_RESUME and ORCH_AUTOSTART to 0 (a launch starts from new: no reloaded lesson, no VS Code, no video);
 * `npm run dev` keeps an explicit value. MIYAGI_STATE_DIR is explicit, so the installed engine's saves stay in
 * ~/miyagi/state and a dev app's engine never writes there (~/miyagi/state-dev, as for dev engines).
 */
export function enginePins(env: NodeJS.ProcessEnv, packaged: boolean): { ORCH_AUTO_RESUME: string; ORCH_AUTOSTART: string; MIYAGI_STATE_DIR: string } {
  return {
    ORCH_AUTO_RESUME: packaged ? '0' : env.ORCH_AUTO_RESUME || '0',
    ORCH_AUTOSTART: packaged ? '0' : env.ORCH_AUTOSTART || '0',
    MIYAGI_STATE_DIR: env.MIYAGI_STATE_DIR || join(homedir(), 'miyagi', packaged ? 'state' : 'state-dev'),
  }
}

/** The launcher runtime's environment (~/miyagi/engine/bin/miyagi-engine): the app's env plus the step 8 pins. */
export function launcherEnv(env: NodeJS.ProcessEnv, packaged: boolean): NodeJS.ProcessEnv {
  return { ...env, ...enginePins(env, packaged) }
}

/**
 * The bundled Python's environment: the launcher's defaults (scripts/install.sh writes the same ones), the user's
 * own values win (except the step 8 pins), and nothing from a shell's Python setup leaks in (PYTHONHOME, a venv). No
 * PYTHONPATH, PYTHONNOUSERSITE or PYTHONDONTWRITEBYTECODE: the engine hands its environment to everything it starts
 * (`code <folder>` in workspace/editor.py, the learner's commands in "Run it for me"), and VS Code's terminals and
 * kernels must get the user's own Python setup. The interpreter flags do that job instead (spawnEngine: -s -B, cwd = src).
 */
export function pythonEnv(env: NodeJS.ProcessEnv, home: string, python: string, port: number, packaged: boolean): NodeJS.ProcessEnv {
  const e: NodeJS.ProcessEnv = { ...env }
  for (const k of ['PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONEXECUTABLE', 'VIRTUAL_ENV', '__PYVENV_LAUNCHER__', 'CONDA_PREFIX']) delete e[k]
  return {
    ...e,
    PYTHONUNBUFFERED: '1',
    // workspace/setup.py builds lesson .venvs from this when the Mac has no other Python 3 (engine side, E-lane).
    MIYAGI_BUNDLED_PYTHON: python,
    TUT_ENV: e.TUT_ENV || join(home, 'engine.env'),
    ENGINE_HOST: '127.0.0.1',
    ENGINE_PORT: String(port),
    ORCH_SCREEN: e.ORCH_SCREEN || '1',
    ORCH_OPEN_WORKSPACE: e.ORCH_OPEN_WORKSPACE || '1',
    LESSON_ENGINE: e.LESSON_ENGINE || 'claude',
    MIYAGI_EDITOR: e.MIYAGI_EDITOR || 'vscode',
    ...enginePins(e, packaged),
  }
}

/** Who listens on 127.0.0.1:port, for engine.log: `pid <n> (<command name>)` from lsof, never a command line. */
async function portHolder(port: number): Promise<string> {
  const r = await run('/usr/sbin/lsof', ['-nP', `-iTCP:${port}`, '-sTCP:LISTEN', '-Fpc'], 3000)
  const seen: string[] = []
  let pid = ''
  for (const l of r.out.split('\n')) {
    if (l.startsWith('p')) pid = l.slice(1)
    else if (l.startsWith('c') && pid) seen.push(`pid ${pid} (${l.slice(1)})`)
  }
  return [...new Set(seen)].join(', ') || 'unknown (lsof named no listener)'
}

/** What setupLocalEngine reaches outside the process for; the tests pass fakes (no engine, no lsof). */
export type LocalEngineDeps = {
  listening: (port: number, ms?: number) => Promise<boolean>
  spawn: (command: string, args: readonly string[], options: SpawnOptions) => ChildProcess
  holder: (port: number) => Promise<string>
  pollMs: number
  platform: string
}

/** Keys, tokens and secrets never leave in "Copy details", even if the engine printed one. */
function redact(line: string): string {
  return line.replace(/((?:key|token|secret|password|authorization)[^=:\s]*\s*[=:]\s*)\S+/gi, '$1[hidden]').replace(/\b(sk-[\w-]{8,}|AIza[\w-]{20,})/g, '[hidden]')
}

/** The text "Copy details" puts on the clipboard: the state, the facts, and the end of engine.log. */
export function engineDetails(status: LocalEngineStatus, facts: readonly string[], logs: string): string {
  let tail = ''
  try {
    tail = readFileSync(logs, 'utf8').split('\n').slice(-40).map(redact).join('\n').trim()
  } catch {
    tail = '(no engine.log yet)'
  }
  return [
    `miyagi engine: ${status.state}${status.reason ? `: ${status.reason}` : ''}`,
    ...facts,
    `macOS ${process.getSystemVersion?.() ?? ''} ${process.arch}`,
    `log: ${logs}`,
    '',
    tail
  ].join('\n')
}

/**
 * `trusted`: main's sender check (index.ts trustedSender). Every handler here answers only our own windows; an
 * untrusted sender gets undefined / false and, for restart, nothing is stopped or spawned.
 */
export function setupLocalEngine(
  engine: EngineLink,
  url: string,
  broadcast: (channel: string, payload: unknown) => void,
  trusted: (e: IpcMainInvokeEvent) => boolean,
  deps: Partial<LocalEngineDeps> = {}
): () => void {
  const d: LocalEngineDeps = { listening, spawn, holder: portHolder, pollMs: HELD_POLL_MS, platform: process.platform, ...deps }
  const packaged = app.isPackaged
  let status: LocalEngineStatus = { state: 'off' }
  let child: ChildProcess | undefined
  /** We're quitting: the engine's exit is ours, not a crash. */
  let stopping = false
  /** feat:engine-local:restart is stopping the engine: start it again when it exits. */
  let restarting = false
  const set = (next: LocalEngineStatus): void => {
    status = next
    current = next
    // While main brings the engine up itself, refused connects are expected: the pill stays calm (engine.ts).
    engine.holdFailures(next.state === 'checking' || next.state === 'installing' || next.state === 'starting')
    broadcast('engine-local', status)
  }
  // Every connect carries the token (index.ts also passes it to the EngineLink constructor, so the very first attempt
  // does); an engine without one configured ignores the header.
  engine.setToken(ENGINE_TOKEN)
  ipcMain.handle('feat:engine-local:get', (e) => (trusted(e) ? status : undefined))
  ipcMain.handle('feat:engine-local:command', (e) => (trusted(e) ? ONE_LINER : undefined))
  // The pill's "Install the engine": the one-liner on the clipboard. "Engine didn't start": open its log.
  ipcMain.handle('feat:engine-local:copy', (e) => {
    if (!trusted(e)) return false
    clipboard.writeText(ONE_LINER)
    return true
  })
  ipcMain.handle('feat:engine-local:logs', async (e) => {
    if (!trusted(e)) return false
    const file = status.logs ?? ''
    return file && existsSync(file) ? (await shell.openPath(file)) === '' : false
  })
  /**
   * v2 (W0-5): the Engine offline card's Restart (A7). Ours: stop it and start it again. External (Terminal): nothing
   * to do here, the card says "Restart it in Terminal". Not managed (dev without MIYAGI_AUTOSTART): nothing either.
   * Missing / failed: run the start-up sequence again. → { ok, state }
   */
  let restart: () => { ok: boolean; state: LocalEngineState } = () => ({ ok: false, state: status.state })
  ipcMain.handle('feat:engine-local:restart', (e) => (trusted(e) ? restart() : { ok: false, state: status.state }))
  restartRef = () => restart()

  // The companion works whether or not this app manages the engine (an engine in Terminal still talks to it).
  setupCompanion(broadcast, trusted)

  const home = process.env.MIYAGI_HOME || join(homedir(), 'miyagi', 'engine')
  const logs = join(home, 'logs', 'engine.log')
  /** Details (paths, error codes) go to engine.log only; the pill gets plain fixed copy. */
  const note = (msg: string): void => {
    try {
      mkdirSync(join(home, 'logs'), { recursive: true })
      appendFileSync(logs, `--- ${new Date().toISOString()} ${msg}\n`)
    } catch {
      // No log is no reason to fail.
    }
  }
  /** Every failure path ends here: the reason goes to engine.log and "Copy details"; the surfaces say one calm line. */
  const fail = (reason: string, extra: Partial<LocalEngineStatus> = {}): void => {
    note(`engine not running: ${reason}`)
    set({ state: 'failed', line: ENGINE_FAILED_LINE, logs, reason, ...extra })
  }
  /** Facts for "Copy details": never the token, never keys. */
  const facts: string[] = []
  ipcMain.handle('feat:engine-local:details', (e) => {
    if (!trusted(e)) return false
    clipboard.writeText(engineDetails(status, facts, logs))
    return true
  })

  const port = (() => {
    try {
      return Number(new URL(url).port) || 8787
    } catch {
      return 8787
    }
  })()
  const local = /^wss?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?\/?$/i.test(url)
  const chosen = engineMode()
  // {"cloud": "off"} in engine.json: features/cloud.ts reads MIYAGI_CLOUD_URL when it sets up, after this runs.
  if (chosen.cloud === 'off' && process.env.MIYAGI_CLOUD_URL === undefined) process.env.MIYAGI_CLOUD_URL = 'off'
  if (chosen.mode === 'dev') {
    console.log(`[tut] engine mode dev (${chosen.source}): connecting to ${url}, never starting one`)
    // The engine is someone else's (Terminal): onboarding says "Running in Terminal", permissions.ts knows the grants
    // belong to that app, and Restart says "Restart it in Terminal".
    set({ state: 'external' })
  }
  const unmanaged = whyUnmanaged({
    platform: d.platform,
    packaged,
    autostart: process.env.MIYAGI_AUTOSTART === '1',
    demo: process.env.DEMO === '1',
    local,
    dev: chosen.mode === 'dev'
  })
  facts.push(
    `app: ${app.getVersion()}, ${app.isPackaged ? 'packaged' : 'not packaged (npm run dev)'}, ${process.execPath}`,
    `engine url: ${url}`,
    `engine mode: ${chosen.mode} (${chosen.source})`,
    `managed by this app: ${unmanaged ? `no, ${unmanaged}` : 'yes'}`
  )
  if (unmanaged) {
    console.log(`[tut] not starting an engine: ${unmanaged}`)
    // DEMO runs the mock engine in-process; dev mode already says "Start the engine in Terminal" (external).
    if (process.env.DEMO === '1' || chosen.mode === 'dev') return () => undefined
    // Nobody starts an engine here (`npm run dev`, a remote ENGINE_URL). If none answers soon, say so instead of
    // "Connecting" forever (the rows read Connecting while the state is off). Retry tries the link again.
    const before = status
    let timer: ReturnType<typeof setTimeout> | undefined
    const watch = (): void => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        timer = undefined
        if (!engine.connected) fail(`nothing answers on ${url}, and this app doesn't start an engine (${unmanaged}). Start one in Terminal, or open the installed miyagi app.`)
      }, UNMANAGED_TIMEOUT_MS)
    }
    engine.onStatus((up) => {
      if (up && status.state === 'failed') set(before)
      if (!up && status.state !== 'failed') watch()
    })
    restart = () => {
      if (status.state === 'failed') set(before)
      engine.reconnect()
      watch()
      return { ok: true, state: status.state }
    }
    if (!engine.connected) watch()
    return () => {
      if (timer) clearTimeout(timer)
    }
  }

  const src = join(home, 'src')
  const launcher = join(home, 'bin', 'miyagi-engine')
  const marker = join(home, 'BUNDLED')
  /** Step 7: which engine process this app started, so a later launch can tell its own leftover from the user's. */
  const pidFile = join(home, 'run', pidFileName(packaged))
  const bundle = bundleDir()
  facts.push(`engine bundle: ${bundle} (${readText(join(bundle, 'VERSION')) || 'no VERSION'})`, `engine home: ${home}`)
  const bundleVersion = (): string => readText(join(bundle, 'VERSION')) || 'bundled'
  const hasSource = existsSync(join(bundle, 'src', 'server', 'pyproject.toml'))
  const python = join(bundle, 'python', 'bin', 'python3')
  /** A12: the app carries its own Python with the packages installed, built for a CPU this Mac can run. */
  const pythonBundled = ((): boolean => {
    if (!hasSource || !executable(python)) return false
    const problem = pythonArchProblem(bundle)
    if (problem) note(`not using the bundled Python: ${problem}`)
    facts.push(`bundled Python: ${problem || 'ok'}`)
    return !problem
  })()
  /** Older bundles: source + the uv installer. */
  const installerBundled = hasSource && existsSync(join(bundle, 'install.sh'))
  const env: NodeJS.ProcessEnv = { ...process.env, MIYAGI_HOME: home, PATH: fixedPath(home), MIYAGI_ENGINE_TOKEN: ENGINE_TOKEN }
  /** Which way start() runs the engine; boot() decides. */
  let runtime: 'bundled' | 'launcher' = 'launcher'
  /** A respawn waiting to start (ROADMAP 1.4). */
  let respawnTimer: ReturnType<typeof setTimeout> | undefined
  ownChildAlive = () => !!child && !child.killed && child.exitCode === null

  /** Step 2 (packaged): an engine this app didn't start holds the port; boot() waits for it to go. */
  let held: ReturnType<typeof setTimeout> | undefined
  let holding = false
  engine.onStatus((up) => {
    // The link may reach the other engine; that never makes it this app's engine (Core request: a link hold).
    if (holding) return
    if (up && status.state !== 'running' && status.state !== 'external') set({ state: child ? 'running' : 'external', runtime: child ? runtime : undefined })
  })

  /**
   * Copy the bundled source into ~/miyagi/engine/src: next to it first, then swap, so a crash mid-copy never leaves a
   * half tree. What the engine writes into its own tree is merged into src.new before the swap (the new source's
   * files win), so src.old never holds the only copy once it's deleted: src/demo/cache (built lessons, searches,
   * transcripts) and src/demo/runs (recorder runs, and the backups of learner files made before "Do it for me"). A src.old left by a run
   * that stopped mid-swap is merged the same way before it goes. Async so the first launch never blocks the main
   * process. → ok
   */
  const copySource = async (): Promise<boolean> => {
    set({ state: 'installing', line: 'Setting up the engine' })
    try {
      mkdirSync(home, { recursive: true })
      const next = join(home, 'src.new')
      const old = join(home, 'src.old')
      await rm(next, { recursive: true, force: true })
      // preserveTimestamps: the .pyc files are hash-checked, but keeping mtimes avoids needless re-reads.
      await cp(join(bundle, 'src'), next, { recursive: true, preserveTimestamps: true })
      // force: false keeps what's already there: the bundle's files first, then the current src's over src.old's.
      for (const from of [src, old]) {
        for (const dir of KEPT_DIRS) {
          const kept = join(from, ...dir)
          if (existsSync(kept)) await cp(kept, join(next, ...dir), { recursive: true, force: false, errorOnExist: false })
        }
      }
      await rm(old, { recursive: true, force: true })
      if (existsSync(src)) await rename(src, old)
      await rename(next, src)
      await rm(old, { recursive: true, force: true })
      return true
    } catch (err) {
      fail(`setting up ${src} from the app failed: ${String(err)}`)
      return false
    }
  }

  /** Older bundles: copy the source, then run the uv installer on it (about a minute, needs the network). */
  const install = async (): Promise<boolean> => {
    if (!(await copySource())) return false
    return new Promise((resolve) => {
      const p = d.spawn('bash', [join(bundle, 'install.sh'), '--src', src, '--no-app', '--no-vscode', '--no-start', '--yes'], { env, stdio: ['ignore', 'pipe', 'pipe'] })
      const onData = (b: Buffer): void => {
        // eslint-disable-next-line no-control-regex
        const last = b.toString().replace(/\x1b\[[0-9;]*m/g, '').split('\n').map((l) => l.replace(/^\[miyagi\]\s*/, '').trim()).filter(Boolean).pop()
        if (last) set({ state: 'installing', line: last.slice(0, 90) })
      }
      p.stdout?.on('data', onData)
      p.stderr?.on('data', onData)
      p.on('error', (err) => {
        fail(`install.sh didn't run: ${String(err)}`)
        resolve(false)
      })
      p.on('exit', (code) => {
        if (code === 0) {
          writeFileSync(marker, bundleVersion())
          resolve(true)
        } else {
          fail(`install.sh stopped (exit ${code}); it needs the network`)
          resolve(false)
        }
      })
    })
  }

  /** Spawn the engine. Its own process group, so quitting stops it and anything it started (see killGroup). */
  const spawnEngine = (): ChildProcess => {
    if (runtime === 'launcher') return d.spawn(launcher, [], { env: launcherEnv(env, packaged), stdio: 'ignore', detached: true })
    // Bundled Python: no launcher script in between, so this app writes the log the launcher would have.
    mkdirSync(join(home, 'logs'), { recursive: true })
    const fd = openSync(logs, 'a')
    try {
      writeSync(fd, `--- ${new Date().toISOString()} engine start (bundled Python, ${bundleVersion()})\n`)
      // -s: no user site-packages; -B: no .pyc written; -m with cwd = src puts src first on sys.path (no PYTHONPATH).
      return d.spawn(python, ['-s', '-B', '-m', 'server.orchestrator.main', '--host', '127.0.0.1', '--port', String(port)], {
        cwd: src,
        env: pythonEnv(env, home, python, port, packaged),
        stdio: ['ignore', fd, fd],
        detached: true,
      })
    } finally {
      // The child has its own copy of the descriptor.
      closeSync(fd)
    }
  }

  const forgetPid = (): void => {
    try {
      rmSync(pidFile, { force: true })
    } catch {
      // A stale pid file is checked against the process before it's ever used.
    }
  }
  const rememberPid = (pid: number | undefined): void => {
    if (pid === undefined) return
    try {
      mkdirSync(join(home, 'run'), { recursive: true })
      writeFileSync(pidFile, JSON.stringify({ pid, port, runtime, at: new Date().toISOString() }))
    } catch {
      // Without it a force-quit leaves an engine the next launch can't reclaim: the pill says so, nothing breaks.
    }
  }

  /**
   * Whether `cmd` (a `ps -o command=` line) is an engine this app starts, and never anyone else's. The module name
   * alone also matches a dev engine (`.../run-live/.venv/bin/python -m server.orchestrator.main`), so it isn't enough.
   * Bundled: the exact Python inside this app. Launcher: the launcher script itself, or (when it `exec`s into Python)
   * an interpreter under this app's engine home running the engine module.
   */
  const isOwnEngineCommand = (cmd: string, kind: unknown): boolean => {
    const line = cmd.trim()
    if (kind !== 'launcher' && line.startsWith(`${python} `)) return true
    if (kind === 'bundled') return false
    const shells = ['', '/bin/bash ', 'bash ', '/bin/sh ', 'sh ', '/bin/zsh ']
    if (shells.some((sh) => line === `${sh}${launcher}` || line.startsWith(`${sh}${launcher} `))) return true
    return line.startsWith(`${home}/`) && /\s-m\s+server\.orchestrator\.main(\s|$)/.test(line)
  }

  /**
   * The pid started within a few seconds of the pid file's `at` (`ps -o lstart=`, C locale, local time), so a pid the
   * OS has since handed to another process (a dev engine started later from a shell) is never taken for ours.
   */
  const startedWhenSaved = async (pid: number, at: unknown): Promise<boolean> => {
    const saved = typeof at === 'string' ? Date.parse(at) : NaN
    if (!Number.isFinite(saved)) return false
    const ps = await run('/usr/bin/env', ['LC_ALL=C', '/bin/ps', '-o', 'lstart=', '-p', String(pid)], 2000)
    const began = ps.ok ? Date.parse(ps.out.trim().replace(/\s+/g, ' ')) : NaN
    return Number.isFinite(began) && Math.abs(saved - began) <= 10_000
  }

  /**
   * Step 7: the port is taken. If the pid file names a live process whose command line is this app's own engine
   * (isOwnEngineCommand) and which started when the file was written (startedWhenSaved), it's ours from an earlier
   * launch: stop its group (SIGTERM, then SIGKILL after 5 s) and wait for the port. Anything else is never touched.
   * → true when the port is free now.
   */
  const reclaimOwnLeftover = async (): Promise<boolean> => {
    let pid = 0
    let at: unknown
    let kind: unknown
    try {
      const saved = JSON.parse(readFileSync(pidFile, 'utf8')) as { pid?: unknown; at?: unknown; runtime?: unknown }
      pid = Number(saved.pid) || 0
      at = saved.at
      kind = saved.runtime
    } catch {
      return false
    }
    const alive = (): boolean => {
      try {
        process.kill(pid, 0)
        return true
      } catch {
        return false
      }
    }
    if (pid <= 1 || pid === process.pid || !alive()) {
      forgetPid()
      return false
    }
    const ps = await run('/bin/ps', ['-o', 'command=', '-p', String(pid)], 2000)
    if (!ps.ok || !isOwnEngineCommand(ps.out, kind) || !(await startedWhenSaved(pid, at))) {
      // The pid was reused by something else, or can't be proven ours: never touch it.
      forgetPid()
      return false
    }
    note(`port ${port} held by this app's engine from an earlier launch (pid ${pid}): stopping it`)
    const signal = (sig: NodeJS.Signals): void => {
      try {
        process.kill(-pid, sig)
      } catch {
        try {
          process.kill(pid, sig)
        } catch {
          // Already gone.
        }
      }
    }
    const freed = async (ms: number): Promise<boolean> => {
      for (const until = Date.now() + ms; Date.now() < until; ) {
        if (!(await d.listening(port, 300))) return true
        await new Promise((r) => setTimeout(r, 250))
      }
      return !(await d.listening(port, 300))
    }
    signal('SIGTERM')
    if (!(await freed(5000))) {
      signal('SIGKILL')
      if (!(await freed(2000))) return false
    }
    forgetPid()
    return true
  }

  /** Started, but no answer yet: after START_TIMEOUT_MS say so (the engine keeps running; a late connect still wins). */
  let slow: ReturnType<typeof setTimeout> | undefined
  const watchStart = (): void => {
    if (slow) clearTimeout(slow)
    slow = setTimeout(() => {
      slow = undefined
      if (!engine.connected && child && status.state === 'starting') fail(`the engine started (pid ${child.pid}) but didn't answer on port ${port} within ${START_TIMEOUT_MS / 1000} s`, { runtime })
    }, START_TIMEOUT_MS)
  }

  const start = (): void => {
    set({ state: 'starting', runtime })
    try {
      child = spawnEngine()
      rememberPid(child.pid)
    } catch (err) {
      child = undefined
      return fail(`spawning the engine failed: ${String(err)}`, { runtime })
    }
    watchStart()
    child.on('error', (err) => {
      child = undefined
      fail(`the engine process failed: ${String(err)}`, { runtime })
    })
    child.on('exit', (code, signal) => {
      const wasRunning = status.state === 'running'
      child = undefined
      forgetPid()
      if (stopping) return set({ state: 'off' })
      if (restarting) {
        restarting = false
        return start()
      }
      const why = code === null ? `stopped by ${signal ?? 'a signal'}` : `exited with code ${code}`
      // ROADMAP 1.4: a crash mid-run starts it again (features/recover.ts decides how soon, and when to give up). The
      // surfaces keep the calm "miyagi is reconnecting"; the lesson comes back on reconnect (the engine's snapshot).
      const delay = wasRunning ? respawnPolicy?.(why) : undefined
      if (delay !== undefined) {
        note(`the engine ${why} while running; starting it again in ${delay} ms`)
        set({ state: 'starting', runtime })
        clearTimeout(respawnTimer)
        respawnTimer = setTimeout(() => {
          respawnTimer = undefined
          if (!stopping && !child) start()
        }, delay)
        return
      }
      if (wasRunning) return fail(`the engine ${why} while running (its own output is above in this log)`, { line: 'The engine stopped.', runtime })
      // exit 1 right away can be "port already in use" (someone else's engine is up, the link will find it), or a
      // Python error on start. Only the port can tell them apart.
      const failed = (): void => fail(`the engine ${why} before it answered (its own output is above in this log)`, { runtime })
      if (code !== 1) return failed()
      void d.listening(port).then((up) => {
        if (!up) return failed()
        if (adoptExternal({ packaged, mode: chosen.mode, ours: false })) return set({ state: 'external' })
        void hold()
      })
    })
  }

  const killGroup = (c: ChildProcess): void => {
    if (c.pid === undefined) return
    try {
      process.kill(-c.pid, 'SIGTERM')
    } catch {
      c.kill('SIGTERM')
    }
  }

  restart = () => {
    if (status.state === 'external') return { ok: false, state: 'external' }
    if (child && !child.killed) {
      if (restarting) return { ok: true, state: status.state }
      restarting = true
      set({ state: 'starting', line: 'Restarting the engine', runtime })
      killGroup(child)
      return { ok: true, state: 'starting' }
    }
    if (respawnTimer) {
      // Retry while a respawn waits: start it now.
      clearTimeout(respawnTimer)
      respawnTimer = undefined
      start()
      return { ok: true, state: 'starting' }
    }
    if (status.state === 'checking' || status.state === 'installing' || status.state === 'starting') return { ok: true, state: status.state }
    void safeBoot()
    return { ok: true, state: 'checking' }
  }

  const stopHolding = (): void => {
    if (held) clearTimeout(held)
    held = undefined
    holding = false
  }
  /**
   * Step 2, installed app: the port belongs to an engine this app didn't start. Say so calmly, log who holds it, never
   * stop it, and check every pollMs (5 s); once the port is free, run the start-up sequence again (it ends in start()).
   */
  const hold = async (): Promise<void> => {
    stopHolding()
    holding = true
    const who = redact(await d.holder(port).catch((err: unknown) => `unknown (${String(err)})`))
    note(`port ${port} already has an engine this app didn't start (${who}): not using it, not stopping it; waiting for the port`)
    set({ state: 'failed', line: ENGINE_HELD_LINE, logs, reason: `port ${port} held by an engine this app did not start` })
    const poll = (): void => {
      held = setTimeout(() => {
        held = undefined
        if (!holding) return
        void d.listening(port).then((up) => {
          if (!holding) return
          if (up) return poll()
          stopHolding()
          note(`port ${port} is free again: starting this app's engine`)
          void safeBoot()
        })
      }, d.pollMs)
    }
    poll()
  }

  const boot = async (): Promise<void> => {
    stopHolding()
    set({ state: 'checking' })
    if (await d.listening(port)) {
      const ours = await reclaimOwnLeftover()
      if (!ours) {
        if (!adoptExternal({ packaged, mode: chosen.mode, ours })) return hold()
        note(`port ${port} already has an engine this app didn't start: using it, and leaving it running on quit`)
        return set({ state: 'external' })
      }
    }
    const installedFromBundle = existsSync(marker)
    // The user's own install (the one-liner: a launcher and no BUNDLED marker) always wins.
    const userInstall = existsSync(launcher) && !installedFromBundle
    if (!userInstall && pythonBundled) {
      runtime = 'bundled'
      // Once per bundled version (first launch, an app update), or when the source was deleted.
      const fresh = installedFromBundle && readText(marker) === bundleVersion() && existsSync(join(src, 'server', 'pyproject.toml'))
      if (!fresh) {
        if (!(await copySource())) return
        writeFileSync(marker, bundleVersion())
      }
      return start()
    }
    runtime = 'launcher'
    // A newer engine inside the app (an app update) replaces one the app installed before; never one the
    // user installed with the one-liner (no BUNDLED marker).
    const stale = installerBundled && installedFromBundle && readText(marker) !== bundleVersion()
    if ((!existsSync(launcher) || stale) && installerBundled && !userInstall) {
      if (!(await install())) return
    }
    if (!existsSync(launcher)) {
      note(`no engine to start: the app carries no usable engine (${bundle}) and ${launcher} doesn't exist`)
      return set({ state: 'missing', line: ONE_LINER, logs, reason: `no usable engine in ${bundle} and no ${launcher}` })
    }
    start()
  }
  // Never leave the state at checking / installing: anything boot didn't expect is a failure, with its reason.
  const safeBoot = (): Promise<void> => boot().catch((err: unknown) => fail(`start-up stopped: ${err instanceof Error ? (err.stack ?? err.message) : String(err)}`))
  void safeBoot()

  return () => {
    // Only the engine this app started (never one the user runs in Terminal). SIGTERM lets uvicorn close its
    // sockets; the whole group, in case the launcher didn't `exec` into Python.
    if (slow) clearTimeout(slow)
    stopHolding()
    // Quitting: a respawn waiting to start never starts (and an exit from here on is ours, not a crash).
    stopping = true
    clearTimeout(respawnTimer)
    if (!child || child.killed || child.pid === undefined) return
    killGroup(child)
    // Electron exits before the child's 'exit' handler runs, so forget the pid now: a stale file would name a pid
    // the OS can later hand to someone else's process.
    forgetPid()
  }
}

// ---------------------------------------------------------------------------------------------------------------------
// A12: the VS Code companion inside the app

/**
 *   unavailable  not macOS, or this build carries no .vsix and the companion isn't installed
 *   no-vscode    Visual Studio Code isn't on this Mac (the row offers "Get VS Code" through safeOpen, A3)
 *   missing      VS Code is here, the companion isn't
 *   outdated     an older companion than the one in the app
 *   installed    the companion is in VS Code (`needs` lists the Python / Jupyter extensions still missing)
 *   installing   an install is running (`line` says which step)
 *   failed       the last install didn't finish (`line` says where); the row offers Install again
 * Whether VS Code is running and connected is the engine's to say (ports 8791 to 8799), not this probe's.
 */
export type CompanionState = 'unavailable' | 'no-vscode' | 'missing' | 'outdated' | 'installed' | 'installing' | 'failed'
export type CompanionStatus = { state: CompanionState; version?: string; bundled?: string; needs?: string[]; line?: string }

const COMPANION_ID = 'miyagi.companion'
/** Lessons run Python and notebooks in VS Code; installed from the Marketplace with the companion, only on Install. */
const COMPANION_NEEDS = ['ms-python.python', 'ms-toolsai.jupyter']
const VSCODE_BUNDLE_ID = 'com.microsoft.VSCode'

type Bundled = { id: string; version: string; vsix: string }

/** The .vsix this app carries (bundle-engine.mjs writes companion.json next to it). */
function bundledCompanion(): Bundled | null {
  const dir = vscodeDir()
  try {
    const m = JSON.parse(readFileSync(join(dir, 'companion.json'), 'utf8')) as { id?: unknown; version?: unknown; file?: unknown }
    if (m.id !== COMPANION_ID || typeof m.version !== 'string' || typeof m.file !== 'string') return null
    // A plain file name in that folder, nothing else.
    if (basename(m.file) !== m.file || !/^[\w.-]+\.vsix$/.test(m.file)) return null
    const vsix = join(dir, m.file)
    return existsSync(vsix) ? { id: m.id, version: m.version, vsix } : null
  } catch {
    return null
  }
}

/** Numeric dotted-version compare: <0 when a is older. */
function compareVersions(a: string, b: string): number {
  const pa = a.split(/[.-]/).map((x) => parseInt(x, 10) || 0)
  const pb = b.split(/[.-]/).map((x) => parseInt(x, 10) || 0)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0)
    if (d) return d
  }
  return 0
}

/** execFile, no shell, bounded: → { ok, out } */
function run(file: string, args: string[], timeout: number): Promise<{ ok: boolean; out: string }> {
  return new Promise((resolve) => {
    execFile(file, args, { timeout, maxBuffer: 4 << 20, env: { ...process.env, PATH: fixedPath(join(homedir(), 'miyagi', 'engine')) } }, (err, stdout) => {
      resolve({ ok: !err, out: String(stdout ?? '') })
    })
  })
}

/**
 * VS Code's own CLI: the two usual app folders, then Spotlight by bundle id (only Visual Studio Code itself), and
 * only inside /Applications or ~/Applications: never a copy in Downloads, on a mounted dmg or an external volume
 * (a bundle id is just a string anyone can put in an Info.plist).
 */
async function findCodeCli(): Promise<string | null> {
  const inApp = (a: string): string => join(a, CODE_IN_APP, 'code')
  for (const a of VSCODE_APPS) if (executable(inApp(a))) return inApp(a)
  const roots = ['/Applications', join(homedir(), 'Applications')]
  const found = await run('/usr/bin/mdfind', [...roots.flatMap((r) => ['-onlyin', r]), `kMDItemCFBundleIdentifier == '${VSCODE_BUNDLE_ID}'`], 5000)
  for (const a of found.out.split('\n').map((l) => l.trim())) {
    const underRoot = roots.some((r) => a.startsWith(r + '/') && !a.split('/').includes('..'))
    if (underRoot && a.endsWith('.app') && executable(inApp(a))) return inApp(a)
  }
  return null
}

/** `code --list-extensions --show-versions` → id (lowercase) → version */
async function listExtensions(code: string): Promise<Map<string, string> | null> {
  const r = await run(code, ['--list-extensions', '--show-versions'], 30_000)
  if (!r.ok) return null
  const m = new Map<string, string>()
  for (const line of r.out.split('\n')) {
    const [id, ver] = line.trim().split('@')
    if (id) m.set(id.toLowerCase(), ver ?? '')
  }
  return m
}

function setupCompanion(broadcast: (channel: string, payload: unknown) => void, trusted: (e: IpcMainInvokeEvent) => boolean): void {
  let installing: Promise<CompanionStatus> | null = null
  let live: CompanionStatus | null = null
  const tell = (s: CompanionStatus): CompanionStatus => {
    live = s
    broadcast('engine-local-companion', s)
    return s
  }

  const probe = async (): Promise<CompanionStatus> => {
    if (process.platform !== 'darwin') return { state: 'unavailable' }
    const bundled = bundledCompanion()
    const code = await findCodeCli()
    if (!code) return { state: 'no-vscode', bundled: bundled?.version }
    const exts = await listExtensions(code)
    if (!exts) return { state: 'failed', bundled: bundled?.version, line: "Couldn't read VS Code's extensions." }
    const version = exts.get(COMPANION_ID)
    const needs = COMPANION_NEEDS.filter((id) => !exts.has(id))
    if (version === undefined) return { state: bundled ? 'missing' : 'unavailable', bundled: bundled?.version, needs }
    if (bundled && compareVersions(version, bundled.version) < 0) return { state: 'outdated', version, bundled: bundled.version, needs }
    return { state: 'installed', version, bundled: bundled?.version, needs }
  }

  const install = async (): Promise<CompanionStatus> => {
    const bundled = bundledCompanion()
    const code = await findCodeCli()
    if (!code) return tell({ state: 'no-vscode', bundled: bundled?.version })
    const before = await listExtensions(code)
    const has = before?.get(COMPANION_ID)
    // Our own .vsix, from inside the signed app, unless VS Code already has this version or newer.
    if (bundled && (has === undefined || compareVersions(has, bundled.version) < 0)) {
      tell({ state: 'installing', bundled: bundled.version, line: 'Installing the companion' })
      const r = await run(code, ['--install-extension', bundled.vsix, '--force'], 120_000)
      if (!r.ok) return tell({ state: 'failed', bundled: bundled.version, line: "VS Code didn't install the companion." })
    } else if (!bundled && has === undefined) {
      return tell({ state: 'unavailable' })
    }
    // Python and Jupyter from the Marketplace (needs the network). The companion works without them, so a miss here
    // leaves it installed with `needs` still listing what to add.
    for (const id of COMPANION_NEEDS) {
      if (before?.has(id)) continue
      tell({ state: 'installing', bundled: bundled?.version, line: id === 'ms-python.python' ? 'Adding Python support' : 'Adding notebook support' })
      await run(code, ['--install-extension', id], 300_000)
    }
    return tell(await probe())
  }

  ipcMain.handle('feat:engine-local:companion', async (e) => {
    if (!trusted(e)) return undefined
    if (installing && live) return live
    return probe()
  })
  ipcMain.handle('feat:engine-local:companion-install', async (e) => {
    if (!trusted(e)) return undefined
    // One install at a time: a second click waits for the first.
    if (!installing) {
      installing = install()
        .catch((): CompanionStatus => tell({ state: 'failed', line: "VS Code didn't install the companion." }))
        .finally(() => {
          installing = null
        })
    }
    return installing
  })
}
