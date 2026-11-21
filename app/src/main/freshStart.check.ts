/**
 * Fresh start: a Node check, no Electron, no window, no network beyond this Mac's loopback, no engine.
 *
 *   npx tsx src/main/freshStart.check.ts      (from app/)
 *
 * 1. RunGuard alone: an old lesson's replayed events (lesson.ready, steps, checks, a resume card, a watching status,
 *    video, spotlight) are dropped at launch; hello, search, library, an answer card pass; a lesson started now
 *    (learn, library.start, Continue) passes; an interrupted lesson's replay passes again; an ended one stops.
 * 2. The real EngineLink (main/engine.ts, loaded through Vite SSR for its import.meta.glob) against a fake engine on
 *    127.0.0.1 that replays an old lesson on connect, like the engine after a restart: nothing of it reaches the
 *    listeners (what main relays to every window) or the replay log; after `learn` the new lesson does; a reconnect
 *    that replays the run's own lesson keeps it.
 * 3. Starts sent while the engine is down (launch window, engine restart) never leave and let nothing in; a start
 *    that went out but was never answered expires on the next connection.
 * Exits 1 on any failure.
 */
import { WebSocketServer, type WebSocket } from 'ws'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import type { Incoming, Outgoing } from '../common/wire'
import { RunGuard } from './freshStart'

let failed = 0
let passed = 0
function ok(cond: unknown, what: string): void {
  if (cond) passed++
  else {
    failed++
    console.error(`FAIL ${what}`)
  }
}

const ev = (type: string, payload: unknown = {}): Incoming => ({ type, payload }) as Incoming
const cmd = (type: string, payload: unknown = {}): Outgoing => ({ type, payload }) as Outgoing
const ready = (id: string): Incoming => ev('lesson.ready', { lesson: { id, title: `Lesson ${id}`, sources: [] }, steps: [{ id: 's1', title: 'One' }] })

/** What an engine with a kept lesson sends on connect (its snapshot). */
const OLD_SNAPSHOT: Incoming[] = [
  ready('old'),
  ev('step.started', { stepId: 's3', index: 2, title: 'Three', instructions: 'Type it' }),
  ev('check.updated', { stepId: 's3', checkId: 'c1', label: 'Runs', status: 'pending' }),
  ev('card', { kind: 'resume', title: 'Continue where you left off?', body: 'Lesson old · step 3', actions: ['resume', 'end_lesson'] }),
  ev('card', { kind: 'step', stepId: 's3', title: 'Save calc.py', body: 'Save it' }),
  ev('status', { state: 'watching' }),
  ev('video.seek', { t: 42, play: true }),
  ev('video.play'),
  ev('spotlight', { rect: { x: 1, y: 2, w: 3, h: 4 }, caption: 'Here' }),
  ev('diagram', { kind: 'network', caption: 'Net', stepId: 's3', data: { layers: [1, 4, 1], activation: 'tanh', derivatives: [], residual: '' } }),
  ev('lesson.paused', { reason: 'editor_closed' }),
  ev('blocker', { kind: 'editor_closed', title: 'VS Code closed' }),
  ev('metric', { runId: 'r', step: 1, name: 'm', value: 1 }),
  ev('screen.seen', { app: 'Code', summary: 'calc.py', t: 1 }),
  ev('step.passed', { stepId: 's3' }),
  ev('lesson.updated', { steps: [], complete: true }),
  ev('lesson.building', { message: 'Writing checks', progress: 0.5 })
]
/** Always passes, lesson or not. */
const NEUTRAL: Incoming[] = [
  ev('engine.hello', { version: 't', contract: '2026-11-20', capabilities: ['library.start'], restored: true }),
  ev('search.result', { id: 'r1', kind: 'video', title: 'A', meta: '', score: 1, reason: '' }),
  ev('search.done', { total: 1 }),
  ev('library', { items: [] }),
  ev('progress', {}),
  ev('health', { items: [], ready: 0, total: 0 }),
  ev('error', { message: 'x' }),
  ev('status', { state: 'idle' }),
  ev('status', { state: 'thinking' }),
  ev('card', { kind: 'answer', title: 'Answer', body: 'Because' }),
  ev('diagram', { kind: 'graph', caption: 'Idea', data: { nodes: [], edges: [] } }),
  ev('blocker', { kind: 'network', title: 'Offline' }),
  ev('blocker', { kind: 'editor_closed', clear: true }),
  ev('lesson.ended', { reason: 'end_lesson' })
]

