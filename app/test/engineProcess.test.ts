/**
 * R44 (research/launch/SOLUTIONS.md), main/engineProcess.ts: the pid file, the group stop and the launch reclaim.
 * Fakes for every signal except the last describe, which starts its own two node processes (a leader that ignores
 * SIGTERM, stopped with SIGSTOP on macOS / Linux, and a child of it) and stops only those.
 */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, describe, test } from 'node:test'
import {
  isOwnEngineCommand,
  processAlive,
  processInfo,
  readPidRecord,
  reclaimLeftover,
  removePidRecord,
  signalTree,
  startedNear,
  stopTree,
  taskkillTree,
  writePidRecord,
  type ReclaimDeps
} from '../src/main/engineProcess'

const sandbox = mkdtempSync(join(tmpdir(), 'miyagi-engine-process-'))
after(() => rmSync(sandbox, { recursive: true, force: true }))
let n = 0
const pidFile = (): string => join(sandbox, `run-${++n}`, 'app-engine.json')

const HOME = '/Users/learner/miyagi/engine'
const PATHS = { python: '/Applications/miyagi.app/Contents/Resources/engine/python/bin/python3', launcher: `${HOME}/bin/miyagi-engine`, home: HOME }
const ours = (cmd: string, kind: unknown): boolean => isOwnEngineCommand(cmd, kind, PATHS)
const BUNDLED_CMD = `${PATHS.python} -s -B -m server.orchestrator.main --host 127.0.0.1 --port 8787`

describe('the pid file', () => {
  test('round trip, owner-only', () => {
    const f = pidFile()
    const at = new Date().toISOString()
    assert.equal(writePidRecord(f, { pid: 4321, port: 8787, runtime: 'bundled', at }), true)
    assert.deepEqual(readPidRecord(f), { pid: 4321, port: 8787, runtime: 'bundled', at })
    if (process.platform !== 'win32') assert.equal(statSync(f).mode & 0o777, 0o600)
    removePidRecord(f)
    assert.equal(existsSync(f), false)
    removePidRecord(f)
  })
  test('a missing, half-written or hand-edited file reads as nothing', () => {
    const f = pidFile()
    assert.equal(readPidRecord(f), undefined)
    writePidRecord(f, { pid: 1, port: 1, runtime: 'x', at: 'y' })
    for (const body of ['{"pid":', '{"pid":"abc","at":"x"}', '{"pid":-5,"at":"x"}', '{"pid":12}', '[]', 'null']) {
      writeFileSync(f, body)
      assert.equal(readPidRecord(f), undefined, body)
    }
  })
})

describe('isOwnEngineCommand: this app engine, never anyone else', () => {
  test('bundled: the exact Python inside this app', () => {
    assert.equal(ours(BUNDLED_CMD, 'bundled'), true)
    assert.equal(ours(`${PATHS.python}x -m server.orchestrator.main`, 'bundled'), false)
  })
  test('a dev engine runs the same module from another Python: not ours', () => {
    assert.equal(ours('/Users/learner/code/miyagi/run-live/.venv/bin/python -m server.orchestrator.main', 'bundled'), false)
    assert.equal(ours('/Users/learner/code/miyagi/run-live/.venv/bin/python -m server.orchestrator.main', 'launcher'), false)
    assert.equal(ours('/usr/bin/python3 -m server.orchestrator.main', undefined), false)
  })
  test('launcher: the script itself, through a shell, or its Python under the engine home', () => {
    assert.equal(ours(PATHS.launcher, 'launcher'), true)
    assert.equal(ours(`/bin/bash ${PATHS.launcher}`, 'launcher'), true)
    assert.equal(ours(`${HOME}/.venv/bin/python -m server.orchestrator.main --port 8787`, 'launcher'), true)
    assert.equal(ours(`${HOME}/.venv/bin/python -m something.else`, 'launcher'), false)
    assert.equal(ours(PATHS.launcher, 'bundled'), false, 'a bundled pid file never matches the launcher')
  })
  test('Windows quotes a first token with spaces', () => {
    const win = { python: 'C:\\Program Files\\miyagi\\resources\\engine\\python\\python.exe', launcher: 'C:\\Users\\l\\miyagi\\engine\\bin\\miyagi-engine.cmd', home: 'C:\\Users\\l\\miyagi\\engine' }
    assert.equal(isOwnEngineCommand(`"${win.python}" -s -B -m server.orchestrator.main`, 'bundled', win), true)
    assert.equal(isOwnEngineCommand(`"C:\\Python312\\python.exe" -m server.orchestrator.main`, 'bundled', win), false)
  })
  test('empty is never ours', () => assert.equal(ours('  ', undefined), false))
})

