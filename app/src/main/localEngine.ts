/**
 * Core: the app starts the engine on this Mac when nobody else has (Michael's docs/DISTRIBUTION.md, app ask 1,
 * and "C", the self-contained app). One download: open miyagi and it works, offline, in seconds.
 *
 *   1. Only on macOS (the engine reads the screen with Vision / ScreenCaptureKit), only in a built app or with
 *      MIYAGI_AUTOSTART=1, never with DEMO=1, and only when ENGINE_URL is unset or points at this Mac.
 *   2. Something already answers on 127.0.0.1:<port> → use it. An engine started in Terminal stays the user's.
 *   3. ~/miyagi/engine/bin/miyagi-engine exists with no BUNDLED marker (the user ran Michael's one-liner) → start it.
 *      The app never replaces an engine the user installed.
 *   4. A12 (DISTRIBUTION-PLAN.md section 2): this app carries a standalone Python with the engine's packages
 *      (Resources/engine/python + src/, put there by scripts/bundle-engine.mjs) → copy the source to
 *      ~/miyagi/engine/src once per bundled version (cached lessons kept), then start
 *      `Resources/engine/python/bin/python3 -m server.orchestrator.main --host 127.0.0.1` directly. No uv, no Python
 *      download, no network; nothing is written inside the signed app (PYTHONDONTWRITEBYTECODE=1, all precompiled).
 *   5. Older bundles (install.sh + src/, no python/): run `install.sh --src … --no-app --no-vscode --no-start --yes`
 *      once (uv + Python + packages: about a minute, needs the network), then start the launcher it writes.
 *   6. Quit → stop only the engine this app started.
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
import { execFile, spawn, type ChildProcess } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { accessSync, closeSync, constants, existsSync, mkdirSync, openSync, readFileSync, writeFileSync, writeSync } from 'node:fs'
import { cp, rename, rm } from 'node:fs/promises'
import { connect } from 'node:net'
import { homedir } from 'node:os'
import { basename, join } from 'node:path'
import type { EngineLink } from './engine'

export type LocalEngineState = 'off' | 'checking' | 'installing' | 'starting' | 'running' | 'external' | 'missing' | 'failed'
/** `runtime`: which way this app runs the engine. bundled = the Python inside the app; launcher = ~/miyagi/engine/bin. */
export type LocalEngineStatus = { state: LocalEngineState; line?: string; logs?: string; runtime?: 'bundled' | 'launcher' }

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

/** v2: the latest state, for core modules that need it (main/permissions.ts: 'external' means grants are unknown). */
let current: LocalEngineStatus = { state: 'off' }
export function localEngineState(): LocalEngineState {
  return current.state
}

/**
 * v2 (W0-5): a per-launch engine token. 32 random bytes, made once per app launch, kept in memory only: passed to the
 * engine this app starts in its environment (MIYAGI_ENGINE_TOKEN, never on a command line) and sent back by the link
 * as a header, so a page in a browser or another local process can't drive the engine (the engine checks it, E2).
 * MIYAGI_ENGINE_TOKEN already in this app's environment (dev, an engine started by hand with the same value) wins.
 */
export const ENGINE_TOKEN: string = process.env.MIYAGI_ENGINE_TOKEN?.trim() || randomBytes(32).toString('base64url')

/**
 * `trusted`: main's sender check (index.ts trustedSender). Every handler here answers only our own windows; an
 * untrusted sender gets undefined / false and, for restart, nothing is stopped or spawned.
 */