// ---- 1. RunGuard ---------------------------------------------------------------------------------------------------

{
  const g = new RunGuard()
  for (const e of OLD_SNAPSHOT) ok(!g.admit(e), `launch: old ${e.type}${e.type === 'card' ? ` (${(e.payload as { kind: string }).kind})` : ''} is dropped`)
  for (const e of NEUTRAL) ok(g.admit(e), `launch: ${e.type} passes`)
  ok(!g.state().lessonId && !g.state().pending, 'launch: no lesson, nothing pending')
  ok(!g.admit(ready('old')), 'launch: a second replay of the old lesson is dropped too')
}

for (const start of [cmd('learn', { query: 'sin(x)' }), cmd('learn_url', { url: 'https://youtu.be/x' }), cmd('build_lesson', { resultIds: ['r1'] }), cmd('library.start', { id: 'nn' }), cmd('action', { kind: 'resume' })]) {
  const g = new RunGuard()
  ok(!g.admit(ready('old')), `${start.type}: the old replay before it is dropped`)
  g.command(start)
  ok(g.state().pending, `${start.type}: a lesson is on its way`)
  ok(g.admit(ev('lesson.ended', { lessonId: 'old', reason: 'new_lesson' })), `${start.type}: the old lesson's end passes`)
  ok(g.state().pending, `${start.type}: the old lesson's end keeps the wait`)
  ok(g.admit(ev('lesson.building', { message: 'Watching', progress: 0.1 })), `${start.type}: building passes`)
  ok(g.admit(ready('new')), `${start.type}: the lesson started now passes`)
  ok(g.state().lessonId === 'new' && !g.state().pending, `${start.type}: it is the run's lesson`)
  for (const e of OLD_SNAPSHOT.slice(1)) ok(g.admit(e), `${start.type}: ${e.type} passes during the run's lesson`)
}

{
  // An engine deploy: lesson.ended interrupted, then the same lesson comes back on reconnect.
  const g = new RunGuard()
  g.command(cmd('learn', { query: 'x' }))
  g.admit(ready('a'))
  ok(g.admit(ev('lesson.ended', { reason: 'interrupted' })), 'interrupted: the end passes')
  ok(g.state().lessonId === 'a', 'interrupted: the run keeps its lesson')
  ok(g.admit(ready('a')), 'interrupted: the same lesson replayed on reconnect passes')
  ok(g.admit(ev('step.started', { stepId: 's1', index: 0, title: 'One', instructions: '' })), 'interrupted: its step passes')
  ok(!g.admit(ready('other')), 'a different lesson the run never started is dropped')
}

{
  // Ended: lesson events stop until the learner starts another.
  const g = new RunGuard()
  g.command(cmd('library.start', { id: 'nn' }))
  g.admit(ready('a'))
  ok(g.admit(ev('lesson.ended', { lessonId: 'a', reason: 'end_lesson' })), 'ended: the end passes')
  ok(!g.state().lessonId, 'ended: the run has no lesson')
  ok(!g.admit(ready('a')), 'ended: a replay of the ended lesson is dropped')
  ok(!g.admit(ev('step.started', { stepId: 's1', index: 0, title: 'One', instructions: '' })), 'ended: a stale step is dropped')
  ok(!g.admit(ev('card', { kind: 'resume', title: 'Continue?', body: '' })), 'ended: a resume card is dropped')
}

