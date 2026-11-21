/**
 * Fresh start: a Node check, no Electron, no window, no network beyond this Mac's loopback, no engine.
 *
 *   npx tsx src/main/freshStart.check.ts      (from app/)
 *
 * 1. RunGuard alone: an old lesson's replayed events (lesson.ready, steps, checks, a resume or preflight card, its
 *    thinking / busy / watching statuses, video, spotlight) are dropped at launch, and the pill rests idle; hello,
 *    search, library, an answer card pass; a lesson started now (learn, library.start, Continue) passes; an
 *    interrupted lesson's replay passes again; an ended one stops; DEMO re-arms on dev.reset; a build's wait survives
 *    a reconnect, but only a fresh lesson.ready ends it. While a start is on its way only its build traffic passes
 *    (never the kept lesson's steps, cards, video, spotlight, checks); an abandoned start (search over, nothing
 *    picked, a library.start error, a timeout) expires; only presses the engine answers keep the pill spinning.
 * 2. The real EngineLink (main/engine.ts, loaded through Vite SSR for its import.meta.glob) against a fake engine on
 *    127.0.0.1 that replays an old lesson on connect, like the engine after a restart: nothing of it reaches the
 *    listeners (what main relays to every window) or the replay log; after `learn` the new lesson does; a reconnect
 *    that replays the run's own lesson keeps it.
 * 3. Starts sent while the engine is down (launch window, engine restart) never leave and let nothing in; a start
 *    that went out but was never answered lets no old replay in after a restart; a build carried over a dropped
 *    socket still lands; MIYAGI_REPLAY_ON_CONNECT=1 (npm run dev:all) shows the mock's connect lesson.
 * Exits 1 on any failure.
 */
import { WebSocketServer, type WebSocket } from 'ws'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import type { Incoming, Outgoing } from '../common/wire'
import { OPEN_TTL_MS, PICK_TTL_MS, RunGuard } from './freshStart'

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
/** A snapshot's lesson.ready: the engine marks the SAME lesson again with replay: true (session.py snapshot()). */
const replayOf = (id: string): Incoming => ev('lesson.ready', { ...(ready(id).payload as object), replay: true })