describe('startedNear: a reused pid started at another time', () => {
  const at = '2026-11-21T18:00:00.000Z'
  test('within 10 s of the file', () => {
    assert.equal(startedNear(at, Date.parse(at) + 900), true)
    assert.equal(startedNear(at, Date.parse(at) - 9_000), true)
  })
  test('later, earlier, or unknown: not ours', () => {
    assert.equal(startedNear(at, Date.parse(at) + 60_000), false)
    assert.equal(startedNear(at, Date.parse(at) - 11_000), false)
    assert.equal(startedNear(at, NaN), false)
    assert.equal(startedNear('not a date', Date.parse(at)), false)
    assert.equal(startedNear(undefined, Date.parse(at)), false)
  })
})

describe('signalTree', () => {
  const rec = (): { calls: Array<[number, string]>; kill: (pid: number, sig: NodeJS.Signals) => void } => {
    const calls: Array<[number, string]> = []
    return { calls, kill: (pid, sig) => void calls.push([pid, sig]) }
  }
  test('macOS: the whole group (-pid)', () => {
    const r = rec()
    signalTree(4242, 'SIGTERM', { platform: 'darwin', kill: r.kill, taskkill: () => assert.fail('no taskkill on a Mac') }, () => assert.fail('no fallback'))
    assert.deepEqual(r.calls, [[-4242, 'SIGTERM']])
  })
  test('no group to signal: the fallback', () => {
    const fell: string[] = []
    signalTree(
      4242,
      'SIGKILL',
      {
        platform: 'darwin',
        kill: () => {
          throw Object.assign(new Error('ESRCH'), { code: 'ESRCH' })
        },
        taskkill: () => assert.fail('no taskkill')
      },
      (s) => void fell.push(s)
    )
    assert.deepEqual(fell, ['SIGKILL'])
  })
  test('Windows: taskkill /T /F for both signals, never a negative pid', () => {
    const r = rec()
    const tk: number[] = []
    for (const sig of ['SIGTERM', 'SIGKILL'] as const) signalTree(4242, sig, { platform: 'win32', kill: r.kill, taskkill: (p) => void tk.push(p) }, () => assert.fail('no fallback'))
    assert.deepEqual(tk, [4242, 4242])
    assert.deepEqual(r.calls, [])
  })
})

