/**
 * Feature: sound. A Node check, no audio device, nothing played:
 *
 *   npx tsx src/renderer/src/features/sound/sound.check.ts      (from app/)
 *
 * Renders every cue at 44.1 and 48 kHz and checks: peak under -24 dBFS, duration under 250 ms, starts and ends on
 * silence (no click), no DC, finite samples, deterministic. Then drives the gate on a fake clock: off by default, one
 * cue per 400 ms, never during typing, Do Not Disturb, taps sub-toggle, a held done outranking a tick, stale drop, a
 * second pass keeping the first one's wait, and typing in another app (a fake whole-second system idle clock, as main's
 * sound:idle reports it, sampled every SYSTEM_POLL_MS while held), plus the store's lesson-reset generation guard.
 * Finally the main process's Do Not Disturb parse. Exits 1 on the first failure.
 */
import { focusOn } from '../../../../main/features/sound'
import { createGate, MAX_WAIT_MS, MIN_GAP_MS, SYSTEM_BUSY_S, SYSTEM_POLL_MS, TYPING_QUIET_MS, withSystemIdle, type Gate, type GateEnv } from './gate'
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
  // An equal cue keeps the first: a second pass while a tick is held never stretches the wait past MAX_WAIT_MS.
  const g = createGate()
  ok(!g.ask('tick', on(1000, { typingAt: 1000 })).play && g.pending()?.bornAt === 1000, 'a tick held by typing')
  const v = g.ask('tick', on(1500, { typingAt: 1400 }))
  ok(!v.play && v.reason === 'held' && g.pending()?.bornAt === 1000, 'a second tick keeps the first bornAt')
  const w = g.ask('tick', on(2000, { typingAt: 2000 })) // would wait until 3200: 2.2 s after the first pass, fine
  ok(!w.play && w.reason === 'held' && g.pending()?.bornAt === 1000, 'still the first bornAt')
  const x = g.ask('tick', on(2400, { typingAt: 2400 })) // would wait until 3600: 2.6 s after the first pass
  ok(!x.play && x.reason === 'stale' && g.pending() === undefined, 'dropped MAX_WAIT_MS after the FIRST pass, not the newest')
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
 * retryInMs with the original bornAt. `lastInputAt`: the learner's last key or mouse input in another app (VS Code);
 * input continues up to then. Idle is whole seconds since it, like powerMonitor.getSystemIdleTime. Returns when it
 * played (or undefined), when it was dropped, and the verdicts on the way.
 */
