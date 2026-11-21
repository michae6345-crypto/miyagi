/**
 * Lane reconnect (app/agents/reconnect.md), ROADMAP 1.4: the engine link's heartbeat, wake probe and held failures,
 * the respawn budget and the hung-engine restart, and fresh start across every reconnect (RunGuard keeps an old
 * lesson out after a dropped socket, a wake and a respawned engine, and keeps this run's own lesson).
 * A real `ws` server on 127.0.0.1 stands in for the engine: no Electron, no engine, no network, no paid calls.
 *
 *   cd app && node --import tsx --import ./test/setup.mjs --test --test-force-exit test/reconnect.test.ts
 */
import assert from 'node:assert/strict'
import type { AddressInfo } from 'node:net'
import { after, describe, test } from 'node:test'
import { WebSocketServer, type WebSocket } from 'ws'
import type { Incoming } from '../src/common/wire'
import { EngineLink, type LinkInfo } from '../src/main/engine'
import { Heartbeat } from '../src/main/heartbeat'
import { MAX_RESPAWNS, RespawnBudget, superviseEngine } from '../src/main/respawn'

const servers: WebSocketServer[] = []
after(() => {
  for (const s of servers) {
    for (const c of s.clients) c.terminate()
    s.close()
  }
})

const wait = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))
async function until(ok: () => boolean, ms: number, what: string): Promise<void> {
  for (const end = Date.now() + ms; Date.now() < end; await wait(20)) if (ok()) return
  assert.fail(`timed out waiting for ${what}`)
}

type Engine = { wss: WebSocketServer; url: string; port: number; conns: WebSocket[] }

/**
 * A fake engine. `silent` stops reading new sockets (no pong, like a hung engine or a dead Mac link). `snapshot` is
 * what it sends on every connect (the engine's snapshot). `onMessage` sees every command.
 */
async function server(
  opts: { port?: number; silent?: () => boolean; snapshot?: () => Incoming[]; onMessage?: (ws: WebSocket, m: { type: string; payload?: unknown }) => void } = {}
): Promise<Engine> {
  const wss = new WebSocketServer({ host: '127.0.0.1', port: opts.port ?? 0 })
  servers.push(wss)
  await new Promise<void>((r) => wss.once('listening', () => r()))
  const conns: WebSocket[] = []
  wss.on('connection', (ws) => {
    conns.push(ws)
    if (opts.silent?.()) return (ws as unknown as { _socket: { pause(): void } })._socket.pause()
    for (const e of opts.snapshot?.() ?? []) ws.send(JSON.stringify(e))
    ws.on('message', (raw) => opts.onMessage?.(ws, JSON.parse(String(raw)) as { type: string; payload?: unknown }))
  })
  const port = (wss.address() as AddressInfo).port
  return { wss, url: `ws://127.0.0.1:${port}`, port, conns }
}

/** The engine process dies: every socket ends without a close frame, and the port stops listening. */
async function crash(e: Engine): Promise<void> {
  for (const c of e.wss.clients) c.terminate()
  await new Promise<void>((r) => e.wss.close(() => r()))
}

const link = (url: string, timings = { heartbeatMs: 100, deadMs: 350, probeMs: 150 }): EngineLink => new EngineLink(url, undefined, undefined, timings)

// ---- the respawn budget and the supervisor ----------------------------------------------------------------------------

test('respawn budget: growing waits, at most 3 in the window, then a fresh budget', () => {
  const b = new RespawnBudget([500, 2000, 5000], 3, 60_000)
  assert.equal(b.next(0), 500)
  assert.equal(b.next(10), 2000)
  assert.equal(b.next(20), 5000)
  assert.equal(b.next(30), undefined, 'a fourth crash inside the window is a real failure')
  assert.equal(b.used(30), 3)
  assert.equal(b.next(60_001), 5000, 'the first respawn aged out of the window: room for one more')
  b.reset()
  assert.equal(b.next(60_002), 500)
})