describe('stopTree: SIGTERM, a grace, then SIGKILL', () => {
  const run = async (onSignal: (sig: string) => boolean, o: { first?: 'SIGTERM' | 'SIGKILL'; goneAlready?: boolean } = {}): Promise<{ outcome: string; sent: string[]; ms: number }> => {
    const sent: string[] = []
    let gone = !!o.goneAlready
    const t = Date.now()
    const outcome = await stopTree({
      signal: (sig) => {
        sent.push(sig)
        if (onSignal(sig)) setTimeout(() => (gone = true), 5)
      },
      gone: () => gone,
      graceMs: 120,
      confirmMs: 80,
      pollMs: 10,
      first: o.first
    })
    return { outcome, sent, ms: Date.now() - t }
  }
  test('an engine that obeys SIGTERM gets no SIGKILL', async () => {
    const r = await run((sig) => sig === 'SIGTERM')
    assert.equal(r.outcome, 'gone')
    assert.deepEqual(r.sent, ['SIGTERM'])
  })
  test('a hung (or stopped) engine gets SIGKILL after the grace', async () => {
    const r = await run((sig) => sig === 'SIGKILL')
    assert.equal(r.outcome, 'killed')
    assert.deepEqual(r.sent, ['SIGTERM', 'SIGKILL'])
    assert.ok(r.ms >= 110, `waited ${r.ms} ms`)
  })
  test('one that outlives SIGKILL is reported alive (the caller keeps the pid file)', async () => {
    const r = await run(() => false)
    assert.equal(r.outcome, 'alive')
    assert.deepEqual(r.sent, ['SIGTERM', 'SIGKILL'])
    assert.ok(r.ms >= 190, `waited ${r.ms} ms`)
  })
  test("first: 'SIGKILL' skips the grace", async () => {
    const r = await run((sig) => sig === 'SIGKILL', { first: 'SIGKILL' })
    assert.equal(r.outcome, 'killed')
    assert.deepEqual(r.sent, ['SIGKILL'])
  })
  test('already gone: nothing is sent', async () => {
    const r = await run(() => true, { goneAlready: true })
    assert.equal(r.outcome, 'gone')
    assert.deepEqual(r.sent, [])
  })
  test('the first signal goes out before the promise is awaited', () => {
    const sent: string[] = []
    void stopTree({ signal: (s) => void sent.push(s), gone: () => sent.length > 0, graceMs: 50, confirmMs: 50 })
    assert.deepEqual(sent, ['SIGTERM'])
  })
})

