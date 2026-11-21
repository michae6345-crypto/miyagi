/**
 * ROADMAP 1.4 reconnect and recovery: the engine link's heartbeat, wake probe and held failures, and the respawn budget.
 * A real `ws` server on 127.0.0.1 stands in for the engine (no Electron, no network, no paid calls).
 *
 *   cd app && node --import tsx --import ./tests/stub-scenarios.mjs --test tests/reconnect.test.ts
 */
import assert from 'node:assert/strict'
import type { AddressInfo } from 'node:net'
import { after, test } from 'node:test'
import { WebSocketServer, type WebSocket } from 'ws'
import { EngineLink, type LinkInfo } from '../src/main/engine'
import { RespawnBudget } from '../src/main/respawn'

const links: EngineLink[] = []
const servers: WebSocketServer[] = []
after(() => {
  // EngineLink has no stop(): its retry timers would keep the process alive, so the run ends here.
  for (const s of servers) s.close()
  setTimeout(() => process.exit(0), 50).unref()
})

const wait = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))
async function until(ok: () => boolean, ms: number, what: string): Promise<void> {
  for (const end = Date.now() + ms; Date.now() < end; await wait(20)) if (ok()) return
  assert.fail(`timed out waiting for ${what}`)
}

/** A server that counts connections; `silent` stops reading new sockets (no pong, like a hung engine or a dead Mac link). */
async function server(opts: { silent?: () => boolean } = {}): Promise<{ wss: WebSocketServer; url: string; conns: WebSocket[] }> {
  const wss = new WebSocketServer({ host: '127.0.0.1', port: 0 })
  servers.push(wss)
  await new Promise<void>((r) => wss.once('listening', () => r()))
  const conns: WebSocket[] = []
  wss.on('connection', (ws) => {
    conns.push(ws)
    if (opts.silent?.()) (ws as unknown as { _socket: { pause(): void } })._socket.pause()
  })
  return { wss, url: `ws://127.0.0.1:${(wss.address() as AddressInfo).port}`, conns }
}

function link(url: string, timings = { heartbeatMs: 100, deadMs: 350, probeMs: 150 }): EngineLink {
  const l = new EngineLink(url, undefined, undefined, timings)
  links.push(l)
  return l
}

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
