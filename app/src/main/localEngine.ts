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
import { app, clipboard, ipcMain, shell } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { connect } from 'node:net'
import { homedir } from 'node:os'
import { join } from 'node:path'
import type { EngineLink } from './engine'

export type LocalEngineState = 'off' | 'checking' | 'installing' | 'starting' | 'running' | 'external' | 'missing' | 'failed'
export type LocalEngineStatus = { state: LocalEngineState; line?: string; logs?: string }

/** Michael's installer (docs/INSTALL.md), for a Mac where the app carries no engine. */
const ONE_LINER = 'curl -fsSL https://raw.githubusercontent.com/michae6345-crypto/sandhacks-tutor/integration/live/scripts/install.sh | bash'

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

export function setupLocalEngine(engine: EngineLink, url: string, broadcast: (channel: string, payload: unknown) => void): () => void {
  let status: LocalEngineStatus = { state: 'off' }
  let child: ChildProcess | undefined
  /** We're quitting: the engine's exit is ours, not a crash. */
  let stopping = false
  const set = (next: LocalEngineStatus): void => {
    status = next
    broadcast('engine-local', status)
  }
  ipcMain.handle('feat:engine-local:get', () => status)
  ipcMain.handle('feat:engine-local:command', () => ONE_LINER)
  // The pill's "Install the engine": the one-liner on the clipboard. "Engine didn't start": open its log.
  ipcMain.handle('feat:engine-local:copy', () => {
    clipboard.writeText(ONE_LINER)
    return true
  })
  ipcMain.handle('feat:engine-local:logs', async () => {
    const file = status.logs ?? ''
    return file && existsSync(file) ? (await shell.openPath(file)) === '' : false
  })

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
  const env = { ...process.env, MIYAGI_HOME: home, PATH: fixedPath(home) }

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
      // exit 1 right away = "port already in use": someone else's engine is up, the link will find it.
      if (!wasRunning) set(code === 1 ? { state: 'external' } : { state: 'failed', line: `The engine stopped (exit ${code}).`, logs })
      else set({ state: 'failed', line: 'The engine stopped.', logs })
    })
  }

  void (async () => {
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
  })()

  return () => {
    // Only the engine this app started (never one the user runs in Terminal). SIGTERM lets uvicorn close its
    // sockets; the whole group, in case the launcher didn't `exec` into Python.
    if (!child || child.killed || child.pid === undefined) return
    stopping = true
    try {
      process.kill(-child.pid, 'SIGTERM')
    } catch {
      child.kill('SIGTERM')
    }
  }
}