describe('reclaimLeftover: the next launch stops a stray engine of its own, and nothing else', () => {
  const AT = new Date(Date.now() - 3_600_000).toISOString()
  type World = { alive: Set<number>; kills: Array<[number, string]>; taskkills: number[]; notes: string[]; infos: Map<number, { command: string; startedAt: number }>; members: Map<number, Array<{ pid: number; command: string }>> }
  const world = (): World => ({ alive: new Set(), kills: [], taskkills: [], notes: [], infos: new Map(), members: new Map() })
  /** `dies` decides which signal ends the pid and its group. */
  const deps = (w: World, dies: (sig: string) => boolean, platform = 'darwin'): ReclaimDeps => ({
    platform,
    alive: (pid) => w.alive.has(pid),
    kill: (pid, sig) => {
      w.kills.push([pid, sig])
      if (!w.alive.has(pid)) throw Object.assign(new Error('ESRCH'), { code: 'ESRCH' })
      if (dies(sig)) {
        w.alive.delete(Math.abs(pid))
        w.alive.delete(-Math.abs(pid))
      }
    },
    taskkill: (pid) => {
      w.taskkills.push(pid)
      w.alive.delete(pid)
    },
    info: async (pid) => w.infos.get(pid),
    members: async (pgid) => w.members.get(pgid) ?? [],
    graceMs: 100,
    confirmMs: 60,
    note: (m) => void w.notes.push(m),
    self: 777
  })
  const withFile = (pid: number, runtime = 'bundled', at = AT): string => {
    const f = pidFile()
    writePidRecord(f, { pid, port: 8787, runtime, at })
    return f
  }
  const stray = (w: World, pid: number, command = BUNDLED_CMD, startedAt = Date.parse(AT) + 400): void => {
    w.alive.add(pid)
    w.alive.add(-pid)
    w.infos.set(pid, { command, startedAt })
  }

  test('no pid file: nothing to do', async () => {
    const w = world()
    assert.equal(await reclaimLeftover(pidFile(), ours, deps(w, () => true)), 'none')
    assert.deepEqual(w.kills, [])
  })
  test('a pid that no longer runs: the file goes, nothing is signalled', async () => {
    const w = world()
    const f = withFile(5001)
    assert.equal(await reclaimLeftover(f, ours, deps(w, () => true)), 'stale')
    assert.equal(existsSync(f), false)
    assert.deepEqual(w.kills, [])
  })
  test('an unreadable file, pid 1, or this app itself: the file goes, nothing is signalled', async () => {
    for (const pid of [1, 777]) {
      const w = world()
      stray(w, pid)
      const f = withFile(pid)
      assert.equal(await reclaimLeftover(f, ours, deps(w, () => true)), 'stale')
      assert.equal(existsSync(f), false)
      assert.deepEqual(w.kills, [])
    }
    const f = pidFile()
    writePidRecord(f, { pid: 5, port: 1, runtime: '', at: AT })
    writeFileSync(f, '{"pid":')
    assert.equal(await reclaimLeftover(f, ours, deps(world(), () => true)), 'stale')
    assert.equal(existsSync(f), false)
  })
  test('the pid now runs something else (reused): never touched, the file goes', async () => {
    const w = world()
    stray(w, 5002, '/Applications/Safari.app/Contents/MacOS/Safari')
    const f = withFile(5002)
    assert.equal(await reclaimLeftover(f, ours, deps(w, () => true)), 'foreign')
    assert.deepEqual(w.kills, [])
    assert.ok(w.alive.has(5002))
    assert.equal(existsSync(f), false)
  })
  test('the same command line but started at another time (reused by a later engine): never touched', async () => {
    const w = world()
    stray(w, 5003, BUNDLED_CMD, Date.now())
    const f = withFile(5003)
    assert.equal(await reclaimLeftover(f, ours, deps(w, () => true)), 'foreign')
    assert.deepEqual(w.kills, [])
  })
  test('ours, and it obeys SIGTERM: its group gets SIGTERM, the file goes', async () => {
    const w = world()
    stray(w, 5004)
    const f = withFile(5004)
    assert.equal(await reclaimLeftover(f, ours, deps(w, (s) => s === 'SIGTERM')), 'stopped')
    assert.deepEqual(w.kills, [[-5004, 'SIGTERM']])
    assert.equal(existsSync(f), false)
    assert.match(w.notes.join('\n'), /pid 5004/)
  })
  test('ours and hung (or kill -STOP): SIGKILL to the group after the grace, then the file goes', async () => {
    const w = world()
    stray(w, 5005)
    const f = withFile(5005)
    assert.equal(await reclaimLeftover(f, ours, deps(w, (s) => s === 'SIGKILL')), 'stopped')
    assert.deepEqual(w.kills, [
      [-5005, 'SIGTERM'],
      [-5005, 'SIGKILL']
    ])
    assert.equal(existsSync(f), false)
  })
  test('ours and it survives SIGKILL: the file stays for the next launch', async () => {
    const w = world()
    stray(w, 5006)
    const f = withFile(5006)
    assert.equal(await reclaimLeftover(f, ours, deps(w, () => false)), 'survived')
    assert.equal(existsSync(f), true)
    assert.equal(readPidRecord(f)?.pid, 5006)
  })
  test('the leader is gone but its group still runs this app engine (the launcher shell died): the group is stopped', async () => {
    const w = world()
    w.alive.add(-5007)
    w.members.set(5007, [{ pid: 5099, command: `${HOME}/.venv/bin/python -m server.orchestrator.main --port 8787` }])
    const f = withFile(5007, 'launcher')
    assert.equal(await reclaimLeftover(f, ours, deps(w, (s) => s === 'SIGKILL')), 'stopped')
    assert.deepEqual(w.kills, [
      [-5007, 'SIGTERM'],
      [-5007, 'SIGKILL']
    ])
    assert.equal(existsSync(f), false)
  })
  test('the leader is gone and its group runs nothing of this app: never touched', async () => {
    const w = world()
    w.alive.add(-5008)
    w.members.set(5008, [{ pid: 5100, command: '/bin/zsh -l' }])
    const f = withFile(5008, 'launcher')
    assert.equal(await reclaimLeftover(f, ours, deps(w, () => true)), 'foreign')
    assert.deepEqual(w.kills, [])
  })
  test('Windows: taskkill /T /F on the tree, no group checks', async () => {
    const w = world()
    w.alive.add(5009)
    w.infos.set(5009, { command: BUNDLED_CMD, startedAt: Date.parse(AT) })
    const f = withFile(5009)
    assert.equal(await reclaimLeftover(f, ours, deps(w, () => true, 'win32')), 'stopped')
    assert.deepEqual(w.taskkills, [5009])
    assert.deepEqual(w.kills, [])
    assert.equal(existsSync(f), false)
  })
})

