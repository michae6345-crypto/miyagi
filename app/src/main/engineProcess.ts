/**
 * R44 (research/launch/SOLUTIONS.md): the engine this app started never outlives the app. No Electron here, so all of
 * it runs under plain node (test/engineProcess.test.ts); localEngine.ts wires it up.
 *
 *   Quit      SIGTERM the engine's whole process group (it spawns children), wait a few seconds, then SIGKILL the group.
 *             A hung engine ignores SIGTERM (a blocked uvicorn loop never acts on it), and one stopped with
 *             `kill -STOP` can't act on anything: only SIGKILL ends those.
 *   Pid file  ~/miyagi/engine/run/app-engine.json goes only once the engine and its group are confirmed gone. If they
 *             survive, the file stays, so the next launch can find them.
 *   Launch    A pid file naming a live process: stop it only when it is provably this app's engine (its exact command
 *             line, and a start time that matches the file's `at`), so a pid the OS has since given to another process
 *             is never touched. Port or no port: a hung engine may not answer, and its children hold no port.
 *   Windows   No process groups, and no SIGTERM a windowless process can act on: `taskkill /PID <pid> /T /F` ends the
 *             tree. (The Windows build doesn't start an engine yet, see whyUnmanaged; this keeps that path right.)
 */
import { execFile } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'

/** What the pid file holds: which process this app started as its engine, on which port, run which way, and when. */
export type PidRecord = { pid: number; port: number; runtime: string; at: string }

/** The pid file, or undefined when there is none or it can't be read (a half-written or hand-edited file). */
export function readPidRecord(file: string): PidRecord | undefined {
  try {
    const v = JSON.parse(readFileSync(file, 'utf8')) as Partial<Record<keyof PidRecord, unknown>>
    const pid = Number(v?.pid)
    if (!Number.isInteger(pid) || pid <= 0 || typeof v.at !== 'string') return undefined
    return { pid, port: Number(v.port) || 0, runtime: typeof v.runtime === 'string' ? v.runtime : '', at: v.at }
  } catch {
    return undefined
  }
}

/** Written owner-only (0600): it names a process of the user's. → whether it was written */
export function writePidRecord(file: string, rec: PidRecord): boolean {
  try {
    mkdirSync(dirname(file), { recursive: true })
    writeFileSync(file, JSON.stringify(rec), { mode: 0o600 })
    return true
  } catch {
    return false
  }
}

export function removePidRecord(file: string): void {
  try {
    rmSync(file, { force: true })
  } catch {
    // A stale pid file is checked against the process before it's ever used.
  }
}

/**
 * Signal 0: true while the process (pid > 0) or the process group (pid < 0, macOS and Linux only) exists. EPERM
 * counts as alive: it is there, it just isn't the user's (and so is never taken for this app's engine).
 */
export function processAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch (err) {
    return (err as NodeJS.ErrnoException)?.code === 'EPERM'
  }
}

/** Windows: end the process and everything it started. A missing taskkill.exe falls back to the process alone. */
export function taskkillTree(pid: number): void {
  const exe = join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'taskkill.exe')
  execFile(exe, ['/PID', String(pid), '/T', '/F'], { windowsHide: true, timeout: 5000 }, (err) => {
    // A non-zero exit (the process is already gone) has a numeric code; only a taskkill that didn't run has a string one.
    if (err && typeof (err as NodeJS.ErrnoException).code === 'string') {
      try {
        process.kill(pid)
      } catch {
        // Already gone.
      }
    }
  })
}

export type TreeDeps = {
  platform: string
  /** process.kill; the tests pass a fake, so they never signal a real pid. */
  kill: (pid: number, signal: NodeJS.Signals) => void
  /** taskkillTree; the tests pass a fake. */
  taskkill: (pid: number) => void
}

/**
 * Signal the engine and everything it started. macOS and Linux: the engine is spawned detached, so it leads its own
 * process group and -pid reaches its children too; `fallback` (the leader alone) when there's no group to signal.
 * Windows: taskkill /T /F for both signals (there's no graceful stop for a process with no window).
 */
export function signalTree(pid: number, sig: NodeJS.Signals, d: TreeDeps, fallback: (sig: NodeJS.Signals) => void): void {
  if (d.platform === 'win32') return d.taskkill(pid)
  try {
    d.kill(-pid, sig)
  } catch {
    try {
      fallback(sig)
    } catch {
      // Already gone.
    }
  }
}

/** Polls `cond` until it holds or `ms` have passed. → whether it held */
export async function waitFor(cond: () => boolean, ms: number, pollMs = 50): Promise<boolean> {
  for (const until = Date.now() + ms; ; ) {
    if (cond()) return true
    if (Date.now() >= until) return false
    await new Promise((r) => setTimeout(r, Math.max(1, Math.min(pollMs, until - Date.now()))))
  }
}