describe('superviseEngine: crash policy and hung restart share one budget', () => {
  type Fake = {
    up: boolean
    alive: boolean
    restarts: number
    policy?: (why: string) => number | undefined
    status: Array<(up: boolean) => void>
    setUp(up: boolean): void
  }
  const fake = (): Fake => {
    const f: Fake = {
      up: false,
      alive: true,
      restarts: 0,
      status: [],
      setUp(up) {
        f.up = up
        for (const fn of f.status) fn(up)
      }
    }
    return f
  }
  const supervise = (f: Fake, hungMs = 80): ReturnType<typeof superviseEngine> =>
    superviseEngine(
      {
        connected: () => f.up,
        onStatus: (fn) => f.status.push(fn),
        ownEngineAlive: () => f.alive,
        restart: () => void f.restarts++,
        setPolicy: (p) => void (f.policy = p),
        warn: () => undefined,
        error: () => undefined
      },
      new RespawnBudget([500, 2000, 5000], MAX_RESPAWNS, 60_000),
      hungMs
    )

  test('a crash respawns after 0.5 s, 2 s, 5 s; the fourth is reported', () => {
    const f = fake()
    supervise(f)
    assert.deepEqual([f.policy?.('exited'), f.policy?.('exited'), f.policy?.('exited'), f.policy?.('exited')], [500, 2000, 5000, undefined])
  })

  test('answering again after a spent budget earns a fresh one', () => {
    const f = fake()
    supervise(f)
    for (let i = 0; i < 3; i++) f.policy?.('exited')
    assert.equal(f.policy?.('exited'), undefined)
    f.setUp(true)
    assert.equal(f.policy?.('exited'), 500)
  })

  test('hung: alive but the link down for hungMs restarts it once', async () => {
    const f = fake()
    supervise(f)
    f.setUp(true)
    f.setUp(false)
    await wait(200)
    assert.equal(f.restarts, 1)
  })

  test('hung: no restart when the link comes back, when it is not ours, or while asleep', async () => {
    const back = fake()
    supervise(back)
    back.setUp(false)
    await wait(30)
    back.setUp(true)
    await wait(150)
    assert.equal(back.restarts, 0, 'the link came back in time')

    const notOurs = fake()
    notOurs.alive = false
    supervise(notOurs)
    notOurs.setUp(false)
    await wait(150)
    assert.equal(notOurs.restarts, 0, 'an engine this app did not start (or one already gone) is never restarted')

    const sleepy = fake()
    const w = supervise(sleepy)
    sleepy.setUp(false)
    w.suspend()
    await wait(150)
    assert.equal(sleepy.restarts, 0, 'no verdict across a sleep')
    w.resume()
    await wait(150)
    assert.equal(sleepy.restarts, 1, 'awake and still down: restarted')
  })

  test('hung restarts spend the same budget as crashes', async () => {
    const f = fake()
    supervise(f)
    for (let i = 0; i < 3; i++) f.policy?.('exited')
    f.setUp(false)
    await wait(150)
    assert.equal(f.restarts, 0, 'budget spent: reported instead of restarting again')
  })
})

// ---- the heartbeat alone (a fake clock for the sleep) ----------------------------------------------------------------

test('heartbeat: a tick late by a sleep probes instead of dropping a healthy socket', async () => {
  let now = 1_000_000
  let dead = 0
  let pings = 0
  let answer = true
  const hb = new Heartbeat({ ping: () => (pings++, answer && setTimeout(() => hb.alive(), 5)), dead: () => dead++ }, 60_000, 30_000, 40, () => now)
  hb.start()
  now += 10 * 60_000 // ten minutes asleep: silence far past deadMs, but the timers were frozen
  hb.tick()
  assert.equal(dead, 0, 'not dropped on the late tick')
  assert.equal(pings, 1, 'probed instead')
  await wait(80)
  assert.equal(dead, 0, 'the probe was answered')
  answer = false
  now += 10 * 60_000
  hb.tick()
  await wait(80)
  assert.equal(dead, 1, 'a dead socket after a sleep is still caught within the probe window')
  hb.stop()
})

// ---- the link: heartbeat, wake, held failures --------------------------------------------------------------------------

test('heartbeat: a socket that stops answering is dropped and reconnected', async () => {
  let silent = true
  const { url, conns } = await server({ silent: () => silent })
  const l = link(url)
  const states: boolean[] = []
  l.onStatus((c) => states.push(c))
  await until(() => l.connected, 2000, 'first connect')
  silent = false
  // No pong for deadMs: dropped, then the fast retry (1 s) opens a fresh socket.
  await until(() => states.includes(false), 2000, 'the heartbeat to drop the silent socket')
  await until(() => l.connected && conns.length === 2, 3000, 'the reconnect')
})

test('heartbeat: a healthy socket stays open across many beats', async () => {
  const { url, conns } = await server()
  const l = link(url)
  await until(() => l.connected, 2000, 'connect')
  await wait(900)
  assert.equal(l.connected, true)
  assert.equal(conns.length, 1, 'no needless reconnects')
})