describe('real processes (only the two this test starts)', () => {
  test('a leader that ignores SIGTERM (stopped with SIGSTOP on macOS / Linux) and its child both end', async () => {
    const posix = process.platform !== 'win32'
    const marker = `miyagi-r44-test-${process.pid}`
    // Each exits on its own after 20 s, so nothing outlives a failed run.
    const grand = "process.on('SIGTERM',()=>{});setTimeout(()=>{},20000)"
    const leader = `process.on('SIGTERM',()=>{});const g=require('child_process').spawn(process.execPath,['-e',${JSON.stringify(grand)}],{stdio:'ignore',windowsHide:true});process.stdout.write(String(g.pid)+'\\n');setTimeout(()=>{},20000)`
    const child = spawn(process.execPath, ['-e', leader, marker], { detached: true, stdio: ['ignore', 'pipe', 'ignore'], windowsHide: true })
    let exited = false
    child.on('exit', () => (exited = true))
    try {
      const grandPid = await new Promise<number>((resolve, reject) => {
        let out = ''
        child.stdout?.on('data', (b: Buffer) => {
          out += b.toString()
          const m = /^(\d+)\n/.exec(out)
          if (m) resolve(Number(m[1]))
        })
        setTimeout(() => reject(new Error('the test leader never reported its child')), 10_000)
      })
      const pid = child.pid!
      assert.ok(processAlive(pid) && processAlive(grandPid))

      // processInfo reads the real command line and start time (ps; PowerShell on Windows).
      const info = await processInfo(pid)
      assert.ok(info, 'processInfo found the leader')
      assert.ok(info.command.includes(marker), info.command)
      assert.ok(Math.abs(info.startedAt - Date.now()) < 30_000, `startedAt ${new Date(info.startedAt).toISOString()}`)

      if (posix) process.kill(pid, 'SIGSTOP')
      const sent: string[] = []
      const outcome = await stopTree({
        signal: (sig) => {
          sent.push(sig)
          signalTree(pid, sig, { platform: process.platform, kill: (p, s) => void process.kill(p, s), taskkill: taskkillTree }, (s) => child.kill(s))
        },
        gone: () => exited && !(posix && processAlive(-pid)),
        graceMs: 1500,
        confirmMs: 5000
      })
      if (posix) {
        assert.equal(outcome, 'killed', 'SIGTERM is ignored; SIGKILL ends the stopped group')
        assert.deepEqual(sent, ['SIGTERM', 'SIGKILL'])
      } else {
        assert.equal(outcome, 'gone', 'taskkill /T /F ends the tree at once')
      }
      assert.equal(processAlive(pid), false, 'the leader is gone')
      assert.ok(await waitGone(grandPid), 'its child is gone too')
    } finally {
      if (!exited) child.kill('SIGKILL')
    }
  })
})

async function waitGone(pid: number): Promise<boolean> {
  for (const end = Date.now() + 5000; Date.now() < end; ) {
    if (!processAlive(pid)) return true
    await new Promise((r) => setTimeout(r, 50))
  }
  return !processAlive(pid)
}
