/**
 * Core: the app starts the engine on this Mac when nobody else has (Michael's docs/DISTRIBUTION.md, app ask 1,
 * and "C", the self-contained app). One download: open miyagi and it works.
 *
 *   1. Only on macOS (the engine reads the screen with Vision / ScreenCaptureKit), only in a built app or with
 *      MIYAGI_AUTOSTART=1, never with DEMO=1, and only when ENGINE_URL is unset or points at this Mac.
 *   2. Something already answers on 127.0.0.1:<port> → use it. An engine started in Terminal stays the user's.
 *   3. ~/miyagi/engine/bin/miyagi-engine exists (Michael's installer made it) → start it.
 *   4. Missing, and this app carries the engine (Resources/engine: install.sh + src/, put there by
 *      scripts/bundle-engine.mjs) → copy the source to ~/miyagi/engine/src (keeping cached lessons), run
 *      `install.sh --src … --no-app --no-vscode --no-start --yes` once (uv + Python + packages: about a minute,
 *      needs the network), then start it. A newer bundled engine (app update) is installed the same way.
 *   5. Quit → stop only the engine this app started.
 *
 * Every window hears the state as feat:engine-local {state, line?}; bridge.invoke('engine-local:get') reads it.
 * The macOS Screen Recording prompt names miyagi (the app started the engine), not Terminal.
 */
import { app, clipboard, ipcMain, shell, type IpcMainInvokeEvent } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { cpSync, existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { connect } from 'node:net'
import { homedir } from 'node:os'
import { join } from 'node:path'
import type { EngineLink } from './engine'

export type LocalEngineState = 'off' | 'checking' | 'installing' | 'starting' | 'running' | 'external' | 'missing' | 'failed'
export type LocalEngineStatus = { state: LocalEngineState; line?: string; logs?: string }

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

/** A Finder-launched app has a bare PATH; the installer and the launcher need uv, git, curl. */
function fixedPath(home: string): string {
  const extra = [join(home, 'bin'), join(homedir(), '.local/bin'), '/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin']
  return [...extra, process.env.PATH ?? ''].filter(Boolean).join(':')
}

const readText = (p: string): string => {
  try {
    return readFileSync(p, 'utf8').trim()
  } catch {
    return ''
  }
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
  const launcher = join(home, 'bin', 'miyagi-engine')
  const logs = join(home, 'logs', 'engine.log')
  const bundle = join(process.resourcesPath, 'engine')
  const bundled = existsSync(join(bundle, 'install.sh')) && existsSync(join(bundle, 'src', 'server', 'pyproject.toml'))
  const env = { ...process.env, MIYAGI_HOME: home, PATH: fixedPath(home), MIYAGI_ENGINE_TOKEN: ENGINE_TOKEN }

  engine.onStatus((up) => {
    if (up && status.state !== 'running' && status.state !== 'external') set({ state: child ? 'running' : 'external' })
  })

  /** Copy the bundled source into ~/miyagi/engine/src (learner's cached lessons kept), then run the installer on it. */
  const install = (): Promise<boolean> =>
    new Promise((resolve) => {
      set({ state: 'installing', line: 'Copying the engine' })
      try {
        mkdirSync(home, { recursive: true })
        const src = join(home, 'src')
        const next = join(home, 'src.new')
        const old = join(home, 'src.old')
        rmSync(next, { recursive: true, force: true })
        cpSync(join(bundle, 'src'), next, { recursive: true })
        rmSync(old, { recursive: true, force: true })
        if (existsSync(src)) renameSync(src, old)
        renameSync(next, src)
        // Built lessons, searches and transcripts are cached in src/demo/cache: the new source's files win.
        if (existsSync(join(old, 'demo', 'cache'))) cpSync(join(old, 'demo', 'cache'), join(src, 'demo', 'cache'), { recursive: true, force: false, errorOnExist: false })
        rmSync(old, { recursive: true, force: true })
      } catch (err) {
        set({ state: 'failed', line: `Couldn't copy the engine: ${String(err).slice(0, 120)}`, logs })
        return resolve(false)
      }
      const p = spawn('bash', [join(bundle, 'install.sh'), '--src', join(home, 'src'), '--no-app', '--no-vscode', '--no-start', '--yes'], { env, stdio: ['ignore', 'pipe', 'pipe'] })
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
          writeFileSync(join(home, 'BUNDLED'), readText(join(bundle, 'VERSION')) || 'bundled')
          resolve(true)
        } else {
          set({ state: 'failed', line: `Setup stopped (exit ${code}). Check the network, then reopen miyagi.`, logs })
          resolve(false)
        }
      })
    })

  const start = (): void => {
    set({ state: 'starting' })
    // Its own process group, so quitting stops the launcher AND the Python it starts (see the cleanup below).
    child = spawn(launcher, [], { env, stdio: 'ignore', detached: true })
    child.on('error', (err) => {
      child = undefined
      set({ state: 'failed', line: `Couldn't start the engine: ${err.message}`, logs })
    })
    child.on('exit', (code) => {
      const wasRunning = status.state === 'running'
      child = undefined
      if (stopping) return set({ state: 'off' })
      if (restarting) {
        restarting = false
        return start()
      }
      // exit 1 right away = "port already in use": someone else's engine is up, the link will find it.
      if (!wasRunning) set(code === 1 ? { state: 'external' } : { state: 'failed', line: `The engine stopped (exit ${code}).`, logs })
      else set({ state: 'failed', line: 'The engine stopped.', logs })
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
      set({ state: 'starting', line: 'Restarting the engine' })
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
    // A newer engine inside the app (an app update) replaces one the app installed before; never one the
    // user installed with the one-liner (no BUNDLED marker).
    const installedFromBundle = existsSync(join(home, 'BUNDLED'))
    const stale = bundled && installedFromBundle && readText(join(home, 'BUNDLED')) !== readText(join(bundle, 'VERSION'))
    if ((!existsSync(launcher) || stale) && bundled) {
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