{
  // Another lesson's end (an id that isn't the run's) leaves the run's lesson alone.
  const g = new RunGuard()
  g.command(cmd('learn', { query: 'x' }))
  g.admit(ready('a'))
  g.admit(ev('lesson.ended', { lessonId: 'zzz', reason: 'end_lesson' }))
  ok(g.state().lessonId === 'a', "another lesson's end keeps the run's lesson")
}

{
  // A failed build ends the wait: a stale lesson.ready afterwards is dropped.
  const g = new RunGuard()
  g.command(cmd('learn_url', { url: 'https://youtu.be/x' }))
  ok(g.admit(ev('lesson.building', { message: 'x', progress: 0, failed: true })), 'failed build: the failure passes')
  ok(!g.state().pending, 'failed build: nothing pending')
  ok(!g.admit(ready('old')), 'failed build: a stale lesson.ready is dropped')
}

{
  // Commands that are not a start never let a lesson in.
  const g = new RunGuard()
  for (const c of [cmd('action', { kind: 'ask', text: 'why' }), cmd('action', { kind: 'explain' }), cmd('library.list'), cmd('progress.get'), cmd('health.get'), cmd('config.keys', {}), cmd('end_lesson'), cmd('overlay.bounds', { rects: [] })]) g.command(c)
  ok(!g.admit(ready('old')), 'ask / explain / list / keys / end: the old lesson is still dropped')
  g.command(cmd('dev.reset'))
  ok(!g.admit(ready('old')), 'dev.reset: a fresh start too')
  ok(new RunGuard(true).admit(ready('demo')), "DEMO=1 (armed): the scripted run's lesson passes")
}

{
  // The wait expires: end_lesson (command or the resume card's action) and a new engine connection.
  for (const stop of [cmd('end_lesson'), cmd('action', { kind: 'end_lesson' })]) {
    const name = stop.type === 'action' ? 'action end_lesson' : 'end_lesson'
    const g = new RunGuard()
    g.command(cmd('learn', { query: 'x' }))
    g.command(stop)
    ok(!g.state().pending, `${name} while building: nothing pending`)
    ok(!g.admit(ready('old')), `${name} while building: a later replay of the old lesson is dropped`)
  }
  // A search the learner abandons, then the engine restarts (update-engine.sh) and replays its kept lesson.
  const g = new RunGuard()
  g.command(cmd('learn', { query: 'x' }))
  ok(g.admit(ev('search.result', { id: 'r1', kind: 'video', title: 'A', meta: '', score: 1, reason: '' })), 'abandoned search: its rows pass')
  g.connected()
  ok(!g.state().pending, 'abandoned search: a new connection ends the wait')
  ok(!g.admit(ready('old')), "abandoned search: the restarted engine's old lesson is dropped")
  // A library.start the engine answers with an error, then a restart.
  const h = new RunGuard()
  h.command(cmd('library.start', { id: 'nn' }))
  ok(h.admit(ev('error', { message: 'no such lesson' })), 'library.start error: the error passes')
  h.connected()
  ok(!h.admit(ready('old')), 'library.start error: the replay after a restart is dropped')
  // The run's own lesson survives a new connection.
  const k = new RunGuard()
  k.command(cmd('learn', { query: 'x' }))
  k.admit(ready('a'))
  k.connected()
  ok(k.admit(ready('a')) && k.state().lessonId === 'a', "a new connection keeps the run's lesson")
  ok(!k.admit(ready('b')), 'a new connection admits no other lesson')
}

// ---- 2. EngineLink against a fake engine on loopback -----------------------------------------------------------------

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))
async function until(cond: () => boolean, ms = 4000): Promise<boolean> {
  const end = Date.now() + ms
  while (Date.now() < end) {
    if (cond()) return true
    await sleep(25)
  }
  return cond()
}