function drive(g: Gate, cue: Cue, bornAt: number, lastInputAt: number): { playedAt?: number; droppedAt?: number; reasons: string[] } {
  const idleAt = (t: number): number => (t < lastInputAt ? 0 : Math.floor((t - lastInputAt) / 1000))
  const reasons: string[] = []
  let t = bornAt
  for (let i = 0; i < 40; i++) {
    const v = g.ask(cue, withSystemIdle(on(t), idleAt(t)), bornAt)
    reasons.push(v.play ? 'play' : v.reason)
    if (v.play) return { playedAt: t, reasons }
    if (v.reason !== 'held') return { droppedAt: t, reasons }
    t += v.retryInMs
  }
  return { reasons }
}
{
  ok(withSystemIdle(on(5000), 0).systemBusy === true, 'system input in the last second marks the system busy')
  ok(withSystemIdle(on(5000), 0).typingAt === 0, 'system input never moves the miyagi keystroke time (no fixed 1.2 s wait)')
  ok(!withSystemIdle(on(5000), SYSTEM_BUSY_S).systemBusy, 'a second of system idle is not busy')
  ok(!withSystemIdle(on(5000), undefined).systemBusy && !withSystemIdle(on(5000), NaN).systemBusy, 'an unreadable idle time changes nothing')
  ok(withSystemIdle(on(5000, { typingAt: 4000 }), 30).typingAt === 4000, 'idle keeps the miyagi keystroke time')
  const v = createGate().ask('tick', withSystemIdle(on(5000), 0))
  ok(!v.play && v.reason === 'held' && v.retryInMs === SYSTEM_POLL_MS, 'held by input elsewhere: asked again after SYSTEM_POLL_MS')
  const t = createGate().ask('tap', { ...withSystemIdle(on(5000), 0), taps: true })
  ok(!t.play && t.reason === 'typing', 'a tap is never held by input elsewhere')
  const k = createGate().ask('tick', on(5000, { typingAt: 4800 }))
  ok(!k.play && k.reason === 'held' && k.retryInMs === 4800 + TYPING_QUIET_MS - 5000, 'typing in a miyagi field keeps the fixed quiet wait')
}
{
  const g = createGate()
  const r = drive(g, 'tick', 10_000, 10_000 + 60_000) // typing in the editor the whole time
  ok(r.playedAt === undefined && r.reasons[0] === 'held' && r.reasons[r.reasons.length - 1] === 'stale', 'a tick while typing in another app waits, then drops')
  ok(g.pending() === undefined, 'nothing left waiting after the drop')
  ok(r.droppedAt !== undefined && r.droppedAt - 10_000 <= MAX_WAIT_MS, 'dropped within MAX_WAIT_MS of the pass')
  ok(r.reasons.filter((x) => x === 'held').length >= 8, 'several chances to play inside the 2.5 s window')
}
{
  // The usual case: the pass lands 0.3 s after the learner's last key (Cmd+S). The idle clock reads 1 at +0.7 s.
  const g = createGate()
  const pass = 40_000
  const r = drive(g, 'tick', pass, pass - 300)
  const after = r.playedAt === undefined ? undefined : r.playedAt - pass
  ok(after !== undefined && after <= 1000, `the tick lands within 1 s of the green (at +${after ?? '-'} ms)`)
  ok(after !== undefined && after >= 700, 'and not before the idle clock reads a quiet second')
}
{
  // Pointer moves at +1.2 s and +2.4 s (the old fixed sample times) no longer drop the tick: any quiet sample plays it.
  const g = createGate()
  const pass = 50_000
  const moves = [pass - 200, pass + 1200, pass + 2400]
  const idleAt = (t: number): number => Math.floor((t - Math.max(...moves.filter((m) => m <= t))) / 1000)
  let t = pass
  let playedAt: number | undefined
  for (let i = 0; i < 40 && playedAt === undefined; i++) {
    const v = g.ask('tick', withSystemIdle(on(t), idleAt(t)), pass)
    if (v.play) playedAt = t
    else if (v.reason === 'held') t += v.retryInMs
    else break
  }
  ok(playedAt !== undefined && playedAt < pass + 1200, 'a stray move at the old sample times does not drop the tick')
}
{
  const g = createGate()
  const r = drive(g, 'done', 20_000, 20_500) // the learner stops half a second after the pass
  ok(r.playedAt !== undefined && r.playedAt - 20_000 <= MAX_WAIT_MS && r.playedAt >= 21_500, 'a done plays once the system goes quiet')
  ok(r.playedAt !== undefined && r.playedAt - 21_500 < SYSTEM_POLL_MS, 'within one poll of the quiet second')
}
{
  const g = createGate()
  const r = drive(g, 'tick', 30_000, 0) // idle for a long time
  ok(r.playedAt === 30_000, 'an idle system plays the tick at once')
}
{
  // Input elsewhere inside the 400 ms gap: the retry waits for the gap, not just one poll.
  const g = createGate()
  ok(g.ask('done', on(60_000)).play, 'a done plays')
  const v = g.ask('tick', withSystemIdle(on(60_050), 0))
  ok(!v.play && v.reason === 'held' && v.retryInMs === MIN_GAP_MS - 50, 'input elsewhere inside the gap waits for the gap')
}

// ---- store: the lesson-reset generation guard ----------------------------------------------------------------------

{
  // store.ts: request() captures the generation, onUi('reset') bumps it, and a sound:idle answer that lands after the
  // reset returns before asking the gate. Mirrored here on a fresh gate: without the guard the old tick would play.
  let generation = 0
  const g = createGate()
  const played: number[] = []
  const decide = (gen: number, now: number, bornAt: number): void => {
    if (gen !== generation) return
    if (g.ask('tick', on(now), bornAt).play) played.push(now)
  }
  const gen = generation // request() at the pass, 70_000; sound:idle is in flight
  generation++ // onUi('reset'): the next lesson
  g.reset()
  ok(g.ask('tick', on(71_000), 70_000).play && g.reset() === undefined, 'unguarded, the reset gate would play the old tick')
  decide(gen, 71_000, 70_000) // the old answer arrives in the new lesson
  ok(played.length === 0, 'an idle answer from before a reset never plays in the next lesson')
  decide(generation, 71_000, 71_000)
  ok(played.length === 1, 'a fresh cue after the reset still plays')
}

// ---- Do Not Disturb parse (main) -----------------------------------------------------------------------------------

ok(focusOn({ data: [{ storeAssertionRecords: [{ assertionDetails: { assertionDetailsModeIdentifier: 'com.apple.donotdisturb.mode.default' } }] }] }), 'a Focus assertion reads as on')
ok(!focusOn({ data: [{ storeAssertionRecords: [] }] }), 'no assertion reads as off')
ok(!focusOn({ data: [{}] }) && !focusOn(null) && !focusOn('x'), 'an unknown shape reads as off (ignore)')

console.log(rows.join('\n'))
console.log(`\nsound check: ${passed} passed, ${failed} failed`)
if (failed) process.exit(1)
