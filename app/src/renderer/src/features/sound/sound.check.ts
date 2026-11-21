/**
 * Feature: sound. A Node check, no audio device, nothing played:
 *
 *   npx tsx src/renderer/src/features/sound/sound.check.ts      (from app/)
 *
 * Renders every cue at 44.1 and 48 kHz and checks: peak under -24 dBFS, duration under 250 ms, starts and ends on
 * silence (no click), no DC, finite samples, deterministic. Then drives the gate on a fake clock: off by default, one
 * cue per 400 ms, never during typing, Do Not Disturb, taps sub-toggle, a held done outranking a tick, stale drop, and
 * typing in another app (a fake system idle clock, as main's sound:idle reports it).
 * Finally the main process's Do Not Disturb parse. Exits 1 on the first failure.
 */
import { focusOn } from '../../../../main/features/sound'
import { createGate, MAX_WAIT_MS, MIN_GAP_MS, SYSTEM_BUSY_S, TYPING_QUIET_MS, withSystemIdle, type Gate, type GateEnv } from './gate'
import { CUES, gainToDb, MAX_DURATION_MS, MAX_PEAK_DBFS, peakOf, renderCue, type Cue } from './synth'

let failed = 0
let passed = 0
function ok(cond: unknown, what: string): void {
  if (cond) passed++
  else {
    failed++
    console.error(`FAIL ${what}`)
  }
}

// ---- buffers -------------------------------------------------------------------------------------------------------

const rows: string[] = []
for (const rate of [44100, 48000]) {
  for (const cue of Object.keys(CUES) as Cue[]) {
    const buf = renderCue(cue, rate)
    const ms = (buf.length / rate) * 1000
    const peakDb = gainToDb(peakOf(buf))
    let sum = 0
    let finite = true
    for (const s of buf) {
      sum += s
      if (!Number.isFinite(s)) finite = false
    }
    const dc = Math.abs(sum / buf.length)
    const edge = Math.max(Math.abs(buf[0]), Math.abs(buf[buf.length - 1]))
    const again = renderCue(cue, rate)
    rows.push(`${cue.padEnd(5)} ${String(rate).padEnd(6)} ${ms.toFixed(1).padStart(6)} ms  peak ${peakDb.toFixed(2).padStart(7)} dBFS  dc ${dc.toExponential(1)}`)
    ok(finite, `${cue}@${rate}: finite samples`)
    ok(ms > 0 && ms < MAX_DURATION_MS, `${cue}@${rate}: duration ${ms.toFixed(1)} ms < ${MAX_DURATION_MS}`)
    ok(peakDb <= MAX_PEAK_DBFS, `${cue}@${rate}: peak ${peakDb.toFixed(2)} dBFS <= ${MAX_PEAK_DBFS}`)
    ok(Math.abs(peakDb - CUES[cue].peakDbfs) < 0.01, `${cue}@${rate}: peak lands on its level`)
    ok(edge < 1e-3 * peakOf(buf) + 1e-9, `${cue}@${rate}: starts and ends on silence`)
    ok(dc < 0.02 * peakOf(buf), `${cue}@${rate}: no DC offset`)
    ok(again.every((s, i) => s === buf[i]), `${cue}@${rate}: deterministic`)
  }
}
ok(CUES.tap.peakDbfs < CUES.tick.peakDbfs && CUES.tick.peakDbfs < CUES.done.peakDbfs, 'loudness order: tap < tick < done')
ok(CUES.done.notes.length === 2 && CUES.done.notes[1].freq > CUES.done.notes[0].freq, 'done is two rising notes')

// ---- gate ----------------------------------------------------------------------------------------------------------