/** What an engine with a kept lesson sends on connect (its snapshot). */
const OLD_SNAPSHOT: Incoming[] = [
  replayOf('old'),
  ev('step.started', { stepId: 's3', index: 2, title: 'Three', instructions: 'Type it' }),
  ev('check.updated', { stepId: 's3', checkId: 'c1', label: 'Runs', status: 'pending' }),
  ev('card', { kind: 'resume', title: 'Continue where you left off?', body: 'Lesson old · step 3', actions: ['resume', 'end_lesson'] }),
  ev('card', { kind: 'step', stepId: 's3', title: 'Save calc.py', body: 'Save it' }),
  ev('card', { kind: 'preflight', title: 'What this video is', body: 'Build it?', actions: ['build', 'pick_another'] }),
  ev('status', { state: 'watching' }),
  ev('status', { state: 'thinking', detail: 'Looking at your code' }),
  ev('status', { state: 'busy', retryInS: 5 }),
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
/** What a real engine replays for a kept lesson (no build running: its snapshot never holds lesson.building too). */
const LESSON_SNAPSHOT = OLD_SNAPSHOT.filter((e) => e.type !== 'lesson.building')
const HELLO = ev('engine.hello', { version: 't', contract: '2026-11-20', capabilities: ['library.start'], restored: true })
const LIBRARY = ev('library', { items: [] })
/** The fake engines' last message: when it arrived, the snapshot before it did too. */
const ANSWER = ev('card', { kind: 'answer', title: 'Answer', body: 'Because' })
/** Always passes, lesson or not. */
const NEUTRAL: Incoming[] = [
  HELLO,
  ev('search.result', { id: 'r1', kind: 'video', title: 'A', meta: '', score: 1, reason: '' }),
  ev('search.done', { total: 1 }),
  LIBRARY,
  ev('progress', {}),
  ev('health', { items: [], ready: 0, total: 0 }),
  ev('error', { message: 'x' }),
  ev('status', { state: 'idle' }),
  ANSWER,
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
}

{
  // DEMO=1 (armed): the scripted run's lesson passes, and again after every dev.reset (the mock replays its
  // scenario's 'connect' segment, mock/engine.ts handle('dev.reset')).
  const d = new RunGuard(true)
  ok(d.admit(ready('demo')), "DEMO=1 (armed): the scripted run's lesson passes")
  d.command(cmd('dev.reset'))
  ok(d.state().pending && !d.state().lessonId, 'DEMO dev.reset: a lesson is on its way again')
  ok(d.admit(ready('demo')), "DEMO dev.reset: the scenario's connect lesson passes again")
  ok(d.admit(ev('step.started', { stepId: 's1', index: 0, title: 'One', instructions: '' })), 'DEMO dev.reset: and its step')
  d.command(cmd('dev.reset'))
  ok(d.admit(ready('other')), 'DEMO dev.reset: whatever lesson the scenario plays passes')
  // MIYAGI_REPLAY_ON_CONNECT=1 (npm run dev:all): the mock replays its scenario on every connection.
  const r = new RunGuard(true)
  ok(r.admit(ready('m')), 'replay on connect: the first connect lesson passes')
  r.admit(ev('lesson.ended', { reason: 'end_lesson' }))
  r.connected()
  ok(r.admit(replayOf('m2')), 'replay on connect: a reconnect plays the scenario lesson again')
}

{
  // The wait ends on end_lesson (command or the resume card's action).
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
  ok(g.state().pending && g.state().carried, 'abandoned search: the wait came over the new connection')
  for (const e of LESSON_SNAPSHOT) ok(!g.admit(e), `abandoned search: the restarted engine's old ${e.type} is dropped`)
  // A library.start the engine answers with an error, then a restart.
  const h = new RunGuard()
  h.command(cmd('library.start', { id: 'nn' }))
  ok(h.admit(ev('error', { message: 'no such lesson' })), 'library.start error: the error passes')
  h.connected()
  ok(!h.admit(replayOf('old')), 'library.start error: the replay after a restart is dropped')
  // The run's own lesson survives a new connection.
  const k = new RunGuard()
  k.command(cmd('learn', { query: 'x' }))
  k.admit(ready('a'))
  k.connected()
  ok(k.admit(replayOf('a')) && k.state().lessonId === 'a', "a new connection keeps the run's lesson")
  ok(!k.admit(replayOf('b')), 'a new connection admits no other lesson')
}

{
  // A long build survives a dropped socket (sleep / wake, the engine stays up): its snapshot's lesson.building and
  // its final lesson.ready get in; an old lesson's replay does not.
  const g = new RunGuard()
  g.command(cmd('build_lesson', { resultIds: ['r1'] }))
  ok(g.admit(ev('lesson.building', { message: 'Watching', progress: 0.1 })), 'carried build: building passes before the drop')
  g.connected()
  ok(g.state().pending && g.state().carried, 'carried build: still waiting after the reconnect')
  ok(g.admit(ev('lesson.building', { message: 'Writing checks', progress: 0.6 })), "carried build: the snapshot's lesson.building passes")
  ok(g.admit(ev('status', { state: 'thinking', detail: 'Building your lesson' })), 'carried build: its thinking passes once the build is back')
  ok(!g.admit(replayOf('old')), 'carried build: a replay of an old lesson is dropped')
  ok(!g.admit(ev('step.started', { stepId: 's3', index: 2, title: 'Three', instructions: '' })), 'carried build: an old step is dropped')
  ok(g.admit(ready('built')), 'carried build: the fresh lesson.ready of the build passes')
  ok(g.state().lessonId === 'built' && !g.state().pending && !g.state().carried, "carried build: it is the run's lesson")
  ok(g.admit(ev('step.started', { stepId: 's1', index: 0, title: 'One', instructions: '' })), 'carried build: its step passes')
  // A failed build after the reconnect ends the wait.
  const f = new RunGuard()
  f.command(cmd('learn_url', { url: 'https://youtu.be/x' }))
  f.connected()
  ok(f.admit(ev('lesson.building', { message: 'x', progress: 0, failed: true })), 'carried build: the failure passes')
  ok(!f.state().pending && !f.admit(ready('late')), 'carried build: after the failure nothing is let in')
  // A start sent on the new connection may be answered with a replay (action resume, or a learn / library.start of
  // the lesson the engine is already running answers with its snapshot, replay: true).
  for (const start of [cmd('action', { kind: 'resume' }), cmd('library.start', { id: 'nn' }), cmd('learn', { query: 'build a neural network' })]) {
    const c = new RunGuard()
    c.command(cmd('learn', { query: 'x' }))
    c.connected()
    ok(!c.admit(replayOf('nn')), `${start.type} after a reconnect: the snapshot replay before it is dropped`)
    c.command(start)
    ok(!c.state().carried, `${start.type} after a reconnect: a start on the new connection`)
    ok(c.admit(replayOf('nn')), `${start.type} after a reconnect: its replay answer passes`)
  }
}

{
  // preflight: an old pick's card at launch is dropped; this run's learn_url / learn gets it; Build starts.
  const pre = ev('card', { kind: 'preflight', title: 'What this video is', body: 'Build it?', actions: ['build', 'pick_another'] })
  ok(!new RunGuard().admit(pre), 'preflight: an old pick at launch is dropped')
  const g = new RunGuard()
  g.command(cmd('learn_url', { url: 'https://youtu.be/x' }))
  ok(g.admit(pre), "preflight: this run's learn_url shows it")
  g.command(cmd('action', { kind: 'build' }))
  ok(g.state().pending, 'preflight: Build keeps a lesson on its way')
  ok(g.admit(ready('v')), 'preflight: the built lesson passes')
}

/** The kept lesson's events an engine may still send while this run's start is on its way (review round 3). */
const OLD_DURING: Incoming[] = [
  ev('step.started', { stepId: 's3', index: 2, title: 'Three', instructions: 'Type it' }),
  ev('check.updated', { stepId: 's3', checkId: 'c1', label: 'Runs', status: 'pending' }),
  ev('offtrack', { stepId: 's3', title: 'Not yet', body: 'Save the file' }),
  ev('spotlight', { rect: { x: 1, y: 2, w: 3, h: 4 }, caption: 'Here' }),
  ev('card', { kind: 'hint', stepId: 's3', title: 'Hint', body: 'Try this' }),
  ev('card', { kind: 'hint', title: 'Hint', body: 'Try this' }),
  ev('card', { kind: 'resume', title: 'Continue where you left off?', body: 'Lesson old · step 3', actions: ['resume', 'end_lesson'] }),
  ev('card', { kind: 'step', stepId: 's3', title: 'Save calc.py', body: 'Save it' }),
  ev('card', { kind: 'where', title: 'Where', body: 'Here' }),
  ev('video.play'),
  ev('video.seek', { t: 42, play: true }),
  ev('diagram', { kind: 'network', caption: 'Net', stepId: 's3', data: { layers: [1, 4, 1], activation: 'tanh', derivatives: [], residual: '' } }),
  ev('lesson.updated', { steps: [], complete: false }),
  ev('lesson.paused', { reason: 'editor_closed' }),
  ev('step.passed', { stepId: 's3' }),
  ev('metric', { runId: 'r', step: 1, name: 'm', value: 1 })
]
const label = (e: Incoming): string => `${e.type}${e.type === 'card' ? ` (${(e.payload as { kind: string }).kind})` : ''}`
const restsIdle = (g: RunGuard, e: Incoming): boolean => (g.filter(e)?.payload as { state?: string } | undefined)?.state === 'idle'

{
  // (a) A start on its way admits only its build traffic: the kept lesson's events stay out until this run's ready.
  for (const start of [cmd('learn', { query: 'sin(x)' }), cmd('learn', { query: 'x', mode: 'lesson' }), cmd('learn_url', { url: 'https://youtu.be/x' }), cmd('build_lesson', { resultIds: ['r1'] }), cmd('library.start', { id: 'nn' }), cmd('action', { kind: 'resume' })]) {
    const name = start.type === 'action' ? 'action resume' : start.type
    const g = new RunGuard()
    g.connected()
    for (const e of LESSON_SNAPSHOT) g.filter(e)
    g.command(start)
    for (const e of OLD_DURING) ok(!g.admit(e), `${name} on its way: the kept lesson's ${label(e)} is dropped`)
    ok(restsIdle(g, ev('status', { state: 'watching' })), `${name} on its way: the kept lesson's watching reaches the pill as idle`)
    ok(restsIdle(g, ev('status', { state: 'offtrack' })), `${name} on its way: its offtrack status as idle`)
    ok(!g.admit(ev('blocker', { kind: 'editor_closed', title: 'VS Code closed' })), `${name} on its way: a lesson blocker is dropped`)
    ok(g.admit(ev('search.result', { id: 'r1', kind: 'video', title: 'A', meta: '', score: 1, reason: '' })), `${name} on its way: search rows pass`)
    ok(g.admit(ev('card', { kind: 'preflight', title: 'What this video is', body: 'Build it?', actions: ['build', 'pick_another'] })), `${name} on its way: this run's preflight card passes`)
    ok(g.admit(ev('status', { state: 'thinking', detail: 'Building your lesson' })), `${name} on its way: the build's thinking passes`)
    ok(g.admit(ev('lesson.building', { message: 'Watching', progress: 0.3 })), `${name} on its way: lesson.building passes`)
    ok(g.admit(ev('error', { message: 'x' })) && g.admit(ev('blocker', { kind: 'network', title: 'Offline' })), `${name} on its way: errors and network blockers pass`)
    ok(g.state().pending && !g.state().lessonId, `${name} on its way: still waiting, no lesson`)
    for (const e of OLD_DURING) ok(!g.admit(e), `${name} building: the kept lesson's ${label(e)} is still dropped`)
    // (c) This run's lesson.ready: its own events pass from now on.
    ok(g.admit(ready('new')), `${name}: this run's lesson.ready passes`)
    for (const e of OLD_DURING) ok(g.admit(e), `${name} after its ready: the run's ${label(e)} passes`)
    ok(g.admit(ev('status', { state: 'watching' })), `${name} after its ready: watching passes as sent`)
  }
}

{
  // (b) An abandoned start expires: the kept lesson stays out for the rest of the run.
  const pre = ev('card', { kind: 'preflight', title: 'What this video is', body: 'Build it?', actions: ['build', 'pick_another'] })
  // The search ends and nothing is picked (also: the search failed, an error then search.done).
  for (const failedSearch of [false, true]) {
    const name = failedSearch ? 'failed search' : 'nothing picked'
    const g = new RunGuard()
    g.command(cmd('learn', { query: 'sin(x)' }))
    if (failedSearch) ok(g.admit(ev('error', { message: 'Search failed' })), `${name}: the error passes`)
    else ok(g.admit(ev('search.result', { id: 'r1', kind: 'video', title: 'A', meta: '', score: 1, reason: '' })), `${name}: rows pass`)
    ok(g.admit(ev('search.done', { total: failedSearch ? 0 : 1 })), `${name}: search.done passes`)
    ok(!g.state().pending, `${name}: the search's wait is over`)
    for (const e of OLD_DURING) ok(!g.admit(e), `${name}: the kept lesson's ${label(e)} is dropped`)
    ok(!g.admit(ready('old')), `${name}: a later lesson.ready of the kept lesson is dropped`)
    ok(!g.admit(ev('lesson.building', { message: 'x', progress: 0.1 })), `${name}: and no stray build`)
    ok(!g.admit(pre), `${name}: an old preflight card is dropped`)
  }
  // The learner picks a row after all: that pick is its own start.
  const p = new RunGuard()
  p.command(cmd('learn', { query: 'sin(x)' }))
  p.admit(ev('search.done', { total: 3 }))
  p.command(cmd('build_lesson', { resultIds: ['r1'] }))
  ok(p.admit(pre) && p.state().pending, 'a pick after search.done: its preflight passes, a lesson is on its way')
  // Pick another: back to the rows (the engine re-sends them and search.done): nothing on its way any more.
  p.command(cmd('action', { kind: 'pick_another' }))
  ok(p.admit(ev('search.done', { total: 3 })) && !p.state().pending, "pick another: the re-sent search.done ends the pick's wait")
  ok(!p.admit(ready('old')), 'pick another: a later old lesson.ready is dropped')
  // A pick before search.done (the engine cancels the search, so no search.done comes): the build is not a search.
  const q = new RunGuard()
  q.command(cmd('learn', { query: 'sin(x)' }))
  q.command(cmd('learn_url', { url: 'https://youtu.be/x' }))
  ok(q.admit(ev('search.done', { total: 1 })) && q.state().pending, "a pick: a late search.done does not end the pick's wait")
  // "Just teach me" builds at once: no search, search.done never ends it.
  const j = new RunGuard()
  j.command(cmd('learn', { query: 'x', mode: 'lesson' }))
  j.admit(ev('search.done', { total: 0 }))
  ok(j.state().pending, 'learn mode lesson: no search, the wait stays')
  // A learn whose engine builds at once (MIYAGI_STAGE): its build progress makes it a build.
  const s = new RunGuard()
  s.command(cmd('learn', { query: 'x' }))
  s.admit(ev('lesson.building', { message: 'x', progress: 0.1 }))
  ok(!s.state().searching && (s.admit(ev('search.done', { total: 0 })), s.state().pending), 'learn that builds: its build progress keeps the wait past a search.done')
  // library.start answered with an error.
  const l = new RunGuard()
  l.command(cmd('library.start', { id: 'gone' }))
  ok(l.admit(ev('error', { message: 'no such lesson' })) && !l.state().pending, 'library.start error: the wait is over')
  ok(!l.admit(ready('old')), 'library.start error: a later old lesson.ready is dropped')
  // learn_url's preflight error is followed by its build: the wait stays.
  const u = new RunGuard()
  u.command(cmd('learn_url', { url: 'https://youtu.be/x' }))
  ok(u.admit(ev('error', { message: "Couldn't check this video first; building it anyway." })) && u.state().pending, "learn_url: a preflight error keeps the build's wait")
  // A timeout: no sign of life for OPEN_TTL_MS.
  let t = 0
  const clock = (): number => t
  const o = new RunGuard(false, clock)
  o.command(cmd('learn_url', { url: 'https://youtu.be/x' }))
  t = OPEN_TTL_MS - 1
  ok(o.state().pending, 'timeout: just before it the wait stays')
  ok(o.admit(ev('lesson.building', { message: 'x', progress: 0.2 })), 'timeout: build progress passes')
  t += OPEN_TTL_MS - 1
  ok(o.state().pending, 'timeout: build progress kept it alive')
  t += 2
  ok(!o.state().pending, 'timeout: no sign of life for OPEN_TTL_MS ends the wait')
  ok(!o.admit(ready('old')) && !o.admit(ev('lesson.building', { message: 'x', progress: 0.3 })), 'timeout: an old lesson.ready and a stray build are dropped')
  // The preflight card waits for the learner (PICK_TTL_MS), then expires too.
  t = 0
  const w = new RunGuard(false, clock)
  w.command(cmd('build_lesson', { resultIds: ['r1'] }))
  w.admit(pre)
  t = PICK_TTL_MS - 1
  ok(w.state().pending, 'preflight: the learner may read the card for PICK_TTL_MS')
  t = PICK_TTL_MS + 1
  ok(!w.state().pending, 'preflight: after PICK_TTL_MS the wait is over')
  w.command(cmd('action', { kind: 'build' }))
  ok(w.state().pending && w.admit(ready('v')), 'preflight: Build later is a start of its own')
  // A carried build: the socket was down for long; the reconnect gives it time again.
  t = 0
  const c = new RunGuard(false, clock)
  c.command(cmd('build_lesson', { resultIds: ['r1'] }))
  t = OPEN_TTL_MS - 10
  c.connected()
  t = OPEN_TTL_MS + 10
  ok(c.admit(ev('lesson.building', { message: 'x', progress: 0.7 })) && c.state().pending, 'carried build: a reconnect gives it time to show its progress')
  // Armed runs (DEMO) never expire.
  t = 0
  const d = new RunGuard(true, clock)
  t = 10 * PICK_TTL_MS
  ok(d.admit(ready('demo')), 'DEMO (armed): the wait never expires')
}

{
  // asking: only presses the engine answers keep the pill's spinner; fire-and-forget ones rest it.
  for (const kind of ['voice_toggle', 'pick_another', 'download', 'open_in_browser', 'install', 'install_all', 'skip_setup', 'open_editor', 'back', 'confirm', 'undo', 'card.closed']) {
    const g = new RunGuard()
    g.command(kind === 'card.closed' ? cmd('card.closed', { title: 'x', by: 'user' }) : cmd('action', { kind, text: 'python' }))
    ok(!g.state().asking, `${kind}: waits for no answer`)
    ok(!g.admit(ev('status', { state: 'thinking', detail: 'Looking at your code' })), `${kind}: an old lesson's thinking stays out`)
    ok(restsIdle(g, ev('status', { state: 'watching' })), `${kind}: an old lesson's watching rests the pill`)
  }
  for (const kind of ['ask', 'explain', 'diagram', 'hint', 'show_me', 'retry', 'check_step']) {
    const g = new RunGuard()
    g.command(cmd('action', { kind, text: 'why' }))
    ok(g.state().asking, `${kind}: waits for its answer`)
  }
}

{
  // The pill never spins for an old lesson (Michael: "the top is not working"). Feed what passes into a pill the way
  // core/lesson.ts does (engineState = the last status) and check where it rests.
  const pill = (g: RunGuard, events: Incoming[]): { state: string; detail?: string } => {
    let st: { state: string; detail?: string } = { state: 'idle' }
    for (const e of events) {
      const out = g.filter(e)
      if (out?.type === 'status') st = out.payload as { state: string; detail?: string }
    }
    return st
  }
  const thinking = ev('status', { state: 'thinking', detail: 'Looking at your code' })
  const watching = ev('status', { state: 'watching' })
  ok(pill(new RunGuard(), [thinking, watching]).state === 'idle', "launch: an old lesson's thinking then watching leaves the pill idle")
  ok(pill(new RunGuard(), [watching, thinking]).state === 'idle', "launch: an old lesson's watching then thinking leaves the pill idle")
  ok(pill(new RunGuard(), [ev('status', { state: 'thinking', detail: 'Checking your work' })]).state === 'idle', "launch: a snapshot ending on thinking leaves the pill idle")
  ok(pill(new RunGuard(), [ev('status', { state: 'busy', retryInS: 3 }), ev('status', { state: 'passed' })]).state === 'idle', 'launch: busy then passed leaves the pill idle')
  ok(new RunGuard().filter(watching)?.type === 'status' && (new RunGuard().filter(watching)?.payload as { state: string }).state === 'idle', 'launch: an old watching reaches the windows as idle')
  // A typed question with no lesson: its spinner shows and ends with its answer.
  const g = new RunGuard()
  g.command(cmd('action', { kind: 'ask', text: 'why' }))
  ok(g.admit(ev('status', { state: 'thinking', detail: 'Writing an answer' })), 'ask: its thinking shows')
  ok(!g.filter(watching), "ask: an old lesson's watching does not end the learner's spinner")
  ok(g.admit(ANSWER), 'ask: the answer card passes')
  ok(!g.state().asking, 'ask: the answer ends the wait')
  ok(pill(g, [thinking, watching]).state === 'idle', 'ask: afterwards an old thinking then watching leaves the pill idle')
  const x = new RunGuard()
  x.command(cmd('action', { kind: 'explain' }))
  x.admit(ev('error', { message: 'no key' }))
  ok(!x.state().asking && !x.admit(thinking), 'explain: an error ends the wait, a later old thinking is dropped')
  const y = new RunGuard()
  y.command(cmd('action', { kind: 'hint' }))
  y.connected()
  ok(!y.admit(thinking), 'a press sent on the old connection: its answer no longer comes, old thinking is dropped')
  // During the run's own lesson every status passes untouched.
  const l = new RunGuard()
  l.command(cmd('learn', { query: 'x' }))
  l.admit(ready('a'))
  ok(l.admit(thinking) && l.admit(watching), "run's lesson: thinking and watching pass as sent")
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
    sendAll(ws, [HELLO, LIBRARY, ...LESSON_SNAPSHOT.map((e) => (e.type === 'lesson.ready' ? replayOf(kept) : e)), ANSWER])
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
  const working = (list: Incoming[]): boolean => list.some((e) => e.type === 'status' && ['thinking', 'busy'].includes((e.payload as { state: string }).state))
  ok(!working(seen) && !working(link.log), "link: the old lesson's thinking / busy never reach the pill at launch")

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

  await openStartCheck(EngineLink)
  await offlineCheck(EngineLink)
  await carriedCheck(EngineLink)
  await replayEnvCheck(EngineLink)
  await vite.close()
}

/**
 * Review round 3: an engine that replays an old lesson on connect and keeps emitting its step events after `learn`.
 * None of them reach the listeners (every window) or engine.log before the new lesson's lesson.ready; the build's
 * own traffic does; after the new lesson.ready its own steps do.
 */
async function openStartCheck(EngineLink: typeof import('./engine').EngineLink): Promise<void> {
  const wss = new WebSocketServer({ host: '127.0.0.1', port: 0 })
  await new Promise<void>((r) => wss.once('listening', () => r()))
  const port = (wss.address() as { port: number }).port
  const NEW_STEP = ev('step.started', { stepId: 'n1', index: 0, title: 'New one', instructions: '' })
  wss.on('connection', (ws) => {
    for (const m of [HELLO, ...LESSON_SNAPSHOT, ANSWER]) ws.send(JSON.stringify(m))
    ws.on('message', (raw) => {
      if ((JSON.parse(String(raw)) as { type: string }).type !== 'learn') return
      const during = [...OLD_DURING, ev('status', { state: 'watching' }), ev('lesson.building', { message: 'Watching', progress: 0.2 }), ev('status', { state: 'thinking', detail: 'Building your lesson' }), ...OLD_DURING]
      for (const m of during) ws.send(JSON.stringify(m))
      // The new lesson lands a moment later.
      setTimeout(() => {
        for (const m of [ready('new'), NEW_STEP]) ws.send(JSON.stringify(m))
      }, 150)
    })
  })
  const link = new EngineLink(`ws://127.0.0.1:${port}`)
  const seen: Incoming[] = []
  link.onEvent((e) => seen.push(e))
  ok(await until(() => seen.some((e) => e.type === 'card')), 'open start: the engine connected')
  link.send({ type: 'learn', payload: { query: 'sin(x)' } })
  ok(await until(() => seen.some((e) => e.type === 'lesson.ready')), 'open start: the new lesson arrived')
  ok(await until(() => seen.some((e) => JSON.stringify(e) === JSON.stringify(NEW_STEP))), 'open start: and its own step')
  const at = seen.findIndex((e) => e.type === 'lesson.ready')
  const OLD = new Set([...OLD_DURING, ...LESSON_SNAPSHOT].map((e) => JSON.stringify(e)))
  const leaked = seen.slice(0, at).filter((e) => OLD.has(JSON.stringify(e)))
  ok(!leaked.length, `open start: no kept-lesson event reaches the windows before the new lesson.ready (got ${leaked.map(label).join(', ')})`)
  const logAt = link.log.findIndex((e) => e.type === 'lesson.ready')
  ok(!link.log.slice(0, logAt).some((e) => OLD.has(JSON.stringify(e))), 'open start: nor the replay log')
  ok(seen.slice(0, at).some((e) => e.type === 'lesson.building'), "open start: the build's progress reaches the windows")
  ok(!seen.slice(0, at).some((e) => e.type === 'status' && (e.payload as { state: string }).state === 'watching'), 'open start: no watching before the new lesson')
  ok((seen[at]?.payload as { lesson: { id: string } }).lesson.id === 'new', 'open start: the lesson that landed is the new one')
  for (const ws of wss.clients) ws.terminate()
  await new Promise<void>((r) => wss.close(() => r()))
}

/**
 * Starts sent while the engine is down never leave, so they must not let the next connect's old snapshot in:
 * (a) the launch window (localEngine still starting, no engine yet) and (b) an engine restart (update-engine.sh).
 * (c) A start that went out but was never answered: after a restart, the snapshot replay of an old lesson stays out.
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
      for (const m of [HELLO, ...LESSON_SNAPSHOT, ANSWER]) ws.send(JSON.stringify(m))
    })
    return wss
  }
  const down = async (wss: WebSocketServer): Promise<void> => {
    for (const ws of sockets) ws.terminate()
    await new Promise<void>((r) => wss.close(() => r()))
  }

  // Every event of the old snapshot, matched by value (card / status / diagram / blocker also have neutral forms).
  const OLD = new Set(LESSON_SNAPSHOT.map((e) => JSON.stringify(e)))
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

/** A free loopback port with nothing on it yet. */
async function freePort(): Promise<number> {
  const probe = new WebSocketServer({ host: '127.0.0.1', port: 0 })
  await new Promise<void>((r) => probe.once('listening', () => r()))
  const port = (probe.address() as { port: number }).port
  await new Promise<void>((r) => probe.close(() => r()))
  return port
}

/**
 * A long build survives a dropped socket while the engine stays up (sleep / wake): the new connection's snapshot
 * (thinking + lesson.building) and the build's final lesson.ready reach the windows.
 */
async function carriedCheck(EngineLink: typeof import('./engine').EngineLink): Promise<void> {
  const wss = new WebSocketServer({ host: '127.0.0.1', port: 0 })
  await new Promise<void>((r) => wss.once('listening', () => r()))
  const port = (wss.address() as { port: number }).port
  let building = false
  let socket: WebSocket | undefined
  const building1 = ev('lesson.building', { message: 'Writing checks', progress: 0.6 })
  wss.on('connection', (ws) => {
    socket = ws
    // Like session.py snapshot(): a build in progress replays as status thinking + lesson.building, nothing else.
    const snap = building ? [ev('status', { state: 'thinking', detail: 'Building your lesson' }), building1] : LESSON_SNAPSHOT
    for (const m of [HELLO, ...snap, ANSWER]) ws.send(JSON.stringify(m))
    ws.on('message', (raw) => {
      if ((JSON.parse(String(raw)) as { type: string }).type !== 'build_lesson') return
      building = true
      ws.send(JSON.stringify(ev('lesson.building', { message: 'Watching', progress: 0.1 })))
    })
  })
  const link = new EngineLink(`ws://127.0.0.1:${port}`)
  const seen: Incoming[] = []
  link.onEvent((e) => seen.push(e))
  ok(await until(() => seen.some((e) => e.type === 'card')), 'carried: the engine connected')
  link.send({ type: 'build_lesson', payload: { resultIds: ['r1'] } })
  ok(await until(() => seen.some((e) => e.type === 'lesson.building')), 'carried: the build started')
  seen.length = 0
  socket?.terminate()
  ok(await until(() => seen.some((e) => e.type === 'lesson.building'), 6000), "carried: after the reconnect the snapshot's lesson.building reaches the windows")
  // The build finishes on the new connection (no replay flag: a new lesson).
  socket?.send(JSON.stringify(ready('built')))
  ok(await until(() => seen.some((e) => e.type === 'lesson.ready')), "carried: the build's lesson.ready reaches the windows")
  ok(link.log.some((e) => e.type === 'lesson.ready'), 'carried: and the replay log')
  for (const ws of wss.clients) ws.terminate()
  await new Promise<void>((r) => wss.close(() => r()))
}

/**
 * MIYAGI_REPLAY_ON_CONNECT=1 (`npm run dev:all`): the mock replays a scenario lesson on every connect, on purpose,
 * and the dev app shows it. Without it (the shipped app) the same replay stays out.
 */
async function replayEnvCheck(EngineLink: typeof import('./engine').EngineLink): Promise<void> {
  const port = await freePort()
  const wss = new WebSocketServer({ host: '127.0.0.1', port })
  await new Promise<void>((r) => wss.once('listening', () => r()))
  wss.on('connection', (ws) => {
    for (const m of [HELLO, ready('scenario'), ev('step.started', { stepId: 's1', index: 0, title: 'One', instructions: '' }), ANSWER]) ws.send(JSON.stringify(m))
  })
  const before = process.env.MIYAGI_REPLAY_ON_CONNECT
  process.env.MIYAGI_REPLAY_ON_CONNECT = '1'
  const dev = new EngineLink(`ws://127.0.0.1:${port}`)
  if (before === undefined) delete process.env.MIYAGI_REPLAY_ON_CONNECT
  else process.env.MIYAGI_REPLAY_ON_CONNECT = before
  const seenDev: Incoming[] = []
  dev.onEvent((e) => seenDev.push(e))
  ok(await until(() => seenDev.some((e) => e.type === 'card')), 'dev:all: the mock connected')
  ok(seenDev.some((e) => e.type === 'lesson.ready') && seenDev.some((e) => e.type === 'step.started'), "dev:all (MIYAGI_REPLAY_ON_CONNECT=1): the scenario's connect lesson shows")
  const shipped = new EngineLink(`ws://127.0.0.1:${port}`)
  const seenShipped: Incoming[] = []
  shipped.onEvent((e) => seenShipped.push(e))
  ok(await until(() => seenShipped.some((e) => e.type === 'card')), 'shipped: connected')
  ok(!seenShipped.some((e) => e.type === 'lesson.ready' || e.type === 'step.started'), 'shipped (no env): the same replay stays out')
  for (const ws of wss.clients) ws.terminate()
  await new Promise<void>((r) => wss.close(() => r()))
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