/** gone: it stopped on SIGTERM (or was gone already). killed: it took SIGKILL. alive: still there after SIGKILL. */
export type StopOutcome = 'gone' | 'killed' | 'alive'

/**
 * SIGTERM, up to `graceMs` for `gone()`, then SIGKILL and up to `confirmMs` more. `first: 'SIGKILL'` skips the grace
 * (a Restart's SIGTERM was already ignored). The first signal goes out before this returns its promise.
 */
export async function stopTree(o: {
  signal: (sig: NodeJS.Signals) => void
  gone: () => boolean
  graceMs: number
  confirmMs: number
  first?: 'SIGTERM' | 'SIGKILL'
  pollMs?: number
  onEscalate?: () => void
}): Promise<StopOutcome> {
  if (o.gone()) return 'gone'
  const first = o.first ?? 'SIGTERM'
  o.signal(first)
  if (first === 'SIGTERM') {
    if (await waitFor(o.gone, o.graceMs, o.pollMs)) return 'gone'
    o.onEscalate?.()
    o.signal('SIGKILL')
  }
  return (await waitFor(o.gone, o.confirmMs, o.pollMs)) ? 'killed' : 'alive'
}

/** The paths an engine this app starts runs from (localEngine.ts: the bundled Python, the launcher, the engine home). */
export type EnginePaths = { python: string; launcher: string; home: string }

/** Windows quotes a first token with spaces in it (`"C:\x y\python.exe" -m ...`); ps never does. */
function unquoteFirst(line: string): string {
  const m = /^"([^"]*)"(.*)$/s.exec(line)
  return m ? `${m[1]}${m[2]}` : line
}

/**
 * Whether `cmd` (a `ps -o command=` line) is an engine this app starts, and never anyone else's. The module name
 * alone also matches a dev engine (`.../run-live/.venv/bin/python -m server.orchestrator.main`), so it isn't enough.
 * Bundled: the exact Python inside this app. Launcher: the launcher script itself, or (when it `exec`s into Python)
 * an interpreter under this app's engine home running the engine module. `kind` is the pid file's runtime.
 */
export function isOwnEngineCommand(cmd: string, kind: unknown, p: EnginePaths): boolean {
  const line = unquoteFirst(cmd.trim())
  if (!line) return false
  if (kind !== 'launcher' && line.startsWith(`${p.python} `)) return true
  if (kind === 'bundled') return false
  const shells = ['', '/bin/bash ', 'bash ', '/bin/sh ', 'sh ', '/bin/zsh ']
  if (shells.some((sh) => line === `${sh}${p.launcher}` || line.startsWith(`${sh}${p.launcher} `))) return true
  return (line.startsWith(`${p.home}/`) || line.startsWith(`${p.home}\\`)) && /\s-m\s+server\.orchestrator\.main(\s|$)/.test(line)
}

/**
 * The process started within `slackMs` of the pid file's `at`, so a pid the OS has since handed to another process (a
 * dev engine started later from a shell, the same command line) is never taken for ours.
 */
export function startedNear(at: unknown, startedAt: number | undefined, slackMs = 10_000): boolean {
  const saved = typeof at === 'string' ? Date.parse(at) : NaN
  return Number.isFinite(saved) && typeof startedAt === 'number' && Number.isFinite(startedAt) && Math.abs(saved - startedAt) <= slackMs
}

/** A process's command line and start time (ms since the epoch, NaN when unknown). */
export type ProcInfo = { command: string; startedAt: number }

/** execFile, no shell, bounded: → { ok, out } */
function run(file: string, args: string[], timeout: number): Promise<{ ok: boolean; out: string }> {
  return new Promise((resolve) => {
    execFile(file, args, { timeout, maxBuffer: 8 << 20, windowsHide: true }, (err, stdout) => resolve({ ok: !err, out: String(stdout ?? '') }))
  })
}

/**
 * macOS / Linux: `ps -o lstart= -o command=` in the C locale (lstart is five words, local time). Windows: Win32_Process's
 * CommandLine and CreationDate through PowerShell. → undefined when there's no such process or it can't be read
 */