function on(now: number, extra: Partial<GateEnv> = {}): GateEnv {
  return { now, enabled: true, taps: false, typingAt: 0, dnd: false, ...extra }
}
{
  const g = createGate()
  const v = g.ask('tick', { ...on(1000), enabled: false })
  ok(!v.play && v.reason === 'off', 'off by default plays nothing')
}
{
  const g = createGate()
  ok(g.ask('tick', on(1000)).play, 'tick plays')
  const v = g.ask('tick', on(1000 + 100))
  ok(!v.play && v.reason === 'held' && v.retryInMs === MIN_GAP_MS - 100, 'second tick inside 400 ms waits for the gap')
  ok(!g.ask('tick', on(1000 + MIN_GAP_MS - 1), 1100).play, 'still not before 400 ms')
  ok(g.ask('tick', on(1000 + MIN_GAP_MS), 1100).play, 'plays at exactly 400 ms')
}
{
  const g = createGate()
  g.ask('tick', on(0))
  const t = g.ask('tap', { ...on(50), taps: true })
  ok(!t.play && t.reason === 'gap', 'a tap inside the gap is dropped, not held')
  ok(!g.ask('tap', on(1000)).play, 'taps need the sub-toggle')
  ok(g.ask('tap', { ...on(1000), taps: true }).play, 'tap plays with the sub-toggle')
}
{
  const g = createGate()
  const v = g.ask('tick', on(5000, { typingAt: 4800 }))
  ok(!v.play && v.reason === 'held' && v.retryInMs === 4800 + TYPING_QUIET_MS - 5000, 'tick waits for typing to stop')
  ok(!g.ask('tap', on(5000, { typingAt: 4800, taps: true })).play, 'no tap while typing')
  ok(g.ask('tick', on(4800 + TYPING_QUIET_MS, { typingAt: 4800 }), 5000).play, 'tick plays once typing is quiet')
}
{
  const g = createGate()
  const v = g.ask('done', on(0, { typingAt: 1 }), -MAX_WAIT_MS)
  ok(!v.play && v.reason === 'stale', 'a cue that waited too long is dropped')
}
{
  const g = createGate()
  const v = g.ask('done', on(9000, { dnd: true }))
  ok(!v.play && v.reason === 'dnd', 'Do Not Disturb plays nothing')
}
{
  const g = createGate()
  g.ask('tick', on(0))
  g.ask('tick', on(100)) // held
  g.ask('done', on(150)) // outranks the held tick
  ok(g.pending()?.cue === 'done', 'a done replaces a waiting tick')
  const t = g.ask('tick', on(200))
  ok(!t.play && t.reason === 'outranked', 'a tick never jumps a waiting done')
  ok(g.ask('done', on(MIN_GAP_MS), 150).play && g.pending() === undefined, 'the done plays at the gap, nothing left waiting')
}
{
  const g = createGate()
  g.note(10_000) // another window played
  const v = g.ask('tick', on(10_100))
  ok(!v.play && v.reason === 'held', 'the gap counts across windows')
}
{
  // Never overlapping: in any run of cues the gap between plays is >= 400 ms and every cue is < 250 ms.
  const g = createGate()
  const plays: number[] = []
  for (let t = 0; t < 5000; t += 37) {
    const cue: Cue = t % 3 === 0 ? 'done' : t % 3 === 1 ? 'tick' : 'tap'
    if (g.ask(cue, on(t, { taps: true })).play) plays.push(t)
  }
  ok(plays.length > 5 && plays.every((t, i) => i === 0 || t - plays[i - 1] >= MIN_GAP_MS), 'a burst never plays two cues within 400 ms')
  ok(Math.max(...Object.values(CUES).map((c) => c.durationMs)) < MIN_GAP_MS, 'every cue ends before the next may start')
}

// ---- typing in another app: a fake system idle clock (main's sound:idle) -------------------------------------------

/**
 * Drives one engine cue the way store.ts does: ask with the system idle folded in, and on "held" re-ask after
 * retryInMs with the original bornAt. `busyUntil`: the learner types in VS Code until then (whole-second idle, like
 * powerMonitor.getSystemIdleTime). Returns when it played (or undefined) and the verdicts on the way.
 */
function drive(g: Gate, cue: Cue, bornAt: number, busyUntil: number): { playedAt?: number; reasons: string[] } {
  const idleAt = (t: number): number => (t < busyUntil ? 0 : Math.floor((t - busyUntil) / 1000) + 1)
  const reasons: string[] = []
  let t = bornAt
  for (let i = 0; i < 20; i++) {
    const v = g.ask(cue, withSystemIdle(on(t), idleAt(t)), bornAt)
    reasons.push(v.play ? 'play' : v.reason)
    if (v.play) return { playedAt: t, reasons }
    if (v.reason !== 'held') return { reasons }
    t += v.retryInMs
  }
  return { reasons }
}
{
  ok(withSystemIdle(on(5000), 0).typingAt === 5000, 'system input in the last second counts as typing now')
  ok(withSystemIdle(on(5000), SYSTEM_BUSY_S).typingAt === 0, 'a second of system idle is not typing')
  ok(withSystemIdle(on(5000), undefined).typingAt === 0 && withSystemIdle(on(5000), NaN).typingAt === 0, 'an unreadable idle time changes nothing')
  ok(withSystemIdle(on(5000, { typingAt: 4000 }), 30).typingAt === 4000, 'idle keeps the miyagi keystroke time')
}
{
  const g = createGate()
  const r = drive(g, 'tick', 10_000, 10_000 + 60_000) // typing in the editor the whole time
  ok(r.playedAt === undefined && r.reasons[0] === 'held' && r.reasons[r.reasons.length - 1] === 'stale', 'a tick while typing in another app waits, then drops')
  ok(g.pending() === undefined, 'nothing left waiting after the drop')
  ok(r.reasons.filter((x) => x === 'held').length * TYPING_QUIET_MS <= MAX_WAIT_MS, 'dropped within MAX_WAIT_MS')
}
{
  const g = createGate()
  const r = drive(g, 'done', 20_000, 20_500) // the learner stops half a second after the pass
  ok(r.playedAt !== undefined && r.playedAt - 20_000 <= MAX_WAIT_MS && r.playedAt >= 20_500, 'a done plays once the system goes quiet')
}
{
  const g = createGate()
  const r = drive(g, 'tick', 30_000, 0) // idle for a long time
  ok(r.playedAt === 30_000, 'an idle system plays the tick at once')
}

// ---- Do Not Disturb parse (main) -----------------------------------------------------------------------------------

ok(focusOn({ data: [{ storeAssertionRecords: [{ assertionDetails: { assertionDetailsModeIdentifier: 'com.apple.donotdisturb.mode.default' } }] }] }), 'a Focus assertion reads as on')
ok(!focusOn({ data: [{ storeAssertionRecords: [] }] }), 'no assertion reads as off')
ok(!focusOn({ data: [{}] }) && !focusOn(null) && !focusOn('x'), 'an unknown shape reads as off (ignore)')

console.log(rows.join('\n'))
console.log(`\nsound check: ${passed} passed, ${failed} failed`)
if (failed) process.exit(1)