export function setupLocalEngine(
  engine: EngineLink,
  url: string,
  broadcast: (channel: string, payload: unknown) => void,
  trusted: (e: IpcMainInvokeEvent) => boolean
): () => void {
  let status: LocalEngineStatus = { state: 'off' }
  let child: ChildProcess | undefined
  /** We're quitting: the engine's exit is ours, not a crash. */
  let stopping = false
  /** feat:engine-local:restart is stopping the engine: start it again when it exits. */
  let restarting = false
  const set = (next: LocalEngineStatus): void => {
    status = next
    current = next
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

  // The companion works whether or not this app manages the engine (an engine in Terminal still talks to it).
  setupCompanion(broadcast, trusted)

  const port = (() => {
    try {
      return Number(new URL(url).port) || 8787
    } catch {
      return 8787
    }
  })()
  const local = /^wss?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?\/?$/i.test(url)
  const wanted = process.platform === 'darwin' && (app.isPackaged || process.env.MIYAGI_AUTOSTART === '1') && process.env.DEMO !== '1' && local
  if (!wanted) return () => undefined

  const home = process.env.MIYAGI_HOME || join(homedir(), 'miyagi', 'engine')
  const src = join(home, 'src')
  const launcher = join(home, 'bin', 'miyagi-engine')
  const logs = join(home, 'logs', 'engine.log')
  const marker = join(home, 'BUNDLED')
  const bundle = bundleDir()
  const bundleVersion = (): string => readText(join(bundle, 'VERSION')) || 'bundled'
  const hasSource = existsSync(join(bundle, 'src', 'server', 'pyproject.toml'))
  const python = join(bundle, 'python', 'bin', 'python3')
  /** A12: the app carries its own Python with the packages installed. */
  const pythonBundled = hasSource && executable(python)
  /** Older bundles: source + the uv installer. */
  const installerBundled = hasSource && existsSync(join(bundle, 'install.sh'))
  const env: NodeJS.ProcessEnv = { ...process.env, MIYAGI_HOME: home, PATH: fixedPath(home), MIYAGI_ENGINE_TOKEN: ENGINE_TOKEN }
  /** Which way start() runs the engine; boot() decides. */
  let runtime: 'bundled' | 'launcher' = 'launcher'

  engine.onStatus((up) => {
    if (up && status.state !== 'running' && status.state !== 'external') set({ state: child ? 'running' : 'external', runtime: child ? runtime : undefined })
  })

  /**
   * Copy the bundled source into ~/miyagi/engine/src: next to it first, then swap, so a crash mid-copy never leaves a
   * half tree. Built lessons, searches and transcripts are cached in src/demo/cache: kept, and the new source's files
   * win. Async so the first launch never blocks the main process. → ok
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
      await rm(old, { recursive: true, force: true })
      if (existsSync(src)) await rename(src, old)
      await rename(next, src)
      if (existsSync(join(old, 'demo', 'cache'))) await cp(join(old, 'demo', 'cache'), join(src, 'demo', 'cache'), { recursive: true, force: false, errorOnExist: false })
      await rm(old, { recursive: true, force: true })
      return true
    } catch (err) {
      set({ state: 'failed', line: `Couldn't copy the engine: ${String(err).slice(0, 120)}`, logs })
      return false
    }
  }

  /** Older bundles: copy the source, then run the uv installer on it (about a minute, needs the network). */
  const install = async (): Promise<boolean> => {
    if (!(await copySource())) return false
    return new Promise((resolve) => {
      const p = spawn('bash', [join(bundle, 'install.sh'), '--src', src, '--no-app', '--no-vscode', '--no-start', '--yes'], { env, stdio: ['ignore', 'pipe', 'pipe'] })
      const onData = (b: Buffer): void => {
        // eslint-disable-next-line no-control-regex
        const last = b.toString().replace(/\x1b\[[0-9;]*m/g, '').split('\n').map((l) => l.replace(/^\[miyagi\]\s*/, '').trim()).filter(Boolean).pop()
        if (last) set({ state: 'installing', line: last.slice(0, 90) })
      }
      p.stdout?.on('data', onData)
      p.stderr?.on('data', onData)
      p.on('error', () => resolve(false))
      p.on('exit', (code) => {
        if (code === 0) {
          writeFileSync(marker, bundleVersion())
          resolve(true)
        } else {
          set({ state: 'failed', line: `Setup stopped (exit ${code}). Check the network, then reopen miyagi.`, logs })
          resolve(false)
        }
      })
    })
  }

  /**
   * The bundled Python's environment: the launcher's defaults (scripts/install.sh writes the same ones), the user's
   * own values win, and nothing from a shell's Python setup leaks in (PYTHONHOME, a venv, user site-packages).
   */
  const pythonEnv = (): NodeJS.ProcessEnv => {
    const e: NodeJS.ProcessEnv = { ...env }
    for (const k of ['PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONEXECUTABLE', 'VIRTUAL_ENV', '__PYVENV_LAUNCHER__', 'CONDA_PREFIX']) delete e[k]
    return {
      ...e,
      PYTHONPATH: src,
      PYTHONNOUSERSITE: '1',
      PYTHONDONTWRITEBYTECODE: '1',
      PYTHONUNBUFFERED: '1',
      // workspace/setup.py builds lesson .venvs from this when the Mac has no other Python 3 (engine side, E-lane).
      MIYAGI_BUNDLED_PYTHON: python,
      PYTHON: python,
      TUT_ENV: e.TUT_ENV || join(home, 'engine.env'),
      ENGINE_HOST: '127.0.0.1',
      ENGINE_PORT: String(port),
      ORCH_SCREEN: e.ORCH_SCREEN || '1',
      ORCH_OPEN_WORKSPACE: e.ORCH_OPEN_WORKSPACE || '1',
      ORCH_AUTOSTART: e.ORCH_AUTOSTART || '0',
      LESSON_ENGINE: e.LESSON_ENGINE || 'claude',
      MIYAGI_EDITOR: e.MIYAGI_EDITOR || 'vscode',
    }
  }

  /** Spawn the engine. Its own process group, so quitting stops it and anything it started (see killGroup). */
  const spawnEngine = (): ChildProcess => {
    if (runtime === 'launcher') return spawn(launcher, [], { env, stdio: 'ignore', detached: true })
    // Bundled Python: no launcher script in between, so this app writes the log the launcher would have.
    mkdirSync(join(home, 'logs'), { recursive: true })
    const fd = openSync(logs, 'a')
    try {
      writeSync(fd, `--- ${new Date().toISOString()} engine start (bundled Python, ${bundleVersion()})\n`)
      return spawn(python, ['-m', 'server.orchestrator.main', '--host', '127.0.0.1', '--port', String(port)], {
        cwd: src,
        env: pythonEnv(),
        stdio: ['ignore', fd, fd],
        detached: true,
      })
    } finally {
      // The child has its own copy of the descriptor.
      closeSync(fd)
    }
  }

  const start = (): void => {
    set({ state: 'starting', runtime })
    try {
      child = spawnEngine()
    } catch (err) {
      child = undefined
      return set({ state: 'failed', line: `Couldn't start the engine: ${String(err).slice(0, 120)}`, logs, runtime })
    }
    child.on('error', (err) => {
      child = undefined
      set({ state: 'failed', line: `Couldn't start the engine: ${err.message}`, logs, runtime })
    })
    child.on('exit', (code) => {
      const wasRunning = status.state === 'running'
      child = undefined
      if (stopping) return set({ state: 'off' })
      if (restarting) {
        restarting = false
        return start()
      }
      if (wasRunning) return set({ state: 'failed', line: 'The engine stopped.', logs, runtime })
      // exit 1 right away can be "port already in use" (someone else's engine is up, the link will find it), or a
      // Python error on start. Only the port can tell them apart.
      const failed: LocalEngineStatus = { state: 'failed', line: `The engine stopped (exit ${code}).`, logs, runtime }
      if (code !== 1) return set(failed)
      void listening(port).then((up) => set(up ? { state: 'external' } : failed))
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
    if (status.state === 'checking' || status.state === 'installing' || status.state === 'starting') return { ok: true, state: status.state }
    void boot()
    return { ok: true, state: 'checking' }
  }

  const boot = async (): Promise<void> => {
    set({ state: 'checking' })
    if (await listening(port)) return set({ state: 'external' })
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
    if (!existsSync(launcher)) return set({ state: 'missing', line: ONE_LINER })
    start()
  }
  void boot()

  return () => {
    // Only the engine this app started (never one the user runs in Terminal). SIGTERM lets uvicorn close its
    // sockets; the whole group, in case the launcher didn't `exec` into Python.
    if (!child || child.killed || child.pid === undefined) return
    stopping = true
    killGroup(child)
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

/** VS Code's own CLI: the two usual app folders, then Spotlight by bundle id (only Visual Studio Code itself). */
async function findCodeCli(): Promise<string | null> {
  const inApp = (a: string): string => join(a, CODE_IN_APP, 'code')
  for (const a of VSCODE_APPS) if (executable(inApp(a))) return inApp(a)
  const found = await run('/usr/bin/mdfind', [`kMDItemCFBundleIdentifier == '${VSCODE_BUNDLE_ID}'`], 5000)
  for (const a of found.out.split('\n').map((l) => l.trim())) {
    if (a.endsWith('.app') && executable(inApp(a))) return inApp(a)
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