test('wake: an open socket that does not answer is dropped at once (Mac slept)', async () => {
  let silent = true
  const { url, conns } = await server({ silent: () => silent })
  // A long heartbeat, so only the wake probe can catch it.
  const l = link(url, { heartbeatMs: 60_000, deadMs: 120_000, probeMs: 150 })
  await until(() => l.connected, 2000, 'connect')
  silent = false
  const t = Date.now()
  l.wake()
  await until(() => !l.connected, 1000, 'the wake probe to drop the dead socket')
  assert.ok(Date.now() - t < 800)
  await until(() => l.connected && conns.length === 2, 3000, 'the reconnect after wake')
})

test('wake: an answering socket stays open', async () => {
  const { url, conns } = await server()
  const l = link(url, { heartbeatMs: 60_000, deadMs: 120_000, probeMs: 150 })
  await until(() => l.connected, 2000, 'connect')
  l.wake()
  await wait(400)
  assert.equal(l.connected, true)
  assert.equal(conns.length, 1)
})

test('a closed connection reconnects within about a second', async () => {
  const { url, conns } = await server()
  const l = link(url)
  await until(() => l.connected, 2000, 'connect')
  conns[0].close()
  await until(() => !l.connected, 1000, 'the drop')
  await until(() => l.connected && conns.length === 2, 3000, 'the reconnect')
})

test('held failures: refused attempts while main starts the engine are not counted', async () => {
  // A port nothing listens on: every attempt is refused.
  const { wss, url } = await server()
  await new Promise<void>((r) => wss.close(() => r()))
  const l = link(url)
  const seen: LinkInfo[] = []
  l.onLink((i) => seen.push(i))
  l.holdFailures(true)
  await wait(2500)
  assert.equal(l.link().failures, 0, 'held: the pill stays on its calm line')
  l.holdFailures(false)
  await wait(1300)
  assert.ok(l.link().failures >= 1, 'released: a refused attempt counts again')
  assert.ok(seen.every((i) => !i.open))
})

test('respawn: the engine dies, main holds failures, the new engine on the same port is picked up fast', async () => {
  const first = await server()
  const l = link(first.url)
  await until(() => l.connected, 2000, 'connect')
  await crash(first)
  // What localEngine does on a crash mid-run with budget left: state 'starting' (held), start again after 0.5 s.
  l.holdFailures(true)
  await until(() => !l.connected, 1000, 'the drop')
  await wait(1500)
  assert.equal(l.link().failures, 0, 'refused attempts while it restarts are not failures')
  const second = await server({ port: first.port })
  const t = Date.now()
  await until(() => l.connected, 2500, 'the respawned engine')
  assert.ok(Date.now() - t < 2000, `picked up ${Date.now() - t} ms after it listened`)
  assert.equal(second.conns.length, 1)
  l.holdFailures(false)
})

// ---- fresh start across reconnects (RunGuard) ------------------------------------------------------------------------

const ev = (type: string, payload: unknown = {}): Incoming => ({ type, payload }) as Incoming
const ready = (id: string, replay = false): Incoming =>
  ev('lesson.ready', { lesson: { id, title: `Lesson ${id}`, sources: [] }, steps: [{ id: 's1', title: 'One' }], ...(replay ? { replay: true } : {}) })
/** An engine that kept lesson `id`: what it sends on every connect. */
const snapshotOf = (id: string): Incoming[] => [
  ev('engine.hello', { version: 'test', capabilities: [] }),
  ready(id, true),
  ev('step.started', { stepId: 's2', index: 1, title: 'Two', instructions: 'Type it' }),
  ev('check.updated', { stepId: 's2', checkId: 'c1', label: 'Runs', status: 'pending' }),
  ev('card', { kind: 'resume', title: 'Continue?', body: 'step 2', actions: ['resume', 'end_lesson'] }),
  ev('status', { state: 'watching' }),
  ev('library', { lessons: [] })
]
const lessonOf = (e: Incoming): string | undefined => (e.type === 'lesson.ready' ? (e.payload as { lesson: { id: string } }).lesson.id : undefined)
const LESSONY = new Set(['lesson.ready', 'step.started', 'check.updated'])
const oldLeaks = (seen: Incoming[]): Incoming[] =>
  seen.filter(
    (e) =>
      (LESSONY.has(e.type) && lessonOf(e) !== 'mine' && !(e.type !== 'lesson.ready' && seen.some((x) => lessonOf(x) === 'mine'))) ||
      (e.type === 'card' && (e.payload as { kind: string }).kind === 'resume') ||
      (e.type === 'status' && (e.payload as { state: string }).state === 'watching')
  )

