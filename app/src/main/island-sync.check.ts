/**
 * Node check, no Electron, no engine: the heartbeat and the coalescer.   npx tsx src/main/island-sync.check.ts
 * Exits 1 on any failure.
 */
import { Heartbeat } from './heartbeat'
import { coalesce } from './coalesce'

let bad = 0
const ok = (c: boolean, m: string): void => {
  if (!c) bad++
  console.log(`${c ? 'ok  ' : 'FAIL'} ${m}`)
}
const wait = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

async function main(): Promise<void> {
  // 1. A silent peer is declared dead within deadMs + one tick; pongs keep it alive.
  let pings = 0
  let dead = 0
  const silent = new Heartbeat({ ping: () => pings++, dead: () => dead++ }, 20, 70)
  silent.start()
  await wait(200)
  ok(dead === 1, `silent socket declared dead once (dead=${dead})`)
  ok(pings >= 2, `pinged before dying (pings=${pings})`)
  const t0 = Date.now()
  let d2 = 0
  const live = new Heartbeat({ ping: () => live.alive(), dead: () => d2++ }, 20, 70)
  live.start()
  await wait(250)
  live.stop()
  ok(d2 === 0, `answering socket never declared dead (${Date.now() - t0} ms)`)

  // 2. probe(): a wake with no answer fails fast, with an answer does not.
  let d3 = 0
  const p1 = new Heartbeat({ ping: () => undefined, dead: () => d3++ }, 1000, 5000)
  p1.start()
  p1.probe(40)
  await wait(100)
  ok(d3 === 1, 'probe with no answer -> dead after the probe window')
  let d4 = 0
  const p2 = new Heartbeat({ ping: () => setTimeout(() => p2.alive(), 5), dead: () => d4++ }, 1000, 5000)
  p2.start()
  p2.probe(40)
  await wait(100)
  p2.stop()
  ok(d4 === 0, 'probe answered -> still alive')

  // 3. coalesce: a burst of 200 window-move events becomes a handful of sends carrying the last value.
  const got: number[] = []
  const c = coalesce<number>((v) => got.push(v), 30)
  for (let i = 0; i < 200; i++) {
    c.push(i)
    if (i % 50 === 49) await wait(35)
  }
  await wait(50)
  ok(got.length <= 5 && got[got.length - 1] === 199, `200 pushes -> ${got.length} runs, last value kept (${got.join(',')})`)
  console.log(`BURST pushed=${c.stats.pushed} ran=${c.stats.ran}`)
  process.exit(bad ? 1 : 0)
}
void main()