export async function processInfo(pid: number, platform: string = process.platform): Promise<ProcInfo | undefined> {
  if (!Number.isInteger(pid) || pid <= 0) return undefined
  if (platform === 'win32') {
    const ps = join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
    const script = `$p = Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}'; if ($p) { [Console]::Out.WriteLine($p.CreationDate.ToUniversalTime().ToString('o')); [Console]::Out.WriteLine($p.CommandLine) }`
    const r = await run(ps, ['-NoProfile', '-NonInteractive', '-Command', script], 15_000)
    const [when, ...rest] = r.out.replace(/\r/g, '').split('\n')
    if (!r.ok || !when?.trim()) return undefined
    return { startedAt: Date.parse(when.trim()), command: rest.join('\n').trim() }
  }
  // One -o per column: after `=`, procps takes the rest of the argument as the header.
  const r = await run('/usr/bin/env', ['LC_ALL=C', '/bin/ps', '-ww', '-o', 'lstart=', '-o', 'command=', '-p', String(pid)], 3000)
  const m = /^\s*(\S+\s+\S+\s+\S+\s+\S+\s+\S+)\s+(.*)$/s.exec(r.out.trim())
  if (!r.ok || !m) return undefined
  return { startedAt: Date.parse(m[1].replace(/\s+/g, ' ')), command: m[2].trim() }
}

/** macOS / Linux: the processes in process group `pgid` (pid and command line). Windows has no groups: []. */
export async function groupMembers(pgid: number, platform: string = process.platform): Promise<Array<{ pid: number; command: string }>> {
  if (platform === 'win32' || !Number.isInteger(pgid) || pgid <= 1) return []
  const r = await run('/bin/ps', ['-axww', '-o', 'pid=', '-o', 'pgid=', '-o', 'command='], 3000)
  if (!r.ok) return []
  const out: Array<{ pid: number; command: string }> = []
  for (const l of r.out.split('\n')) {
    const m = /^\s*(\d+)\s+(\d+)\s+(.*)$/.exec(l)
    if (m && Number(m[2]) === pgid) out.push({ pid: Number(m[1]), command: m[3].trim() })
  }
  return out
}

export type ReclaimDeps = TreeDeps & {
  /** processAlive (signal 0); a negative pid asks about the group. */
  alive: (pid: number) => boolean
  info: (pid: number) => Promise<ProcInfo | undefined>
  members: (pgid: number) => Promise<Array<{ pid: number; command: string }>>
  graceMs: number
  confirmMs: number
  /** engine.log */
  note: (msg: string) => void
  /** This app's own pid, never a target. */
  self: number
}

/**
 * none      no pid file
 * stale     a pid file naming nothing that runs (or unreadable): removed
 * foreign   the pid runs, but it isn't provably this app's engine (the OS reused the pid): removed, the process untouched
 * stopped   it was this app's engine from an earlier launch, and it and its group are gone now: removed
 * survived  this app's engine, still there after SIGKILL: the file stays, for the next launch
 */
export type ReclaimResult = 'none' | 'stale' | 'foreign' | 'stopped' | 'survived'

/**
 * Launch: stop an engine an earlier launch of this app left running (a quit it outlived, a force-quit, a crash), and
 * nothing else. `ours(cmd, runtime)` is isOwnEngineCommand with this build's paths.
 */
export async function reclaimLeftover(file: string, ours: (cmd: string, runtime: string) => boolean, d: ReclaimDeps): Promise<ReclaimResult> {
  if (!existsSync(file)) return 'none'
  const rec = readPidRecord(file)
  if (!rec || rec.pid <= 1 || rec.pid === d.self) {
    removePidRecord(file)
    return 'stale'
  }
  const { pid } = rec
  const posix = d.platform !== 'win32'
  const groupAlive = (): boolean => posix && d.alive(-pid)
  const leader = d.alive(pid)
  if (!leader && !groupAlive()) {
    removePidRecord(file)
    return 'stale'
  }
  let proof = ''
  if (leader) {
    const info = await d.info(pid)
    if (info && ours(info.command, rec.runtime) && startedNear(rec.at, info.startedAt)) proof = 'its command line and start time'
  } else {
    // The leader is gone but its group isn't (the launcher's shell died, its Python didn't). A group id is never
    // reused while the group exists, so only the engine's own children are in it; still, stop it only when one of
    // them runs this app's engine.
    const member = (await d.members(pid)).find((m) => ours(m.command, rec.runtime))
    if (member) proof = `its group still runs this app's engine (pid ${member.pid})`
  }
  if (!proof) {
    removePidRecord(file)
    return 'foreign'
  }
  d.note(`this app's engine from an earlier launch is still running (pid ${pid}, ${proof}): stopping its group`)
  const outcome = await stopTree({
    signal: (sig) =>
      signalTree(pid, sig, d, (s) => {
        if (d.alive(pid)) d.kill(pid, s)
      }),
    gone: () => !d.alive(pid) && !groupAlive(),
    graceMs: d.graceMs,
    confirmMs: d.confirmMs,
    onEscalate: () => d.note(`the earlier engine (pid ${pid}) ignored SIGTERM for ${d.graceMs / 1000} s; sending SIGKILL to its group`)
  })
  if (outcome === 'alive') {
    d.note(`the earlier engine (pid ${pid}) is still running after SIGKILL; keeping its pid file`)
    return 'survived'
  }
  removePidRecord(file)
  return 'stopped'
}