async function linkCheck(): Promise<void> {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
  const vite = await createServer({ configFile: false, root, logLevel: 'error', server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  const { EngineLink } = (await vite.ssrLoadModule('/src/main/engine.ts')) as typeof import('./engine')

  const wss = new WebSocketServer({ host: '127.0.0.1', port: 0 })
  await new Promise<void>((r) => wss.once('listening', () => r()))
  const port = (wss.address() as { port: number }).port
  /** The lesson the fake engine holds (what it replays on every connect). */
  let kept = 'old'
  let socket: WebSocket | undefined
  const sendAll = (ws: WebSocket, list: Incoming[]): void => list.forEach((m) => ws.send(JSON.stringify(m)))
  wss.on('connection', (ws) => {
    socket = ws
    sendAll(ws, [NEUTRAL[0], NEUTRAL[3], ...OLD_SNAPSHOT.map((e) => (e.type === 'lesson.ready' ? ready(kept) : e)), NEUTRAL[9]])
    ws.on('message', (raw) => {
      const m = JSON.parse(String(raw)) as { type: string }
      if (m.type !== 'learn') return
      kept = 'new'
      sendAll(ws, [ev('lesson.ended', { lessonId: 'old', reason: 'new_lesson' }), ev('lesson.building', { message: 'Watching', progress: 0.2 }), ready('new'), ev('step.started', { stepId: 's1', index: 0, title: 'One', instructions: '' })])
    })
  })

  const link = new EngineLink(`ws://127.0.0.1:${port}`)
  const seen: Incoming[] = []
  link.onEvent((e) => seen.push(e))
  const LESSONY = new Set(['lesson.ready', 'step.started', 'check.updated', 'video.seek', 'video.play', 'spotlight', 'lesson.paused', 'step.passed', 'lesson.updated', 'lesson.building'])

  ok(await until(() => seen.some((e) => e.type === 'card')), 'link: the answer card (last message) arrived')
  ok(seen.some((e) => e.type === 'engine.hello') && seen.some((e) => e.type === 'library'), 'link: hello and library reach the windows')
  ok(!seen.some((e) => LESSONY.has(e.type)), `link: no old lesson event reaches the windows at launch (got ${seen.map((e) => e.type).join(', ')})`)
  ok(!seen.some((e) => e.type === 'card' && (e.payload as { kind: string }).kind !== 'answer'), 'link: no resume or step card at launch')
  ok(!seen.some((e) => e.type === 'status' && (e.payload as { state: string }).state === 'watching'), 'link: no watching status at launch')
  ok(!link.log.some((e) => LESSONY.has(e.type)), 'link: the replay log (ui:ready) holds no old lesson')

  link.send({ type: 'learn', payload: { query: 'sin(x)' } })
  const isNew = (e: Incoming): boolean => e.type === 'lesson.ready' && (e.payload as { lesson: { id: string } }).lesson.id === 'new'
  ok(await until(() => seen.some(isNew)), 'link: the lesson started now reaches the windows')
  ok(await until(() => seen.some((e) => e.type === 'step.started')), 'link: and its first step')
  ok(!seen.some((e) => e.type === 'lesson.ready' && !isNew(e)), 'link: the old lesson never did')
  ok(link.log.some((e) => e.type === 'lesson.ready'), 'link: the replay log holds the new lesson')

  // The connection drops; the engine comes back and replays the run's own lesson: it is kept.
  seen.length = 0
  socket?.terminate()
  ok(await until(() => seen.some((e) => e.type === 'lesson.ready'), 6000), "link: after a reconnect the run's own lesson replays")
  ok(seen.some((e) => e.type === 'step.started'), 'link: and its step')

  wss.close()

  await offlineCheck(EngineLink)
  await vite.close()
}

/**
 * Starts sent while the engine is down never leave, so they must not let the next connect's old snapshot in:
 * (a) the launch window (localEngine still starting, no engine yet) and (b) an engine restart (update-engine.sh).
 * (c) A start that went out but was never answered expires on the next connection.
 */
async function offlineCheck(EngineLink: typeof import('./engine').EngineLink): Promise<void> {
  // A free loopback port with nothing on it yet.
  const probe = new WebSocketServer({ host: '127.0.0.1', port: 0 })
  await new Promise<void>((r) => probe.once('listening', () => r()))
  const port = (probe.address() as { port: number }).port
  await new Promise<void>((r) => probe.close(() => r()))

  /** A fake engine with a kept lesson: replays it on every connect and never answers a start. */
  const sockets = new Set<WebSocket>()
  const up = async (): Promise<WebSocketServer> => {
    const wss = new WebSocketServer({ host: '127.0.0.1', port })
    await new Promise<void>((r) => wss.once('listening', () => r()))
    wss.on('connection', (ws) => {
      sockets.add(ws)
      ws.on('close', () => sockets.delete(ws))
      for (const m of [NEUTRAL[0], ...OLD_SNAPSHOT, NEUTRAL[9]]) ws.send(JSON.stringify(m))
    })
    return wss
  }
  const down = async (wss: WebSocketServer): Promise<void> => {
    for (const ws of sockets) ws.terminate()
    await new Promise<void>((r) => wss.close(() => r()))
  }

  // Every event of the old snapshot, matched by value (card / status / diagram / blocker also have neutral forms).
  const OLD = new Set(OLD_SNAPSHOT.map((e) => JSON.stringify(e)))
  const lessonish = (list: Incoming[]): string[] => list.filter((e) => OLD.has(JSON.stringify(e))).map((e) => e.type)
  const answered = (list: Incoming[]): boolean => list.some((e) => e.type === 'card' && (e.payload as { kind: string }).kind === 'answer')

  // (a) Launch: the engine isn't up yet; the learner types a goal at once.
  const link = new EngineLink(`ws://127.0.0.1:${port}`)
  const seen: Incoming[] = []
  link.onEvent((e) => seen.push(e))
  link.send({ type: 'learn', payload: { query: 'sin(x)' } })
  ok(seen.some((e) => e.type === 'error'), 'offline launch: learn fails visibly')
  let wss = await up()
  ok(await until(() => answered(seen), 9000), 'offline launch: the engine connected and sent its snapshot')
  ok(!lessonish(seen).length, `offline launch: no old lesson event reaches the windows (got ${lessonish(seen).join(', ')})`)
  ok(!lessonish(link.log).length, 'offline launch: the replay log holds no old lesson')

  // (b) The engine restarts; while it is down the learner sends learn and library.start (the link knows its caps).
  await down(wss)
  ok(await until(() => !link.link().open), 'restart: the link sees the engine go')
  seen.length = 0
  link.send({ type: 'learn', payload: { query: 'sin(x)' } })
  link.send({ type: 'library.start', payload: { id: 'nn' } })
  wss = await up()
  ok(await until(() => answered(seen), 9000), 'restart: the engine came back with its snapshot')
  ok(!lessonish(seen).length, `restart: starts sent offline let no old lesson in (got ${lessonish(seen).join(', ')})`)
  ok(!lessonish(link.log).length, 'restart: the replay log holds no old lesson')

  // (c) A start that goes out but is never answered (a search the learner abandons), then another restart.
  link.send({ type: 'learn', payload: { query: 'sin(x)' } })
  await sleep(100)
  await down(wss)
  ok(await until(() => !link.link().open), 'abandoned: the link sees the engine go')
  seen.length = 0
  wss = await up()
  ok(await until(() => answered(seen), 9000), 'abandoned: the engine came back with its snapshot')
  ok(!lessonish(seen).length, `abandoned: the old lesson stays out after the restart (got ${lessonish(seen).join(', ')})`)
  await down(wss)
}

void (async () => {
  try {
    await linkCheck()
  } catch (err) {
    failed++
    console.error('FAIL link check threw', err)
  }
  console.log(`${passed} passed, ${failed} failed`)
  process.exit(failed ? 1 : 0)
})()