test('fresh start: an old lesson stays out across a heartbeat drop, a wake drop, a close and a respawn', async () => {
  let silent = false
  const first = await server({ silent: () => silent, snapshot: () => snapshotOf('old') })
  const l = link(first.url, { heartbeatMs: 100, deadMs: 350, probeMs: 150 })
  const seen: Incoming[] = []
  l.onEvent((e) => seen.push(e))
  const hellos = (): number => seen.filter((e) => e.type === 'library').length

  await until(() => hellos() === 1, 2000, 'the first snapshot')
  // 1. Heartbeat: the next socket is silent, so it is dropped; the one after answers with the old snapshot again.
  silent = true
  first.conns[0].terminate()
  await until(() => first.conns.length >= 2, 2000, 'a reconnect to a silent socket')
  silent = false
  await until(() => hellos() === 2, 3000, 'the snapshot after the heartbeat drop')
  // 2. Wake: the open socket answers nothing (paused), the probe drops it.
  ;(first.conns.at(-1) as unknown as { _socket: { pause(): void } })._socket.pause()
  l.wake()
  await until(() => hellos() === 3, 3000, 'the snapshot after the wake drop')
  // 3. A plain close.
  first.conns.at(-1)?.close()
  await until(() => hellos() === 4, 3000, 'the snapshot after a close')
  // 4. The engine crashes and a new one on the same port replays its kept (old) lesson.
  await crash(first)
  await server({ port: first.port, snapshot: () => snapshotOf('old') })
  await until(() => hellos() === 5, 4000, 'the snapshot from the respawned engine')

  assert.deepEqual(oldLeaks(seen), [], 'no old lesson event reached the windows')
  assert.ok(!l.log.some((e) => LESSONY.has(e.type)), 'the replay log (a window that loads) holds no old lesson')
  const idles = seen.filter((e) => e.type === 'status' && (e.payload as { state: string }).state === 'idle').length
  assert.equal(idles, 5, "the old lesson's watching rests the pill on every connect")
})

test("fresh start: this run's lesson comes back after a drop, a respawned engine's old lesson does not", async () => {
  let kept = 'old'
  const onMessage = (ws: WebSocket, m: { type: string }): void => {
    if (m.type !== 'learn') return
    kept = 'mine'
    for (const e of [ev('lesson.ended', { lessonId: 'old', reason: 'new_lesson' }), ev('lesson.building', { message: 'Building', progress: 0.5 }), ready('mine'), ev('step.started', { stepId: 's1', index: 0, title: 'One', instructions: '' })])
      ws.send(JSON.stringify(e))
  }
  const first = await server({ snapshot: () => snapshotOf(kept), onMessage })
  const l = link(first.url)
  const seen: Incoming[] = []
  l.onEvent((e) => seen.push(e))
  await until(() => seen.some((e) => e.type === 'library'), 2000, 'the first snapshot')
  assert.ok(!seen.some((e) => e.type === 'lesson.ready'), 'nothing of the old lesson at launch')

  l.send({ type: 'learn', payload: { query: 'sin(x)', mode: 'lesson' } } as Parameters<EngineLink['send']>[0])
  await until(() => seen.some((e) => lessonOf(e) === 'mine'), 2000, "this run's lesson")

  // The socket drops (heartbeat or sleep); the same engine replays this run's lesson: it comes back.
  seen.length = 0
  first.conns[0].terminate()
  await until(() => seen.some((e) => lessonOf(e) === 'mine'), 3000, "this run's lesson after the reconnect")
  assert.ok(seen.some((e) => e.type === 'step.started'), 'and its step')

  // The engine crashes; the respawned one kept an older lesson (a different save): it stays out.
  seen.length = 0
  await crash(first)
  await server({ port: first.port, snapshot: () => snapshotOf('old') })
  await until(() => seen.some((e) => e.type === 'library'), 4000, 'the respawned engine')
  assert.ok(!seen.some((e) => lessonOf(e) === 'old'), "the respawned engine's old lesson never reaches the windows")
  assert.ok(!seen.some((e) => e.type === 'card' && (e.payload as { kind: string }).kind === 'resume'), 'nor its resume card')
})
